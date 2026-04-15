from __future__ import annotations

import re
import sys
import unicodedata
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
        "trocar horário",
        "mudar horario",
        "mudar horário",
    }
    _PAID_MARKERS = {
        "ja paguei",
        "já paguei",
        "pago",
        "pagamento",
        "paguei",
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
        "nao tenho acesso",
        "nao posso acessar",
        "nao posso ajudar com isso",
        "nao consigo ajudar com isso",
    }
    _ABUSIVE_MARKERS = {
        "vai tomar no cu",
        "filho da puta",
        "fdp",
        "lixo imundo",
        "arrombado",
        "otario",
        "otario",
        "idiota",
        "porra",
        "caralho",
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

        if self._should_close_conversation(cleaned_user_text):
            requested_model = str(model_override or settings.llm_model).strip() or "unknown"
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

        escalation_reason = self._detect_escalation_reason(cleaned_user_text)
        if escalation_reason:
            requested_model = str(model_override or settings.llm_model).strip() or "unknown"
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
        normalized_user = self._normalize_for_quality(cleaned_user_text)

        if self._contains_abusive_language(normalized_user):
            requested_model = str(model_override or settings.llm_model).strip() or "unknown"
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
                reply_text=(
                    "Vamos manter o atendimento de forma respeitosa. "
                    "Posso te ajudar com locacao do estudio, estrutura, valores e agendamento pelo site."
                ),
            )

        if cta_reason == "agendar":
            requested_model = str(model_override or settings.llm_model).strip() or "unknown"
            schedule_reply = (
                "O agendamento e feito totalmente pelo nosso site, mas ele e super intuitivo, "
                "tenho certeza que voce conseguira agendar de forma facil e simples! "
                "Nao consigo confirmar horario manualmente por aqui."
            )
            reply_text = self._ensure_final_cta(schedule_reply, cta_link, cta_reason)
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
        reply_text = self._ensure_final_cta(sanitized_reply, cta_link, cta_reason)

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
        knowledge_text = self._load_knowledge_text()
        context_window_size = settings.llm_effective_context_messages
        tolerated_offtopic_turns = max(1, int(settings.llm_offtopic_tolerance_turns))

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
                system_prompt += "\n\nMemorias-chave do cliente:\n" + "\n".join(compact_memories[:25])

        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        recent_context_messages = context_messages[-context_window_size:]
        for item in recent_context_messages:
            role = str(item.get("role") or "").strip().lower()
            content = " ".join(str(item.get("text") or "").split()).strip()
            if role not in {"user", "assistant"} or not content:
                continue
            messages.append({"role": role, "content": content[:1200]})

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

        normalized_user = self._normalize_for_quality(user_text)
        critical_intent = any(keyword in normalized_user for keyword in self._QUALITY_CRITICAL_INTENT_KEYWORDS)
        if critical_intent and len(compact_reply) < (min_chars + 30):
            return "critical_intent_low_depth"
        return None

    def _normalize_for_quality(self, value: str) -> str:
        lowered = str(value or "").lower()
        ascii_value = unicodedata.normalize("NFKD", lowered).encode("ascii", "ignore").decode("ascii")
        return " ".join(ascii_value.split())

    def _load_knowledge_text(self) -> str:
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
            try:
                content = file_path.read_text(encoding="utf-8")
            except Exception:  # noqa: BLE001
                continue
            cleaned = content.replace("\r\n", "\n").strip()
            if cleaned:
                return cleaned[:12000]
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

        if asked_schedule:
            if customer_status == "antigo":
                return self._LINK_OLD_SCHEDULE, "agendar"
            return self._LINK_NEW_SCHEDULE, "agendar"

        if asked_tour:
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

    def _detect_escalation_reason(self, user_text: str) -> str | None:
        normalized = self._normalize_for_quality(user_text)
        if not normalized:
            return None

        if any(keyword in normalized for keyword in self._RISK_CONTENT_KEYWORDS):
            return "uso de itens/efeitos que exigem avaliacao (ex.: sujeira, liquidos, fumaca, glitter, fogo ou animais)"

        if any(keyword in normalized for keyword in self._CANCEL_RESCHEDULE_KEYWORDS) and any(
            marker in normalized for marker in self._PAID_MARKERS
        ):
            return "cancelamento/reagendamento de horario ja pago"

        if self._mentions_more_than_five_people(normalized):
            return "quantidade de pessoas acima do permitido"

        return None

    def _mentions_more_than_five_people(self, normalized_user_text: str) -> bool:
        if not any(token in normalized_user_text for token in {"pessoa", "pessoas", "equipe", "gente"}):
            return False
        matches = re.findall(r"\b(\d{1,2})\b", normalized_user_text)
        for item in matches[:6]:
            try:
                value = int(item)
            except ValueError:
                continue
            if value >= 6:
                return True
        return False

    def _contains_abusive_language(self, normalized_user_text: str) -> bool:
        if not normalized_user_text:
            return False
        return any(marker in normalized_user_text for marker in self._ABUSIVE_MARKERS)

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

    def _extract_reply_text(self, body: Any) -> str:
        if isinstance(body, dict):
            message = body.get("message")
            if isinstance(message, dict):
                content = str(message.get("content") or "").strip()
                if content:
                    return content[:1500]
        return ""
