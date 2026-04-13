from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import settings
from app.services.contact_memory_service import ContactMemoryService
from app.services.llm_reply_service import LLMReplyService

VALID_PLATFORMS = {"whatsapp", "instagram", "facebook"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_platform(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"ig", "insta", "instagram_dm"}:
        return "instagram"
    if normalized in {"messenger", "facebook_messenger", "fb"}:
        return "facebook"
    return normalized


def _normalize_identity(platform: str, value: str) -> str:
    raw = str(value or "").strip()
    if platform == "whatsapp":
        digits = "".join(ch for ch in raw if ch.isdigit())
        return digits or raw
    return raw.lower()


def _available_models() -> list[str]:
    models = settings.llm_test_models_list[:]
    if settings.llm_model and settings.llm_model not in models:
        models.insert(0, settings.llm_model)
    return models


class RoadTestStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.state = self._load()

    def _load(self) -> dict:
        if not self.path.exists():
            return {"customers": {}}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {"customers": {}}

    def save(self) -> None:
        self.path.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")

    def _iter_customers(self):
        return self.state.setdefault("customers", {}).items()

    def resolve_customer(self, *, platform: str, identity: str, display_name: str | None) -> tuple[str, dict]:
        normalized_platform = _normalize_platform(platform)
        normalized_identity = _normalize_identity(normalized_platform, identity)

        for customer_id, payload in self._iter_customers():
            identities = payload.setdefault("identities", [])
            for item in identities:
                if item.get("platform") == normalized_platform and item.get("value") == normalized_identity:
                    if display_name and not str(payload.get("display_name") or "").strip():
                        payload["display_name"] = display_name
                    payload["updated_at"] = _now_iso()
                    return customer_id, payload

        customer_id = f"CUST-{uuid4().hex[:12].upper()}"
        payload = {
            "customer_id": customer_id,
            "display_name": display_name or "",
            "identities": [{"platform": normalized_platform, "value": normalized_identity}],
            "key_memories": {},
            "history": [],
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        self.state.setdefault("customers", {})[customer_id] = payload
        return customer_id, payload

    def link_identity(self, *, customer_id: str, platform: str, identity: str) -> tuple[bool, str]:
        payload = self.state.setdefault("customers", {}).get(customer_id)
        if payload is None:
            return False, "Cliente nao encontrado."

        normalized_platform = _normalize_platform(platform)
        normalized_identity = _normalize_identity(normalized_platform, identity)
        if not normalized_identity:
            return False, "Identificador invalido."

        for existing_customer_id, existing_payload in self._iter_customers():
            for item in existing_payload.get("identities", []):
                if (
                    item.get("platform") == normalized_platform
                    and item.get("value") == normalized_identity
                    and existing_customer_id != customer_id
                ):
                    return False, f"Identidade ja vinculada ao cliente {existing_customer_id}."

        for item in payload.setdefault("identities", []):
            if item.get("platform") == normalized_platform and item.get("value") == normalized_identity:
                return True, "Identidade ja estava vinculada."

        payload["identities"].append({"platform": normalized_platform, "value": normalized_identity})
        payload["updated_at"] = _now_iso()
        return True, "Identidade vinculada ao cliente atual."


def _default_model() -> str:
    models = _available_models()
    if not models:
        return settings.llm_model
    if settings.llm_model in models:
        return settings.llm_model
    return models[0]


def _show_help() -> None:
    print("\nComandos:")
    print("/help                mostra ajuda")
    print("/exit                encerra")
    print("/mem                 lista memorias-chave")
    print("/who                 mostra cliente identificado")
    print("/models              lista modelos disponiveis")
    print("/use <indice|nome>   troca modelo")
    print("/link <canal> <id>   vincula nova identidade ao mesmo cliente")


def main() -> None:
    storage_dir = Path(settings.local_storage_path)
    if not storage_dir.is_absolute():
        storage_dir = Path(__file__).resolve().parents[1] / storage_dir
    store = RoadTestStore(storage_dir / "road_test" / "chat_test_profiles.json")

    print("=== Road Test Chat - Estudio ===")
    print("Este chat e isolado do fluxo real de producao.")
    print("Regras: dominio travado em estudio/agendamento e agendamento sempre no site.\n")

    while True:
        platform = _normalize_platform(input("Canal (whatsapp/instagram/facebook): ").strip())
        if platform in VALID_PLATFORMS:
            break
        print("Canal invalido. Digite novamente: whatsapp, instagram ou facebook.")

    while True:
        identity = input("Identificador do cliente (telefone/id): ").strip()
        if identity:
            break
        print("Identificador obrigatorio. Digite novamente.")

    display_name = input("Nome do cliente (opcional): ").strip()

    customer_id, customer_payload = store.resolve_customer(
        platform=platform,
        identity=identity,
        display_name=display_name or None,
    )
    selected_model = _default_model()
    memory_service = ContactMemoryService()
    llm_service = LLMReplyService()

    print(f"\nCliente identificado: {customer_id}")
    if customer_payload.get("display_name"):
        print(f"Nome: {customer_payload['display_name']}")
    print(f"Modelo ativo: {selected_model}")
    print("Selecao manual de modelo no inicio foi removida para deixar o fluxo mais rapido.")
    _show_help()

    max_history = max(4, settings.llm_context_messages)

    while True:
        user_text = input("\nVoce: ").strip()
        if not user_text:
            continue

        if user_text.lower() in {"/exit", "/quit"}:
            break
        if user_text.lower() == "/help":
            _show_help()
            continue
        if user_text.lower() == "/who":
            print(f"customer_id: {customer_id}")
            print(f"nome: {customer_payload.get('display_name') or '(nao informado)'}")
            print(f"identidades: {customer_payload.get('identities')}")
            continue
        if user_text.lower() == "/mem":
            memories = customer_payload.get("key_memories", {})
            if not memories:
                print("Sem memorias-chave.")
            else:
                for key, value in memories.items():
                    print(f"- {key}: {value.get('value')} (updated_at={value.get('updated_at')})")
            continue
        if user_text.lower() == "/models":
            for index, model in enumerate(_available_models(), start=1):
                marker = " <= ativo" if model == selected_model else ""
                print(f"{index}. {model}{marker}")
            continue
        if user_text.lower().startswith("/use "):
            arg = user_text[5:].strip()
            models = _available_models()
            if arg.isdigit():
                idx = int(arg)
                if 1 <= idx <= len(models):
                    selected_model = models[idx - 1]
                    print(f"Modelo ativo: {selected_model}")
                    continue
            if arg in models:
                selected_model = arg
                print(f"Modelo ativo: {selected_model}")
                continue
            print("Modelo invalido.")
            continue
        if user_text.lower().startswith("/link "):
            parts = user_text.split(maxsplit=2)
            if len(parts) < 3:
                print("Uso: /link <canal> <identificador>")
                continue
            ok, detail = store.link_identity(customer_id=customer_id, platform=parts[1], identity=parts[2])
            if ok:
                print(detail)
                store.save()
            else:
                print(detail)
            continue

        analyzed = memory_service.analyze_text(user_text)
        if analyzed["status"] == "candidate_found":
            for candidate in analyzed["candidates"]:
                key = candidate["memory_key"]
                customer_payload.setdefault("key_memories", {})[key] = {
                    "value": candidate["memory_value"],
                    "importance": candidate["importance"],
                    "confidence": candidate["confidence"],
                    "updated_at": _now_iso(),
                }

        history = customer_payload.setdefault("history", [])
        context_messages = history[-max_history:]
        key_memories = [
            {"key": key, "value": value.get("value")}
            for key, value in customer_payload.get("key_memories", {}).items()
        ]

        llm_result = llm_service.generate_reply(
            user_text=user_text,
            context_messages=context_messages,
            key_memories=key_memories,
            model_override=selected_model,
        )
        status = str(llm_result.get("status") or "")
        reply_text = str(llm_result.get("reply_text") or "").strip()

        if status not in {"completed", "blocked_out_of_scope"} or not reply_text:
            detail = str(llm_result.get("detail") or "").strip()
            diagnostic = f" Detalhe tecnico: {detail}" if detail else ""
            reply_text = (
                "Nao consegui falar com o motor de IA local agora."
                " Inicie o runtime com: road_test\\iniciar_leve_local.cmd"
                f"{diagnostic}"
            )

        print(f"Atendente: {reply_text}")

        history.append({"role": "user", "text": user_text, "created_at": _now_iso()})
        history.append({"role": "assistant", "text": reply_text, "created_at": _now_iso()})
        customer_payload["history"] = history[-100:]
        customer_payload["updated_at"] = _now_iso()
        store.save()

    store.save()
    print("\nEncerrado.")


if __name__ == "__main__":
    main()

