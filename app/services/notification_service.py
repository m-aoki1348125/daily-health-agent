from __future__ import annotations

import logging

from app.clients.line_client import LineClient
from app.config.settings import Settings
from app.schemas.report_schema import DailyReport


class NotificationService:
    def __init__(self, line_client: LineClient, settings: Settings) -> None:
        self.line_client = line_client
        self.settings = settings
        self.logger = logging.getLogger(__name__)

    def build_message(self, report: DailyReport) -> str:
        trends = report.trends
        advice = report.advice
        weekly_trends = list(report.source_summary.get("weekly_trends", []))
        monthly_trends = list(report.source_summary.get("monthly_trends", []))
        sleep_hours = report.metrics.sleep_minutes // 60
        sleep_minutes = report.metrics.sleep_minutes % 60
        sleep_delta = (
            f"{trends.sleep_vs_14d_avg:+.0f}分" if trends.sleep_vs_14d_avg is not None else "N/A"
        )
        resting_hr_text = self._build_resting_hr_text(report)
        fact_bullets = "\n".join(f"- {item}" for item in advice.key_findings[:3])
        if not fact_bullets:
            fact_bullets = "- 目立つ悪化サインはありません"
        today_actions = "\n".join(f"- {item}" for item in advice.today_actions[:3])
        if not today_actions:
            today_actions = "- 生活リズムを整えながら様子を見てください"
        long_term_items = [
            *(str(item) for item in weekly_trends[:2]),
            *(str(item) for item in monthly_trends[:1]),
            advice.long_term_comment,
        ]
        long_term_lines = "\n".join(f"- {item}" for item in long_term_items if item)
        if not long_term_lines:
            long_term_lines = "- 過去データが増えるほど中長期の傾向を詳しく分析できます"
        return (
            f"今日の健康サマリー {report.date.isoformat()}\n\n"
            f"コンディション: {report.rule_evaluation.risk_level.title()}\n"
            f"睡眠: {sleep_hours}時間{sleep_minutes:02d}分"
            f"（14日平均より {sleep_delta}）\n"
            f"安静時心拍: {resting_hr_text}\n"
            f"前日歩数: {report.metrics.steps:,}歩\n\n"
            f"昨日の事実\n{fact_bullets}\n\n"
            f"今日のおすすめ\n{today_actions}\n\n"
            f"中長期の分析\n{long_term_lines}\n\n"
            "詳細レポートは Drive に保存済みです"
        )

    @staticmethod
    def _build_resting_hr_text(report: DailyReport) -> str:
        current = report.metrics.resting_hr
        delta = report.trends.resting_hr_vs_30d_avg
        if current is None:
            return "N/A（Fitbit から当日の安静時心拍が取得できませんでした）"
        if delta is None:
            return f"{current} bpm（30日平均との差分は未算出）"
        return f"{current} bpm（30日平均より {delta:+.0f} bpm）"

    def send(self, report: DailyReport) -> str:
        message = self.build_message(report)
        try:
            self.line_client.push_message(self.settings.line_user_id, message)
        except Exception:
            self.logger.exception("line notification failed")
        return message
