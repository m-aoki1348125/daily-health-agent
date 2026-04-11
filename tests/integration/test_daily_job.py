from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.batch.run_daily_job import run
from app.config.settings import Settings
from app.db.models import AdviceHistory, DailyMetric, DriveIndex, MealRecord, TrendFeature
from app.schemas.health_features import ActivitySummary, FitbitDayRaw, SleepSummary


def test_daily_job_end_to_end(session: Session, settings: Settings) -> None:
    session.add(
        MealRecord(
            source_message_id="meal-msg-1",
            meal_date=date(2026, 4, 1),
            consumed_at=datetime(2026, 4, 1, 12, 0),
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
    assert payload["source_summary"]["sleep_source_date"] == "2026-04-02"
    assert payload["source_summary"]["activity_source_date"] == "2026-04-01"
    assert payload["source_summary"]["meal_source_date"] == "2026-04-01"
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


def test_daily_job_uses_today_sleep_and_yesterday_activity_sources(
    session: Session,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings.historical_bootstrap_enabled = False
    fetched_dates: list[date] = []

    class RecordingFitbitClient:
        def fetch_day(self, target_date: date) -> FitbitDayRaw:
            fetched_dates.append(target_date)
            offset = (target_date - date(2026, 4, 1)).days
            return FitbitDayRaw(
                date=target_date,
                sleep=SleepSummary(
                    total_minutes=300 + offset,
                    efficiency=90.0,
                    deep_minutes=60,
                    rem_minutes=70,
                    awakenings=1,
                    start_time=f"{target_date.isoformat()}T00:15:00+09:00",
                ),
                resting_hr=55 + offset,
                activity=ActivitySummary(
                    steps=5000 + offset,
                    calories=2000 + offset,
                ),
                raw_payload={"date": target_date.isoformat()},
            )

    monkeypatch.setattr(
        "app.batch.run_daily_job.build_fitbit_client",
        lambda _: RecordingFitbitClient(),
    )

    result = run(session, settings)
    session.commit()

    metric = session.get(DailyMetric, date(2026, 4, 2))
    assert result["date"] == "2026-04-02"
    assert fetched_dates == [date(2026, 4, 2), date(2026, 4, 1)]
    assert metric is not None
    assert metric.sleep_minutes == 301
    assert metric.steps == 5000
