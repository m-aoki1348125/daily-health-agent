from __future__ import annotations

from app.schemas.health_features import DailyMetricInput, FitbitDayRaw


class FeatureBuilder:
    def build_daily_metrics(
        self,
        raw: FitbitDayRaw,
        meal_calories: int | None = None,
        raw_drive_file_id: str | None = None,
    ) -> DailyMetricInput:
        return DailyMetricInput(
            date=raw.date,
            sleep_minutes=raw.sleep.total_minutes,
            sleep_efficiency=raw.sleep.efficiency,
            deep_sleep_minutes=raw.sleep.deep_minutes,
            rem_sleep_minutes=raw.sleep.rem_minutes,
            awakenings=raw.sleep.awakenings,
            resting_hr=raw.resting_hr,
            steps=raw.activity.steps,
            calories=raw.activity.calories,
            weight_kg=raw.body.weight_kg,
            bmi=raw.body.bmi,
            body_fat_percent=raw.body.body_fat_percent,
            body_logged_at=raw.body.logged_at,
            meal_calories=meal_calories,
            raw_drive_file_id=raw_drive_file_id,
            bedtime_start=raw.sleep.start_time,
        )
