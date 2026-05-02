from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from datetime import date
from typing import Any, cast

import google.auth
import httpx
from google.cloud import secretmanager

from app.config.settings import Settings
from app.schemas.health_features import ActivitySummary, BodySummary, FitbitDayRaw, SleepSummary


class FitbitClient(ABC):
    @abstractmethod
    def fetch_day(self, target_date: date) -> FitbitDayRaw:
        raise NotImplementedError


class MockFitbitClient(FitbitClient):
    def fetch_day(self, target_date: date) -> FitbitDayRaw:
        raw_payload: dict[str, Any] = {
            "sleep": {
                "total_minutes": 352,
                "efficiency": 88.0,
                "deep_minutes": 72,
                "rem_minutes": 81,
                "awakenings": 2,
                "start_time": f"{target_date.isoformat()}T00:38:00+09:00",
            },
            "resting_hr": 59,
            "activity": {"steps": 8420, "calories": 2150},
            "body": {
                "weight_kg": 64.2,
                "bmi": 21.9,
                "body_fat_percent": 18.4,
                "source": "mock",
                "logged_at": f"{target_date.isoformat()}T07:10:00",
            },
        }
        return FitbitDayRaw(
            date=target_date,
            sleep=SleepSummary(**raw_payload["sleep"]),
            resting_hr=raw_payload["resting_hr"],
            activity=ActivitySummary(**raw_payload["activity"]),
            body=BodySummary(**raw_payload["body"]),
            raw_payload=raw_payload,
        )


