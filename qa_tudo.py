from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import webbrowser
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Iterator
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import ProxyHandler, Request, build_opener


BASE_DIR = Path(__file__).resolve().parent
ROOT = Path.cwd() if getattr(sys, "frozen", False) else BASE_DIR
DEFAULT_BASE_URL = "https://projeto-automacao-production.up.railway.app"
REPORT_PATH = ROOT / "qa_report_latest.json"
_PROXYLESS_HTTP_OPENER = build_opener(ProxyHandler({}))

EXPECTED_ROUTES = [
    "/",
    "/health",
    "/dashboard",
    "/contacts",
    "/conversations",
    "/messages",
    "/posts",
    "/analytics",
    "/oauth/meta/start",
    "/oauth/meta/callback",
    "/webhooks/meta",
]

REMOTE_ROUTES = [
    "/",
    "/health",
    "/dashboard",
    "/contacts",
    "/messages",
]

LOCAL_SMOKE_ROUTES = [
    "/",
    "/health",
    "/dashboard",
    "/contacts",
    "/conversations",
    "/messages",
    "/posts",
    "/analytics",
]

SAMPLE_WEBHOOK_PAYLOAD = {
    "object": "whatsapp_business_account",
    "entry": [
        {
            "id": "WABA123",
            "time": 1710000000,
            "changes": [
                {
                    "field": "messages",
                    "value": {
                        "messaging_product": "whatsapp",
                        "contacts": [
                            {
                                "wa_id": "5511999999999",
                                "profile": {"name": "QA Bot"},
                            }
                        ],
                        "messages": [
                            {
                                "from": "5511999999999",
                                "id": "wamid.qa.smoke.20260409",
                                "type": "text",
                                "text": {"body": "qa smoke test"},
                            }
                        ],
                    },
                }
            ],
        }
    ],
}

ROADMAP_ITEMS = [
    {
        "scope": "Proximas etapas",
        "name": "Link com redes (Meta/Instagram/TikTok/YouTube)",
        "status": "WIP",
        "details": "Trabalho em progresso",
    },
    {
        "scope": "Proximas etapas",
        "name": "Pipeline de resposta via LLM no worker",
        "status": "WIP",
        "details": "Trabalho em progresso",
    },
    {
        "scope": "Proximas etapas",
        "name": "Substituir stubs por integracoes reais",
        "status": "WIP",
        "details": "Trabalho em progresso",
    },
]


@dataclass
class CheckResult:
    scope: str
    name: str
    status: str
    details: str
    duration_ms: int


@dataclass(frozen=True)
class CheckSpec:
    scope: str
    name: str
    fn: Callable[[], tuple[str, str]]


@dataclass(frozen=True)
class RemoteRouteProbe:
    route: str
    status_code: int | None
    body: Any
    error: str | None
    unreachable: bool


@dataclass(frozen=True)
class LocalLogicHarness:
    app: Any
    session_factory: Any
    queue_calls: list[dict[str, Any]]


def _extract_first_match(patterns: list[str], text: str) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return str(match.group(1))
    return None


def _extract_error_code(details: str) -> str:
    http_code = _extract_first_match(
        [
            r"\bHTTP\s+(\d{3})\b",
            r"\bstatus(?:_code)?[=: ]+(\d{3})\b",
            r"\b(\d{3})\s+Unauthorized\b",
        ],
        details,
    )
    meta_code = _extract_first_match(
        [
            r'"code"\s*:\s*(\d+)',
            r"'code'\s*:\s*(\d+)",
            r"\bcode[=: ]+(\d+)\b",
        ],
        details,
    )
    subcode = _extract_first_match(
        [
            r'"error_subcode"\s*:\s*(\d+)',
            r'"subcode"\s*:\s*(\d+)',
            r"\bsubcode[=: ]+(\d+)\b",
        ],
        details,
    )

    parts: list[str] = []
    if http_code:
        parts.append(f"HTTP {http_code}")
    if meta_code and subcode:
        parts.append(f"META {meta_code}/{subcode}")
    elif meta_code:
        parts.append(f"META {meta_code}")
    return " | ".join(parts) if parts else "N/A"


def _extract_where(scope: str, name: str, details: str) -> str:
    route_match = re.search(r"\b(GET|POST|PUT|DELETE|PATCH)\s+(/[^\s\"']+)", details)
    if route_match:
        method = str(route_match.group(1)).upper()
        route = str(route_match.group(2))
        return f"{method} {route}"
    if "graph.facebook.com" in details.lower():
        return "Meta Graph API"
    if "railway" in details.lower():
        return "Railway CLI"
    return f"{scope} > {name}"


def _simple_error_explanation(details: str) -> tuple[str, str]:
    text = details.lower()

    if "131030" in text or "allowed list" in text:
        return (
            "A Meta recusou o envio porque esse numero destino nao esta liberado para teste.",
            "Numero do cliente nao foi adicionado na lista de destinatarios permitidos do WhatsApp Cloud API.",
        )
    if "instagram" in text and "inbound_count=0" in text:
        return (
            "Nao entrou nenhuma DM do Instagram no sistema no periodo validado.",
            "Webhook do Instagram nao esta assinando/entregando eventos de mensagens, ou permissao do app esta incompleta.",
        )
    if "meta_webhook_invalid_signature" in text or ("/webhooks/meta" in text and "401" in text):
        return (
            "A Meta tentou entregar evento, mas seu webhook recusou por assinatura invalida.",
            "App Secret diferente entre Meta App e variavel META_APP_SECRET no servidor.",
        )
    if "sem prova recente de entrada" in text or "inbound_status=warn" in text:
        return (
            "Nao houve evento recente de entrada para provar webhook ativo agora.",
            "Sem mensagem/teste recente no periodo, embora a configuracao possa estar correta.",
        )
    if "session has expired" in text or "error validating access token" in text or "subcode\": 463" in text:
        return (
            "A Meta recusou a chamada porque o token expirou.",
            "Token OAuth vencido; precisa renovar token e usar credencial persistida valida.",
        )
    if "requires pages_manage_metadata permission" in text or "permission" in text:
        return (
            "A chamada foi negada por falta de permissao.",
            "Escopo/permissao do app nao concedido (ex.: pages_manage_metadata).",
        )
    if "does not have the capability" in text:
        return (
            "O app nao tem recurso habilitado para essa API.",
            "Capability/produto de Instagram Messaging nao habilitado/aprovado para o app.",
        )
    if "could not resolve host" in text or "connection refused" in text or "timed out" in text:
        return (
            "Nao foi possivel conectar no servico externo.",
            "Problema de rede/DNS/firewall ou servico temporariamente indisponivel.",
        )
    if "redis" in text and "error" in text:
        return (
            "A fila Redis falhou ou ficou indisponivel.",
            "Credencial/host Redis invalido, ou indisponibilidade de rede.",
        )
    if "db" in text or "database" in text:
        return (
            "A conexao com banco de dados falhou.",
            "Banco indisponivel, URL incorreta ou timeout de conexao.",
        )
    return (
        "O teste encontrou um erro tecnico e o fluxo nao ficou confiavel.",
        "Falha nao classificada automaticamente; verificar detalhe tecnico bruto.",
    )


def _build_error_entry(scope: str, name: str, status: str, details: str) -> dict[str, str]:
    simple, likely = _simple_error_explanation(details)
    fbtrace = _extract_first_match([r'"fbtrace_id"\s*:\s*"([^"]+)"'], details) or ""
    technical = details.strip() or "Sem detalhe tecnico."
    if fbtrace and "fbtrace_id" not in technical:
        technical = f"{technical} | fbtrace_id={fbtrace}"
    return {
        "status": status,
        "scope": scope,
        "check_name": name,
        "where": _extract_where(scope, name, technical),
        "error_code": _extract_error_code(technical),
        "simple_explanation": simple,
        "most_likely_cause": likely,
        "technical_error": technical[:1800],
    }


