"""
Unit tests for AI Key Pool — round-robin, health tracking, failover.
No external dependencies (no AI keys, no network calls).
"""

import time
import threading
import pytest

from ai_key_pool import APIKeyState, KeyPool, get_next_ai_credentials


# ---------------------------------------------------------------------------
# APIKeyState tests
# ---------------------------------------------------------------------------

class TestAPIKeyState:
    def test_key_suffix_hides_full_key(self):
        state = APIKeyState(key="sk-abcdef123456", provider="openai", model="gpt-5-mini")
        assert state.key_suffix == "...123456"
        assert "abcdef" not in state.key_suffix

    def test_key_suffix_short_key(self):
        state = APIKeyState(key="short", provider="openai", model="gpt-5-mini")
        assert state.key_suffix == "***"  # Keys <= 6 chars are fully masked

    def test_is_available_healthy(self):
        state = APIKeyState(key="sk-test", provider="openai", model="gpt-5-mini")
        assert state.is_available() is True

    def test_is_available_unhealthy(self):
        state = APIKeyState(key="sk-test", provider="openai", model="gpt-5-mini", is_healthy=False)
        assert state.is_available() is False

    def test_is_available_rate_limited(self):
        state = APIKeyState(
            key="sk-test", provider="openai", model="gpt-5-mini",
            rate_limited_until=time.time() + 60
        )
        assert state.is_available() is False

    def test_is_available_rate_limit_expired(self):
        state = APIKeyState(
            key="sk-test", provider="openai", model="gpt-5-mini",
            rate_limited_until=time.time() - 1
        )
        assert state.is_available() is True


# ---------------------------------------------------------------------------
# KeyPool tests
# ---------------------------------------------------------------------------

