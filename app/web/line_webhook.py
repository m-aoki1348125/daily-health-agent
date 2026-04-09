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
from app.db.base import Base
from app.db.session import create_engine_from_settings, create_session_factory
from app.repositories.meal_repository import MealRepository
from app.services.meal_logging_service import MealLoggingService


def create_app(settings_factory: Callable[[], Settings] = get_settings) -> FastAPI:
    settings = settings_factory()
    configure_logging(settings.log_level)
    engine = create_engine_from_settings(settings)
    Base.metadata.create_all(engine)
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
        events = payload.get("events", [])
        processed = 0
        with session_factory() as session:
            service = MealLoggingService(
                settings=settings,
                line_client=build_line_client(settings),
                drive_client=build_drive_client(settings),
                llm_provider=build_llm_provider(settings),
                meal_repository=MealRepository(session),
            )
            for event in events:
                if event.get("type") != "message":
                    continue
                reply_token = str(event.get("replyToken", ""))
                message = event.get("message", {})
                if message.get("type") != "image":
                    if reply_token:
                        service.line_client.reply_message(
                            reply_token,
                            "食事写真を送ると、推定カロリーを記録して明朝の健康アドバイスへ反映します。",
                        )
                    continue
                source = event.get("source", {})
                service.process_image_message(
                    message_id=str(message.get("id")),
                    reply_token=reply_token,
                    line_user_id=str(source.get("userId") or settings.line_user_id),
                    event_timestamp_ms=int(event.get("timestamp")),
                )
                processed += 1
            session.commit()
        logger.info("processed line webhook events", extra={"processed_count": processed})
        return JSONResponse({"ok": True, "processed": processed})

    return app


def _is_valid_signature(settings: Settings, body: bytes, signature: str) -> bool:
    if not settings.line_channel_secret:
        return True
    digest = hmac.new(
        settings.line_channel_secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(expected, signature)


app = create_app()
