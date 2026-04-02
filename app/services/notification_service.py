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
        condition_text = self._build_condition_text(report.rule_evaluation.risk_level)
        resting_hr_text = self._build_resting_hr_text(report)
        body_condition_lines = self._build_body_condition_lines(report)
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
        footer = "詳細レポートは Drive に保存済みです"
        if advice.provider == "fallback":
            footer = f"{footer} (Not LLM)"
        return (
            f"今日の健康サマリー {report.date.isoformat()}\n\n"
            f"コンディション: {condition_text}\n"
            f"睡眠: {sleep_hours}時間{sleep_minutes:02d}分"
            f"（14日平均より {sleep_delta}）\n"
            f"安静時心拍: {resting_hr_text}\n"
            f"前日歩数: {report.metrics.steps:,}歩\n\n"
            f"今日の体調\n{body_condition_lines}\n\n"
            f"今日のアドバイス\n{today_actions}\n\n"
            f"中長期の分析\n{long_term_lines}\n\n"
            f"{footer}"
        )

    @staticmethod
    def _build_condition_text(risk_level: str) -> str:
        normalized = risk_level.lower()
        if normalized == "green":
            return "🟢 Green"
        if normalized == "yellow":
            return "🟡 Yellow"
        if normalized == "red":
            return "🔴 Red"
        return risk_level.title()

    def _build_body_condition_lines(self, report: DailyReport) -> str:
        findings = [self._normalize_condition_line(item) for item in report.advice.key_findings[:4]]
        findings = [item for item in findings if item]
        if findings:
            return "\n".join(findings)
        return "\n".join(self._build_fallback_condition_lines(report))

    @staticmethod
    def _normalize_condition_line(item: str) -> str:
        text = item.strip()
        if not text:
            return ""
        if text.startswith(("☀️", "⛅", "🌧️")):
            return f"- {text}"
        return f"- ⛅ {text}"

    @staticmethod
    def _build_fallback_condition_lines(report: DailyReport) -> list[str]:
        metrics = report.metrics
        trends = report.trends
        sleep_icon = "☀️"
        sleep_text = "睡眠の回復感は安定しています"
        if trends.sleep_vs_14d_avg is not None and trends.sleep_vs_14d_avg < -30:
            sleep_icon = "🌧️"
            sleep_text = "睡眠量が直近平均より少なく、疲れが残りやすい状態です"
        elif trends.sleep_vs_14d_avg is not None and trends.sleep_vs_14d_avg < 30:
            sleep_icon = "⛅"
            sleep_text = "睡眠はおおむね平常ですが、回復余地が少しあります"

        hr_icon = "⛅"
        hr_text = "安静時心拍は比較データを蓄積中です"
        if metrics.resting_hr is not None and trends.resting_hr_vs_30d_avg is not None:
            if trends.resting_hr_vs_30d_avg <= -1:
                hr_icon = "☀️"
                hr_text = "安静時心拍は落ち着いていて回復傾向です"
            elif trends.resting_hr_vs_30d_avg >= 3:
                hr_icon = "🌧️"
                hr_text = "安静時心拍がやや高めで負荷が残っている可能性があります"
            else:
                hr_icon = "⛅"
                hr_text = "安静時心拍は大きな乱れなく推移しています"

        activity_icon = "⛅"
        activity_text = "活動量は通常範囲です"
        if metrics.steps >= 8000:
            activity_icon = "☀️"
            activity_text = "活動量はしっかり確保できています"
        elif metrics.steps < 4000:
            activity_icon = "🌧️"
            activity_text = "活動量は少なめなので、軽い歩行で整えたい日です"

        return [
            f"- {sleep_icon} 睡眠回復: {sleep_text}",
            f"- {hr_icon} 心拍コンディション: {hr_text}",
            f"- {activity_icon} 活動リズム: {activity_text}",
        ]

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