class TestKeyPool:
    def test_register_single_key(self):
        pool = KeyPool()
        pool.register_keys("openai", ["sk-key1"], "gpt-5-mini")
        assert pool.has_provider("openai")

    def test_register_multiple_keys(self):
        pool = KeyPool()
        pool.register_keys("openai", ["sk-key1", "sk-key2", "sk-key3"], "gpt-5-mini")
        stats = pool.get_stats()
        assert stats["openai"]["total_keys"] == 3

    def test_register_ignores_empty_strings(self):
        pool = KeyPool()
        pool.register_keys("openai", ["sk-key1", "", "  ", "sk-key2"], "gpt-5-mini")
        stats = pool.get_stats()
        assert stats["openai"]["total_keys"] == 2

    def test_no_provider_returns_none(self):
        pool = KeyPool()
        assert pool.get_next_key("openai") is None

    def test_round_robin(self):
        pool = KeyPool()
        pool.register_keys("openai", ["sk-aaa111", "sk-bbb222", "sk-ccc333"], "gpt-5-mini")

        keys_seen = []
        for _ in range(6):
            state = pool.get_next_key("openai")
            keys_seen.append(state.key)

        # Should cycle through all 3 keys twice
        assert keys_seen == [
            "sk-aaa111", "sk-bbb222", "sk-ccc333",
            "sk-aaa111", "sk-bbb222", "sk-ccc333",
        ]

    def test_report_success_resets_consecutive_errors(self):
        pool = KeyPool()
        pool.register_keys("openai", ["sk-test123"], "gpt-5-mini")

        state = pool.get_next_key("openai")
        state.consecutive_errors = 2

        pool.report_success(state)
        assert state.consecutive_errors == 0
        assert state.requests_count == 1
        assert state.is_healthy is True

    def test_report_error_rate_limit_applies_backoff(self):
        pool = KeyPool()
        pool.register_keys("openai", ["sk-test123"], "gpt-5-mini")

        state = pool.get_next_key("openai")
        pool.report_error(state, is_rate_limit=True)

        # Should be rate-limited for ~30s (first backoff level)
        assert state.rate_limited_until > time.time()
        assert state.errors_count == 1

    def test_report_error_consecutive_marks_unhealthy(self):
        pool = KeyPool(unhealthy_threshold=3)
        pool.register_keys("openai", ["sk-test123"], "gpt-5-mini")

        state = pool.get_next_key("openai")

        # 3 consecutive errors should mark unhealthy
        for _ in range(3):
            pool.report_error(state, is_rate_limit=False)

        assert state.is_healthy is False
        assert state.consecutive_errors == 3

    def test_unhealthy_key_skipped(self):
        pool = KeyPool(unhealthy_threshold=2, recovery_seconds=9999)
        pool.register_keys("openai", ["sk-bad000", "sk-good00"], "gpt-5-mini")

        # Get first key and mark it unhealthy
        state1 = pool.get_next_key("openai")
        assert state1.key == "sk-bad000"
        pool.report_error(state1, is_rate_limit=False)
        pool.report_error(state1, is_rate_limit=False)  # threshold=2 -> unhealthy
        assert state1.is_healthy is False

        # Next call should skip unhealthy key and return the good one
        state2 = pool.get_next_key("openai")
        assert state2.key == "sk-good00"

    def test_all_keys_unhealthy_returns_none(self):
        pool = KeyPool(unhealthy_threshold=1, recovery_seconds=9999)
        pool.register_keys("openai", ["sk-bad1xx", "sk-bad2xx"], "gpt-5-mini")

        for _ in range(2):
            state = pool.get_next_key("openai")
            pool.report_error(state, is_rate_limit=False)

        # Both keys unhealthy, recovery not yet
        assert pool.get_next_key("openai") is None

    def test_auto_recovery(self):
        pool = KeyPool(unhealthy_threshold=1, recovery_seconds=0)  # instant recovery
        pool.register_keys("openai", ["sk-recov1"], "gpt-5-mini")

        state = pool.get_next_key("openai")
        pool.report_error(state, is_rate_limit=False)
        assert state.is_healthy is False

        # With recovery_seconds=0, it should auto-recover immediately
        recovered = pool.get_next_key("openai")
        assert recovered is not None
        assert recovered.is_healthy is True
        assert recovered.consecutive_errors == 0

    def test_rate_limited_key_skipped_then_available(self):
        pool = KeyPool()
        pool.register_keys("openai", ["sk-ratelm"], "gpt-5-mini")

        state = pool.get_next_key("openai")
        # Simulate rate limit that's already expired
        state.rate_limited_until = time.time() - 1

        # Should still be available
        state2 = pool.get_next_key("openai")
        assert state2 is not None

    def test_get_all_providers(self):
        pool = KeyPool()
        pool.register_keys("openai", ["sk-oai001"], "gpt-5-mini")
        pool.register_keys("anthropic", ["sk-ant01"], "claude-haiku-4-5")

        providers = pool.get_all_providers()
        assert "openai" in providers
        assert "anthropic" in providers

    def test_get_all_providers_excludes_unhealthy(self):
        pool = KeyPool(unhealthy_threshold=1, recovery_seconds=9999)
        pool.register_keys("openai", ["sk-oai001"], "gpt-5-mini")
        pool.register_keys("anthropic", ["sk-ant01"], "claude-haiku-4-5")

        # Mark openai key unhealthy
        state = pool.get_next_key("openai")
        pool.report_error(state, is_rate_limit=False)

        providers = pool.get_all_providers()
        assert "openai" not in providers
        assert "anthropic" in providers

    def test_has_provider(self):
        pool = KeyPool()
        pool.register_keys("openai", ["sk-key001"], "gpt-5-mini")
        assert pool.has_provider("openai") is True
        assert pool.has_provider("anthropic") is False

    def test_get_stats_structure(self):
        pool = KeyPool()
        pool.register_keys("openai", ["sk-key001", "sk-key002"], "gpt-5-mini")

        state = pool.get_next_key("openai")
        pool.report_success(state)

        stats = pool.get_stats()
        assert "openai" in stats
        assert stats["openai"]["total_keys"] == 2
        assert stats["openai"]["healthy_keys"] == 2
        assert len(stats["openai"]["keys"]) == 2

        # Verify key data structure
        key_info = stats["openai"]["keys"][0]
        assert "key_suffix" in key_info
        assert "model" in key_info
        assert "requests" in key_info
        assert "errors" in key_info
        assert "is_healthy" in key_info
        assert "is_available" in key_info
        assert "rate_limited_remaining_s" in key_info

    def test_exponential_backoff_increases(self):
        pool = KeyPool()
        pool.register_keys("openai", ["sk-backof"], "gpt-5-mini")

        state = pool.get_next_key("openai")

        # First rate limit: 30s
        pool.report_error(state, is_rate_limit=True)
        backoff1 = state.rate_limited_until - time.time()

        # Second rate limit: 60s
        state.rate_limited_until = 0  # Reset for test
        pool.report_error(state, is_rate_limit=True)
        backoff2 = state.rate_limited_until - time.time()

        # Third rate limit: 120s
        state.rate_limited_until = 0
        pool.report_error(state, is_rate_limit=True)
        backoff3 = state.rate_limited_until - time.time()

        assert backoff1 < backoff2 < backoff3
        # Verify roughly: 30, 60, 120
        assert 25 < backoff1 < 35
        assert 55 < backoff2 < 65
        assert 115 < backoff3 < 125

    def test_backoff_capped_at_300(self):
        pool = KeyPool()
        pool.register_keys("openai", ["sk-capped"], "gpt-5-mini")

        state = pool.get_next_key("openai")

        # Simulate many rate limits
        for _ in range(10):
            state.rate_limited_until = 0  # Reset for each test
            pool.report_error(state, is_rate_limit=True)

        # Backoff should be capped at 300s
        backoff = state.rate_limited_until - time.time()
        assert backoff <= 305  # Allow small tolerance

    def test_thread_safety(self):
        """Verify KeyPool is safe under concurrent access"""
        pool = KeyPool()
        pool.register_keys("openai", ["sk-t1xxxx", "sk-t2xxxx", "sk-t3xxxx"], "gpt-5-mini")

        results = []
        errors = []

        def worker():
            try:
                for _ in range(100):
                    state = pool.get_next_key("openai")
                    if state:
                        pool.report_success(state)
                        results.append(state.key)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(results) == 1000  # 10 threads * 100 iterations


