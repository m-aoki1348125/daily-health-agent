from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class MealEstimateResult(BaseModel):
    estimated_calories: int = Field(ge=0)
    confidence: str
    summary: str
    meal_items: list[str] = Field(default_factory=list)
    rationale: str
    provider: str
    model_name: str


class MealRecordInput(BaseModel):
    source_message_id: str
    line_user_id: str
    consumed_at: datetime
    image_mime_type: str
    estimated_calories: int
    confidence: str
    summary: str
    meal_items: list[str] = Field(default_factory=list)
    rationale: str
    image_drive_file_id: str | None = None
    analysis_drive_file_id: str | None = None
    provider: str
    model_name: str
