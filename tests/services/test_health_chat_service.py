from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.clients.drive_client import LocalDriveClient
from app.clients.line_client import MockLineClient
from app.clients.llm_factory import MockLLMProvider
from app.config.settings import Settings
from app.db.models import AdviceHistory, DailyMetric, MealRecord
from app.repositories.advice_repository import AdviceRepository
from app.repositories.line_state_repository import LineStateRepository
from app.repositories.meal_repository import MealRepository
from app.repositories.metrics_repository import MetricsRepository
from app.services.health_chat_service import HealthChatService
from app.services.meal_logging_service import MealLoggingService


def build_service(session: Session, settings: Settings, tmp_path: Path) -> HealthChatService:
    drive_client = LocalDriveClient(str(tmp_path / "drive"))
    line_state_repository = LineStateRepository(session)
    meal_logging_service = MealLoggingService(
        settings=settings,
        line_client=MockLineClient(),
        drive_client=drive_client,
        llm_provider=MockLLMProvider(),
        meal_repository=MealRepository(session),
        line_state_repository=line_state_repository,
    )
    return HealthChatService(
        settings=settings,
        drive_client=drive_client,
        llm_provider=MockLLMProvider(),
        meal_repository=MealRepository(session),
        metrics_repository=MetricsRepository(session),
        advice_repository=AdviceRepository(session),
        line_state_repository=line_state_repository,
        meal_logging_service=meal_logging_service,
    )


def test_health_chat_service_deletes_latest_meal(
    session: Session,
    settings: Settings,
    tmp_path: Path,
) -> None:
    session.add(
        MealRecord(
            source_message_id="meal-msg-1",
            meal_date=date(2026, 4, 2),
            consumed_at=datetime(2026, 4, 2, 12, 0, tzinfo=ZoneInfo("Asia/Tokyo")),
            line_user_id="U-test",
            image_mime_type="image/jpeg",
            estimated_calories=720,
            confidence="medium",
            summary="昼食の定食です。",
            meal_items_json=["ごはん", "焼き魚"],
            rationale="定食として推定",
            provider="mock",
            model_name="mock",
        )
    )
    session.commit()

    service = build_service(session, settings, tmp_path)
    message = service.handle_text_message(
        text="先ほど送った食事写真は誤りなので登録から削除してください",
        line_user_id="U-test",
        event_timestamp_ms=int(
            datetime(2026, 4, 2, 20, 0, tzinfo=ZoneInfo("Asia/Tokyo")).timestamp() * 1000
        ),
    )
    session.commit()

    assert "削除しました" in message
    assert MealRepository(session).get_by_source_message_id("meal-msg-1") is None
    summary_path = (
        tmp_path
        / "drive"
        / "HealthAgent"
        / "meal_records"
        / "2026"
        / "2026-04"
        / "2026-04-02_meal_summary.json"
    )
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert payload["meal_count"] == 0


def test_health_chat_service_corrects_sleep(
    session: Session,
    settings: Settings,
    tmp_path: Path,
) -> None:
    session.add(
        DailyMetric(
            date=date(2026, 4, 1),
            sleep_minutes=120,
            sleep_efficiency=0.8,
            deep_sleep_minutes=20,
            rem_sleep_minutes=30,
            awakenings=2,
            resting_hr=60,
            steps=5000,
            calories=1800,
            meal_calories=900,
        )
    )
    session.commit()

    service = build_service(session, settings, tmp_path)
    message = service.handle_text_message(
        text="昨日の睡眠時間を8時間に修正してください",
        line_user_id="U-test",
        event_timestamp_ms=int(
            datetime(2026, 4, 2, 9, 0, tzinfo=ZoneInfo("Asia/Tokyo")).timestamp() * 1000
        ),
    )
    session.commit()

    metric = MetricsRepository(session).get_daily_metric(date(2026, 4, 1))
    assert metric is not None
    assert metric.sleep_minutes == 480
    assert "8時間00分" in message