class FitbitApiClient(FitbitClient):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.logger = logging.getLogger(__name__)
        self._access_token: str | None = None
        self._access_token_expires_at: float = 0.0

    def _build_client(self) -> httpx.Client:
        return httpx.Client(timeout=self.settings.request_timeout_seconds)

    def fetch_day(self, target_date: date) -> FitbitDayRaw:
        if not all(
            [
                self.settings.fitbit_client_id,
                self.settings.fitbit_client_secret,
                self.settings.fitbit_refresh_token,
            ]
        ):
            raise ValueError("Fitbit API mode requires client id, client secret, and refresh token")
        token = self._get_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        sleep_url = (
            f"{self.settings.fitbit_base_url}/1.2/user/-/sleep/date/{target_date.isoformat()}.json"
        )
        hr_url = (
            f"{self.settings.fitbit_base_url}/1/user/-/activities/heart/date/"
            f"{target_date.isoformat()}/1d.json"
        )
        activity_url = (
            f"{self.settings.fitbit_base_url}/1/user/-/activities/date/"
            f"{target_date.isoformat()}.json"
        )
        weight_url = (
            f"{self.settings.fitbit_base_url}/1/user/-/body/log/weight/date/"
            f"{target_date.isoformat()}.json"
        )
        fat_url = (
            f"{self.settings.fitbit_base_url}/1/user/-/body/log/fat/date/"
            f"{target_date.isoformat()}.json"
        )
        with self._build_client() as client:
            sleep_resp = self._send_with_retry(client, "GET", sleep_url, headers=headers)
            hr_resp = self._send_with_retry(client, "GET", hr_url, headers=headers)
            activity_resp = self._send_with_retry(client, "GET", activity_url, headers=headers)
            weight_json = self._fetch_optional_body_json(
                client, weight_url, headers=headers, endpoint_name="body_weight"
            )
            fat_json = self._fetch_optional_body_json(
                client, fat_url, headers=headers, endpoint_name="body_fat"
            )
        sleep_json = sleep_resp.json()
        hr_json = hr_resp.json()
        activity_json = activity_resp.json()
        sleep_records = sleep_json.get("sleep") or []
        aggregated_sleep = _aggregate_sleep_records(sleep_records)
        body_summary = _build_body_summary(
            weight_json.get("weight") or [],
            fat_json.get("fat") or [],
        )
        summary = activity_json.get("summary", {})
        resting_hr = None
        value_list = hr_json.get("activities-heart", [])
        if value_list:
            resting_hr = value_list[0].get("value", {}).get("restingHeartRate")
        raw_payload = {
            "sleep": sleep_json,
            "heart": hr_json,
            "activity": activity_json,
            "body_weight": weight_json,
            "body_fat": fat_json,
        }
        return FitbitDayRaw(
            date=target_date,
            sleep=aggregated_sleep,
            resting_hr=resting_hr,
            activity=ActivitySummary(
                steps=int(summary.get("steps", 0)),
                calories=int(summary.get("caloriesOut", 0)),
            ),
            body=body_summary,
            raw_payload=raw_payload,
        )

    def _get_access_token(self) -> str:
        if self._access_token and time.monotonic() < self._access_token_expires_at:
            return self._access_token
        return self._refresh_access_token()

    def _refresh_access_token(self) -> str:
        client_id = self.settings.fitbit_client_id
        client_secret = self.settings.fitbit_client_secret
        refresh_token = self.settings.fitbit_refresh_token
        if not client_id or not client_secret or not refresh_token:
            raise ValueError("Fitbit credentials are not fully configured")
        token_url = f"{self.settings.fitbit_base_url}/oauth2/token"
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
        }
        with self._build_client() as client:
            response = client.post(
                token_url,
                data=payload,
                auth=(client_id, client_secret),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
        token_payload = response.json()
        access_token = token_payload.get("access_token")
        if not access_token:
            raise ValueError("Fitbit token refresh response did not include access_token")
        expires_in = int(token_payload.get("expires_in", 3600))
        self._access_token = str(access_token)
        self._access_token_expires_at = time.monotonic() + max(0, expires_in - 60)
        next_refresh_token = token_payload.get("refresh_token")
        if isinstance(next_refresh_token, str) and next_refresh_token:
            self.settings.fitbit_refresh_token = next_refresh_token
            self._store_refresh_token(next_refresh_token)
        return self._access_token

    def _send_with_retry(
        self,
        client: httpx.Client,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        max_attempts: int = 3,
    ) -> httpx.Response:
        response: httpx.Response | None = None
        for attempt in range(1, max_attempts + 1):
            response = client.request(method, url, headers=headers)
            if response.status_code != 429:
                response.raise_for_status()
                return response

            if attempt == max_attempts:
                response.raise_for_status()

            retry_after = self._parse_retry_after_seconds(response)
            self.logger.warning(
                "fitbit rate limited request",
                extra={"url": url, "attempt": attempt, "retry_after_seconds": retry_after},
            )
            time.sleep(retry_after)

        assert response is not None
        return response

    @staticmethod
    def _parse_retry_after_seconds(response: httpx.Response) -> float:
        header_value = response.headers.get("Retry-After")
        if not header_value:
            return 2.0
        try:
            return max(1.0, float(header_value))
        except ValueError:
            return 2.0

    def _fetch_optional_body_json(
        self,
        client: httpx.Client,
        url: str,
        *,
        headers: dict[str, str],
        endpoint_name: str,
    ) -> dict[str, Any]:
        try:
            return cast(
                dict[str, Any],
                self._send_with_retry(client, "GET", url, headers=headers).json(),
            )
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            if status_code not in {403, 404}:
                raise
            self.logger.warning(
                "fitbit body endpoint unavailable",
                extra={"endpoint": endpoint_name, "status_code": status_code},
            )
            return {}

    def _store_refresh_token(self, refresh_token: str) -> None:
        try:
            _, project_id = google.auth.default()
            if not project_id:
                self.logger.warning(
                    "google auth did not provide project id for refresh token update"
                )
                return
            client = secretmanager.SecretManagerServiceClient()
            parent = f"projects/{project_id}/secrets/fitbit-refresh-token"
            client.add_secret_version(
                request={
                    "parent": parent,
                    "payload": {"data": refresh_token.encode("utf-8")},
                }
            )
        except Exception:
            self.logger.exception("failed to persist refreshed Fitbit token")


def _sum_sleep_stage_minutes(summary: dict[str, Any], key: str) -> int:
    stage = summary.get(key) or {}
    return int(stage.get("minutes", 0))


def _aggregate_sleep_records(records: list[dict[str, Any]]) -> SleepSummary:
    if not records:
        return SleepSummary(
            total_minutes=0,
            efficiency=0.0,
            deep_minutes=0,
            rem_minutes=0,
            awakenings=0,
            start_time=None,
        )

    total_minutes = sum(int(record.get("minutesAsleep", 0)) for record in records)
    weighted_efficiency_base = sum(int(record.get("minutesAsleep", 0)) for record in records)
    weighted_efficiency_sum = sum(
        float(record.get("efficiency", 0.0)) * int(record.get("minutesAsleep", 0))
        for record in records
    )
    deep_minutes = sum(
        _sum_sleep_stage_minutes(record.get("levels", {}).get("summary", {}), "deep")
        for record in records
    )
    rem_minutes = sum(
        _sum_sleep_stage_minutes(record.get("levels", {}).get("summary", {}), "rem")
        for record in records
    )
    awakenings = sum(int(record.get("awakeCount", 0)) for record in records)
    start_time = min(
        (str(record.get("startTime")) for record in records if record.get("startTime")),
        default=None,
    )
    efficiency = (
        weighted_efficiency_sum / weighted_efficiency_base if weighted_efficiency_base else 0.0
    )
    return SleepSummary(
        total_minutes=total_minutes,
        efficiency=efficiency,
        deep_minutes=deep_minutes,
        rem_minutes=rem_minutes,
        awakenings=awakenings,
        start_time=start_time,
    )


def _latest_log(logs: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not logs:
        return None
    return max(logs, key=lambda item: f"{item.get('date', '')}T{item.get('time', '')}")


def _as_optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _build_logged_at(log: dict[str, Any] | None) -> str | None:
    if not log:
        return None
    log_date = log.get("date")
    log_time = log.get("time")
    if log_date and log_time:
        return f"{log_date}T{log_time}"
    if log_date:
        return str(log_date)
    return None


def _build_body_summary(
    weight_logs: list[dict[str, Any]],
    fat_logs: list[dict[str, Any]],
) -> BodySummary:
    weight_log = _latest_log(weight_logs)
    fat_log = _latest_log(fat_logs)
    body_fat = _as_optional_float(weight_log.get("fat")) if weight_log else None
    if body_fat is None and fat_log:
        body_fat = _as_optional_float(fat_log.get("fat"))
    return BodySummary(
        weight_kg=_as_optional_float(weight_log.get("weight")) if weight_log else None,
        bmi=_as_optional_float(weight_log.get("bmi")) if weight_log else None,
        body_fat_percent=body_fat,
        source=str(weight_log.get("source")) if weight_log and weight_log.get("source") else None,
        logged_at=_build_logged_at(weight_log or fat_log),
    )


def build_fitbit_client(settings: Settings) -> FitbitClient:
    if settings.fitbit_client_mode == "api":
        return FitbitApiClient(settings)
    return MockFitbitClient()
