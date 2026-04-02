from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DailyMetric, TrendFeature
from app.repositories.metrics_repository import MetricsRepository
from app.schemas.health_features import DailyMetricInput, TrendFeatureInput


def test_metrics_repository_upsert(session: Session) -> None:
    repo = MetricsRepository(session)
    metric = DailyMetricInput(
        date=date(2026, 4, 2),
        sleep_minutes=360,
        sleep_efficiency=90,
        deep_sleep_minutes=70,
        rem_sleep_minutes=70,
        awakenings=2,
        resting_hr=60,
        steps=8000,
        calories=2100,
        raw_drive_file_id="raw1",
    )
    repo.upsert_daily_metric(metric, bedtime_start="2026-04-02T00:30:00+09:00")
    repo.upsert_trend_feature(
        TrendFeatureInput(
            date=metric.date,
            sleep_vs_14d_avg=-30,
            resting_hr_vs_30d_avg=2,
            sleep_debt_streak_days=1,
            bedtime_drift_minutes=15,
            recovery_score=70,
        )
    )
    session.commit()

    repo.upsert_daily_metric(
        metric.model_copy(update={"steps": 9000}),
        bedtime_start=metric.bedtime_start,
    )
    session.commit()

    stored_metric = session.scalar(select(DailyMetric).where(DailyMetric.date == metric.date))
    stored_trend = session.scalar(select(TrendFeature).where(TrendFeature.date == metric.date))
    assert stored_metric is not None
    assert stored_trend is not None
    assert stored_metric.steps == 9000
