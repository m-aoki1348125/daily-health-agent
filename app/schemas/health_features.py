from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field


class SleepSummary(BaseModel):
    total_minutes: int
    efficiency: float
    deep_minutes: int
    rem_minutes: int
    awakenings: int
    start_time: str | None = None


class ActivitySummary(BaseModel):
    steps: int
    calories: int


class FitbitDayRaw(BaseModel):
    date: date
    sleep: SleepSummary
    resting_hr: int | None = None
    activity: ActivitySummary
    raw_payload: dict[str, Any]


class DailyMetricInput(BaseModel):
    date: date
    sleep_minutes: int
    sleep_efficiency: float
    deep_sleep_minutes: int
    rem_sleep_minutes: int
    awakenings: int
    resting_hr: int | None
    steps: int
    calories: int
    raw_drive_file_id: str | None = None
    bedtime_start: str | None = None


class TrendFeatureInput(BaseModel):
    date: date
    sleep_vs_14d_avg: float | None = None
    resting_hr_vs_30d_avg: float | None = None
    sleep_debt_streak_days: int = 0
    bedtime_drift_minutes: float | None = None
    recovery_score: int = 50


class TrendContext(BaseModel):
    current: TrendFeatureInput
    weekly_trends: list[str] = Field(default_factory=list)
    monthly_trends: list[str] = Field(default_factory=list)
    lookback_metrics: list[DailyMetricInput] = Field(default_factory=list)
