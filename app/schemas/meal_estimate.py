from __future__ import annotations

from datetime import date as date_type
from datetime import datetime

from pydantic import BaseModel, Field


class MealComponentEstimate(BaseModel):
    item_name: str
    estimated_calories: int = Field(ge=0)
    portion_basis: str


class MealEstimateResult(BaseModel):
    estimated_calories: int = Field(ge=0)
    calorie_range_low: int | None = Field(default=None, ge=0)
    calorie_range_high: int | None = Field(default=None, ge=0)
    confidence: str
    summary: str
    meal_items: list[str] = Field(default_factory=list)
    components: list[MealComponentEstimate] = Field(default_factory=list)
    rationale: str
    provider: str
    model_name: str


class ParsedMealEntry(BaseModel):
    time_text: str | None = None
    summary: str
    meal_items: list[str] = Field(default_factory=list)
    estimated_calories: int = Field(ge=0)
    confidence: str


class MealTextParseResult(BaseModel):
    meals: list[ParsedMealEntry] = Field(default_factory=list)
    note: str | None = None
    provider: str
    model_name: str


class MealRecordInput(BaseModel):
    source_message_id: str
    line_user_id: str
    meal_date: date_type
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
