from __future__ import annotations

import base64
import hashlib
import hmac
import logging
from collections.abc import Callable

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from app.clients.drive_client import build_drive_client
from app.clients.line_client import build_line_client
from app.clients.llm_factory import build_llm_provider
from app.config.logging import configure_logging
from app.config.settings import Settings, get_settings
from app.db.session import create_session_factory
from app.repositories.advice_repository import AdviceRepository
from app.repositories.line_state_repository import LineStateRepository
from app.repositories.meal_repository import MealRepository
from app.repositories.metrics_repository import MetricsRepository
from app.services.health_chat_service import HealthChatService
from app.services.line_webhook_service import LineWebhookService
from app.services.meal_logging_service import MealLoggingService


def create_app(settings_factory: Callable[[], Settings] = get_settings) -> FastAPI:
    settings = settings_factory()
    configure_logging(settings.log_level)
    session_factory = create_session_factory(settings)
    app = FastAPI(title="daily-health-agent-line-webhook")
    logger = logging.getLogger(__name__)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post(settings.line_webhook_path)
    async def line_webhook(request: Request) -> JSONResponse:
        body = await request.body()
        signature = request.headers.get("x-line-signature", "")
        if not _is_valid_signature(settings, body, signature):
            raise HTTPException(status_code=401, detail="invalid signature")
        payload = await request.json()
        processed = 0
        with session_factory() as session:
            line_client = build_line_client(settings)
            drive_client = build_drive_client(settings)
            llm_provider = build_llm_provider(settings)
            meal_logging_service = MealLoggingService(
                settings=settings,
                line_client=line_client,
                drive_client=drive_client,
                llm_provider=llm_provider,
                meal_repository=MealRepository(session),
            )
            health_chat_service = HealthChatService(
                settings=settings,
                drive_client=drive_client,
                llm_provider=llm_provider,
                meal_repository=MealRepository(session),
                metrics_repository=MetricsRepository(session),
                advice_repository=AdviceRepository(session),
                line_state_repository=LineStateRepository(session),
                meal_logging_service=meal_logging_service,
            )
            processed = LineWebhookService(
                meal_logging_service=meal_logging_service,
                health_chat_service=health_chat_service,
                default_line_user_id=settings.line_user_id,
            ).process_events(payload)
            session.commit()
        logger.info("processed line webhook events", extra={"processed_count": processed})
        return JSONResponse({"ok": True, "processed": processed})

    return app


def _is_valid_signature(settings: Settings, body: bytes, signature: str) -> bool:
    if not settings.line_channel_secret or settings.line_channel_secret == "__DISABLED__":
        return True
    digest = hmac.new(
        settings.line_channel_secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(expected, signature)


app = create_app()
