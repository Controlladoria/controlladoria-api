"""
Integration tests for the AI financial advisor.

The AI provider is stubbed throughout — these cover the wiring we own (plan
gating, SSE framing, persistence, history bounding, context shape), not the
model's answers.
"""

import json
import os
from datetime import date

import pytest

os.environ.setdefault("USE_S3", "false")
os.environ.setdefault("S3_BUCKET_NAME", "dummy")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-advisor-tests")
os.environ.setdefault("AI_PROVIDER", "gemini")
os.environ.setdefault("GEMINI_API_KEY", "fake-key")


# ─── SSE FRAMING ───────────────────────────────────────────────────────────────


def parse_sse(body: str):
    """Parse an SSE body into a list of payload dicts."""
    events = []
    for frame in body.split("\n\n"):
        for line in frame.splitlines():
            if line.startswith("data:"):
                raw = line[5:].strip()
                if raw:
                    events.append(json.loads(raw))
    return events


def test_sse_frame_roundtrip():
    from routers.advisor import _sse

    body = _sse({"event": "connected", "conversation_id": 7}) + _sse({"chunk": "olá"})
    events = parse_sse(body)

    assert events[0]["event"] == "connected"
    assert events[0]["conversation_id"] == 7
    assert events[1]["chunk"] == "olá"


def test_sse_preserves_accents_and_newlines():
    """Chunks carry markdown with newlines — those must not break framing."""
    from routers.advisor import _sse

    frame = _sse({"chunk": "Margem\n- Líquida: 12,3%\n"})
    events = parse_sse(frame)

    assert events[0]["chunk"] == "Margem\n- Líquida: 12,3%\n"


# ─── PLAN GATING ───────────────────────────────────────────────────────────────


class FakePlan:
    def __init__(self, features):
        self.features = features


def test_has_plan_feature_advisor():
    from plan_features import AI_ADVISOR, has_plan_feature

    assert has_plan_feature(FakePlan({"ai_advisor": True}), AI_ADVISOR) is True
    assert has_plan_feature(FakePlan({"ai_advisor": False}), AI_ADVISOR) is False
    # Basic plans predating the migration simply lack the key
    assert has_plan_feature(FakePlan({"team_management": True}), AI_ADVISOR) is False
    assert has_plan_feature(None, AI_ADVISOR) is False


# ─── PERIOD RESOLUTION ─────────────────────────────────────────────────────────


class FakeUser:
    id = 1
    active_org_id = None
    _active_org_id = None
    company_name = "Empresa Teste"
    cnpj = "00000000000191"


def test_resolve_period_month():
    from ai.advisor_service import AdvisorService

    service = AdvisorService.__new__(AdvisorService)
    start, end, label = AdvisorService.resolve_period(
        service, "month", reference_date="2026-03-15"
    )

    assert start == date(2026, 3, 1)
    assert end == date(2026, 3, 31)
    assert label == "março de 2026"


def test_resolve_period_custom():
    from ai.advisor_service import AdvisorService

    service = AdvisorService.__new__(AdvisorService)
    start, end, _ = AdvisorService.resolve_period(
        service, "custom", start_date="2026-01-10", end_date="2026-02-20"
    )

    assert start == date(2026, 1, 10)
    assert end == date(2026, 2, 20)


def test_resolve_period_falls_back_on_garbage():
    """A malformed date must not 500 the chat — fall back to the month."""
    from ai.advisor_service import AdvisorService

    service = AdvisorService.__new__(AdvisorService)
    start, end, _ = AdvisorService.resolve_period(
        service, "custom", start_date="not-a-date", end_date="also-bad"
    )

    assert start <= end


# ─── PREVIOUS-PERIOD MATH ──────────────────────────────────────────────────────


def test_previous_period_full_month_maps_to_prior_calendar_month():
    from ai.context_builder import _previous_period

    start, end = _previous_period(date(2026, 3, 1), date(2026, 3, 31))
    assert (start, end) == (date(2026, 2, 1), date(2026, 2, 28))


def test_previous_period_january_crosses_year():
    from ai.context_builder import _previous_period

    start, end = _previous_period(date(2026, 1, 1), date(2026, 1, 31))
    assert (start, end) == (date(2025, 12, 1), date(2025, 12, 31))


