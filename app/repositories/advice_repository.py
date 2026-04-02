from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.db.models import AdviceHistory
from app.schemas.advice_result import AdviceResult


class AdviceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert_advice(
        self, report_date: date, advice: AdviceResult, daily_report_drive_file_id: str | None
    ) -> None:
        entity = self.session.get(AdviceHistory, report_date)
        if entity is None:
            entity = AdviceHistory(date=report_date)
            self.session.add(entity)
        entity.risk_level = advice.risk_level
        entity.summary = advice.summary
        entity.key_findings_json = advice.key_findings
        entity.today_actions_json = advice.today_actions
        entity.exercise_advice = advice.exercise_advice
        entity.sleep_advice = advice.sleep_advice
        entity.caffeine_advice = advice.caffeine_advice
        entity.medical_note = advice.medical_note
        entity.long_term_comment = advice.long_term_comment
        entity.provider = advice.provider
        entity.model_name = advice.model_name
        entity.daily_report_drive_file_id = daily_report_drive_file_id

    def get_advice(self, report_date: date) -> AdviceHistory | None:
        return self.session.get(AdviceHistory, report_date)
