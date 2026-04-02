from __future__ import annotations

from pydantic import BaseModel, Field


class AdviceResult(BaseModel):
    risk_level: str
    summary: str
    key_findings: list[str] = Field(default_factory=list)
    today_actions: list[str] = Field(default_factory=list)
    exercise_advice: str
    sleep_advice: str
    caffeine_advice: str
    medical_note: str
    long_term_comment: str
    provider: str
    model_name: str