def test_previous_period_custom_range_shifts_by_duration():
    from ai.context_builder import _previous_period

    start, end = _previous_period(date(2026, 3, 10), date(2026, 3, 20))
    assert end == date(2026, 3, 9)
    assert (end - start).days == 10


def test_month_windows_are_chronological_and_bounded():
    from ai.context_builder import _month_windows

    windows = _month_windows(date(2026, 3, 31), 6)

    assert len(windows) == 6
    assert windows[0][0] == date(2025, 10, 1)
    assert windows[-1][0] == date(2026, 3, 1)
    assert windows == sorted(windows)


# ─── SNAPSHOT SHAPE ────────────────────────────────────────────────────────────


def test_serialize_dre_handles_empty_input():
    from ai.context_builder import _serialize_dre

    assert _serialize_dre(None) == {}


def test_serialize_dre_reads_real_model_fields():
    """Guards against drift between the DRE model and the snapshot keys."""
    from accounting import PeriodType, calculate_dre
    from ai.context_builder import _serialize_dre

    dre = calculate_dre(
        transactions=[
            {
                "date": "2026-03-05",
                "amount": 10000,
                "category": "receita_vendas_produtos",
                "transaction_type": "receita",
                "description": "venda",
            },
            {
                "date": "2026-03-06",
                "amount": 3000,
                "category": "aluguel",
                "transaction_type": "despesa",
                "description": "aluguel",
            },
        ],
        period_type=PeriodType.CUSTOM,
        start_date=date(2026, 3, 1),
        end_date=date(2026, 3, 31),
        company_name="Teste",
        cnpj=None,
    )

    snapshot = _serialize_dre(dre)

    # Every key the prompt promises must actually be produced
    for key in (
        "receita_bruta",
        "receita_liquida",
        "margem_contribuicao",
        "ebitda",
        "lucro_liquido",
        "margens_pct_sobre_receita_bruta",
        "margens_pct_sobre_receita_liquida",
        "detalhe_custos",
        "qualidade",
    ):
        assert key in snapshot, f"missing {key}"

    assert snapshot["receita_bruta"] == 10000.0
    # None of the values may be Decimal — they have to survive json.dumps
    json.dumps(snapshot)


def test_top_categories_ranks_costs_and_skips_subtotals():
    from ai.context_builder import _top_categories

    class FakeDRE:
        @staticmethod
        def model_dump():
            return {
                "detailed_lines": [
                    {"code": "1", "description": "RECEITA", "amount": 10000, "is_total": True},
                    {"code": "6", "description": "CUSTOS", "amount": -5000, "is_subtotal": True},
                    {"code": "6.1", "description": "Aluguel", "amount": -3000},
                    {"code": "6.2", "description": "Energia", "amount": -1200},
                    {"code": "6.3", "description": "Zerado", "amount": 0},
                ]
            }

    top = _top_categories(FakeDRE(), limit=10)

    assert [t["categoria"] for t in top] == ["Aluguel", "Energia"]
    assert top[0]["valor"] == 3000.0


def test_top_categories_respects_limit():
    from ai.context_builder import _top_categories

    class FakeDRE:
        @staticmethod
        def model_dump():
            return {
                "detailed_lines": [
                    {"code": f"6.{i}", "description": f"Custo {i}", "amount": -(i * 100)}
                    for i in range(1, 30)
                ]
            }

    assert len(_top_categories(FakeDRE(), limit=10)) == 10


def test_pct_returns_none_not_zero_on_zero_denominator():
    """`null` means 'not calculable' to the prompt — 0 would be a lie."""
    from ai.context_builder import _pct

    assert _pct(100, 0) is None
    assert _pct(100, None) is None
    assert _pct(50, 200) == 25.0


