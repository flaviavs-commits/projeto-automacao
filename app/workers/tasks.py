from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unicodedata
from uuid import UUID

from sqlalchemy import delete, func, select

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.audit_log import AuditLog
from app.models.contact import Contact
from app.models.contact_identity import ContactIdentity
from app.models.contact_memory import ContactMemory
from app.models.conversation import Conversation
from app.models.job import Job
from app.models.message import Message
from app.models.post import Post
from app.services.contact_memory_service import ContactMemoryService
from app.services.customer_identity_service import CustomerIdentityService
from app.services.fcvip_partner_api_service import FCVIPPartnerAPIService
from app.services.instagram_service import InstagramService
from app.services.instagram_publish_service import InstagramPublishService
from app.services.llm_reply_service import LLMReplyService
from app.services.menu_bot_service import MenuBotService
from app.services.memory_service import MemoryService
from app.services.routing_service import RoutingService
from app.services.tiktok_service import TikTokService
from app.services.transcription_service import TranscriptionService
from app.services.whatsapp_service import WhatsAppService
from app.services.youtube_service import YouTubeService
from app.workers.celery_app import celery_app


AUDIO_MESSAGE_TYPES = {"audio", "voice", "ptt"}
SPAM_MESSAGE_THRESHOLD = 5
SPAM_WINDOW_SECONDS = 10
SPAM_COOLDOWN_SECONDS = 60
_CLOSING_REPLY_MARKERS = (
    "por nada! sempre que precisar de ajuda",
    "fc vip agradece seu contato",
)
_WHATSAPP_LID_SUFFIX = "@lid"
FOLLOW_UP_WINDOWS_MINUTES = (30, 24 * 60)


def _legacy_qa_result(task_name: str, payload: dict | None = None) -> dict:
    return {
        "task": task_name,
        "status": "queued_stub",
        "payload": payload or {},
    }


def _safe_error_text(exc: Exception) -> str:
    return f"{exc.__class__.__name__}: {str(exc)}"[:2000]


def _normalize_text(value: str) -> str:
    lowered = str(value or "").lower()
    ascii_value = unicodedata.normalize("NFKD", lowered).encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_value.split())


def _should_mark_conversation_closed(*, llm_model: str, reply_text: str) -> bool:
    if str(llm_model or "").strip().lower() == "rule_close":
        return True
    normalized_reply = _normalize_text(reply_text)
    if not normalized_reply:
        return False
    return all(marker in normalized_reply for marker in _CLOSING_REPLY_MARKERS)


def _parse_uuid(value: object, field_name: str) -> UUID:
    as_text = str(value or "").strip()
    if not as_text:
        raise ValueError(f"{field_name} is required")
    try:
        return UUID(as_text)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"{field_name} is invalid: {as_text}") from exc


def _build_llm_disabled_fallback_reply(source_text: str) -> str:
    normalized = _normalize_text(source_text)
    asks_schedule = any(
        marker in normalized
        for marker in ("agendar", "agendamento", "horario", "disponibilidade", "reserva", "data")
    )
    asks_price = any(
        marker in normalized
        for marker in ("valor", "valores", "preco", "precos", "pacote", "orcamento")
    )
    if asks_schedule:
        return (
            "Recebi sua mensagem. O agendamento e feito direto no site oficial da FC VIP: "
            "https://www.fcvip.com.br/formulario"
        )
    if asks_price:
        return (
            "Recebi sua mensagem. Os valores e pacotes atualizados estao no site oficial da FC VIP: "
            "https://www.fcvip.com.br/formulario"
        )
    return (
        "Recebi sua mensagem e ja registrei seu atendimento. "
        "Se quiser, ja posso te orientar para agendamento no site: https://www.fcvip.com.br/formulario"
    )


def _has_followup_already_sent(*, db, conversation_id: UUID, stage_minutes: int) -> bool:
    logs = (
        db.execute(
            select(AuditLog).where(
                AuditLog.entity_type == "conversation",
                AuditLog.entity_id == conversation_id,
                AuditLog.event_type == "follow_up_sent",
            )
        )
        .scalars()
        .all()
    )
    for entry in logs:
        details = entry.details if isinstance(entry.details, dict) else {}
        if int(details.get("stage_minutes") or 0) == int(stage_minutes):
            return True
    return False


def _upsert_menu_memory_updates(
    *,
    db,
    contact_id: UUID,
    source_message_id: UUID | None,
    memory_updates: list[dict],
) -> list[str]:
    saved_keys: list[str] = []
    for update in memory_updates:
        key = str(update.get("memory_key") or "").strip()
        value = str(update.get("memory_value") or "").strip()
        if not key or not value:
            continue
        existing = (
            db.execute(
                select(ContactMemory).where(
                    ContactMemory.contact_id == contact_id,
                    ContactMemory.memory_key == key,
                )
            )
            .scalars()
            .first()
        )
        if existing is None:
            db.add(
                ContactMemory(
                    contact_id=contact_id,
                    source_message_id=source_message_id,
                    memory_key=key,
                    memory_value=value,
                    status="active",
                    importance=4,
                    confidence=0.9,
                )
            )
        else:
            existing.memory_value = value
            existing.source_message_id = source_message_id
            existing.status = "active"
            existing.importance = max(existing.importance, 4)
            existing.confidence = max(existing.confidence, 0.9)
        saved_keys.append(key)
    return saved_keys


