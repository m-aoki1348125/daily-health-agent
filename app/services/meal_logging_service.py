from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.clients.drive_client import DriveClient
from app.clients.line_client import LineClient
from app.clients.llm_base import LLMProvider
from app.config.settings import Settings
from app.repositories.line_state_repository import LineStateRepository
from app.repositories.meal_repository import MealRepository
from app.schemas.meal_estimate import MealEstimateResult, MealRecordInput
from app.services.meal_time_service import format_meal_service_time, resolve_meal_service_date


@dataclass
class MealLoggingService:
    settings: Settings
    line_client: LineClient
    drive_client: DriveClient
    llm_provider: LLMProvider
    meal_repository: MealRepository
    line_state_repository: LineStateRepository | None = None

    def process_image_message(
        self,
        *,
        message_id: str,
        reply_token: str,
        line_user_id: str,
        event_timestamp_ms: int,
    ) -> str:
        existing = self.meal_repository.get_by_source_message_id(message_id)
        if existing is not None:
            message = (
                "この食事画像は記録済みです。"
                f"推定摂取カロリーは {existing.estimated_calories} kcal でした。"
            )
            self.line_client.reply_message(reply_token, message)
            return message

        image_bytes, mime_type = self.line_client.fetch_message_content(message_id)
        event_time = datetime.fromtimestamp(
            event_timestamp_ms / 1000,
            tz=ZoneInfo(self.settings.timezone),
        )
        consumed_at = self._resolve_consumed_at(
            line_user_id=line_user_id,
            fallback=event_time,
        )
        estimate = self.llm_provider.estimate_meal(
            prompt=self._build_prompt(consumed_at),
            image_bytes=image_bytes,
            mime_type=mime_type,
        )
        target_date = resolve_meal_service_date(
            consumed_at,
            timezone=self.settings.timezone,
            rollover_hour=self.settings.meal_day_rollover_hour,
        )
        timestamp_label = consumed_at.strftime("%H%M%S")
        extension = mimetypes.guess_extension(mime_type, strict=False) or ".jpg"
        if extension == ".jpe":
            extension = ".jpg"
        image_filename = f"{target_date.isoformat()}_{timestamp_label}_{message_id}{extension}"
        image_drive_file_id = self.drive_client.store_bytes(
            category="meal_images",
            target_date=target_date,
            filename=image_filename,
            content=image_bytes,
            mime_type=mime_type,
        )
        analysis_payload = self._build_analysis_payload(
            message_id=message_id,
            consumed_at=consumed_at,
            estimate=estimate,
            image_drive_file_id=image_drive_file_id,
            mime_type=mime_type,
        )
        analysis_filename = (
            f"{target_date.isoformat()}_{timestamp_label}_{message_id}_meal_estimate.json"
        )
        analysis_drive_file_id = self.drive_client.store_json(
            category="meal_records",
            target_date=target_date,
            filename=analysis_filename,
            payload=analysis_payload,
        )
        meal = MealRecordInput(
            source_message_id=message_id,
            line_user_id=line_user_id,
            meal_date=target_date,
            consumed_at=consumed_at,
            image_mime_type=mime_type,
            estimated_calories=estimate.estimated_calories,
            confidence=estimate.confidence,
            summary=estimate.summary,
            meal_items=estimate.meal_items,
            rationale=estimate.rationale,
            image_drive_file_id=image_drive_file_id,
            analysis_drive_file_id=analysis_drive_file_id,
            provider=estimate.provider,
            model_name=estimate.model_name,
        )
        self.meal_repository.upsert(meal)
        self.meal_repository.flush()
        stored_meal = self.meal_repository.get_by_source_message_id(message_id)
        if stored_meal is not None:
            self._store_post_image_timing_state(
                line_user_id=line_user_id,
                meal_id=stored_meal.id,
                event_time=event_time,
            )
        self.store_daily_summary(target_date)
        total_for_day = self.meal_repository.sum_calories_for_date(target_date)
        time_text = format_meal_service_time(
            consumed_at,
            timezone=self.settings.timezone,
            rollover_hour=self.settings.meal_day_rollover_hour,
        )
        reply_text = (
            f"食事を記録しました。推定摂取カロリーは {estimate.estimated_calories} kcal です。\n"
            f"記録時刻: {time_text} ごろ\n"
            f"今日の累計は {total_for_day} kcal です。\n"
            "明朝の健康アドバイスにも反映します。"
        )
        self.line_client.reply_message(reply_token, reply_text)
        return reply_text

    def store_daily_summary(self, target_date: date) -> None:
        meals = self.meal_repository.list_for_date(target_date)
        payload = {
            "date": target_date.isoformat(),
            "total_estimated_calories": sum(item.estimated_calories for item in meals),
            "meal_count": len(meals),
            "meals": [
                {
                    "source_message_id": item.source_message_id,
                    "consumed_at": item.consumed_at.isoformat(),
                    "estimated_calories": item.estimated_calories,
                    "confidence": item.confidence,
                    "summary": item.summary,
                    "meal_items": item.meal_items_json,
                    "provider": item.provider,
                    "model_name": item.model_name,
                    "analysis_drive_file_id": item.analysis_drive_file_id,
                    "image_drive_file_id": item.image_drive_file_id,
                }
                for item in meals
            ],
        }
        self.drive_client.store_json(
            category="meal_records",
            target_date=target_date,
            filename=f"{target_date.isoformat()}_meal_summary.json",
            payload=payload,
        )

    @staticmethod
    def _build_prompt(consumed_at: datetime) -> str:
        return (
            f"この写真は {consumed_at.strftime('%Y-%m-%d %H:%M')} 頃の食事です。"
            "料理名を短く列挙し、食事全体の推定摂取カロリーを整数kcalで返してください。"
            "飲み物や付け合わせも見える場合は反映してください。"
        )

    @staticmethod
    def _build_analysis_payload(
        *,
        message_id: str,
        consumed_at: datetime,
        estimate: MealEstimateResult,
        image_drive_file_id: str,
        mime_type: str,
    ) -> dict[str, object]:
        return {
            "source_message_id": message_id,
            "consumed_at": consumed_at.isoformat(),
            "image_mime_type": mime_type,
            "image_drive_file_id": image_drive_file_id,
            "estimated_calories": estimate.estimated_calories,
            "confidence": estimate.confidence,
            "summary": estimate.summary,
            "meal_items": estimate.meal_items,
            "rationale": estimate.rationale,
            "provider": estimate.provider,
            "model_name": estimate.model_name,
        }

    def _resolve_consumed_at(self, *, line_user_id: str, fallback: datetime) -> datetime:
        if self.line_state_repository is None:
            return fallback
        state = self.line_state_repository.get(line_user_id)
        if state is None or state.intent != "pending_meal_timing_hint":
            return fallback

        expires_at = str(state.state_json.get("expires_at", ""))
        consumed_at_text = str(state.state_json.get("consumed_at", ""))
        if not expires_at or not consumed_at_text:
            self.line_state_repository.clear(line_user_id)
            return fallback
        if fallback > datetime.fromisoformat(expires_at):
            self.line_state_repository.clear(line_user_id)
            return fallback
        self.line_state_repository.clear(line_user_id)
        return datetime.fromisoformat(consumed_at_text)

    def _store_post_image_timing_state(
        self,
        *,
        line_user_id: str,
        meal_id: int,
        event_time: datetime,
    ) -> None:
        if self.line_state_repository is None:
            return
        expires_at = event_time.replace(microsecond=0) + self._timing_ttl(
            self.settings.meal_post_image_timing_ttl_minutes
        )
        self.line_state_repository.upsert(
            line_user_id,
            "pending_meal_time_confirmation",
            {
                "meal_id": meal_id,
                "expires_at": expires_at.isoformat(),
            },
        )

    @staticmethod
    def _timing_ttl(minutes: int) -> timedelta:
        return timedelta(minutes=minutes)
