from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.clients.drive_client import build_drive_client
from app.clients.fitbit_client import build_fitbit_client
from app.clients.line_client import build_line_client
from app.clients.llm_factory import build_llm_provider
from app.config.logging import configure_logging
from app.config.settings import Settings, get_settings
from app.db.session import create_session_factory
from app.repositories.advice_repository import AdviceRepository
from app.repositories.drive_index_repository import DriveIndexRepository
from app.repositories.meal_repository import MealRepository
from app.repositories.metrics_repository import MetricsRepository
from app.schemas.health_features import FitbitDayRaw
from app.services.feature_builder import FeatureBuilder
from app.services.history_bootstrap_service import HistoryBootstrapService
from app.services.notification_service import NotificationService
from app.services.report_service import ReportService
from app.services.rule_engine import RuleEngine
from app.services.trend_analyzer import TrendAnalyzer


@dataclass(frozen=True)
class MorningReportWindow:
    report_date: date
    sleep_source_date: date
    activity_source_date: date
    meal_source_date: date


def resolve_report_date(settings: Settings) -> date:
    if settings.health_agent_date:
        return datetime.fromisoformat(settings.health_agent_date).date()
    now = datetime.now(ZoneInfo(settings.timezone))
    return now.date()


def resolve_morning_report_window(settings: Settings) -> MorningReportWindow:
    report_date = resolve_report_date(settings)
    previous_date = report_date - timedelta(days=1)
    return MorningReportWindow(
        report_date=report_date,
        sleep_source_date=report_date,
        activity_source_date=previous_date,
        meal_source_date=previous_date,
    )


def _select_sleep_snapshot(
    *,
    preferred: FitbitDayRaw,
    fallback: FitbitDayRaw,
) -> tuple[FitbitDayRaw, bool]:
    preferred_sleep = preferred.sleep
    if preferred_sleep.total_minutes > 0:
        return preferred, False
    if preferred_sleep.start_time:
        return preferred, False
    return fallback, True


