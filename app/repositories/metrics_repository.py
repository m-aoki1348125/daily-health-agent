from __future__ import annotations

from datetime import date

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.db.models import DailyMetric, TrendFeature
from app.schemas.health_features import DailyMetricInput, TrendFeatureInput


class MetricsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def flush(self) -> None:
        self.session.flush()

    def upsert_daily_metric(
        self,
        metric: DailyMetricInput,
        bedtime_start: str | None = None,
    ) -> None:
        entity = self.session.get(DailyMetric, metric.date)
        if entity is None:
            entity = DailyMetric(date=metric.date)
            self.session.add(entity)
        entity.sleep_minutes = metric.sleep_minutes
        entity.sleep_efficiency = metric.sleep_efficiency
        entity.deep_sleep_minutes = metric.deep_sleep_minutes
        entity.rem_sleep_minutes = metric.rem_sleep_minutes
        entity.awakenings = metric.awakenings
        entity.resting_hr = metric.resting_hr
        entity.steps = metric.steps
        entity.calories = metric.calories
        entity.raw_drive_file_id = metric.raw_drive_file_id
        entity.bedtime_start = bedtime_start

    def upsert_trend_feature(self, trend: TrendFeatureInput) -> None:
        entity = self.session.get(TrendFeature, trend.date)
        if entity is None:
            entity = TrendFeature(date=trend.date)
            self.session.add(entity)
        entity.sleep_vs_14d_avg = trend.sleep_vs_14d_avg
        entity.resting_hr_vs_30d_avg = trend.resting_hr_vs_30d_avg
        entity.sleep_debt_streak_days = trend.sleep_debt_streak_days
        entity.bedtime_drift_minutes = trend.bedtime_drift_minutes
        entity.recovery_score = trend.recovery_score

    def list_recent_daily_metrics(self, until_date: date, limit: int = 90) -> list[DailyMetric]:
        stmt: Select[tuple[DailyMetric]] = (
            select(DailyMetric)
            .where(DailyMetric.date < until_date)
            .order_by(DailyMetric.date.desc())
            .limit(limit)
        )
        return list(self.session.scalars(stmt))

    def list_metric_dates_in_range(self, start_date: date, end_date: date) -> set[date]:
        stmt: Select[tuple[date]] = select(DailyMetric.date).where(
            DailyMetric.date >= start_date,
            DailyMetric.date <= end_date,
        )
        return set(self.session.scalars(stmt))

    def get_daily_metric(self, metric_date: date) -> DailyMetric | None:
        return self.session.get(DailyMetric, metric_date)
