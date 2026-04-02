from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, cast

import httpx

from app.config.settings import Settings
from app.schemas.health_features import ActivitySummary, FitbitDayRaw, SleepSummary
from app.services.feature_builder import FeatureBuilder
from app.services.history_bootstrap_service import HistoryBootstrapService
from app.services.trend_analyzer import TrendAnalyzer


@dataclass
class StubFitbitClient:
    fetched_dates: list[date]
    failing_date: date | None = None

    def fetch_day(self, target_date: date) -> FitbitDayRaw:
        self.fetched_dates.append(target_date)
        if self.failing_date == target_date:
            request = httpx.Request("GET", f"https://api.fitbit.com/day/{target_date.isoformat()}")
            response = httpx.Response(429, request=request)
            raise httpx.HTTPStatusError("rate limited", request=request, response=response)
        return FitbitDayRaw(
            date=target_date,
            sleep=SleepSummary(
                total_minutes=420,
                efficiency=90,
                deep_minutes=80,
                rem_minutes=90,
                awakenings=1,
                start_time=f"{target_date.isoformat()}T00:30:00+09:00",
            ),
            resting_hr=58,
            activity=ActivitySummary(steps=7000, calories=2100),
            raw_payload={"date": target_date.isoformat()},
        )


@dataclass
class StubDriveClient:
    stored_dates: list[date]

    def store_json(
        self, *, category: str, target_date: date, filename: str, payload: dict[str, object]
    ) -> str:
        self.stored_dates.append(target_date)
        return f"{category}-{filename}"


class StubMetricsRepo:
    def __init__(self, existing_dates: list[date] | None = None) -> None:
        self.existing_dates = existing_dates or []
        self.upserted_dates: list[date] = []

    def list_metric_dates_in_range(self, start_date: date, end_date: date) -> list[date]:
        return [value for value in self.existing_dates if start_date <= value <= end_date]

    def upsert_daily_metric(self, metrics: Any, bedtime_start: str | None) -> None:
        self.upserted_dates.append(metrics.date)

    def flush(self) -> None:
        return None

    def list_recent_daily_metrics(self, until_date: date, limit: int = 90) -> list[object]:
        return []

    def upsert_trend_feature(self, trend: Any) -> None:
        return None


class StubDriveIndexRepo:
    def upsert_for_date(self, target_date: date, **kwargs: str) -> None:
        return None


def test_bootstrap_prioritizes_recent_missing_days_and_caps_per_run() -> None:
    settings = Settings(
        historical_bootstrap_enabled=True,
        historical_bootstrap_days=10,
        historical_bootstrap_max_days_per_run=3,
    )
    fetched_dates: list[date] = []
    drive_dates: list[date] = []
    service = HistoryBootstrapService(
        settings=settings,
        fitbit_client=cast(Any, StubFitbitClient(fetched_dates=fetched_dates)),
        drive_client=cast(Any, StubDriveClient(stored_dates=drive_dates)),
        metrics_repo=cast(Any, StubMetricsRepo()),
        drive_index_repo=cast(Any, StubDriveIndexRepo()),
        feature_builder=FeatureBuilder(),
        trend_analyzer=TrendAnalyzer(settings),
    )

    bootstrapped = service.bootstrap(date(2026, 4, 2))

    assert bootstrapped == [date(2026, 4, 1), date(2026, 3, 31), date(2026, 3, 30)]
    assert fetched_dates == bootstrapped
    assert drive_dates == bootstrapped


def test_bootstrap_stops_on_rate_limit_and_returns_completed_recent_days() -> None:
    settings = Settings(
        historical_bootstrap_enabled=True,
        historical_bootstrap_days=5,
        historical_bootstrap_max_days_per_run=5,
    )
    fetched_dates: list[date] = []
    service = HistoryBootstrapService(
        settings=settings,
        fitbit_client=cast(
            Any,
            StubFitbitClient(
                fetched_dates=fetched_dates,
                failing_date=date(2026, 3, 31),
            ),
        ),
        drive_client=cast(Any, StubDriveClient(stored_dates=[])),
        metrics_repo=cast(Any, StubMetricsRepo()),
        drive_index_repo=cast(Any, StubDriveIndexRepo()),
        feature_builder=FeatureBuilder(),
        trend_analyzer=TrendAnalyzer(settings),
    )

    bootstrapped = service.bootstrap(date(2026, 4, 2))

    assert bootstrapped == [date(2026, 4, 1)]
    assert fetched_dates[:2] == [date(2026, 4, 1), date(2026, 3, 31)]
