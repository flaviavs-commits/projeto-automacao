import base64
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import unittest
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.models.appointment import Appointment
from app.models.audit_log import AuditLog
from app.models.contact import Contact
from app.models.contact_identity import ContactIdentity
from app.models.contact_memory import ContactMemory
from app.models.conversation import Conversation
from app.models.message import Message
from app.workers import tasks


def _basic_auth_header(username: str, password: str) -> dict[str, str]:
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {token}"}


class TestDashboardOPCentralTDD(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self.db = self.SessionLocal()

        self.original_auth_enabled = getattr(settings, "op_dashboard_auth_enabled", False)
        self.original_auth_user = getattr(settings, "op_dashboard_username", "")
        self.original_auth_hash = getattr(settings, "op_dashboard_password_hash", "")
        self.original_llm_enabled = settings.llm_enabled
        self.original_evolution_api_base_url = settings.evolution_api_base_url
        self.original_evolution_api_key = settings.evolution_api_key
        self.original_evolution_instance_name = settings.evolution_instance_name
        self.original_tasks_session_local = tasks.SessionLocal
        settings.evolution_api_base_url = "http://localhost:8080"
        settings.evolution_api_key = "test-key"
        settings.evolution_instance_name = "test-instance"
        tasks.SessionLocal = self.SessionLocal

        def _override_get_db():
            db = self.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = _override_get_db
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()
        settings.op_dashboard_auth_enabled = self.original_auth_enabled
        settings.op_dashboard_username = self.original_auth_user
        settings.op_dashboard_password_hash = self.original_auth_hash
        settings.llm_enabled = self.original_llm_enabled
        settings.evolution_api_base_url = self.original_evolution_api_base_url
        settings.evolution_api_key = self.original_evolution_api_key
        settings.evolution_instance_name = self.original_evolution_instance_name
        tasks.SessionLocal = self.original_tasks_session_local

    def _seed_contact(self, *, name: str = "Cliente", phone: str = "5511999999999") -> Contact:
        contact = Contact(name=name, phone=phone)
        self.db.add(contact)
        self.db.flush()
        return contact

    def _seed_conversation(
        self,
        *,
        contact: Contact,
        platform: str = "whatsapp",
        status: str = "open",
        needs_human: bool = False,
        human_reason: str | None = None,
    ) -> Conversation:
        conversation = Conversation(
            contact_id=contact.id,
            platform=platform,
            status=status,
            needs_human=needs_human,
            human_reason=human_reason,
            human_requested_at=datetime.now(timezone.utc) if needs_human else None,
        )
        self.db.add(conversation)
        self.db.flush()
        return conversation

    def _seed_message(
        self,
        *,
        conversation: Conversation,
        direction: str,
        text: str,
        created_at: datetime | None = None,
    ) -> Message:
        message = Message(
            conversation_id=conversation.id,
            platform=conversation.platform,
            direction=direction,
            message_type="text",
            text_content=text,
            raw_payload={},
            ai_generated=(direction == "outbound"),
            created_at=created_at or datetime.now(timezone.utc),
        )
        self.db.add(message)
        self.db.flush()
        return message

    # 1
    def test_dashboard_protegido_quando_auth_ativa(self) -> None:
        settings.op_dashboard_auth_enabled = True
        settings.op_dashboard_username = "op"
        settings.op_dashboard_password_hash = "dummy"
        response = self.client.get("/dashboard/op")
        assert response.status_code in {401, 403}

    # 2
    def test_dashboard_nao_expoe_secrets_no_html(self) -> None:
        settings.op_dashboard_auth_enabled = False
        settings.whatsapp_gateway_api_key = "SECRET_GATEWAY"
        settings.evolution_api_key = "SECRET_EVOLUTION"
        response = self.client.get("/dashboard/op")
        assert response.status_code == 200
        body = response.text
        assert "SECRET_GATEWAY" not in body
        assert "SECRET_EVOLUTION" not in body
        assert "WHATSAPP_GATEWAY_API_KEY" not in body
        assert "BAILEYS_API_KEY" not in body

    # 3
    def test_lista_conversas_com_paginacao(self) -> None:
        settings.op_dashboard_auth_enabled = False
        contact = self._seed_contact()
        for _ in range(5):
            self._seed_conversation(contact=contact)
        self.db.commit()
        response = self.client.get("/dashboard/op/conversations?limit=2&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert len(data.get("items", [])) <= 2

    # 4
    def test_filtra_conversas_por_canal(self) -> None:
        settings.op_dashboard_auth_enabled = False
        c1 = self._seed_contact(name="A")
        c2 = self._seed_contact(name="B", phone="5511888888888")
        self._seed_conversation(contact=c1, platform="whatsapp")
        self._seed_conversation(contact=c2, platform="instagram")
        self.db.commit()
        response = self.client.get("/dashboard/op/conversations?channel=instagram")
        assert response.status_code == 200
        items = response.json().get("items", [])
        assert all(item.get("channel") == "instagram" for item in items)

    # 5
    def test_filtra_conversas_por_perfil_quente(self) -> None:
        settings.op_dashboard_auth_enabled = False
        contact = self._seed_contact()
        conversation = self._seed_conversation(contact=contact)
        self.db.add(
            ContactMemory(
                contact_id=contact.id,
                source_message_id=None,
                memory_key="interesse",
                memory_value="agendamento",
                status="active",
                importance=5,
                confidence=0.95,
            )
        )
        self.db.commit()
        response = self.client.get("/dashboard/op/conversations?hot_only=true")
        assert response.status_code == 200
        items = response.json().get("items", [])
        assert any(UUID(item["id"]) == conversation.id for item in items)

    # 6
    def test_filtra_conversas_por_humano_pendente(self) -> None:
        settings.op_dashboard_auth_enabled = False
        contact = self._seed_contact()
        conv = self._seed_conversation(contact=contact, needs_human=True, human_reason="agendamento")
        self.db.commit()
        response = self.client.get("/dashboard/op/conversations?human_pending=true")
        assert response.status_code == 200
        items = response.json().get("items", [])
        assert any(UUID(item["id"]) == conv.id for item in items)

    # 7
    def test_busca_conversa_por_nome(self) -> None:
        settings.op_dashboard_auth_enabled = False
        contact = self._seed_contact(name="Flavia Souza")
        conv = self._seed_conversation(contact=contact)
        self.db.commit()
        response = self.client.get("/dashboard/op/conversations?search=Flavia")
        assert response.status_code == 200
        items = response.json().get("items", [])
        assert any(UUID(item["id"]) == conv.id for item in items)

    # 8
    def test_busca_conversa_por_telefone(self) -> None:
        settings.op_dashboard_auth_enabled = False
        contact = self._seed_contact(phone="5521999999999")
        conv = self._seed_conversation(contact=contact)
        self.db.commit()
        response = self.client.get("/dashboard/op/conversations?search=5521999999999")
        assert response.status_code == 200
        items = response.json().get("items", [])
        assert any(UUID(item["id"]) == conv.id for item in items)

    # 9
    def test_abre_conversa_e_retorna_mensagens(self) -> None:
        settings.op_dashboard_auth_enabled = False
        contact = self._seed_contact()
        conv = self._seed_conversation(contact=contact)
        self._seed_message(conversation=conv, direction="inbound", text="oi")
        self.db.commit()
        response = self.client.get(f"/dashboard/op/conversations/{conv.id}/messages")
        assert response.status_code == 200
        assert len(response.json().get("items", [])) >= 1

    # 10
    def test_mensagens_retorna_canal_correto(self) -> None:
        settings.op_dashboard_auth_enabled = False
        contact = self._seed_contact()
        conv = self._seed_conversation(contact=contact, platform="instagram")
        self._seed_message(conversation=conv, direction="inbound", text="olá")
        self.db.commit()
        response = self.client.get(f"/dashboard/op/conversations/{conv.id}/messages")
        assert response.status_code == 200
        item = response.json()["items"][0]
        assert item["channel"] == "instagram"

    # 11
    def test_memorias_pilares_aparecem_no_payload_da_conversa(self) -> None:
        settings.op_dashboard_auth_enabled = False
        contact = self._seed_contact()
        conv = self._seed_conversation(contact=contact)
        self.db.add(
            ContactMemory(
                contact_id=contact.id,
                source_message_id=None,
                memory_key="pacote_interesse",
                memory_value="2h",
                status="active",
                importance=4,
                confidence=0.9,
            )
        )
        self.db.commit()
        response = self.client.get(f"/dashboard/op/conversations/{conv.id}")
        assert response.status_code == 200
        memories = response.json().get("pillar_memories", [])
        assert any(memory.get("key") == "pacote_interesse" for memory in memories)

    # 12
    def test_envio_manual_texto_vazio_retorna_erro(self) -> None:
        settings.op_dashboard_auth_enabled = False
        contact = self._seed_contact()
        conv = self._seed_conversation(contact=contact)
        self.db.commit()
        response = self.client.post(
            f"/dashboard/op/conversations/{conv.id}/send",
            json={"channel": "whatsapp", "text": "   "},
        )
        assert response.status_code == 400

    # 13
    def test_envio_manual_sem_identidade_valida_retorna_bloqueado(self) -> None:
        settings.op_dashboard_auth_enabled = False
        contact = self._seed_contact(phone="")
        conv = self._seed_conversation(contact=contact, platform="whatsapp")
        self.db.commit()
        response = self.client.post(
            f"/dashboard/op/conversations/{conv.id}/send",
            json={"channel": "whatsapp", "text": "teste"},
        )
        assert response.status_code in {400, 422}
        assert "canal" in response.text.lower() or "identidade" in response.text.lower()

    # 14
    def test_envio_manual_whatsapp_chama_service_correto_mockado(self) -> None:
        settings.op_dashboard_auth_enabled = False
        contact = self._seed_contact()
        conv = self._seed_conversation(contact=contact, platform="whatsapp")
        self.db.commit()
        with patch("app.services.whatsapp_service.WhatsAppService.send_text_message", return_value={"status": "completed"}):
            response = self.client.post(
                f"/dashboard/op/conversations/{conv.id}/send",
                json={"channel": "whatsapp", "text": "mensagem"},
            )
        assert response.status_code == 200

    # 15
    def test_envio_manual_persiste_mensagem_outbound_manual(self) -> None:
        settings.op_dashboard_auth_enabled = False
        contact = self._seed_contact()
        conv = self._seed_conversation(contact=contact, platform="whatsapp")
        self.db.commit()
        with patch("app.services.whatsapp_service.WhatsAppService.send_text_message", return_value={"status": "completed"}):
            response = self.client.post(
                f"/dashboard/op/conversations/{conv.id}/send",
                json={"channel": "whatsapp", "text": "manual"},
            )
        assert response.status_code == 200
        msg = (
            self.db.query(Message)
            .filter(Message.conversation_id == conv.id, Message.direction == "outbound")
            .order_by(Message.created_at.desc())
            .first()
        )
        assert msg is not None
        assert msg.text_content == "manual"

    # 16
    def test_envio_manual_cria_auditlog(self) -> None:
        settings.op_dashboard_auth_enabled = False
        contact = self._seed_contact()
        conv = self._seed_conversation(contact=contact, platform="whatsapp")
        self.db.commit()
        with patch("app.services.whatsapp_service.WhatsAppService.send_text_message", return_value={"status": "completed"}):
            self.client.post(
                f"/dashboard/op/conversations/{conv.id}/send",
                json={"channel": "whatsapp", "text": "manual"},
            )
        audit = (
            self.db.query(AuditLog)
            .filter(AuditLog.entity_type == "conversation", AuditLog.entity_id == conv.id, AuditLog.event_type == "manual_message_sent")
            .first()
        )
        assert audit is not None

    # 17
    def test_aceitar_humano_muda_status_para_human_accepted(self) -> None:
        settings.op_dashboard_auth_enabled = False
        contact = self._seed_contact()
        conv = self._seed_conversation(contact=contact, needs_human=True, human_reason="agendamento")
        self.db.commit()
        response = self.client.post(f"/dashboard/op/conversations/{conv.id}/human/accept")
        assert response.status_code == 200
        assert response.json().get("human_status") == "human_accepted"

    # 18
    def test_ignorar_humano_muda_status_para_human_ignored(self) -> None:
        settings.op_dashboard_auth_enabled = False
        contact = self._seed_contact()
        conv = self._seed_conversation(contact=contact, needs_human=True, human_reason="agendamento")
        self.db.commit()
        response = self.client.post(f"/dashboard/op/conversations/{conv.id}/human/ignore")
        assert response.status_code == 200
        assert response.json().get("human_status") == "human_ignored"

    # 19
    def test_conversa_aceita_continua_na_fila_humana_enquanto_open(self) -> None:
        settings.op_dashboard_auth_enabled = False
        contact = self._seed_contact()
        conv = self._seed_conversation(contact=contact, needs_human=True, human_reason="agendamento", status="open")
        self.db.commit()
        self.client.post(f"/dashboard/op/conversations/{conv.id}/human/accept")
        queue = self.client.get("/dashboard/op/human-queue")
        assert queue.status_code == 200
        ids = [item.get("conversation_id") for item in queue.json().get("items", [])]
        assert str(conv.id) in ids

    # 20
    def test_conversa_ignorada_continua_visivel_enquanto_open(self) -> None:
        settings.op_dashboard_auth_enabled = False
        contact = self._seed_contact()
        conv = self._seed_conversation(contact=contact, needs_human=True, human_reason="agendamento", status="open")
        self.db.commit()
        self.client.post(f"/dashboard/op/conversations/{conv.id}/human/ignore")
        queue = self.client.get("/dashboard/op/human-queue")
        assert queue.status_code == 200
        ids = [item.get("conversation_id") for item in queue.json().get("items", [])]
        assert str(conv.id) in ids

    # 21
    def test_modal_vermelho_recebe_solicitacao_human_pending(self) -> None:
        settings.op_dashboard_auth_enabled = False
        contact = self._seed_contact()
        conv = self._seed_conversation(contact=contact, needs_human=True, human_reason="agendamento")
        self._seed_message(conversation=conv, direction="inbound", text="quero atendente")
        self.db.commit()
        response = self.client.get("/dashboard/op/human-queue?for_modal=true")
        assert response.status_code == 200
        assert len(response.json().get("items", [])) >= 1

    # 22
    def test_modal_aceitar_chama_endpoint_correto(self) -> None:
        settings.op_dashboard_auth_enabled = False
        contact = self._seed_contact()
        conv = self._seed_conversation(contact=contact, needs_human=True, human_reason="agendamento")
        self.db.commit()
        response = self.client.post(f"/dashboard/op/conversations/{conv.id}/human/accept")
        assert response.status_code == 200

    # 23
    def test_modal_ignorar_chama_endpoint_correto(self) -> None:
        settings.op_dashboard_auth_enabled = False
        contact = self._seed_contact()
        conv = self._seed_conversation(contact=contact, needs_human=True, human_reason="agendamento")
        self.db.commit()
        response = self.client.post(f"/dashboard/op/conversations/{conv.id}/human/ignore")
        assert response.status_code == 200

    # 24
    def test_desligar_chatbot_salva_false(self) -> None:
        settings.op_dashboard_auth_enabled = False
        contact = self._seed_contact()
        conv = self._seed_conversation(contact=contact)
        self.db.commit()
        response = self.client.post(
            f"/dashboard/op/conversations/{conv.id}/chatbot/toggle",
            json={"enabled": False},
        )
        assert response.status_code == 200
        assert response.json().get("chatbot_enabled") is False

    # 25
    def test_worker_nao_envia_resposta_automatica_chatbot_off(self) -> None:
        settings.op_dashboard_auth_enabled = False
        settings.llm_enabled = False
        contact = self._seed_contact()
        conv = self._seed_conversation(contact=contact)
        setattr(conv, "chatbot_enabled", False)
        inbound = self._seed_message(conversation=conv, direction="inbound", text="oi")
        self.db.commit()
        with patch("app.workers.tasks.generate_reply", wraps=tasks.generate_reply) as mocked_generate:
            result = tasks.process_incoming_message({"message_id": str(inbound.id), "platform": conv.platform})
        assert result.get("status") in {"completed", "failed", "ignored_chatbot_disabled"}
        assert mocked_generate.call_count == 0

    # 26
    def test_followup_nao_dispara_chatbot_off(self) -> None:
        contact = self._seed_contact()
        conv = self._seed_conversation(contact=contact)
        setattr(conv, "chatbot_enabled", False)
        self._seed_message(
            conversation=conv,
            direction="inbound",
            text="oi",
            created_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        self.db.commit()
        result = tasks.send_follow_up(conversation_id=str(conv.id), stage_minutes=30, reply_message_id=None)
        assert result.get("status") in {"ignored_chatbot_disabled", "completed"}

    # 27
    def test_ligar_chatbot_salva_true(self) -> None:
        settings.op_dashboard_auth_enabled = False
        contact = self._seed_contact()
        conv = self._seed_conversation(contact=contact)
        self.db.commit()
        response = self.client.post(
            f"/dashboard/op/conversations/{conv.id}/chatbot/toggle",
            json={"enabled": True},
        )
        assert response.status_code == 200
        assert response.json().get("chatbot_enabled") is True

    # 28
    def test_banco_dados_lista_nome_telefone_e_agendado(self) -> None:
        settings.op_dashboard_auth_enabled = False
        self._seed_contact(name="Maria", phone="5511777777777")
        self.db.commit()
        response = self.client.get("/dashboard/op/contacts")
        assert response.status_code == 200
        first = response.json().get("items", [])[0]
        assert "name" in first and "phone" in first and "scheduled" in first

    # 29
    def test_modal_cliente_retorna_blocos_separados(self) -> None:
        settings.op_dashboard_auth_enabled = False
        contact = self._seed_contact(name="Jose")
        self.db.commit()
        response = self.client.get(f"/dashboard/op/contacts/{contact.id}")
        assert response.status_code == 200
        data = response.json()
        assert "main" in data
        assert "channels" in data
        assert "memories" in data
        assert "conversations" in data
        assert "agenda" in data
        assert "notes" in data
        assert "data_sources" in data

    # 30
    def test_agenda_retorna_horarios_livres_reservados(self) -> None:
        settings.op_dashboard_auth_enabled = False
        response = self.client.get("/dashboard/op/appointments")
        assert response.status_code == 200
        assert "slots" in response.json()

    def test_agenda_aceita_filtro_periodo_por_query(self) -> None:
        settings.op_dashboard_auth_enabled = False
        response = self.client.get("/dashboard/op/appointments?start_date=2026-05-01&end_date=2026-05-31")
        assert response.status_code == 200
        payload = response.json()
        assert "slots" in payload
        assert payload.get("range_start_date") == "2026-05-01"
        assert payload.get("range_end_date") == "2026-05-31"

    # 31
    def test_proximos_5_agendamentos_lista_ou_mensagem_vazia(self) -> None:
        settings.op_dashboard_auth_enabled = False
        response = self.client.get("/dashboard/op/appointments?include_next=true")
        assert response.status_code == 200
        payload = response.json()
        assert "next_appointments" in payload
        assert "next_appointments_message" in payload

    # 32
    def test_usuario_sem_auth_nao_consegue_enviar_mensagem(self) -> None:
        settings.op_dashboard_auth_enabled = True
        settings.op_dashboard_username = "op"
        settings.op_dashboard_password_hash = "0000"
        contact = self._seed_contact()
        conv = self._seed_conversation(contact=contact)
        self.db.commit()
        response = self.client.post(
            f"/dashboard/op/conversations/{conv.id}/send",
            json={"channel": "whatsapp", "text": "teste"},
        )
        assert response.status_code in {401, 403}

    # 33
    def test_endpoint_status_nao_expoe_secrets(self) -> None:
        settings.op_dashboard_auth_enabled = False
        settings.whatsapp_gateway_api_key = "SECRET_GATEWAY"
        settings.evolution_api_key = "SECRET_EVOLUTION"
        response = self.client.get("/dashboard/op/status")
        assert response.status_code == 200
        payload_text = str(response.json())
        assert "SECRET_GATEWAY" not in payload_text
        assert "SECRET_EVOLUTION" not in payload_text

    # 34
    def test_iniciar_conversa_reabre_conversa_fechada(self) -> None:
        settings.op_dashboard_auth_enabled = False
        contact = self._seed_contact()
        conv = self._seed_conversation(contact=contact, platform="whatsapp", status="closed")
        self.db.commit()
        response = self.client.post(f"/dashboard/op/contacts/{contact.id}/start-conversation?channel=whatsapp")
        assert response.status_code == 200
        payload = response.json()
        assert payload.get("conversation_id") == str(conv.id)
        assert payload.get("status") == "reopened"
        self.db.refresh(conv)
        assert conv.status == "open"

    # 35
    def test_iniciar_conversa_cria_nova_quando_nao_existe(self) -> None:
        settings.op_dashboard_auth_enabled = False
        contact = self._seed_contact()
        self.db.commit()
        response = self.client.post(f"/dashboard/op/contacts/{contact.id}/start-conversation?channel=whatsapp")
        assert response.status_code == 200
        payload = response.json()
        assert payload.get("status") == "created"
        conversation = self.db.query(Conversation).filter(Conversation.contact_id == contact.id).first()
        assert conversation is not None
        assert str(conversation.id) == payload.get("conversation_id")

    # 36
    def test_modal_humano_nao_aparece_sem_human_pending(self) -> None:
        settings.op_dashboard_auth_enabled = False
        contact = self._seed_contact()
        conv = self._seed_conversation(contact=contact, needs_human=True, human_reason="duvida_valor")
        conv.human_status = "human_accepted"
        self.db.commit()
        response = self.client.get("/dashboard/op/human-queue?for_modal=true")
        assert response.status_code == 200
        assert response.json().get("items") == []

    # 37
    def test_fila_humana_ordenada_por_data_da_requisicao(self) -> None:
        settings.op_dashboard_auth_enabled = False
        now = datetime.now(timezone.utc)
        contact_a = self._seed_contact(name="A")
        contact_b = self._seed_contact(name="B", phone="5511888888888")
        old_conv = self._seed_conversation(contact=contact_a, needs_human=True, human_reason="duvida_valor")
        new_conv = self._seed_conversation(contact=contact_b, needs_human=True, human_reason="duvida_pagamento")
        old_conv.human_requested_at = now - timedelta(minutes=20)
        new_conv.human_requested_at = now - timedelta(minutes=2)
        self.db.commit()
        response = self.client.get("/dashboard/op/human-queue")
        assert response.status_code == 200
        queue_ids = [item.get("conversation_id") for item in response.json().get("items", [])]
        assert queue_ids.index(str(old_conv.id)) < queue_ids.index(str(new_conv.id))

    # 38
    def test_modal_humano_retorna_caminho_simplificado_do_menu(self) -> None:
        settings.op_dashboard_auth_enabled = False
        now = datetime.now(timezone.utc)
        contact = self._seed_contact()
        conv = self._seed_conversation(contact=contact, needs_human=True, human_reason="problema_agendamento")
        conv.human_requested_at = now
        for idx, value in enumerate(["1", "2", "3", "4", "5", "6"]):
            self._seed_message(
                conversation=conv,
                direction="inbound",
                text=value,
                created_at=now - timedelta(minutes=10 - idx),
            )
        self.db.commit()
        response = self.client.get("/dashboard/op/human-queue?for_modal=true")
        assert response.status_code == 200
        item = response.json().get("items", [])[0]
        path = str(item.get("menu_path_summary") or "")
        assert "Agendamento" in path
        assert "historico completo" in path

    # 39
    def test_busca_clientes_por_nome_no_endpoint_contacts(self) -> None:
        settings.op_dashboard_auth_enabled = False
        self._seed_contact(name="Ana Clara")
        self._seed_contact(name="Bruno")
        self.db.commit()
        response = self.client.get("/dashboard/op/contacts?search=Ana")
        assert response.status_code == 200
        items = response.json().get("items", [])
        assert len(items) == 1
        assert items[0].get("name") == "Ana Clara"