def run(session: Session, settings: Settings) -> dict[str, str]:
    logger = logging.getLogger(__name__)
    report_window = resolve_morning_report_window(settings)
    report_date = report_window.report_date
    logger.info(
        "starting daily job",
        extra={
            "date": report_date.isoformat(),
            "sleep_source_date": report_window.sleep_source_date.isoformat(),
            "activity_source_date": report_window.activity_source_date.isoformat(),
        },
    )

    fitbit_client = build_fitbit_client(settings)
    drive_client = build_drive_client(settings)
    line_client = build_line_client(settings)
    llm_provider = build_llm_provider(settings)

    feature_builder = FeatureBuilder()
    trend_analyzer = TrendAnalyzer(settings)
    rule_engine = RuleEngine(settings)
    report_service = ReportService(llm_provider, settings)
    notification_service = NotificationService(line_client, settings)

    metrics_repo = MetricsRepository(session)
    advice_repo = AdviceRepository(session)
    drive_index_repo = DriveIndexRepository(session)
    meal_repo = MealRepository(session)
    history_bootstrap_service = HistoryBootstrapService(
        settings=settings,
        fitbit_client=fitbit_client,
        drive_client=drive_client,
        metrics_repo=metrics_repo,
        drive_index_repo=drive_index_repo,
        feature_builder=feature_builder,
        trend_analyzer=trend_analyzer,
    )

    history_bootstrap_service.bootstrap(report_date)

    sleep_day_raw = fitbit_client.fetch_day(report_window.sleep_source_date)
    activity_day_raw = (
        sleep_day_raw
        if report_window.activity_source_date == report_window.sleep_source_date
        else fitbit_client.fetch_day(report_window.activity_source_date)
    )
    selected_sleep_raw, sleep_fallback_used = _select_sleep_snapshot(
        preferred=sleep_day_raw,
        fallback=activity_day_raw,
    )
    raw_payload = {
        "report_date": report_date.isoformat(),
        "sources": {
            "sleep": report_window.sleep_source_date.isoformat(),
            "activity": report_window.activity_source_date.isoformat(),
            "meal": report_window.meal_source_date.isoformat(),
            "sleep_fallback_used": sleep_fallback_used,
            "sleep_effective_source": (
                report_window.activity_source_date.isoformat()
                if sleep_fallback_used
                else report_window.sleep_source_date.isoformat()
            ),
        },
        "sleep_day": sleep_day_raw.raw_payload,
        "activity_day": activity_day_raw.raw_payload,
    }
    raw_filename = f"{report_date.isoformat()}_fitbit_raw.json"
    raw_file_id = drive_client.store_json(
        category="raw", target_date=report_date, filename=raw_filename, payload=raw_payload
    )

    meals = meal_repo.list_for_date(report_window.meal_source_date)
    recent_meal_daily_totals = meal_repo.list_recent_daily_totals(
        report_window.meal_source_date, limit=7
    )
    meal_calories = meal_repo.sum_calories_for_date(report_window.meal_source_date)
    composite_raw = selected_sleep_raw.model_copy(
        update={
            "date": report_date,
            "activity": activity_day_raw.activity,
            "raw_payload": raw_payload,
        }
    )
    metrics = feature_builder.build_daily_metrics(
        composite_raw,
        meal_calories=meal_calories or None,
        raw_drive_file_id=raw_file_id,
    )
    metrics_repo.upsert_daily_metric(metrics, bedtime_start=metrics.bedtime_start)
    drive_index_repo.upsert_for_date(report_date, raw_file_id=raw_file_id)
    metrics_repo.flush()

    history = metrics_repo.list_recent_daily_metrics(report_date, limit=90)
    trend_context = trend_analyzer.build(metrics, history)
    metrics_repo.upsert_trend_feature(trend_context.current)

    rule_eval = rule_engine.evaluate(metrics, trend_context.current)
    meal_summary = report_service.build_meal_summary(
        meals=meals,
        recent_daily_totals=recent_meal_daily_totals,
        meal_calorie_delta=trend_context.current.meal_calories_vs_7d_avg,
    )
    advice = report_service.build_advice(metrics, trend_context, rule_eval, meal_summary)
    report = report_service.build_report(
        metrics,
        trend_context,
        rule_eval,
        advice,
        meal_summary,
        raw_file_id,
        source_summary={
            "sleep_source_date": report_window.sleep_source_date.isoformat(),
            "activity_source_date": report_window.activity_source_date.isoformat(),
            "meal_source_date": report_window.meal_source_date.isoformat(),
            "sleep_fallback_used": sleep_fallback_used,
        },
    )

    report_json_id = drive_client.store_json(
        category="daily_reports",
        target_date=report_date,
        filename=f"{report_date.isoformat()}_daily_report.json",
        payload=report_service.to_json_payload(report),
    )
    report_md_id = drive_client.store_markdown(
        category="daily_reports",
        target_date=report_date,
        filename=f"{report_date.isoformat()}_daily_report.md",
        content=report_service.to_markdown(report),
    )
    report.daily_json_drive_file_id = report_json_id
    report.daily_md_drive_file_id = report_md_id
    drive_index_repo.upsert_for_date(
        report_date, daily_json_file_id=report_json_id, daily_md_file_id=report_md_id
    )
    advice_repo.upsert_advice(report_date, advice, report_json_id)

    session.flush()
    line_message = notification_service.send(report)
    logger.info("daily job completed", extra={"date": report_date.isoformat()})
    return {
        "date": report_date.isoformat(),
        "raw_file_id": raw_file_id,
        "daily_json_file_id": report_json_id,
        "daily_md_file_id": report_md_id,
        "line_message": line_message,
    }


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    session_factory = create_session_factory(settings)
    with session_factory() as session:
        result = run(session, settings)
        session.commit()
    logging.getLogger(__name__).info("result summary: %s", result["date"])


if __name__ == "__main__":
    main()
