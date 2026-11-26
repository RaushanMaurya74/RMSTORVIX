"""FastAPI application entry point and configuration."""

from contextlib import asynccontextmanager
import json
import logging
from pathlib import Path

from fastapi import FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.health import router as health_router
from app.api.router import api_router
from app.core.config import PROJECT_ROOT, Settings, get_settings
from app.db.session import (
    classify_db_error,
    get_session_factory,
    redact_connection_secrets,
    reset_db_engine,
)
from scripts.seed_admin import ensure_initial_admin

logger = logging.getLogger("app.main")
FRONTEND_DIR = PROJECT_ROOT / "frontend"


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Manage startup and shutdown resources cleanly across local and serverless runtimes."""
    settings = get_settings()
    if settings.effective_storage_backend == "local":
        for folder in (
            settings.resolved_pdf_dir,
            settings.resolved_signature_dir,
            settings.resolved_logo_dir,
        ):
            try:
                folder.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass
    try:
        session_factory = get_session_factory()
        with session_factory() as db:
            if inspect(db.get_bind()).has_table("admin_users"):
                ensure_initial_admin(db, settings)
    except Exception as exc:
        # Startup stays resilient when DB is temporarily unreachable; /health reports details.
        logger.warning(
            "Startup admin check skipped (%s): %s",
            type(exc).__name__,
            redact_connection_secrets(str(exc)),
        )
    yield
    reset_db_engine()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Application factory creating a configured FastAPI instance."""
    active_settings = settings or get_settings()

    app = FastAPI(
        title=active_settings.app_name,
        version=active_settings.app_version,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=active_settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def no_stale_frontend_cache(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
        )
        path = request.url.path
        if (
            path == "/"
            or path.startswith("/css/")
            or path.startswith("/js/")
            or response.headers.get("content-type", "").startswith("text/html")
        ):
            response.headers["Cache-Control"] = "no-store, max-age=0"
        return response

    register_exception_handlers(app)

    # Health endpoint at root (/health) and versioned API (/api/v1/health)
    app.include_router(health_router)
    app.include_router(api_router)

    # Public, non-secret runtime config script loaded by frontend HTML pages
    @app.get("/app-config.js", include_in_schema=False)
    async def serve_app_config() -> Response:
        cfg = {
            "appEnv": active_settings.app_env,
            "apiBaseUrl": active_settings.api_base_url.strip().rstrip("/"),
        }
        return Response(
            content=f"window.__RMSTORVIX_CONFIG__ = Object.freeze({json.dumps(cfg)});",
            media_type="application/javascript; charset=utf-8",
            headers={"Cache-Control": "no-store, max-age=0"},
        )

    mount_frontend(app, FRONTEND_DIR)

    return app


def register_exception_handlers(app: FastAPI) -> None:
    """Register consistent JSON error handlers that never leak stack traces or secrets."""

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": "http_error",
                    "message": exc.detail if isinstance(exc.detail, str) else "Request failed.",
                }
            },
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_exception_handler(_: Request, exc: SQLAlchemyError) -> JSONResponse:
        active_settings = get_settings()
        logger.error(
            "Database request failed (%s) target=%s: %s",
            type(exc).__name__,
            active_settings.safe_database_target(),
            redact_connection_secrets(str(exc)),
        )
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "error": {
                    "code": "database_unavailable",
                    "message": classify_db_error(exc, settings=active_settings),
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = [
            {
                "field": ".".join(str(part) for part in err.get("loc", [])),
                "message": err.get("msg", "Invalid value."),
            }
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Request validation failed.",
                    "details": details,
                }
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_: Request, __: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "An unexpected server error occurred.",
                }
            },
        )


def mount_frontend(app: FastAPI, frontend_dir: Path) -> None:
    """Serve the modular frontend shell when present."""
    if not frontend_dir.is_dir():
        return

    css_dir = frontend_dir / "css"
    js_dir = frontend_dir / "js"
    if css_dir.is_dir():
        app.mount("/css", StaticFiles(directory=css_dir), name="frontend-css")
    if js_dir.is_dir():
        app.mount("/js", StaticFiles(directory=js_dir), name="frontend-js")

    index_file = frontend_dir / "index.html"
    if index_file.is_file():

        @app.get("/", include_in_schema=False)
        @app.get("/dashboard", include_in_schema=False)
        @app.get("/invoices", include_in_schema=False)
        @app.get("/invoices/new", include_in_schema=False)
        @app.get("/invoices/{invoice_id:int}", include_in_schema=False)
        @app.get("/customers", include_in_schema=False)
        @app.get("/products", include_in_schema=False)
        @app.get("/inventory", include_in_schema=False)
        @app.get("/payments", include_in_schema=False)
        @app.get("/reports", include_in_schema=False)
        @app.get("/notifications", include_in_schema=False)
        @app.get("/subscription", include_in_schema=False)
        @app.get("/activation", include_in_schema=False)
        @app.get("/settings", include_in_schema=False)
        async def serve_index() -> FileResponse:
            return FileResponse(index_file)

    admin_file = frontend_dir / "admin.html"
    if admin_file.is_file():

        @app.get("/admin", include_in_schema=False)
        @app.get("/admin/{admin_path:path}", include_in_schema=False)
        async def serve_admin() -> FileResponse:
            return FileResponse(admin_file)


app = create_app()
