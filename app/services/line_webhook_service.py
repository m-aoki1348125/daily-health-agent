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
    restrict_to_configured_user: bool = True

    def process_events(self, payload: dict[str, Any]) -> int:
        events = payload.get("events", [])
        processed = 0
        for event in events:
            if event.get("type") != "message":
                continue
            reply_token = str(event.get("replyToken", ""))
            message = event.get("message", {})
            source = event.get("source", {})
            source_line_user_id = str(source.get("userId") or "")
            if not self._is_authorized_user(source_line_user_id):
                if reply_token:
                    self.meal_logging_service.line_client.reply_message(
                        reply_token,
                        "このアカウントは個人利用のため、登録済みの本人アカウントからのみ利用できます。",
                    )
                    processed += 1
                continue
            line_user_id = source_line_user_id or self.default_line_user_id
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

    def _is_authorized_user(self, source_line_user_id: str) -> bool:
        if not self.restrict_to_configured_user:
            return True
        configured = self.default_line_user_id.strip()
        if not configured or configured == "mock-user":
            return True
        return source_line_user_id == configured
