"""FastAPI application entry point."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app import __version__
from app.api.v1 import api_router
from app.core.config import settings
from app.core.errors import RepoMedicError
from app.core.logging import configure_logging, get_logger
from app.db.session import init_db
from app.services import events
from app.services.workspace import sweep_stale_workspaces

configure_logging()
logger = get_logger(__name__)

DESCRIPTION = """
Repository-aware AI code review that detects architectural, security, performance
and reliability issues — and validates every proposed fix before it reaches your branch.

**How it differs from an LLM wrapper**

* Deterministic scanners (Ruff, Bandit, Mypy, ESLint, tsc, Semgrep, Gitleaks, OSV) run first.
* AST analyzers reason about scope, loops and async context — not text patterns.
* A repository knowledge graph resolves imports, calls and blast radius.
* Retrieval sends only the relevant chunks to the model; never the whole repository.
* Every suggested patch is parsed, linted, type-checked, security-scanned and tested
  before a human is asked to approve it.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    events.set_event_loop(asyncio.get_running_loop())
    init_db()
    sweep_stale_workspaces()

    if settings.demo_mode:
        from app.services.demo import seed_demo_workspace

        try:
            seed_demo_workspace()
        except Exception as exc:  # demo data must never block startup
            logger.warning("demo.seed_failed", error=str(exc))

    logger.info(
        "app.started",
        version=__version__,
        environment=settings.app_env,
        demo_mode=settings.demo_mode,
        sandbox_mode=settings.sandbox_mode.value,
        llm_provider=settings.default_llm_provider,
        cors_origins=settings.cors_origins,
    )
    yield
    logger.info("app.stopped")


app = FastAPI(
    title=f"{settings.app_name} API",
    description=DESCRIPTION,
    version=__version__,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    contact={"name": "RepoMedic", "url": settings.app_url},
    license_info={"name": "MIT"},
)

# Strict CORS: only the configured frontend origin, with credentials for the
# HTTP-only session cookie.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
    expose_headers=["X-Request-Id"],
    max_age=600,
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Baseline hardening headers on every response."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        if settings.is_production:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response


app.add_middleware(SecurityHeadersMiddleware)


@app.exception_handler(RepoMedicError)
async def repomedic_error_handler(_request: Request, exc: RepoMedicError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.to_payload())


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": "Request validation failed",
                "details": {"errors": exc.errors()[:10]},
            }
        },
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("request.unhandled_error", path=request.url.path)
    message = str(exc) if not settings.is_production else "An unexpected error occurred"
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "internal_error", "message": message, "details": {}}},
    )


app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/", include_in_schema=False)
def root() -> dict:
    return {
        "name": settings.app_name,
        "version": __version__,
        "docs": "/docs",
        "api": settings.api_v1_prefix,
    }