def test_health_chat_service_corrects_sleep_with_richer_phrasing(
    session: Session,
    settings: Settings,
    tmp_path: Path,
) -> None:
    session.add(
        DailyMetric(
            date=date(2026, 4, 10),
            sleep_minutes=85,
            sleep_efficiency=0.8,
            deep_sleep_minutes=10,
            rem_sleep_minutes=15,
            awakenings=3,
            resting_hr=62,
            steps=8553,
            calories=1900,
            meal_calories=0,
        )
    )
    session.commit()

    service = build_service(session, settings, tmp_path)
    message = service.handle_text_message(
        text="昨日は睡眠トラッカー付け忘れていました。7時間睡眠で記録し直してください",
        line_user_id="U-test",
        event_timestamp_ms=int(
            datetime(2026, 4, 11, 11, 21, tzinfo=ZoneInfo("Asia/Tokyo")).timestamp() * 1000
        ),
    )
    session.commit()

    metric = MetricsRepository(session).get_daily_metric(date(2026, 4, 10))
    assert metric is not None
    assert metric.sleep_minutes == 420
    assert "7時間00分" in message
    assert "Drive" in message


def test_health_chat_service_registers_sleep_when_missing(
    session: Session,
    settings: Settings,
    tmp_path: Path,
) -> None:
    service = build_service(session, settings, tmp_path)
    message = service.handle_text_message(
        text="昨日は8時間睡眠で再登録してください",
        line_user_id="U-test",
        event_timestamp_ms=int(
            datetime(2026, 4, 2, 9, 0, tzinfo=ZoneInfo("Asia/Tokyo")).timestamp() * 1000
        ),
    )
    session.commit()

    metric = MetricsRepository(session).get_daily_metric(date(2026, 4, 1))
    assert metric is not None
    assert metric.sleep_minutes == 480
    assert "新規登録" in message


def test_health_chat_service_reports_meal_counts(
    session: Session,
    settings: Settings,
    tmp_path: Path,
) -> None:
    session.add_all(
        [
            MealRecord(
                source_message_id="meal-msg-1",
                meal_date=date(2026, 4, 1),
                consumed_at=datetime(2026, 4, 1, 8, 0, tzinfo=ZoneInfo("Asia/Tokyo")),
                line_user_id="U-test",
                image_mime_type="image/jpeg",
                estimated_calories=350,
                confidence="medium",
                summary="朝食です。",
                meal_items_json=["パン"],
                rationale="推定",
                provider="mock",
                model_name="mock",
            ),
            MealRecord(
                source_message_id="meal-msg-2",
                meal_date=date(2026, 4, 1),
                consumed_at=datetime(2026, 4, 1, 12, 0, tzinfo=ZoneInfo("Asia/Tokyo")),
                line_user_id="U-test",
                image_mime_type="image/jpeg",
                estimated_calories=650,
                confidence="medium",
                summary="昼食です。",
                meal_items_json=["定食"],
                rationale="推定",
                provider="mock",
                model_name="mock",
            ),
        ]
    )
    session.commit()

    service = build_service(session, settings, tmp_path)
    message = service.handle_text_message(
        text="昨日の食事回数と摂取カロリーを教えてください",
        line_user_id="U-test",
        event_timestamp_ms=int(
            datetime(2026, 4, 2, 9, 0, tzinfo=ZoneInfo("Asia/Tokyo")).timestamp() * 1000
        ),
    )
    assert "2 回" in message
    assert "1000 kcal" in message


def test_health_chat_service_formats_post_midnight_meal_as_26_oclock(
    session: Session,
    settings: Settings,
    tmp_path: Path,
) -> None:
    session.add(
        MealRecord(
            source_message_id="meal-msg-26",
            meal_date=date(2026, 4, 1),
            consumed_at=datetime(2026, 4, 2, 2, 0, tzinfo=ZoneInfo("Asia/Tokyo")),
            line_user_id="U-test",
            image_mime_type="image/jpeg",
            estimated_calories=300,
            confidence="medium",
            summary="夜食です。",
            meal_items_json=["サンドイッチ"],
            rationale="推定",
            provider="mock",
            model_name="mock",
        )
    )
    session.commit()

    service = build_service(session, settings, tmp_path)
    message = service.handle_text_message(
        text="昨日の食事回数と摂取カロリーを教えてください",
        line_user_id="U-test",
        event_timestamp_ms=int(
            datetime(2026, 4, 2, 9, 0, tzinfo=ZoneInfo("Asia/Tokyo")).timestamp() * 1000
        ),
    )
    assert "26:00頃の食事" in message


