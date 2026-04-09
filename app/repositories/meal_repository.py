from __future__ import annotations

from collections.abc import Sequence
from datetime import date

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

    def list_for_date(self, meal_date: date) -> list[MealRecord]:
        stmt: Select[tuple[MealRecord]] = (
            select(MealRecord)
            .where(MealRecord.meal_date == meal_date)
            .order_by(MealRecord.consumed_at)
        )
        return list(self.session.scalars(stmt))

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
