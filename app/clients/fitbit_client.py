from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from typing import Any

import httpx

from app.config.settings import Settings
from app.schemas.health_features import ActivitySummary, FitbitDayRaw, SleepSummary


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
        }
        return FitbitDayRaw(
            date=target_date,
            sleep=SleepSummary(**raw_payload["sleep"]),
            resting_hr=raw_payload["resting_hr"],
            activity=ActivitySummary(**raw_payload["activity"]),
            raw_payload=raw_payload,
        )


class FitbitApiClient(FitbitClient):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

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
        token = self._refresh_access_token()
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
        with self._build_client() as client:
            sleep_resp = client.get(sleep_url, headers=headers)
            sleep_resp.raise_for_status()
            hr_resp = client.get(hr_url, headers=headers)
            hr_resp.raise_for_status()
            activity_resp = client.get(activity_url, headers=headers)
            activity_resp.raise_for_status()
        sleep_json = sleep_resp.json()
        hr_json = hr_resp.json()
        activity_json = activity_resp.json()
        sleep_record = (sleep_json.get("sleep") or [{}])[0]
        summary = activity_json.get("summary", {})
        resting_hr = None
        value_list = hr_json.get("activities-heart", [])
        if value_list:
            resting_hr = value_list[0].get("value", {}).get("restingHeartRate")
        raw_payload = {
            "sleep": sleep_json,
            "heart": hr_json,
            "activity": activity_json,
        }
        return FitbitDayRaw(
            date=target_date,
            sleep=SleepSummary(
                total_minutes=int(sleep_record.get("minutesAsleep", 0)),
                efficiency=float(sleep_record.get("efficiency", 0.0)),
                deep_minutes=int(
                    _sum_sleep_stage_minutes(
                        sleep_record.get("levels", {}).get("summary", {}),
                        "deep",
                    )
                ),
                rem_minutes=int(
                    _sum_sleep_stage_minutes(
                        sleep_record.get("levels", {}).get("summary", {}),
                        "rem",
                    )
                ),
                awakenings=int(sleep_record.get("awakeCount", 0)),
                start_time=sleep_record.get("startTime"),
            ),
            resting_hr=resting_hr,
            activity=ActivitySummary(
                steps=int(summary.get("steps", 0)),
                calories=int(summary.get("caloriesOut", 0)),
            ),
            raw_payload=raw_payload,
        )

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
        return str(access_token)


def _sum_sleep_stage_minutes(summary: dict[str, Any], key: str) -> int:
    stage = summary.get(key) or {}
    return int(stage.get("minutes", 0))


def build_fitbit_client(settings: Settings) -> FitbitClient:
    if settings.fitbit_client_mode == "api":
        return FitbitApiClient(settings)
    return MockFitbitClient()
