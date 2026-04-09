from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.clients.drive_client import DriveClient
from app.clients.llm_base import LLMProvider
from app.config.settings import Settings
from app.repositories.advice_repository import AdviceRepository
from app.repositories.meal_repository import MealRepository
from app.repositories.metrics_repository import MetricsRepository
from app.services.meal_logging_service import MealLoggingService


@dataclass
class HealthChatService:
    settings: Settings
    drive_client: DriveClient
    llm_provider: LLMProvider
    meal_repository: MealRepository
    metrics_repository: MetricsRepository
    advice_repository: AdviceRepository
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

        if "削除" in normalized and ("食事" in normalized or "写真" in normalized):
            return self._delete_latest_meal(line_user_id=line_user_id, target_date=target_date)

        if "睡眠" in normalized and any(word in normalized for word in ["修正", "訂正", "変更"]):
            corrected_minutes = self._parse_sleep_minutes(normalized)
            if corrected_minutes is None:
                return "睡眠時間の修正は『昨日の睡眠時間を8時間10分に修正』のように送ってください。"
            return self._correct_sleep_duration(
                target_date=target_date,
                sleep_minutes=corrected_minutes,
            )

        if any(word in normalized for word in ["食事回数", "摂取カロリー", "食事"]) and any(
            word in normalized
            for word in ["教えて", "確認", "何回", "何kcal", "何キロカロリー", "?"]
        ):
            return self._summarize_meals(target_date=target_date, line_user_id=line_user_id)

        if "健康" in normalized and any(word in normalized for word in ["ログ", "データ", "記録"]):
            return self._summarize_health_log(target_date)

        if "運動" in normalized:
            return self._answer_exercise_question(question=text, target_date=target_date)

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
        total = self.meal_repository.sum_calories_for_date(meal_date)
        count = len(self.meal_repository.list_for_user_and_date(line_user_id, meal_date))
        return (
            f"{meal_date.isoformat()} の最新の食事記録を削除しました。"
            f"削除した推定カロリーは {deleted_calories} kcal です。\n"
            f"その日の食事は現在 {count} 回、合計 {total} kcal です。"
        )

    def _correct_sleep_duration(self, *, target_date: date, sleep_minutes: int) -> str:
        metric = self.metrics_repository.get_daily_metric(target_date)
        if metric is None:
            return f"{target_date.isoformat()} の睡眠記録が見つからないため修正できませんでした。"
        original_minutes = metric.sleep_minutes or 0
        self.metrics_repository.update_sleep_minutes(target_date, sleep_minutes)
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
                "reason": "line user requested correction",
            },
        )
        return (
            f"{target_date.isoformat()} の睡眠時間を "
            f"{self._format_minutes(sleep_minutes)} に修正しました。\n"
            "今後のトレンド分析とアドバイスに反映します。"
        )

    def _summarize_meals(self, *, target_date: date, line_user_id: str) -> str:
        meals = self.meal_repository.list_for_user_and_date(line_user_id, target_date)
        total = sum(meal.estimated_calories for meal in meals)
        if not meals:
            return f"{target_date.isoformat()} の食事記録はありません。"
        lines = [
            f"{target_date.isoformat()} の食事は {len(meals)} 回、合計 {total} kcal です。"
        ]
        for idx, meal in enumerate(meals, start=1):
            meal_time = meal.consumed_at.astimezone(ZoneInfo(self.settings.timezone)).strftime(
                "%H:%M"
            )
            lines.append(
                f"{idx}回目 {meal_time}: "
                f"{meal.estimated_calories} kcal（{meal.summary}）"
            )
        return "\n".join(lines)

    def _summarize_health_log(self, target_date: date) -> str:
        metric = self.metrics_repository.get_daily_metric(target_date)
        if metric is None:
            return f"{target_date.isoformat()} の健康ログはまだありません。"
        total_meal_calories = metric.meal_calories or 0
        meal_count = len(self.meal_repository.list_for_date(target_date))
        return (
            f"{target_date.isoformat()} の健康ログです。\n"
            f"睡眠: {self._format_minutes(metric.sleep_minutes or 0)}\n"
            f"安静時心拍: {metric.resting_hr if metric.resting_hr is not None else '記録なし'}\n"
            f"歩数: {metric.steps or 0} 歩\n"
            f"食事: {meal_count} 回 / {total_meal_calories} kcal"
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
                "『昨日の食事回数を教えて』『睡眠時間を8時間に修正』のように送ってください。"
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
                "meal_calories": metric.meal_calories if metric else None,
            },
            "meals": [
                {
                    "time": meal.consumed_at.astimezone(ZoneInfo(self.settings.timezone)).strftime(
                        "%H:%M"
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

    def _resolve_date(self, text: str, event_timestamp_ms: int) -> date:
        base_date = datetime.fromtimestamp(
            event_timestamp_ms / 1000, tz=ZoneInfo(self.settings.timezone)
        ).date()
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
    def _format_minutes(total_minutes: int) -> str:
        hours = total_minutes // 60
        minutes = total_minutes % 60
        return f"{hours}時間{minutes:02d}分"
