"""App factory. Run with: uvicorn app.main:create_app --factory"""

import logging
import re
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import router
from app.config import Settings, get_settings
from app.db.connection import init_db
from app.errors import AppError, error_response
from app.logging_config import configure_logging, request_id_var
from app.providers import EmbeddingProvider, LLMProvider, build_providers
from app.services.ingestion import IngestionDeps, fail_interrupted_items

logger = logging.getLogger("app")

_REQUEST_ID_OK = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_HTTP_CODES = {404: ("NOT_FOUND", "Route not found"), 405: ("METHOD_NOT_ALLOWED", "Method not allowed")}


def create_app(
    settings: Settings | None = None,
    *,
    embedder: EmbeddingProvider | None = None,
    llm: LLMProvider | None = None,
    ingestion_deps: IngestionDeps | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    closable = None
    if embedder is None or llm is None:
        built_embedder, built_llm, closable = build_providers(settings)
        embedder = embedder or built_embedder
        llm = llm or built_llm

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        init_db(settings.database_path)
        interrupted = fail_interrupted_items(settings.database_path)
        logger.info(
            "startup",
            extra={
                "provider": settings.provider,
                "embedding_model": embedder.model_id,
                "db": settings.database_path,
                "interrupted_items": interrupted,
            },
        )
        yield
        if closable is not None:
            closable.close()  # type: ignore[attr-defined]

    app = FastAPI(title="AI Knowledge Inbox", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.embedder = embedder
    app.state.llm = llm
    app.state.ingestion_deps = ingestion_deps or IngestionDeps(settings=settings, embedder=embedder)

    _register_error_handlers(app)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        incoming = request.headers.get("x-request-id", "")
        request_id = incoming if _REQUEST_ID_OK.match(incoming) else uuid.uuid4().hex
        token = request_id_var.set(request_id)
        start = time.perf_counter()
        try:
            try:
                response = await call_next(request)
            except Exception:
                logger.exception("unhandled error", extra={"method": request.method, "path": request.url.path})
                response = error_response(500, "INTERNAL_ERROR", "Internal server error")
            response.headers["X-Request-ID"] = request_id
            logger.info(
                "request",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": round((time.perf_counter() - start) * 1000, 1),
                },
            )
            return response
        finally:
            request_id_var.reset(token)

    # Added last so it is outermost and error responses carry CORS headers too.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    app.include_router(router)
    return app


def _register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        details = [
            {"loc": [str(p) for p in err.get("loc", ())], "msg": err.get("msg", ""), "type": err.get("type", "")}
            for err in exc.errors()
        ]
        message = "Request validation failed"
        if details:
            loc, msg = details[0]["loc"], details[0]["msg"]
            # loc looks like ["body", "note", "content"] or ["query", "limit"]; name the field only.
            message = f"{loc[-1]}: {msg}" if len(loc) > 1 else msg
        return error_response(422, "VALIDATION_ERROR", message, details)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        code, message = _HTTP_CODES.get(exc.status_code, ("HTTP_ERROR", str(exc.detail)))
        return error_response(exc.status_code, code, message)

    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        level = logging.WARNING if exc.status_code < 500 or exc.code.startswith("PROVIDER") else logging.ERROR
        logger.log(level, "request failed", extra={"code": exc.code, "error": exc.message})
        return error_response(exc.status_code, exc.code, exc.message, exc.details)
