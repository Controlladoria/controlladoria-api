"""
AI package — conversational financial advisor.

Separate from `structured_processor.py` (document extraction) because chat has
different needs: streaming, multi-turn history, stronger models, and a context
built from *calculated reports* rather than raw document bytes.

Shares the extraction pipeline's `ai_key_pool.KeyPool` for round-robin key
rotation, health tracking and provider failover.
"""

from .providers import AdvisorProviderManager, ProviderAdapter, get_provider_manager

__all__ = [
    "AdvisorProviderManager",
    "ProviderAdapter",
    "get_provider_manager",
]