def _derive_error_entries_from_checks(checks: list[dict[str, Any]]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for check in checks:
        status = str(check.get("status") or "")
        if status not in {"WARN", "FAIL"}:
            continue
        items.append(
            _build_error_entry(
                scope=str(check.get("scope") or "desconhecido"),
                name=str(check.get("name") or "check"),
                status=status,
                details=str(check.get("details") or ""),
            )
        )
    return items


def _derive_error_entries_from_results(results: list[CheckResult]) -> list[dict[str, str]]:
    checks = [
        {
            "scope": result.scope,
            "name": result.name,
            "status": result.status,
            "details": result.details,
        }
        for result in results
    ]
    return _derive_error_entries_from_checks(checks)


def _error_totals(errors: list[dict[str, str]]) -> dict[str, int]:
    totals = {"WARN": 0, "FAIL": 0}
    for item in errors:
        status = str(item.get("status") or "")
        if status in totals:
            totals[status] += 1
    return totals


def _build_plain_summary(
    totals: dict[str, int],
    errors: list[dict[str, str]],
) -> str:
    fail = int(totals.get("FAIL", 0))
    warn = int(totals.get("WARN", 0))
    passed = int(totals.get("PASS", 0))
    if fail == 0 and warn == 0:
        return (
            f"Ambiente saudavel: {passed} checks passaram e nao houve erros relevantes."
        )
    if errors:
        first = next((item for item in errors if item.get("status") == "FAIL"), errors[0])
        return (
            f"Existem problemas reais ({fail} falhas, {warn} alertas). "
            f"Principal agora: {first.get('simple_explanation')}"
        )
    return f"Existem problemas reais ({fail} falhas, {warn} alertas) e exigem correcao."


class DashboardState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state: dict[str, Any] = {
            "project": "bot-multiredes",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": None,
            "finished_at": None,
            "message": "Aguardando inicio do QA.",
            "plain_summary": "Ainda sem resultados. O QA vai explicar problemas em linguagem simples.",
            "checks": [],
            "roadmap": list(ROADMAP_ITEMS),
        }
        self._touch()

    def _touch(self) -> None:
        self._state["updated_at"] = datetime.now(timezone.utc).isoformat()

    def register_checks(self, checks: list[CheckSpec]) -> None:
        with self._lock:
            self._state["checks"] = [
                {
                    "scope": check.scope,
                    "name": check.name,
                    "status": "PENDING",
                    "details": "Aguardando execucao.",
                    "duration_ms": None,
                }
                for check in checks
            ]
            self._touch()

    def start_check(self, check: CheckSpec) -> None:
        with self._lock:
            for item in self._state["checks"]:
                if item["scope"] == check.scope and item["name"] == check.name:
                    item["status"] = "RUNNING"
                    item["details"] = "Verificando..."
                    item["duration_ms"] = None
                    break
            self._state["message"] = f"Verificando [{check.scope}] {check.name}"
            self._touch()

    def finish_check(self, result: CheckResult) -> None:
        with self._lock:
            for item in self._state["checks"]:
                if item["scope"] == result.scope and item["name"] == result.name:
                    item["status"] = result.status
                    item["details"] = result.details
                    item["duration_ms"] = result.duration_ms
                    break
            self._state["message"] = (
                f"Ultimo check: [{result.scope}] {result.name} -> {result.status}"
            )
            self._touch()

    def finalize(self) -> None:
        with self._lock:
            self._state["finished_at"] = datetime.now(timezone.utc).isoformat()
            self._state["message"] = "Execucao do QA finalizada."
            self._touch()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            snap = json.loads(json.dumps(self._state, ensure_ascii=True))
        snap["totals"] = self._totals(snap["checks"])
        snap["roadmap_totals"] = self._totals(snap["roadmap"])
        snap["errors"] = _derive_error_entries_from_checks(snap["checks"])
        snap["error_totals"] = _error_totals(snap["errors"])
        snap["plain_summary"] = _build_plain_summary(snap["totals"], snap["errors"])
        return snap

    @staticmethod
    def _totals(items: list[dict[str, Any]]) -> dict[str, int]:
        totals = {"PENDING": 0, "RUNNING": 0, "PASS": 0, "WARN": 0, "FAIL": 0, "WIP": 0}
        for item in items:
            status = str(item.get("status", ""))
            totals[status] = totals.get(status, 0) + 1
        return totals


class DashboardServer:
    def __init__(self, state: DashboardState, port: int) -> None:
        self._state = state
        self._port = port
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.url: str | None = None

    def start(self) -> None:
        handler = self._build_handler()
        ports = [self._port]
        if self._port != 0:
            ports.append(0)
        last_error: OSError | None = None
        for port in ports:
            try:
                self._server = ThreadingHTTPServer(("127.0.0.1", port), handler)
                break
            except OSError as exc:
                last_error = exc
        if self._server is None:
            raise last_error or OSError("Falha ao iniciar dashboard.")

        actual_port = int(self._server.server_address[1])
        self.url = f"http://127.0.0.1:{actual_port}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        try:
            webbrowser.open(self.url, new=2)
        except Exception:
            pass

    def stop(self) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def _build_handler(self) -> type[BaseHTTPRequestHandler]:
        state = self._state
        html = build_dashboard_html()

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                path = urlparse(self.path).path
                if path in ("/", "/index.html"):
                    data = html.encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return

                if path == "/state":
                    payload = json.dumps(state.snapshot(), ensure_ascii=True).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                    return

                self.send_response(404)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"Not found")

            def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
                return

        return Handler


class QARunner:
    def __init__(self, dashboard_state: DashboardState | None = None) -> None:
        self.results: list[CheckResult] = []
        self.dashboard_state = dashboard_state

    def run(self, check: CheckSpec) -> None:
        if self.dashboard_state is not None:
            self.dashboard_state.start_check(check)

        start = time.time()
        try:
            status, details = check.fn()
        except Exception as exc:  # noqa: BLE001
            status = "FAIL"
            details = f"{exc}\n{traceback.format_exc(limit=3)}"

        result = CheckResult(
            scope=check.scope,
            name=check.name,
            status=status,
            details=details,
            duration_ms=int((time.time() - start) * 1000),
        )
        self.results.append(result)
        if self.dashboard_state is not None:
            self.dashboard_state.finish_check(result)

    def summary(self) -> dict[str, int]:
        totals = {"PASS": 0, "WARN": 0, "FAIL": 0}
        for result in self.results:
            totals[result.status] = totals.get(result.status, 0) + 1
        return totals


def maybe_reexec_in_venv(argv: list[str]) -> int | None:
    if getattr(sys, "frozen", False):
        return None

    if "--no-reexec" in argv:
        return None

    venv_python = ROOT / ".venv" / "Scripts" / "python.exe"
    if not venv_python.exists():
        return None

    current_python = Path(sys.executable).resolve()
    if current_python == venv_python.resolve():
        return None

    forwarded = [arg for arg in argv if arg != "--no-reexec"]
    cmd = [str(venv_python), str(Path(__file__).resolve()), "--no-reexec", *forwarded]
    print(f"[qa] Reexecutando na venv: {venv_python}")
    return subprocess.call(cmd, cwd=str(ROOT))