def _create_job(job_type: str, payload: dict) -> UUID:
    with SessionLocal() as db:
        job = Job(
            job_type=job_type,
            status="processing",
            payload=payload,
            attempts=1,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return job.id


def _finish_job(job_id: UUID, status: str, error_message: str | None = None) -> None:
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if job is None:
            return
        job.status = status
        job.error_message = error_message
        db.commit()


def _resolve_final_job_status(service_status: str) -> str:
    if service_status in {
        "not_configured",
        "integration_disabled",
        "missing_credentials",
        "invalid_payload",
        "ignored",
    }:
        return "blocked_integration"
    if service_status in {"request_failed"}:
        return "failed"
    return "completed"


def _compute_spam_state(
    *,
    db,
    conversation_id: UUID,
    reference_time: datetime,
) -> dict:
    window_start = reference_time - timedelta(seconds=SPAM_WINDOW_SECONDS)
    window_end = reference_time + timedelta(seconds=SPAM_WINDOW_SECONDS)
    window_inbound_messages = (
        db.execute(
            select(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.direction == "inbound",
                Message.created_at >= window_start,
                Message.created_at <= window_end,
            )
            .order_by(Message.created_at.desc())
        )
        .scalars()
        .all()
    )

    latest_window_inbound = window_inbound_messages[0] if window_inbound_messages else None
    burst_count = len(window_inbound_messages)
    spam_active = burst_count > SPAM_MESSAGE_THRESHOLD
    cooldown_until = None
    if spam_active and latest_window_inbound is not None:
        cooldown_until = latest_window_inbound.created_at + timedelta(seconds=SPAM_COOLDOWN_SECONDS)

    return {
        "burst_count": burst_count,
        "latest_inbound_id": str(latest_window_inbound.id) if latest_window_inbound is not None else "",
        "spam_active": spam_active,
        "cooldown_until": cooldown_until,
    }


def _normalize_whatsapp_phone(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    lowered = raw.lower()
    if lowered.endswith(_WHATSAPP_LID_SUFFIX) or "@" in lowered:
        return ""
    digits = "".join(ch for ch in raw if ch.isdigit())
    return digits or ""


def _normalize_whatsapp_identity(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    lowered = raw.lower()
    if lowered.endswith("@s.whatsapp.net"):
        digits = "".join(ch for ch in lowered[: -len("@s.whatsapp.net")] if ch.isdigit())
        return digits
    if lowered.endswith("@c.us"):
        digits = "".join(ch for ch in lowered[: -len("@c.us")] if ch.isdigit())
        return digits
    if lowered.endswith(_WHATSAPP_LID_SUFFIX):
        digits = "".join(ch for ch in lowered[: -len(_WHATSAPP_LID_SUFFIX)] if ch.isdigit())
        return f"{digits}{_WHATSAPP_LID_SUFFIX}" if digits else lowered
    if "@" in lowered:
        return lowered
    digits = "".join(ch for ch in raw if ch.isdigit())
    return digits or lowered


def _normalize_collection_email(value: str | None) -> str:
    return str(value or "").strip().lower()


def _normalize_instagram_identity(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    return raw.lstrip("@")


def _normalize_facebook_identity(value: str | None) -> str:
    return str(value or "").strip().lower()


def _safe_link_identity(*, db, contact: Contact, platform: str, platform_user_id: str, conflicts: list[dict]) -> None:
    normalized_platform = str(platform or "").strip().lower()
    normalized_value = str(platform_user_id or "").strip()
    if not normalized_platform or not normalized_value:
        return

    existing = (
        db.execute(
            select(ContactIdentity).where(
                ContactIdentity.platform == normalized_platform,
                ContactIdentity.platform_user_id == normalized_value,
            )
        )
        .scalars()
        .first()
    )
    if existing is not None and existing.contact_id != contact.id:
        conflicts.append(
            {
                "platform": normalized_platform,
                "value": normalized_value,
                "existing_contact_id": str(existing.contact_id),
                "target_contact_id": str(contact.id),
            }
        )
        return

    CustomerIdentityService().upsert_identity_for_contact(
        db=db,
        contact=contact,
        platform=normalized_platform,
        platform_user_id=normalized_value,
    )


def _extract_collection_whatsapp_candidates(*, source_message: Message | None, contact: Contact | None) -> list[str]:
    candidates: list[str] = []
    if contact is not None:
        normalized_phone = _normalize_whatsapp_identity(str(contact.phone or ""))
        if normalized_phone:
            candidates.append(normalized_phone)
    raw_payload = source_message.raw_payload if source_message is not None and isinstance(source_message.raw_payload, dict) else {}
    for key in ("_resolved_platform_user_id", "_preferred_phone_number"):
        normalized_value = _normalize_whatsapp_identity(str(raw_payload.get(key) or ""))
        if normalized_value and normalized_value not in candidates:
            candidates.append(normalized_value)
    for item in raw_payload.get("_alternate_platform_user_ids") or []:
        normalized_value = _normalize_whatsapp_identity(str(item or ""))
        if normalized_value and normalized_value not in candidates:
            candidates.append(normalized_value)
    return candidates


def _find_collection_contact_match(
    *,
    db,
    current_contact: Contact | None,
    collection_data: dict,
    whatsapp_candidates: list[str],
) -> Contact | None:
    current_contact_id = str(current_contact.id) if current_contact is not None else ""

    for candidate in whatsapp_candidates:
        identity = (
            db.execute(
                select(ContactIdentity).where(
                    ContactIdentity.platform == "whatsapp",
                    ContactIdentity.platform_user_id == candidate,
                )
            )
            .scalars()
            .first()
        )
        if identity is not None and str(identity.contact_id) != current_contact_id:
            return identity.contact

    normalized_phone = _normalize_whatsapp_phone(str(collection_data.get("phone_normalized") or ""))
    if normalized_phone:
        contacts_with_phone = (
            db.execute(select(Contact).where(Contact.phone.isnot(None)))
            .scalars()
            .all()
        )
        for candidate_contact in contacts_with_phone:
            if current_contact is not None and candidate_contact.id == current_contact.id:
                continue
            contact_phone = _normalize_whatsapp_phone(str(candidate_contact.phone or ""))
            if contact_phone and contact_phone == normalized_phone:
                return candidate_contact

    normalized_email = _normalize_collection_email(collection_data.get("email"))
    if normalized_email:
        by_email = (
            db.execute(
                select(Contact).where(
                    Contact.email.isnot(None),
                    func.lower(Contact.email) == normalized_email,
                )
            )
            .scalars()
            .first()
        )
        if by_email is not None and (current_contact is None or by_email.id != current_contact.id):
            return by_email

    instagram_value = _normalize_instagram_identity(collection_data.get("instagram"))
    if instagram_value:
        by_ig_identity = (
            db.execute(
                select(ContactIdentity).where(
                    ContactIdentity.platform == "instagram",
                    ContactIdentity.platform_user_id == instagram_value,
                )
            )
            .scalars()
            .first()
        )
        if by_ig_identity is not None and str(by_ig_identity.contact_id) != current_contact_id:
            return by_ig_identity.contact

        by_ig_legacy = (
            db.execute(
                select(Contact).where(
                    Contact.instagram_user_id.isnot(None),
                    func.lower(Contact.instagram_user_id) == instagram_value,
                )
            )
            .scalars()
            .first()
        )
        if by_ig_legacy is not None and (current_contact is None or by_ig_legacy.id != current_contact.id):
            return by_ig_legacy

    facebook_value = _normalize_facebook_identity(collection_data.get("facebook"))
    if facebook_value:
        by_fb_identity = (
            db.execute(
                select(ContactIdentity).where(
                    ContactIdentity.platform == "facebook",
                    ContactIdentity.platform_user_id == facebook_value,
                )
            )
            .scalars()
            .first()
        )
        if by_fb_identity is not None and str(by_fb_identity.contact_id) != current_contact_id:
            return by_fb_identity.contact

    return None


def _finalize_collected_customer_data(
    *,
    db,
    conversation: Conversation,
    contact: Contact | None,
    source_message: Message | None,
    collection_data: dict,
) -> dict:
    required_name = str(collection_data.get("name") or "").strip()
    required_phone = str(collection_data.get("phone_normalized") or "").strip()
    required_email = _normalize_collection_email(collection_data.get("email"))
    if not (required_name and required_phone and required_email):
        return {"status": "incomplete"}

    if contact is None:
        contact = db.get(Contact, conversation.contact_id)
    if contact is None:
        return {"status": "missing_contact"}

    whatsapp_candidates = _extract_collection_whatsapp_candidates(source_message=source_message, contact=contact)
    matched_contact = _find_collection_contact_match(
        db=db,
        current_contact=contact,
        collection_data=collection_data,
        whatsapp_candidates=whatsapp_candidates,
    )
    target_contact = contact
    merged_from_contact_id: str | None = None
    field_conflicts: list[dict] = []
    identity_conflicts: list[dict] = []

    if matched_contact is not None and matched_contact.id != contact.id:
        merged_from_contact_id = str(contact.id)
        target_contact = matched_contact
        conversation.contact_id = target_contact.id

        if not str(target_contact.name or "").strip() and str(contact.name or "").strip():
            target_contact.name = contact.name
        if not str(target_contact.phone or "").strip() and str(contact.phone or "").strip():
            target_contact.phone = contact.phone
        if not str(target_contact.email or "").strip() and str(contact.email or "").strip():
            target_contact.email = contact.email
        if not str(target_contact.instagram_user_id or "").strip() and str(contact.instagram_user_id or "").strip():
            target_contact.instagram_user_id = contact.instagram_user_id

        linked_identities = (
            db.execute(select(ContactIdentity).where(ContactIdentity.contact_id == contact.id))
            .scalars()
            .all()
        )
        for identity in linked_identities:
            _safe_link_identity(
                db=db,
                contact=target_contact,
                platform=str(identity.platform or ""),
                platform_user_id=str(identity.platform_user_id or ""),
                conflicts=identity_conflicts,
            )

    if not str(target_contact.name or "").strip():
        target_contact.name = required_name
    elif str(target_contact.name or "").strip().lower() != required_name.lower():
        field_conflicts.append(
            {
                "field": "name",
                "existing_value": str(target_contact.name or "").strip(),
                "incoming_value": required_name,
            }
        )

    if not str(target_contact.phone or "").strip():
        target_contact.phone = required_phone
    else:
        existing_phone = _normalize_whatsapp_phone(str(target_contact.phone or ""))
        incoming_phone = _normalize_whatsapp_phone(required_phone)
        if existing_phone and incoming_phone and existing_phone != incoming_phone:
            field_conflicts.append(
                {
                    "field": "phone",
                    "existing_value": str(target_contact.phone or "").strip(),
                    "incoming_value": required_phone,
                }
            )

    if not str(target_contact.email or "").strip():
        target_contact.email = required_email
    else:
        existing_email = _normalize_collection_email(target_contact.email)
        if existing_email and required_email and existing_email != required_email:
            field_conflicts.append(
                {
                    "field": "email",
                    "existing_value": str(target_contact.email or "").strip(),
                    "incoming_value": required_email,
                }
            )

    instagram_value = _normalize_instagram_identity(collection_data.get("instagram"))
    if instagram_value:
        if not str(target_contact.instagram_user_id or "").strip():
            target_contact.instagram_user_id = instagram_value
        elif str(target_contact.instagram_user_id or "").strip().lower() != instagram_value:
            field_conflicts.append(
                {
                    "field": "instagram_user_id",
                    "existing_value": str(target_contact.instagram_user_id or "").strip(),
                    "incoming_value": instagram_value,
                }
            )

    target_contact.is_temporary = False
    whatsapp_identity_values: list[str] = []
    primary_whatsapp_identity = _normalize_whatsapp_identity(required_phone)
    if primary_whatsapp_identity:
        whatsapp_identity_values.append(primary_whatsapp_identity)
    for candidate in whatsapp_candidates:
        normalized_candidate = _normalize_whatsapp_identity(candidate)
        if normalized_candidate and normalized_candidate not in whatsapp_identity_values:
            whatsapp_identity_values.append(normalized_candidate)
    for normalized_candidate in whatsapp_identity_values:
        _safe_link_identity(
            db=db,
            contact=target_contact,
            platform="whatsapp",
            platform_user_id=normalized_candidate,
            conflicts=identity_conflicts,
        )
    if instagram_value:
        _safe_link_identity(db=db, contact=target_contact, platform="instagram", platform_user_id=instagram_value, conflicts=identity_conflicts)
    facebook_value = _normalize_facebook_identity(collection_data.get("facebook"))
    if facebook_value:
        _safe_link_identity(db=db, contact=target_contact, platform="facebook", platform_user_id=facebook_value, conflicts=identity_conflicts)

    db.add(
        AuditLog(
            entity_type="contact",
            entity_id=target_contact.id,
            event_type="customer_data_collected",
            details={
                "contact_id": str(target_contact.id),
                "conversation_id": str(conversation.id),
                "merged_from_contact_id": merged_from_contact_id,
                "source": "whatsapp/chatbot",
                "field_conflicts": field_conflicts,
                "identity_conflicts": identity_conflicts,
                "collected_fields": {
                    "name": required_name,
                    "phone_normalized": required_phone,
                    "email": required_email,
                    "instagram": instagram_value or None,
                    "facebook": facebook_value or None,
                },
            },
        )
    )
    conversation.customer_collection_data = {}
    conversation.customer_collection_step = None

    return {
        "status": "completed",
        "contact_id": str(target_contact.id),
        "merged_from_contact_id": merged_from_contact_id,
        "field_conflicts": field_conflicts,
        "identity_conflicts": identity_conflicts,
    }


def _resolve_customer_profile_for_reply(*, contact: Contact | None) -> dict:
    if contact is None:
        return {"status": "skipped_missing_contact", "source": "local"}

    phone = _normalize_whatsapp_phone(contact.phone)
    if not phone:
        return {"status": "skipped_missing_phone", "source": "local"}

    lookup_result = FCVIPPartnerAPIService().lookup_customer_by_whatsapp(phone_number=phone)
    lookup_status = str(lookup_result.get("status") or "").strip().lower()
    if lookup_status == "completed":
        return {
            "status": "completed",
            "source": "partner_api",
            "customer_exists": bool(lookup_result.get("customer_exists")),
            "checked_pages": lookup_result.get("checked_pages"),
        }

    return {
        "status": lookup_status or "request_failed",
        "source": "partner_api",
        "detail": lookup_result.get("detail"),
        "status_code": lookup_result.get("status_code"),
    }


def _inject_runtime_customer_status_memory(
    *,
    key_memories: list[dict],
    customer_exists: bool,
    source: str,
) -> list[dict]:
    if source != "partner_api":
        return list(key_memories)

    filtered: list[dict] = []
    for memory in list(key_memories):
        key = str(memory.get("key") or "").strip().lower()
        if key in {"cliente_status", "customer_status_source"}:
            continue
        filtered.append(memory)

    filtered.append(
        {
            "key": "cliente_status",
            "value": "antigo" if customer_exists else "novo",
            "importance": 5,
            "confidence": 0.99,
            "updated_at": None,
        }
    )
    filtered.append(
        {
            "key": "customer_status_source",
            "value": "partner_api",
            "importance": 5,
            "confidence": 0.99,
            "updated_at": None,
        }
    )
    return filtered


def _strip_api_derived_memory_updates(*, memory_updates: list[dict], source: str) -> list[dict]:
    if source != "partner_api":
        return memory_updates
    blocked_keys = {"cliente_status", "tipo_agendamento"}
    return [
        update
        for update in memory_updates
        if str(update.get("memory_key") or "").strip().lower() not in blocked_keys
    ]


def _close_stale_open_conversations(*, db, now_utc: datetime) -> None:
    stale_minutes = max(1, int(settings.conversation_auto_close_after_minutes))
    cutoff = now_utc - timedelta(minutes=stale_minutes)
    stale_open_conversations = (
        db.execute(
            select(Conversation).where(
                Conversation.status == "open",
                Conversation.last_message_at.isnot(None),
                Conversation.last_message_at < cutoff,
            )
        )
        .scalars()
        .all()
    )
    for conversation in stale_open_conversations:
        conversation.status = "closed"


def _contact_has_reliable_identity(*, db, contact: Contact) -> bool:
    if _normalize_whatsapp_phone(contact.phone):
        return True

    identities = (
        db.execute(
            select(ContactIdentity).where(ContactIdentity.contact_id == contact.id)
        )
        .scalars()
        .all()
    )
    for identity in identities:
        platform = str(identity.platform or "").strip().lower()
        value = str(identity.platform_user_id or "").strip().lower()
        if not value:
            continue
        if platform != "whatsapp":
            return True
        if value.endswith(_WHATSAPP_LID_SUFFIX) or "@" in value:
            continue
        if _normalize_whatsapp_phone(value):
            return True
    return False


def _contact_has_pillar_memories(*, db, contact_id: UUID) -> bool:
    pillar_keys = list(ContactMemoryService.PILLAR_MEMORY_KEYS)
    if not pillar_keys:
        return False
    memory = (
        db.execute(
            select(ContactMemory.id).where(
                ContactMemory.contact_id == contact_id,
                ContactMemory.status == "active",
                ContactMemory.memory_key.in_(pillar_keys),
            )
        )
        .scalars()
        .first()
    )
    return memory is not None


def _prune_conversation_messages(*, db, conversation_id: UUID) -> int:
    retention_limit = max(1, int(settings.message_retention_max_per_conversation))
    ordered_ids = (
        db.execute(
            select(Message.id)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
        )
        .scalars()
        .all()
    )
    removable_ids = ordered_ids[retention_limit:]
    if not removable_ids:
        return 0

    db.execute(delete(Message).where(Message.id.in_(removable_ids)))
    db.add(
        AuditLog(
            entity_type="conversation",
            entity_id=conversation_id,
            event_type="message_retention_pruned",
            details={
                "conversation_id": str(conversation_id),
                "removed_count": len(removable_ids),
                "limit_applied": retention_limit,
            },
        )
    )
    return len(removable_ids)


def _cleanup_temporary_contact_if_eligible(*, db, contact_id: UUID, now_utc: datetime) -> None:
    contact = db.get(Contact, contact_id)
    if contact is None or not bool(contact.is_temporary):
        return

    if _contact_has_reliable_identity(db=db, contact=contact):
        contact.is_temporary = False
        return

    stale_minutes = max(1, int(settings.conversation_auto_close_after_minutes))
    stale_cutoff = now_utc - timedelta(minutes=stale_minutes)
    conversations = (
        db.execute(
            select(Conversation).where(Conversation.contact_id == contact.id)
        )
        .scalars()
        .all()
    )

    if not conversations:
        return

    for conversation in conversations:
        is_closed_and_stale = bool(
            str(conversation.status or "").strip().lower() == "closed"
            and conversation.last_message_at is not None
            and conversation.last_message_at < stale_cutoff
        )
        is_stale_open = bool(
            str(conversation.status or "").strip().lower() == "open"
            and conversation.last_message_at is not None
            and conversation.last_message_at < stale_cutoff
        )
        if not (is_closed_and_stale or is_stale_open):
            return

    if _contact_has_pillar_memories(db=db, contact_id=contact.id):
        return

    ttl_minutes = max(1, int(settings.temp_contact_ttl_minutes))
    if contact.created_at and contact.created_at > now_utc - timedelta(minutes=ttl_minutes):
        return

    for conversation in conversations:
        db.execute(delete(Message).where(Message.conversation_id == conversation.id))
        db.delete(conversation)

    db.add(
        AuditLog(
            entity_type="contact",
            entity_id=contact.id,
            event_type="temporary_contact_pruned",
            details={
                "contact_id": str(contact.id),
                "customer_id": contact.customer_id,
                "conversation_count_removed": len(conversations),
            },
        )
    )
    db.delete(contact)


@celery_app.task(name="process_incoming_message")
def process_incoming_message(payload: dict) -> dict:
    if payload.get("qa_probe"):
        return _legacy_qa_result("process_incoming_message", payload)

    job_id = _create_job("process_incoming_message", payload)
    try:
        message_id = _parse_uuid(payload.get("message_id"), "message_id")
        with SessionLocal() as db:
            message = db.get(Message, message_id)
            if message is None:
                raise ValueError(f"message not found: {message_id}")

            conversation = db.get(Conversation, message.conversation_id)
            if conversation is None:
                raise ValueError(f"conversation not found: {message.conversation_id}")
            contact = db.get(Contact, conversation.contact_id)

            if not bool(getattr(conversation, "chatbot_enabled", True)):
                db.add(
                    AuditLog(
                        entity_type="conversation",
                        entity_id=conversation.id,
                        event_type="chatbot_disabled_inbound_stored",
                        details={
                            "conversation_id": str(conversation.id),
                            "message_id": str(message.id),
                        },
                    )
                )
                db.commit()
                _finish_job(job_id, "completed")
                return {
                    "task": "process_incoming_message",
                    "status": "ignored_chatbot_disabled",
                    "job_id": str(job_id),
                    "message_id": str(message_id),
                }

            context = MemoryService().build_context(str(conversation.id))
            route = RoutingService().route_intent(
                {
                    "platform": message.platform,
                    "message_type": message.message_type,
                    "has_text": bool((message.text_content or "").strip()),
                    "has_media": bool((message.media_url or "").strip()),
                }
            )

            transcription_result: dict | None = None
            if message.message_type in AUDIO_MESSAGE_TYPES and message.media_url:
                transcription_result = transcribe_audio(
                    {
                        "message_id": str(message.id),
                        "media_url": message.media_url,
                    }
                )

            inbound_text = (message.transcription or message.text_content or "").strip()
            if settings.llm_enabled:
                strict_temporary_mode = bool(contact is not None and contact.is_temporary and not contact.phone)
                memory_result = ContactMemoryService().save_from_inbound_text(
                    db=db,
                    contact_id=conversation.contact_id,
                    source_message_id=message.id,
                    inbound_text=inbound_text,
                    strict_temporary_mode=strict_temporary_mode,
                )
            else:
                memory_result = {
                    "status": "skipped_menu_mode",
                    "saved_keys": [],
                }
            reply_result = generate_reply(
                {
                    "conversation_id": str(conversation.id),
                    "platform": message.platform,
                    "source_message_id": str(message.id),
                    "source_text": inbound_text,
                    "phone_number_id": payload.get("phone_number_id"),
                    "memory_saved_keys": memory_result.get("saved_keys"),
                }
            )

            db.add(
                AuditLog(
                    entity_type="message",
                    entity_id=message.id,
                    event_type="incoming_message_processed",
                    details={
                        "message_id": str(message.id),
                        "conversation_id": str(conversation.id),
                        "route": route,
                        "context_status": context.get("status"),
                        "memory_status": memory_result.get("status"),
                        "memory_saved_keys": memory_result.get("saved_keys"),
                        "transcription_status": (transcription_result or {}).get("status"),
                        "reply_status": reply_result.get("status"),
                    },
                )
            )
            db.commit()

        _finish_job(job_id, "completed")
        return {
            "task": "process_incoming_message",
            "status": "completed",
            "job_id": str(job_id),
            "message_id": str(message_id),
        }
    except Exception as exc:  # noqa: BLE001
        error_text = _safe_error_text(exc)
        _finish_job(job_id, "failed", error_text)
        return {
            "task": "process_incoming_message",
            "status": "failed",
            "job_id": str(job_id),
            "error": error_text,
        }


@celery_app.task(name="transcribe_audio")
def transcribe_audio(payload: dict) -> dict:
    job_id = _create_job("transcribe_audio", payload)
    try:
        media_url = str(payload.get("media_url") or "").strip() or None
        result = TranscriptionService().transcribe(media_url)

        message_id_raw = payload.get("message_id")
        if message_id_raw and payload.get("transcription_text"):
            message_id = _parse_uuid(message_id_raw, "message_id")
            with SessionLocal() as db:
                message = db.get(Message, message_id)
                if message is not None:
                    message.transcription = str(payload.get("transcription_text"))
                    db.commit()

        _finish_job(job_id, "completed")
        return {
            "task": "transcribe_audio",
            "status": str(result.get("status") or "completed"),
            "job_id": str(job_id),
            "provider": result.get("provider"),
            "media_url": media_url,
        }
    except Exception as exc:  # noqa: BLE001
        error_text = _safe_error_text(exc)
        _finish_job(job_id, "failed", error_text)
        return {
            "task": "transcribe_audio",
            "status": "failed",
            "job_id": str(job_id),
            "error": error_text,
        }


@celery_app.task(name="generate_reply")
def generate_reply(payload: dict) -> dict:
    job_id = _create_job("generate_reply", payload)
    try:
        conversation_id = _parse_uuid(payload.get("conversation_id"), "conversation_id")
        source_text = str(payload.get("source_text") or "").strip()
        if not source_text:
            source_text = "Mensagem recebida sem texto. Solicitar detalhes de agendamento."

        platform = str(payload.get("platform") or "whatsapp")
        source_message_id = str(payload.get("source_message_id") or "").strip() or None
        phone_number_id = str(payload.get("phone_number_id") or "").strip() or None
        now_utc = datetime.now(timezone.utc)
        spam_retry_count = int(payload.get("spam_retry_count") or 0)
        dispatch_result: dict | None = None
        llm_result: dict | None = None
        reply_text: str | None = None
        spam_notice: str | None = None

        with SessionLocal() as db:
            conversation = db.get(Conversation, conversation_id)
            if conversation is None:
                raise ValueError(f"conversation not found: {conversation_id}")
            contact = db.get(Contact, conversation.contact_id)
            source_message: Message | None = None
            if source_message_id:
                source_message_uuid = _parse_uuid(source_message_id, "source_message_id")
                source_message = db.get(Message, source_message_uuid)
                if source_message is None:
                    raise ValueError(f"source_message not found: {source_message_id}")
            context = MemoryService().build_context(str(conversation.id))
            key_memories = list(context.get("key_memories") or [])
            if contact is not None:
                if str(contact.name or "").strip():
                    key_memories.append({"key": "nome_contato", "value": str(contact.name).strip()})
                if str(contact.phone or "").strip():
                    key_memories.append({"key": "telefone_contato", "value": str(contact.phone).strip()})

            spam_reference_time = source_message.created_at if source_message is not None else now_utc
            spam_state = _compute_spam_state(
                db=db,
                conversation_id=conversation.id,
                reference_time=spam_reference_time,
            )
            latest_inbound_id = str(spam_state.get("latest_inbound_id") or "").strip()
            if bool(spam_state.get("spam_active")) and source_message_id and latest_inbound_id:
                if source_message_id != latest_inbound_id:
                    db.add(
                        AuditLog(
                            entity_type="conversation",
                            entity_id=conversation.id,
                            event_type="spam_non_latest_ignored",
                            details={
                                "source_message_id": source_message_id,
                                "latest_inbound_id": latest_inbound_id,
                                "burst_count": spam_state.get("burst_count"),
                            },
                        )
                    )
                    db.commit()
                    _finish_job(job_id, "completed")
                    return {
                        "task": "generate_reply",
                        "status": "ignored_spam_non_latest",
                        "job_id": str(job_id),
                        "conversation_id": str(conversation_id),
                        "source_message_id": source_message_id,
                        "latest_inbound_id": latest_inbound_id,
                    }

            if bool(spam_state.get("spam_active")) and latest_inbound_id:
                latest_inbound_uuid = _parse_uuid(latest_inbound_id, "latest_inbound_id")
                latest_inbound_message = db.get(Message, latest_inbound_uuid)
                if latest_inbound_message is not None:
                    source_message_id = latest_inbound_id
                    source_text = (latest_inbound_message.transcription or latest_inbound_message.text_content or "").strip() or source_text

                cooldown_until = spam_state.get("cooldown_until")
                if isinstance(cooldown_until, datetime) and now_utc < cooldown_until and spam_retry_count < 1:
                    remaining_seconds = max(1, int((cooldown_until - now_utc).total_seconds()))
                    retry_payload = {
                        **payload,
                        "source_message_id": source_message_id,
                        "source_text": source_text,
                        "spam_retry_count": spam_retry_count + 1,
                    }
                    generate_reply.apply_async(args=[retry_payload], countdown=remaining_seconds)
                    db.add(
                        AuditLog(
                            entity_type="conversation",
                            entity_id=conversation.id,
                            event_type="spam_cooldown_scheduled",
                            details={
                                "source_message_id": source_message_id,
                                "latest_inbound_id": latest_inbound_id,
                                "burst_count": spam_state.get("burst_count"),
                                "retry_in_seconds": remaining_seconds,
                                "spam_retry_count": spam_retry_count + 1,
                            },
                        )
                    )
                    db.commit()
                    _finish_job(job_id, "completed")
                    return {
                        "task": "generate_reply",
                        "status": "deferred_spam_cooldown",
                        "job_id": str(job_id),
                        "conversation_id": str(conversation_id),
                        "retry_in_seconds": remaining_seconds,
                        "burst_count": spam_state.get("burst_count"),
                    }

                spam_notice = (
                    "Detectamos alta atividade em curto intervalo e, para preservar desempenho, "
                    "responderei apenas a sua ultima mensagem."
                )

            customer_profile_lookup = _resolve_customer_profile_for_reply(contact=contact)
            customer_exists = bool(contact is not None and not contact.is_temporary)
            customer_status_source = "local"
            if customer_profile_lookup.get("status") == "completed":
                customer_exists = bool(customer_profile_lookup.get("customer_exists"))
                customer_status_source = "partner_api"

            effective_key_memories = _inject_runtime_customer_status_memory(
                key_memories=key_memories,
                customer_exists=customer_exists,
                source=customer_status_source,
            )

            memory_saved_keys: list[str] = []
            if settings.llm_enabled:
                llm_result = LLMReplyService().generate_reply(
                    user_text=source_text,
                    context_messages=context.get("memory_items") or [],
                    key_memories=effective_key_memories,
                )
                llm_status = str((llm_result or {}).get("status") or "")
                llm_model = str((llm_result or {}).get("model") or "")
                reply_text = str((llm_result or {}).get("reply_text") or "").strip()
                if llm_status not in {"completed", "blocked_out_of_scope"} or not reply_text:
                    raise RuntimeError(f"llm_reply_generation_failed: status={llm_status}")
            else:
                is_new_chat = not bool(str(conversation.menu_state or "").strip())
                contact_identities = (
                    db.execute(
                        select(ContactIdentity).where(ContactIdentity.contact_id == conversation.contact_id)
                    )
                    .scalars()
                    .all()
                )
                identity_payload = [
                    {
                        "platform": str(identity.platform or ""),
                        "platform_user_id": str(identity.platform_user_id or ""),
                        "normalized_value": str(identity.normalized_value or ""),
                    }
                    for identity in contact_identities
                ]
                menu_result = MenuBotService().handle_message(
                    message_text=source_text,
                    conversation=SimpleNamespace(
                        menu_state=conversation.menu_state,
                        is_new_chat=is_new_chat,
                        customer_collection_data=getattr(conversation, "customer_collection_data", {}) or {},
                    ),
                    contact=contact,
                    customer_exists=customer_exists,
                    identities=identity_payload,
                    memories=effective_key_memories,
                    collection_data=getattr(conversation, "customer_collection_data", {}) or {},
                )
                llm_result = {"status": "completed", "model": "menu_bot"}
                llm_status = "completed"
                llm_model = "menu_bot"
                reply_text = str(menu_result.get("reply_text") or "").strip()
                if not reply_text:
                    raise RuntimeError("menu_bot_failed_without_reply")
                conversation.menu_state = str(menu_result.get("next_state") or conversation.menu_state or "main_menu")
                conversation.customer_collection_data = dict(menu_result.get("collected_customer_data") or {})
                conversation.customer_collection_step = menu_result.get("customer_collection_step")
                if bool(menu_result.get("close_conversation")):
                    conversation.status = "closed"
                    conversation.menu_state = "end"
                    conversation.customer_collection_step = None
                menu_needs_human = bool(menu_result.get("needs_human"))
                conversation.needs_human = menu_needs_human
                conversation.human_reason = str(menu_result.get("human_reason") or "").strip() or None
                conversation.human_requested_at = now_utc if menu_needs_human else None
                conversation.human_status = "human_pending" if menu_needs_human else "closed"
                if menu_needs_human:
                    db.add(
                        AuditLog(
                            entity_type="conversation",
                            entity_id=conversation.id,
                            event_type="human_requested",
                            details={
                                "conversation_id": str(conversation.id),
                                "human_reason": conversation.human_reason,
                                "contact_name": str((contact.name if contact else "") or "").strip() or None,
                                "contact_phone": str((contact.phone if contact else "") or "").strip() or None,
                                "last_inbound_message_text": conversation.last_inbound_message_text,
                            },
                        )
                    )
                collection_finalize_result = {"status": "skipped"}
                collected_customer_data = dict(menu_result.get("collected_customer_data") or {})
                has_required_collection = bool(
                    str(collected_customer_data.get("name") or "").strip()
                    and str(collected_customer_data.get("phone_normalized") or "").strip()
                    and str(collected_customer_data.get("email") or "").strip()
                )
                if has_required_collection and menu_result.get("customer_collection_step") in {None, ""}:
                    collection_finalize_result = _finalize_collected_customer_data(
                        db=db,
                        conversation=conversation,
                        contact=contact,
                        source_message=source_message,
                        collection_data=collected_customer_data,
                    )
                    contact = db.get(Contact, conversation.contact_id)
                memory_saved_keys = _upsert_menu_memory_updates(
                    db=db,
                    contact_id=conversation.contact_id,
                    source_message_id=source_message.id if source_message is not None else None,
                    memory_updates=_strip_api_derived_memory_updates(
                        memory_updates=list(menu_result.get("memory_updates") or []),
                        source=customer_status_source,
                    ),
                )
                if collection_finalize_result.get("status") == "completed":
                    memory_saved_keys.append("customer_data_collected")
            if spam_notice:
                reply_text = f"{spam_notice}\n\n{reply_text}".strip()
            if _should_mark_conversation_closed(llm_model=llm_model, reply_text=reply_text):
                conversation.status = "closed"

            outbound = Message(
                conversation_id=conversation.id,
                platform=platform,
                direction="outbound",
                message_type="text",
                text_content=reply_text,
                transcription=None,
                media_url=None,
                raw_payload={
                    "source": "celery_auto_reply",
                    "source_message_id": source_message_id,
                    "llm_status": llm_status,
                    "llm_model": llm_model,
                },
                ai_generated=True,
            )
            db.add(outbound)
            conversation.last_message_at = now_utc
            db.flush()

            if platform == "whatsapp" and contact is not None and contact.phone:
                dispatch_result = WhatsAppService().send_text_message(
                    {
                        "to": contact.phone,
                        "text": reply_text,
                        "phone_number_id": phone_number_id,
                    }
                )
                outbound.raw_payload = {
                    **outbound.raw_payload,
                    "dispatch_result": dispatch_result,
                }
            elif platform == "instagram":
                recipient_id = ""
                source_payload = source_message.raw_payload if source_message is not None else {}
                if isinstance(source_payload, dict):
                    sender_payload = source_payload.get("sender")
                    if isinstance(sender_payload, dict):
                        recipient_id = str(sender_payload.get("id") or "").strip()
                if not recipient_id and contact is not None:
                    recipient_id = str(contact.instagram_user_id or "").strip()

                if recipient_id:
                    dispatch_result = InstagramService().send_text_message(
                        {
                            "to": recipient_id,
                            "text": reply_text,
                        }
                    )
                else:
                    dispatch_result = {
                        "status": "invalid_payload",
                        "service": "instagram",
                        "action": "send_text_message",
                        "detail": "missing_recipient_id",
                    }
                outbound.raw_payload = {
                    **outbound.raw_payload,
                    "dispatch_result": dispatch_result,
                }
                dispatch_status = str((dispatch_result or {}).get("status") or "").strip().lower()
                if dispatch_status not in {"completed", "ok", "success"} and contact is not None and contact.phone:
                    whatsapp_dispatch_result = WhatsAppService().send_text_message(
                        {
                            "to": contact.phone,
                            "text": reply_text,
                        }
                    )
                    outbound.raw_payload = {
                        **outbound.raw_payload,
                        "dispatch_result": whatsapp_dispatch_result,
                        "meta_dispatch_result": dispatch_result,
                        "fallback_channel": "whatsapp",
                    }
                    dispatch_result = whatsapp_dispatch_result
                    db.add(
                        AuditLog(
                            entity_type="conversation",
                            entity_id=conversation.id,
                            event_type="channel_fallback_to_whatsapp",
                            details={
                                "platform": platform,
                                "source_message_id": source_message_id,
                                "primary_dispatch_status": dispatch_status,
                            },
                        )
                    )

            db.add(
                AuditLog(
                    entity_type="conversation",
                    entity_id=conversation.id,
                    event_type="auto_reply_generated",
                    details={
                        "source_message_id": source_message_id,
                        "reply_message_preview": reply_text[:120],
                        "llm_status": llm_status,
                        "llm_model": llm_model,
                        "dispatch_status": (dispatch_result or {}).get("status"),
                        "menu_memory_saved_keys": memory_saved_keys,
                    },
                )
            )
            _close_stale_open_conversations(db=db, now_utc=now_utc)
            _prune_conversation_messages(db=db, conversation_id=conversation.id)
            _cleanup_temporary_contact_if_eligible(
                db=db,
                contact_id=conversation.contact_id,
                now_utc=now_utc,
            )
            db.commit()
            db.refresh(outbound)
            for stage_minutes in FOLLOW_UP_WINDOWS_MINUTES:
                send_follow_up.apply_async(
                    kwargs={
                        "conversation_id": str(conversation.id),
                        "stage_minutes": int(stage_minutes),
                        "reply_message_id": str(outbound.id),
                    },
                    countdown=int(stage_minutes) * 60,
                )

        _finish_job(job_id, "completed")
        return {
            "task": "generate_reply",
            "status": "completed",
            "job_id": str(job_id),
            "conversation_id": str(conversation_id),
            "reply_message_id": str(outbound.id),
            "llm_status": (llm_result or {}).get("status"),
            "llm_model": llm_model,
            "dispatch_status": (dispatch_result or {}).get("status"),
        }
    except Exception as exc:  # noqa: BLE001
        error_text = _safe_error_text(exc)
        _finish_job(job_id, "failed", error_text)
        return {
            "task": "generate_reply",
            "status": "failed",
            "job_id": str(job_id),
            "error": error_text,
        }


def _run_external_publish(
    job_type: str,
    payload: dict,
    fn,
) -> dict:
    job_id = _create_job(job_type, payload)
    try:
        result = fn(payload)
        result_status = str(result.get("status") or "completed")
        final_status = _resolve_final_job_status(result_status)
        _finish_job(job_id, final_status)
        return {
            "task": job_type,
            "status": final_status,
            "job_id": str(job_id),
            "result": result,
        }
    except Exception as exc:  # noqa: BLE001
        error_text = _safe_error_text(exc)
        _finish_job(job_id, "failed", error_text)
        return {
            "task": job_type,
            "status": "failed",
            "job_id": str(job_id),
            "error": error_text,
        }


@celery_app.task(name="publish_instagram")
def publish_instagram(payload: dict) -> dict:
    service = InstagramPublishService()
    return _run_external_publish("publish_instagram", payload, service.publish_post)


@celery_app.task(name="publish_tiktok")
def publish_tiktok(payload: dict) -> dict:
    service = TikTokService()
    return _run_external_publish("publish_tiktok", payload, service.publish_post)


@celery_app.task(name="publish_youtube")
def publish_youtube(payload: dict) -> dict:
    service = YouTubeService()
    return _run_external_publish("publish_youtube", payload, service.publish_video)


@celery_app.task(name="sync_youtube_comments")
def sync_youtube_comments(payload: dict) -> dict:
    job_id = _create_job("sync_youtube_comments", payload)
    try:
        service = YouTubeService()
        result = service.sync_comments(str(payload.get("channel_id") or "").strip() or None)
        result_status = str(result.get("status") or "completed")
        final_status = _resolve_final_job_status(result_status)
        _finish_job(job_id, final_status)
        return {
            "task": "sync_youtube_comments",
            "status": final_status,
            "job_id": str(job_id),
            "result": result,
        }
    except Exception as exc:  # noqa: BLE001
        error_text = _safe_error_text(exc)
        _finish_job(job_id, "failed", error_text)
        return {
            "task": "sync_youtube_comments",
            "status": "failed",
            "job_id": str(job_id),
            "error": error_text,
        }


@celery_app.task(name="send_follow_up")
def send_follow_up(*, conversation_id: str, stage_minutes: int, reply_message_id: str | None = None) -> dict:
    job_id = _create_job(
        "send_follow_up",
        {
            "conversation_id": conversation_id,
            "stage_minutes": stage_minutes,
            "reply_message_id": reply_message_id,
        },
    )
    try:
        conversation_uuid = _parse_uuid(conversation_id, "conversation_id")
        with SessionLocal() as db:
            conversation = db.get(Conversation, conversation_uuid)
            if conversation is None:
                raise ValueError(f"conversation not found: {conversation_uuid}")
            if not bool(getattr(conversation, "chatbot_enabled", True)):
                _finish_job(job_id, "completed")
                return {
                    "task": "send_follow_up",
                    "status": "ignored_chatbot_disabled",
                    "job_id": str(job_id),
                    "conversation_id": conversation_id,
                }
            if str(conversation.status or "").strip().lower() != "open":
                _finish_job(job_id, "completed")
                return {
                    "task": "send_follow_up",
                    "status": "ignored_conversation_closed",
                    "job_id": str(job_id),
                    "conversation_id": conversation_id,
                }

            latest_inbound = (
                db.execute(
                    select(Message)
                    .where(
                        Message.conversation_id == conversation.id,
                        Message.direction == "inbound",
                    )
                    .order_by(Message.created_at.desc())
                )
                .scalars()
                .first()
            )
            if latest_inbound is None:
                _finish_job(job_id, "completed")
                return {
                    "task": "send_follow_up",
                    "status": "ignored_without_inbound",
                    "job_id": str(job_id),
                    "conversation_id": conversation_id,
                }

            now_utc = datetime.now(timezone.utc)
            due_at = latest_inbound.created_at + timedelta(minutes=max(1, int(stage_minutes)))
            if now_utc < due_at:
                _finish_job(job_id, "completed")
                return {
                    "task": "send_follow_up",
                    "status": "ignored_not_due",
                    "job_id": str(job_id),
                    "conversation_id": conversation_id,
                }

            outbound_after_latest_inbound = (
                db.execute(
                    select(Message.id)
                    .where(
                        Message.conversation_id == conversation.id,
                        Message.direction == "outbound",
                        Message.created_at > latest_inbound.created_at,
                    )
                )
                .scalars()
                .first()
            )
            if outbound_after_latest_inbound is not None:
                _finish_job(job_id, "completed")
                return {
                    "task": "send_follow_up",
                    "status": "ignored_already_replied",
                    "job_id": str(job_id),
                    "conversation_id": conversation_id,
                }

            if _has_followup_already_sent(db=db, conversation_id=conversation.id, stage_minutes=stage_minutes):
                _finish_job(job_id, "completed")
                return {
                    "task": "send_follow_up",
                    "status": "ignored_duplicate_stage",
                    "job_id": str(job_id),
                    "conversation_id": conversation_id,
                }

            contact = db.get(Contact, conversation.contact_id)
            if contact is None or not contact.phone:
                _finish_job(job_id, "completed")
                return {
                    "task": "send_follow_up",
                    "status": "ignored_missing_phone",
                    "job_id": str(job_id),
                    "conversation_id": conversation_id,
                }

            follow_up_text = (
                "Passando para retomar seu atendimento. "
                "Se quiser, te ajudo agora com valores e agendamento da FC VIP."
            )
            dispatch_result = WhatsAppService().send_text_message({"to": contact.phone, "text": follow_up_text})
            dispatch_status = str((dispatch_result or {}).get("status") or "").strip().lower()
            if dispatch_status not in {"completed", "ok", "success"}:
                _finish_job(job_id, "failed")
                return {
                    "task": "send_follow_up",
                    "status": "failed_dispatch",
                    "job_id": str(job_id),
                    "conversation_id": conversation_id,
                    "dispatch_status": dispatch_status or "unknown",
                }

            outbound = Message(
                conversation_id=conversation.id,
                platform="whatsapp",
                direction="outbound",
                message_type="text",
                text_content=follow_up_text,
                transcription=None,
                media_url=None,
                raw_payload={
                    "source": "auto_follow_up",
                    "stage_minutes": int(stage_minutes),
                    "reply_message_id": reply_message_id,
                    "dispatch_result": dispatch_result,
                },
                ai_generated=False,
            )
            db.add(outbound)
            conversation.last_message_at = now_utc
            db.add(
                AuditLog(
                    entity_type="conversation",
                    entity_id=conversation.id,
                    event_type="follow_up_sent",
                    details={
                        "conversation_id": str(conversation.id),
                        "stage_minutes": int(stage_minutes),
                        "reply_message_id": reply_message_id,
                    },
                )
            )
            db.commit()

        _finish_job(job_id, "completed")
        return {
            "task": "send_follow_up",
            "status": "completed",
            "job_id": str(job_id),
            "conversation_id": conversation_id,
            "stage_minutes": int(stage_minutes),
        }
    except Exception as exc:  # noqa: BLE001
        error_text = _safe_error_text(exc)
        _finish_job(job_id, "failed", error_text)
        return {
            "task": "send_follow_up",
            "status": "failed",
            "job_id": str(job_id),
            "error": error_text,
        }


@celery_app.task(name="recalc_metrics")
def recalc_metrics(payload: dict) -> dict:
    job_id = _create_job("recalc_metrics", payload)
    try:
        with SessionLocal() as db:
            metrics = {
                "contacts": db.scalar(select(func.count()).select_from(Contact)) or 0,
                "conversations": db.scalar(select(func.count()).select_from(Conversation)) or 0,
                "messages": db.scalar(select(func.count()).select_from(Message)) or 0,
                "posts": db.scalar(select(func.count()).select_from(Post)) or 0,
                "pending_jobs": (
                    db.scalar(
                        select(func.count()).select_from(Job).where(Job.status.in_(("pending", "processing")))
                    )
                    or 0
                ),
            }
            db.add(
                AuditLog(
                    entity_type="system",
                    event_type="metrics_recalculated",
                    details={"metrics": metrics},
                )
            )
            db.commit()

        _finish_job(job_id, "completed")
        return {
            "task": "recalc_metrics",
            "status": "completed",
            "job_id": str(job_id),
            "metrics": metrics,
        }
    except Exception as exc:  # noqa: BLE001
        error_text = _safe_error_text(exc)
        _finish_job(job_id, "failed", error_text)
        return {
            "task": "recalc_metrics",
            "status": "failed",
            "job_id": str(job_id),
            "error": error_text,
        }
