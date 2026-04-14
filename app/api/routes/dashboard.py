from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.contact import Contact
from app.models.contact_identity import ContactIdentity
from app.models.conversation import Conversation
from app.models.message import Message
from app.services.whatsapp_service import WhatsAppService


router = APIRouter(tags=["dashboard"])


class DashboardSendPayload(BaseModel):
    conversation_id: UUID
    text: str


def _normalize_whatsapp_destination(value: str | None) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    digits = "".join(ch for ch in raw if ch.isdigit())
    return digits or raw


def _resolve_contact_whatsapp_destination(db: Session, contact_id: UUID) -> str | None:
    contact = db.get(Contact, contact_id)
    if contact is None:
        return None

    direct_phone = _normalize_whatsapp_destination(contact.phone)
    if direct_phone:
        return direct_phone

    identities = (
        db.query(ContactIdentity)
        .filter(
            ContactIdentity.contact_id == contact_id,
            ContactIdentity.platform == "whatsapp",
        )
        .order_by(ContactIdentity.is_primary.desc(), ContactIdentity.created_at.desc())
        .all()
    )
    for identity in identities:
        normalized = _normalize_whatsapp_destination(identity.platform_user_id)
        if normalized:
            return normalized
    return None


def _message_preview(message: Message | None) -> str:
    if message is None:
        return "Sem mensagens"
    body = str(message.text_content or "").strip()
    if body:
        return body[:120]
    media = str(message.media_url or "").strip()
    if media:
        return f"[{message.message_type}] {media[:80]}"
    return f"[{message.message_type}]"


def _serialize_message(message: Message) -> dict:
    return {
        "id": str(message.id),
        "conversation_id": str(message.conversation_id),
        "platform": message.platform,
        "direction": message.direction,
        "message_type": message.message_type,
        "text_content": message.text_content,
        "media_url": message.media_url,
        "external_message_id": message.external_message_id,
        "ai_generated": message.ai_generated,
        "created_at": message.created_at.isoformat() if message.created_at else None,
    }


def _conversation_sort_key(conversation: Conversation) -> datetime:
    return (
        conversation.last_message_at
        or conversation.updated_at
        or conversation.created_at
        or datetime.fromtimestamp(0, tz=timezone.utc)
    )


