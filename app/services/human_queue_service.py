from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.message import Message


class HumanQueueService:
    """Handles human handoff queue listing and state transitions."""

    ACTIVE_HUMAN_STATUSES = {"human_pending", "human_accepted", "human_ignored"}
    _HUMAN_REASON_LABELS = {
        "problema_agendamento": "Duvida para concluir agendamento",
        "duvida_pagamento": "Duvida sobre pagamento",
        "duvida_valor": "Duvida sobre valores",
        "nao_entendeu_menu": "Cliente nao conseguiu continuar no menu",
        "pedido_humano": "Cliente pediu atendimento humano",
    }
    _MENU_OPTION_LABELS = {
        "0": "Encerrar atendimento",
        "1": "Agendamento",
        "2": "Valores e pacotes",
        "3": "Informacoes do estudio",
        "4": "Endereco",
        "5": "Atendimento humano",
        "6": "Horarios",
        "7": "Estrutura",
        "8": "Outras duvidas",
        "9": "Voltar ao menu",
    }

    def list_active_queue(self, *, db: Session, for_modal: bool = False, limit: int = 50) -> list[dict]:
        rows = (
            db.execute(
                select(Conversation)
                .where(
                    and_(
                        Conversation.status != "closed",
                        or_(
                            Conversation.needs_human.is_(True),
                            Conversation.human_status.in_(tuple(self.ACTIVE_HUMAN_STATUSES)),
                        ),
                    )
                )
                .order_by(Conversation.human_requested_at.asc().nullslast(), Conversation.updated_at.asc())
                .limit(max(1, min(limit, 200)))
            )
            .scalars()
            .all()
        )
        if for_modal:
            rows = [
                item
                for item in rows
                if self._effective_human_status(item) == "human_pending"
            ][-1:]

        items: list[dict] = []
        for conversation in rows:
            contact = db.get(Contact, conversation.contact_id)
            last_inbound = (
                db.execute(
                    select(Message)
                    .where(
                        Message.conversation_id == conversation.id,
                        Message.direction == "inbound",
                    )
                    .order_by(Message.created_at.desc())
                    .limit(1)
                )
                .scalars()
                .first()
            )
            items.append(
                {
                    "conversation_id": str(conversation.id),
                    "name": str((contact.name if contact else "") or "").strip() or "Sem nome",
                    "phone": str((contact.phone if contact else "") or "").strip() or "-",
                    "channel": conversation.platform,
                    "human_reason": self._friendly_reason(conversation.human_reason),
                    "human_requested_at": conversation.human_requested_at.isoformat() if conversation.human_requested_at else None,
                    "human_status": self._effective_human_status(conversation),
                    "last_customer_message": str((last_inbound.text_content if last_inbound else "") or "").strip() or "Sem mensagem",
                    "menu_path_summary": self._menu_path_summary(
                        db=db,
                        conversation_id=conversation.id,
                        requested_at=conversation.human_requested_at,
                    ),
                }
            )
        return items

    def accept(self, *, db: Session, conversation_id: UUID, actor: str | None) -> dict:
        conversation = db.get(Conversation, conversation_id)
        if conversation is None:
            raise ValueError("conversation_not_found")

        now_utc = datetime.now(timezone.utc)
        conversation.needs_human = True
        conversation.human_status = "human_accepted"
        conversation.human_accepted_at = now_utc
        conversation.human_accepted_by = actor
        conversation.chatbot_enabled = False

        db.add(
            AuditLog(
                entity_type="conversation",
                entity_id=conversation.id,
                event_type="human_request_accepted",
                details={
                    "conversation_id": str(conversation.id),
                    "actor": actor,
                },
            )
        )
        db.add(
            AuditLog(
                entity_type="conversation",
                entity_id=conversation.id,
                event_type="chatbot_disabled",
                details={
                    "conversation_id": str(conversation.id),
                    "actor": actor,
                    "reason": "human_request_accepted",
                },
            )
        )
        db.commit()
        return {"conversation_id": str(conversation.id), "human_status": conversation.human_status}

    def ignore(self, *, db: Session, conversation_id: UUID, actor: str | None) -> dict:
        conversation = db.get(Conversation, conversation_id)
        if conversation is None:
            raise ValueError("conversation_not_found")

        now_utc = datetime.now(timezone.utc)
        conversation.needs_human = True
        conversation.human_status = "human_ignored"
        conversation.human_ignored_at = now_utc
        conversation.human_ignored_by = actor

        db.add(
            AuditLog(
                entity_type="conversation",
                entity_id=conversation.id,
                event_type="human_request_ignored",
                details={
                    "conversation_id": str(conversation.id),
                    "actor": actor,
                },
            )
        )
        db.commit()
        return {"conversation_id": str(conversation.id), "human_status": conversation.human_status}

    def _effective_human_status(self, conversation: Conversation) -> str:
        if str(conversation.status or "").strip().lower() == "closed":
            return "closed"
        explicit = str(conversation.human_status or "").strip().lower()
        if explicit in self.ACTIVE_HUMAN_STATUSES:
            return explicit
        if conversation.needs_human:
            return "human_pending"
        return "closed"

    def _friendly_reason(self, reason: str | None) -> str:
        raw = str(reason or "").strip().lower()
        if not raw:
            return "Cliente pediu ajuda"
        return self._HUMAN_REASON_LABELS.get(raw, raw.replace("_", " ").capitalize())

    def _menu_path_summary(self, *, db: Session, conversation_id: UUID, requested_at: datetime | None) -> str:
        query = (
            select(Message.text_content)
            .where(
                Message.conversation_id == conversation_id,
                Message.direction == "inbound",
            )
            .order_by(Message.created_at.asc())
        )
        if requested_at is not None:
            query = query.where(Message.created_at <= requested_at)

        picks = (
            db.execute(query)
            .scalars()
            .all()
        )
        labels: list[str] = []
        for value in picks:
            text = str(value or "").strip()
            if text in self._MENU_OPTION_LABELS:
                labels.append(self._MENU_OPTION_LABELS[text])

        if not labels:
            return "Sem trilha de menu registrada"
        if len(labels) > 5:
            preview = " -> ".join(labels[:5])
            return f"{preview} -> ... (leia o historico completo)"
        return " -> ".join(labels)
