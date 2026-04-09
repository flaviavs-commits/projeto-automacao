from collections.abc import Generator
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, MetaData, Uuid, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.core.config import settings


NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Base(DeclarativeBase):
    metadata = metadata


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class UUIDPrimaryKeyMixin:
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)


def _is_local_database_url(database_url: str) -> bool:
    try:
        parsed = urlparse(database_url)
        host = (parsed.hostname or "").lower()
    except Exception:
        host = ""
    return host in {"localhost", "127.0.0.1", "::1"} or "localhost" in database_url.lower()


def _probe_database_url(database_url: str, timeout_seconds: int = 2) -> tuple[bool, str | None]:
    probe_kwargs: dict = {"pool_pre_ping": True}
    if database_url.lower().startswith("postgresql"):
        probe_kwargs["connect_args"] = {"connect_timeout": timeout_seconds}

    probe_engine = create_engine(database_url, **probe_kwargs)
    try:
        with probe_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, None
    except Exception as exc:  # noqa: BLE001
        return False, exc.__class__.__name__
    finally:
        probe_engine.dispose()


def _build_sqlite_fallback_url() -> str:
    root = Path(__file__).resolve().parents[2]
    storage_path = Path(settings.local_storage_path)
    if not storage_path.is_absolute():
        storage_path = root / storage_path
    storage_path.mkdir(parents=True, exist_ok=True)
    sqlite_path = storage_path / "bot_multiredes_local.db"
    return f"sqlite+pysqlite:///{sqlite_path.resolve().as_posix()}"


def _resolve_database_runtime() -> tuple[str, dict[str, str | bool | None]]:
    configured_url = settings.database_url
    state: dict[str, str | bool | None] = {
        "configured_url": configured_url,
        "active_url": configured_url,
        "mode": "primary",
        "fallback_enabled": settings.app_env.lower() == "development",
        "fallback_reason": None,
    }

    if settings.app_env.lower() != "development":
        return configured_url, state

    is_local_postgres = configured_url.lower().startswith("postgresql") and _is_local_database_url(
        configured_url
    )
    if not is_local_postgres:
        return configured_url, state

    primary_ok, primary_error = _probe_database_url(configured_url)
    if primary_ok:
        return configured_url, state

    sqlite_url = _build_sqlite_fallback_url()
    fallback_ok, fallback_error = _probe_database_url(sqlite_url)
    if not fallback_ok:
        state["mode"] = "degraded"
        state["fallback_reason"] = (
            f"primary_error={primary_error}; sqlite_fallback_error={fallback_error}"
        )
        return configured_url, state

    state["mode"] = "fallback_sqlite"
    state["active_url"] = sqlite_url
    state["fallback_reason"] = f"primary_error={primary_error}"
    return sqlite_url, state


ACTIVE_DATABASE_URL, DATABASE_RUNTIME_STATE = _resolve_database_runtime()

engine_kwargs = {"pool_pre_ping": True}
if ACTIVE_DATABASE_URL.lower().startswith("postgresql"):
    engine_kwargs["connect_args"] = {"connect_timeout": 5}

engine = create_engine(ACTIVE_DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def json_column() -> Mapped[dict]:
    return mapped_column(JSON, default=dict, nullable=False)


def get_database_runtime_state() -> dict[str, str | bool | None]:
    return dict(DATABASE_RUNTIME_STATE)
