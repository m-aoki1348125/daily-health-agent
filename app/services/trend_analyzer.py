from __future__ import annotations

from dataclasses import dataclass
from statistics import mean

from app.config.settings import Settings
from app.db.models import DailyMetric
from app.schemas.health_features import DailyMetricInput, TrendContext, TrendFeatureInput


@dataclass
class TrendAnalyzer:
    settings: Settings

    def build(self, current: DailyMetricInput, history: list[DailyMetric]) -> TrendContext:
        sleep_window = [m.sleep_minutes for m in history[:14] if m.sleep_minutes is not None]
        hr_window = [m.resting_hr for m in history[:30] if m.resting_hr is not None]
        bedtime_window = [
            bedtime
            for bedtime in (
                self._extract_bedtime_minutes(m.bedtime_start)
                for m in history[:30]
                if m.bedtime_start
            )
            if bedtime is not None
        ]

        sleep_vs_14d_avg = current.sleep_minutes - mean(sleep_window) if sleep_window else None
        resting_hr_vs_30d_avg = (
            current.resting_hr - mean(hr_window)
            if hr_window and current.resting_hr is not None
            else None
        )
        bedtime_drift = None
        current_bedtime = self._extract_bedtime_minutes_from_current(current)
        if bedtime_window and current_bedtime is not None:
            bedtime_drift = current_bedtime - mean(bedtime_window)
        streak = self._sleep_debt_streak(current, history)
        recovery_score = self._recovery_score(current, sleep_vs_14d_avg, resting_hr_vs_30d_avg)

        weekly_trends = []
        monthly_trends = []
        if sleep_vs_14d_avg is not None and sleep_vs_14d_avg < 0:
            weekly_trends.append("直近2週間平均より睡眠時間が短めです")
        if bedtime_drift is not None and bedtime_drift > 0:
            monthly_trends.append("就寝時刻が後ろ倒し傾向です")
        if current.steps >= 8000 and recovery_score < self.settings.recovery_score_yellow_threshold:
            weekly_trends.append("活動量に対して回復が追いついていません")

        return TrendContext(
            current=TrendFeatureInput(
                date=current.date,
                sleep_vs_14d_avg=sleep_vs_14d_avg,
                resting_hr_vs_30d_avg=resting_hr_vs_30d_avg,
                sleep_debt_streak_days=streak,
                bedtime_drift_minutes=bedtime_drift,
                recovery_score=recovery_score,
            ),
            weekly_trends=weekly_trends,
            monthly_trends=monthly_trends,
            lookback_metrics=[
                DailyMetricInput(
                    date=m.date,
                    sleep_minutes=m.sleep_minutes or 0,
                    sleep_efficiency=m.sleep_efficiency or 0.0,
                    deep_sleep_minutes=m.deep_sleep_minutes or 0,
                    rem_sleep_minutes=m.rem_sleep_minutes or 0,
                    awakenings=m.awakenings or 0,
                    resting_hr=m.resting_hr,
                    steps=m.steps or 0,
                    calories=m.calories or 0,
                    raw_drive_file_id=m.raw_drive_file_id,
                    bedtime_start=m.bedtime_start,
                )
                for m in history
            ],
        )

    def _sleep_debt_streak(self, current: DailyMetricInput, history: list[DailyMetric]) -> int:
        threshold = self.settings.sleep_debt_threshold_minutes
        streak = 1 if current.sleep_minutes < threshold else 0
        if streak == 0:
            return 0
        for metric in history:
            if (metric.sleep_minutes or 0) < threshold:
                streak += 1
            else:
                break
        return streak

    def _recovery_score(
        self,
        current: DailyMetricInput,
        sleep_vs_14d_avg: float | None,
        resting_hr_vs_30d_avg: float | None,
    ) -> int:
        score = 80
        if sleep_vs_14d_avg is not None and sleep_vs_14d_avg < 0:
            score += int(sleep_vs_14d_avg / 6)
        if resting_hr_vs_30d_avg is not None and resting_hr_vs_30d_avg > 0:
            score -= int(resting_hr_vs_30d_avg * 3)
        if current.steps > 10000:
            score -= 5
        return max(0, min(100, score))

    @staticmethod
    def _extract_bedtime_minutes(value: str | None) -> int | None:
        if not value:
            return None
        hour = int(value[11:13])
        minute = int(value[14:16])
        return hour * 60 + minute

    @staticmethod
    def _extract_bedtime_minutes_from_current(current: DailyMetricInput) -> int | None:
        return TrendAnalyzer._extract_bedtime_minutes(current.bedtime_start)
