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

    def reply_message(self, reply_token: str, text: str) -> None:
        return None

    def fetch_message_content(self, message_id: str) -> tuple[bytes, str]:
        return (b"", "image/jpeg")


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
            meal_calories=1450,
        ),
        trends=TrendFeatureInput(
            date=date(2026, 4, 1),
            sleep_vs_14d_avg=-15,
            resting_hr_vs_30d_avg=2,
            meal_calories_vs_7d_avg=120,
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
            key_findings=[
                "☀️ 睡眠回復: 睡眠量は十分で回復感があります",
                "⛅ 心拍コンディション: 心拍は安定していますが少し慎重に見たいです",
                "☀️ 活動リズム: 日中の動きは良い流れです",
            ],
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
    assert "今日の体調" in message
    assert "今日のアドバイス" in message
    assert "中長期の分析" in message
    assert "食事: 推定 1,450 kcal（7日平均より +120 kcal）" in message
    assert "- ☀️ 睡眠回復: 睡眠量は十分で回復感があります" in message
    assert "- ⛅ 心拍コンディション: 心拍は安定していますが少し慎重に見たいです" in message
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
            meal_calories=900,
        ),
        trends=TrendFeatureInput(
            date=date(2026, 4, 1),
            sleep_vs_14d_avg=None,
            resting_hr_vs_30d_avg=None,
            meal_calories_vs_7d_avg=None,
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
    assert "食事: 推定 900 kcal（比較データを蓄積中）" in message
    assert "- ⛅ 睡眠は確保できています" in message


def test_notification_message_marks_rule_based_fallback() -> None:
    service = NotificationService(DummyLineClient(), Settings())
    report = DailyReport(
        date=date(2026, 4, 1),
        generated_at=datetime.now(UTC),
        metrics=DailyMetricInput(
            date=date(2026, 4, 1),
            sleep_minutes=420,
            sleep_efficiency=90,
            deep_sleep_minutes=80,
            rem_sleep_minutes=90,
            awakenings=1,
            resting_hr=57,
            steps=7000,
            calories=2100,
            meal_calories=1200,
        ),
        trends=TrendFeatureInput(
            date=date(2026, 4, 1),
            sleep_vs_14d_avg=10,
            resting_hr_vs_30d_avg=-1,
            meal_calories_vs_7d_avg=80,
            sleep_debt_streak_days=0,
            bedtime_drift_minutes=None,
            recovery_score=82,
        ),
        rule_evaluation=RuleEvaluation(risk_level="green", reasons=[]),
        advice=AdviceResult(
            risk_level="green",
            summary="ルールベース判定に基づくサマリーを生成しました。",
            key_findings=["☀️ 睡眠回復: 睡眠はしっかり確保できています"],
            today_actions=["水分補給を意識する"],
            exercise_advice="軽く体を動かしてください。",
            sleep_advice="今夜も睡眠を確保してください。",
            caffeine_advice="午後は控えめにしてください。",
            medical_note="不調が続けば相談してください。",
            long_term_comment="長期傾向の安定化には睡眠リズムの固定が有効です。",
            provider="fallback",
            model_name="rule-based",
        ),
    )

    message = service.build_message(report)

    assert message.endswith("詳細レポートは Drive に保存済みです (Not LLM)")
