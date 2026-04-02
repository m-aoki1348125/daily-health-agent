from __future__ import annotations

from datetime import date

import httpx
import pytest

from app.clients.fitbit_client import FitbitApiClient, MockFitbitClient
from app.config.settings import Settings


def test_mock_fitbit_client_returns_expected_shape() -> None:
    client = MockFitbitClient()
    result = client.fetch_day(date(2026, 4, 2))

    assert result.sleep.total_minutes > 0
    assert result.activity.steps > 0
    assert "sleep" in result.raw_payload


def test_fitbit_api_client_refreshes_access_token(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        fitbit_client_mode="api",
        fitbit_client_id="client-id",
        fitbit_client_secret="client-secret",
        fitbit_refresh_token="refresh-token",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth2/token":
            return httpx.Response(200, json={"access_token": "fresh-access-token"})
        if request.url.path == "/1.2/user/-/sleep/date/2026-04-02.json":
            assert request.headers["Authorization"] == "Bearer fresh-access-token"
            return httpx.Response(
                200,
                json={
                    "sleep": [
                        {
                            "minutesAsleep": 420,
                            "efficiency": 90,
                            "awakeCount": 1,
                            "startTime": "2026-04-02T00:10:00+09:00",
                            "levels": {
                                "summary": {
                                    "deep": {"minutes": 80},
                                    "rem": {"minutes": 90},
                                }
                            },
                        }
                    ]
                },
            )
        if request.url.path == "/1/user/-/activities/heart/date/2026-04-02/1d.json":
            return httpx.Response(
                200,
                json={"activities-heart": [{"value": {"restingHeartRate": 55}}]},
            )
        if request.url.path == "/1/user/-/activities/date/2026-04-02.json":
            return httpx.Response(200, json={"summary": {"steps": 1234, "caloriesOut": 2222}})
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    transport = httpx.MockTransport(handler)
    client = FitbitApiClient(settings)
    stored_refresh_tokens: list[str] = []

    monkeypatch.setattr(client, "_store_refresh_token", stored_refresh_tokens.append)
    monkeypatch.setattr(
        client,
        "_build_client",
        lambda: httpx.Client(timeout=settings.request_timeout_seconds, transport=transport),
    )
    result = client.fetch_day(date(2026, 4, 2))

    assert result.sleep.total_minutes == 420
    assert result.resting_hr == 55
    assert result.activity.steps == 1234
    assert stored_refresh_tokens == []


def test_fitbit_api_client_stores_rotated_refresh_token(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        fitbit_client_mode="api",
        fitbit_client_id="client-id",
        fitbit_client_secret="client-secret",
        fitbit_refresh_token="refresh-token",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth2/token":
            return httpx.Response(
                200,
                json={
                    "access_token": "fresh-access-token",
                    "refresh_token": "rotated-refresh-token",
                },
            )
        if request.url.path == "/1.2/user/-/sleep/date/2026-04-02.json":
            return httpx.Response(
                200,
                json={"sleep": [{"minutesAsleep": 420, "levels": {"summary": {}}}]},
            )
        if request.url.path == "/1/user/-/activities/heart/date/2026-04-02/1d.json":
            return httpx.Response(200, json={"activities-heart": []})
        if request.url.path == "/1/user/-/activities/date/2026-04-02.json":
            return httpx.Response(200, json={"summary": {"steps": 1, "caloriesOut": 2}})
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    transport = httpx.MockTransport(handler)
    client = FitbitApiClient(settings)
    stored_refresh_tokens: list[str] = []

    monkeypatch.setattr(client, "_store_refresh_token", stored_refresh_tokens.append)
    monkeypatch.setattr(
        client,
        "_build_client",
        lambda: httpx.Client(timeout=settings.request_timeout_seconds, transport=transport),
    )

    client.fetch_day(date(2026, 4, 2))

    assert settings.fitbit_refresh_token == "rotated-refresh-token"
    assert stored_refresh_tokens == ["rotated-refresh-token"]


def test_fitbit_api_client_reuses_access_token_between_days(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        fitbit_client_mode="api",
        fitbit_client_id="client-id",
        fitbit_client_secret="client-secret",
        fitbit_refresh_token="refresh-token",
    )
    token_requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal token_requests
        if request.url.path == "/oauth2/token":
            token_requests += 1
            return httpx.Response(
                200,
                json={"access_token": "fresh-access-token", "expires_in": 28800},
            )
        if request.url.path in {
            "/1.2/user/-/sleep/date/2026-04-02.json",
            "/1.2/user/-/sleep/date/2026-04-01.json",
        }:
            return httpx.Response(
                200,
                json={"sleep": [{"minutesAsleep": 420, "levels": {"summary": {}}}]},
            )
        if request.url.path in {
            "/1/user/-/activities/heart/date/2026-04-02/1d.json",
            "/1/user/-/activities/heart/date/2026-04-01/1d.json",
        }:
            return httpx.Response(200, json={"activities-heart": []})
        if request.url.path in {
            "/1/user/-/activities/date/2026-04-02.json",
            "/1/user/-/activities/date/2026-04-01.json",
        }:
            return httpx.Response(200, json={"summary": {"steps": 1, "caloriesOut": 2}})
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    transport = httpx.MockTransport(handler)
    client = FitbitApiClient(settings)
    monkeypatch.setattr(
        client,
        "_build_client",
        lambda: httpx.Client(timeout=settings.request_timeout_seconds, transport=transport),
    )

    client.fetch_day(date(2026, 4, 2))
    client.fetch_day(date(2026, 4, 1))

    assert token_requests == 1


def test_fitbit_api_client_retries_after_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        fitbit_client_mode="api",
        fitbit_client_id="client-id",
        fitbit_client_secret="client-secret",
        fitbit_refresh_token="refresh-token",
    )
    sleep_attempts = 0
    slept: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal sleep_attempts
        if request.url.path == "/oauth2/token":
            return httpx.Response(
                200,
                json={"access_token": "fresh-access-token", "expires_in": 28800},
            )
        if request.url.path == "/1.2/user/-/sleep/date/2026-04-02.json":
            sleep_attempts += 1
            if sleep_attempts == 1:
                return httpx.Response(429, headers={"Retry-After": "1"})
            return httpx.Response(
                200,
                json={"sleep": [{"minutesAsleep": 420, "levels": {"summary": {}}}]},
            )
        if request.url.path == "/1/user/-/activities/heart/date/2026-04-02/1d.json":
            return httpx.Response(200, json={"activities-heart": []})
        if request.url.path == "/1/user/-/activities/date/2026-04-02.json":
            return httpx.Response(200, json={"summary": {"steps": 1, "caloriesOut": 2}})
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    transport = httpx.MockTransport(handler)
    client = FitbitApiClient(settings)
    monkeypatch.setattr(
        client,
        "_build_client",
        lambda: httpx.Client(timeout=settings.request_timeout_seconds, transport=transport),
    )
    monkeypatch.setattr("app.clients.fitbit_client.time.sleep", slept.append)

    result = client.fetch_day(date(2026, 4, 2))

    assert result.sleep.total_minutes == 420


def test_fitbit_api_client_aggregates_multiple_sleep_logs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        fitbit_client_mode="api",
        fitbit_client_id="client-id",
        fitbit_client_secret="client-secret",
        fitbit_refresh_token="refresh-token",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth2/token":
            return httpx.Response(
                200,
                json={"access_token": "fresh-access-token", "expires_in": 28800},
            )
        if request.url.path == "/1.2/user/-/sleep/date/2026-04-02.json":
            return httpx.Response(
                200,
                json={
                    "sleep": [
                        {
                            "minutesAsleep": 360,
                            "efficiency": 90,
                            "awakeCount": 1,
                            "startTime": "2026-04-01T23:50:00+09:00",
                            "levels": {
                                "summary": {
                                    "deep": {"minutes": 70},
                                    "rem": {"minutes": 80},
                                }
                            },
                        },
                        {
                            "minutesAsleep": 45,
                            "efficiency": 80,
                            "awakeCount": 0,
                            "startTime": "2026-04-02T06:30:00+09:00",
                            "levels": {
                                "summary": {
                                    "deep": {"minutes": 5},
                                    "rem": {"minutes": 10},
                                }
                            },
                        },
                    ]
                },
            )
        if request.url.path == "/1/user/-/activities/heart/date/2026-04-02/1d.json":
            return httpx.Response(
                200,
                json={"activities-heart": [{"value": {"restingHeartRate": 55}}]},
            )
        if request.url.path == "/1/user/-/activities/date/2026-04-02.json":
            return httpx.Response(200, json={"summary": {"steps": 1234, "caloriesOut": 2222}})
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    transport = httpx.MockTransport(handler)
    client = FitbitApiClient(settings)
    monkeypatch.setattr(
        client,
        "_build_client",
        lambda: httpx.Client(timeout=settings.request_timeout_seconds, transport=transport),
    )

    result = client.fetch_day(date(2026, 4, 2))

    assert result.sleep.total_minutes == 405
    assert round(result.sleep.efficiency, 1) == 88.9
    assert result.sleep.deep_minutes == 75
    assert result.sleep.rem_minutes == 90
    assert result.sleep.awakenings == 1
    assert result.sleep.start_time == "2026-04-01T23:50:00+09:00"
