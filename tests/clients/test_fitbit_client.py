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
    monkeypatch.setattr(
        client,
        "_build_client",
        lambda: httpx.Client(timeout=settings.request_timeout_seconds, transport=transport),
    )
    result = client.fetch_day(date(2026, 4, 2))

    assert result.sleep.total_minutes == 420
    assert result.resting_hr == 55
    assert result.activity.steps == 1234
