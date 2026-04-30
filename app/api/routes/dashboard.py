from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from pathlib import Path
import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.conversation import Conversation
from app.services.conversation_chatbot_control_service import ConversationChatbotControlService
from app.services.dashboard_op_service import DashboardOpService
from app.services.human_queue_service import HumanQueueService
from app.services.manual_message_service import ManualMessageService
from app.services.schedule_service import ScheduleService


router = APIRouter(tags=["dashboard"])
security = HTTPBasic(auto_error=False)


class ManualSendPayload(BaseModel):
    channel: str = Field(min_length=1, max_length=30)
    text: str = Field(min_length=1, max_length=5000)
    contact_identity_id: UUID | None = None


class ToggleChatbotPayload(BaseModel):
    enabled: bool


class DashboardSendPayload(BaseModel):
    conversation_id: UUID
    text: str


class AppointmentCreatePayload(BaseModel):
    contact_id: UUID | None = None
    conversation_id: UUID | None = None
    customer_name: str | None = None
    customer_phone: str | None = None
    start_time: datetime
    end_time: datetime
    status: str = "reserved"
    notes: str | None = None


class AppointmentPatchPayload(BaseModel):
    status: str | None = None
    notes: str | None = None


def _authorize_dashboard(
    credentials: HTTPBasicCredentials | None = Depends(security),
) -> str | None:
    if not settings.op_dashboard_auth_enabled:
        return None

    expected_user = str(settings.op_dashboard_username or "").strip()
    expected_hash = str(settings.op_dashboard_password_hash or "").strip().lower()
    if not expected_user or not expected_hash:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Painel operacional indisponivel.",
        )
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticacao obrigatoria.",
            headers={"WWW-Authenticate": "Basic"},
        )
    provided_user = str(credentials.username or "")
    provided_hash = sha256(str(credentials.password or "").encode("utf-8")).hexdigest().lower()
    if not (secrets.compare_digest(provided_user, expected_user) and secrets.compare_digest(provided_hash, expected_hash)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais invalidas.",
            headers={"WWW-Authenticate": "Basic"},
        )
    return provided_user


@router.get("/dashboard/op", response_class=HTMLResponse)
def dashboard_op_page(_: str | None = Depends(_authorize_dashboard)) -> str:
    template_path = Path(__file__).resolve().parents[2] / "templates" / "dashboard_op.html"
    return template_path.read_text(encoding="utf-8")


@router.get("/dashboard")
def dashboard_page_redirect(_: str | None = Depends(_authorize_dashboard)) -> HTMLResponse:
    return HTMLResponse(content=dashboard_op_page(None), status_code=200)


@router.get("/dashboard/op/conversations")
def list_conversations(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    channel: str | None = Query(default=None),
    hot_only: bool = Query(default=False),
    human_pending: bool = Query(default=False),
    search: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    _: str | None = Depends(_authorize_dashboard),
    db: Session = Depends(get_db),
) -> dict:
    return DashboardOpService().list_conversations(
        db=db,
        limit=limit,
        offset=offset,
        channel=channel,
        hot_only=hot_only,
        human_pending=human_pending,
        search=search,
        status=status_filter,
    )