def test_health_chat_service_answers_exercise_question(
    session: Session,
    settings: Settings,
    tmp_path: Path,
) -> None:
    session.add(
        DailyMetric(
            date=date(2026, 4, 2),
            sleep_minutes=420,
            sleep_efficiency=0.9,
            deep_sleep_minutes=70,
            rem_sleep_minutes=80,
            awakenings=1,
            resting_hr=58,
            steps=8000,
            calories=2000,
            meal_calories=1200,
        )
    )
    session.add(
        AdviceHistory(
            date=date(2026, 4, 2),
            risk_level="green",
            summary="安定しています。",
            key_findings_json=["☀️ 睡眠回復: 良好です"],
            today_actions_json=["水分補給を意識する"],
            exercise_advice="軽いジョグか速歩が向いています。",
            sleep_advice="就寝を整えてください。",
            caffeine_advice="午後は控えめに。",
            medical_note="不調が続けば相談してください。",
            long_term_comment="安定しています。",
            provider="mock",
            model_name="mock",
        )
    )
    session.commit()

    service = build_service(session, settings, tmp_path)
    message = service.handle_text_message(
        text="今日運動するとしたら何が最適？",
        line_user_id="U-test",
        event_timestamp_ms=int(
            datetime(2026, 4, 2, 18, 0, tzinfo=ZoneInfo("Asia/Tokyo")).timestamp() * 1000
        ),
    )
    assert "今日運動するとしたら何が最適" in message


def test_health_chat_service_corrects_specific_lunch_directly(
    session: Session,
    settings: Settings,
    tmp_path: Path,
) -> None:
    session.add(
        MealRecord(
            source_message_id="meal-msg-3",
            meal_date=date(2026, 4, 1),
            consumed_at=datetime(2026, 4, 1, 12, 15, tzinfo=ZoneInfo("Asia/Tokyo")),
            line_user_id="U-test",
            image_mime_type="image/jpeg",
            estimated_calories=780,
            confidence="medium",
            summary="昼の定食です。",
            meal_items_json=["ごはん", "鶏肉"],
            rationale="推定",
            provider="mock",
            model_name="mock",
        )
    )
    session.commit()

    service = build_service(session, settings, tmp_path)
    message = service.handle_text_message(
        text="昨日のこの昼食を650kcalに修正してください",
        line_user_id="U-test",
        event_timestamp_ms=int(
            datetime(2026, 4, 2, 12, 0, tzinfo=ZoneInfo("Asia/Tokyo")).timestamp() * 1000
        ),
    )
    session.commit()

    meal = MealRepository(session).get_by_source_message_id("meal-msg-3")
    assert meal is not None
    assert meal.estimated_calories == 650
    assert "650 kcal" in message


def test_health_chat_service_requests_candidate_selection_for_multiple_meals(
    session: Session,
    settings: Settings,
    tmp_path: Path,
) -> None:
    session.add_all(
        [
            MealRecord(
                source_message_id="meal-msg-10",
                meal_date=date(2026, 4, 1),
                consumed_at=datetime(2026, 4, 1, 12, 0, tzinfo=ZoneInfo("Asia/Tokyo")),
                line_user_id="U-test",
                image_mime_type="image/jpeg",
                estimated_calories=500,
                confidence="medium",
                summary="昼食Aです。",
                meal_items_json=["A"],
                rationale="推定",
                provider="mock",
                model_name="mock",
            ),
            MealRecord(
                source_message_id="meal-msg-11",
                meal_date=date(2026, 4, 1),
                consumed_at=datetime(2026, 4, 1, 13, 0, tzinfo=ZoneInfo("Asia/Tokyo")),
                line_user_id="U-test",
                image_mime_type="image/jpeg",
                estimated_calories=700,
                confidence="medium",
                summary="昼食Bです。",
                meal_items_json=["B"],
                rationale="推定",
                provider="mock",
                model_name="mock",
            ),
        ]
    )
    session.commit()

    service = build_service(session, settings, tmp_path)
    prompt = service.handle_text_message(
        text="昨日の昼食を650kcalに修正してください",
        line_user_id="U-test",
        event_timestamp_ms=int(
            datetime(2026, 4, 2, 12, 0, tzinfo=ZoneInfo("Asia/Tokyo")).timestamp() * 1000
        ),
    )
    session.commit()

    assert "候補が複数ある" in prompt
    assert "1番" in prompt
    assert "2番" in prompt

    message = service.handle_text_message(
        text="2番を650kcalに修正してください",
        line_user_id="U-test",
        event_timestamp_ms=int(
            datetime(2026, 4, 2, 12, 1, tzinfo=ZoneInfo("Asia/Tokyo")).timestamp() * 1000
        ),
    )
    session.commit()

    meal = MealRepository(session).get_by_source_message_id("meal-msg-11")
    assert meal is not None
    assert meal.estimated_calories == 650
    assert "650 kcal" in message


