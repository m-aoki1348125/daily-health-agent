from __future__ import annotations

from dataclasses import dataclass

from app.config.settings import Settings
from app.schemas.health_features import DailyMetricInput, TrendFeatureInput
from app.schemas.report_schema import RuleEvaluation


@dataclass
class RuleEngine:
    settings: Settings

    def evaluate(self, metrics: DailyMetricInput, trends: TrendFeatureInput) -> RuleEvaluation:
        reasons: list[str] = []
        explanations: list[str] = []

        if trends.sleep_vs_14d_avg is not None and (
            trends.sleep_vs_14d_avg <= -self.settings.sleep_deficit_alert_delta_minutes
        ):
            reasons.append("sleep deficit detected")
            explanations.append("睡眠時間が直近14日平均より大きく短い状態です。")

        if trends.resting_hr_vs_30d_avg is not None and (
            trends.resting_hr_vs_30d_avg >= self.settings.resting_hr_elevation_bpm
        ):
            reasons.append("elevated resting heart rate")
            explanations.append("安静時心拍が直近30日平均より高めです。")

        if trends.sleep_debt_streak_days >= 3:
            reasons.append("multi-day recovery issue")
            explanations.append("睡眠不足が複数日連続しています。")

        if trends.bedtime_drift_minutes is not None and (
            trends.bedtime_drift_minutes >= self.settings.bedtime_drift_alert_minutes
        ):
            reasons.append("bedtime drift detected")
            explanations.append("就寝時刻が長期平均より後ろ倒しです。")

        if trends.recovery_score <= self.settings.recovery_score_red_threshold:
            reasons.append("insufficient recovery for activity")
            explanations.append("活動量に対して回復不足が見られます。")

        if trends.meal_calories_vs_7d_avg is not None and (
            trends.meal_calories_vs_7d_avg >= self.settings.meal_calorie_alert_delta
        ):
            reasons.append("meal intake above recent baseline")
            explanations.append("食事摂取カロリーが直近7日平均より多めです。")

        if (
            metrics.meal_calories is not None
            and metrics.calories > 0
            and metrics.meal_calories - metrics.calories
            >= self.settings.meal_calorie_balance_alert_delta
        ):
            reasons.append("meal intake exceeds activity burn")
            explanations.append("食事摂取カロリーが推定消費カロリーを上回っています。")

        fallback_used = False
        if metrics.resting_hr is None:
            reasons.append("missing resting heart rate data")
            explanations.append("心拍データ欠損のため保守的に評価しました。")
            fallback_used = True

        risk_level = "green"
        if len(reasons) >= 3 or trends.recovery_score <= self.settings.recovery_score_red_threshold:
            risk_level = "red"
        elif reasons:
            risk_level = "yellow"

        return RuleEvaluation(
            risk_level=risk_level,
            reasons=reasons,
            explanations=explanations,
            fallback_used=fallback_used,
        )