@router.get("/dashboard/op/conversations/{conversation_id}")
def conversation_detail(
    conversation_id: UUID,
    _: str | None = Depends(_authorize_dashboard),
    db: Session = Depends(get_db),
) -> dict:
    payload = DashboardOpService().get_conversation_detail(db=db, conversation_id=conversation_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Essa conversa nao existe.")
    return payload


@router.get("/dashboard/op/conversations/{conversation_id}/messages")
def conversation_messages(
    conversation_id: UUID,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _: str | None = Depends(_authorize_dashboard),
    db: Session = Depends(get_db),
) -> dict:
    payload = DashboardOpService().list_messages(db=db, conversation_id=conversation_id, limit=limit, offset=offset)
    if payload is None:
        raise HTTPException(status_code=404, detail="Essa conversa nao existe.")
    return payload


@router.post("/dashboard/op/conversations/{conversation_id}/send")
def manual_send_message(
    conversation_id: UUID,
    payload: ManualSendPayload,
    actor: str | None = Depends(_authorize_dashboard),
    db: Session = Depends(get_db),
) -> dict:
    result = ManualMessageService().send(
        db=db,
        conversation_id=conversation_id,
        channel=payload.channel,
        text=payload.text,
        contact_identity_id=payload.contact_identity_id,
        actor=actor,
    )
    if result.get("status") == "sent":
        return {"status": "sent", "message": "Mensagem enviada."}
    code = int(result.get("status_code") or 400)
    raise HTTPException(status_code=code, detail=result.get("detail") or "Nao foi possivel enviar por este canal agora.")


@router.get("/dashboard/op/human-queue")
def human_queue(
    for_modal: bool = Query(default=False),
    _: str | None = Depends(_authorize_dashboard),
    db: Session = Depends(get_db),
) -> dict:
    items = HumanQueueService().list_active_queue(db=db, for_modal=for_modal)
    return {"items": items}


@router.post("/dashboard/op/conversations/{conversation_id}/human/accept")
def human_accept(
    conversation_id: UUID,
    actor: str | None = Depends(_authorize_dashboard),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return HumanQueueService().accept(db=db, conversation_id=conversation_id, actor=actor)
    except ValueError:
        raise HTTPException(status_code=404, detail="Essa conversa nao existe.")


@router.post("/dashboard/op/conversations/{conversation_id}/human/ignore")
def human_ignore(
    conversation_id: UUID,
    actor: str | None = Depends(_authorize_dashboard),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return HumanQueueService().ignore(db=db, conversation_id=conversation_id, actor=actor)
    except ValueError:
        raise HTTPException(status_code=404, detail="Essa conversa nao existe.")


@router.post("/dashboard/op/conversations/{conversation_id}/chatbot/toggle")
def chatbot_toggle(
    conversation_id: UUID,
    payload: ToggleChatbotPayload,
    actor: str | None = Depends(_authorize_dashboard),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return ConversationChatbotControlService().set_enabled(
            db=db,
            conversation_id=conversation_id,
            enabled=payload.enabled,
            actor=actor,
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="Essa conversa nao existe.")


@router.get("/dashboard/op/contacts")
def contacts_list(
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    search: str | None = Query(default=None),
    _: str | None = Depends(_authorize_dashboard),
    db: Session = Depends(get_db),
) -> dict:
    if search:
        return DashboardOpService().search_contacts(db=db, query_text=search, limit=limit, offset=offset)
    return DashboardOpService().list_contacts(db=db, limit=limit, offset=offset)


@router.get("/dashboard/op/contacts/{contact_id}")
def contact_detail(
    contact_id: UUID,
    _: str | None = Depends(_authorize_dashboard),
    db: Session = Depends(get_db),
) -> dict:
    payload = DashboardOpService().get_contact_detail(db=db, contact_id=contact_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Nao encontramos esse cliente.")
    return payload


@router.post("/dashboard/op/contacts/{contact_id}/start-conversation")
def contact_start_conversation(
    contact_id: UUID,
    channel: str = Query(default="whatsapp"),
    _: str | None = Depends(_authorize_dashboard),
    db: Session = Depends(get_db),
) -> dict:
    payload = DashboardOpService().start_or_resume_conversation(
        db=db,
        contact_id=contact_id,
        channel=channel,
    )
    if payload is None:
        raise HTTPException(status_code=404, detail="Nao encontramos esse cliente.")
    return payload


@router.get("/dashboard/op/appointments")
def appointments_list(
    include_next: bool = Query(default=False),
    _: str | None = Depends(_authorize_dashboard),
    db: Session = Depends(get_db),
) -> dict:
    return ScheduleService().list_appointments(db=db, include_next=include_next)


@router.post("/dashboard/op/appointments")
def appointment_create(
    payload: AppointmentCreatePayload,
    _: str | None = Depends(_authorize_dashboard),
    db: Session = Depends(get_db),
) -> dict:
    return ScheduleService().create_appointment(
        db=db,
        contact_id=payload.contact_id,
        conversation_id=payload.conversation_id,
        customer_name=payload.customer_name,
        customer_phone=payload.customer_phone,
        start_time=payload.start_time,
        end_time=payload.end_time,
        status=payload.status,
        notes=payload.notes,
    )


@router.patch("/dashboard/op/appointments/{appointment_id}")
def appointment_patch(
    appointment_id: UUID,
    payload: AppointmentPatchPayload,
    _: str | None = Depends(_authorize_dashboard),
    db: Session = Depends(get_db),
) -> dict:
    updated = ScheduleService().update_appointment(
        db=db,
        appointment_id=appointment_id,
        status=payload.status,
        notes=payload.notes,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Agendamento nao encontrado.")
    return updated


@router.get("/dashboard/op/status")
def operational_status(
    _: str | None = Depends(_authorize_dashboard),
) -> dict:
    whatsapp_status = "conectado" if settings.whatsapp_dispatch_ready else "indisponivel"
    instagram_status = "disponivel" if settings.meta_runtime_enabled else "indisponivel"
    facebook_status = "indisponivel"
    tiktok_status = "disponivel" if settings.tiktok_runtime_enabled else "indisponivel"
    return {
        "channels": {
            "whatsapp": whatsapp_status,
            "instagram": instagram_status,
            "facebook": facebook_status,
            "tiktok": tiktok_status,
        },
        "message": "Status indisponivel no momento." if whatsapp_status == "indisponivel" else "",
    }


# Backward-compatible endpoints used by current dashboard scripts/tests
@router.get("/dashboard/op/state")
def dashboard_op_state_compat(
    conversation_id: UUID | None = Query(default=None),
    conversation_limit: int = Query(default=60, ge=1, le=200),
    message_limit: int = Query(default=120, ge=1, le=500),
    _: str | None = Depends(_authorize_dashboard),
    db: Session = Depends(get_db),
) -> dict:
    conversation_payload = DashboardOpService().list_conversations(
        db=db,
        limit=conversation_limit,
        offset=0,
    )
    items = conversation_payload.get("items", [])
    selected_id = str(conversation_id) if conversation_id else (items[0]["id"] if items else None)
    selected_messages = {"items": []}
    selected_meta = {"conversation_id": selected_id}
    if selected_id:
        detail = DashboardOpService().get_conversation_detail(db=db, conversation_id=UUID(selected_id))
        selected_messages = DashboardOpService().list_messages(
            db=db,
            conversation_id=UUID(selected_id),
            limit=message_limit,
            offset=0,
        ) or {"items": []}
        if detail:
            selected_meta = {
                "conversation_id": selected_id,
                "platform": detail.get("channel"),
                "contact_name": (detail.get("contact") or {}).get("name"),
                "contact_phone": (detail.get("contact") or {}).get("phone"),
                "whatsapp_destination": (detail.get("contact") or {}).get("phone"),
            }

    human_items = HumanQueueService().list_active_queue(db=db, for_modal=False, limit=200)
    inbound_total = db.query(Conversation.id).count()
    outbound_total = db.query(Conversation.id).count()
    return {
        "kpis": {
            "leads_total": db.query(Conversation.contact_id).distinct().count(),
            "open_conversations_total": db.query(Conversation.id).filter(Conversation.status == "open").count(),
            "inbound_total": inbound_total,
            "outbound_total": outbound_total,
            "human_pending_total": len(human_items),
        },
        "selected": selected_meta,
        "conversations": items,
        "human_pending": human_items,
        "messages": selected_messages.get("items", []),
        "generated_at": datetime.now().isoformat(),
    }


@router.post("/dashboard/op/send")
def dashboard_op_send_compat(
    payload: DashboardSendPayload,
    actor: str | None = Depends(_authorize_dashboard),
    db: Session = Depends(get_db),
) -> dict:
    conversation = db.get(Conversation, payload.conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversa nao encontrada")
    result = ManualMessageService().send(
        db=db,
        conversation_id=conversation.id,
        channel=conversation.platform,
        text=payload.text,
        actor=actor,
    )
    if result.get("status") != "sent":
        raise HTTPException(status_code=400, detail=result.get("detail") or "Falha ao enviar.")
    return {"status": "ok", "dispatch_status": "sent"}