def test_health_chat_service_stores_pre_image_timing_hint(
    session: Session,
    settings: Settings,
    tmp_path: Path,
) -> None:
    service = build_service(session, settings, tmp_path)
    message = service.handle_text_message(
        text="この食事は18:30ごろ食べました",
        line_user_id="U-test",
        event_timestamp_ms=int(
            datetime(2026, 4, 1, 18, 40, tzinfo=ZoneInfo("Asia/Tokyo")).timestamp() * 1000
        ),
    )
    session.commit()

    state = LineStateRepository(session).get("U-test")
    assert state is not None
    assert state.intent == "pending_meal_timing_hint"
    assert "18:30" in message


def test_health_chat_service_registers_meal_text_from_reminder_followup(
    session: Session,
    settings: Settings,
    tmp_path: Path,
) -> None:
    line_state_repository = LineStateRepository(session)
    line_state_repository.upsert(
        "U-test",
        "meal_reminder_followup",
        {
            "date": "2026-04-01",
            "expires_at": datetime(
                2026,
                4,
                2,
                7,
                0,
                tzinfo=ZoneInfo("Asia/Tokyo"),
            ).isoformat(),
        },
    )
    session.commit()
    service = build_service(session, settings, tmp_path)
    message = service.handle_text_message(
        text="朝7:30におにぎり、昼12:15にラーメンを食べました",
        line_user_id="U-test",
        event_timestamp_ms=int(
            datetime(2026, 4, 1, 23, 5, tzinfo=ZoneInfo("Asia/Tokyo")).timestamp() * 1000
        ),
    )
    session.commit()

    meals = MealRepository(session).list_for_user_and_date("U-test", date(2026, 4, 1))
    assert len(meals) >= 2
    assert "追加登録" in message
    assert "現在の合計" in message


def test_health_chat_service_updates_latest_meal_time_after_image_followup(
    session: Session,
    settings: Settings,
    tmp_path: Path,
) -> None:
    meal = MealRecord(
        source_message_id="meal-msg-20",
        meal_date=date(2026, 4, 1),
        consumed_at=datetime(2026, 4, 1, 20, 0, tzinfo=ZoneInfo("Asia/Tokyo")),
        line_user_id="U-test",
        image_mime_type="image/jpeg",
        estimated_calories=620,
        confidence="medium",
        summary="夕食です。",
        meal_items_json=["丼"],
        rationale="推定",
        provider="mock",
        model_name="mock",
    )
    session.add(meal)
    session.flush()
    LineStateRepository(session).upsert(
        "U-test",
        "pending_meal_time_confirmation",
        {
            "meal_id": meal.id,
            "expires_at": datetime(
                2026,
                4,
                1,
                22,
                0,
                tzinfo=ZoneInfo("Asia/Tokyo"),
            ).isoformat(),
        },
    )
    session.commit()

    service = build_service(session, settings, tmp_path)
    message = service.handle_text_message(
        text="この写真は18:30ごろ食べました",
        line_user_id="U-test",
        event_timestamp_ms=int(
            datetime(2026, 4, 1, 20, 5, tzinfo=ZoneInfo("Asia/Tokyo")).timestamp() * 1000
        ),
    )
    session.commit()

    stored_meal = MealRepository(session).get_by_source_message_id("meal-msg-20")
    assert stored_meal is not None
    assert stored_meal.consumed_at.astimezone(ZoneInfo("Asia/Tokyo")).strftime("%H:%M") == "18:30"
    assert "18:30" in message
