from datetime import datetime, timedelta, timezone
import unicodedata
from uuid import UUID

from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.models.audit_log import AuditLog
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.job import Job
from app.models.message import Message
from app.models.post import Post
from app.services.contact_memory_service import ContactMemoryService
from app.services.instagram_service import InstagramService
from app.services.instagram_publish_service import InstagramPublishService
from app.services.llm_reply_service import LLMReplyService
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
            memory_result = ContactMemoryService().save_from_inbound_text(
                db=db,
                contact_id=conversation.contact_id,
                source_message_id=message.id,
                inbound_text=inbound_text,
            )
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

            llm_result = LLMReplyService().generate_reply(
                user_text=source_text,
                context_messages=context.get("memory_items") or [],
                key_memories=key_memories,
            )
            llm_status = str((llm_result or {}).get("status") or "")
            llm_model = str((llm_result or {}).get("model") or "")
            reply_text = str((llm_result or {}).get("reply_text") or "").strip()
            if llm_status not in {"completed", "blocked_out_of_scope"} or not reply_text:
                raise RuntimeError(f"llm_reply_generation_failed: status={llm_status}")
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
                    },
                )
            )
            db.commit()
            db.refresh(outbound)

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
