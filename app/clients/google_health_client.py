from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date
from typing import Any, cast

import httpx

from app.config.settings import Settings
from app.schemas.health_features import BodySummary


@dataclass(frozen=True)
class GoogleHealthBodyRaw:
    date: date
    body: BodySummary
    raw_payload: dict[str, Any]


class GoogleHealthClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._access_token: str | None = None
        self._access_token_expires_at: float = 0.0
        self._identity_verified = False

    def _build_client(self) -> httpx.Client:
        return httpx.Client(timeout=self.settings.request_timeout_seconds)

    def fetch_body(self, target_date: date) -> GoogleHealthBodyRaw:
        token = self._get_access_token()
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        with self._build_client() as client:
            identity_payload = self._verify_identity(client, headers=headers)
            weight_payload = self._list_points(client, "weight", target_date, headers=headers)
            body_fat_payload = self._list_points(
                client, "body-fat", target_date, headers=headers
            )

        allowed_platforms = _parse_allowed_platforms(
            self.settings.google_health_allowed_source_platforms
        )
        weight_kg = _extract_weight_kg(
            weight_payload,
            allowed_platforms=allowed_platforms,
            target_date=target_date,
        )
        body_fat_percent = _extract_body_fat_percent(
            body_fat_payload,
            allowed_platforms=allowed_platforms,
            target_date=target_date,
        )
        has_body_metrics = weight_kg is not None or body_fat_percent is not None
        body = BodySummary(
            weight_kg=weight_kg,
            bmi=None,
            body_fat_percent=body_fat_percent,
            source="google_health" if has_body_metrics else None,
            logged_at=target_date.isoformat() if has_body_metrics else None,
        )
        return GoogleHealthBodyRaw(
            date=target_date,
            body=body,
            raw_payload={
                "identity": identity_payload,
                "allowed_source_platforms": sorted(allowed_platforms)
                if allowed_platforms
                else None,
                "weight": weight_payload,
                "body_fat": body_fat_payload,
            },
        )

    def _verify_identity(
        self,
        client: httpx.Client,
        *,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        response = client.get(
            f"{self.settings.google_health_base_url}/v4/users/me/identity",
            headers=headers,
        )
        response.raise_for_status()
        payload = cast(dict[str, Any], response.json())
        expected_user_id = self.settings.google_health_expected_user_id
        if expected_user_id and not self._identity_verified:
            actual_user_id = payload.get("healthUserId")
            if str(actual_user_id) != expected_user_id:
                raise ValueError(
                    "Google Health identity mismatch: expected configured "
                    "health user id"
                )
            self._identity_verified = True
        return payload

    def _list_points(
        self,
        client: httpx.Client,
        data_type: str,
        target_date: date,
        *,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        data_points: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            params = {"pageSize": "100"}
            if page_token:
                params["pageToken"] = page_token
            response = client.get(
                f"{self.settings.google_health_base_url}/v4/users/me/dataTypes/"
                f"{data_type}/dataPoints",
                headers=headers,
                params=params,
            )
            response.raise_for_status()
            payload = cast(dict[str, Any], response.json())
            points = payload.get("dataPoints")
            if isinstance(points, list):
                data_points.extend(point for point in points if isinstance(point, dict))
            if any(_point_matches_date(point, target_date) for point in data_points):
                break
            page_token = payload.get("nextPageToken")
            if not page_token:
                break
        return {"dataPoints": data_points}

    def _get_access_token(self) -> str:
        if self._access_token and time.monotonic() < self._access_token_expires_at:
            return self._access_token
        return self._refresh_access_token()

    def _refresh_access_token(self) -> str:
        client_id = self.settings.google_health_client_id
        client_secret = self.settings.google_health_client_secret
        refresh_token = self.settings.google_health_refresh_token
        if not client_id or not client_secret or not refresh_token:
            raise ValueError(
                "Google Health API requires client id, client secret, and refresh token"
            )
        with self._build_client() as client:
            response = client.post(
                self.settings.google_health_token_url,
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
        payload = response.json()
        access_token = payload.get("access_token")
        if not access_token:
            raise ValueError("Google Health token response did not include access_token")
        expires_in = int(payload.get("expires_in", 3600))
        self._access_token = str(access_token)
        self._access_token_expires_at = time.monotonic() + max(0, expires_in - 60)
        return self._access_token


def _parse_allowed_platforms(raw_value: str | None) -> set[str]:
    if not raw_value:
        return set()
    return {
        value.strip().upper()
        for value in raw_value.split(",")
        if value.strip()
    }


def _point_platform(point: dict[str, Any]) -> str | None:
    data_source = point.get("dataSource")
    if not isinstance(data_source, dict):
        return None
    platform = data_source.get("platform")
    return str(platform).upper() if platform else None


def _point_matches_date(point: dict[str, Any], target_date: date) -> bool:
    for value_key in ("weight", "bodyFat"):
        sample_time = (point.get(value_key) or {}).get("sampleTime")
        if not isinstance(sample_time, dict):
            continue
        civil_date = (sample_time.get("civilTime") or {}).get("date")
        if isinstance(civil_date, dict) and (
            civil_date.get("year") == target_date.year
            and civil_date.get("month") == target_date.month
            and civil_date.get("day") == target_date.day
        ):
            return True
        physical_time = sample_time.get("physicalTime")
        if physical_time and str(physical_time).startswith(target_date.isoformat()):
            return True
    return False


def _allowed_points(
    payload: dict[str, Any], *, allowed_platforms: set[str], target_date: date
) -> list[dict[str, Any]]:
    points = payload.get("dataPoints")
    if not isinstance(points, list) or not points:
        return []
    dict_points = [point for point in points if isinstance(point, dict)]
    dict_points = [
        point for point in dict_points if _point_matches_date(point, target_date)
    ]
    if not allowed_platforms:
        return dict_points
    return [
        point
        for point in dict_points
        if (_point_platform(point) or "") in allowed_platforms
    ]


def _latest_point(points: list[dict[str, Any]], value_key: str) -> dict[str, Any] | None:
    value_points = [point for point in points if point.get(value_key)]
    if not value_points:
        return None
    return max(value_points, key=_point_sample_time)


def _point_sample_time(point: dict[str, Any]) -> str:
    for value_key in ("weight", "bodyFat"):
        sample_time = (point.get(value_key) or {}).get("sampleTime")
        if isinstance(sample_time, dict):
            physical_time = sample_time.get("physicalTime")
            if physical_time:
                return str(physical_time)
    return ""


def _extract_weight_kg(
    payload: dict[str, Any], *, allowed_platforms: set[str], target_date: date
) -> float | None:
    point = _latest_point(
        _allowed_points(
            payload,
            allowed_platforms=allowed_platforms,
            target_date=target_date,
        ),
        "weight",
    )
    if not point:
        return None
    value = (point.get("weight") or {}).get("weightGrams")
    if value is None:
        return None
    return float(value) / 1000


def _extract_body_fat_percent(
    payload: dict[str, Any], *, allowed_platforms: set[str], target_date: date
) -> float | None:
    point = _latest_point(
        _allowed_points(
            payload,
            allowed_platforms=allowed_platforms,
            target_date=target_date,
        ),
        "bodyFat",
    )
    if not point:
        return None
    value = (point.get("bodyFat") or {}).get("percentage")
    if value is None:
        return None
    return float(value)


def build_google_health_client(settings: Settings) -> GoogleHealthClient:
    return GoogleHealthClient(settings)
