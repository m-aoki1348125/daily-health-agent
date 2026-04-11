from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.clients.line_client import MockLineClient
from app.config.settings import Settings
from app.db.models import MealRecord
from app.repositories.line_state_repository import LineStateRepository
from app.repositories.meal_repository import MealRepository
from app.services.meal_reminder_service import MealReminderService


def test_meal_reminder_service_pushes_when_meals_look_missing(
    session: Session,
    settings: Settings,
) -> None:
    line_client = MockLineClient()
    service = MealReminderService(
        settings=settings,
        line_client=line_client,
        meal_repository=MealRepository(session),
        line_state_repository=LineStateRepository(session),
    )

    sent = service.send_if_needed(date(2026, 4, 1))
    session.commit()

    assert sent is True
    assert line_client.sent_messages
    assert "食事記録の確認" in line_client.sent_messages[0][1]
    state = LineStateRepository(session).get(settings.line_user_id)
    assert state is not None
    assert state.intent == "meal_reminder_followup"


def test_meal_reminder_service_skips_when_enough_meals_are_registered(
    session: Session,
    settings: Settings,
) -> None:
    session.add_all(
        [
            MealRecord(
                source_message_id="meal-a",
                meal_date=date(2026, 4, 1),
                consumed_at=datetime(2026, 4, 1, 8, 0, tzinfo=ZoneInfo("Asia/Tokyo")),
                line_user_id=settings.line_user_id,
                image_mime_type="image/jpeg",
                estimated_calories=450,
                confidence="medium",
                summary="朝食",
                meal_items_json=["パン"],
                rationale="test",
                provider="mock",
                model_name="mock",
            ),
            MealRecord(
                source_message_id="meal-b",
                meal_date=date(2026, 4, 1),
                consumed_at=datetime(2026, 4, 1, 12, 0, tzinfo=ZoneInfo("Asia/Tokyo")),
                line_user_id=settings.line_user_id,
                image_mime_type="image/jpeg",
                estimated_calories=600,
                confidence="medium",
                summary="昼食",
                meal_items_json=["定食"],
                rationale="test",
                provider="mock",
                model_name="mock",
            ),
        ]
    )
    session.commit()

    line_client = MockLineClient()
    rich_settings = Settings.model_validate(
        {
            **settings.model_dump(),
            "meal_reminder_min_count": 2,
            "meal_reminder_min_calories": 900,
        }
    )
    service = MealReminderService(
        settings=rich_settings,
        line_client=line_client,
        meal_repository=MealRepository(session),
        line_state_repository=LineStateRepository(session),
    )

    sent = service.send_if_needed(date(2026, 4, 1))
    session.commit()

    assert sent is False
    assert not line_client.sent_messages
