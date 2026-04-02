from __future__ import annotations

from app.schemas.health_features import DailyMetricInput, FitbitDayRaw


class FeatureBuilder:
    def build_daily_metrics(
        self,
        raw: FitbitDayRaw,
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
            raw_drive_file_id=raw_drive_file_id,
            bedtime_start=raw.sleep.start_time,
        )
