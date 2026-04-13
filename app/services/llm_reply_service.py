from __future__ import annotations

import sys
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

    _INTENT_SCHEDULE_KEYWORDS = {
        "agendar",
        "agendamento",
        "reserva",
        "marcar",
        "data",
        "horario",
        "disponibilidade",
        "agenda",
    }
    _INTENT_DISCOVER_KEYWORDS = {
        "conhecer",
        "como funciona",
        "quero conhecer",
        "primeira vez",
        "informacoes",
        "estrutura",
        "onde fica",
        "endereco",
        "localizacao",
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
        mandatory_link = self._select_mandatory_link(cleaned_user_text, context_messages, key_memories)

        model_name = str(model_override or settings.llm_model).strip()
        if not model_name:
            return self.invalid_payload(action, "model is required")

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

        url = settings.llm_base_url.rstrip("/") + "/api/chat"
        result = self._request(
            "POST",
            url,
            json_payload=payload,
            timeout_seconds=max(5.0, float(settings.llm_timeout_seconds)),
        )
        if result.get("status") != "ok":
            return result

        body = result.get("body")
        reply_text = self._extract_reply_text(body)
        if not reply_text:
            return self.request_failed(action, "empty_llm_response")
        reply_text = self._ensure_final_cta(reply_text, mandatory_link)

        return ExternalServiceResult(
            status="completed",
            service=self.service_name,
            action=action,
            model=model_name,
            routing_link=mandatory_link,
            reply_text=reply_text,
        )

    def _build_messages(
        self,
        *,
        user_text: str,
        context_messages: list[dict[str, Any]],
        key_memories: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        knowledge_text = self._load_knowledge_text()
        system_prompt = (
            "Voce e o atendente comercial virtual da FC VIP (estudio de fotografia e video). "
            "Fale somente sobre locacao do estudio, horarios, estrutura geral, valores quando perguntado, "
            "e beneficios do membro VIP. "
            "Tom obrigatorio: acolhedor, profissional, educado, objetivo e levemente persuasivo. "
            "Nunca use linguagem informal excessiva. "
            "Nunca negocie valores, nunca feche contrato, nunca prometa disponibilidade, "
            "nunca prometa equipamento especifico e nunca ofereca suporte tecnico avancado. "
            "Se o cliente desviar de assunto, reconheca em 1 frase e redirecione imediatamente para estudio/agendamento. "
            "Sempre tente coletar: nome, tipo de projeto (foto/video), duracao, numero de pessoas e se ja conhece o estudio. "
            "Se o cliente nao quiser responder, continue normalmente. "
            "Se detectar cliente irritado, negociacao fora do padrao, parceria, evento grande, reclamacao "
            "ou duvida fora da base, ofereca atendimento humano. "
            "Nunca confirme horario manualmente; use somente o link oficial. "
            "Se perguntarem seu nome, responda exatamente: 'Eu sou o Agente FC VIP'. "
            "Toda resposta final deve ter CTA claro e link oficial adequado."
        )
        if knowledge_text:
            system_prompt += "\n\nBase oficial FC VIP:\n" + knowledge_text
        if key_memories:
            compact_memories = [
                f"- {str(item.get('key') or '').strip()}: {str(item.get('value') or '').strip()}"
                for item in key_memories
                if str(item.get("key") or "").strip() and str(item.get("value") or "").strip()
            ]
            if compact_memories:
                system_prompt += "\n\nMemorias-chave do cliente:\n" + "\n".join(compact_memories[:20])

        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        for item in context_messages:
            role = str(item.get("role") or "").strip().lower()
            content = " ".join(str(item.get("text") or "").split()).strip()
            if role not in {"user", "assistant"} or not content:
                continue
            messages.append({"role": role, "content": content[:1200]})

        messages.append({"role": "user", "content": user_text})
        return messages

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
        for item in key_memories:
            if str(item.get("key") or "").strip() == key:
                return str(item.get("value") or "").strip().lower()
        return ""

    def _select_mandatory_link(
        self,
        user_text: str,
        context_messages: list[dict[str, Any]],
        key_memories: list[dict[str, Any]],
    ) -> str:
        haystack = self._normalize(
            " ".join(
                [
                    user_text,
                    " ".join(str(item.get("text") or "") for item in context_messages[-4:]),
                ]
            )
        )
        customer_status = ""
        memory_customer_status = self._memory_lookup(key_memories, "cliente_status")
        memory_knows_studio = self._memory_lookup(key_memories, "ja_conhece_estudio")
        if memory_customer_status in {"novo", "antigo"}:
            customer_status = memory_customer_status
        elif memory_knows_studio in {"sim", "nao"}:
            customer_status = "antigo" if memory_knows_studio == "sim" else "novo"

        if any(marker in haystack for marker in self._OLD_CUSTOMER_MARKERS):
            customer_status = "antigo"
        if any(marker in haystack for marker in self._NEW_CUSTOMER_MARKERS):
            customer_status = "novo"

        intent = "indefinido"
        if any(keyword in haystack for keyword in self._INTENT_SCHEDULE_KEYWORDS):
            intent = "agendar"
        elif any(keyword in haystack for keyword in self._INTENT_DISCOVER_KEYWORDS):
            intent = "conhecer"

        if intent == "agendar":
            if customer_status == "antigo":
                return self._LINK_OLD_SCHEDULE
            return self._LINK_NEW_SCHEDULE
        if intent == "conhecer":
            return self._LINK_NEW_DISCOVER

        if customer_status == "antigo":
            return self._LINK_OLD_SCHEDULE
        return self._LINK_NEW_DISCOVER

    def _ensure_final_cta(self, reply_text: str, mandatory_link: str) -> str:
        compact = " ".join(str(reply_text or "").split()).strip()
        if not compact:
            compact = "Posso te ajudar com o atendimento do estudio FC VIP."

        for known_link in {
            self._LINK_NEW_DISCOVER,
            self._LINK_NEW_SCHEDULE,
            self._LINK_OLD_SCHEDULE,
        }:
            compact = compact.replace(known_link, mandatory_link)

        current_link = mandatory_link

        if current_link == self._LINK_OLD_SCHEDULE:
            cta = f"Para garantir seu horario, acesse agora: {self._LINK_OLD_SCHEDULE}"
        elif current_link == self._LINK_NEW_SCHEDULE:
            cta = f"Para garantir seu horario, acesse agora: {self._LINK_NEW_SCHEDULE}"
        else:
            cta = f"Para conhecer melhor o estudio e seguir com o atendimento, acesse: {self._LINK_NEW_DISCOVER}"

        if compact.endswith(cta):
            return compact
        return f"{compact}\n\n{cta}"

    def _extract_reply_text(self, body: Any) -> str:
        if isinstance(body, dict):
            message = body.get("message")
            if isinstance(message, dict):
                content = str(message.get("content") or "").strip()
                if content:
                    return content[:1500]
        return ""
