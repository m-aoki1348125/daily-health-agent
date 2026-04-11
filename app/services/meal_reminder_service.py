from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.clients.line_client import LineClient
from app.config.settings import Settings
from app.repositories.line_state_repository import LineStateRepository
from app.repositories.meal_repository import MealRepository


@dataclass
class MealReminderService:
    settings: Settings
    line_client: LineClient
    meal_repository: MealRepository
    line_state_repository: LineStateRepository

    def send_if_needed(self, target_date: date) -> bool:
        meals = self.meal_repository.list_for_user_and_date(self.settings.line_user_id, target_date)
        meal_count = len(meals)
        total_calories = sum(meal.estimated_calories for meal in meals)
        if (
            meal_count >= self.settings.meal_reminder_min_count
            and total_calories >= self.settings.meal_reminder_min_calories
        ):
            logging.getLogger(__name__).info(
                "meal reminder skipped; enough meals registered",
                extra={
                    "date": target_date.isoformat(),
                    "meal_count": meal_count,
                    "total_calories": total_calories,
                },
            )
            return False

        self.line_state_repository.upsert(
            self.settings.line_user_id,
            "meal_reminder_followup",
            {
                "date": target_date.isoformat(),
                "expires_at": (
                    datetime.now(ZoneInfo(self.settings.timezone)) + timedelta(hours=8)
                ).isoformat(),
            },
        )
        self.line_client.push_message(
            self.settings.line_user_id,
            self._build_message(
                target_date=target_date,
                meal_count=meal_count,
                total_calories=total_calories,
            ),
        )
        return True

    @staticmethod
    def _build_message(*, target_date: date, meal_count: int, total_calories: int) -> str:
        return (
            f"🍽️ 食事記録の確認 {target_date.isoformat()}\n"
            f"現在の登録は {meal_count} 回 / {total_calories} kcal です。\n"
            "登録漏れがありそうなら、"
            "『朝7:30におにぎり、昼12:15にラーメン、夜19:30にカレー』のように送ってください。\n"
            "食事写真の前後に『18:30ごろ食べた』と送っても反映できます。"
        )
