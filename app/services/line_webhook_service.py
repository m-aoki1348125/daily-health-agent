from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.health_chat_service import HealthChatService
from app.services.meal_logging_service import MealLoggingService


@dataclass
class LineWebhookService:
    meal_logging_service: MealLoggingService
    health_chat_service: HealthChatService
    default_line_user_id: str

    def process_events(self, payload: dict[str, Any]) -> int:
        events = payload.get("events", [])
        processed = 0
        for event in events:
            if event.get("type") != "message":
                continue
            reply_token = str(event.get("replyToken", ""))
            message = event.get("message", {})
            source = event.get("source", {})
            line_user_id = str(source.get("userId") or self.default_line_user_id)
            if message.get("type") == "text":
                if reply_token:
                    response_text = self.health_chat_service.handle_text_message(
                        text=str(message.get("text", "")),
                        line_user_id=line_user_id,
                        event_timestamp_ms=int(event.get("timestamp")),
                    )
                    self.meal_logging_service.line_client.reply_message(reply_token, response_text)
                    processed += 1
                continue
            if message.get("type") != "image":
                if reply_token:
                    self.meal_logging_service.line_client.reply_message(
                        reply_token,
                        "食事写真の記録、健康ログの確認、記録の修正ができます。"
                        " 例:『昨日の食事回数を教えて』『昨日の睡眠時間を8時間に修正』",
                    )
                    processed += 1
                continue
            self.meal_logging_service.process_image_message(
                message_id=str(message.get("id")),
                reply_token=reply_token,
                line_user_id=line_user_id,
                event_timestamp_ms=int(event.get("timestamp")),
            )
            processed += 1
        return processed
