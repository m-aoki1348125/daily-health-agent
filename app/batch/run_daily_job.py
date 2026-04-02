from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.clients.drive_client import build_drive_client
from app.clients.fitbit_client import build_fitbit_client
from app.clients.line_client import build_line_client
from app.clients.llm_factory import build_llm_provider
from app.config.logging import configure_logging
from app.config.settings import Settings, get_settings
from app.db.base import Base
from app.db.session import create_engine_from_settings, create_session_factory
from app.repositories.advice_repository import AdviceRepository
from app.repositories.drive_index_repository import DriveIndexRepository
from app.repositories.metrics_repository import MetricsRepository
from app.services.feature_builder import FeatureBuilder
from app.services.history_bootstrap_service import HistoryBootstrapService
from app.services.notification_service import NotificationService
from app.services.report_service import ReportService
from app.services.rule_engine import RuleEngine
from app.services.trend_analyzer import TrendAnalyzer


def resolve_target_date(settings: Settings) -> date:
    if settings.health_agent_date:
        return datetime.fromisoformat(settings.health_agent_date).date()
    now = datetime.now(ZoneInfo(settings.timezone))
    return now.date() - timedelta(days=1)


def run(session: Session, settings: Settings) -> dict[str, str]:
    logger = logging.getLogger(__name__)
    target_date = resolve_target_date(settings)
    logger.info("starting daily job", extra={"date": target_date.isoformat()})

    fitbit_client = build_fitbit_client(settings)
    drive_client = build_drive_client(settings)
    line_client = build_line_client(settings)
    llm_provider = build_llm_provider(settings)

    feature_builder = FeatureBuilder()
    trend_analyzer = TrendAnalyzer(settings)
    rule_engine = RuleEngine(settings)
    report_service = ReportService(llm_provider)
    notification_service = NotificationService(line_client, settings)

    metrics_repo = MetricsRepository(session)
    advice_repo = AdviceRepository(session)
    drive_index_repo = DriveIndexRepository(session)
    history_bootstrap_service = HistoryBootstrapService(
        settings=settings,
        fitbit_client=fitbit_client,
        drive_client=drive_client,
        metrics_repo=metrics_repo,
        drive_index_repo=drive_index_repo,
        feature_builder=feature_builder,
        trend_analyzer=trend_analyzer,
    )

    history_bootstrap_service.bootstrap(target_date)

    raw = fitbit_client.fetch_day(target_date)
    raw_filename = f"{target_date.isoformat()}_fitbit_raw.json"
    raw_file_id = drive_client.store_json(
        category="raw", target_date=target_date, filename=raw_filename, payload=raw.raw_payload
    )

    metrics = feature_builder.build_daily_metrics(raw, raw_drive_file_id=raw_file_id)
    metrics_repo.upsert_daily_metric(metrics, bedtime_start=metrics.bedtime_start)
    drive_index_repo.upsert_for_date(target_date, raw_file_id=raw_file_id)
    metrics_repo.flush()

    history = metrics_repo.list_recent_daily_metrics(target_date, limit=90)
    trend_context = trend_analyzer.build(metrics, history)
    metrics_repo.upsert_trend_feature(trend_context.current)

    rule_eval = rule_engine.evaluate(metrics, trend_context.current)
    advice = report_service.build_advice(metrics, trend_context, rule_eval)
    report = report_service.build_report(metrics, trend_context, rule_eval, advice, raw_file_id)

    report_json_id = drive_client.store_json(
        category="daily_reports",
        target_date=target_date,
        filename=f"{target_date.isoformat()}_daily_report.json",
        payload=report_service.to_json_payload(report),
    )
    report_md_id = drive_client.store_markdown(
        category="daily_reports",
        target_date=target_date,
        filename=f"{target_date.isoformat()}_daily_report.md",
        content=report_service.to_markdown(report),
    )
    report.daily_json_drive_file_id = report_json_id
    report.daily_md_drive_file_id = report_md_id
    drive_index_repo.upsert_for_date(
        target_date, daily_json_file_id=report_json_id, daily_md_file_id=report_md_id
    )
    advice_repo.upsert_advice(target_date, advice, report_json_id)

    session.flush()
    line_message = notification_service.send(report)
    logger.info("daily job completed", extra={"date": target_date.isoformat()})
    return {
        "date": target_date.isoformat(),
        "raw_file_id": raw_file_id,
        "daily_json_file_id": report_json_id,
        "daily_md_file_id": report_md_id,
        "line_message": line_message,
    }


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    engine = create_engine_from_settings(settings)
    session_factory = create_session_factory(settings)
    Base.metadata.create_all(engine)
    with session_factory() as session:
        result = run(session, settings)
        session.commit()
    logging.getLogger(__name__).info("result summary: %s", result["date"])


if __name__ == "__main__":
    main()