def run_subprocess(
    command: list[str],
    timeout: int = 120,
    *,
    clear_proxy: bool = False,
) -> tuple[int, str, str]:
    resolved_command = list(command)
    if (
        resolved_command
        and resolved_command[0] == sys.executable
        and getattr(sys, "frozen", False)
    ):
        venv_python = ROOT / ".venv" / "Scripts" / "python.exe"
        if venv_python.exists():
            resolved_command[0] = str(venv_python)

    env = None
    if clear_proxy:
        env = os.environ.copy()
        for key in (
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "http_proxy",
            "https_proxy",
            "all_proxy",
        ):
            env.pop(key, None)

    proc = subprocess.run(
        resolved_command,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def _runtime_mode_details(runtime: dict[str, Any]) -> tuple[str, str]:
    mode = str(runtime.get("mode") or "unknown")
    fallback_reason = runtime.get("fallback_reason")
    reason_details = f"; motivo={fallback_reason}" if fallback_reason else ""
    return mode, reason_details


def check_runtime() -> tuple[str, str]:
    details = f"python={sys.version.split()[0]} exe={sys.executable}"
    return "PASS", details


def check_dependencies() -> tuple[str, str]:
    modules = ["fastapi", "sqlalchemy", "celery", "httpx", "redis", "alembic"]
    missing: list[str] = []
    for module in modules:
        try:
            __import__(module)
        except Exception:  # noqa: BLE001
            missing.append(module)
    if missing:
        return "FAIL", f"Dependencias ausentes: {', '.join(missing)}"
    return "PASS", "Dependencias principais carregadas"


def check_compileall() -> tuple[str, str]:
    code, out, err = run_subprocess([sys.executable, "-m", "compileall", "app"])
    if code != 0:
        details = (out + "\n" + err).strip()[-2000:]
        return "FAIL", f"compileall falhou\n{details}"
    return "PASS", "Sintaxe Python validada em app/"


def check_imports() -> tuple[str, str]:
    code, out, err = run_subprocess(
        [
            sys.executable,
            "-c",
            (
                "import app.main, app.workers.celery_app, app.workers.tasks; "
                "print('imports_ok')"
            ),
        ]
    )
    if code != 0:
        return "FAIL", (out + "\n" + err).strip()[-2000:]
    return "PASS", out or "imports_ok"


def check_registered_routes() -> tuple[str, str]:
    from app.main import app

    registered = {getattr(route, "path", "") for route in app.routes}
    missing = [path for path in EXPECTED_ROUTES if path not in registered]
    if missing:
        return "FAIL", f"Rotas ausentes: {', '.join(missing)}"
    return "PASS", f"{len(EXPECTED_ROUTES)} rotas esperadas registradas"


def _extract_markdown_section(markdown_text: str, heading: str) -> str:
    lines = markdown_text.splitlines()
    start = None
    heading_norm = heading.strip().lower()
    for idx, line in enumerate(lines):
        if line.strip().lower() == heading_norm:
            start = idx + 1
            break
    if start is None:
        return ""

    collected: list[str] = []
    for line in lines[start:]:
        stripped = line.strip()
        if stripped.startswith("## "):
            break
        collected.append(line)
    return "\n".join(collected).strip()


def check_scope_objective_alignment() -> tuple[str, str]:
    readme_path = ROOT / "README.md"
    ia_path = ROOT / "ia.md"
    if not readme_path.exists() or not ia_path.exists():
        return "FAIL", "README.md ou ia.md ausente"

    readme_text = readme_path.read_text(encoding="utf-8", errors="replace")
    ia_text = ia_path.read_text(encoding="utf-8", errors="replace")

    failures: list[str] = []
    validated: list[str] = []

    if "Backend central em Python/FastAPI" not in readme_text:
        failures.append("README sem objetivo principal explicito")
    else:
        validated.append("objetivo_readme")

    scope_section = _extract_markdown_section(ia_text, "## Escopo do projeto")
    if not scope_section:
        failures.append("ia.md sem secao 'Escopo do projeto'")
        return "FAIL", "; ".join(failures)

    scope_lower = scope_section.lower()
    route_files = {
        "whatsapp": ROOT / "app" / "api" / "routes" / "webhooks_meta.py",
        "instagram": ROOT / "app" / "services" / "instagram_publish_service.py",
        "tiktok": ROOT / "app" / "services" / "tiktok_service.py",
        "youtube": ROOT / "app" / "services" / "youtube_service.py",
        "dashboard": ROOT / "app" / "api" / "routes" / "dashboard.py",
        "fila assincrona": ROOT / "app" / "workers" / "celery_app.py",
        "deploy no railway": ROOT / "Procfile",
        "memoria de conversas": ROOT / "app" / "services" / "memory_service.py",
    }

    for capability, file_path in route_files.items():
        if capability in scope_lower:
            if not file_path.exists():
                failures.append(f"escopo cita '{capability}', mas arquivo ausente: {file_path.name}")
            else:
                validated.append(capability.replace(" ", "_"))

    procfile_path = ROOT / "Procfile"
    if procfile_path.exists():
        procfile_text = procfile_path.read_text(encoding="utf-8", errors="replace")
        if "uvicorn" in procfile_text and "PORT" in procfile_text:
            validated.append("procfile_port_ok")
        else:
            failures.append("Procfile sem start esperado com PORT")

    if failures:
        return "FAIL", " | ".join(failures)

    return "PASS", "Escopo/objetivo alinhados: " + ", ".join(validated)


def _run_railway_cli(command_args: list[str], timeout: int = 60) -> tuple[int, str, str]:
    candidates = [
        ["railway", *command_args],
        ["cmd", "/c", "railway", *command_args],
    ]
    last_exc: FileNotFoundError | None = None
    for candidate in candidates:
        try:
            return run_subprocess(candidate, timeout=timeout, clear_proxy=True)
        except FileNotFoundError as exc:
            last_exc = exc
    raise last_exc or FileNotFoundError("Railway CLI nao encontrado no PATH")


def check_railway_cli_status() -> tuple[str, str]:
    try:
        code, out, err = _run_railway_cli(["status", "--json"], timeout=60)
    except FileNotFoundError:
        return "WARN", "Railway CLI nao encontrado no PATH"
    merged = "\n".join(part for part in (out, err) if part).strip()
    merged_lower = merged.lower()

    if code != 0:
        if (
            "unauthorized" in merged_lower
            or "invalid_grant" in merged_lower
            or "please run `railway login` again" in merged_lower
        ):
            return "WARN", "Railway CLI sem sessao valida (execute railway login)"
        if (
            "failed to fetch" in merged_lower
            or "error sending request for url" in merged_lower
            or "connect error" in merged_lower
            or "connection refused" in merged_lower
            or "timed out" in merged_lower
            or "could not resolve host" in merged_lower
            or "nenhuma conexão pôde ser feita" in merged_lower
            or "nenhuma conexao pode ser feita" in merged_lower
        ):
            return "WARN", f"Railway CLI indisponivel por rede/conectividade: {(merged or 'sem detalhes')[:300]}"
        if "not recognized" in merged_lower or "command not found" in merged_lower:
            return "WARN", "Railway CLI nao encontrado no PATH"
        return "FAIL", f"railway status falhou: {(merged or 'sem detalhes')[:400]}"

    try:
        payload = json.loads(out) if out else {}
    except Exception as exc:  # noqa: BLE001
        return "FAIL", f"railway status retornou JSON invalido: {exc.__class__.__name__}"

    project_name = str(payload.get("name") or payload.get("project") or "desconhecido")
    environment_name = str(payload.get("environment") or payload.get("environmentName") or "desconhecido")

    try:
        svc_code, svc_out, svc_err = _run_railway_cli(
            ["service", "status", "--all", "--json"],
            timeout=60,
        )
    except FileNotFoundError:
        return "WARN", "railway status ok, mas Railway CLI nao encontrado para service status"
    if svc_code != 0:
        svc_details = "\n".join(part for part in (svc_out, svc_err) if part).strip()
        return (
            "WARN",
            "railway status ok, mas service status indisponivel: "
            f"{(svc_details or 'sem detalhes')[:250]}",
        )

    service_total = 0
    service_success = 0
    try:
        service_payload = json.loads(svc_out) if svc_out else []
        if isinstance(service_payload, list):
            service_total = len(service_payload)
            for item in service_payload:
                if not isinstance(item, dict):
                    continue
                status_value = str(
                    item.get("latestDeployment", {}).get("status")
                    or item.get("deployment", {}).get("status")
                    or item.get("status")
                    or ""
                ).upper()
                if status_value in {"SUCCESS", "HEALTHY", "RUNNING", "DEPLOYED"}:
                    service_success += 1
    except Exception:  # noqa: BLE001
        return "WARN", f"railway status ok, mas parse de servicos falhou (projeto={project_name})"

    if service_total > 0 and service_success < service_total:
        return (
            "WARN",
            (
                f"Railway projeto={project_name} env={environment_name}; "
                f"servicos saudaveis={service_success}/{service_total}"
            ),
        )

    return (
        "PASS",
        (
            f"Railway projeto={project_name} env={environment_name}; "
            f"servicos saudaveis={service_success}/{service_total}"
        ),
    )


def _database_status_from_mode(mode: str, reason_details: str) -> tuple[str, str]:
    if mode == "primary":
        return "PASS", "Conexao DB ok (SELECT 1; modo=primary)"
    if mode == "fallback_sqlite":
        return (
            "PASS",
            "Conexao DB ok (fallback_sqlite ativo) "
            f"- DB primario indisponivel{reason_details}",
        )
    if mode == "degraded":
        return "FAIL", f"DB em modo degradado{reason_details}"
    return "FAIL", f"Modo de DB desconhecido: {mode}{reason_details}"


def check_database() -> tuple[str, str]:
    from sqlalchemy import text

    from app.core.database import engine, get_database_runtime_state

    runtime = get_database_runtime_state()
    mode, reason_details = _runtime_mode_details(runtime)

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        return (
            "FAIL",
            "Falha de conexao DB no engine ativo "
            f"(modo={mode}{reason_details}): {exc.__class__.__name__}",
        )

    return _database_status_from_mode(mode, reason_details)


def _check_redis_fallback(process_incoming_message: Any, reason_details: str) -> tuple[str, str]:
    try:
        probe_payload = {"qa_probe": "redis_fallback_memory"}
        result = process_incoming_message.delay(probe_payload)
        resolved = result.get(timeout=5)
        if isinstance(resolved, dict) and resolved.get("status") == "queued_stub":
            return (
                "PASS",
                "Fila operacional em fallback_memory "
                f"(Redis primario indisponivel{reason_details})",
            )
        return (
            "FAIL",
            "Fallback de fila ativo, mas resposta da task foi inesperada: "
            f"{resolved}",
        )
    except Exception as exc:  # noqa: BLE001
        return (
            "FAIL",
            "Fallback de fila ativo, mas task falhou "
            f"({exc.__class__.__name__}: {exc}){reason_details}",
        )


def _check_redis_primary(broker_url: str) -> tuple[str, str]:
    import redis

    client = redis.Redis.from_url(
        broker_url,
        socket_connect_timeout=3,
        socket_timeout=3,
    )
    try:
        pong = client.ping()
        if pong:
            return "PASS", "Conexao Redis ok (PING; modo=redis)"
        return "FAIL", "Redis sem resposta no PING (modo=redis)"
    except Exception as exc:  # noqa: BLE001
        return "FAIL", f"Falha de conexao Redis (modo=redis): {exc.__class__.__name__}"


def check_redis() -> tuple[str, str]:
    from app.workers.celery_app import get_queue_runtime_state
    from app.workers.tasks import process_incoming_message

    runtime = get_queue_runtime_state()
    mode, reason_details = _runtime_mode_details(runtime)

    if mode == "fallback_memory":
        return _check_redis_fallback(process_incoming_message, reason_details)

    if mode != "redis":
        return "FAIL", f"Modo de fila invalido: {mode}{reason_details}"

    broker_url = str(runtime.get("broker_url") or "")
    return _check_redis_primary(broker_url)


@contextmanager
def _muted_loggers(logger_names: tuple[str, ...]) -> Iterator[None]:
    previous_states: list[tuple[str, bool]] = []
    for logger_name in logger_names:
        target = logging.getLogger(logger_name)
        previous_states.append((logger_name, target.disabled))
        target.disabled = True
    try:
        yield
    finally:
        for logger_name, state in previous_states:
            logging.getLogger(logger_name).disabled = state


@contextmanager
def _temporary_local_smoke_dependencies(
    app: Any,
    Base: Any,
    get_db: Any,
    webhooks_meta: Any,
) -> Iterator[None]:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    original_overrides = dict(app.dependency_overrides)
    original_delay = webhooks_meta.process_incoming_message.delay

    tmp_root = ROOT / ".qa_tmp"
    tmp_root.mkdir(parents=True, exist_ok=True)
    local_tmp_dir = Path(tempfile.mkdtemp(prefix="qa_local_smoke_", dir=str(tmp_root)))
    local_engine = None

    try:
        sqlite_path = local_tmp_dir / "qa_local_smoke.db"
        sqlite_url = f"sqlite+pysqlite:///{sqlite_path.as_posix()}"
        local_engine = create_engine(
            sqlite_url,
            connect_args={"check_same_thread": False},
            future=True,
        )
        LocalSession = sessionmaker(bind=local_engine, autoflush=False, autocommit=False)
        Base.metadata.create_all(bind=local_engine)

        def override_get_db() -> Iterator[Any]:
            db = LocalSession()
            try:
                yield db
            finally:
                db.close()

        def queue_stub(payload: dict[str, Any]) -> dict[str, Any]:
            return {
                "status": "queued_stub",
                "payload": payload,
            }

        app.dependency_overrides[get_db] = override_get_db
        webhooks_meta.process_incoming_message.delay = queue_stub
        yield
    finally:
        app.dependency_overrides = original_overrides
        webhooks_meta.process_incoming_message.delay = original_delay
        if local_engine is not None:
            local_engine.dispose()
        shutil.rmtree(local_tmp_dir, ignore_errors=True)


@contextmanager
def _temporary_settings_override(**updates: Any) -> Iterator[None]:
    from app.core.config import settings

    snapshots: dict[str, Any] = {}
    for key, value in updates.items():
        snapshots[key] = getattr(settings, key)
        setattr(settings, key, value)
    try:
        yield
    finally:
        for key, value in snapshots.items():
            setattr(settings, key, value)


@contextmanager
def _temporary_logic_harness() -> Iterator[LocalLogicHarness]:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app import models as _models  # noqa: F401
    from app.api.routes import webhooks_meta
    from app.core.database import Base, get_db
    from app.main import app

    original_overrides = dict(app.dependency_overrides)
    original_delay = webhooks_meta.process_incoming_message.delay

    tmp_root = ROOT / ".qa_tmp"
    tmp_root.mkdir(parents=True, exist_ok=True)
    local_tmp_dir = Path(tempfile.mkdtemp(prefix="qa_scope_logic_", dir=str(tmp_root)))
    local_engine = None
    queue_calls: list[dict[str, Any]] = []

    try:
        sqlite_path = local_tmp_dir / "qa_scope_logic.db"
        sqlite_url = f"sqlite+pysqlite:///{sqlite_path.as_posix()}"
        local_engine = create_engine(
            sqlite_url,
            connect_args={"check_same_thread": False},
            future=True,
        )
        local_session = sessionmaker(bind=local_engine, autoflush=False, autocommit=False)
        Base.metadata.create_all(bind=local_engine)

        def override_get_db() -> Iterator[Any]:
            db = local_session()
            try:
                yield db
            finally:
                db.close()

        def queue_stub(payload: dict[str, Any]) -> dict[str, Any]:
            queue_calls.append(dict(payload))
            return {"status": "queued_stub", "payload": payload}

        app.dependency_overrides[get_db] = override_get_db
        webhooks_meta.process_incoming_message.delay = queue_stub
        yield LocalLogicHarness(app=app, session_factory=local_session, queue_calls=queue_calls)
    finally:
        app.dependency_overrides = original_overrides
        webhooks_meta.process_incoming_message.delay = original_delay
        if local_engine is not None:
            local_engine.dispose()
        shutil.rmtree(local_tmp_dir, ignore_errors=True)


def _run_local_route_checks(client: Any, checks: list[str], failures: list[str]) -> None:
    for path in LOCAL_SMOKE_ROUTES:
        resp = client.get(path)
        checks.append(f"GET {path} -> {resp.status_code}")
        if resp.status_code != 200:
            failures.append(f"GET {path} status={resp.status_code}")


def _run_local_webhook_checks(client: Any, checks: list[str], failures: list[str]) -> None:
    verify = client.get(
        "/webhooks/meta",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "__invalid_token__",
            "hub.challenge": "123",
        },
    )
    checks.append(f"GET /webhooks/meta (invalid token) -> {verify.status_code}")
    if verify.status_code != 403:
        failures.append(
            f"GET /webhooks/meta invalid-token expected=403 got={verify.status_code}"
        )

    post_hook = client.post("/webhooks/meta", json=SAMPLE_WEBHOOK_PAYLOAD)
    checks.append(f"POST /webhooks/meta -> {post_hook.status_code}")
    if post_hook.status_code != 202:
        failures.append(f"POST /webhooks/meta expected=202 got={post_hook.status_code}")


