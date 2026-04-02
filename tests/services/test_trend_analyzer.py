from __future__ import annotations

from datetime import date, timedelta

from app.config.settings import Settings
from app.db.models import DailyMetric
from app.schemas.health_features import DailyMetricInput
from app.services.trend_analyzer import TrendAnalyzer


def test_trend_analyzer_builds_expected_deltas() -> None:
    analyzer = TrendAnalyzer(Settings())
    current = DailyMetricInput(
        date=date(2026, 4, 2),
        sleep_minutes=360,
        sleep_efficiency=88,
        deep_sleep_minutes=70,
        rem_sleep_minutes=80,
        awakenings=2,
        resting_hr=62,
        steps=9000,
        calories=2000,
        bedtime_start="2026-04-02T00:50:00+09:00",
    )
    history = [
        DailyMetric(
            date=date(2026, 4, 1) - timedelta(days=i),
            sleep_minutes=360 if i == 0 else 420,
            sleep_efficiency=90,
            deep_sleep_minutes=80,
            rem_sleep_minutes=85,
            awakenings=1,
            resting_hr=58,
            steps=7000,
            calories=1900,
            bedtime_start="2026-04-01T00:10:00+09:00",
        )
        for i in range(14)
    ]

    context = analyzer.build(current, history)

    assert round(context.current.sleep_vs_14d_avg or 0, 1) == -55.7
    assert round(context.current.resting_hr_vs_30d_avg or 0, 1) == 4.0
    assert context.current.sleep_debt_streak_days == 2
    assert context.current.bedtime_drift_minutes == 40
