from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.batch.run_daily_job import run
from app.config.settings import Settings
from app.db.models import AdviceHistory, DailyMetric, DriveIndex, TrendFeature


def test_daily_job_is_idempotent(session: Session, settings: Settings) -> None:
    run(session, settings)
    session.commit()
    run(session, settings)
    session.commit()

    assert session.scalar(select(func.count()).select_from(DailyMetric)) == 1
    assert session.scalar(select(func.count()).select_from(TrendFeature)) == 1
    assert session.scalar(select(func.count()).select_from(AdviceHistory)) == 1
    assert session.scalar(select(func.count()).select_from(DriveIndex)) == 1
