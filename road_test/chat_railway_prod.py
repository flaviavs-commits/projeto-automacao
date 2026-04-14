from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from hmac import new as hmac_new
from typing import Any

import httpx


DEFAULT_BASE_URL = "https://projeto-automacao-production.up.railway.app"
DEFAULT_WA_ID = "5511999999999"
DEFAULT_PROFILE_NAME = "Railway CLI"
DEFAULT_PHONE_NUMBER_ID = ""


@dataclass
class ReplyResult:
    external_message_id: str
    inbound_message_id: str
    outbound_message_id: str
    reply_text: str
    llm_status: str
    llm_model: str
    dispatch_status: str
    request_latency_seconds: float


def _build_external_message_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    suffix = uuid.uuid4().hex[:8]
    return f"wamid.prod.cli.{stamp}.{suffix}"


def _build_webhook_payload(
    *,
    wa_id: str,
    profile_name: str,
    external_message_id: str,
    user_text: str,
    phone_number_id: str,
) -> dict[str, Any]:
    value_payload: dict[str, Any] = {
        "messaging_product": "whatsapp",
        "contacts": [
            {
                "wa_id": wa_id,
                "profile": {"name": profile_name},
            }
        ],
        "messages": [
            {
                "from": wa_id,
                "id": external_message_id,
                "type": "text",
                "text": {"body": user_text},
            }
        ],
    }
    if phone_number_id:
        value_payload["metadata"] = {"phone_number_id": phone_number_id}

    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA123",
                "time": 1710000000,
                "changes": [
                    {
                        "field": "messages",
                        "value": value_payload,
                    }
                ],
            }
        ],
    }


def _list_messages(client: httpx.Client, *, base_url: str) -> list[dict[str, Any]]:
    response = client.get(f"{base_url.rstrip('/')}/messages")
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise RuntimeError("invalid_messages_payload")
    return payload


def _find_inbound_by_external_id(messages: list[dict[str, Any]], external_message_id: str) -> dict[str, Any] | None:
    for message in messages:
        if str(message.get("external_message_id") or "").strip() == external_message_id:
            return message
    return None


def _find_outbound_by_source_message_id(messages: list[dict[str, Any]], source_message_id: str) -> dict[str, Any] | None:
    for message in messages:
        raw_payload = message.get("raw_payload")
        if not isinstance(raw_payload, dict):
            continue
        if str(raw_payload.get("source_message_id") or "").strip() == source_message_id:
            return message
    return None


def send_message_and_wait_reply(
    *,
    client: httpx.Client,
    base_url: str,
    wa_id: str,
    profile_name: str,
    phone_number_id: str,
    app_secret: str,
    user_text: str,
    timeout_seconds: int,
    poll_interval_seconds: float,
) -> ReplyResult:
    started_at = time.time()
    external_message_id = _build_external_message_id()
    payload = _build_webhook_payload(
        wa_id=wa_id,
        profile_name=profile_name,
        external_message_id=external_message_id,
        user_text=user_text,
        phone_number_id=phone_number_id,
    )

    headers: dict[str, str] = {"Content-Type": "application/json"}
    body_text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if app_secret:
        digest = hmac_new(app_secret.encode("utf-8"), body_text.encode("utf-8"), sha256).hexdigest()
        headers["X-Hub-Signature-256"] = f"sha256={digest}"
    webhook_response = client.post(
        f"{base_url.rstrip('/')}/webhooks/meta",
        content=body_text.encode("utf-8"),
        headers=headers,
    )
    if webhook_response.status_code != 202:
        detail: str
        try:
            detail = json.dumps(webhook_response.json(), ensure_ascii=True)
        except Exception:  # noqa: BLE001
            detail = webhook_response.text
        if webhook_response.status_code == 401 and "Invalid Meta signature" in detail:
            raise RuntimeError(
                "webhook_failed status=401 invalid_meta_signature "
                "(use --app-secret or configure META_APP_SECRET/INSTAGRAM_APP_SECRET local env)"
            )
        raise RuntimeError(f"webhook_failed status={webhook_response.status_code} detail={detail[:500]}")

    deadline = time.time() + max(5, timeout_seconds)
    inbound_message_id = ""
    while time.time() < deadline:
        messages = _list_messages(client, base_url=base_url)
        inbound = _find_inbound_by_external_id(messages, external_message_id)
        if inbound is None:
            time.sleep(max(0.5, poll_interval_seconds))
            continue

        inbound_message_id = str(inbound.get("id") or "").strip()
        if not inbound_message_id:
            time.sleep(max(0.5, poll_interval_seconds))
            continue

        outbound = _find_outbound_by_source_message_id(messages, inbound_message_id)
        if outbound is None:
            time.sleep(max(0.5, poll_interval_seconds))
            continue

        raw_payload = outbound.get("raw_payload") if isinstance(outbound.get("raw_payload"), dict) else {}
        dispatch_result = raw_payload.get("dispatch_result") if isinstance(raw_payload, dict) else {}
        dispatch_status = ""
        if isinstance(dispatch_result, dict):
            dispatch_status = str(dispatch_result.get("status") or "")

        return ReplyResult(
            external_message_id=external_message_id,
            inbound_message_id=inbound_message_id,
            outbound_message_id=str(outbound.get("id") or ""),
            reply_text=str(outbound.get("text_content") or "").strip(),
            llm_status=str(raw_payload.get("llm_status") or ""),
            llm_model=str(raw_payload.get("llm_model") or ""),
            dispatch_status=dispatch_status,
            request_latency_seconds=round(time.time() - started_at, 3),
        )

    raise RuntimeError(
        f"timeout_waiting_reply external_message_id={external_message_id} inbound_message_id={inbound_message_id}"
    )


