"""
Advisor Router — AI financial consultant chat.

Streams answers over SSE so the user sees text as it is generated instead of
staring at a spinner for 10+ seconds. Gated behind the `ai_advisor` plan
feature (Pro and Max).

SSE event protocol (same shape used by tutoria-api, so clients are portable):
    {"event": "connected", "conversation_id": 12}
    {"chunk": "texto parcial"}
    {"event": "done", "conversation_id": 12, "provider": "gemini", "model": "..."}
    {"event": "error", "message": "..."}
"""

import asyncio
import json
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ai.advisor_service import AdvisorService
from auth.dependencies import get_current_active_user
from config import settings
from database import AdvisorMessage, User, get_db
from plan_features import AI_ADVISOR, user_has_feature

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/advisor", tags=["AI Advisor"])


# ─── ACCESS CONTROL ────────────────────────────────────────────────────────────


def require_advisor_access(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> User:
    """
    Gate the advisor behind the plan feature.

    Deliberately does *not* inherit the global `free_demo_mode` bypass. Demo
    mode makes the product free to explore, but every advisor message costs a
    model call, so it stays closed unless `ai_advisor_free_demo` is set too.
    """
    if not settings.advisor_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="O consultor de IA está temporariamente indisponível.",
        )

    if settings.free_demo_mode and settings.ai_advisor_free_demo:
        return current_user

    if not user_has_feature(db, current_user, AI_ADVISOR):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="O Consultor IA está disponível nos planos Pro e Max.",
        )
    return current_user


# ─── SCHEMAS ───────────────────────────────────────────────────────────────────


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    conversation_id: Optional[int] = None

    # Period the user is looking at — mirrors the report endpoints' parameters
    period_type: str = "month"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    reference_date: Optional[str] = None


class MessageResponse(BaseModel):
    id: int
    role: str
    content: str
    provider: Optional[str] = None
    model: Optional[str] = None
    created_at: Optional[str] = None


class ConversationSummary(BaseModel):
    id: int
    title: Optional[str]
    message_count: int
    updated_at: Optional[str]


class ConversationDetail(ConversationSummary):
    messages: List[MessageResponse]


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    # Without this, nginx buffers the whole response and streaming silently
    # degrades into a slow single delivery.
    "X-Accel-Buffering": "no",
}


# ─── STREAMING CHAT ────────────────────────────────────────────────────────────


