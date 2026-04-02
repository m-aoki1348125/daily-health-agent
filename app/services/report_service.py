from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, cast

from app.clients.llm_base import LLMProvider
from app.schemas.advice_result import AdviceResult
from app.schemas.health_features import DailyMetricInput, TrendContext
from app.schemas.report_schema import DailyReport, RuleEvaluation


class ReportService:
    def __init__(self, llm_provider: LLMProvider) -> None:
        self.llm_provider = llm_provider

    def build_advice(
        self, metrics: DailyMetricInput, trend_context: TrendContext, rule_eval: RuleEvaluation
    ) -> AdviceResult:
        payload: dict[str, Any] = {
            "date": metrics.date.isoformat(),
            "sleep_minutes": metrics.sleep_minutes,
            "sleep_vs_14d_avg": trend_context.current.sleep_vs_14d_avg,
            "resting_hr_vs_30d_avg": trend_context.current.resting_hr_vs_30d_avg,
            "steps_yesterday": metrics.steps,
            "sleep_debt_streak_days": trend_context.current.sleep_debt_streak_days,
            "rule_status": rule_eval.risk_level,
            "rule_reasons": rule_eval.reasons,
            "weekly_trends": trend_context.weekly_trends,
            "monthly_trends": trend_context.monthly_trends,
        }
        try:
            return self.llm_provider.generate_advice(payload)
        except Exception:
            return AdviceResult(
                risk_level=rule_eval.risk_level,
                summary="ルールベース判定に基づくサマリーを生成しました。",
                key_findings=rule_eval.reasons or ["rule-based fallback"],
                today_actions=[
                    "午前は体調確認を優先する",
                    "水分補給を意識する",
                    "今夜は早めに休む",
                ],
                exercise_advice="強度は控えめにし、軽い有酸素を中心にしてください。",
                sleep_advice="就寝前の刺激を減らし、睡眠時間の確保を優先してください。",
                caffeine_advice="カフェインは午後早い時間までにしてください。",
                medical_note="不調が持続する場合は医療機関へ相談してください。",
                long_term_comment="長期傾向の安定化には睡眠リズムの固定が有効です。",
                provider="fallback",
                model_name="rule-based",
            )

    def build_report(
        self,
        metrics: DailyMetricInput,
        trend_context: TrendContext,
        rule_eval: RuleEvaluation,
        advice: AdviceResult,
        raw_drive_file_id: str | None,
    ) -> DailyReport:
        return DailyReport(
            date=metrics.date,
            generated_at=datetime.now(UTC),
            metrics=metrics,
            trends=trend_context.current,
            rule_evaluation=rule_eval,
            advice=advice,
            raw_drive_file_id=raw_drive_file_id,
            source_summary={
                "weekly_trends": trend_context.weekly_trends,
                "monthly_trends": trend_context.monthly_trends,
            },
        )

    @staticmethod
    def to_json_payload(report: DailyReport) -> dict[str, Any]:
        return cast(dict[str, Any], json.loads(report.model_dump_json()))

    @staticmethod
    def to_markdown(report: DailyReport) -> str:
        metrics = report.metrics
        trends = report.trends
        advice = report.advice
        return f"""# Daily Health Report {report.date.isoformat()}

## Condition
- Risk level: {report.rule_evaluation.risk_level}
- Sleep: {metrics.sleep_minutes} minutes
- Resting HR: {metrics.resting_hr}
- Steps: {metrics.steps}
- Recovery score: {trends.recovery_score}

## Rule Findings
{chr(10).join(f"- {reason}" for reason in report.rule_evaluation.reasons) or "- No alerts"}

## Today Actions
{chr(10).join(f"- {item}" for item in advice.today_actions)}

## Long Term Comment
{advice.long_term_comment}
"""
