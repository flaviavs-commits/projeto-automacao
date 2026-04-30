from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.models.contact_memory import ContactMemory
from app.models.conversation import Conversation


class LeadTemperatureService:
    """Computes simple hot-profile indicators for operational triage."""

    _HOT_MEMORY_KEYS = {"interesse", "pacote_interesse", "duvida_valor", "interesse_agendamento"}

    def evaluate_contact(self, *, db: Session, contact_id: UUID) -> dict:
        reasons: list[str] = []

        human_conversation = (
            db.execute(
                select(Conversation.id, Conversation.human_status, Conversation.needs_human, Conversation.last_message_at)
                .where(Conversation.contact_id == contact_id)
                .order_by(Conversation.updated_at.desc())
            )
            .all()
        )
        for _, human_status, needs_human, _ in human_conversation:
            if needs_human:
                reasons.append("pediu atendimento humano")
                break
            if str(human_status or "").strip().lower() in {"human_pending", "human_accepted"}:
                reasons.append("em atendimento humano")
                break

        memory_rows = (
            db.execute(
                select(ContactMemory.memory_key).where(
                    ContactMemory.contact_id == contact_id,
                    ContactMemory.status == "active",
                )
            )
            .scalars()
            .all()
        )
        memory_keys = {str(item or "").strip().lower() for item in memory_rows}
        if memory_keys.intersection(self._HOT_MEMORY_KEYS):
            reasons.append("interesse em agendamento/valores")

        has_appointment = (
            db.execute(
                select(Appointment.id).where(
                    Appointment.contact_id == contact_id,
                    Appointment.status.in_(("reserved", "completed")),
                )
            )
            .scalars()
            .first()
            is not None
        )
        if has_appointment:
            reasons.append("possui agendamento")

        recent_open = (
            db.execute(
                select(Conversation.id).where(
                    Conversation.contact_id == contact_id,
                    Conversation.status == "open",
                    Conversation.last_message_at.is_not(None),
                    Conversation.last_message_at >= datetime.now(timezone.utc) - timedelta(hours=48),
                )
            )
            .scalars()
            .first()
            is not None
        )
        if recent_open:
            reasons.append("conversa recente aberta")

        unique_reasons = list(dict.fromkeys(reasons))
        return {
            "is_hot": bool(unique_reasons),
            "reasons": unique_reasons,
        }
