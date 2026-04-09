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
            "resting_hr": metrics.resting_hr,
            "sleep_vs_14d_avg": trend_context.current.sleep_vs_14d_avg,
            "resting_hr_vs_30d_avg": trend_context.current.resting_hr_vs_30d_avg,
            "meal_calories": metrics.meal_calories,
            "meal_calories_vs_7d_avg": trend_context.current.meal_calories_vs_7d_avg,
            "fitbit_calories_burned": metrics.calories,
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
                key_findings=[
                    *(
                        ["🌧️ 睡眠回復: 直近の睡眠不足が続いています"]
                        if trend_context.current.sleep_debt_streak_days >= 3
                        else []
                    ),
                    *(
                        ["☀️ 睡眠回復: 睡眠はしっかり確保できています"]
                        if metrics.sleep_minutes >= 420
                        else ["⛅ 睡眠回復: 睡眠は大きく崩れていません"]
                    ),
                    *(
                        ["☀️ 心拍コンディション: 安静時心拍は落ち着いています"]
                        if trend_context.current.resting_hr_vs_30d_avg is not None
                        and trend_context.current.resting_hr_vs_30d_avg <= 0
                        else ["⛅ 心拍コンディション: 心拍の比較データを蓄積中です"]
                    ),
                    *(
                        ["☀️ 活動リズム: 無理のない範囲で活動できています"]
                        if metrics.steps >= 6000
                        else ["⛅ 活動リズム: 軽い歩行で体を整えたい日です"]
                    ),
                    *(
                        ["🌧️ 食事バランス: 摂取カロリーが最近より多めです"]
                        if trend_context.current.meal_calories_vs_7d_avg is not None
                        and trend_context.current.meal_calories_vs_7d_avg >= 400
                        else (
                            ["☀️ 食事バランス: 食事量は安定しています"]
                            if metrics.meal_calories is not None
                            else ["⛅ 食事バランス: 食事データを蓄積中です"]
                        )
                    ),
                ][:4],
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
        fallback_note = ""
        if advice.provider == "fallback":
            fallback_note = "\n\n_Not LLM: rule-based fallback output used._"
        return f"""# Daily Health Report {report.date.isoformat()}

## Condition
- Risk level: {report.rule_evaluation.risk_level}
- Sleep: {metrics.sleep_minutes} minutes
- Resting HR: {metrics.resting_hr}
- Steps: {metrics.steps}
- Meal calories: {metrics.meal_calories}
- Recovery score: {trends.recovery_score}

## Rule Findings
{chr(10).join(f"- {reason}" for reason in report.rule_evaluation.reasons) or "- No alerts"}

## Today Actions
{chr(10).join(f"- {item}" for item in advice.today_actions)}

## Long Term Comment
{advice.long_term_comment}
{fallback_note}
"""
