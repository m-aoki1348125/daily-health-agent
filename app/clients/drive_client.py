from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from datetime import date
from pathlib import Path

from app.config.settings import Settings


class DriveClient(ABC):
    @abstractmethod
    def store_json(
        self,
        *,
        category: str,
        target_date: date,
        filename: str,
        payload: dict,
    ) -> str:
        raise NotImplementedError

    @abstractmethod
    def store_markdown(
        self,
        *,
        category: str,
        target_date: date,
        filename: str,
        content: str,
    ) -> str:
        raise NotImplementedError


class LocalDriveClient(DriveClient):
    def __init__(self, root: str) -> None:
        self.root = Path(root)

    def store_json(
        self,
        *,
        category: str,
        target_date: date,
        filename: str,
        payload: dict,
    ) -> str:
        path = self._path(category, target_date, filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return self._stable_file_id(path)

    def store_markdown(
        self,
        *,
        category: str,
        target_date: date,
        filename: str,
        content: str,
    ) -> str:
        path = self._path(category, target_date, filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return self._stable_file_id(path)

    def _path(self, category: str, target_date: date, filename: str) -> Path:
        year = target_date.strftime("%Y")
        year_month = target_date.strftime("%Y-%m")
        if category == "raw":
            return self.root / "HealthAgent" / "raw" / year / year_month / filename
        if category == "daily_reports":
            return self.root / "HealthAgent" / "daily_reports" / year / year_month / filename
        if category == "weekly_reports":
            return self.root / "HealthAgent" / "weekly_reports" / year / filename
        if category == "monthly_reports":
            return self.root / "HealthAgent" / "monthly_reports" / year / filename
        if category == "profile":
            return self.root / "HealthAgent" / "profile" / filename
        raise ValueError(f"unsupported category: {category}")

    @staticmethod
    def _stable_file_id(path: Path) -> str:
        return hashlib.sha1(str(path).encode("utf-8")).hexdigest()


class GoogleDriveClient(DriveClient):
    def __init__(self, settings: Settings) -> None:
        from googleapiclient.discovery import build  # type: ignore[import-untyped]

        self.root_folder_id = settings.drive_root_folder_id
        self.service = build("drive", "v3", cache_discovery=False)

    def store_json(
        self,
        *,
        category: str,
        target_date: date,
        filename: str,
        payload: dict,
    ) -> str:
        parent_id = self._ensure_folder_path(category, target_date)
        return self._upsert_file(
            parent_id=parent_id,
            filename=filename,
            content=json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
            mime_type="application/json",
        )

    def store_markdown(
        self,
        *,
        category: str,
        target_date: date,
        filename: str,
        content: str,
    ) -> str:
        parent_id = self._ensure_folder_path(category, target_date)
        return self._upsert_file(
            parent_id=parent_id,
            filename=filename,
            content=content.encode("utf-8"),
            mime_type="text/markdown",
        )

    def _ensure_folder_path(self, category: str, target_date: date) -> str:
        parts = ["HealthAgent", category]
        if category in {"raw", "daily_reports"}:
            parts.extend([target_date.strftime("%Y"), target_date.strftime("%Y-%m")])
        elif category in {"weekly_reports", "monthly_reports"}:
            parts.append(target_date.strftime("%Y"))
        parent_id = self.root_folder_id
        for part in parts:
            parent_id = self._ensure_folder(parent_id, part)
        return parent_id

    def _ensure_folder(self, parent_id: str, name: str) -> str:
        query = (
            f"name = '{name}' and '{parent_id}' in parents and "
            "mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        )
        response = self.service.files().list(q=query, fields="files(id, name)").execute()
        files = response.get("files", [])
        if files:
            return str(files[0]["id"])
        file_metadata = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
        }
        created = self.service.files().create(body=file_metadata, fields="id").execute()
        return str(created["id"])

    def _upsert_file(self, *, parent_id: str, filename: str, content: bytes, mime_type: str) -> str:
        from googleapiclient.http import MediaInMemoryUpload  # type: ignore[import-untyped]

        query = f"name = '{filename}' and '{parent_id}' in parents and trashed = false"
        response = self.service.files().list(q=query, fields="files(id)").execute()
        media = MediaInMemoryUpload(content, mimetype=mime_type, resumable=False)
        files = response.get("files", [])
        if files:
            file_id = str(files[0]["id"])
            self.service.files().update(fileId=file_id, media_body=media).execute()
            return file_id
        created = (
            self.service.files()
            .create(body={"name": filename, "parents": [parent_id]}, media_body=media, fields="id")
            .execute()
        )
        return str(created["id"])


def build_drive_client(settings: Settings) -> DriveClient:
    if settings.google_drive_mode == "api":
        return GoogleDriveClient(settings)
    return LocalDriveClient(settings.drive_local_root)