@router.get("/dashboard/op/state")
def dashboard_op_state(
    conversation_id: UUID | None = Query(default=None),
    conversation_limit: int = Query(default=60, ge=1, le=200),
    message_limit: int = Query(default=120, ge=1, le=500),
    db: Session = Depends(get_db),
) -> dict:
    leads_total = db.query(Contact.id).count()
    open_conversations_total = db.query(Conversation.id).filter(Conversation.status == "open").count()
    inbound_total = db.query(Message.id).filter(Message.direction == "inbound").count()
    outbound_total = db.query(Message.id).filter(Message.direction == "outbound").count()

    conversations = (
        db.query(Conversation)
        .order_by(
            func.coalesce(
                Conversation.last_message_at,
                Conversation.updated_at,
                Conversation.created_at,
            ).desc()
        )
        .limit(conversation_limit)
        .all()
    )

    conversation_items: list[dict] = []
    for conversation in conversations:
        contact = db.get(Contact, conversation.contact_id)
        last_message = (
            db.query(Message)
            .filter(Message.conversation_id == conversation.id)
            .order_by(Message.created_at.desc())
            .first()
        )
        conversation_items.append(
            {
                "id": str(conversation.id),
                "platform": conversation.platform,
                "status": conversation.status,
                "last_activity_at": _conversation_sort_key(conversation).isoformat(),
                "contact": {
                    "id": str(contact.id) if contact else None,
                    "name": (contact.name if contact else None),
                    "phone": (contact.phone if contact else None),
                    "customer_id": (contact.customer_id if contact else None),
                },
                "last_message_preview": _message_preview(last_message),
                "last_message_direction": (last_message.direction if last_message else None),
                "last_message_created_at": (
                    last_message.created_at.isoformat() if last_message and last_message.created_at else None
                ),
            }
        )

    available_ids = {item["id"] for item in conversation_items}
    selected_conversation_id: str | None = str(conversation_id) if conversation_id else None
    if not selected_conversation_id or selected_conversation_id not in available_ids:
        selected_conversation_id = conversation_items[0]["id"] if conversation_items else None

    selected_messages: list[dict] = []
    selected_meta: dict = {"conversation_id": selected_conversation_id, "platform": None, "contact_name": None}
    if selected_conversation_id:
        selected_conversation = db.get(Conversation, UUID(selected_conversation_id))
        if selected_conversation is not None:
            selected_contact = db.get(Contact, selected_conversation.contact_id)
            selected_meta = {
                "conversation_id": selected_conversation_id,
                "platform": selected_conversation.platform,
                "contact_name": (selected_contact.name if selected_contact else None),
                "contact_phone": (selected_contact.phone if selected_contact else None),
                "whatsapp_destination": _resolve_contact_whatsapp_destination(
                    db=db,
                    contact_id=selected_conversation.contact_id,
                ),
            }
            rows = (
                db.query(Message)
                .filter(Message.conversation_id == selected_conversation.id)
                .order_by(Message.created_at.desc())
                .limit(message_limit)
                .all()
            )
            selected_messages = [_serialize_message(message) for message in reversed(rows)]

    return {
        "kpis": {
            "leads_total": leads_total,
            "open_conversations_total": open_conversations_total,
            "inbound_total": inbound_total,
            "outbound_total": outbound_total,
        },
        "selected": selected_meta,
        "conversations": conversation_items,
        "messages": selected_messages,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/dashboard/op/send")
def dashboard_op_send_message(
    payload: DashboardSendPayload,
    db: Session = Depends(get_db),
) -> dict:
    clean_text = str(payload.text or "").strip()
    if not clean_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mensagem vazia",
        )

    conversation = db.get(Conversation, payload.conversation_id)
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversa nao encontrada",
        )

    contact = db.get(Contact, conversation.contact_id)
    if contact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contato da conversa nao encontrado",
        )

    now_utc = datetime.now(timezone.utc)
    message = Message(
        conversation_id=conversation.id,
        platform=conversation.platform,
        direction="outbound",
        message_type="text",
        text_content=clean_text,
        raw_payload={"source": "dashboard_operator"},
        ai_generated=False,
    )
    db.add(message)
    conversation.last_message_at = now_utc
    db.flush()

    dispatch_status = "stored_only"
    dispatch_result: dict = {}
    destination = None

    if conversation.platform == "whatsapp":
        destination = _resolve_contact_whatsapp_destination(db=db, contact_id=contact.id)
        if destination:
            dispatch_result = WhatsAppService().send_text_message({"to": destination, "text": clean_text})
            dispatch_status = str(dispatch_result.get("status") or "unknown")
            external_id = str(dispatch_result.get("message_id") or "").strip()
            if external_id:
                message.external_message_id = external_id
        else:
            dispatch_status = "missing_contact_phone"

    message.raw_payload = {
        "source": "dashboard_operator",
        "dispatch": {
            "status": dispatch_status,
            "to": destination,
            "result": dispatch_result,
        },
    }

    db.commit()
    db.refresh(message)

    return {
        "status": "ok",
        "dispatch_status": dispatch_status,
        "message": _serialize_message(message),
    }


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard_page() -> str:
    return """<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Central OP - bot-multiredes</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&display=swap');
    :root{
      --bg:#f6f7f9;
      --ink:#17151f;
      --muted:#666173;
      --line:#dedbe6;
      --card:#ffffff;
      --brand:#0f5f4f;
      --brand-soft:#d9f4ed;
      --inbound:#fff1bf;
      --outbound:#d7f4ea;
      --danger:#8f1d2a;
      --danger-soft:#ffe4e8;
    }
    *{box-sizing:border-box}
    body{
      margin:0;
      color:var(--ink);
      background:
        radial-gradient(1000px 420px at -120px -120px, #d0efe6 0%, transparent 65%),
        radial-gradient(900px 360px at 120% 0%, #fce5b9 0%, transparent 62%),
        var(--bg);
      font-family:"Space Grotesk","Trebuchet MS",sans-serif;
    }
    .wrap{max-width:1320px;margin:0 auto;padding:16px 12px 18px;display:grid;gap:12px}
    .card{background:var(--card);border:1px solid var(--line);border-radius:14px;box-shadow:0 6px 18px rgba(18,16,27,.05)}
    .header{padding:14px 16px;display:flex;justify-content:space-between;gap:12px;align-items:flex-start}
    .title{margin:0;font-size:26px;line-height:1}
    .sub{margin-top:6px;font-size:13px;color:var(--muted)}
    .meta{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
    .chip{padding:6px 10px;border-radius:999px;background:var(--brand-soft);color:var(--brand);font-weight:700;font-size:12px}
    button{
      border:1px solid #164137;
      background:linear-gradient(180deg,#1f7a66,#0f5f4f);
      color:#fff;padding:9px 12px;border-radius:10px;cursor:pointer;font-weight:700
    }
    button:disabled{opacity:.6;cursor:not-allowed}
    .kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;padding:0 12px 12px}
    .kpi{padding:12px;border:1px solid var(--line);border-radius:12px;background:#fff}
    .kpi small{display:block;color:var(--muted);font-size:12px}
    .kpi strong{font-size:25px}
    .layout{display:grid;grid-template-columns:360px 1fr;gap:10px;padding:0 12px 12px}
    .pane{border:1px solid var(--line);border-radius:12px;background:#fff;display:grid}
    .pane-head{padding:10px 12px;border-bottom:1px solid var(--line);font-size:13px;color:var(--muted);font-weight:700}
    .convos{max-height:62vh;overflow:auto;padding:8px;display:grid;gap:6px}
    .conv{
      border:1px solid var(--line);border-radius:10px;background:#fff;padding:10px;cursor:pointer;display:grid;gap:4px
    }
    .conv.active{border-color:#116956;background:#f1fbf8}
    .conv .top{display:flex;justify-content:space-between;gap:8px}
    .conv .name{font-weight:700}
    .conv .meta{font-size:12px;color:var(--muted)}
    .conv .preview{font-size:12px;color:#2a2735;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    .chat{display:grid;grid-template-rows:auto 1fr auto;min-height:62vh}
    .chat-head{padding:10px 12px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;gap:10px;align-items:center}
    .chat-title{font-weight:700}
    .msgs{padding:12px;overflow:auto;display:grid;gap:8px;background:#fcfbff}
    .msg{max-width:82%;padding:10px 12px;border-radius:12px;border:1px solid var(--line);font-size:14px;line-height:1.35}
    .msg .meta{display:block;margin-top:6px;color:var(--muted);font-size:11px}
    .msg.inbound{justify-self:start;background:var(--inbound)}
    .msg.outbound{justify-self:end;background:var(--outbound)}
    .empty{color:var(--muted);font-size:13px;padding:8px 0}
    .composer{border-top:1px solid var(--line);padding:10px;display:grid;gap:8px}
    textarea{
      width:100%;resize:vertical;min-height:70px;max-height:220px;border:1px solid var(--line);
      border-radius:10px;padding:10px;font-family:inherit;font-size:14px
    }
    .composer-actions{display:flex;justify-content:space-between;align-items:center;gap:8px}
    .hint{font-size:12px;color:var(--muted)}
    .error{display:none;margin:0 12px 12px;padding:10px 12px;border:1px solid #f6a2af;border-radius:10px;background:var(--danger-soft);color:var(--danger)}
    @media (max-width:1080px){
      .kpis{grid-template-columns:repeat(2,minmax(0,1fr))}
      .layout{grid-template-columns:1fr}
      .convos{max-height:34vh}
      .chat{min-height:56vh}
    }
  </style>
</head>
<body>
  <main class="wrap">
    <section class="card header">
      <div>
        <h1 class="title">Central OP de Mensagens</h1>
        <div class="sub">Entrada e saida operacional de conversas sem depender do app do WhatsApp.</div>
      </div>
      <div class="meta">
        <span class="chip" id="refresh-chip">Atualizando...</span>
        <button id="btn-refresh">Atualizar agora</button>
      </div>
    </section>

    <section class="kpis">
      <article class="kpi"><small>Leads</small><strong id="kpi-leads">-</strong></article>
      <article class="kpi"><small>Conversas abertas</small><strong id="kpi-open">-</strong></article>
      <article class="kpi"><small>Mensagens recebidas</small><strong id="kpi-inbound">-</strong></article>
      <article class="kpi"><small>Mensagens enviadas</small><strong id="kpi-outbound">-</strong></article>
    </section>

    <section class="layout">
      <article class="pane">
        <header class="pane-head">Conversas</header>
        <div id="conversation-list" class="convos"></div>
      </article>

      <article class="pane chat">
        <header class="chat-head">
          <div>
            <div class="chat-title" id="chat-title">Sem conversa selecionada</div>
            <div class="hint" id="chat-subtitle">Selecione uma conversa para operar.</div>
          </div>
          <div class="chip" id="dispatch-chip">dispatch: -</div>
        </header>
        <div id="messages-list" class="msgs"></div>
        <div class="composer">
          <textarea id="outbound-text" placeholder="Digite a resposta para o cliente..."></textarea>
          <div class="composer-actions">
            <div class="hint">As mensagens enviadas aqui ficam registradas no historico da conversa.</div>
            <button id="btn-send">Enviar mensagem</button>
          </div>
        </div>
      </article>
    </section>
    <div id="error-box" class="error"></div>
  </main>

  <script>
    const byId = (id) => document.getElementById(id);
    const esc = (value) => {
      const text = String(value ?? "");
      return text
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
    };
    const short = (value) => {
      const t = String(value ?? "").trim();
      return t ? t : "-";
    };

    let selectedConversationId = null;
    let isSending = false;

    function setError(message) {
      const box = byId("error-box");
      if (!message) {
        box.style.display = "none";
        box.textContent = "";
        return;
      }
      box.textContent = message;
      box.style.display = "block";
    }

    function setSending(state) {
      isSending = state;
      byId("btn-send").disabled = state;
      byId("btn-send").textContent = state ? "Enviando..." : "Enviar mensagem";
    }

    function formatWhen(iso) {
      if (!iso) return "-";
      try {
        return new Date(iso).toLocaleString("pt-BR");
      } catch (_) {
        return iso;
      }
    }

    function renderConversations(items) {
      const root = byId("conversation-list");
      root.innerHTML = "";
      if (!items || items.length === 0) {
        root.innerHTML = "<div class='empty'>Sem conversas ainda.</div>";
        return;
      }

      for (const item of items) {
        const contactName = short(item?.contact?.name || item?.contact?.phone || item?.contact?.customer_id);
        const isActive = item.id === selectedConversationId;
        const row = document.createElement("button");
        row.type = "button";
        row.className = "conv" + (isActive ? " active" : "");
        row.onclick = () => {
          selectedConversationId = item.id;
          refreshState();
        };
        row.innerHTML = `
          <div class="top">
            <div class="name">${esc(contactName)}</div>
            <div class="meta">${esc(item.platform || "-")}</div>
          </div>
          <div class="preview">${esc(item.last_message_preview || "Sem mensagens")}</div>
          <div class="meta">${esc(formatWhen(item.last_message_created_at || item.last_activity_at))}</div>
        `;
        root.appendChild(row);
      }
    }

    function renderMessages(messages) {
      const root = byId("messages-list");
      root.innerHTML = "";
      if (!messages || messages.length === 0) {
        root.innerHTML = "<div class='empty'>Sem mensagens nesta conversa.</div>";
        return;
      }

      for (const message of messages) {
        const bubble = document.createElement("article");
        bubble.className = "msg " + (message.direction === "outbound" ? "outbound" : "inbound");
        const body = short(message.text_content || message.media_url || "[" + short(message.message_type) + "]");
        bubble.innerHTML = `
          <div>${esc(body)}</div>
          <span class="meta">${esc(message.direction)} | ${esc(formatWhen(message.created_at))}</span>
        `;
        root.appendChild(bubble);
      }
      root.scrollTop = root.scrollHeight;
    }

    function updateSelectedHeader(selected) {
      const name = short(selected?.contact_name || "Sem conversa selecionada");
      const platform = short(selected?.platform);
      const phone = short(selected?.whatsapp_destination || selected?.contact_phone || "-");
      byId("chat-title").textContent = name;
      byId("chat-subtitle").textContent = `plataforma=${platform} | destino=${phone}`;
      byId("dispatch-chip").textContent = selected?.whatsapp_destination ? "dispatch: whatsapp pronto" : "dispatch: sem destino";
    }

    async function refreshState() {
      byId("refresh-chip").textContent = "Atualizando...";
      setError("");
      try {
        const query = selectedConversationId ? `?conversation_id=${encodeURIComponent(selectedConversationId)}` : "";
        const response = await fetch(`/dashboard/op/state${query}`, { cache: "no-store" });
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const data = await response.json();
        selectedConversationId = data?.selected?.conversation_id || null;

        byId("kpi-leads").textContent = String(data?.kpis?.leads_total ?? 0);
        byId("kpi-open").textContent = String(data?.kpis?.open_conversations_total ?? 0);
        byId("kpi-inbound").textContent = String(data?.kpis?.inbound_total ?? 0);
        byId("kpi-outbound").textContent = String(data?.kpis?.outbound_total ?? 0);

        renderConversations(data?.conversations || []);
        renderMessages(data?.messages || []);
        updateSelectedHeader(data?.selected || {});
        byId("refresh-chip").textContent = "Atualizado " + formatWhen(data?.generated_at);
      } catch (error) {
        byId("refresh-chip").textContent = "Falha na atualizacao";
        setError("Erro ao carregar central operacional: " + error);
      }
    }

    async function sendCurrentMessage() {
      if (isSending) return;
      if (!selectedConversationId) {
        setError("Selecione uma conversa antes de enviar.");
        return;
      }

      const text = byId("outbound-text").value.trim();
      if (!text) {
        setError("Digite uma mensagem antes de enviar.");
        return;
      }

      setError("");
      setSending(true);
      try {
        const response = await fetch("/dashboard/op/send", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            conversation_id: selectedConversationId,
            text,
          }),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(data?.detail || `HTTP ${response.status}`);
        }
        byId("outbound-text").value = "";
        byId("dispatch-chip").textContent = "dispatch: " + short(data?.dispatch_status);
        await refreshState();
      } catch (error) {
        setError("Falha ao enviar mensagem: " + error);
      } finally {
        setSending(false);
      }
    }

    byId("btn-refresh").addEventListener("click", refreshState);
    byId("btn-send").addEventListener("click", sendCurrentMessage);
    byId("outbound-text").addEventListener("keydown", (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
        event.preventDefault();
        sendCurrentMessage();
      }
    });

    refreshState();
    setInterval(refreshState, 4500);
  </script>
</body>
</html>
"""
