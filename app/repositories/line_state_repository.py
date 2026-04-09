from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.db.models import LineConversationState


class LineStateRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, line_user_id: str) -> LineConversationState | None:
        return self.session.get(LineConversationState, line_user_id)

    def upsert(self, line_user_id: str, intent: str, state: dict[str, Any]) -> None:
        entity = self.get(line_user_id)
        if entity is None:
            entity = LineConversationState(line_user_id=line_user_id)
            self.session.add(entity)
        entity.intent = intent
        entity.state_json = state

    def clear(self, line_user_id: str) -> None:
        entity = self.get(line_user_id)
        if entity is not None:
            self.session.delete(entity)
