from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.clients.drive_client import GoogleDriveClient
from app.config.settings import Settings


def test_google_drive_client_requires_oauth_settings() -> None:
    settings = Settings(google_drive_mode="api")

    with pytest.raises(ValueError):
        GoogleDriveClient(settings)


def test_google_drive_client_stores_rotated_refresh_token(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        google_drive_mode="api",
        drive_root_folder_id="root-folder",
        drive_oauth_client_id="client-id",
        drive_oauth_client_secret="client-secret",
        drive_oauth_refresh_token="refresh-token",
    )
    stored: list[tuple[str, str]] = []

    class FakeCredentials:
        def __init__(self, **kwargs: str | None) -> None:
            self.refresh_token = kwargs["refresh_token"]

        def refresh(self, _request: object) -> None:
            self.refresh_token = "rotated-refresh-token"

    monkeypatch.setattr("google.oauth2.credentials.Credentials", FakeCredentials)
    monkeypatch.setattr("google.auth.transport.requests.Request", lambda: object())
    monkeypatch.setattr(
        GoogleDriveClient,
        "_build_service",
        lambda self: SimpleNamespace(files=lambda: None),
    )
    monkeypatch.setattr(
        GoogleDriveClient,
        "_store_secret",
        lambda self, name, value: stored.append((name, value)),
    )

    client = GoogleDriveClient(settings)

    assert client.root_folder_id == "root-folder"
    assert settings.drive_oauth_refresh_token == "rotated-refresh-token"
    assert stored == [("drive-oauth-refresh-token", "rotated-refresh-token")]
