from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.schemas.advice_result import AdviceResult
from app.schemas.meal_estimate import MealEstimateResult, MealTextParseResult


class LLMProvider(ABC):
    @abstractmethod
    def generate_advice(self, payload: dict[str, Any]) -> AdviceResult:
        raise NotImplementedError

    @abstractmethod
    def estimate_meal(
        self,
        *,
        prompt: str,
        image_bytes: bytes,
        mime_type: str,
    ) -> MealEstimateResult:
        raise NotImplementedError

    @abstractmethod
    def answer_health_question(
        self,
        *,
        question: str,
        context: dict[str, Any],
    ) -> str:
        raise NotImplementedError

    @abstractmethod
    def parse_meal_text(
        self,
        *,
        text: str,
        target_date: str,
    ) -> MealTextParseResult:
        raise NotImplementedError
