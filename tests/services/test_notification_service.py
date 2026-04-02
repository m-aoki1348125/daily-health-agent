from __future__ import annotations

from datetime import UTC, date, datetime

from app.clients.line_client import LineClient
from app.config.settings import Settings
from app.schemas.advice_result import AdviceResult
from app.schemas.health_features import DailyMetricInput, TrendFeatureInput
from app.schemas.report_schema import DailyReport, RuleEvaluation
from app.services.notification_service import NotificationService


class DummyLineClient(LineClient):
    def push_message(self, user_id: str, text: str) -> None:
        return None


def test_notification_message_includes_fact_and_long_term_sections() -> None:
    service = NotificationService(DummyLineClient(), Settings())
    report = DailyReport(
        date=date(2026, 4, 1),
        generated_at=datetime.now(UTC),
        metrics=DailyMetricInput(
            date=date(2026, 4, 1),
            sleep_minutes=445,
            sleep_efficiency=89,
            deep_sleep_minutes=70,
            rem_sleep_minutes=90,
            awakenings=2,
            resting_hr=58,
            steps=5257,
            calories=2100,
        ),
        trends=TrendFeatureInput(
            date=date(2026, 4, 1),
            sleep_vs_14d_avg=-15,
            resting_hr_vs_30d_avg=2,
            sleep_debt_streak_days=1,
            bedtime_drift_minutes=20,
            recovery_score=74,
        ),
        rule_evaluation=RuleEvaluation(
            risk_level="green",
            reasons=["sleep slightly below recent baseline", "resting HR mildly elevated"],
        ),
        advice=AdviceResult(
            risk_level="green",
            summary="前日の睡眠と心拍の事実をもとに落ち着いて整える日です。",
            key_findings=["睡眠は14日平均より15分短い", "安静時心拍は30日平均より2 bpm高い"],
            today_actions=[
                "午前は無理に負荷を上げない",
                "昼前に軽く歩く",
                "今夜は就寝を15分早める",
            ],
            exercise_advice="軽い有酸素を優先してください。",
            sleep_advice="睡眠時間を少し長めに確保してください。",
            caffeine_advice="カフェインは午後早めまでにしてください。",
            medical_note="不調が続く場合は相談してください。",
            long_term_comment="平日の就寝が少し遅れる傾向があるため固定化が有効です。",
            provider="claude",
            model_name="claude-haiku-4-5",
        ),
        source_summary={
            "weekly_trends": ["平日は睡眠がやや短い"],
            "monthly_trends": ["就寝時刻が少し後ろ倒しです"],
        },
    )

    message = service.build_message(report)

    assert "コンディション: 🟢 Green" in message
    assert "昨日の健康データ" in message
    assert "中長期の分析" in message
    assert "- 睡眠時間: 7時間25分（14日平均より -15分）" in message
    assert "- 安静時心拍: 58 bpm（30日平均より +2 bpm）" in message
    assert "- 前日歩数: 5,257歩" in message
    assert "- 平日は睡眠がやや短い" in message
    assert "- 平日の就寝が少し遅れる傾向があるため固定化が有効です。" in message
    assert "安静時心拍: 58 bpm（30日平均より +2 bpm）" in message


def test_notification_message_shows_current_resting_hr_even_without_delta() -> None:
    service = NotificationService(DummyLineClient(), Settings())
    report = DailyReport(
        date=date(2026, 4, 1),
        generated_at=datetime.now(UTC),
        metrics=DailyMetricInput(
            date=date(2026, 4, 1),
            sleep_minutes=445,
            sleep_efficiency=89,
            deep_sleep_minutes=70,
            rem_sleep_minutes=90,
            awakenings=2,
            resting_hr=58,
            steps=5257,
            calories=2100,
        ),
        trends=TrendFeatureInput(
            date=date(2026, 4, 1),
            sleep_vs_14d_avg=None,
            resting_hr_vs_30d_avg=None,
            sleep_debt_streak_days=0,
            bedtime_drift_minutes=None,
            recovery_score=80,
        ),
        rule_evaluation=RuleEvaluation(risk_level="green", reasons=[]),
        advice=AdviceResult(
            risk_level="green",
            summary="前日のデータを短くまとめます。",
            key_findings=["睡眠は確保できています"],
            today_actions=["いつもどおりの生活リズムを維持する"],
            exercise_advice="軽い運動を継続してください。",
            sleep_advice="今夜も睡眠を確保してください。",
            caffeine_advice="午後は控えめにしてください。",
            medical_note="不調が続けば相談してください。",
            long_term_comment="長期傾向は今後の蓄積で詳しく見られます。",
            provider="claude",
            model_name="claude-haiku-4-5",
        ),
    )

    message = service.build_message(report)

    assert "安静時心拍: 58 bpm（30日平均との差分は未算出）" in message
