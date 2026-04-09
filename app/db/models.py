from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DailyMetric(Base):
    __tablename__ = "daily_metrics"

    date: Mapped[date] = mapped_column(Date, primary_key=True)
    sleep_minutes: Mapped[int | None] = mapped_column(Integer)
    sleep_efficiency: Mapped[float | None] = mapped_column(Float)
    deep_sleep_minutes: Mapped[int | None] = mapped_column(Integer)
    rem_sleep_minutes: Mapped[int | None] = mapped_column(Integer)
    awakenings: Mapped[int | None] = mapped_column(Integer)
    resting_hr: Mapped[int | None] = mapped_column(Integer)
    steps: Mapped[int | None] = mapped_column(Integer)
    calories: Mapped[int | None] = mapped_column(Integer)
    meal_calories: Mapped[int | None] = mapped_column(Integer)
    raw_drive_file_id: Mapped[str | None] = mapped_column(String(255))
    bedtime_start: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now()
    )


class TrendFeature(Base):
    __tablename__ = "trend_features"

    date: Mapped[date] = mapped_column(Date, primary_key=True)
    sleep_vs_14d_avg: Mapped[float | None] = mapped_column(Float)
    resting_hr_vs_30d_avg: Mapped[float | None] = mapped_column(Float)
    meal_calories_vs_7d_avg: Mapped[float | None] = mapped_column(Float)
    sleep_debt_streak_days: Mapped[int] = mapped_column(Integer, default=0)
    bedtime_drift_minutes: Mapped[float | None] = mapped_column(Float)
    recovery_score: Mapped[int] = mapped_column(Integer, default=50)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now()
    )


class AdviceHistory(Base):
    __tablename__ = "advice_history"

    date: Mapped[date] = mapped_column(Date, primary_key=True)
    risk_level: Mapped[str] = mapped_column(String(32))
    summary: Mapped[str] = mapped_column(Text)
    key_findings_json: Mapped[list[str]] = mapped_column(JSON)
    today_actions_json: Mapped[list[str]] = mapped_column(JSON)
    exercise_advice: Mapped[str] = mapped_column(Text)
    sleep_advice: Mapped[str] = mapped_column(Text)
    caffeine_advice: Mapped[str] = mapped_column(Text)
    medical_note: Mapped[str] = mapped_column(Text)
    long_term_comment: Mapped[str] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(64))
    model_name: Mapped[str] = mapped_column(String(128))
    daily_report_drive_file_id: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now()
    )


class DriveIndex(Base):
    __tablename__ = "drive_index"

    date: Mapped[date] = mapped_column(Date, primary_key=True)
    raw_file_id: Mapped[str | None] = mapped_column(String(255))
    daily_json_file_id: Mapped[str | None] = mapped_column(String(255))
    daily_md_file_id: Mapped[str | None] = mapped_column(String(255))
    weekly_file_id: Mapped[str | None] = mapped_column(String(255))
    monthly_file_id: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now()
    )


class MealRecord(Base):
    __tablename__ = "meal_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_message_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    meal_date: Mapped[date] = mapped_column(Date, index=True)
    consumed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    line_user_id: Mapped[str] = mapped_column(String(128), index=True)
    image_mime_type: Mapped[str] = mapped_column(String(64))
    estimated_calories: Mapped[int] = mapped_column(Integer)
    confidence: Mapped[str] = mapped_column(String(32))
    summary: Mapped[str] = mapped_column(Text)
    meal_items_json: Mapped[list[str]] = mapped_column(JSON)
    rationale: Mapped[str] = mapped_column(Text)
    image_drive_file_id: Mapped[str | None] = mapped_column(String(255))
    analysis_drive_file_id: Mapped[str | None] = mapped_column(String(255))
    provider: Mapped[str] = mapped_column(String(64))
    model_name: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now()
    )


class LineConversationState(Base):
    __tablename__ = "line_conversation_states"

    line_user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    intent: Mapped[str] = mapped_column(String(64))
    state_json: Mapped[dict[str, object]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now()
    )
