from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.db.models import MealRecord
from app.schemas.meal_estimate import MealRecordInput


class MealRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def flush(self) -> None:
        self.session.flush()

    def upsert(self, meal: MealRecordInput) -> MealRecord:
        entity = self.get_by_source_message_id(meal.source_message_id)
        if entity is None:
            entity = MealRecord(source_message_id=meal.source_message_id)
            self.session.add(entity)
        entity.meal_date = meal.consumed_at.date()
        entity.consumed_at = meal.consumed_at
        entity.line_user_id = meal.line_user_id
        entity.image_mime_type = meal.image_mime_type
        entity.estimated_calories = meal.estimated_calories
        entity.confidence = meal.confidence
        entity.summary = meal.summary
        entity.meal_items_json = meal.meal_items
        entity.rationale = meal.rationale
        entity.image_drive_file_id = meal.image_drive_file_id
        entity.analysis_drive_file_id = meal.analysis_drive_file_id
        entity.provider = meal.provider
        entity.model_name = meal.model_name
        return entity

    def get_by_source_message_id(self, source_message_id: str) -> MealRecord | None:
        stmt: Select[tuple[MealRecord]] = select(MealRecord).where(
            MealRecord.source_message_id == source_message_id
        )
        return self.session.scalar(stmt)

    def get_by_id(self, meal_id: int) -> MealRecord | None:
        return self.session.get(MealRecord, meal_id)

    def list_for_date(self, meal_date: date) -> list[MealRecord]:
        stmt: Select[tuple[MealRecord]] = (
            select(MealRecord)
            .where(MealRecord.meal_date == meal_date)
            .order_by(MealRecord.consumed_at)
        )
        return list(self.session.scalars(stmt))

    def list_for_user_and_date(self, line_user_id: str, meal_date: date) -> list[MealRecord]:
        stmt: Select[tuple[MealRecord]] = (
            select(MealRecord)
            .where(MealRecord.line_user_id == line_user_id, MealRecord.meal_date == meal_date)
            .order_by(MealRecord.consumed_at)
        )
        return list(self.session.scalars(stmt))

    def get_latest_for_user(
        self,
        line_user_id: str,
        meal_date: date | None = None,
    ) -> MealRecord | None:
        stmt: Select[tuple[MealRecord]] = select(MealRecord).where(
            MealRecord.line_user_id == line_user_id
        )
        if meal_date is not None:
            stmt = stmt.where(MealRecord.meal_date == meal_date)
        stmt = stmt.order_by(MealRecord.consumed_at.desc()).limit(1)
        return self.session.scalar(stmt)

    def delete(self, meal: MealRecord) -> None:
        self.session.delete(meal)

    def update_estimated_calories(self, meal: MealRecord, estimated_calories: int) -> MealRecord:
        meal.estimated_calories = estimated_calories
        return meal

    def update_consumed_at(self, meal: MealRecord, consumed_at: datetime) -> MealRecord:
        meal.consumed_at = consumed_at
        meal.meal_date = consumed_at.date()
        return meal

    def sum_calories_for_date(self, meal_date: date) -> int:
        stmt = select(func.coalesce(func.sum(MealRecord.estimated_calories), 0)).where(
            MealRecord.meal_date == meal_date
        )
        value = self.session.scalar(stmt)
        return int(value or 0)

    def list_recent_for_dates(self, until_date: date, limit: int = 30) -> Sequence[MealRecord]:
        stmt: Select[tuple[MealRecord]] = (
            select(MealRecord)
            .where(MealRecord.meal_date < until_date)
            .order_by(MealRecord.consumed_at.desc())
            .limit(limit)
        )
        return list(self.session.scalars(stmt))

    def list_recent_daily_totals(self, until_date: date, limit: int = 7) -> list[int]:
        stmt = (
            select(
                MealRecord.meal_date,
                func.coalesce(func.sum(MealRecord.estimated_calories), 0).label("total_calories"),
            )
            .where(MealRecord.meal_date < until_date)
            .group_by(MealRecord.meal_date)
            .order_by(MealRecord.meal_date.desc())
            .limit(limit)
        )
        rows = self.session.execute(stmt).all()
        return [int(row.total_calories or 0) for row in rows]