def check_local_smoke() -> tuple[str, str]:
    from fastapi.testclient import TestClient

    from app import models as _models  # noqa: F401
    from app.api.routes import webhooks_meta
    from app.core.config import settings
    from app.core.database import Base, get_db
    from app.main import app

    checks: list[str] = []
    failures: list[str] = []

    with _muted_loggers(("httpx", "app.main")):
        with _temporary_local_smoke_dependencies(app, Base, get_db, webhooks_meta):
            with TestClient(app, raise_server_exceptions=False) as client:
                _run_local_route_checks(client, checks, failures)
                _run_local_webhook_checks(client, checks, failures)

    details = f"env={settings.app_env}; db=sqlite_temp; " + " | ".join(checks)
    if failures:
        return "FAIL", details + " | falhas: " + "; ".join(failures)
    return "PASS", details


def _build_logic_webhook_payload(*, external_message_id: str, phone_number_id: str = "") -> dict[str, Any]:
    value_payload: dict[str, Any] = {
        "messaging_product": "whatsapp",
        "contacts": [
            {
                "wa_id": "5511990000000",
                "profile": {"name": "Scope Logic QA"},
            }
        ],
        "messages": [
            {
                "from": "5511990000000",
                "id": external_message_id,
                "type": "text",
                "text": {"body": "quero agendar ensaio de 2 horas"},
            }
        ],
    }
    if phone_number_id:
        value_payload["metadata"] = {"phone_number_id": phone_number_id}

    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA_SCOPE_QA",
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


