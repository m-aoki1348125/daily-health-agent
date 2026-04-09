from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.advice_result import AdviceResult
from app.schemas.health_features import DailyMetricInput, TrendFeatureInput


class RuleEvaluation(BaseModel):
    risk_level: str
    reasons: list[str] = Field(default_factory=list)
    explanations: list[str] = Field(default_factory=list)
    fallback_used: bool = False


class MealContextItem(BaseModel):
    consumed_at: datetime
    estimated_calories: int
    summary: str
    meal_items: list[str] = Field(default_factory=list)
    confidence: str


class DailyMealSummary(BaseModel):
    total_calories: int = 0
    meal_count: int = 0
    average_calories: float | None = None
    max_calories: int | None = None
    meals: list[MealContextItem] = Field(default_factory=list)
    recent_daily_totals: list[int] = Field(default_factory=list)
    trend_notes: list[str] = Field(default_factory=list)


class DailyReport(BaseModel):
    date: date
    generated_at: datetime
    metrics: DailyMetricInput
    trends: TrendFeatureInput
    rule_evaluation: RuleEvaluation
    advice: AdviceResult
    meal_summary: DailyMealSummary = Field(default_factory=DailyMealSummary)
    raw_drive_file_id: str | None = None
    daily_json_drive_file_id: str | None = None
    daily_md_drive_file_id: str | None = None
    source_summary: dict[str, Any] = Field(default_factory=dict)