def _run_once(args: argparse.Namespace) -> int:
    user_text = (args.once or "").strip()
    if not user_text:
        raise RuntimeError("--once requires non-empty message")

    with httpx.Client(timeout=max(15.0, float(args.http_timeout)), trust_env=bool(args.trust_env)) as client:
        result = send_message_and_wait_reply(
            client=client,
            base_url=args.base_url,
            wa_id=args.wa_id,
            profile_name=args.profile_name,
            phone_number_id=str(args.phone_number_id or "").strip(),
            app_secret=str(args.app_secret or "").strip(),
            user_text=user_text,
            timeout_seconds=args.reply_timeout,
            poll_interval_seconds=args.poll_interval,
        )

    print(json.dumps(result.__dict__, ensure_ascii=False))
    return 0


def _run_interactive(args: argparse.Namespace) -> int:
    print("=== Chat Producao Railway ===")
    print("Comandos: /exit para sair")
    print(f"Base URL: {args.base_url}")
    print(f"WA ID: {args.wa_id}")
    if str(args.phone_number_id or "").strip():
        print(f"Phone Number ID: {args.phone_number_id}")
    if str(args.app_secret or "").strip():
        print("App Secret: provided")
    print("")

    with httpx.Client(timeout=max(15.0, float(args.http_timeout)), trust_env=bool(args.trust_env)) as client:
        while True:
            user_text = input("Voce: ").strip()
            if not user_text:
                continue
            if user_text.lower() in {"/exit", "/quit"}:
                break

            try:
                result = send_message_and_wait_reply(
                    client=client,
                    base_url=args.base_url,
                    wa_id=args.wa_id,
                    profile_name=args.profile_name,
                    phone_number_id=str(args.phone_number_id or "").strip(),
                    app_secret=str(args.app_secret or "").strip(),
                    user_text=user_text,
                    timeout_seconds=args.reply_timeout,
                    poll_interval_seconds=args.poll_interval,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"Erro: {exc}")
                continue

            print(f"Atendente: {result.reply_text}")
            print(
                "Meta: "
                f"model={result.llm_model} "
                f"llm_status={result.llm_status} "
                f"dispatch_status={result.dispatch_status or 'n/a'}"
            )
            print("")

    print("Encerrado.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Conversa com o LLM em producao via webhook Railway (API + worker + llm-runtime)."
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Base URL publica da API em producao")
    parser.add_argument("--wa-id", default=DEFAULT_WA_ID, help="Identidade WhatsApp usada no payload")
    parser.add_argument("--profile-name", default=DEFAULT_PROFILE_NAME, help="Nome de perfil no payload")
    parser.add_argument(
        "--phone-number-id",
        default=DEFAULT_PHONE_NUMBER_ID,
        help="Phone Number ID Meta opcional para melhorar dispatch outbound",
    )
    parser.add_argument(
        "--app-secret",
        default=(os.getenv("META_APP_SECRET", "").strip() or os.getenv("INSTAGRAM_APP_SECRET", "").strip()),
        help="App Secret Meta para assinar webhook de teste (X-Hub-Signature-256)",
    )
    parser.add_argument(
        "--reply-timeout",
        type=int,
        default=90,
        help="Timeout (segundos) para esperar a mensagem outbound",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=2.0,
        help="Intervalo de polling de mensagens (segundos)",
    )
    parser.add_argument(
        "--http-timeout",
        type=float,
        default=40.0,
        help="Timeout de requisicao HTTP (segundos)",
    )
    parser.add_argument(
        "--once",
        default="",
        help="Executa uma unica pergunta e sai, retornando JSON",
    )
    parser.add_argument(
        "--trust-env",
        action="store_true",
        help="Usa variaveis de proxy do ambiente (HTTP_PROXY/HTTPS_PROXY).",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.once:
            return _run_once(args)
        return _run_interactive(args)
    except httpx.ConnectError as exc:
        message = str(exc)
        if "127.0.0.1" in message and "10061" in message:
            print(
                "Erro de conexao. O ambiente parece estar forçando proxy local invalido "
                "(127.0.0.1). Rode sem proxy (padrao) ou ajuste variaveis HTTP_PROXY/HTTPS_PROXY."
            )
            return 2
        print(f"Erro de conexao HTTP: {message}")
        return 2
    except httpx.HTTPError as exc:
        print(f"Erro HTTP: {exc}")
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"Falha: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
