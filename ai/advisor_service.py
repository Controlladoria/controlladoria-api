"""
Advisor Service — conversation orchestration.

Owns the parts that are neither transport (routers) nor provider plumbing
(providers.py): resolving the period, assembling the prompt, keeping history
bounded, and persisting turns.

History strategy: the last `advisor_history_turns` exchanges are replayed
verbatim; everything older is folded into a rolling summary stored on the
conversation row. Prompt size therefore stays bounded no matter how long a
thread runs — the same principle as the financial snapshot.
"""

import logging
from datetime import date, datetime
from typing import AsyncIterator, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from config import settings
from database import AdvisorConversation, AdvisorMessage, User

from .context_builder import FinancialContextBuilder
from .prompts import SUGGESTIONS_PROMPT, SUMMARY_PROMPT, build_system_messages
from .providers import get_provider_manager

logger = logging.getLogger(__name__)


class AdvisorService:
    def __init__(self, db: Session, current_user: User):
        self.db = db
        self.user = current_user
        self.org_id = (
            getattr(current_user, "_active_org_id", None)
            or getattr(current_user, "active_org_id", None)
        )
        self.manager = get_provider_manager()

    # -- period ---------------------------------------------------------------

    def resolve_period(
        self,
        period_type: str = "month",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        reference_date: Optional[str] = None,
    ) -> Tuple[date, date, str]:
        """
        Mirror the period semantics of the report endpoints so the advisor is
        always looking at exactly the window the user has on screen.
        """
        from accounting import PeriodType, get_period_dates
        from config import now_brazil

        try:
            period_enum = PeriodType((period_type or "month").lower())
        except ValueError:
            period_enum = PeriodType.MONTH

        if period_enum == PeriodType.CUSTOM and start_date and end_date:
            try:
                period_start = datetime.strptime(start_date, "%Y-%m-%d").date()
                period_end = datetime.strptime(end_date, "%Y-%m-%d").date()
                return period_start, period_end, f"{period_start} a {period_end}"
            except ValueError:
                period_enum = PeriodType.MONTH

        if reference_date:
            try:
                ref = datetime.strptime(reference_date, "%Y-%m-%d").date()
            except ValueError:
                ref = now_brazil().date()
        else:
            ref = now_brazil().date()

        period_start, period_end = get_period_dates(period_enum, ref)
        return period_start, period_end, self._label(period_enum, period_start, period_end)

    @staticmethod
    def _label(period_enum, period_start: date, period_end: date) -> str:
        from accounting import PeriodType

        months = [
            "janeiro", "fevereiro", "março", "abril", "maio", "junho",
            "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
        ]
        if period_enum == PeriodType.MONTH:
            return f"{months[period_start.month - 1]} de {period_start.year}"
        if period_enum == PeriodType.YEAR:
            return f"ano de {period_start.year}"
        if period_enum == PeriodType.DAY:
            return period_start.strftime("%d/%m/%Y")
        return f"{period_start.strftime('%d/%m/%Y')} a {period_end.strftime('%d/%m/%Y')}"

    # -- conversations --------------------------------------------------------

    def _base_query(self):
        """Every read is scoped to the caller's organization."""
        query = self.db.query(AdvisorConversation)
        if self.org_id:
            return query.filter(AdvisorConversation.organization_id == self.org_id)
        # No active org (legacy single-user account) — fall back to ownership
        return query.filter(
            AdvisorConversation.organization_id.is_(None),
            AdvisorConversation.user_id == self.user.id,
        )

    def get_conversation(self, conversation_id: int) -> Optional[AdvisorConversation]:
        return self._base_query().filter(
            AdvisorConversation.id == conversation_id
        ).first()

    def list_conversations(self, limit: int = 30) -> List[AdvisorConversation]:
        return (
            self._base_query()
            .filter(AdvisorConversation.is_archived.is_(False))
            .order_by(AdvisorConversation.updated_at.desc())
            .limit(limit)
            .all()
        )

    def create_conversation(
        self, first_message: str, period_start: date, period_end: date
    ) -> AdvisorConversation:
        conversation = AdvisorConversation(
            organization_id=self.org_id,
            user_id=self.user.id,
            title=self._derive_title(first_message),
            period_start=period_start,
            period_end=period_end,
        )
        self.db.add(conversation)
        self.db.commit()
        self.db.refresh(conversation)
        return conversation

    @staticmethod
    def _derive_title(message: str, max_len: int = 60) -> str:
        title = " ".join((message or "").split())
        if len(title) <= max_len:
            return title or "Nova conversa"
        return title[:max_len].rsplit(" ", 1)[0] + "…"

    def add_message(
        self,
        conversation: AdvisorConversation,
        role: str,
        content: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> AdvisorMessage:
        message = AdvisorMessage(
            conversation_id=conversation.id,
            role=role,
            content=content,
            provider=provider,
            model=model,
        )
        self.db.add(message)
        conversation.message_count = (conversation.message_count or 0) + 1
        conversation.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(message)
        return message

    # -- history --------------------------------------------------------------

    def _recent_turns(self, conversation: AdvisorConversation) -> List[Dict]:
        """
        The last N exchanges, oldest first.

        Fetched newest-first with a LIMIT so we never load a long thread into
        memory, then reversed for chronological order.
        """
        window = settings.advisor_history_turns * 2  # user + assistant per turn
        rows = (
            self.db.query(AdvisorMessage)
            .filter(AdvisorMessage.conversation_id == conversation.id)
            .order_by(AdvisorMessage.id.desc())
            .limit(window)
            .all()
        )
        rows.reverse()

        max_chars = settings.advisor_max_message_chars
        return [
            {"role": row.role, "content": (row.content or "")[:max_chars]}
            for row in rows
        ]

    async def maybe_summarize(self, conversation: AdvisorConversation) -> None:
        """
        Fold aged-out turns into the rolling summary.

        Runs after a response is already delivered, so its latency is invisible
        to the user. Failure is non-fatal: worst case the thread keeps its old
        summary and the oldest turns simply drop out of the replay window.
        """
        window = settings.advisor_history_turns * 2
        total = conversation.message_count or 0
        if total <= window:
            return

        cutoff_id = (
            self.db.query(AdvisorMessage.id)
            .filter(AdvisorMessage.conversation_id == conversation.id)
            .order_by(AdvisorMessage.id.desc())
            .offset(window - 1)
            .limit(1)
            .scalar()
        )
        if cutoff_id is None:
            return
        if conversation.summarized_through_id and conversation.summarized_through_id >= cutoff_id:
            return  # already covered

        aged = (
            self.db.query(AdvisorMessage)
            .filter(
                AdvisorMessage.conversation_id == conversation.id,
                AdvisorMessage.id < cutoff_id,
            )
            .order_by(AdvisorMessage.id)
            .all()
        )
        if not aged:
            return

        transcript_parts = []
        if conversation.summary:
            transcript_parts.append(f"[resumo anterior] {conversation.summary}")
        for row in aged:
            speaker = "Gestor" if row.role == "user" else "Consultor"
            transcript_parts.append(f"{speaker}: {(row.content or '')[:1500]}")
        transcript = "\n\n".join(transcript_parts)

        try:
            summary = await self.manager.complete(
                [{"role": "user", "content": SUMMARY_PROMPT.format(conversation=transcript)}],
                max_tokens=400,
            )
            conversation.summary = summary.strip()
            conversation.summarized_through_id = cutoff_id
            self.db.commit()
            logger.info(
                "Advisor: summarized conversation %s through message %s",
                conversation.id,
                cutoff_id,
            )
        except Exception as exc:
            self.db.rollback()
            logger.warning("Advisor: summarization failed for %s: %s", conversation.id, exc)

    # -- context --------------------------------------------------------------

    def build_context(
        self, period_start: date, period_end: date, period_label: str
    ) -> Dict:
        builder = FinancialContextBuilder(self.db, self.user)
        return builder.build(period_start, period_end, period_label)

    def build_messages(
        self,
        conversation: Optional[AdvisorConversation],
        user_message: str,
        context: Dict,
    ) -> List[Dict]:
        context_json = FinancialContextBuilder.to_prompt_block(context)
        messages = build_system_messages(
            context_json,
            summary=(conversation.summary if conversation else "") or "",
        )
        if conversation is not None:
            messages.extend(self._recent_turns(conversation))
        messages.append(
            {
                "role": "user",
                "content": user_message[: settings.advisor_max_message_chars],
            }
        )
        return messages

    # -- generation -----------------------------------------------------------

    async def stream_answer(
        self, messages: List[Dict]
    ) -> AsyncIterator[Tuple[str, str, str]]:
        async for chunk, provider, model in self.manager.stream(messages):
            yield chunk, provider, model

    async def generate_suggestions(self, context: Dict) -> List[str]:
        """Starter prompts derived from the org's actual numbers."""
        context_json = FinancialContextBuilder.to_prompt_block(context)
        try:
            raw = await self.manager.complete(
                [
                    {
                        "role": "user",
                        "content": SUGGESTIONS_PROMPT.format(context_json=context_json),
                    }
                ],
                max_tokens=300,
            )
        except Exception as exc:
            logger.warning("Advisor: suggestion generation failed: %s", exc)
            return self.default_suggestions()

        suggestions = []
        for line in (raw or "").splitlines():
            cleaned = line.strip().lstrip("-•0123456789. ").strip().strip('"')
            if cleaned:
                suggestions.append(cleaned[:100])

        return suggestions[:4] or self.default_suggestions()

    @staticmethod
    def default_suggestions() -> List[str]:
        """Fallback when the model is unavailable or the org has no data yet."""
        return [
            "Como foi meu resultado neste período?",
            "Onde estou gastando mais?",
            "Minha margem está saudável?",
            "Consigo pagar minhas contas de curto prazo?",
        ]
