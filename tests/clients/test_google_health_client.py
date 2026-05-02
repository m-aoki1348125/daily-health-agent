from __future__ import annotations

from datetime import date

import httpx
import pytest

from app.clients.google_health_client import GoogleHealthClient
from app.config.settings import Settings


def test_google_health_client_fetches_body_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        google_health_client_id="client-id",
        google_health_client_secret="client-secret",
        google_health_refresh_token="refresh-token",
        google_health_expected_user_id="health-user-1",
        google_health_allowed_source_platforms="FITBIT_WEB_API",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/token":
            return httpx.Response(
                200,
                json={"access_token": "google-access-token", "expires_in": 3600},
            )
        assert request.headers["Authorization"] == "Bearer google-access-token"
        if request.url.path == "/v4/users/me/identity":
            return httpx.Response(200, json={"healthUserId": "health-user-1"})
        if request.url.path == "/v4/users/me/dataTypes/weight/dataPoints":
            return httpx.Response(
                200,
                json={
                    "dataPoints": [
                        {
                            "dataSource": {"platform": "HEALTH_CONNECT"},
                            "weight": {
                                "sampleTime": {"physicalTime": "2026-05-02T00:10:00Z"},
                                "weightGrams": 51000,
                            },
                        },
                        {
                            "dataSource": {"platform": "FITBIT_WEB_API"},
                            "weight": {
                                "sampleTime": {"physicalTime": "2026-05-02T00:15:00Z"},
                                "weightGrams": 64200,
                            },
                        },
                    ]
                },
            )
        if request.url.path == "/v4/users/me/dataTypes/body-fat/dataPoints":
            return httpx.Response(
                200,
                json={
                    "dataPoints": [
                        {
                            "dataSource": {"platform": "FITBIT_WEB_API"},
                            "bodyFat": {
                                "sampleTime": {"physicalTime": "2026-05-02T00:15:00Z"},
                                "percentage": 18.4,
                            },
                        }
                    ]
                },
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    transport = httpx.MockTransport(handler)
    client = GoogleHealthClient(settings)
    monkeypatch.setattr(
        client,
        "_build_client",
        lambda: httpx.Client(timeout=settings.request_timeout_seconds, transport=transport),
    )

    result = client.fetch_body(date(2026, 5, 2))

    assert result.body.weight_kg == 64.2
    assert result.body.body_fat_percent == 18.4
    assert result.body.source == "google_health"
    assert result.raw_payload["identity"]["healthUserId"] == "health-user-1"
    assert result.raw_payload["allowed_source_platforms"] == ["FITBIT_WEB_API"]
    assert result.raw_payload["weight"]["dataPoints"]


def test_google_health_client_requires_oauth_settings() -> None:
    client = GoogleHealthClient(Settings())

    with pytest.raises(ValueError):
        client.fetch_body(date(2026, 5, 2))


def test_google_health_client_rejects_unexpected_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        google_health_client_id="client-id",
        google_health_client_secret="client-secret",
        google_health_refresh_token="refresh-token",
        google_health_expected_user_id="momotaka-health-user",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/token":
            return httpx.Response(
                200,
                json={"access_token": "google-access-token", "expires_in": 3600},
            )
        if request.url.path == "/v4/users/me/identity":
            return httpx.Response(200, json={"healthUserId": "someone-else"})
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    transport = httpx.MockTransport(handler)
    client = GoogleHealthClient(settings)
    monkeypatch.setattr(
        client,
        "_build_client",
        lambda: httpx.Client(timeout=settings.request_timeout_seconds, transport=transport),
    )

    with pytest.raises(ValueError, match="identity mismatch"):
        client.fetch_body(date(2026, 5, 2))