def check_scope_logic_flow() -> tuple[str, str]:
    from fastapi.testclient import TestClient

    from app.core.config import settings
    from app.models.contact import Contact
    from app.models.contact_identity import ContactIdentity
    from app.models.conversation import Conversation
    from app.models.message import Message

    checks: list[str] = []
    failures: list[str] = []

    with _muted_loggers(("httpx", "app.main")):
        with _temporary_logic_harness() as harness:
            with TestClient(harness.app, raise_server_exceptions=False) as client:
                seed_id = f"wamid.scope.logic.{int(time.time())}"
                payload = _build_logic_webhook_payload(
                    external_message_id=seed_id,
                    phone_number_id="15551234567",
                )

                first = client.post("/webhooks/meta", json=payload)
                checks.append(f"POST webhook first -> {first.status_code}")
                if first.status_code != 202:
                    failures.append(f"primeiro webhook status={first.status_code}")
                first_body = first.json() if first.status_code == 202 else {}
                if first_body.get("messages_created") != 1:
                    failures.append("primeiro webhook nao criou exatamente 1 mensagem")
                if first_body.get("messages_queued") != 1:
                    failures.append("primeiro webhook nao enfileirou 1 mensagem")

                second = client.post("/webhooks/meta", json=payload)
                checks.append(f"POST webhook duplicate -> {second.status_code}")
                if second.status_code != 202:
                    failures.append(f"webhook duplicado status={second.status_code}")
                second_body = second.json() if second.status_code == 202 else {}
                if second_body.get("messages_duplicated", 0) < 1:
                    failures.append("deduplicacao por external_message_id nao confirmada")

                with harness.session_factory() as db:
                    contacts_count = db.query(Contact).count()
                    conversations_count = db.query(Conversation).count()
                    messages_count = db.query(Message).count()
                    identities_count = db.query(ContactIdentity).count()

                checks.append(
                    "persistencia "
                    f"contacts={contacts_count} conversations={conversations_count} "
                    f"messages={messages_count} identities={identities_count}"
                )
                if contacts_count < 1 or conversations_count < 1 or messages_count < 1:
                    failures.append("persistencia principal do webhook incompleta")
                if identities_count < 1:
                    failures.append("contact_identities nao foi preenchido")

                if len(harness.queue_calls) < 1:
                    failures.append("fila nao recebeu payload do webhook")
                else:
                    first_payload = harness.queue_calls[0]
                    if not first_payload.get("message_id"):
                        failures.append("payload de fila sem message_id")
                    if str(first_payload.get("phone_number_id") or "") != "15551234567":
                        failures.append("payload de fila sem phone_number_id esperado")
                    checks.append("queue payload ok")

                pre_disabled_queue_calls = len(harness.queue_calls)
                with _temporary_settings_override(meta_enabled=False):
                    disabled = client.post(
                        "/webhooks/meta",
                        json=_build_logic_webhook_payload(
                            external_message_id=seed_id + ".disabled",
                            phone_number_id="15550000000",
                        ),
                    )
                checks.append(f"POST webhook meta_disabled -> {disabled.status_code}")
                disabled_body = disabled.json() if disabled.status_code == 202 else {}
                if disabled.status_code != 202:
                    failures.append("meta_disabled deveria aceitar webhook com 202")
                if disabled_body.get("ignored_reason") != "meta_disabled":
                    failures.append("meta_disabled nao retornou ignored_reason=meta_disabled")
                if len(harness.queue_calls) != pre_disabled_queue_calls:
                    failures.append("meta_disabled nao deveria enfileirar payload")

                with _temporary_settings_override(meta_enabled=False):
                    post_meta = client.post(
                        "/posts",
                        json={
                            "platform": "instagram",
                            "status": "draft",
                            "title": "scope-qa-meta",
                        },
                    )
                checks.append(f"POST /posts instagram fallback -> {post_meta.status_code}")
                if post_meta.status_code != 201:
                    failures.append("fallback de post Meta nao criou registro")
                else:
                    post_meta_body = post_meta.json()
                    if post_meta_body.get("status") != "pending_meta_review":
                        failures.append("post Meta sem fallback pending_meta_review")

                with _temporary_settings_override(
                    tiktok_enabled=False,
                    tiktok_client_key="",
                    tiktok_client_secret="",
                ):
                    post_tiktok = client.post(
                        "/posts",
                        json={
                            "platform": "tiktok",
                            "status": "draft",
                            "title": "scope-qa-tiktok",
                        },
                    )
                checks.append(f"POST /posts tiktok fallback -> {post_tiktok.status_code}")
                if post_tiktok.status_code != 201:
                    failures.append("fallback de post TikTok nao criou registro")
                else:
                    post_tiktok_body = post_tiktok.json()
                    if post_tiktok_body.get("status") != "pending_tiktok_setup":
                        failures.append("post TikTok sem fallback pending_tiktok_setup")

                health = client.get("/health")
                checks.append(f"GET /health -> {health.status_code}")
                if health.status_code != 200:
                    failures.append("/health falhou no teste de logica")
                else:
                    integrations = health.json().get("integrations", {})
                    for key in (
                        "meta_runtime_enabled",
                        "tiktok_runtime_enabled",
                        "whatsapp_dispatch_ready",
                    ):
                        if key not in integrations:
                            failures.append(f"/health sem integrations.{key}")

    details = " | ".join(checks)
    if failures:
        return "FAIL", details + " | falhas: " + "; ".join(failures)
    return "PASS", details


def _http_get_json(url: str, timeout_seconds: int = 10) -> tuple[int, Any]:
    req = Request(url=url, method="GET", headers={"User-Agent": "qa-tudo/2.0"})
    with _PROXYLESS_HTTP_OPENER.open(req, timeout=timeout_seconds) as response:
        status = int(response.status)
        raw = response.read().decode("utf-8", errors="replace")
        try:
            return status, json.loads(raw)
        except json.JSONDecodeError:
            return status, raw


def _probe_remote_route(base: str, route: str) -> RemoteRouteProbe:
    url = f"{base}{route}"
    try:
        status_code, body = _http_get_json(url)
        return RemoteRouteProbe(route=route, status_code=status_code, body=body, error=None, unreachable=False)
    except HTTPError as exc:
        return RemoteRouteProbe(
            route=route,
            status_code=exc.code,
            body=None,
            error=f"HTTP {exc.code}",
            unreachable=False,
        )
    except URLError as exc:
        return RemoteRouteProbe(
            route=route,
            status_code=None,
            body=None,
            error=f"unreachable ({exc.reason})",
            unreachable=True,
        )
    except Exception as exc:  # noqa: BLE001
        return RemoteRouteProbe(
            route=route,
            status_code=None,
            body=None,
            error=f"error ({exc})",
            unreachable=True,
        )


def _probe_to_summary(probe: RemoteRouteProbe) -> str:
    if probe.status_code is not None:
        return f"GET {probe.route} -> {probe.status_code}"
    return f"GET {probe.route} -> {probe.error}"


def _validate_remote_health_payload(payload: Any, failures: list[str]) -> None:
    if not isinstance(payload, dict):
        failures.append("/health payload invalido")
        return

    status = payload.get("status")
    db_status = payload.get("database")
    redis_status = payload.get("redis")
    if status != "ok":
        failures.append(f"/health status esperado 'ok', recebido '{status}'")
    if db_status != "ok":
        failures.append(f"/health database esperado 'ok', recebido '{db_status}'")
    if redis_status not in {"ok", "fallback", "configured"}:
        failures.append(f"/health redis esperado 'ok|fallback|configured', recebido '{redis_status}'")


