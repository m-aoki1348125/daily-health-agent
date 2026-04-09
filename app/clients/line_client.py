from __future__ import annotations

from abc import ABC, abstractmethod

import httpx

from app.config.settings import Settings


class LineClient(ABC):
    @abstractmethod
    def push_message(self, user_id: str, text: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def reply_message(self, reply_token: str, text: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def fetch_message_content(self, message_id: str) -> tuple[bytes, str]:
        raise NotImplementedError


class MockLineClient(LineClient):
    def __init__(self) -> None:
        self.sent_messages: list[tuple[str, str]] = []
        self.replied_messages: list[tuple[str, str]] = []
        self.message_contents: dict[str, tuple[bytes, str]] = {}

    def push_message(self, user_id: str, text: str) -> None:
        self.sent_messages.append((user_id, text))

    def reply_message(self, reply_token: str, text: str) -> None:
        self.replied_messages.append((reply_token, text))

    def fetch_message_content(self, message_id: str) -> tuple[bytes, str]:
        return self.message_contents[message_id]


class LineMessagingApiClient(LineClient):
    def __init__(self, access_token: str, timeout_seconds: int) -> None:
        self.access_token = access_token
        self.timeout_seconds = timeout_seconds

    def push_message(self, user_id: str, text: str) -> None:
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "to": user_id,
            "messages": [{"type": "text", "text": text}],
        }
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(
                "https://api.line.me/v2/bot/message/push",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()

    def reply_message(self, reply_token: str, text: str) -> None:
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "replyToken": reply_token,
            "messages": [{"type": "text", "text": text}],
        }
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(
                "https://api.line.me/v2/bot/message/reply",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()

    def fetch_message_content(self, message_id: str) -> tuple[bytes, str]:
        headers = {"Authorization": f"Bearer {self.access_token}"}
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.get(
                f"https://api-data.line.me/v2/bot/message/{message_id}/content",
                headers=headers,
            )
            response.raise_for_status()
        mime_type = response.headers.get("content-type", "image/jpeg")
        return response.content, mime_type


def build_line_client(settings: Settings) -> LineClient:
    if settings.line_client_mode == "api":
        if not settings.line_channel_access_token:
            raise ValueError("LINE API mode requires line_channel_access_token")
        return LineMessagingApiClient(
            settings.line_channel_access_token,
            settings.request_timeout_seconds,
        )
    return MockLineClient()
