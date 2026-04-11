from __future__ import annotations

import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.clients.line_client import build_line_client
from app.config.logging import configure_logging
from app.config.settings import Settings, get_settings
from app.db.session import create_session_factory
from app.repositories.line_state_repository import LineStateRepository
from app.repositories.meal_repository import MealRepository
from app.services.meal_reminder_service import MealReminderService


def resolve_target_date(settings: Settings) -> date:
    if settings.health_agent_date:
        return datetime.fromisoformat(settings.health_agent_date).date()
    return datetime.now(ZoneInfo(settings.timezone)).date()


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    session_factory = create_session_factory(settings)
    line_client = build_line_client(settings)
    target_date = resolve_target_date(settings)

    with session_factory() as session:
        sent = MealReminderService(
            settings=settings,
            line_client=line_client,
            meal_repository=MealRepository(session),
            line_state_repository=LineStateRepository(session),
        ).send_if_needed(target_date)
        session.commit()

    logging.getLogger(__name__).info(
        "meal reminder job completed",
        extra={"date": target_date.isoformat(), "sent": sent},
    )


if __name__ == "__main__":
    main()
