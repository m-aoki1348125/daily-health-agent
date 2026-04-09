from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.meal_logging_service import MealLoggingService


@dataclass
class LineWebhookService:
    meal_logging_service: MealLoggingService
    default_line_user_id: str

    def process_events(self, payload: dict[str, Any]) -> int:
        events = payload.get("events", [])
        processed = 0
        for event in events:
            if event.get("type") != "message":
                continue
            reply_token = str(event.get("replyToken", ""))
            message = event.get("message", {})
            if message.get("type") != "image":
                if reply_token:
                    self.meal_logging_service.line_client.reply_message(
                        reply_token,
                        "食事写真を送ると、推定カロリーを記録して明朝の健康アドバイスへ反映します。",
                    )
                continue
            source = event.get("source", {})
            self.meal_logging_service.process_image_message(
                message_id=str(message.get("id")),
                reply_token=reply_token,
                line_user_id=str(source.get("userId") or self.default_line_user_id),
                event_timestamp_ms=int(event.get("timestamp")),
            )
            processed += 1
        return processed
