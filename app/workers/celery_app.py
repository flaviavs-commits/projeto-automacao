from urllib.parse import urlparse

from celery import Celery
import redis

from app.core.config import settings


def _is_local_redis_url(redis_url: str) -> bool:
    try:
        parsed = urlparse(redis_url)
        host = (parsed.hostname or "").lower()
    except Exception:
        host = ""
    return host in {"localhost", "127.0.0.1", "::1"} or "localhost" in redis_url.lower()


def _probe_redis(redis_url: str) -> tuple[bool, str | None]:
    client = redis.Redis.from_url(
        redis_url,
        socket_connect_timeout=2,
        socket_timeout=2,
    )
    try:
        pong = client.ping()
        if pong:
            return True, None
        return False, "NoPingResponse"
    except Exception as exc:  # noqa: BLE001
        return False, exc.__class__.__name__


def _resolve_queue_runtime() -> tuple[str, str, dict[str, str | bool | None]]:
    configured_redis_url = settings.redis_url
    state: dict[str, str | bool | None] = {
        "configured_redis_url": configured_redis_url,
        "broker_url": configured_redis_url,
        "backend_url": configured_redis_url,
        "mode": "redis",
        "fallback_enabled": settings.app_env.lower() == "development",
        "fallback_reason": None,
    }

    if settings.app_env.lower() != "development":
        return configured_redis_url, configured_redis_url, state

    if not _is_local_redis_url(configured_redis_url):
        return configured_redis_url, configured_redis_url, state

    redis_ok, redis_error = _probe_redis(configured_redis_url)
    if redis_ok:
        return configured_redis_url, configured_redis_url, state

    state["mode"] = "fallback_memory"
    state["broker_url"] = "memory://localhost/"
    state["backend_url"] = "cache+memory://"
    state["fallback_reason"] = f"primary_error={redis_error}"
    return "memory://localhost/", "cache+memory://", state


ACTIVE_BROKER_URL, ACTIVE_BACKEND_URL, QUEUE_RUNTIME_STATE = _resolve_queue_runtime()

celery_app = Celery(
    "bot_multiredes",
    broker=ACTIVE_BROKER_URL,
    backend=ACTIVE_BACKEND_URL,
)

base_conf = {
    "task_serializer": "json",
    "accept_content": ["json"],
    "result_serializer": "json",
    "timezone": "UTC",
    "enable_utc": True,
    "task_ignore_result": False,
}
if QUEUE_RUNTIME_STATE.get("mode") == "fallback_memory":
    base_conf["task_always_eager"] = True
    base_conf["task_store_eager_result"] = True

celery_app.conf.update(**base_conf)

celery_app.autodiscover_tasks(["app.workers"])


def get_queue_runtime_state() -> dict[str, str | bool | None]:
    return dict(QUEUE_RUNTIME_STATE)
