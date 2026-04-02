from __future__ import annotations

from datetime import date

from app.clients.fitbit_client import MockFitbitClient


def test_mock_fitbit_client_returns_expected_shape() -> None:
    client = MockFitbitClient()
    result = client.fetch_day(date(2026, 4, 2))

    assert result.sleep.total_minutes > 0
    assert result.activity.steps > 0
    assert "sleep" in result.raw_payload