# ---------------------------------------------------------------------------
# get_next_ai_credentials tests
# ---------------------------------------------------------------------------

class TestGetNextAICredentials:
    def test_returns_preferred_provider(self):
        pool = KeyPool()
        pool.register_keys("openai", ["sk-oaikey"], "gpt-5-mini")
        pool.register_keys("anthropic", ["sk-antkey"], "claude-haiku-4-5")

        provider, key, model = get_next_ai_credentials(pool, preferred_provider="openai")
        assert provider == "openai"
        assert key == "sk-oaikey"
        assert model == "gpt-5-mini"

    def test_fallback_when_preferred_unavailable(self):
        pool = KeyPool(unhealthy_threshold=1, recovery_seconds=9999)
        pool.register_keys("openai", ["sk-oaikey"], "gpt-5-mini")
        pool.register_keys("anthropic", ["sk-antkey"], "claude-haiku-4-5")

        # Mark openai key unhealthy
        state = pool.get_next_key("openai")
        pool.report_error(state, is_rate_limit=False)

        provider, key, model = get_next_ai_credentials(pool, preferred_provider="openai")
        assert provider == "anthropic"
        assert key == "sk-antkey"

    def test_raises_when_no_keys(self):
        pool = KeyPool()
        with pytest.raises(ValueError, match="No AI API keys available"):
            get_next_ai_credentials(pool, preferred_provider="openai")

    def test_no_preferred_provider(self):
        pool = KeyPool()
        pool.register_keys("anthropic", ["sk-antkey"], "claude-haiku-4-5")

        provider, key, model = get_next_ai_credentials(pool)
        assert provider == "anthropic"