def check_remote_smoke(base_url: str) -> tuple[str, str]:
    base = base_url.rstrip("/")
    probes = [_probe_remote_route(base, route) for route in REMOTE_ROUTES]

    results: list[str] = []
    failures: list[str] = []
    unreachable = 0

    for probe in probes:
        results.append(_probe_to_summary(probe))
        if probe.unreachable:
            unreachable += 1
            continue
        if probe.status_code != 200:
            failures.append(f"{probe.route} status={probe.status_code}")
            continue
        if probe.route == "/health":
            _validate_remote_health_payload(probe.body, failures)

    details = f"base_url={base}; " + " | ".join(results)
    if failures:
        tolerated_routes = {"/contacts"}
        non_tolerated = [item for item in failures if not any(route in item for route in tolerated_routes)]
        if non_tolerated:
            return "FAIL", details + " | falhas: " + "; ".join(failures)
        return "WARN", details + " | alertas: " + "; ".join(failures)
    if unreachable == len(REMOTE_ROUTES):
        return "WARN", details + " | remoto indisponivel no ambiente atual"
    if unreachable > 0:
        return "WARN", details + " | parte dos endpoints remotos indisponiveis"
    return "PASS", details


def _format_meta_error_from_payload(payload: Any) -> str:
    if not isinstance(payload, dict):
        return "sem payload"
    error_meta = payload.get("error_meta")
    status_code = payload.get("status_code")
    if not isinstance(error_meta, dict):
        return f"status_code={status_code}"
    code = error_meta.get("code")
    subcode = error_meta.get("error_subcode")
    fbtrace = error_meta.get("fbtrace_id")
    message = error_meta.get("message")
    return (
        f"status_code={status_code}; code={code}; subcode={subcode}; "
        f"fbtrace_id={fbtrace}; message={message}"
    )


