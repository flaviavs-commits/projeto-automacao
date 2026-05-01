from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.models.contact import Contact
from app.models.contact_identity import ContactIdentity
from app.models.contact_memory import ContactMemory
from app.models.conversation import Conversation
from app.models.message import Message
from app.services.fcvip_partner_api_service import FCVIPPartnerAPIService
from app.services.lead_temperature_service import LeadTemperatureService


class DashboardOpService:
    """Aggregates operational dashboard data with backend-side filtering."""
    _MEMORY_LABELS = {
        "interesse": "Interesse",
        "pacote_interesse": "Pacote de interesse",
        "interesse_membro": "Interesse em membros",
        "interesse_agendamento": "Interesse em agendamento",
        "estrutura_interesse": "Interesse em estrutura",
        "human_reason": "Motivo do pedido humano",
        "cliente_status": "Status do cliente",
    }
    _HUMAN_REASON_LABELS = {
        "problema_agendamento": "Duvida para concluir agendamento",
        "duvida_pagamento": "Duvida sobre pagamento",
        "duvida_valor": "Duvida sobre valores",
        "nao_entendeu_menu": "Cliente nao conseguiu continuar no menu",
        "pedido_humano": "Cliente pediu atendimento humano",
    }

    def list_conversations(
        self,
        *,
        db: Session,
        limit: int = 50,
        offset: int = 0,
        channel: str | None = None,
        hot_only: bool = False,
        human_pending: bool = False,
        search: str | None = None,
        status: str | None = None,
    ) -> dict:
        query = select(Conversation).order_by(
            func.coalesce(Conversation.last_message_at, Conversation.updated_at, Conversation.created_at).desc()
        )

        if channel:
            query = query.where(Conversation.platform == str(channel).strip().lower())
        if human_pending:
            query = query.where(
                and_(
                    Conversation.status != "closed",
                    or_(
                        Conversation.needs_human.is_(True),
                        Conversation.human_status.in_(("human_pending", "human_accepted", "human_ignored")),
                    ),
                )
            )
        if status:
            query = query.where(Conversation.status == str(status).strip().lower())

        rows = db.execute(query).scalars().all()

        items: list[dict] = []
        normalized_search = str(search or "").strip().lower()
        for conversation in rows:
            contact = db.get(Contact, conversation.contact_id)
            hot = LeadTemperatureService().evaluate_contact(db=db, contact_id=conversation.contact_id)
            if hot_only and not hot.get("is_hot"):
                continue

            identities = (
                db.execute(
                    select(ContactIdentity).where(ContactIdentity.contact_id == conversation.contact_id)
                )
                .scalars()
                .all()
            )
            search_haystack = " ".join(
                [
                    str(contact.name if contact else ""),
                    str(contact.phone if contact else ""),
                    str(contact.email if contact else ""),
                    " ".join(str(item.platform_user_id or "") for item in identities),
                ]
            ).lower()
            if normalized_search and normalized_search not in search_haystack:
                continue

            items.append(
                {
                    "id": str(conversation.id),
                    "channel": conversation.platform,
                    "status": conversation.status,
                    "human_status": self._effective_human_status(conversation),
                    "chatbot_enabled": bool(conversation.chatbot_enabled),
                    "last_activity_at": self._conversation_last_activity(conversation).isoformat(),
                    "contact": {
                        "id": str(contact.id) if contact else None,
                        "name": str((contact.name if contact else "") or "").strip() or "Sem nome",
                        "phone": str((contact.phone if contact else "") or "").strip() or "-",
                    },
                    "is_hot": bool(hot.get("is_hot")),
                    "hot_reasons": hot.get("reasons", []),
                }
            )

        total = len(items)
        paged = items[offset : offset + max(1, min(limit, 200))]
        return {"items": paged, "total": total, "limit": limit, "offset": offset}

    def get_conversation_detail(self, *, db: Session, conversation_id: UUID) -> dict | None:
        conversation = db.get(Conversation, conversation_id)
        if conversation is None:
            return None
        contact = db.get(Contact, conversation.contact_id)
        hot = LeadTemperatureService().evaluate_contact(db=db, contact_id=conversation.contact_id)
        identities = (
            db.execute(
                select(ContactIdentity).where(ContactIdentity.contact_id == conversation.contact_id)
                .order_by(ContactIdentity.is_primary.desc(), ContactIdentity.created_at.asc())
            )
            .scalars()
            .all()
        )
        identities = [item for item in identities if str(item.platform_user_id or "").strip()]
        memories = (
            db.execute(
                select(ContactMemory).where(
                    ContactMemory.contact_id == conversation.contact_id,
                    ContactMemory.status == "active",
                )
                .order_by(ContactMemory.importance.desc(), ContactMemory.updated_at.desc())
            )
            .scalars()
            .all()
        )
        memory_payload = [
            {
                "key": item.memory_key,
                "label": self._friendly_memory_label(item.memory_key),
                "value": item.memory_value,
            }
            for item in memories
        ]
        human_reason_label = self._friendly_reason(conversation.human_reason)
        return {
            "id": str(conversation.id),
            "channel": conversation.platform,
            "status": conversation.status,
            "human_status": self._effective_human_status(conversation),
            "human_reason_label": human_reason_label,
            "chatbot_enabled": bool(conversation.chatbot_enabled),
            "contact": {
                "id": str(contact.id) if contact else None,
                "name": str((contact.name if contact else "") or "").strip() or "Sem nome",
                "phone": str((contact.phone if contact else "") or "").strip() or "-",
            },
            "identities": [
                {
                    "id": str(identity.id),
                    "channel": identity.platform,
                    "value": identity.platform_user_id,
                    "is_primary": bool(identity.is_primary),
                }
                for identity in identities
            ],
            "pillar_memories": memory_payload,
            "is_hot": bool(hot.get("is_hot")),
            "hot_reasons": hot.get("reasons", []),
        }

    def list_messages(self, *, db: Session, conversation_id: UUID, limit: int = 100, offset: int = 0) -> dict | None:
        conversation = db.get(Conversation, conversation_id)
        if conversation is None:
            return None
        rows = (
            db.execute(
                select(Message)
                .where(Message.conversation_id == conversation.id)
                .order_by(Message.created_at.asc())
            )
            .scalars()
            .all()
        )
        total = len(rows)
        paged = rows[offset : offset + max(1, min(limit, 500))]
        return {
            "items": [
                {
                    "id": str(item.id),
                    "channel": item.platform,
                    "type": "enviada" if item.direction == "outbound" else "recebida",
                    "text": item.text_content or "",
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                    "manual": str((item.raw_payload or {}).get("source") or "") == "dashboard_manual",
                    "automatic": bool(item.ai_generated),
                }
                for item in paged
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def list_contacts(self, *, db: Session, limit: int = 100, offset: int = 0) -> dict:
        rows = (
            db.execute(select(Contact).order_by(Contact.updated_at.desc()))
            .scalars()
            .all()
        )
        items: list[dict] = []
        for contact in rows:
            hot = LeadTemperatureService().evaluate_contact(db=db, contact_id=contact.id)
            has_appointment = (
                db.execute(
                    select(Appointment.id).where(
                        Appointment.contact_id == contact.id,
                        Appointment.status.in_(("reserved", "completed")),
                    )
                )
                .scalars()
                .first()
                is not None
            )
            primary_channel = self._primary_channel(db=db, contact=contact)
            items.append(
                {
                    "id": str(contact.id),
                    "name": str(contact.name or "").strip() or "Sem nome",
                    "phone": str(contact.phone or "").strip() or "-",
                    "scheduled": bool(has_appointment),
                    "main_channel": primary_channel,
                    "is_hot": bool(hot.get("is_hot")),
                }
            )
        total = len(items)
        paged = items[offset : offset + max(1, min(limit, 200))]
        return {"items": paged, "total": total, "limit": limit, "offset": offset}

    def search_contacts(self, *, db: Session, query_text: str, limit: int = 100, offset: int = 0) -> dict:
        normalized = str(query_text or "").strip().lower()
        payload = self.list_contacts(db=db, limit=1000, offset=0)
        if not normalized:
            return self.list_contacts(db=db, limit=limit, offset=offset)
        filtered: list[dict] = []
        for item in payload.get("items", []):
            hay = " ".join(
                [
                    str(item.get("name") or ""),
                    str(item.get("phone") or ""),
                    str(item.get("main_channel") or ""),
                ]
            ).lower()
            if normalized in hay:
                filtered.append(item)
        total = len(filtered)
        paged = filtered[offset : offset + max(1, min(limit, 200))]
        return {"items": paged, "total": total, "limit": limit, "offset": offset}

    def get_contact_detail(self, *, db: Session, contact_id: UUID) -> dict | None:
        contact = db.get(Contact, contact_id)
        if contact is None:
            return None
        hot = LeadTemperatureService().evaluate_contact(db=db, contact_id=contact.id)
        identities = (
            db.execute(
                select(ContactIdentity).where(ContactIdentity.contact_id == contact.id)
                .order_by(ContactIdentity.is_primary.desc(), ContactIdentity.created_at.asc())
            )
            .scalars()
            .all()
        )
        memories = (
            db.execute(
                select(ContactMemory).where(
                    ContactMemory.contact_id == contact.id,
                    ContactMemory.status == "active",
                )
            )
            .scalars()
            .all()
        )
        conversations = (
            db.execute(
                select(Conversation).where(Conversation.contact_id == contact.id).order_by(Conversation.updated_at.desc())
            )
            .scalars()
            .all()
        )
        appointments = (
            db.execute(
                select(Appointment).where(Appointment.contact_id == contact.id).order_by(Appointment.start_time.desc())
            )
            .scalars()
            .all()
        )
        last_interaction = max(
            [item.updated_at for item in conversations] + [contact.updated_at],
            default=contact.updated_at,
        )
        return {
            "main": {
                "id": str(contact.id),
                "name": str(contact.name or "").strip() or "Sem nome",
                "phone": str(contact.phone or "").strip() or "-",
                "customer_status": self._resolve_customer_status(contact=contact, memories=memories, conversations=conversations),
                "scheduled": any(item.status in {"reserved", "completed"} for item in appointments),
                "is_hot": bool(hot.get("is_hot")),
                "last_interaction_at": last_interaction.isoformat() if last_interaction else None,
            },
            "channels": [
                {"channel": identity.platform, "value": identity.platform_user_id, "is_primary": bool(identity.is_primary)}
                for identity in identities
                if str(identity.platform_user_id or "").strip()
            ],
            "memories": [
                {"key": item.memory_key, "label": self._friendly_memory_label(item.memory_key), "value": item.memory_value}
                for item in memories
            ],
            "conversations": [
                {
                    "id": str(item.id),
                    "status": item.status,
                    "channel": item.platform,
                    "last_message": item.last_inbound_message_text or "",
                }
                for item in conversations
            ],
            "agenda": [
                {
                    "id": str(item.id),
                    "start_time": item.start_time.isoformat() if item.start_time else None,
                    "status": item.status,
                }
                for item in appointments
            ],
            "notes": {"text": ""},
            "data_sources": {
                "local_database": {
                    "mode": "read_write",
                    "source": "postgresql",
                },
                "fcvip_api": {
                    "mode": "read_only",
                    "writes_to_local_db": False,
                    "sync_enabled": False,
                },
            },
            "fcvip_api": self._read_fcvip_snapshot(contact=contact),
        }

    def start_or_resume_conversation(
        self,
        *,
        db: Session,
        contact_id: UUID,
        channel: str = "whatsapp",
    ) -> dict | None:
        contact = db.get(Contact, contact_id)
        if contact is None:
            return None
        normalized_channel = str(channel or "whatsapp").strip().lower() or "whatsapp"
        conversation = (
            db.execute(
                select(Conversation)
                .where(
                    Conversation.contact_id == contact_id,
                    Conversation.platform == normalized_channel,
                )
                .order_by(
                    Conversation.status.asc(),
                    Conversation.updated_at.desc(),
                )
                .limit(1)
            )
            .scalars()
            .first()
        )
        if conversation is None:
            conversation = Conversation(
                contact_id=contact_id,
                platform=normalized_channel,
                status="open",
            )
            db.add(conversation)
            db.commit()
            db.refresh(conversation)
            return {"conversation_id": str(conversation.id), "status": "created"}

        if str(conversation.status or "").strip().lower() == "closed":
            conversation.status = "open"
            conversation.human_status = "closed"
            conversation.needs_human = False
            conversation.human_reason = None
            conversation.human_requested_at = None
            db.commit()
            return {"conversation_id": str(conversation.id), "status": "reopened"}

        return {"conversation_id": str(conversation.id), "status": "existing"}

    def _extract_customer_status(self, memories: list[ContactMemory]) -> str:
        for item in memories:
            if str(item.memory_key or "").strip().lower() == "cliente_status":
                value = str(item.memory_value or "").strip().lower()
                if value in {"antigo", "novo"}:
                    return value
                return str(item.memory_value or "").strip() or "-"
        return "-"

    def _resolve_customer_status(
        self,
        *,
        contact: Contact,
        memories: list[ContactMemory],
        conversations: list[Conversation],
    ) -> str:
        raw = self._extract_customer_status(memories)
        has_name = bool(str(contact.name or "").strip())
        if not has_name and len(conversations) <= 1:
            return "novo"
        return raw

    def _primary_channel(self, *, db: Session, contact: Contact) -> str:
        if contact.phone:
            return "whatsapp"
        identity = (
            db.execute(
                select(ContactIdentity).where(ContactIdentity.contact_id == contact.id).order_by(ContactIdentity.is_primary.desc())
            )
            .scalars()
            .first()
        )
        if identity is None:
            return "-"
        return identity.platform

    def _conversation_last_activity(self, conversation: Conversation) -> datetime:
        return (
            conversation.last_message_at
            or conversation.updated_at
            or conversation.created_at
            or datetime.fromtimestamp(0, tz=timezone.utc)
        )

    def _effective_human_status(self, conversation: Conversation) -> str:
        if str(conversation.status or "").strip().lower() == "closed":
            return "closed"
        explicit = str(conversation.human_status or "").strip().lower()
        if explicit:
            return explicit
        if conversation.needs_human:
            return "human_pending"
        return "closed"

    def _friendly_memory_label(self, key: str | None) -> str:
        raw = str(key or "").strip().lower()
        if not raw:
            return "-"
        return self._MEMORY_LABELS.get(raw, raw.replace("_", " ").capitalize())

    def _friendly_reason(self, reason: str | None) -> str:
        raw = str(reason or "").strip().lower()
        if not raw:
            return "Cliente pediu ajuda"
        return self._HUMAN_REASON_LABELS.get(raw, raw.replace("_", " ").capitalize())

    def _read_fcvip_snapshot(self, *, contact: Contact) -> dict:
        phone = str(contact.phone or "").strip()
        if not phone:
            return {
                "status": "not_checked",
                "message": "Sem telefone para consulta na FC VIP.",
            }
        result = FCVIPPartnerAPIService().lookup_customer_by_whatsapp(phone_number=phone)
        status = str(result.get("status") or "").strip().lower()
        if status != "completed":
            return {
                "status": status or "failed",
                "message": "Consulta FC VIP indisponivel no momento.",
            }
        return {
            "status": "completed",
            "customer_exists": bool(result.get("customer_exists")),
            "customer_status": str(result.get("customer_status") or "").strip() or ("antigo" if result.get("customer_exists") else "novo"),
            "checked_pages": result.get("checked_pages"),
        }
