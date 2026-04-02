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


class DailyReport(BaseModel):
    date: date
    generated_at: datetime
    metrics: DailyMetricInput
    trends: TrendFeatureInput
    rule_evaluation: RuleEvaluation
    advice: AdviceResult
    raw_drive_file_id: str | None = None
    daily_json_drive_file_id: str | None = None
    daily_md_drive_file_id: str | None = None
    source_summary: dict[str, Any] = Field(default_factory=dict)
