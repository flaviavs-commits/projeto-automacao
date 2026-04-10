from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.models.audit_log import AuditLog
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.job import Job
from app.models.message import Message
from app.models.post import Post
from app.services.instagram_publish_service import InstagramPublishService
from app.services.memory_service import MemoryService
from app.services.routing_service import RoutingService
from app.services.tiktok_service import TikTokService
from app.services.transcription_service import TranscriptionService
from app.services.whatsapp_service import WhatsAppService
from app.services.youtube_service import YouTubeService
from app.workers.celery_app import celery_app


AUDIO_MESSAGE_TYPES = {"audio", "voice", "ptt"}


def _legacy_qa_result(task_name: str, payload: dict | None = None) -> dict:
    return {
        "task": task_name,
        "status": "queued_stub",
        "payload": payload or {},
    }


def _safe_error_text(exc: Exception) -> str:
    return f"{exc.__class__.__name__}: {str(exc)}"[:2000]


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


def _render_auto_reply(source_text: str) -> str:
    compact = " ".join(source_text.strip().split())
    if not compact:
        return "Recebemos sua mensagem. Nosso time vai te responder em breve."
    snippet = compact[:140]
    if len(compact) > 140:
        snippet += "..."
    return (
        "Recebemos sua mensagem: "
        f"\"{snippet}\". "
        "Nossa equipe vai te responder em breve."
    )


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
            reply_result = generate_reply(
                {
                    "conversation_id": str(conversation.id),
                    "platform": message.platform,
                    "source_message_id": str(message.id),
                    "source_text": inbound_text,
                    "phone_number_id": payload.get("phone_number_id"),
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
        reply_text = _render_auto_reply(source_text)

        platform = str(payload.get("platform") or "whatsapp")
        source_message_id = str(payload.get("source_message_id") or "").strip() or None
        phone_number_id = str(payload.get("phone_number_id") or "").strip() or None
        now_utc = datetime.now(timezone.utc)
        dispatch_result: dict | None = None

        with SessionLocal() as db:
            conversation = db.get(Conversation, conversation_id)
            if conversation is None:
                raise ValueError(f"conversation not found: {conversation_id}")
            contact = db.get(Contact, conversation.contact_id)

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

            db.add(
                AuditLog(
                    entity_type="conversation",
                    entity_id=conversation.id,
                    event_type="auto_reply_generated",
                    details={
                        "source_message_id": source_message_id,
                        "reply_message_preview": reply_text[:120],
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
