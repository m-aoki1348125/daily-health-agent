from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.clients.drive_client import DriveClient
from app.clients.llm_base import LLMProvider
from app.config.settings import Settings
from app.db.models import MealRecord
from app.repositories.advice_repository import AdviceRepository
from app.repositories.line_state_repository import LineStateRepository
from app.repositories.meal_repository import MealRepository
from app.repositories.metrics_repository import MetricsRepository
from app.schemas.meal_estimate import MealRecordInput, MealTextParseResult, ParsedMealEntry
from app.services.meal_logging_service import MealLoggingService
from app.services.meal_time_service import format_meal_service_time, resolve_meal_service_date


@dataclass
class HealthChatService:
    settings: Settings
    drive_client: DriveClient
    llm_provider: LLMProvider
    meal_repository: MealRepository
    metrics_repository: MetricsRepository
    advice_repository: AdviceRepository
    line_state_repository: LineStateRepository
    meal_logging_service: MealLoggingService

    def handle_text_message(
        self,
        *,
        text: str,
        line_user_id: str,
        event_timestamp_ms: int,
    ) -> str:
        normalized = self._normalize_text(text)
        target_date = self._resolve_date(normalized, event_timestamp_ms)
        event_time = self._event_datetime(event_timestamp_ms)

        if self._looks_like_meal_selection(normalized):
            resolved = self._resolve_pending_meal_selection(
                normalized=normalized,
                line_user_id=line_user_id,
            )
            if resolved is not None:
                return resolved

        timing_resolution = self._resolve_pending_meal_time_confirmation(
            normalized=normalized,
            line_user_id=line_user_id,
            event_time=event_time,
        )
        if timing_resolution is not None:
            return timing_resolution

        meal_followup = self._resolve_pending_meal_followup(
            text=text,
            normalized=normalized,
            line_user_id=line_user_id,
            target_date=target_date,
            event_time=event_time,
        )
        if meal_followup is not None:
            return meal_followup

        if "削除" in normalized and ("食事" in normalized or "写真" in normalized):
            return self._delete_latest_meal(line_user_id=line_user_id, target_date=target_date)

        if self._looks_like_sleep_correction(normalized):
            corrected_minutes = self._parse_sleep_minutes(normalized)
            if corrected_minutes is None:
                return (
                    "睡眠時間の修正や再登録は"
                    "『昨日の睡眠時間を8時間10分に修正』"
                    "『昨日は7時間睡眠で記録し直してください』のように送ってください。"
                )
            return self._correct_sleep_duration(
                target_date=target_date,
                sleep_minutes=corrected_minutes,
            )

        if self._looks_like_meal_correction(normalized):
            corrected_calories = self._parse_calories(normalized)
            if corrected_calories is None:
                return "食事の修正は『この昼食を650kcalに修正』のように送ってください。"
            return self._correct_meal_calories(
                normalized=normalized,
                line_user_id=line_user_id,
                target_date=target_date,
                corrected_calories=corrected_calories,
            )

        if self._looks_like_meal_timing_hint(normalized):
            hint_response = self._store_meal_timing_hint(
                normalized=normalized,
                line_user_id=line_user_id,
                target_date=target_date,
                event_time=event_time,
            )
            if hint_response is not None:
                return hint_response

        if any(word in normalized for word in ["食事回数", "摂取カロリー", "食事"]) and any(
            word in normalized
            for word in ["教えて", "確認", "何回", "何kcal", "何キロカロリー", "?"]
        ):
            return self._summarize_meals(target_date=target_date, line_user_id=line_user_id)

        if "健康" in normalized and any(word in normalized for word in ["ログ", "データ", "記録"]):
            return self._summarize_health_log(target_date)

        if "運動" in normalized:
            return self._answer_exercise_question(question=text, target_date=target_date)

        if self._looks_like_meal_text_registration(normalized):
            return self._register_meal_text_entries(
                text=text,
                line_user_id=line_user_id,
                target_date=target_date,
                event_time=event_time,
            )

        return self._answer_general_question(
            question=text,
            target_date=target_date,
            line_user_id=line_user_id,
        )

    def _delete_latest_meal(self, *, line_user_id: str, target_date: date) -> str:
        meal = self.meal_repository.get_latest_for_user(line_user_id, meal_date=target_date)
        if meal is None:
            meal = self.meal_repository.get_latest_for_user(line_user_id)
        if meal is None:
            return (
                "削除できる食事記録が見つかりませんでした。"
                "削除したい日の食事写真を教えてください。"
            )

        deleted_payload = {
            "action": "delete_meal",
            "deleted_at": datetime.now(ZoneInfo(self.settings.timezone)).isoformat(),
            "meal_date": meal.meal_date.isoformat(),
            "source_message_id": meal.source_message_id,
            "estimated_calories": meal.estimated_calories,
            "summary": meal.summary,
            "meal_items": list(meal.meal_items_json),
            "line_user_id": line_user_id,
        }
        self.drive_client.store_json(
            category="corrections",
            target_date=meal.meal_date,
            filename=f"{meal.meal_date.isoformat()}_{meal.source_message_id}_delete_meal.json",
            payload=deleted_payload,
        )
        meal_date = meal.meal_date
        deleted_calories = meal.estimated_calories
        self.meal_repository.delete(meal)
        self.meal_repository.flush()
        self.meal_logging_service.store_daily_summary(meal_date)
        self.line_state_repository.clear(line_user_id)
        total = self.meal_repository.sum_calories_for_date(meal_date)
        count = len(self.meal_repository.list_for_user_and_date(line_user_id, meal_date))
        return (
            f"{meal_date.isoformat()} の最新の食事記録を削除しました。"
            f"削除した推定カロリーは {deleted_calories} kcal です。\n"
            f"その日の食事は現在 {count} 回、合計 {total} kcal です。"
        )

    def _correct_sleep_duration(self, *, target_date: date, sleep_minutes: int) -> str:
        metric = self.metrics_repository.get_daily_metric(target_date)
        original_minutes = metric.sleep_minutes if metric is not None else None
        self.metrics_repository.upsert_sleep_minutes(target_date, sleep_minutes)
        self.metrics_repository.flush()
        self.drive_client.store_json(
            category="corrections",
            target_date=target_date,
            filename=f"{target_date.isoformat()}_sleep_correction.json",
            payload={
                "action": "correct_sleep_duration",
                "corrected_at": datetime.now(ZoneInfo(self.settings.timezone)).isoformat(),
                "date": target_date.isoformat(),
                "before_sleep_minutes": original_minutes,
                "after_sleep_minutes": sleep_minutes,
                "reason": "line user requested correction or manual registration",
            },
        )
        if original_minutes is None:
            return (
                f"{target_date.isoformat()} の睡眠時間を "
                f"{self._format_minutes(sleep_minutes)} で新規登録しました。\n"
                "DB と Drive の補正ログに反映し、今後のトレンド分析とアドバイスに使います。"
            )
        return (
            f"{target_date.isoformat()} の睡眠時間を "
            f"{self._format_minutes(sleep_minutes)} に修正しました。\n"
            "DB と Drive の補正ログに反映し、今後のトレンド分析とアドバイスに使います。"
        )

    def _correct_meal_calories(
        self,
        *,
        normalized: str,
        line_user_id: str,
        target_date: date,
        corrected_calories: int,
    ) -> str:
        meals = self.meal_repository.list_for_user_and_date(line_user_id, target_date)
        if not meals:
            return f"{target_date.isoformat()} の食事記録が見つからないため修正できませんでした。"

        meal = self._pick_meal_from_text(normalized, meals)
        if meal is not None:
            return self._apply_meal_correction(
                meal=meal,
                line_user_id=line_user_id,
                corrected_calories=corrected_calories,
            )

        self.line_state_repository.upsert(
            line_user_id,
            "meal_correction",
            {
                "date": target_date.isoformat(),
                "corrected_calories": corrected_calories,
                "candidate_meal_ids": [meal.id for meal in meals],
            },
        )
        return self._build_candidate_prompt(
            target_date=target_date,
            meals=meals,
            corrected_calories=corrected_calories,
        )

    def _resolve_pending_meal_selection(self, *, normalized: str, line_user_id: str) -> str | None:
        state = self.line_state_repository.get(line_user_id)
        if state is None or state.intent != "meal_correction":
            return None
        selection = self._parse_candidate_index(normalized)
        if selection is None:
            return None

        candidate_ids = state.state_json.get("candidate_meal_ids", [])
        if not isinstance(candidate_ids, list) or selection < 1 or selection > len(candidate_ids):
            return "候補番号が見つかりませんでした。案内した番号で指定してください。"

        meal_id = candidate_ids[selection - 1]
        if not isinstance(meal_id, int):
            return "候補情報の読み取りに失敗しました。もう一度修正内容を送ってください。"

        corrected_calories = state.state_json.get("corrected_calories")
        if not isinstance(corrected_calories, int):
            parsed_calories = self._parse_calories(normalized)
            if parsed_calories is None:
                return (
                    "修正後のカロリーが読み取れませんでした。"
                    "『2番を650kcalに修正』のように送ってください。"
                )
            corrected_calories = parsed_calories

        meal = self.meal_repository.get_by_id(meal_id)
        if meal is None:
            self.line_state_repository.clear(line_user_id)
            return "候補の食事記録が見つかりませんでした。もう一度修正内容を送ってください。"
        return self._apply_meal_correction(
            meal=meal,
            line_user_id=line_user_id,
            corrected_calories=corrected_calories,
        )

    def _apply_meal_correction(
        self,
        *,
        meal: MealRecord,
        line_user_id: str,
        corrected_calories: int,
    ) -> str:
        before_calories = meal.estimated_calories
        self.meal_repository.update_estimated_calories(meal, corrected_calories)
        self.meal_repository.flush()
        self.meal_logging_service.store_daily_summary(meal.meal_date)
        self.line_state_repository.clear(line_user_id)
        self.drive_client.store_json(
            category="corrections",
            target_date=meal.meal_date,
            filename=f"{meal.meal_date.isoformat()}_{meal.source_message_id}_meal_correction.json",
            payload={
                "action": "correct_meal_calories",
                "corrected_at": datetime.now(ZoneInfo(self.settings.timezone)).isoformat(),
                "meal_date": meal.meal_date.isoformat(),
                "source_message_id": meal.source_message_id,
                "before_calories": before_calories,
                "after_calories": corrected_calories,
                "summary": meal.summary,
                "meal_items": list(meal.meal_items_json),
            },
        )
        total = self.meal_repository.sum_calories_for_date(meal.meal_date)
        return (
            f"{meal.meal_date.isoformat()} {self._format_meal_label(meal)} の食事を "
            f"{before_calories} kcal から {corrected_calories} kcal に修正しました。\n"
            f"その日の食事合計は現在 {total} kcal です。"
        )

    def _summarize_meals(self, *, target_date: date, line_user_id: str) -> str:
        meals = self.meal_repository.list_for_user_and_date(line_user_id, target_date)
        total = sum(meal.estimated_calories for meal in meals)
        if not meals:
            return f"{target_date.isoformat()} の食事記録はありません。"
        lines = [f"{target_date.isoformat()} の食事は {len(meals)} 回、合計 {total} kcal です。"]
        for idx, meal in enumerate(meals, start=1):
            lines.append(
                f"{idx}回目 {self._format_meal_label(meal)}: "
                f"{meal.estimated_calories} kcal（{meal.summary}）"
            )
        return "\n".join(lines)

    def _summarize_health_log(self, target_date: date) -> str:
        metric = self.metrics_repository.get_daily_metric(target_date)
        if metric is None:
            return f"{target_date.isoformat()} の健康ログはまだありません。"
        total_meal_calories = self.meal_repository.sum_calories_for_date(target_date)
        meal_count = len(self.meal_repository.list_for_date(target_date))
        return (
            f"{target_date.isoformat()} の健康ログです。\n"
            f"睡眠: {self._format_minutes(metric.sleep_minutes or 0)}\n"
            f"安静時心拍: {metric.resting_hr if metric.resting_hr is not None else '記録なし'}\n"
            f"歩数: {metric.steps or 0} 歩\n"
            f"食事: {meal_count} 回 / {total_meal_calories} kcal"
        )

    def _resolve_pending_meal_time_confirmation(
        self,
        *,
        normalized: str,
        line_user_id: str,
        event_time: datetime,
    ) -> str | None:
        state = self.line_state_repository.get(line_user_id)
        if state is None or state.intent != "pending_meal_time_confirmation":
            return None
        if not self._looks_like_meal_timing_hint(normalized):
            return None

        expires_at = str(state.state_json.get("expires_at", ""))
        meal_id = state.state_json.get("meal_id")
        if not expires_at or not isinstance(meal_id, int):
            self.line_state_repository.clear(line_user_id)
            return None
        if event_time > datetime.fromisoformat(expires_at):
            self.line_state_repository.clear(line_user_id)
            return None

        meal = self.meal_repository.get_by_id(meal_id)
        if meal is None:
            self.line_state_repository.clear(line_user_id)
            return "直前の食事記録が見つからなかったため、もう一度写真か食事内容を送ってください。"

        consumed_at = self._parse_consumed_at_hint(normalized, target_date=meal.meal_date)
        if consumed_at is None:
            return (
                "食べた時刻を読み取れませんでした。"
                "『18:30ごろ食べた』『朝7時ごろです』のように送ってください。"
            )

        meal_date = resolve_meal_service_date(
            consumed_at,
            timezone=self.settings.timezone,
            rollover_hour=self.settings.meal_day_rollover_hour,
        )
        self.meal_repository.update_consumed_at(meal, consumed_at, meal_date)
        self.meal_repository.flush()
        self.meal_logging_service.store_daily_summary(meal_date)
        self.line_state_repository.clear(line_user_id)
        self.drive_client.store_json(
            category="corrections",
            target_date=meal_date,
            filename=f"{meal_date.isoformat()}_{meal.source_message_id}_meal_time_correction.json",
            payload={
                "action": "correct_meal_time",
                "corrected_at": datetime.now(ZoneInfo(self.settings.timezone)).isoformat(),
                "meal_id": meal.id,
                "source_message_id": meal.source_message_id,
                "meal_date": meal_date.isoformat(),
                "consumed_at": consumed_at.isoformat(),
                "summary": meal.summary,
            },
        )
        time_text = format_meal_service_time(
            consumed_at,
            timezone=self.settings.timezone,
            rollover_hour=self.settings.meal_day_rollover_hour,
        )
        return (
            f"{meal_date.isoformat()} の食事時刻を "
            f"{time_text} ごろに更新しました。\n"
            "今後の食事回数集計と健康アドバイスに反映します。"
        )

    def _resolve_pending_meal_followup(
        self,
        *,
        text: str,
        normalized: str,
        line_user_id: str,
        target_date: date,
        event_time: datetime,
    ) -> str | None:
        state = self.line_state_repository.get(line_user_id)
        if state is None or state.intent != "meal_reminder_followup":
            return None
        expires_at = str(state.state_json.get("expires_at", ""))
        if not expires_at or event_time > datetime.fromisoformat(expires_at):
            self.line_state_repository.clear(line_user_id)
            return None
        if not self._looks_like_meal_text_registration(normalized):
            return None
        reminder_date = state.state_json.get("date")
        effective_target_date = target_date
        if isinstance(reminder_date, str):
            effective_target_date = date.fromisoformat(reminder_date)
        return self._register_meal_text_entries(
            text=text,
            line_user_id=line_user_id,
            target_date=effective_target_date,
            event_time=event_time,
            clear_state=True,
        )

    def _register_meal_text_entries(
        self,
        *,
        text: str,
        line_user_id: str,
        target_date: date,
        event_time: datetime,
        clear_state: bool = False,
    ) -> str:
        try:
            parsed = self.llm_provider.parse_meal_text(
                text=text, target_date=target_date.isoformat()
            )
        except Exception:
            parsed = self._fallback_parse_meal_text(text)
        if not parsed.meals:
            return (
                "食事内容を読み取れませんでした。"
                "『朝7:30におにぎり、昼12:15にラーメン』のように送ってください。"
            )

        saved_meals: list[MealRecord] = []
        for idx, entry in enumerate(parsed.meals, start=1):
            consumed_at = self._resolve_parsed_meal_time(
                time_text=entry.time_text,
                target_date=target_date,
                fallback=event_time,
                index=idx,
            )
            meal_date = resolve_meal_service_date(
                consumed_at,
                timezone=self.settings.timezone,
                rollover_hour=self.settings.meal_day_rollover_hour,
            )
            synthetic_id = f"text-{line_user_id}-{event_time.strftime('%Y%m%d%H%M%S%f')}-{idx}"
            payload = {
                "source": "line_text",
                "meal_date": meal_date.isoformat(),
                "original_text": text,
                "consumed_at": consumed_at.isoformat(),
                "summary": entry.summary,
                "meal_items": list(entry.meal_items),
                "estimated_calories": entry.estimated_calories,
                "confidence": entry.confidence,
                "provider": parsed.provider,
                "model_name": parsed.model_name,
            }
            analysis_file_id = self.drive_client.store_json(
                category="meal_records",
                target_date=target_date,
                filename=f"{target_date.isoformat()}_{synthetic_id}_manual_meal.json",
                payload=payload,
            )
            self.meal_repository.upsert(
                MealRecordInput(
                    source_message_id=synthetic_id,
                    line_user_id=line_user_id,
                    meal_date=meal_date,
                    consumed_at=consumed_at,
                    image_mime_type="text/plain",
                    estimated_calories=entry.estimated_calories,
                    confidence=entry.confidence,
                    summary=entry.summary,
                    meal_items=entry.meal_items,
                    rationale="line text registration",
                    analysis_drive_file_id=analysis_file_id,
                    provider=parsed.provider,
                    model_name=parsed.model_name,
                )
            )
            self.meal_repository.flush()
            meal = self.meal_repository.get_by_source_message_id(synthetic_id)
            if meal is not None:
                saved_meals.append(meal)

        self.meal_logging_service.store_daily_summary(target_date)
        if clear_state:
            self.line_state_repository.clear(line_user_id)
        total = self.meal_repository.sum_calories_for_date(target_date)
        lines = [f"{target_date.isoformat()} の食事を {len(saved_meals)} 件追加登録しました。"]
        for meal in saved_meals:
            time_label = format_meal_service_time(
                meal.consumed_at,
                timezone=self.settings.timezone,
                rollover_hour=self.settings.meal_day_rollover_hour,
            )
            lines.append(
                f"- {time_label} {meal.summary} / {meal.estimated_calories} kcal"
            )
        lines.append(f"現在の合計は {total} kcal です。")
        return "\n".join(lines)

    def _store_meal_timing_hint(
        self,
        *,
        normalized: str,
        line_user_id: str,
        target_date: date,
        event_time: datetime,
    ) -> str | None:
        consumed_at = self._parse_consumed_at_hint(normalized, target_date=target_date)
        if consumed_at is None:
            return None
        expires_at = event_time + timedelta(minutes=self.settings.meal_timing_hint_ttl_minutes)
        self.line_state_repository.upsert(
            line_user_id,
            "pending_meal_timing_hint",
            {
                "consumed_at": consumed_at.isoformat(),
                "expires_at": expires_at.isoformat(),
            },
        )
        return (
            f"次に送る食事写真を {consumed_at.strftime('%H:%M')} ごろの食事として記録します。\n"
            "画像だけ送っても自動登録できます。"
        )

    def _answer_exercise_question(self, *, question: str, target_date: date) -> str:
        context = self._build_question_context(target_date)
        try:
            return self.llm_provider.answer_health_question(question=question, context=context)
        except Exception:
            advice = (
                self.advice_repository.get_advice(target_date)
                or self.advice_repository.get_latest_advice()
            )
            if advice is not None:
                return (
                    f"{target_date.isoformat()} 時点の記録では、{advice.exercise_advice} "
                    f"今日のポイントは {advice.today_actions_json[0]} です。"
                )
            return "今日は強度を上げすぎず、散歩や軽い有酸素から始めるのがおすすめです。"

    def _answer_general_question(
        self,
        *,
        question: str,
        target_date: date,
        line_user_id: str,
    ) -> str:
        context = self._build_question_context(target_date)
        context["meal_query"] = self._meal_query_context(
            line_user_id=line_user_id,
            target_date=target_date,
        )
        try:
            return self.llm_provider.answer_health_question(question=question, context=context)
        except Exception:
            return (
                "記録を確認しました。詳しい指示は簡潔にお伝えしますので、"
                "『昨日の食事回数を教えて』『昼食を650kcalに修正』のように送ってください。"
            )

    def _build_question_context(self, target_date: date) -> dict[str, Any]:
        metric = self.metrics_repository.get_daily_metric(target_date)
        advice = (
            self.advice_repository.get_advice(target_date)
            or self.advice_repository.get_latest_advice()
        )
        meals = self.meal_repository.list_for_date(target_date)
        return {
            "date": target_date.isoformat(),
            "metric": {
                "sleep_minutes": metric.sleep_minutes if metric else None,
                "resting_hr": metric.resting_hr if metric else None,
                "steps": metric.steps if metric else None,
                "fitbit_calories": metric.calories if metric else None,
                "meal_calories": self.meal_repository.sum_calories_for_date(target_date),
            },
            "meals": [
                {
                    "time": format_meal_service_time(
                        meal.consumed_at,
                        timezone=self.settings.timezone,
                        rollover_hour=self.settings.meal_day_rollover_hour,
                    ),
                    "estimated_calories": meal.estimated_calories,
                    "summary": meal.summary,
                    "meal_items": list(meal.meal_items_json),
                }
                for meal in meals
            ],
            "advice": {
                "risk_level": advice.risk_level if advice else None,
                "summary": advice.summary if advice else None,
                "today_actions": advice.today_actions_json if advice else [],
                "exercise_advice": advice.exercise_advice if advice else None,
                "long_term_comment": advice.long_term_comment if advice else None,
            },
        }

    def _meal_query_context(self, *, line_user_id: str, target_date: date) -> dict[str, Any]:
        meals = self.meal_repository.list_for_user_and_date(line_user_id, target_date)
        return {
            "meal_count": len(meals),
            "meal_total_calories": sum(meal.estimated_calories for meal in meals),
        }

    def _pick_meal_from_text(self, text: str, meals: list[MealRecord]) -> MealRecord | None:
        index = self._parse_candidate_index(text)
        if index is not None and 1 <= index <= len(meals):
            return meals[index - 1]

        daypart = self._parse_daypart(text)
        if daypart is None:
            return meals[-1] if len(meals) == 1 else None

        matched = [meal for meal in meals if self._meal_matches_daypart(meal, daypart)]
        if len(matched) == 1:
            return matched[0]
        if not matched and len(meals) == 1:
            return meals[0]
        return None

    def _build_candidate_prompt(
        self,
        *,
        target_date: date,
        meals: list[MealRecord],
        corrected_calories: int,
    ) -> str:
        lines = [
            (
                f"{target_date.isoformat()} の候補が複数あるので、"
                "修正したい食事を番号で指定してください。"
            ),
            f"例:『2番を{corrected_calories}kcalに修正』",
        ]
        for idx, meal in enumerate(meals, start=1):
            lines.append(
                f"{idx}番 {self._format_meal_label(meal)} / "
                f"{meal.estimated_calories} kcal（{meal.summary}）"
            )
        return "\n".join(lines)

    def _resolve_date(self, text: str, event_timestamp_ms: int) -> date:
        base_date = self._event_datetime(event_timestamp_ms).date()
        if "一昨日" in text:
            return base_date - timedelta(days=2)
        if "昨日" in text:
            return base_date - timedelta(days=1)
        if "今日" in text:
            return base_date
        match = re.search(r"(20\d{2})[-/年](\d{1,2})[-/月](\d{1,2})", text)
        if match:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        return base_date

    @staticmethod
    def _normalize_text(text: str) -> str:
        return text.translate(str.maketrans("０１２３４５６７８９", "0123456789")).strip()

    @staticmethod
    def _parse_sleep_minutes(text: str) -> int | None:
        match = re.search(r"(\d+)\s*時間(?:\s*(\d+)\s*分)?", text)
        if match:
            hours = int(match.group(1))
            minutes = int(match.group(2) or 0)
            return hours * 60 + minutes
        minute_match = re.search(r"(\d+)\s*分", text)
        if minute_match:
            total = int(minute_match.group(1))
            return total if total > 0 else None
        return None

    @staticmethod
    def _parse_calories(text: str) -> int | None:
        match = re.search(r"(\d+)\s*(?:kcal|キロカロリー|cal)", text, flags=re.IGNORECASE)
        if match:
            return int(match.group(1))
        return None

    @staticmethod
    def _parse_candidate_index(text: str) -> int | None:
        match = re.search(r"(\d+)\s*番", text)
        if match:
            return int(match.group(1))
        return None

    @staticmethod
    def _parse_daypart(text: str) -> str | None:
        if "朝食" in text:
            return "breakfast"
        if "昼食" in text or "ランチ" in text:
            return "lunch"
        if "夕食" in text or "夜ご飯" in text or "晩ごはん" in text:
            return "dinner"
        return None

    @staticmethod
    def _looks_like_meal_selection(text: str) -> bool:
        return "番" in text and any(word in text for word in ["修正", "訂正", "変更", "直して"])

    @staticmethod
    def _looks_like_sleep_correction(text: str) -> bool:
        if "睡眠" not in text:
            return False
        correction_words = [
            "修正",
            "訂正",
            "変更",
            "直して",
            "記録し直",
            "登録し直",
            "再登録",
            "上書き",
            "更新",
        ]
        return any(word in text for word in correction_words)

    @staticmethod
    def _looks_like_meal_correction(text: str) -> bool:
        if not any(word in text for word in ["修正", "訂正", "変更", "直して"]):
            return False
        meal_words = ["食事", "朝食", "昼食", "ランチ", "夕食", "夜ご飯", "晩ごはん"]
        if any(word in text for word in meal_words):
            return True
        return "kcal" in text or "キロカロリー" in text

    @staticmethod
    def _looks_like_meal_timing_hint(text: str) -> bool:
        meal_words = [
            "食事",
            "写真",
            "画像",
            "朝食",
            "昼食",
            "夕食",
            "夜食",
            "食べた",
            "食べました",
        ]
        if not any(word in text for word in meal_words):
            return False
        return bool(
            re.search(r"(\d{1,2})[:時](\d{1,2})?", text)
            or "半" in text
            or any(word in text for word in ["朝", "昼", "夕方", "夜"])
        )

    @staticmethod
    def _looks_like_meal_text_registration(text: str) -> bool:
        meal_words = [
            "朝",
            "昼",
            "夜",
            "夕",
            "間食",
            "食べた",
            "食べました",
            "おにぎり",
            "ごはん",
            "パン",
        ]
        return any(word in text for word in meal_words)

    @staticmethod
    def _meal_matches_daypart(meal: MealRecord, daypart: str) -> bool:
        hour = meal.consumed_at.hour
        if daypart == "breakfast":
            return 4 <= hour < 11
        if daypart == "lunch":
            return 11 <= hour < 15
        if daypart == "dinner":
            return 17 <= hour <= 23
        return False

    @staticmethod
    def _format_minutes(total_minutes: int) -> str:
        hours = total_minutes // 60
        minutes = total_minutes % 60
        return f"{hours}時間{minutes:02d}分"

    def _format_meal_label(self, meal: MealRecord) -> str:
        time_text = format_meal_service_time(
            meal.consumed_at,
            timezone=self.settings.timezone,
            rollover_hour=self.settings.meal_day_rollover_hour,
        )
        return f"{time_text}頃の食事"

    def _parse_consumed_at_hint(self, text: str, *, target_date: date) -> datetime | None:
        explicit = re.search(r"(\d{1,2})\s*[:時]\s*(\d{1,2})?", text)
        if explicit:
            hour = int(explicit.group(1))
            minute = int(explicit.group(2) or 0)
            if "半" in text and explicit.group(2) is None:
                minute = 30
            return datetime(
                target_date.year,
                target_date.month,
                target_date.day,
                hour,
                minute,
                tzinfo=ZoneInfo(self.settings.timezone),
            )
        if "朝" in text:
            return self._slot_datetime(target_date, "朝")
        if "昼" in text:
            return self._slot_datetime(target_date, "昼")
        if "夕方" in text:
            return self._slot_datetime(target_date, "夕方")
        if "夜" in text or "夕食" in text:
            return self._slot_datetime(target_date, "夜")
        return None

    def _resolve_parsed_meal_time(
        self,
        *,
        time_text: str | None,
        target_date: date,
        fallback: datetime,
        index: int,
    ) -> datetime:
        if time_text:
            parsed = self._parse_consumed_at_hint(time_text, target_date=target_date)
            if parsed is not None:
                return parsed
        defaults = [
            self._slot_datetime(target_date, "朝"),
            self._slot_datetime(target_date, "昼"),
            self._slot_datetime(target_date, "夜"),
            self._slot_datetime(target_date, "間食"),
        ]
        if target_date == fallback.date():
            return fallback
        return defaults[min(index - 1, len(defaults) - 1)]

    def _slot_datetime(self, target_date: date, slot: str) -> datetime:
        mapping = {
            "朝": (8, 0),
            "昼": (12, 30),
            "夕方": (16, 0),
            "夜": (19, 0),
            "間食": (15, 0),
        }
        hour, minute = mapping.get(slot, (12, 0))
        return datetime(
            target_date.year,
            target_date.month,
            target_date.day,
            hour,
            minute,
            tzinfo=ZoneInfo(self.settings.timezone),
        )

    def _event_datetime(self, event_timestamp_ms: int) -> datetime:
        return datetime.fromtimestamp(
            event_timestamp_ms / 1000,
            tz=ZoneInfo(self.settings.timezone),
        )

    def _fallback_parse_meal_text(self, text: str) -> MealTextParseResult:
        entries: list[ParsedMealEntry] = []
        normalized = text.replace("、", "\n").replace("。", "\n")
        for line in [item.strip() for item in normalized.splitlines() if item.strip()]:
            time_text = None
            if "朝" in line:
                time_text = "朝"
            elif "昼" in line:
                time_text = "昼"
            elif "夕" in line or "夜" in line:
                time_text = "夜"
            calories = 400
            if "ラーメン" in line or "丼" in line:
                calories = 700
            elif "おにぎり" in line or "パン" in line:
                calories = 250
            entries.append(
                ParsedMealEntry(
                    time_text=time_text,
                    summary=line,
                    meal_items=[line],
                    estimated_calories=calories,
                    confidence="low",
                )
            )
        return MealTextParseResult(
            meals=entries,
            note="local fallback parser",
            provider="fallback",
            model_name="fallback",
        )
