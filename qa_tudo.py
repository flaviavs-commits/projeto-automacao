from __future__ import annotations

import argparse
import json
import logging
import os
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
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Iterator
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
DEFAULT_BASE_URL = "https://projeto-automacao-production.up.railway.app"
REPORT_PATH = ROOT / "qa_report_latest.json"

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


class DashboardState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state: dict[str, Any] = {
            "project": "bot-multiredes",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": None,
            "finished_at": None,
            "message": "Aguardando inicio do QA.",
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


def run_subprocess(command: list[str], timeout: int = 120) -> tuple[int, str, str]:
    proc = subprocess.run(
        command,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
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
            f"({exc.__class__.__name__}){reason_details}",
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


def _http_get_json(url: str, timeout_seconds: int = 10) -> tuple[int, Any]:
    req = Request(url=url, method="GET", headers={"User-Agent": "qa-tudo/2.0"})
    with urlopen(req, timeout=timeout_seconds) as response:
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
        return "FAIL", details + " | falhas: " + "; ".join(failures)
    if unreachable == len(REMOTE_ROUTES):
        return "WARN", details + " | remoto indisponivel no ambiente atual"
    if unreachable > 0:
        return "WARN", details + " | parte dos endpoints remotos indisponiveis"
    return "PASS", details


def save_report(
    results: list[CheckResult],
    dashboard_url: str | None,
) -> None:
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dashboard_url": dashboard_url,
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
        CheckSpec("Infra Local", "Conexao DB", check_database),
        CheckSpec("Infra Local", "Conexao Redis", check_redis),
    ]

    if not args.skip_local_smoke:
        checks.append(CheckSpec("Smoke Local", "Smoke local FastAPI", check_local_smoke))
    if not args.skip_remote:
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
        renderTotals('totals', data.totals||{});
        renderTotals('roadmap_totals', data.roadmap_totals||{});
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