def _parse_iso8601(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:  # noqa: BLE001
        return None


def _load_remote_messages(base: str) -> tuple[int | None, list[dict[str, Any]] | None, str | None]:
    probe = _probe_remote_route(base, "/messages")
    if probe.unreachable:
        return probe.status_code, None, probe.error or "unreachable"
    if probe.status_code != 200:
        return probe.status_code, None, probe.error or f"HTTP {probe.status_code}"
    if not isinstance(probe.body, list):
        return probe.status_code, None, "payload_invalido"

    rows: list[dict[str, Any]] = []
    for item in probe.body:
        if isinstance(item, dict):
            rows.append(item)
    return probe.status_code, rows, None


def _message_dispatch_status(message: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
    raw_payload = message.get("raw_payload")
    if not isinstance(raw_payload, dict):
        return None, None

    dispatch = raw_payload.get("dispatch")
    if isinstance(dispatch, dict):
        status = str(dispatch.get("status") or "").strip() or None
        result = dispatch.get("result")
        return status, result if isinstance(result, dict) else None

    dispatch_result = raw_payload.get("dispatch_result")
    if isinstance(dispatch_result, dict):
        status = str(dispatch_result.get("status") or "").strip() or None
        return status, dispatch_result
    return None, None


def _is_recent(created_at: datetime | None, since: datetime) -> bool:
    if created_at is None:
        return False
    return created_at >= since


def check_whatsapp_dispatch_failures(base_url: str, lookback_minutes: int = 1440) -> tuple[str, str]:
    base = base_url.rstrip("/")
    status_code, messages, load_error = _load_remote_messages(base)
    if messages is None:
        return "WARN", f"GET /messages -> {status_code}; falha ao carregar mensagens ({load_error})"

    now_utc = datetime.now(timezone.utc)
    since = now_utc - timedelta(minutes=max(lookback_minutes, 1))

    attempts = 0
    failures: list[dict[str, Any]] = []
    for message in messages:
        if str(message.get("platform") or "").lower() != "whatsapp":
            continue
        if str(message.get("direction") or "").lower() != "outbound":
            continue
        created_at = _parse_iso8601(message.get("created_at"))
        if not _is_recent(created_at, since):
            continue

        dispatch_status, dispatch_result = _message_dispatch_status(message)
        if not dispatch_status:
            continue
        attempts += 1
        if dispatch_status in {"sent", "completed"}:
            continue

        detail_parts = [
            f"id={message.get('id')}",
            f"created_at={message.get('created_at')}",
            f"dispatch_status={dispatch_status}",
        ]
        if isinstance(dispatch_result, dict):
            status_code_val = dispatch_result.get("status_code")
            error_meta = dispatch_result.get("error_meta")
            detail_parts.append(f"status_code={status_code_val}")
            if isinstance(error_meta, dict):
                detail_parts.append(f"code={error_meta.get('code')}")
                detail_parts.append(f"subcode={error_meta.get('error_subcode')}")
                detail_parts.append(f"fbtrace_id={error_meta.get('fbtrace_id')}")
                detail_parts.append(f"message={error_meta.get('message')}")
            elif dispatch_result.get("detail"):
                detail_parts.append(f"detail={dispatch_result.get('detail')}")
        failures.append(
            {
                "created_at": created_at,
                "details": "; ".join(str(part) for part in detail_parts if str(part).strip()),
            }
        )

    base_detail = f"GET /messages -> {status_code}; janela={lookback_minutes}min; tentativas={attempts}"
    if failures:
        failures.sort(
            key=lambda item: item.get("created_at") or datetime.fromtimestamp(0, tz=timezone.utc),
            reverse=True,
        )
        primary = str(failures[0].get("details") or "")
        extras = " || ".join(
            str(item.get("details") or "")
            for item in failures[1:4]
            if str(item.get("details") or "").strip()
        )
        if extras:
            primary = primary + f" | outros_erros_recentes={len(failures)-1} | " + extras
        return (
            "FAIL",
            base_detail + "; falhas_recentes=" + str(len(failures)) + " | " + primary,
        )
    if attempts == 0:
        return "WARN", base_detail + "; sem envio WhatsApp recente para validar dispatch real"
    return "PASS", base_detail + "; nenhum erro de dispatch WhatsApp detectado"


def check_instagram_inbound_delivery(base_url: str, lookback_minutes: int = 360) -> tuple[str, str]:
    base = base_url.rstrip("/")
    health_probe = _probe_remote_route(base, "/health")
    status_code, messages, load_error = _load_remote_messages(base)

    if messages is None:
        return "WARN", f"GET /messages -> {status_code}; falha ao carregar mensagens ({load_error})"

    health_payload = health_probe.body if isinstance(health_probe.body, dict) else {}
    integrations = health_payload.get("integrations") if isinstance(health_payload, dict) else {}
    if not isinstance(integrations, dict):
        integrations = {}
    instagram_ready = bool(
        integrations.get("instagram_publish_ready")
        or integrations.get("instagram_cached_account_ready")
    )

    now_utc = datetime.now(timezone.utc)
    since = now_utc - timedelta(minutes=max(lookback_minutes, 1))
    inbound_count = 0
    last_inbound_at: str | None = None
    for message in messages:
        if str(message.get("platform") or "").lower() != "instagram":
            continue
        if str(message.get("direction") or "").lower() != "inbound":
            continue
        created_at_text = str(message.get("created_at") or "")
        created_at = _parse_iso8601(created_at_text)
        if not _is_recent(created_at, since):
            continue
        inbound_count += 1
        if last_inbound_at is None or created_at_text > last_inbound_at:
            last_inbound_at = created_at_text

    base_detail = (
        f"GET /messages -> {status_code}; GET /health -> {health_probe.status_code}; "
        f"instagram_ready={instagram_ready}; janela={lookback_minutes}min; inbound_count={inbound_count}; "
        f"last_inbound_at={last_inbound_at}"
    )
    if not instagram_ready:
        return "WARN", base_detail + "; Instagram ainda nao pronto no /health"
    if inbound_count == 0:
        return (
            "WARN",
            base_detail + "; sem DM Instagram recebida no periodo validado",
        )
    return "PASS", base_detail + "; DM Instagram chegando no dashboard"


def check_meta_live_signals(base_url: str) -> tuple[str, str]:
    base = base_url.rstrip("/")
    outbound_probe = _probe_remote_route(base, "/health/meta-live/outbound")
    inbound_probe = _probe_remote_route(base, "/health/meta-live/inbound")
    combined_probe = _probe_remote_route(base, "/health/meta-live")

    checks = [
        _probe_to_summary(outbound_probe),
        _probe_to_summary(inbound_probe),
        _probe_to_summary(combined_probe),
    ]

    if outbound_probe.unreachable and inbound_probe.unreachable and combined_probe.unreachable:
        return "WARN", " | ".join(checks) + " | endpoint meta-live indisponivel"

    failures: list[str] = []
    warnings: list[str] = []

    if outbound_probe.status_code != 200:
        failures.append(f"outbound_http={outbound_probe.status_code}")
    if inbound_probe.status_code != 200:
        failures.append(f"inbound_http={inbound_probe.status_code}")
    if combined_probe.status_code != 200:
        failures.append(f"combined_http={combined_probe.status_code}")

    outbound_payload = outbound_probe.body if isinstance(outbound_probe.body, dict) else {}
    inbound_payload = inbound_probe.body if isinstance(inbound_probe.body, dict) else {}
    combined_payload = combined_probe.body if isinstance(combined_probe.body, dict) else {}

    outbound_status = str(outbound_payload.get("status") or "")
    inbound_status = str(inbound_payload.get("status") or "")
    combined_status = str(combined_payload.get("status") or "")

    if outbound_status not in {"ok", "degraded"}:
        details = outbound_payload.get("details") if isinstance(outbound_payload, dict) else {}
        meta_response = details.get("meta_response") if isinstance(details, dict) else {}
        failures.append(
            "outbound_status="
            f"{outbound_status}; where={outbound_payload.get('where')}; "
            f"meta_error={_format_meta_error_from_payload(meta_response)}"
        )
    elif outbound_status == "degraded":
        details = outbound_payload.get("details") if isinstance(outbound_payload, dict) else {}
        phone_probe = details.get("probe", {}).get("phone") if isinstance(details, dict) else {}
        failures.append(
            "outbound_status=degraded; where=Meta Graph phone check; "
            f"meta_error={_format_meta_error_from_payload(phone_probe)}"
        )

    if inbound_status in {"fail", "degraded"}:
        details = inbound_payload.get("details") if isinstance(inbound_payload, dict) else {}
        recent_received = int(details.get("recent_received_count") or 0)
        recent_invalid_signature = int(details.get("recent_invalid_signature_count") or 0)
        message = (
            "inbound_status="
            f"{inbound_status}; where={inbound_payload.get('where')}; "
            f"recent_received={recent_received}; "
            f"recent_invalid_signature={recent_invalid_signature}; "
            f"last_invalid_signature_at={details.get('last_invalid_signature_at')}"
        )
        if inbound_status == "degraded" and recent_received > 0 and recent_invalid_signature > 0:
            warnings.append(message)
        else:
            failures.append(message)
    elif inbound_status == "warn":
        details = inbound_payload.get("details") if isinstance(inbound_payload, dict) else {}
        warnings.append(
            "inbound_status=warn; "
            f"sem prova recente de entrada; last_received_at={details.get('last_received_at')}"
        )

    if combined_status == "fail":
        failures.append(
            "combined_status="
            f"{combined_status}; message={combined_payload.get('message')}"
        )
    elif combined_status == "degraded" and not failures:
        warnings.append(
            "combined_status=degraded; "
            f"message={combined_payload.get('message')}"
        )

    summary = " | ".join(checks)
    if failures:
        detail = summary + " | falhas: " + " || ".join(failures)
        if warnings:
            detail += " | alertas: " + " || ".join(warnings)
        return "FAIL", detail
    if warnings:
        return "WARN", summary + " | alertas: " + " || ".join(warnings)
    return "PASS", summary + " | sinais de ida e volta Meta validados"


def save_report(
    results: list[CheckResult],
    dashboard_url: str | None,
) -> None:
    errors = _derive_error_entries_from_results(results)
    totals = {"PASS": 0, "WARN": 0, "FAIL": 0}
    for result in results:
        totals[result.status] = totals.get(result.status, 0) + 1
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dashboard_url": dashboard_url,
        "totals": totals,
        "plain_summary": _build_plain_summary(totals, errors),
        "errors": errors,
        "results": [asdict(result) for result in results],
        "roadmap": ROADMAP_ITEMS,
    }
    REPORT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def print_report(results: list[CheckResult], dashboard_url: str | None) -> int:
    print("\n=== QA bot-multiredes ===")
    for result in results:
        print(
            f"[{result.status}] [{result.scope}] {result.name} ({result.duration_ms}ms)\n"
            f"  {result.details}"
        )
    totals = {"PASS": 0, "WARN": 0, "FAIL": 0}
    for result in results:
        totals[result.status] = totals.get(result.status, 0) + 1
    print(
        "\nResumo: "
        f"PASS={totals.get('PASS', 0)} "
        f"WARN={totals.get('WARN', 0)} "
        f"FAIL={totals.get('FAIL', 0)}"
    )
    errors = _derive_error_entries_from_results(results)
    print(f"Resumo simples: {_build_plain_summary(totals, errors)}")
    if errors:
        print("\nTela de erros:")
        for item in errors:
            print(
                f"- [{item['status']}] onde={item['where']} | codigo={item['error_code']}\n"
                f"  explicacao={item['simple_explanation']}\n"
                f"  motivo={item['most_likely_cause']}\n"
                f"  detalhe={item['technical_error']}"
            )
    print(f"Relatorio salvo em: {REPORT_PATH}")
    if dashboard_url:
        print(f"Dashboard web: {dashboard_url}")
    return 1 if totals.get("FAIL", 0) > 0 else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="QA completo do projeto bot-multiredes.")
    parser.add_argument(
        "--base-url",
        default=os.getenv("QA_BASE_URL", DEFAULT_BASE_URL),
        help="Base URL para smoke remoto.",
    )
    parser.add_argument(
        "--skip-remote",
        action="store_true",
        help="Pula checagens de ambiente remoto.",
    )
    parser.add_argument(
        "--skip-local-smoke",
        action="store_true",
        help="Pula smoke local via TestClient.",
    )
    parser.add_argument(
        "--skip-scope-docs",
        action="store_true",
        help="Pula validacao de escopo/objetivo por README.md e ia.md.",
    )
    parser.add_argument(
        "--skip-scope-logic",
        action="store_true",
        help="Pula validacao de logica principal baseada no escopo.",
    )
    parser.add_argument(
        "--skip-railway-cli",
        action="store_true",
        help="Pula check do Railway via CLI (railway status --json).",
    )
    parser.add_argument(
        "--no-dashboard",
        action="store_true",
        help="Nao abre dashboard web local.",
    )
    parser.add_argument(
        "--dashboard-port",
        type=int,
        default=8765,
        help="Porta do dashboard local (usa porta aleatoria se ocupado).",
    )
    parser.add_argument(
        "--no-pause",
        action="store_true",
        help="Nao aguarda ENTER ao finalizar.",
    )
    parser.add_argument(
        "--no-reexec",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    return parser.parse_args()


def build_checks(args: argparse.Namespace) -> list[CheckSpec]:
    checks = [
        CheckSpec("Main/API", "Runtime Python", check_runtime),
        CheckSpec("Main/API", "Dependencias", check_dependencies),
        CheckSpec("Main/API", "Sintaxe (compileall)", check_compileall),
        CheckSpec("Main/API", "Imports principais", check_imports),
        CheckSpec("Main/API", "Rotas registradas", check_registered_routes),
    ]

    if not args.skip_scope_docs:
        checks.append(
            CheckSpec(
                "Escopo/Objetivo",
                "Aderencia README+IA",
                check_scope_objective_alignment,
            )
        )

    checks.extend(
        [
        CheckSpec("Infra Local", "Conexao DB", check_database),
        CheckSpec("Infra Local", "Conexao Redis", check_redis),
        ]
    )

    if not args.skip_scope_logic:
        checks.append(
            CheckSpec(
                "Logica",
                "Fluxo principal do escopo",
                check_scope_logic_flow,
            )
        )

    if not args.skip_local_smoke:
        checks.append(CheckSpec("Smoke Local", "Smoke local FastAPI", check_local_smoke))

    if not args.skip_railway_cli:
        checks.append(
            CheckSpec(
                "Railway CLI",
                "Status do Railway via CLI",
                check_railway_cli_status,
            )
        )

    if not args.skip_remote:
        checks.append(
            CheckSpec(
                "Meta Live",
                "Sinal ida/volta Meta",
                lambda: check_meta_live_signals(args.base_url),
            )
        )
        checks.append(
            CheckSpec(
                "Meta Live",
                "WhatsApp dispatch (falhas reais)",
                lambda: check_whatsapp_dispatch_failures(args.base_url),
            )
        )
        checks.append(
            CheckSpec(
                "Meta Live",
                "Instagram DM entrada",
                lambda: check_instagram_inbound_delivery(args.base_url),
            )
        )
        checks.append(
            CheckSpec(
                "Smoke Remoto",
                "Smoke remoto",
                lambda: check_remote_smoke(args.base_url),
            )
        )
    return checks


def build_dashboard_html() -> str:
    return """<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>QA Dashboard</title>
  <style>
    body{margin:0;padding:20px;font-family:Segoe UI,Tahoma,sans-serif;background:#f5f7fb;color:#0f172a}
    .wrap{max-width:1200px;margin:0 auto;display:grid;gap:12px}
    .card{background:#fff;border:1px solid #dbe3ef;border-radius:12px;padding:14px}
    h1,h2{margin:0 0 8px 0}
    .meta{display:flex;gap:12px;flex-wrap:wrap;font-size:12px;color:#475569}
    .badges{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}
    .badge{padding:4px 8px;border-radius:999px;color:#fff;font-weight:700;font-size:12px}
    .PENDING{background:#6b7280}.RUNNING{background:#eab308;color:#111}.PASS{background:#16a34a}
    .WARN{background:#d97706}.FAIL{background:#dc2626}.WIP{background:#f97316}
    .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:10px}
    table{width:100%;border-collapse:collapse;font-size:12px}th,td{border-top:1px solid #e2e8f0;padding:7px;text-align:left;vertical-align:top}
    .details{white-space:pre-wrap;word-break:break-word;max-height:110px;overflow:auto}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1 id="title">QA Dashboard</h1>
      <div class="meta">
        <span id="started">Inicio: -</span>
        <span id="updated">Atualizado: -</span>
        <span id="finished">Fim: em andamento</span>
      </div>
      <div id="message" style="margin-top:8px;font-weight:600">Carregando...</div>
      <div id="totals" class="badges"></div>
    </div>
    <div class="card">
      <h2>Resumo Simples</h2>
      <div id="plain-summary" class="details">Carregando explicacao simplificada...</div>
    </div>
    <div class="card">
      <h2>Tela de Erros</h2>
      <div id="error_totals" class="badges"></div>
      <table>
        <thead><tr><th>Onde</th><th>Codigo</th><th>Explicacao simples</th><th>Motivo mais provavel</th><th>Detalhe tecnico</th></tr></thead>
        <tbody id="errors"></tbody>
      </table>
    </div>
    <div id="checks" class="grid"></div>
    <div class="card">
      <h2>Proximas Etapas</h2>
      <div id="roadmap_totals" class="badges"></div>
      <table><thead><tr><th>Item</th><th>Status</th><th>Detalhes</th></tr></thead><tbody id="roadmap"></tbody></table>
    </div>
  </div>
  <script>
    function badge(status,text){
      const span=document.createElement('span');
      span.className='badge '+status;
      span.textContent=text||status;
      return span;
    }
    function label(status){
      if(status==='RUNNING') return 'Verificando';
      if(status==='PASS') return 'Verificado';
      if(status==='FAIL') return 'Erro';
      if(status==='WIP') return 'Trabalho em progresso';
      if(status==='WARN') return 'Atencao';
      return 'Aguardando';
    }
    function renderTotals(elId, totals){
      const root=document.getElementById(elId);
      root.innerHTML='';
      Object.keys(totals||{}).forEach(k=>{
        if(!totals[k]) return;
        root.appendChild(badge(k, k+': '+totals[k]));
      });
    }
    function renderChecks(checks){
      const groups={};
      (checks||[]).forEach(c=>{groups[c.scope]=groups[c.scope]||[];groups[c.scope].push(c);});
      const root=document.getElementById('checks');
      root.innerHTML='';
      Object.keys(groups).sort().forEach(scope=>{
        const card=document.createElement('div');
        card.className='card';
        const h2=document.createElement('h2');
        h2.textContent=scope;
        card.appendChild(h2);
        const table=document.createElement('table');
        table.innerHTML='<thead><tr><th>Check</th><th>Status</th><th>Duracao</th><th>Detalhes</th></tr></thead>';
        const body=document.createElement('tbody');
        groups[scope].forEach(c=>{
          const tr=document.createElement('tr');
          tr.innerHTML='<td></td><td></td><td></td><td><div class=\"details\"></div></td>';
          tr.children[0].textContent=c.name;
          tr.children[1].appendChild(badge(c.status,label(c.status)));
          tr.children[2].textContent=(c.duration_ms===null||c.duration_ms===undefined)?'-':(c.duration_ms+' ms');
          tr.children[3].querySelector('.details').textContent=c.details||'-';
          body.appendChild(tr);
        });
        table.appendChild(body);
        card.appendChild(table);
        root.appendChild(card);
      });
    }
    function renderRoadmap(items){
      const body=document.getElementById('roadmap');
      body.innerHTML='';
      (items||[]).forEach(i=>{
        const tr=document.createElement('tr');
        tr.innerHTML='<td></td><td></td><td><div class=\"details\"></div></td>';
        tr.children[0].textContent=i.name;
        tr.children[1].appendChild(badge(i.status,label(i.status)));
        tr.children[2].querySelector('.details').textContent=i.details||'-';
        body.appendChild(tr);
      });
    }
    function renderErrors(items){
      const body=document.getElementById('errors');
      body.innerHTML='';
      if(!items || items.length===0){
        const tr=document.createElement('tr');
        tr.innerHTML='<td colspan=\"5\">Sem erros detectados ate agora.</td>';
        body.appendChild(tr);
        return;
      }
      items.forEach(i=>{
        const tr=document.createElement('tr');
        tr.innerHTML='<td></td><td></td><td><div class=\"details\"></div></td><td><div class=\"details\"></div></td><td><div class=\"details\"></div></td>';
        tr.children[0].textContent=i.where||'-';
        tr.children[1].textContent=i.error_code||'N/A';
        tr.children[2].querySelector('.details').textContent=i.simple_explanation||'-';
        tr.children[3].querySelector('.details').textContent=i.most_likely_cause||'-';
        tr.children[4].querySelector('.details').textContent=i.technical_error||'-';
        body.appendChild(tr);
      });
    }
    async function refresh(){
      try{
        const res=await fetch('/state',{cache:'no-store'});
        if(!res.ok) throw new Error('HTTP '+res.status);
        const data=await res.json();
        document.getElementById('title').textContent='QA Dashboard - '+(data.project||'Projeto');
        document.getElementById('started').textContent='Inicio: '+(data.started_at||'-');
        document.getElementById('updated').textContent='Atualizado: '+(data.updated_at||'-');
        document.getElementById('finished').textContent='Fim: '+(data.finished_at||'em andamento');
        document.getElementById('message').textContent=data.message||'-';
        document.getElementById('plain-summary').textContent=data.plain_summary||'-';
        renderTotals('totals', data.totals||{});
        renderTotals('error_totals', data.error_totals||{});
        renderTotals('roadmap_totals', data.roadmap_totals||{});
        renderErrors(data.errors||[]);
        renderChecks(data.checks||[]);
        renderRoadmap(data.roadmap||[]);
      }catch(err){
        document.getElementById('message').textContent='Falha ao atualizar dashboard: '+err;
      }
    }
    refresh();
    setInterval(refresh, 800);
  </script>
</body>
</html>
"""


def main() -> int:
    args = parse_args()
    reexec_code = maybe_reexec_in_venv(sys.argv[1:])
    if reexec_code is not None:
        return reexec_code

    checks = build_checks(args)

    dashboard_state: DashboardState | None = None
    dashboard_server: DashboardServer | None = None

    if not args.no_dashboard:
        dashboard_state = DashboardState()
        dashboard_state.register_checks(checks)
        dashboard_server = DashboardServer(dashboard_state, args.dashboard_port)
        try:
            dashboard_server.start()
            if dashboard_server.url:
                print(f"[qa] Dashboard web iniciado em {dashboard_server.url}")
        except OSError as exc:
            print(f"[qa] Nao foi possivel iniciar dashboard web: {exc}")
            dashboard_state = None
            dashboard_server = None

    runner = QARunner(dashboard_state=dashboard_state)
    exit_code = 1
    try:
        for check in checks:
            runner.run(check)

        if dashboard_state is not None:
            dashboard_state.finalize()

        dashboard_url = dashboard_server.url if dashboard_server else None
        save_report(runner.results, dashboard_url)
        exit_code = print_report(runner.results, dashboard_url)

        if not args.no_pause:
            try:
                input("\nPressione ENTER para fechar...")
            except EOFError:
                pass
    finally:
        if dashboard_server is not None:
            dashboard_server.stop()

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

