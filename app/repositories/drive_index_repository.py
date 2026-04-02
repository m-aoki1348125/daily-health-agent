from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.db.models import DriveIndex


class DriveIndexRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert_for_date(
        self,
        report_date: date,
        *,
        raw_file_id: str | None = None,
        daily_json_file_id: str | None = None,
        daily_md_file_id: str | None = None,
        weekly_file_id: str | None = None,
        monthly_file_id: str | None = None,
    ) -> None:
        entity = self._get_existing(report_date)
        if entity is None:
            entity = DriveIndex(date=report_date)
            self.session.add(entity)
        if raw_file_id is not None:
            entity.raw_file_id = raw_file_id
        if daily_json_file_id is not None:
            entity.daily_json_file_id = daily_json_file_id
        if daily_md_file_id is not None:
            entity.daily_md_file_id = daily_md_file_id
        if weekly_file_id is not None:
            entity.weekly_file_id = weekly_file_id
        if monthly_file_id is not None:
            entity.monthly_file_id = monthly_file_id

    def get(self, report_date: date) -> DriveIndex | None:
        return self.session.get(DriveIndex, report_date)

    def _get_existing(self, report_date: date) -> DriveIndex | None:
        entity = self.session.get(DriveIndex, report_date)
        if entity is not None:
            return entity
        for pending in self.session.new:
            if isinstance(pending, DriveIndex) and pending.date == report_date:
                return pending
        return None
