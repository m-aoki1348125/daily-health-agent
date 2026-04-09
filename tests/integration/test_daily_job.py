from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.batch.run_daily_job import run
from app.config.settings import Settings
from app.db.models import AdviceHistory, DailyMetric, DriveIndex, MealRecord, TrendFeature


def test_daily_job_end_to_end(session: Session, settings: Settings) -> None:
    session.add(
        MealRecord(
            source_message_id="meal-msg-1",
            meal_date=date(2026, 4, 2),
            consumed_at=datetime(2026, 4, 2, 12, 0),
            line_user_id="U-test",
            image_mime_type="image/jpeg",
            estimated_calories=720,
            confidence="medium",
            summary="昼食の定食です。",
            meal_items_json=["ごはん", "焼き魚", "味噌汁"],
            rationale="一人前の定食に見えるためです。",
            provider="mock",
            model_name="mock-llm",
        )
    )
    session.flush()
    result = run(session, settings)
    session.commit()

    assert result["date"] == "2026-04-02"
    daily_metrics = session.scalars(select(DailyMetric).order_by(DailyMetric.date)).all()
    trend_features = session.scalars(select(TrendFeature).order_by(TrendFeature.date)).all()
    assert len(daily_metrics) == settings.historical_bootstrap_days + 1
    assert len(trend_features) == settings.historical_bootstrap_days + 1
    assert session.scalar(select(AdviceHistory)) is not None
    drive_index_rows = session.scalars(select(DriveIndex).order_by(DriveIndex.date)).all()
    assert len(drive_index_rows) == settings.historical_bootstrap_days + 1

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
    assert payload["metrics"]["meal_calories"] == 720
    assert payload["trends"]["sleep_vs_14d_avg"] == 0
    assert "line_message" in result

    raw_path = (
        Path(settings.drive_local_root)
        / "HealthAgent"
        / "raw"
        / "2026"
        / "2026-03"
        / "2026-03-19_fitbit_raw.json"
    )
    assert raw_path.exists()
