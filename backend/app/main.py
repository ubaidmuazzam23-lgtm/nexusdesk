# Location: ./backend/app/main.py

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import settings
from app.core.database import get_db
from app.api.v1.routes import auth, admin, engineer, chat
from app.api.v1.routes.analytics import router as analytics_router
from app.api.v1.routes.knowledge import router as knowledge_router
from app.api.v1.routes.model_stats import router as model_stats_router
from app.api.v1.routes.routing_simulator import router as routing_router
from app.api.v1.routes.teams import router as teams_router
from app.api.v1.routes.manager import router as manager_router
from app.api.v1.routes.assets import router as assets_router
from app.websockets.team_chat_ws import router as team_chat_ws_router

logger = logging.getLogger(__name__)

_ALLOWED_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
_ALLOWED_HEADERS = ["Authorization", "Content-Type", "Accept"]


_WEAK_JWT_SECRETS = {
    "secret", "changeme", "change-in-prod", "ai-support-jwt-secret-change-in-prod",
    "your-secret-key", "jwt-secret", "supersecret",
}

# Set True by the lifespan after startup completes; /ready uses this.
_server_ready = False

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Give app.* loggers a handler — uvicorn only wires up uvicorn.* loggers, not root
    _app_log = logging.getLogger("app")
    _app_log.setLevel(logging.INFO)
    if not _app_log.handlers:
        _h = logging.StreamHandler()
        _h.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
        _app_log.addHandler(_h)

    # Redis — must be initialised before any service that needs it
    from app.core.redis_client import init_redis
    _redis_ok = init_redis(settings.REDIS_URL)
    if _redis_ok:
        logger.info("Redis session sharing active — safe to run --workers > 1")
    else:
        logger.info("No Redis — single-worker in-memory mode")

    if settings.JWT_SECRET_KEY.lower() in _WEAK_JWT_SECRETS or len(settings.JWT_SECRET_KEY) < 32:
        logger.warning(
            "SECURITY WARNING: JWT_SECRET_KEY is weak or default (%r). "
            "Set a strong random secret in production.",
            settings.JWT_SECRET_KEY,
        )

    # Auto-run DB migrations — safe to re-run (alembic is idempotent)
    try:
        import alembic.config
        import alembic.command
        _ini = os.path.join(os.path.dirname(__file__), "..", "alembic.ini")
        _cfg = alembic.config.Config(os.path.abspath(_ini))
        alembic.command.upgrade(_cfg, "head")
        logger.info("Alembic migrations: up to date")
    except Exception as _exc:
        logger.error("Alembic migration failed — proceeding anyway: %s", _exc)

    from app.services.slack_service import start_slack_bot
    from app.services.knowledge_service import start_url_refresh_scheduler, _get_embedder
    start_slack_bot()
    start_url_refresh_scheduler()

    # Warm the sentence-transformers model so the first RAG query has no extra latency
    try:
        _get_embedder()
        logger.info("Sentence-transformers model loaded")
    except Exception as _exc:
        logger.warning("Embedder warmup failed (will retry on first query): %s", _exc)

    # Signal readiness — /ready starts returning 200 from this point
    global _server_ready
    _server_ready = True
    logger.info("Server ready — accepting traffic")

    yield
    _server_ready = False
    logger.info("Shutting down — lifespan complete")


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL],
    allow_credentials=True,
    allow_methods=_ALLOWED_METHODS,
    allow_headers=_ALLOWED_HEADERS,
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next) -> Response:
    response = await call_next(request)
    for header, value in _SECURITY_HEADERS.items():
        response.headers[header] = value
    return response

app.include_router(auth.router,          prefix="/api/v1")
app.include_router(admin.router,         prefix="/api/v1")
app.include_router(engineer.router,      prefix="/api/v1")
app.include_router(chat.router,          prefix="/api/v1")
app.include_router(analytics_router,     prefix="/api/v1")
app.include_router(knowledge_router,     prefix="/api/v1")
app.include_router(model_stats_router,   prefix="/api/v1")
app.include_router(routing_router,       prefix="/api/v1")
app.include_router(teams_router,         prefix="/api/v1")
app.include_router(manager_router,       prefix="/api/v1")
app.include_router(assets_router,        prefix="/api/v1")
app.include_router(team_chat_ws_router)


@app.get("/")
async def root():
    return {"status": "ok", "app": settings.APP_NAME}


@app.get("/health")
async def health():
    db_ok = False
    try:
        db = next(get_db())
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception as exc:
        logger.error("Health-check DB probe failed: %s", exc)

    status = "healthy" if db_ok else "degraded"
    return {"status": status, "db": db_ok}


@app.get("/ready")
async def ready():
    """Kubernetes/load-balancer readiness probe.
    Returns 200 only after the lifespan startup (embedder warm, migrations done).
    Use this as readinessProbe — not /health — to prevent premature traffic routing."""
    if not _server_ready:
        from fastapi import Response as _Resp
        return _Resp(status_code=503, content='{"ready":false}', media_type="application/json")
    return {"ready": True}