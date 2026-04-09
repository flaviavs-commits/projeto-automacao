from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes.analytics import router as analytics_router
from app.api.routes.contacts import router as contacts_router
from app.api.routes.conversations import router as conversations_router
from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.health import router as health_router
from app.api.routes.messages import router as messages_router
from app.api.routes.posts import router as posts_router
from app.api.routes.webhooks_meta import router as webhooks_meta_router
from app.core.config import settings
from app.core.database import get_database_runtime_state
from app.core.logging import configure_logging, get_logger
from app.workers.celery_app import get_queue_runtime_state


configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    db_runtime = get_database_runtime_state()
    queue_runtime = get_queue_runtime_state()
    logger.info(
        "application_startup",
        extra={
            "environment": settings.app_env,
            "database_mode": db_runtime.get("mode"),
            "database_fallback_reason": db_runtime.get("fallback_reason"),
            "queue_mode": queue_runtime.get("mode"),
            "queue_fallback_reason": queue_runtime.get("fallback_reason"),
        },
    )
    yield
    logger.info("application_shutdown", extra={"environment": settings.app_env})


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/", tags=["root"])
def read_root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "environment": settings.app_env,
        "status": "running",
    }


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    logger.warning(
        "http_error",
        extra={"path": str(request.url.path), "status_code": exc.status_code},
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    logger.warning(
        "validation_error",
        extra={"path": str(request.url.path), "errors": exc.errors()},
    )
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    logger.exception(
        "unhandled_error",
        extra={"path": str(request.url.path), "error": str(exc)},
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


app.include_router(health_router)
app.include_router(webhooks_meta_router)
app.include_router(conversations_router)
app.include_router(messages_router)
app.include_router(contacts_router)
app.include_router(posts_router)
app.include_router(analytics_router)
app.include_router(dashboard_router)
