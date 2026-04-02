from __future__ import annotations

from datetime import date

from app.config.settings import Settings
from app.schemas.health_features import DailyMetricInput, TrendFeatureInput
from app.services.rule_engine import RuleEngine


def test_rule_engine_red_when_multiple_signals() -> None:
    engine = RuleEngine(Settings())
    metrics = DailyMetricInput(
        date=date(2026, 4, 2),
        sleep_minutes=320,
        sleep_efficiency=80,
        deep_sleep_minutes=40,
        rem_sleep_minutes=60,
        awakenings=4,
        resting_hr=68,
        steps=12000,
        calories=2200,
    )
    trends = TrendFeatureInput(
        date=metrics.date,
        sleep_vs_14d_avg=-80,
        resting_hr_vs_30d_avg=6,
        sleep_debt_streak_days=4,
        bedtime_drift_minutes=50,
        recovery_score=30,
    )

    result = engine.evaluate(metrics, trends)

    assert result.risk_level == "red"
    assert "sleep deficit detected" in result.reasons
    assert "elevated resting heart rate" in result.reasons


def test_rule_engine_handles_missing_data_fallback() -> None:
    engine = RuleEngine(Settings())
    metrics = DailyMetricInput(
        date=date(2026, 4, 2),
        sleep_minutes=430,
        sleep_efficiency=90,
        deep_sleep_minutes=80,
        rem_sleep_minutes=70,
        awakenings=1,
        resting_hr=None,
        steps=5000,
        calories=1800,
    )
    trends = TrendFeatureInput(date=metrics.date, recovery_score=70)

    result = engine.evaluate(metrics, trends)

    assert result.fallback_used is True
    assert result.risk_level == "yellow"