@router.post("/chat/stream")
async def chat_stream(
    request: Request,
    payload: ChatRequest,
    current_user: User = Depends(require_advisor_access),
    db: Session = Depends(get_db),
):
    """
    Ask the advisor a question and stream the answer back as SSE.

    Everything that can fail loudly (plan check, period parsing, context build)
    happens *before* the stream opens, so failures surface as a normal HTTP
    error code instead of a 200 with an error event buried in the body.
    """
    service = AdvisorService(db, current_user)

    if not service.manager.available:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Nenhum provedor de IA está configurado.",
        )

    period_start, period_end, period_label = service.resolve_period(
        payload.period_type, payload.start_date, payload.end_date, payload.reference_date
    )

    conversation = None
    if payload.conversation_id is not None:
        conversation = service.get_conversation(payload.conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversa não encontrada.")

    try:
        context = service.build_context(period_start, period_end, period_label)
    except Exception as exc:
        logger.exception("Advisor: failed to build financial context: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Não foi possível carregar seus dados financeiros. Tente novamente.",
        )

    messages = service.build_messages(conversation, payload.message, context)

    # Create the thread only once we know the request is viable, so a failed
    # call doesn't litter the sidebar with empty conversations.
    if conversation is None:
        conversation = service.create_conversation(
            payload.message, period_start, period_end
        )
    service.add_message(conversation, "user", payload.message)

    conversation_id = conversation.id

    async def event_generator():
        full_response = ""
        provider = None
        model = None

        try:
            yield _sse({"event": "connected", "conversation_id": conversation_id})

            try:
                async for chunk, chunk_provider, chunk_model in service.stream_answer(
                    messages
                ):
                    provider = chunk_provider
                    model = chunk_model
                    full_response += chunk
                    yield _sse({"chunk": chunk})

            except RuntimeError as exc:
                if str(exc) == "stream_interrupted":
                    message = (
                        "A resposta foi interrompida antes de terminar. "
                        "Envie a pergunta novamente."
                    )
                else:
                    message = (
                        "Serviço de IA temporariamente indisponível. "
                        "Tente novamente em alguns instantes."
                    )
                logger.error("Advisor: stream failed for conv %s: %s", conversation_id, exc)
                yield _sse({"event": "error", "message": message})

            if full_response.strip():
                service.add_message(
                    conversation, "assistant", full_response, provider, model
                )

            yield _sse(
                {
                    "event": "done",
                    "conversation_id": conversation_id,
                    "provider": provider,
                    "model": model,
                }
            )

            # Post-response housekeeping — the user already has their answer.
            await service.maybe_summarize(conversation)

        except asyncio.CancelledError:
            # Browser tab closed / navigated away. Persist whatever we produced
            # so the thread isn't left with a dangling user message.
            if full_response.strip():
                try:
                    service.add_message(
                        conversation, "assistant", full_response, provider, model
                    )
                except Exception:
                    logger.warning("Advisor: could not persist partial answer")
            logger.info("Advisor: client disconnected from conv %s", conversation_id)
            raise
        except Exception as exc:
            logger.exception("Advisor: unexpected streaming error: %s", exc)
            yield _sse(
                {"event": "error", "message": "Erro inesperado ao gerar a resposta."}
            )

    return StreamingResponse(
        event_generator(), media_type="text/event-stream", headers=SSE_HEADERS
    )


# ─── CONVERSATIONS ─────────────────────────────────────────────────────────────


@router.get("/conversations", response_model=List[ConversationSummary])
async def list_conversations(
    limit: int = Query(30, ge=1, le=100),
    current_user: User = Depends(require_advisor_access),
    db: Session = Depends(get_db),
):
    service = AdvisorService(db, current_user)
    return [
        ConversationSummary(
            id=c.id,
            title=c.title,
            message_count=c.message_count or 0,
            updated_at=c.updated_at.isoformat() if c.updated_at else None,
        )
        for c in service.list_conversations(limit=limit)
    ]


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: int,
    current_user: User = Depends(require_advisor_access),
    db: Session = Depends(get_db),
):
    service = AdvisorService(db, current_user)
    conversation = service.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")

    messages = (
        db.query(AdvisorMessage)
        .filter(AdvisorMessage.conversation_id == conversation.id)
        .order_by(AdvisorMessage.id)
        .all()
    )

    return ConversationDetail(
        id=conversation.id,
        title=conversation.title,
        message_count=conversation.message_count or 0,
        updated_at=conversation.updated_at.isoformat() if conversation.updated_at else None,
        messages=[
            MessageResponse(
                id=m.id,
                role=m.role,
                content=m.content,
                provider=m.provider,
                model=m.model,
                created_at=m.created_at.isoformat() if m.created_at else None,
            )
            for m in messages
        ],
    )


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: int,
    current_user: User = Depends(require_advisor_access),
    db: Session = Depends(get_db),
):
    service = AdvisorService(db, current_user)
    conversation = service.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")

    db.delete(conversation)
    db.commit()
    return {"success": True}


# ─── SUGGESTIONS & STATUS ──────────────────────────────────────────────────────


@router.get("/suggestions")
async def get_suggestions(
    period_type: str = Query("month"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    reference_date: Optional[str] = Query(None),
    current_user: User = Depends(require_advisor_access),
    db: Session = Depends(get_db),
):
    """Starter questions grounded in the org's own numbers."""
    service = AdvisorService(db, current_user)

    if not service.manager.available:
        return {"suggestions": AdvisorService.default_suggestions()}

    period_start, period_end, period_label = service.resolve_period(
        period_type, start_date, end_date, reference_date
    )
    try:
        context = service.build_context(period_start, period_end, period_label)
    except Exception as exc:
        logger.warning("Advisor: suggestions context failed: %s", exc)
        return {"suggestions": AdvisorService.default_suggestions()}

    return {"suggestions": await service.generate_suggestions(context)}


@router.get("/status")
async def advisor_status(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Whether this user can use the advisor. Unlike every other route here it is
    *not* gated, because the UI needs to ask "should I render the button?"
    without triggering a 403.
    """
    has_feature = user_has_feature(db, current_user, AI_ADVISOR)
    if settings.free_demo_mode and settings.ai_advisor_free_demo:
        has_feature = True

    return {
        "enabled": settings.advisor_enabled,
        "has_access": bool(settings.advisor_enabled and has_feature),
        "required_plans": ["pro", "max"],
    }