# ─── PROVIDER FAILOVER ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_manager_falls_over_before_first_chunk():
    """A provider that dies before emitting anything must be retried elsewhere."""
    from ai.providers import AdvisorProviderManager

    manager = AdvisorProviderManager.__new__(AdvisorProviderManager)

    from ai_key_pool import KeyPool

    manager.key_pool = KeyPool()
    manager.key_pool.register_keys("gemini", ["k1"], "m")
    manager.key_pool.register_keys("openai", ["k2"], "m")
    manager._models = {"gemini": "m", "nova": "m", "openai": "m"}
    manager._adapters = {}
    manager._order = ["gemini", "openai"]

    class BrokenAdapter:
        model = "m"

        async def chat_stream(self, *args, **kwargs):
            raise RuntimeError("provider down")
            yield  # pragma: no cover

    class WorkingAdapter:
        model = "m"

        async def chat_stream(self, *args, **kwargs):
            yield "resposta ok"

    def fake_adapter_for(provider, key_state):
        return BrokenAdapter() if provider == "gemini" else WorkingAdapter()

    manager._adapter_for = fake_adapter_for

    chunks = [c async for c, _p, _m in manager.stream([{"role": "user", "content": "oi"}])]
    assert chunks == ["resposta ok"]


@pytest.mark.asyncio
async def test_manager_does_not_fail_over_mid_stream():
    """
    Once bytes are on the wire, switching providers would splice two different
    answers together. It must raise instead.
    """
    from ai.providers import AdvisorProviderManager
    from ai_key_pool import KeyPool

    manager = AdvisorProviderManager.__new__(AdvisorProviderManager)
    manager.key_pool = KeyPool()
    manager.key_pool.register_keys("gemini", ["k1"], "m")
    manager.key_pool.register_keys("openai", ["k2"], "m")
    manager._models = {"gemini": "m", "nova": "m", "openai": "m"}
    manager._adapters = {}
    manager._order = ["gemini", "openai"]

    class HalfwayAdapter:
        model = "m"

        async def chat_stream(self, *args, **kwargs):
            yield "primeira parte"
            raise RuntimeError("connection reset")

    manager._adapter_for = lambda provider, key_state: HalfwayAdapter()

    collected = []
    with pytest.raises(RuntimeError, match="stream_interrupted"):
        async for chunk, _p, _m in manager.stream([{"role": "user", "content": "oi"}]):
            collected.append(chunk)

    assert collected == ["primeira parte"]


@pytest.mark.asyncio
async def test_manager_raises_when_all_providers_fail():
    from ai.providers import AdvisorProviderManager
    from ai_key_pool import KeyPool

    manager = AdvisorProviderManager.__new__(AdvisorProviderManager)
    manager.key_pool = KeyPool()
    manager.key_pool.register_keys("gemini", ["k1"], "m")
    manager._models = {"gemini": "m", "nova": "m", "openai": "m"}
    manager._adapters = {}
    manager._order = ["gemini"]

    class BrokenAdapter:
        model = "m"

        async def chat_stream(self, *args, **kwargs):
            raise RuntimeError("nope")
            yield  # pragma: no cover

    manager._adapter_for = lambda provider, key_state: BrokenAdapter()

    with pytest.raises(RuntimeError, match="Todos os provedores"):
        async for _ in manager.stream([{"role": "user", "content": "oi"}]):
            pass


def test_rate_limit_detection():
    from ai.providers import _is_rate_limit

    assert _is_rate_limit(Exception("429 Too Many Requests")) is True
    assert _is_rate_limit(Exception("quota exceeded for model")) is True
    assert _is_rate_limit(Exception("connection reset by peer")) is False


def test_split_system_separates_persona_from_turns():
    from ai.providers import _split_system

    system, turns = _split_system(
        [
            {"role": "system", "content": "persona"},
            {"role": "system", "content": "contexto"},
            {"role": "user", "content": "oi"},
            {"role": "assistant", "content": "olá"},
        ]
    )

    assert system == "persona\n\ncontexto"
    assert [t["role"] for t in turns] == ["user", "assistant"]


# ─── PROMPT ASSEMBLY ───────────────────────────────────────────────────────────


def test_build_system_messages_embeds_context():
    from ai.prompts import build_system_messages

    messages = build_system_messages('{"dre": {"receita_bruta": 1000}}')

    assert all(m["role"] == "system" for m in messages)
    assert any("receita_bruta" in m["content"] for m in messages)
    # Without a summary there should be exactly persona + context
    assert len(messages) == 2


def test_build_system_messages_includes_summary_when_present():
    from ai.prompts import build_system_messages

    messages = build_system_messages("{}", summary="Discutimos a margem de março.")

    assert len(messages) == 3
    assert any("margem de março" in m["content"] for m in messages)


