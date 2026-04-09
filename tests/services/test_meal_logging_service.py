from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.clients.drive_client import LocalDriveClient
from app.clients.line_client import MockLineClient
from app.clients.llm_factory import MockLLMProvider
from app.config.settings import Settings
from app.repositories.meal_repository import MealRepository
from app.services.meal_logging_service import MealLoggingService


def test_meal_logging_service_records_meal_and_drive_artifacts(
    session: Session, settings: Settings, tmp_path: Path
) -> None:
    line_client = MockLineClient()
    line_client.message_contents["msg-1"] = (b"fake-jpeg", "image/jpeg")
    service = MealLoggingService(
        settings=settings,
        line_client=line_client,
        drive_client=LocalDriveClient(str(tmp_path / "drive")),
        llm_provider=MockLLMProvider(),
        meal_repository=MealRepository(session),
    )

    reply = service.process_image_message(
        message_id="msg-1",
        reply_token="reply-1",
        line_user_id="U-test",
        event_timestamp_ms=int(
            datetime(2026, 4, 1, 12, 30, tzinfo=ZoneInfo("Asia/Tokyo")).timestamp() * 1000
        ),
    )
    session.commit()

    meal = MealRepository(session).get_by_source_message_id("msg-1")
    assert meal is not None
    assert meal.estimated_calories == 650
    assert "推定摂取カロリーは 650 kcal" in reply
    assert line_client.replied_messages

    summary_path = (
        tmp_path
        / "drive"
        / "HealthAgent"
        / "meal_records"
        / "2026"
        / "2026-04"
        / "2026-04-01_meal_summary.json"
    )
    assert summary_path.exists()
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert payload["total_estimated_calories"] == 650
    assert payload["meal_count"] == 1
