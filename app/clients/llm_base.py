from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.schemas.advice_result import AdviceResult


class LLMProvider(ABC):
    @abstractmethod
    def generate_advice(self, payload: dict[str, Any]) -> AdviceResult:
        raise NotImplementedError