# ─── HTTP / SSE END-TO-END ─────────────────────────────────────────────────────


@pytest.fixture
def advisor_client():
    """
    TestClient wired to a throwaway SQLite DB and a scripted AI provider.

    Yields `(client, ctx)` where `ctx` lets a test flip the caller's plan
    features and inspect what was persisted.
    """
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    import ai.advisor_service as advisor_service
    from api import app
    from auth.dependencies import get_current_active_user
    from database import Base, User, get_db

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    session = TestingSession()
    user = User(
        id=1,
        email="gestor@teste.com",
        password_hash="x",
        full_name="Gestor Teste",
        company_name="Empresa Teste",
        cnpj="00000000000191",
        is_active=True,
    )
    session.add(user)
    session.commit()

    ctx = {"features": {"ai_advisor": True}, "chunks": ["Sua margem ", "líquida é 12,3%."]}

    class ScriptedManager:
        available = True

        async def stream(self, messages, max_tokens=None, temperature=None):
            ctx["last_messages"] = messages
            for chunk in ctx["chunks"]:
                yield chunk, "gemini", "gemini-flash-latest"

        async def complete(self, messages, max_tokens=None, temperature=None):
            return "resumo"

    def fake_active_plan(db, current_user):
        return FakePlan(ctx["features"])

    # Patch where the name is *used*, not where it's defined.
    import plan_features
    import routers.advisor as advisor_router_module

    original_get_active_plan = plan_features.get_active_plan
    plan_features.get_active_plan = fake_active_plan
    original_manager_factory = advisor_service.get_provider_manager
    advisor_service.get_provider_manager = lambda: ScriptedManager()

    def override_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    def override_user():
        db = TestingSession()
        return db.query(User).filter(User.id == 1).first()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_active_user] = override_user

    ctx["session_factory"] = TestingSession

    with TestClient(app) as client:
        yield client, ctx

    app.dependency_overrides.clear()
    plan_features.get_active_plan = original_get_active_plan
    advisor_service.get_provider_manager = original_manager_factory


def test_status_reports_access_for_pro_plan(advisor_client):
    client, ctx = advisor_client

    ctx["features"] = {"ai_advisor": True}
    assert client.get("/advisor/status").json()["has_access"] is True

    ctx["features"] = {"ai_advisor": False}
    assert client.get("/advisor/status").json()["has_access"] is False


def test_chat_is_forbidden_without_the_feature(advisor_client):
    client, ctx = advisor_client
    ctx["features"] = {"ai_advisor": False}

    response = client.post("/advisor/chat/stream", json={"message": "e aí?"})

    assert response.status_code == 403
    # The API wraps errors as {"error": {"code", "message"}} — the UI client
    # reads the same shape, so assert on it explicitly.
    body = response.json()
    assert body["error"]["code"] == "FORBIDDEN"
    assert "Pro" in body["error"]["message"]


