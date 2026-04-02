from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.batch.run_daily_job import run
from app.config.settings import Settings
from app.db.models import AdviceHistory, DailyMetric, DriveIndex, TrendFeature


def test_daily_job_end_to_end(session: Session, settings: Settings) -> None:
    result = run(session, settings)
    session.commit()

    assert result["date"] == "2026-04-02"
    assert session.scalar(select(DailyMetric)) is not None
    assert session.scalar(select(TrendFeature)) is not None
    assert session.scalar(select(AdviceHistory)) is not None
    assert session.scalar(select(DriveIndex)) is not None

    json_path = (
        Path(settings.drive_local_root)
        / "HealthAgent"
        / "daily_reports"
        / "2026"
        / "2026-04"
        / "2026-04-02_daily_report.json"
    )
    assert json_path.exists()
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["date"] == "2026-04-02"
    assert "line_message" in result
