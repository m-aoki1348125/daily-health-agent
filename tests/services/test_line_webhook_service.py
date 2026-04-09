from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app.clients.drive_client import LocalDriveClient
from app.clients.line_client import MockLineClient
from app.clients.llm_factory import MockLLMProvider
from app.config.settings import Settings
from app.repositories.advice_repository import AdviceRepository
from app.repositories.line_state_repository import LineStateRepository
from app.repositories.meal_repository import MealRepository
from app.repositories.metrics_repository import MetricsRepository
from app.services.health_chat_service import HealthChatService
from app.services.line_webhook_service import LineWebhookService
from app.services.meal_logging_service import MealLoggingService


def test_line_webhook_service_processes_image_and_non_image_messages(
    session: Session,
    tmp_path: Path,
) -> None:
    settings = Settings(
        database_url="sqlite+pysqlite:///:memory:",
        google_drive_mode="local",
        drive_local_root=str(tmp_path / "drive"),
        fitbit_client_mode="mock",
        line_client_mode="mock",
        llm_provider="mock",
        line_user_id="U-default",
    )
    line_client = MockLineClient()
    line_client.message_contents["meal-image-1"] = (b"fake-image", "image/jpeg")
    meal_logging_service = MealLoggingService(
        settings=settings,
        line_client=line_client,
        drive_client=LocalDriveClient(str(tmp_path / "drive")),
        llm_provider=MockLLMProvider(),
        meal_repository=MealRepository(session),
    )
    service = LineWebhookService(
        meal_logging_service=meal_logging_service,
        health_chat_service=HealthChatService(
            settings=settings,
            drive_client=LocalDriveClient(str(tmp_path / "drive")),
            llm_provider=MockLLMProvider(),
            meal_repository=MealRepository(session),
            metrics_repository=MetricsRepository(session),
            advice_repository=AdviceRepository(session),
            line_state_repository=LineStateRepository(session),
            meal_logging_service=meal_logging_service,
        ),
        default_line_user_id=settings.line_user_id,
    )

    processed = service.process_events(
        {
            "events": [
                {
                    "type": "message",
                    "replyToken": "reply-text",
                    "timestamp": 1775600000000,
                    "source": {"userId": "U-line"},
                    "message": {"type": "text", "id": "text-msg-1"},
                },
                {
                    "type": "message",
                    "replyToken": "reply-image",
                    "timestamp": 1775600000000,
                    "source": {"userId": "U-line"},
                    "message": {"type": "image", "id": "meal-image-1"},
                },
            ]
        }
    )
    session.commit()

    assert processed == 2
    assert len(line_client.replied_messages) == 2
    assert "食事写真の記録" not in line_client.replied_messages[0][1]
    assert MealRepository(session).get_by_source_message_id("meal-image-1") is not None