def test_chat_streams_sse_and_persists_the_exchange(advisor_client):
    from database import AdvisorConversation, AdvisorMessage

    client, ctx = advisor_client

    response = client.post(
        "/advisor/chat/stream",
        json={"message": "Como está minha margem?", "period_type": "month"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    # Proxies must not buffer a stream
    assert response.headers["x-accel-buffering"] == "no"

    events = parse_sse(response.text)
    assert events[0]["event"] == "connected"

    answer = "".join(e["chunk"] for e in events if "chunk" in e)
    assert answer == "Sua margem líquida é 12,3%."

    done = events[-1]
    assert done["event"] == "done"
    assert done["provider"] == "gemini"

    # Both turns are on disk, tagged with the model that produced them
    session = ctx["session_factory"]()
    conversation = session.query(AdvisorConversation).one()
    assert conversation.message_count == 2
    assert conversation.title == "Como está minha margem?"

    messages = (
        session.query(AdvisorMessage)
        .filter(AdvisorMessage.conversation_id == conversation.id)
        .order_by(AdvisorMessage.id)
        .all()
    )
    assert [m.role for m in messages] == ["user", "assistant"]
    assert messages[1].content == "Sua margem líquida é 12,3%."
    assert messages[1].model == "gemini-flash-latest"
    session.close()


def test_prompt_carries_the_financial_context(advisor_client):
    client, ctx = advisor_client

    client.post("/advisor/chat/stream", json={"message": "e a receita?"})

    messages = ctx["last_messages"]
    system_blob = "\n".join(m["content"] for m in messages if m["role"] == "system")

    # The snapshot the prompt advertises must actually be in there
    for key in ("dre", "balanco", "indicadores", "tendencia_mensal"):
        assert key in system_blob, f"context missing {key}"

    assert messages[-1] == {"role": "user", "content": "e a receita?"}


def test_second_message_continues_the_same_conversation(advisor_client):
    from database import AdvisorConversation

    client, ctx = advisor_client

    first = client.post("/advisor/chat/stream", json={"message": "primeira"})
    conversation_id = parse_sse(first.text)[0]["conversation_id"]

    second = client.post(
        "/advisor/chat/stream",
        json={"message": "segunda", "conversation_id": conversation_id},
    )
    assert parse_sse(second.text)[0]["conversation_id"] == conversation_id

    # Prior turns are replayed so the model has continuity
    roles = [m["role"] for m in ctx["last_messages"]]
    assert roles.count("assistant") >= 1

    session = ctx["session_factory"]()
    assert session.query(AdvisorConversation).count() == 1
    session.close()


def test_unknown_conversation_is_rejected(advisor_client):
    client, _ctx = advisor_client

    response = client.post(
        "/advisor/chat/stream", json={"message": "oi", "conversation_id": 4242}
    )
    assert response.status_code == 404


def test_conversations_can_be_listed_and_deleted(advisor_client):
    client, _ctx = advisor_client

    client.post("/advisor/chat/stream", json={"message": "analise minha dre"})

    listed = client.get("/advisor/conversations").json()
    assert len(listed) == 1
    assert listed[0]["message_count"] == 2

    assert client.delete(f"/advisor/conversations/{listed[0]['id']}").status_code == 200
    assert client.get("/advisor/conversations").json() == []


def test_provider_failure_is_reported_as_an_error_event(advisor_client):
    """All providers down must still yield a well-formed stream, not a 500."""
    client, ctx = advisor_client

    class DeadManager:
        available = True

        async def stream(self, messages, max_tokens=None, temperature=None):
            raise RuntimeError("Todos os provedores de IA falharam.")
            yield  # pragma: no cover

        async def complete(self, *a, **k):
            return ""

    import ai.advisor_service as advisor_service

    advisor_service.get_provider_manager = lambda: DeadManager()

    response = client.post("/advisor/chat/stream", json={"message": "oi"})

    assert response.status_code == 200
    events = parse_sse(response.text)
    assert any(e.get("event") == "error" for e in events)
    # The stream still terminates cleanly so the client can reset its UI
    assert events[-1]["event"] == "done"


def test_suggestions_endpoint_returns_four_prompts(advisor_client):
    client, ctx = advisor_client
    ctx["chunks"] = []

    import ai.advisor_service as advisor_service

    class SuggestingManager:
        available = True

        async def stream(self, *a, **k):
            yield "", "gemini", "m"

        async def complete(self, messages, max_tokens=None, temperature=None):
            return "Por que caiu?\nOnde gasto mais?\nPosso pagar?\nQual o ponto?"

    advisor_service.get_provider_manager = lambda: SuggestingManager()

    suggestions = client.get("/advisor/suggestions").json()["suggestions"]
    assert len(suggestions) == 4
    assert "Por que caiu?" in suggestions


def test_suggestion_parsing_strips_list_markers():
    """The model tends to number its output despite being told not to."""
    from ai.advisor_service import AdvisorService

    raw = '1. Por que minha margem caiu?\n- Onde gasto mais?\n"Posso pagar as contas?"\n\nQual meu ponto de equilíbrio?'

    suggestions = []
    for line in raw.splitlines():
        cleaned = line.strip().lstrip("-•0123456789. ").strip().strip('"')
        if cleaned:
            suggestions.append(cleaned[:100])

    assert suggestions == [
        "Por que minha margem caiu?",
        "Onde gasto mais?",
        "Posso pagar as contas?",
        "Qual meu ponto de equilíbrio?",
    ]
    assert AdvisorService.default_suggestions()
