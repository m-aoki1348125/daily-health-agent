from __future__ import annotations

import logging
from datetime import date, timedelta

from app.clients.drive_client import DriveClient
from app.clients.fitbit_client import FitbitClient
from app.config.settings import Settings
from app.repositories.drive_index_repository import DriveIndexRepository
from app.repositories.metrics_repository import MetricsRepository
from app.services.feature_builder import FeatureBuilder
from app.services.trend_analyzer import TrendAnalyzer


class HistoryBootstrapService:
    def __init__(
        self,
        *,
        settings: Settings,
        fitbit_client: FitbitClient,
        drive_client: DriveClient,
        metrics_repo: MetricsRepository,
        drive_index_repo: DriveIndexRepository,
        feature_builder: FeatureBuilder,
        trend_analyzer: TrendAnalyzer,
    ) -> None:
        self.settings = settings
        self.fitbit_client = fitbit_client
        self.drive_client = drive_client
        self.metrics_repo = metrics_repo
        self.drive_index_repo = drive_index_repo
        self.feature_builder = feature_builder
        self.trend_analyzer = trend_analyzer
        self.logger = logging.getLogger(__name__)

    def bootstrap(self, target_date: date) -> list[date]:
        if not self.settings.historical_bootstrap_enabled:
            return []
        lookback_days = self.settings.historical_bootstrap_days
        if lookback_days <= 0:
            return []

        start_date = target_date - timedelta(days=lookback_days)
        end_date = target_date - timedelta(days=1)
        if start_date > end_date:
            return []

        existing_dates = self.metrics_repo.list_metric_dates_in_range(start_date, end_date)
        bootstrapped_dates: list[date] = []
        current_date = start_date
        while current_date <= end_date:
            if current_date not in existing_dates:
                self._bootstrap_day(current_date)
                bootstrapped_dates.append(current_date)
            current_date += timedelta(days=1)
        if bootstrapped_dates:
            self.logger.info(
                "bootstrapped historical Fitbit days",
                extra={
                    "count": len(bootstrapped_dates),
                    "from": bootstrapped_dates[0].isoformat(),
                    "to": bootstrapped_dates[-1].isoformat(),
                },
            )
        return bootstrapped_dates

    def _bootstrap_day(self, target_date: date) -> None:
        raw = self.fitbit_client.fetch_day(target_date)
        raw_file_id = self.drive_client.store_json(
            category="raw",
            target_date=target_date,
            filename=f"{target_date.isoformat()}_fitbit_raw.json",
            payload=raw.raw_payload,
        )
        metrics = self.feature_builder.build_daily_metrics(raw, raw_drive_file_id=raw_file_id)
        self.metrics_repo.upsert_daily_metric(metrics, bedtime_start=metrics.bedtime_start)
        self.drive_index_repo.upsert_for_date(target_date, raw_file_id=raw_file_id)
        self.metrics_repo.flush()

        history = self.metrics_repo.list_recent_daily_metrics(
            target_date, limit=self.settings.historical_bootstrap_days
        )
        trend_context = self.trend_analyzer.build(metrics, history)
        self.metrics_repo.upsert_trend_feature(trend_context.current)
