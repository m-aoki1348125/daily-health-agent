from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.db.base import Base
from app.db.session import create_engine_from_settings, create_session_factory


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=f"sqlite+pysqlite:///{tmp_path / 'test.db'}",
        google_drive_mode="local",
        drive_local_root=str(tmp_path / "drive"),
        fitbit_client_mode="mock",
        line_client_mode="mock",
        llm_provider="mock",
        health_agent_date="2026-04-02",
    )


@pytest.fixture()
def session(settings: Settings) -> Iterator[Session]:
    engine = create_engine_from_settings(settings)
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(settings)
    with session_factory() as db:
        yield db
