from __future__ import annotations

import re
import sys
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.services.base import BaseExternalService, ExternalServiceResult


class LLMReplyService(BaseExternalService):
    """Generates replies using a local/open-source LLM endpoint."""

    service_name = "llm_reply"
    _LINK_NEW_SCHEDULE = "https://www.fcvip.com.br/formulario"
    _LINK_NEW_DISCOVER = "https://www.fcvip.com.br"
    _LINK_OLD_SCHEDULE = "https://www.fcvip.com.br/agendamentos"
    _CLOSING_PHRASE = "Por nada! Sempre que precisar de ajuda é só entrar em contato a FC VIP agradece seu contato"

    _THANKS_MARKERS = {
        "obrigado",
        "obrigada",
        "muito obrigado",
        "muito obrigada",
        "agradeco",
        "agradeço",
        "valeu",
        "vlw",
    }
    _FINALIZE_MARKERS = {
        "vou fechar",
        "vou agendar",
        "vou marcar",
        "vou reservar",
        "vou ver no site",
        "vou olhar no site",
        "entendi, obrigado",
        "entendi, obrigada",
        "tudo certo",
        "fechado",
    }
    _GREETING_MARKERS = {
        "oi",
        "oie",
        "ola",
        "olaa",
        "ols",
        "opa",
        "bom dia",
        "boa tarde",
        "boa noite",
        "ola tudo bem",
        "oi tudo bem",
        "bom dia tudo bem",
        "boa tarde tudo bem",
        "boa noite tudo bem",
    }

    _VALUE_KEYWORDS = {
        "valor",
        "valores",
        "preco",
        "precos",
        "preço",
        "preços",
        "pacote",
        "pacotes",
        "tabela",
    }
    _TOUR_KEYWORDS = {
        "tour",
        "tour virtual",
        "ver o espaco",
        "ver o espaço",
        "conhecer o espaco",
        "conhecer o espaço",
        "fotos do estudio",
        "fotos do estúdio",
        "video do estudio",
        "vídeo do estúdio",
    }
    _RISK_CONTENT_KEYWORDS = {
        "fumaca",
        "fumaça",
        "confete",
        "espuma",
        "liquido",
        "líquido",
        "liquidos",
        "líquidos",
        "agua",
        "água",
        "tinta",
        "tintas",
        "glitter",
        "smash the cake",
        "bolo",
        "areia",
        "po colorido",
        "pó colorido",
        "sangue falso",
        "fogo",
        "vela",
        "velas",
        "faisca",
        "faísca",
        "animais",
        "animal",
    }
    _CANCEL_RESCHEDULE_KEYWORDS = {
        "cancelar",
        "cancelamento",
        "reagendar",
        "reagendamento",
        "remarcar",
        "trocar horario",
        "trocar data",
        "trocar dia",
        "trocar horário",
        "mudar horario",
        "mudar data",
        "mudar dia",
        "alterar horario",
        "alterar data",
        "mudar horário",
    }
    _PAID_MARKERS = {
        "ja paguei",
        "já paguei",
        "pago",
        "paga",
        "pagamento",
        "paguei",
        "ja esta pago",
        "ja foi pago",
        "reserva paga",
        "reserva ja paga",
        "horario pago",
        "apos pagamento",
        "depois de pagar",
    }

    _INTENT_SCHEDULE_KEYWORDS = {
        "agendar",
        "agendamento",
        "reserva",
        "marcar",
        "data",
        "horario",
        "disponibilidade",
        "agenda",
        "vaga",
    }
    _SCHEDULE_EXPLORATORY_MARKERS = {
        "como funciona",
        "sou novo cliente",
        "primeira vez",
        "quero entender",
        "me explica",
    }
    _SCHEDULE_AVAILABILITY_MARKERS = {
        "disponibilidade",
        "horario",
        "data",
        "vaga",
        "agenda",
        "amanha",
        "hoje",
        "segunda",
        "terca",
        "quarta",
        "quinta",
        "sexta",
        "sabado",
        "domingo",
    }
    _INTENT_DISCOVER_KEYWORDS = {
        "conhecer",
        "como funciona",
        "quero conhecer",
        "primeira vez",
        "informacoes",
        "estrutura",
    }
    _OLD_CUSTOMER_MARKERS = {
        "sou cliente",
        "cliente antigo",
        "ja fui cliente",
        "ja conheco",
        "eu ja conheco",
        "voltei",
        "retornando",
    }
    _NEW_CUSTOMER_MARKERS = {
        "cliente novo",
        "nao conheco",
        "primeira vez",
        "ainda nao conheco",
        "nunca fui",
    }
    _FOLLOW_UP_MARKERS = {
        "ok",
        "certo",
        "beleza",
        "entendi",
        "isso",
        "sim",
        "pode ser",
        "perfeito",
        "quero",
        "manda",
        "segue",
    }
    _QUALITY_CRITICAL_INTENT_KEYWORDS = {
        "valor",
        "preco",
        "orcamento",
        "agendar",
        "agendamento",
        "horario",
        "disponibilidade",
        "reserva",
    }
    _LOW_QUALITY_MARKERS = {
        "como ia",
        "como modelo",
        "como assistente virtual",
        "como assistente de inteligencia artificial",
        "nao tenho acesso",
        "nao tenho acesso a informacoes especificas",
        "nao posso acessar",
        "nao posso ajudar com isso",
        "nao consigo ajudar com isso",
    }
    _LOCATION_TOPIC_KEYWORDS = {
        "onde fica",
        "qual endereco",
        "endereco",
        "bairro",
        "como chego",
        "como chegar",
        "acesso",
        "estacionamento",
        "parar carro",
        "elevador",
        "escada",
        "facil acesso",
        "localizacao",
        "rua ou em shopping",
        "fica na rua",
        "shopping",
        "volta redonda",
        "fica em volta redonda",
    }
    _LOCATION_OFFICIAL_PRIMARY_MARKERS = {"corifeu", "corifeu marques"}
    _LOCATION_OFFICIAL_CONTEXT_MARKERS = {"jardim amalia", "volta redonda", "rj", "rio de janeiro"}
    _AUDIO_TOPIC_KEYWORDS = {
        "audio",
        "microfone",
        "microfones",
        "lapela",
        "mesa de som",
        "boom",
        "shotgun",
        "interface de audio",
        "interface",
    }
    _AUDIO_NEGATIVE_MARKERS = {
        "nao",
        "sem",
        "nao possui",
        "nao oferecemos",
        "nao trabalhamos",
    }
    _AUDIO_POLICY_CONTEXT_MARKERS = {
        "equipamentos de audio",
        "estrutura fotografica",
        "iluminacao",
    }
    _PERSONAL_QUESTION_MARKERS = {
        "voce e casada",
        "voce e casado",
        "vc e casada",
        "vc e casado",
        "voce namora",
        "voce tem namorado",
        "voce tem namorada",
        "quantos anos voce tem",
        "onde voce mora",
    }
    _PROFANITY_MARKERS = {
        "foder",
        "fude",
        "fuder",
        "fuck",
        "fdp",
        "caralho",
        "porra",
        "vai tomar no cu",
        "se fuder",
        "se fode",
    }
    _VISIT_EXPERIENCE_MARKERS = {
        "fui ai",
        "fui no estudio",
        "fui ao estudio",
        "estive ai",
        "estive no estudio",
        "passei ai",
        "fui ai na sexta",
        "fui ai no sabado",
        "fui ai ontem",
    }
    _CONTACT_INTAKE_HINTS = {
        "nome completo",
        "@ do instagram",
        "arroba do instagram",
        "fotografo",
        "videomaker",
        "modelo",
        "locacao",
    }
    _KNOWLEDGE_CACHE_SIGNATURE: tuple[str, int] | None = None
    _KNOWLEDGE_CACHE_VALUE: str = ""
    _KNOWLEDGE_SECTIONS_CACHE_KEY: int | None = None
    _KNOWLEDGE_SECTIONS_CACHE_VALUE: list[tuple[str, str]] = []
    _TOPIC_SECTION_HINTS: dict[str, tuple[str, ...]] = {
        "location": ("endereco", "acesso", "estacionamento", "localizacao", "bairro", "rua", "escada"),
        "audio": ("audio", "microfone", "lapela", "mesa de som", "boom", "shotgun", "interface"),
        "risk": ("risco", "transferencia", "cancelamento", "reagendamento", "mais de 5 pessoas", "animais"),
        "schedule": ("agendar", "agendamento", "disponibilidade", "horario", "site", "pagamento"),
        "structure": ("equipamentos", "estrutura", "fundos", "iluminacao", "infraestrutura"),
    }
    _TOPIC_USER_MARKERS: dict[str, tuple[str, ...]] = {
        "location": (
            "onde fica",
            "endereco",
            "bairro",
            "estacionamento",
            "acesso",
            "shopping",
            "rua",
            "escada",
        ),
        "audio": ("audio", "microfone", "lapela", "mesa de som", "boom", "shotgun", "interface"),
        "risk": (
            "cancelar",
            "reagendar",
            "reagendamento",
            "paguei",
            "reserva paga",
            "confete",
            "fumaca",
            "glitter",
            "animal",
            "somos",
            "pessoas",
            "grupo",
        ),
        "schedule": (
            "agendar",
            "agendamento",
            "disponibilidade",
            "horario",
            "reserva",
            "valor",
            "preco",
            "pacote",
        ),
        "structure": (
            "estrutura",
            "equipamento",
            "softbox",
            "fundo",
            "iluminacao",
            "ar condicionado",
            "cenografia",
            "inclui",
        ),
    }
    def generate_reply(
        self,
        *,
        user_text: str,
        context_messages: list[dict[str, Any]] | None = None,
        key_memories: list[dict[str, Any]] | None = None,
        model_override: str | None = None,
    ) -> ExternalServiceResult:
        action = "generate_reply"
        if not settings.llm_ready:
            return self.integration_disabled(action, "llm_not_ready")

        cleaned_user_text = " ".join((user_text or "").split()).strip()
        if not cleaned_user_text:
            return self.invalid_payload(action, "user_text is required")

        context_messages = context_messages or []
        key_memories = key_memories or []
        requested_model = str(model_override or settings.llm_model).strip() or "unknown"
        normalized_user_text = self._normalize_for_quality(cleaned_user_text)

        if self._is_greeting(normalized_user_text):
            reply_text = self._append_contact_intake_if_needed(
                reply_text=(
                    "Ola! Sou o Agente FC VIP. "
                    "Posso te ajudar com estrutura, valores e agendamento do estudio."
                ),
                user_text=cleaned_user_text,
                key_memories=key_memories,
            )
            return ExternalServiceResult(
                status="completed",
                service=self.service_name,
                action=action,
                model="rule_greeting",
                requested_model=requested_model,
                attempted_models=["rule_greeting"],
                quality_issue=None,
                quality_retry_status="not_needed",
                routing_link=None,
                reply_text=reply_text,
            )

        if self._should_close_conversation(cleaned_user_text):
            return ExternalServiceResult(
                status="completed",
                service=self.service_name,
                action=action,
                model="rule_close",
                requested_model=requested_model,
                attempted_models=["rule_close"],
                quality_issue=None,
                quality_retry_status="not_needed",
                routing_link=None,
                reply_text=self._CLOSING_PHRASE,
            )

        if self._is_personal_question(normalized_user_text):
            reply_text = self._append_contact_intake_if_needed(
                reply_text=(
                    "Eu sou o Agente FC VIP e foco no atendimento do estudio. "
                    "Posso te ajudar com estrutura, valores e agendamento."
                ),
                user_text=cleaned_user_text,
                key_memories=key_memories,
            )
            return ExternalServiceResult(
                status="completed",
                service=self.service_name,
                action=action,
                model="rule_domain_redirect",
                requested_model=requested_model,
                attempted_models=["rule_domain_redirect"],
                quality_issue=None,
                quality_retry_status="not_needed",
                routing_link=None,
                reply_text=reply_text,
            )

        if self._contains_profanity(normalized_user_text):
            reply_text = self._append_contact_intake_if_needed(
                reply_text=(
                    "Vamos manter um tom respeitoso para continuar o atendimento. "
                    "Posso te ajudar com locacao do estudio, valores e agendamento."
                ),
                user_text=cleaned_user_text,
                key_memories=key_memories,
            )
            return ExternalServiceResult(
                status="completed",
                service=self.service_name,
                action=action,
                model="rule_respect_redirect",
                requested_model=requested_model,
                attempted_models=["rule_respect_redirect"],
                quality_issue=None,
                quality_retry_status="not_needed",
                routing_link=None,
                reply_text=reply_text,
            )

        if self._is_visit_experience_comment(normalized_user_text):
            reply_text = self._append_contact_intake_if_needed(
                reply_text=(
                    "Que bom saber que voce esteve no estudio. "
                    "Eu nao tenho sentimentos, mas fico feliz em seguir com seu atendimento. "
                    "Se puder, me conte como foi sua experiencia e qual nota de 0 a 10 voce daria para a FC VIP."
                ),
                user_text=cleaned_user_text,
                key_memories=key_memories,
            )
            return ExternalServiceResult(
                status="completed",
                service=self.service_name,
                action=action,
                model="rule_visit_feedback",
                requested_model=requested_model,
                attempted_models=["rule_visit_feedback"],
                quality_issue=None,
                quality_retry_status="not_needed",
                routing_link=None,
                reply_text=reply_text,
            )

        escalation_reason = self._detect_escalation_reason(cleaned_user_text)
        if escalation_reason:
            return ExternalServiceResult(
                status="completed",
                service=self.service_name,
                action=action,
                model="rule_human_handoff",
                requested_model=requested_model,
                attempted_models=["rule_human_handoff"],
                quality_issue=None,
                quality_retry_status="not_needed",
                routing_link=None,
                reply_text=(
                    "Entendi sua solicitacao. Para esse tipo de caso, preciso encaminhar para a nossa equipe humana "
                    f"para avaliacao e confirmacao. Motivo: {escalation_reason}."
                ),
            )

        cta_link, cta_reason = self._select_cta_link(cleaned_user_text, context_messages, key_memories)

        if self._is_value_request(cleaned_user_text):
            if not cta_link:
                cta_link = self._LINK_NEW_SCHEDULE
            cta_reason = "valores"
            reply_text = self._ensure_final_cta(
                "Os pacotes e valores atualizados sao consultados pelo nosso site oficial.",
                cta_link,
                cta_reason,
            )
            reply_text = self._append_contact_intake_if_needed(
                reply_text=reply_text,
                user_text=cleaned_user_text,
                key_memories=key_memories,
            )
            return ExternalServiceResult(
                status="completed",
                service=self.service_name,
                action=action,
                model="rule_values_site_only",
                requested_model=requested_model,
                attempted_models=["rule_values_site_only"],
                quality_issue=None,
                quality_retry_status="not_needed",
                routing_link=cta_link,
                reply_text=reply_text,
            )

        if self._is_explicit_schedule_request(cleaned_user_text):
            if not cta_link:
                recent_text = " ".join(str(item.get("text") or "") for item in context_messages[-settings.llm_effective_context_messages :])
                customer_status = self._infer_customer_status(self._normalize(f"{cleaned_user_text} {recent_text}"), key_memories)
                cta_link = self._LINK_OLD_SCHEDULE if customer_status == "antigo" else self._LINK_NEW_SCHEDULE
            cta_reason = "agendar"
            schedule_reply = self._build_schedule_rule_reply(cleaned_user_text)
            reply_text = self._ensure_final_cta(schedule_reply, cta_link, cta_reason)
            reply_text = self._append_contact_intake_if_needed(
                reply_text=reply_text,
                user_text=cleaned_user_text,
                key_memories=key_memories,
            )
            return ExternalServiceResult(
                status="completed",
                service=self.service_name,
                action=action,
                model="rule_schedule_site_only",
                requested_model=requested_model,
                attempted_models=["rule_schedule_site_only"],
                quality_issue=None,
                quality_retry_status="not_needed",
                routing_link=cta_link,
                reply_text=reply_text,
            )

        model_name = str(model_override or settings.llm_model).strip()
        if not model_name:
            return self.invalid_payload(action, "model is required")
        quality_fallback_model = self._resolve_quality_fallback_model(model_name)

        identity_reply = self._build_identity_reply(cleaned_user_text, key_memories)
        if identity_reply:
            identity_reply = self._append_contact_intake_if_needed(
                reply_text=identity_reply,
                user_text=cleaned_user_text,
                key_memories=key_memories,
            )
            return ExternalServiceResult(
                status="completed",
                service=self.service_name,
                action=action,
                model="rule_memory",
                requested_model=model_name,
                attempted_models=["rule_memory"],
                quality_issue=None,
                quality_retry_status="not_needed",
                routing_link=None,
                reply_text=identity_reply,
            )

        options: dict[str, Any] = {
            "temperature": settings.llm_temperature,
            "num_predict": settings.llm_max_output_tokens,
        }
        if settings.llm_num_ctx > 0:
            options["num_ctx"] = settings.llm_num_ctx
        if settings.llm_num_thread > 0:
            options["num_thread"] = settings.llm_num_thread

        payload = {
            "model": model_name,
            "stream": False,
            "messages": self._build_messages(
                user_text=cleaned_user_text,
                context_messages=context_messages,
                key_memories=key_memories,
            ),
            "options": options,
        }
        if settings.llm_keep_alive.strip():
            payload["keep_alive"] = settings.llm_keep_alive.strip()

        primary_reply, result = self._request_reply_text(
            action=action,
            payload=payload,
        )
        if result is not None:
            return result
        if not primary_reply:
            return self.request_failed(action, "empty_llm_response")

        selected_model = model_name
        selected_reply = primary_reply
        quality_issue = self._detect_quality_issue(
            user_text=cleaned_user_text,
            reply_text=primary_reply,
        )
        quality_retry_status = "not_needed"
        attempted_models = [model_name]

        if quality_issue and quality_fallback_model:
            quality_retry_status = "triggered"
            attempted_models.append(quality_fallback_model)
            fallback_reply, fallback_result = self._request_reply_text(
                action=action,
                payload={
                    **payload,
                    "model": quality_fallback_model,
                },
            )
            if fallback_reply:
                fallback_issue = self._detect_quality_issue(
                    user_text=cleaned_user_text,
                    reply_text=fallback_reply,
                )
                if fallback_issue is None or len(fallback_reply) >= len(primary_reply):
                    selected_model = quality_fallback_model
                    selected_reply = fallback_reply
                    quality_issue = fallback_issue
                    quality_retry_status = "fallback_used"
                else:
                    quality_retry_status = "fallback_not_better"
            elif fallback_result is not None:
                quality_retry_status = "fallback_failed"

        sanitized_reply = self._sanitize_identity_hallucination(selected_reply)
        sanitized_reply = self._sanitize_low_quality_reply(
            user_text=cleaned_user_text,
            reply_text=sanitized_reply,
        )
        policy_aligned_reply = self._apply_domain_policy_guards(
            user_text=cleaned_user_text,
            reply_text=sanitized_reply,
        )
        reply_text = self._ensure_final_cta(policy_aligned_reply, cta_link, cta_reason)
        reply_text = self._append_contact_intake_if_needed(
            reply_text=reply_text,
            user_text=cleaned_user_text,
            key_memories=key_memories,
        )

        return ExternalServiceResult(
            status="completed",
            service=self.service_name,
            action=action,
            model=selected_model,
            requested_model=model_name,
            attempted_models=attempted_models,
            quality_issue=quality_issue,
            quality_retry_status=quality_retry_status,
            routing_link=cta_link,
            reply_text=reply_text,
        )

    def _build_messages(
        self,
        *,
        user_text: str,
        context_messages: list[dict[str, Any]],
        key_memories: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        domain_description = " ".join(settings.llm_domain_description.split()).strip()
        context_window_size = settings.llm_effective_context_messages
        tolerated_offtopic_turns = max(1, int(settings.llm_offtopic_tolerance_turns))
        prompt_context_chars = max(200, int(settings.llm_prompt_max_context_chars))
        limited_memories = max(4, int(settings.llm_max_key_memories))
        knowledge_text = self._build_knowledge_text_for_prompt(
            user_text=user_text,
            context_messages=context_messages,
        )

        system_prompt = (
            "Voce e o Agente Virtual da FC VIP, um estudio de fotografia e video. "
            "Fale somente sobre locacao do estudio, informacoes de estrutura, regras de uso e agendamento via site. "
            "Tom obrigatorio: profissional, formal, respeitoso e direto (evite girias e excesso de emojis). "
            "Mantenha linguagem natural e humana, sem parecer robotico. "
            "Sempre considere o contexto das ultimas mensagens (janela de 3 a 5) e as memorias-chave do cliente antes de responder. "
            "Nunca negocie valores, nunca feche contrato, nunca prometa disponibilidade de agenda. "
            "Nao ofereca suporte tecnico avancado. "
            "Se o cliente fizer um desvio leve de assunto, responda em ate 1-2 frases e redirecione com suavidade para o tema do estudio. "
            f"Se o desvio persistir por mais de {tolerated_offtopic_turns} interacoes, redirecione com firmeza para o tema do estudio. "
            "Sempre tente coletar: nome, @ do Instagram, se e fotografo/videomaker/modelo ou apenas locacao, duracao e numero de pessoas. "
            "Se o cliente nao quiser responder, continue normalmente. "
            "Se detectar solicitacao complexa, risco, ou cancelamento/reagendamento de horario ja pago, encaminhe para atendimento humano. "
            "Nunca confirme horario manualmente; o agendamento e o pagamento sao feitos obrigatoriamente pelo site. "
            "Regra de link: nao envie link em todas as mensagens; envie apenas quando (1) o cliente pedir agendamento/disponibilidade/horarios, "
            "(2) voce apresentar valores/pacotes pela primeira vez, ou (3) quando voce sugerir tour virtual para conhecer o espaco. "
            "Quando o cliente agradecer e finalizar, encerre exatamente com: "
            f"'{self._CLOSING_PHRASE}'. "
            "Se perguntarem seu nome, responda exatamente: 'Eu sou o Agente FC VIP'. "
            "Nunca diga que e Watson, Claude, Anthropic, OpenAI ou qualquer outro nome externo."
        )
        if settings.llm_domain_lock:
            if domain_description:
                system_prompt += f" Dominio permitido para atendimento: {domain_description}."
            else:
                system_prompt += " Dominio permitido para atendimento: estudio, fotografia, video e agendamento."
        if knowledge_text:
            system_prompt += "\n\nBase oficial FC VIP:\n" + knowledge_text
        if key_memories:
            compact_memories = [
                f"- {str(item.get('key') or '').strip()}: {str(item.get('value') or '').strip()}"
                for item in key_memories
                if str(item.get("key") or "").strip() and str(item.get("value") or "").strip()
            ]
            if compact_memories:
                system_prompt += "\n\nMemorias-chave do cliente:\n" + "\n".join(compact_memories[:limited_memories])

        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        recent_context_messages = context_messages[-context_window_size:]
        for item in recent_context_messages:
            role = str(item.get("role") or "").strip().lower()
            content = " ".join(str(item.get("text") or "").split()).strip()
            if role not in {"user", "assistant"} or not content:
                continue
            messages.append({"role": role, "content": content[:prompt_context_chars]})

        messages.append({"role": "user", "content": user_text})
        return messages

    def _request_reply_text(
        self,
        *,
        action: str,
        payload: dict[str, Any],
    ) -> tuple[str | None, ExternalServiceResult | None]:
        url = settings.llm_base_url.rstrip("/") + "/api/chat"
        result = self._request(
            "POST",
            url,
            json_payload=payload,
            timeout_seconds=max(5.0, float(settings.llm_timeout_seconds)),
        )
        if result.get("status") != "ok":
            return None, result

        body = result.get("body")
        reply_text = self._extract_reply_text(body)
        if not reply_text:
            return None, self.request_failed(action, "empty_llm_response")
        return reply_text, None

    def _resolve_quality_fallback_model(self, current_model: str) -> str | None:
        if not settings.llm_quality_retry_enabled:
            return None
        candidate = str(settings.llm_quality_fallback_model or "").strip()
        if not candidate or candidate == current_model:
            return None
        return candidate

    def _detect_quality_issue(self, *, user_text: str, reply_text: str) -> str | None:
        compact_reply = " ".join(str(reply_text or "").split()).strip()
        if not compact_reply:
            return "empty_reply"

        min_chars = max(40, int(settings.llm_quality_min_chars))
        if len(compact_reply) < min_chars:
            return "reply_too_short"

        normalized_reply = self._normalize_for_quality(compact_reply)
        if any(marker in normalized_reply for marker in self._LOW_QUALITY_MARKERS):
            return "low_quality_marker"

        if (
            self._normalize_for_quality(self._CLOSING_PHRASE) in normalized_reply
            and not self._should_close_conversation(user_text)
        ):
            return "unexpected_closing"

        normalized_user = self._normalize_for_quality(user_text)
        critical_intent = any(keyword in normalized_user for keyword in self._QUALITY_CRITICAL_INTENT_KEYWORDS)
        if critical_intent and len(compact_reply) < (min_chars + 30):
            return "critical_intent_low_depth"
        return None

    def _normalize_for_quality(self, value: str) -> str:
        return self._normalize_ascii_cached(str(value or ""))

    @staticmethod
    @lru_cache(maxsize=4096)
    def _normalize_ascii_cached(value: str) -> str:
        lowered = str(value or "").lower()
        ascii_value = unicodedata.normalize("NFKD", lowered).encode("ascii", "ignore").decode("ascii")
        return " ".join(ascii_value.split())

    def _build_knowledge_text_for_prompt(
        self,
        *,
        user_text: str,
        context_messages: list[dict[str, Any]],
    ) -> str:
        base_knowledge = self._load_knowledge_text()
        if not base_knowledge:
            return ""

        context_window_size = settings.llm_effective_context_messages
        recent_context_messages = context_messages[-context_window_size:]
        recent_text = " ".join(str(item.get("text") or "") for item in recent_context_messages)
        normalized_probe = self._normalize_for_quality(f"{user_text} {recent_text}")
        selected_topics = self._select_topics(normalized_probe)
        selected_sections = self._select_knowledge_sections(base_knowledge, selected_topics)
        max_chars = max(1000, int(settings.llm_knowledge_max_chars))

        if not selected_sections:
            return base_knowledge[:max_chars]

        assembled: list[str] = []
        total_chars = 0
        for section_text in selected_sections:
            chunk = section_text.strip()
            if not chunk:
                continue
            projected = total_chars + len(chunk) + 2
            if projected > max_chars and assembled:
                break
            if projected > max_chars:
                assembled.append(chunk[:max_chars])
                break
            assembled.append(chunk)
            total_chars = projected

        final_text = "\n\n".join(assembled).strip()
        if not final_text:
            return base_knowledge[:max_chars]
        return final_text

    def _select_topics(self, normalized_probe: str) -> list[str]:
        selected: list[str] = []
        for topic, markers in self._TOPIC_USER_MARKERS.items():
            if any(marker in normalized_probe for marker in markers):
                selected.append(topic)
        return selected

    def _select_knowledge_sections(self, knowledge_text: str, topics: list[str]) -> list[str]:
        sections = self._split_markdown_sections(knowledge_text)
        if not sections:
            return []

        max_sections = max(1, int(settings.llm_knowledge_max_sections))
        normalized_topics = [item for item in topics if item in self._TOPIC_SECTION_HINTS]

        prioritized: list[str] = []
        for heading, content in sections:
            normalized_heading = self._normalize_for_quality(heading)
            normalized_content = self._normalize_for_quality(content[:1400])

            if not normalized_topics:
                if "regras estritas" in normalized_heading or "base de conhecimento" in normalized_heading:
                    prioritized.append(content)
                continue

            for topic in normalized_topics:
                hints = self._TOPIC_SECTION_HINTS.get(topic, ())
                if any(hint in normalized_heading for hint in hints) or any(hint in normalized_content for hint in hints):
                    prioritized.append(content)
                    break

        if not prioritized:
            prioritized = [sections[0][1]]

        # Dedupe while preserving order, then enforce section cap.
        seen: set[str] = set()
        unique: list[str] = []
        for content in prioritized:
            signature = self._normalize_for_quality(content[:200])
            if signature in seen:
                continue
            seen.add(signature)
            unique.append(content)
            if len(unique) >= max_sections:
                break
        return unique

    def _split_markdown_sections(self, knowledge_text: str) -> list[tuple[str, str]]:
        cls = type(self)
        cache_key = hash(knowledge_text)
        if cls._KNOWLEDGE_SECTIONS_CACHE_KEY == cache_key:
            return cls._KNOWLEDGE_SECTIONS_CACHE_VALUE

        sections: list[tuple[str, str]] = []
        current_heading = "preamble"
        current_lines: list[str] = []
        for line in knowledge_text.split("\n"):
            if line.startswith("## "):
                section_text = "\n".join(current_lines).strip()
                if section_text:
                    sections.append((current_heading, section_text))
                current_heading = line[3:].strip() or "section"
                current_lines = [line]
                continue
            current_lines.append(line)

        final_text = "\n".join(current_lines).strip()
        if final_text:
            sections.append((current_heading, final_text))

        cls._KNOWLEDGE_SECTIONS_CACHE_KEY = cache_key
        cls._KNOWLEDGE_SECTIONS_CACHE_VALUE = sections
        return sections

    def _load_knowledge_text(self) -> str:
        cls = type(self)
        path_raw = settings.llm_knowledge_path.strip()
        if not path_raw:
            return ""

        candidate_paths: list[Path] = []
        configured_path = Path(path_raw)
        if configured_path.is_absolute():
            candidate_paths.append(configured_path)
        else:
            bundle_root = getattr(sys, "_MEIPASS", "")
            if bundle_root:
                candidate_paths.append(Path(bundle_root) / configured_path)

            project_root = Path(__file__).resolve().parents[2]
            candidate_paths.append(project_root / configured_path)
            candidate_paths.append(Path.cwd() / configured_path)

        seen_paths: set[str] = set()
        for file_path in candidate_paths:
            normalized = str(file_path.resolve()) if file_path.exists() else str(file_path)
            if normalized in seen_paths:
                continue
            seen_paths.add(normalized)
            if not file_path.exists() or not file_path.is_file():
                continue
            cache_signature = (normalized, int(file_path.stat().st_mtime_ns))
            if cls._KNOWLEDGE_CACHE_SIGNATURE == cache_signature and cls._KNOWLEDGE_CACHE_VALUE:
                return cls._KNOWLEDGE_CACHE_VALUE
            try:
                content = file_path.read_text(encoding="utf-8")
            except Exception:  # noqa: BLE001
                continue
            cleaned = content.replace("\r\n", "\n").strip()
            if cleaned:
                max_chars = max(1000, int(settings.llm_knowledge_max_chars))
                cached = cleaned[:max_chars]
                cls._KNOWLEDGE_CACHE_SIGNATURE = cache_signature
                cls._KNOWLEDGE_CACHE_VALUE = cached
                cls._KNOWLEDGE_SECTIONS_CACHE_KEY = None
                cls._KNOWLEDGE_SECTIONS_CACHE_VALUE = []
                return cached
        return ""

    def _normalize(self, value: str) -> str:
        return " ".join(str(value or "").lower().strip().split())

    def _memory_lookup(self, key_memories: list[dict[str, Any]], key: str) -> str:
        value = self._memory_lookup_raw(key_memories, key)
        return value.lower() if value else ""

    def _memory_lookup_raw(self, key_memories: list[dict[str, Any]], key: str) -> str:
        for item in key_memories:
            if str(item.get("key") or "").strip() == key:
                return str(item.get("value") or "").strip()
        return ""

    def _has_memory(self, key_memories: list[dict[str, Any]], key: str) -> bool:
        return bool(self._memory_lookup(key_memories, key))

    def _is_truthy_memory(self, key_memories: list[dict[str, Any]], key: str) -> bool:
        value = self._memory_lookup(key_memories, key)
        return value in {"true", "sim", "1", "yes"}

    def _score_keywords(self, text: str, markers: set[str], weight: int) -> int:
        score = 0
        for marker in markers:
            if marker in text:
                score += weight
        return score

    def _looks_like_follow_up(self, normalized_user_text: str) -> bool:
        compact = " ".join(normalized_user_text.split()).strip()
        if not compact:
            return False
        if compact in self._FOLLOW_UP_MARKERS:
            return True
        if len(compact.split(" ")) <= 3 and any(marker in compact for marker in self._FOLLOW_UP_MARKERS):
            return True
        return False

    def _infer_customer_status(self, recent_haystack: str, key_memories: list[dict[str, Any]]) -> str:
        customer_status = ""
        memory_customer_status = self._memory_lookup(key_memories, "cliente_status")
        memory_knows_studio = self._memory_lookup(key_memories, "ja_conhece_estudio")

        if memory_customer_status in {"novo", "antigo"}:
            customer_status = memory_customer_status
        elif memory_knows_studio in {"sim", "nao"}:
            customer_status = "antigo" if memory_knows_studio == "sim" else "novo"

        if any(marker in recent_haystack for marker in self._OLD_CUSTOMER_MARKERS):
            customer_status = "antigo"
        if any(marker in recent_haystack for marker in self._NEW_CUSTOMER_MARKERS):
            customer_status = "novo"

        return customer_status

    def _infer_intent(self, user_text: str, recent_haystack: str, key_memories: list[dict[str, Any]], customer_status: str) -> str:
        normalized_user = self._normalize_for_quality(user_text)
        normalized_recent = self._normalize_for_quality(recent_haystack)

        schedule_score = 0
        discover_score = 0

        schedule_score += self._score_keywords(normalized_user, self._INTENT_SCHEDULE_KEYWORDS, 3)
        discover_score += self._score_keywords(normalized_user, self._INTENT_DISCOVER_KEYWORDS, 3)
        schedule_score += self._score_keywords(normalized_recent, self._INTENT_SCHEDULE_KEYWORDS, 1)
        discover_score += self._score_keywords(normalized_recent, self._INTENT_DISCOVER_KEYWORDS, 1)

        memory_intent = self._memory_lookup(key_memories, "intencao_principal")
        if memory_intent == "agendar":
            schedule_score += 2
        elif memory_intent == "conhecer":
            discover_score += 2

        if self._is_truthy_memory(key_memories, "duvida_disponibilidade"):
            schedule_score += 2
        if self._is_truthy_memory(key_memories, "duvida_valor"):
            schedule_score += 1
        if self._has_memory(key_memories, "horario_perguntado"):
            schedule_score += 2
        if self._has_memory(key_memories, "preferencia_horario"):
            schedule_score += 1
        if self._has_memory(key_memories, "duracao_desejada_horas"):
            schedule_score += 1
        if self._is_truthy_memory(key_memories, "quer_fotos_espaco"):
            discover_score += 1
        if self._is_truthy_memory(key_memories, "perguntou_horario_funcionamento"):
            discover_score += 1

        if customer_status == "antigo":
            schedule_score += 1
        elif customer_status == "novo":
            discover_score += 1

        if self._looks_like_follow_up(normalized_user):
            if schedule_score >= max(2, discover_score):
                return "agendar"
            if discover_score >= max(2, schedule_score):
                return "conhecer"

        if schedule_score >= max(3, discover_score + 1):
            return "agendar"
        if discover_score >= max(3, schedule_score + 1):
            return "conhecer"

        if schedule_score >= 2 and discover_score == 0:
            return "agendar"
        if discover_score >= 2 and schedule_score == 0:
            return "conhecer"

        return "indefinido"

    def _select_cta_link(
        self,
        user_text: str,
        context_messages: list[dict[str, Any]],
        key_memories: list[dict[str, Any]],
    ) -> tuple[str | None, str | None]:
        context_window_size = settings.llm_effective_context_messages
        recent_context_messages = context_messages[-context_window_size:]
        recent_text = " ".join(str(item.get("text") or "") for item in recent_context_messages)
        recent_haystack = self._normalize(recent_text)

        customer_status = self._infer_customer_status(self._normalize(f"{user_text} {recent_text}"), key_memories)
        normalized_user = self._normalize_for_quality(user_text)

        asked_schedule = any(keyword in normalized_user for keyword in self._INTENT_SCHEDULE_KEYWORDS)
        asked_values = any(keyword in normalized_user for keyword in self._VALUE_KEYWORDS)
        asked_tour = any(keyword in normalized_user for keyword in self._TOUR_KEYWORDS)
        is_follow_up = self._looks_like_follow_up(normalized_user)
        inferred_intent = self._infer_intent(user_text, recent_text, key_memories, customer_status)

        if not asked_schedule and inferred_intent == "agendar" and is_follow_up:
            asked_schedule = True
        inferred_discover_follow_up = inferred_intent == "conhecer" and (
            is_follow_up or "ver" in normalized_user or "conhecer" in normalized_user
        )

        if asked_schedule:
            if customer_status == "antigo":
                return self._LINK_OLD_SCHEDULE, "agendar"
            return self._LINK_NEW_SCHEDULE, "agendar"

        if asked_tour or inferred_discover_follow_up:
            if self._has_any_known_link(recent_haystack):
                return None, None
            return self._LINK_NEW_DISCOVER, "tour"

        if asked_values:
            if self._has_any_known_link(recent_haystack):
                return None, None
            if customer_status == "antigo":
                return self._LINK_OLD_SCHEDULE, "valores"
            return self._LINK_NEW_SCHEDULE, "valores"

        return None, None

    def _ensure_final_cta(self, reply_text: str, cta_link: str | None, cta_reason: str | None) -> str:
        compact = " ".join(str(reply_text or "").split()).strip()
        if not compact:
            compact = "Posso te ajudar com o atendimento do estudio FC VIP."

        if not cta_link:
            for known_link in {
                self._LINK_NEW_DISCOVER,
                self._LINK_NEW_SCHEDULE,
                self._LINK_OLD_SCHEDULE,
            }:
                compact = compact.replace(known_link, " ")
            compact = compact.replace("Para garantir seu horario, acesse agora:", " ")
            compact = compact.replace(
                "Para conhecer melhor o estudio e seguir com o atendimento, acesse:",
                " ",
            )
            compact = re.sub(r"\s+", " ", compact).strip(" \n\t.,;:-")
            if not compact:
                compact = "Posso te ajudar com o atendimento do estudio FC VIP."
            return compact

        for known_link in {
            self._LINK_NEW_DISCOVER,
            self._LINK_NEW_SCHEDULE,
            self._LINK_OLD_SCHEDULE,
        }:
            compact = compact.replace(known_link, cta_link)

        compact = compact.replace("[link do site]", cta_link)
        compact = compact.replace("[LINK DO SITE]", cta_link)

        if cta_link in compact:
            return compact

        if cta_reason == "tour":
            cta = f"Tour virtual no site: {cta_link}"
        elif cta_reason == "valores":
            cta = f"Pacotes e valores no site: {cta_link}"
        else:
            cta = f"Agendamento pelo site: {cta_link}"

        return f"{compact}\n\n{cta}"

    def _has_any_known_link(self, normalized_text: str) -> bool:
        return any(
            link in normalized_text
            for link in {
                self._normalize_for_quality(self._LINK_NEW_DISCOVER),
                self._normalize_for_quality(self._LINK_NEW_SCHEDULE),
                self._normalize_for_quality(self._LINK_OLD_SCHEDULE),
            }
        )

    def _should_close_conversation(self, user_text: str) -> bool:
        normalized = self._normalize_for_quality(user_text)
        if not normalized:
            return False
        if any(marker in normalized for marker in self._FINALIZE_MARKERS):
            return True
        if any(marker in normalized for marker in self._THANKS_MARKERS) and "?" not in user_text:
            return True
        return False

    def _is_greeting(self, normalized_user_text: str) -> bool:
        compact = re.sub(r"[^\w\s]", " ", str(normalized_user_text or ""))
        compact = " ".join(compact.split())
        return compact in self._GREETING_MARKERS

    def _is_explicit_schedule_request(self, user_text: str) -> bool:
        normalized = self._normalize_for_quality(user_text)
        if not normalized:
            return False

        has_booking_intent = any(keyword in normalized for keyword in self._INTENT_SCHEDULE_KEYWORDS)
        has_availability_signal = any(marker in normalized for marker in self._SCHEDULE_AVAILABILITY_MARKERS)
        has_time_range_signal = bool(
            re.search(
                r"\b(?:das?|de)\s*(\d{1,2})(?:h)?\s*(?:as|a|-)\s*(\d{1,2})(?:h)?\b",
                normalized,
            )
        )
        has_explicit_time_request = bool(self._extract_hour_mentions(user_text)) and any(
            marker in normalized
            for marker in {"pode ser", "consigo", "precisava", "quero", "marcar", "reservar", "horario", "hora"}
        )
        has_booking_intent = has_booking_intent or has_time_range_signal or has_explicit_time_request
        if not has_booking_intent and not has_availability_signal:
            return False

        has_exploratory_intent = any(marker in normalized for marker in self._SCHEDULE_EXPLORATORY_MARKERS)
        if has_exploratory_intent and not has_availability_signal:
            return False
        return True

    def _build_schedule_rule_reply(self, user_text: str) -> str:
        if self._is_out_of_business_hours(user_text):
            return (
                "Nesse horario nao trabalhamos. "
                "Para verificar todos os horarios disponiveis com seguranca, consulte a agenda completa no site."
            )
        return (
            "O agendamento e feito totalmente pelo nosso site, mas ele e super intuitivo, "
            "tenho certeza que voce conseguira agendar de forma facil e simples! "
            "Nao consigo confirmar horario manualmente por aqui."
        )

    def _is_value_request(self, user_text: str) -> bool:
        normalized = self._normalize_for_quality(user_text)
        if not normalized:
            return False
        return any(keyword in normalized for keyword in self._VALUE_KEYWORDS)

    def _extract_hour_mentions(self, user_text: str) -> list[int]:
        normalized = self._normalize_for_quality(user_text)
        if not normalized:
            return []

        hour_values: list[int] = []
        explicit_time_re = re.compile(r"\b([01]?\d|2[0-3])(?:[:h]([0-5]\d)?)?\b")
        for match in explicit_time_re.finditer(normalized):
            raw_hour = str(match.group(1) or "").strip()
            if not raw_hour:
                continue
            try:
                hour = int(raw_hour)
            except ValueError:
                continue
            if 0 <= hour <= 23:
                hour_values.append(hour)
        return hour_values[:4]

    def _is_out_of_business_hours(self, user_text: str) -> bool:
        open_hour = max(0, min(23, int(settings.llm_business_open_hour)))
        close_hour = max(1, min(24, int(settings.llm_business_close_hour)))
        if close_hour <= open_hour:
            close_hour = min(24, open_hour + 1)

        mentions = self._extract_hour_mentions(user_text)
        if not mentions:
            return False
        return any(hour < open_hour or hour >= close_hour for hour in mentions)

    def _is_personal_question(self, normalized_user_text: str) -> bool:
        return any(marker in normalized_user_text for marker in self._PERSONAL_QUESTION_MARKERS)

    def _contains_profanity(self, normalized_user_text: str) -> bool:
        return any(marker in normalized_user_text for marker in self._PROFANITY_MARKERS)

    def _is_visit_experience_comment(self, normalized_user_text: str) -> bool:
        if any(marker in normalized_user_text for marker in self._VISIT_EXPERIENCE_MARKERS):
            return True
        return bool(
            re.search(
                r"\b(?:fui|estive|passei)\b(?:\s+\w+){0,4}\b(?:estudio|ai)\b",
                normalized_user_text,
            )
        )

    def _append_contact_intake_if_needed(
        self,
        *,
        reply_text: str,
        user_text: str,
        key_memories: list[dict[str, Any]],
    ) -> str:
        if not self._needs_contact_intake(user_text=user_text, key_memories=key_memories):
            return reply_text

        normalized_reply = self._normalize_for_quality(reply_text)
        if self._reply_already_requests_intake(normalized_reply):
            return reply_text

        intake_prompt = self._build_contact_intake_prompt()
        if not reply_text.strip():
            return intake_prompt
        return f"{reply_text.strip()}\n\n{intake_prompt}"

    def _needs_contact_intake(self, *, user_text: str, key_memories: list[dict[str, Any]]) -> bool:
        normalized_user = self._normalize_for_quality(user_text)
        if not normalized_user:
            return False
        if self._should_close_conversation(user_text):
            return False

        has_known_name = bool(
            self._memory_lookup_raw(key_memories, "nome_contato").strip()
            or self._memory_lookup_raw(key_memories, "nome_cliente").strip()
        )
        return not has_known_name

    def _reply_already_requests_intake(self, normalized_reply_text: str) -> bool:
        return any(hint in normalized_reply_text for hint in self._CONTACT_INTAKE_HINTS)

    def _build_contact_intake_prompt(self) -> str:
        return (
            "Antes de avancarmos, para completar seu cadastro me informe: "
            "nome completo, @ do Instagram e se voce e fotografo, videomaker, modelo ou apenas locacao."
        )

    def _detect_escalation_reason(self, user_text: str) -> str | None:
        normalized = self._normalize_for_quality(user_text)
        if not normalized:
            return None

        if any(keyword in normalized for keyword in self._RISK_CONTENT_KEYWORDS):
            return "uso de itens/efeitos que exigem avaliacao (ex.: sujeira, liquidos, fumaca, glitter, fogo ou animais)"

        if self._is_paid_change_request(normalized):
            return "cancelamento/reagendamento de horario ja pago"

        if self._mentions_more_than_five_people(normalized):
            return "quantidade de pessoas acima do permitido"

        return None

    def _is_paid_change_request(self, normalized_user_text: str) -> bool:
        has_change_intent = any(keyword in normalized_user_text for keyword in self._CANCEL_RESCHEDULE_KEYWORDS)
        if not has_change_intent:
            has_change_intent = bool(
                re.search(
                    r"\b(?:trocar|mudar|alterar)\b(?:\s+\w+){0,3}\s+\b(?:dia|data|horario|reserva)\b",
                    normalized_user_text,
                )
            )
        if not has_change_intent:
            return False
        return any(marker in normalized_user_text for marker in self._PAID_MARKERS)

    def _mentions_more_than_five_people(self, normalized_user_text: str) -> bool:
        explicit_over_limit_markers = {
            "mais de 5 pessoas",
            "mais que 5 pessoas",
            "acima de 5 pessoas",
        }
        if any(marker in normalized_user_text for marker in explicit_over_limit_markers):
            return True

        matches = re.findall(r"\b(\d{1,2})\b", normalized_user_text)
        numeric_values: list[int] = []
        for item in matches[:8]:
            try:
                numeric_values.append(int(item))
            except ValueError:
                continue

        if not numeric_values:
            return False

        has_people_tokens = any(
            token in normalized_user_text
            for token in {"pessoa", "pessoas", "equipe", "gente", "integrante", "membro"}
        )
        if has_people_tokens and any(value >= 6 for value in numeric_values):
            return True

        group_size_patterns = (
            r"\b(?:somos|seremos|vamos|iremos|estaremos|grupo de|equipe com|time com)\s*(?:em\s*)?(\d{1,2})\b",
            r"\b(\d{1,2})\s*(?:integrantes?|membros?)\b",
        )
        for pattern in group_size_patterns:
            for raw_value in re.findall(pattern, normalized_user_text):
                try:
                    value = int(raw_value)
                except ValueError:
                    continue
                if value >= 6:
                    return True
        return False


    def _build_identity_reply(self, user_text: str, key_memories: list[dict[str, Any]]) -> str | None:
        normalized = self._normalize_for_quality(user_text)
        if self._is_self_identity_question(normalized):
            return "Eu sou o Agente FC VIP. Posso te ajudar com atendimento, horarios e agendamento."

        if self._is_user_identity_question(normalized):
            customer_name = self._memory_lookup_raw(key_memories, "nome_cliente")
            if customer_name:
                return (
                    f"Voce e {customer_name}. "
                    "Se quiser, ja continuo o atendimento e vejo a melhor opcao para seu agendamento."
                )
            return (
                "Ainda nao tenho seu nome salvo com seguranca. "
                "Se quiser, me diga no formato 'meu nome e ...' que eu guardo para o atendimento."
            )
        return None

    def _is_self_identity_question(self, normalized_user_text: str) -> bool:
        markers = {
            "quem e voce",
            "qual seu nome",
            "seu nome",
            "voce e quem",
        }
        return any(marker in normalized_user_text for marker in markers)

    def _is_user_identity_question(self, normalized_user_text: str) -> bool:
        markers = {
            "quem sou eu",
            "qual meu nome",
            "sabe meu nome",
            "lembra meu nome",
        }
        return any(marker in normalized_user_text for marker in markers)

    def _sanitize_identity_hallucination(self, reply_text: str) -> str:
        normalized = self._normalize_for_quality(reply_text)
        banned_tokens = {"watson", "claude", "anthropic", "openai"}
        if any(token in normalized for token in banned_tokens):
            return "Eu sou o Agente FC VIP. Posso te ajudar com atendimento, horarios e agendamento."
        return reply_text

    def _sanitize_low_quality_reply(self, *, user_text: str, reply_text: str) -> str:
        normalized_reply = self._normalize_for_quality(reply_text)
        if (
            self._normalize_for_quality(self._CLOSING_PHRASE) in normalized_reply
            and not self._should_close_conversation(user_text)
        ):
            return (
                "Sou o Agente FC VIP e posso te ajudar com estrutura, valores e agendamento do estudio. "
                "Me diga como posso ajudar."
            )

        if not any(marker in normalized_reply for marker in self._LOW_QUALITY_MARKERS):
            return reply_text

        normalized_user = self._normalize_for_quality(user_text)
        asks_values = any(keyword in normalized_user for keyword in self._VALUE_KEYWORDS)
        asks_schedule = self._is_explicit_schedule_request(user_text)
        if asks_values or asks_schedule:
            return (
                "Para consultar pacotes, valores e disponibilidade, usamos o site oficial da FC VIP. "
                "Posso te orientar no agendamento por la."
            )
        return (
            "Eu sou o Agente FC VIP e sigo focado no atendimento do estudio. "
            "Posso te ajudar com estrutura, regras de uso e agendamento."
        )

    def _apply_domain_policy_guards(self, *, user_text: str, reply_text: str) -> str:
        normalized_user = self._normalize_for_quality(user_text)
        normalized_reply = self._normalize_for_quality(reply_text)

        if self._is_location_question(normalized_user) and not self._has_official_location_reference(normalized_reply):
            return self._build_location_policy_reply()

        if self._is_audio_question(normalized_user) and not self._is_audio_policy_compliant(normalized_reply):
            return self._build_audio_policy_reply()

        return reply_text

    def _is_location_question(self, normalized_user_text: str) -> bool:
        return any(keyword in normalized_user_text for keyword in self._LOCATION_TOPIC_KEYWORDS)

    def _has_official_location_reference(self, normalized_reply_text: str) -> bool:
        has_primary = any(token in normalized_reply_text for token in self._LOCATION_OFFICIAL_PRIMARY_MARKERS)
        has_context = any(token in normalized_reply_text for token in self._LOCATION_OFFICIAL_CONTEXT_MARKERS)
        return has_primary and has_context

    def _build_location_policy_reply(self) -> str:
        return (
            "O estudio fica na Rua Corifeu Marques, 32 - Jardim Amalia, Volta Redonda/RJ. "
            "O estacionamento e na via publica (rua) e o acesso ao estudio e por escadas."
        )

    def _is_audio_question(self, normalized_user_text: str) -> bool:
        return any(keyword in normalized_user_text for keyword in self._AUDIO_TOPIC_KEYWORDS)

    def _is_audio_policy_compliant(self, normalized_reply_text: str) -> bool:
        has_topic = "audio" in normalized_reply_text or "microfone" in normalized_reply_text
        has_negative_constraint = any(marker in normalized_reply_text for marker in self._AUDIO_NEGATIVE_MARKERS)
        has_policy_context = any(marker in normalized_reply_text for marker in self._AUDIO_POLICY_CONTEXT_MARKERS)
        return has_topic and has_negative_constraint and has_policy_context

    def _build_audio_policy_reply(self) -> str:
        return (
            "Atualmente a FC VIP nao oferece equipamentos de audio "
            "(microfones, lapela, interface, boom ou mesa de som). "
            "Trabalhamos apenas com estrutura fotografica e iluminacao."
        )

    def _extract_reply_text(self, body: Any) -> str:
        if isinstance(body, dict):
            message = body.get("message")
            if isinstance(message, dict):
                content = str(message.get("content") or "").strip()
                if content:
                    return content[:1500]
        return ""
