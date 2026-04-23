from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.v1 import api_router
from app.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.db.session import async_engine

configure_logging()
log = get_logger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Voice Agent QA Platform",
        version="0.1.0",
        description="Test AI voice agents via Retell AI with persona-driven calls and LLM-judged evaluations.",
    )

    if settings.ui_cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[o.strip() for o in settings.ui_cors_origins.split(",") if o.strip()],
            allow_credentials=True,
            allow_methods=["GET"],
            allow_headers=["*"],
            expose_headers=["Cache-Control"],
        )

    register_exception_handlers(app)

    app.include_router(api_router, prefix="/api/v1")

    @app.get("/health/live", tags=["health"])
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready", tags=["health"])
    async def ready() -> dict[str, str]:
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ok", "env": settings.environment}

    return app


app = create_app()
