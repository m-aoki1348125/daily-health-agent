from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any, cast

from app.clients.llm_base import LLMProvider
from app.config.settings import Settings
from app.schemas.advice_result import AdviceResult
from app.schemas.health_features import DailyMetricInput, TrendContext
from app.schemas.report_schema import DailyMealSummary, DailyReport, MealContextItem, RuleEvaluation
from app.services.meal_time_service import format_meal_service_time


class ReportService:
    def __init__(self, llm_provider: LLMProvider, settings: Settings) -> None:
        self.llm_provider = llm_provider
        self.settings = settings
        self.logger = logging.getLogger(__name__)

    def build_advice(
        self,
        metrics: DailyMetricInput,
        trend_context: TrendContext,
        rule_eval: RuleEvaluation,
        meal_summary: DailyMealSummary,
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
            "weight_kg": metrics.weight_kg,
            "bmi": metrics.bmi,
            "body_fat_percent": metrics.body_fat_percent,
            "weight_kg_vs_30d_avg": trend_context.current.weight_kg_vs_30d_avg,
            "body_logged_at": metrics.body_logged_at,
            "sleep_debt_streak_days": trend_context.current.sleep_debt_streak_days,
            "meal_count": meal_summary.meal_count,
            "average_meal_calories": meal_summary.average_calories,
            "largest_meal_calories": meal_summary.max_calories,
            "meal_entries": [
                {
                    "time": format_meal_service_time(
                        item.consumed_at,
                        timezone=self.settings.timezone,
                        rollover_hour=self.settings.meal_day_rollover_hour,
                    ),
                    "estimated_calories": item.estimated_calories,
                    "summary": item.summary,
                    "meal_items": item.meal_items,
                    "confidence": item.confidence,
                }
                for item in meal_summary.meals
            ],
            "recent_meal_daily_totals": meal_summary.recent_daily_totals,
            "meal_trends": meal_summary.trend_notes,
            "rule_status": rule_eval.risk_level,
            "rule_reasons": rule_eval.reasons,
            "weekly_trends": trend_context.weekly_trends,
            "monthly_trends": trend_context.monthly_trends,
        }
        payload["data_window"] = {
            "report_date": metrics.date.isoformat(),
            "sleep_scope": "last_night_sleep",
            "activity_scope": "previous_day_activity",
            "meal_scope": "previous_day_meals",
        }
        try:
            return self.llm_provider.generate_advice(payload)
        except Exception:
            self.logger.exception("llm advice generation failed; falling back to rule-based advice")
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
                        [
                            "⛅ 体組成: 体重データも含めて中長期の傾向を見ています"
                        ]
                        if metrics.weight_kg is not None
                        else []
                    ),
                    *(
                        ["🌧️ 食事バランス: 食事量が最近より多く、配分の見直し余地があります"]
                        if trend_context.current.meal_calories_vs_7d_avg is not None
                        and trend_context.current.meal_calories_vs_7d_avg >= 400
                        else (
                            [
                                "☀️ 食事バランス: 食事回数と摂取量は大きく崩れていません"
                            ]
                            if metrics.meal_calories is not None
                            else ["⛅ 食事バランス: 食事データを蓄積中です"]
                        )
                    ),
                ][:4],
                today_actions=[
                    "午前は体調確認を優先する",
                    "水分補給を意識する",
                    (
                        "食事は "
                        f"{meal_summary.meal_count} 回・合計 {meal_summary.total_calories} kcal "
                        "を踏まえ、夜は軽めに整える"
                        if meal_summary.meal_count > 0 and meal_summary.total_calories > 0
                        else "今夜は早めに休む"
                    ),
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
        meal_summary: DailyMealSummary,
        raw_drive_file_id: str | None,
        source_summary: dict[str, Any] | None = None,
    ) -> DailyReport:
        summary = dict(source_summary or {})
        summary.update(
            {
                "weekly_trends": trend_context.weekly_trends,
                "monthly_trends": trend_context.monthly_trends,
                "meal_trends": meal_summary.trend_notes,
            }
        )
        return DailyReport(
            date=metrics.date,
            generated_at=datetime.now(UTC),
            metrics=metrics,
            trends=trend_context.current,
            rule_evaluation=rule_eval,
            advice=advice,
            meal_summary=meal_summary,
            raw_drive_file_id=raw_drive_file_id,
            source_summary=summary,
        )

    @staticmethod
    def build_meal_summary(
        *,
        meals: list[Any],
        recent_daily_totals: list[int],
        meal_calorie_delta: float | None,
    ) -> DailyMealSummary:
        items = [
            MealContextItem(
                consumed_at=meal.consumed_at,
                estimated_calories=meal.estimated_calories,
                summary=meal.summary,
                meal_items=list(meal.meal_items_json),
                confidence=meal.confidence,
            )
            for meal in meals
        ]
        total_calories = sum(item.estimated_calories for item in items)
        meal_count = len(items)
        average_calories = total_calories / meal_count if meal_count else None
        max_calories = max((item.estimated_calories for item in items), default=None)
        trend_notes: list[str] = []
        if meal_count:
            trend_notes.append(f"昨日の食事回数は {meal_count} 回でした")
            if max_calories is not None:
                trend_notes.append(f"最大の食事は {max_calories} kcal でした")
        if meal_calorie_delta is not None:
            if meal_calorie_delta >= 300:
                trend_notes.append("ここ数日より摂取カロリーが多めです")
            elif meal_calorie_delta <= -200:
                trend_notes.append("ここ数日より摂取カロリーは控えめです")
        return DailyMealSummary(
            total_calories=total_calories,
            meal_count=meal_count,
            average_calories=average_calories,
            max_calories=max_calories,
            meals=items,
            recent_daily_totals=recent_daily_totals,
            trend_notes=trend_notes,
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
- Weight: {metrics.weight_kg} kg
- Body fat: {metrics.body_fat_percent} %
- Meal calories: {metrics.meal_calories}
- Meal count: {report.meal_summary.meal_count}
- Recovery score: {trends.recovery_score}

## Rule Findings
{chr(10).join(f"- {reason}" for reason in report.rule_evaluation.reasons) or "- No alerts"}

## Today Actions
{chr(10).join(f"- {item}" for item in advice.today_actions)}

## Long Term Comment
{advice.long_term_comment}
{fallback_note}
"""
