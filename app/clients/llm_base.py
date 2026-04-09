from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.schemas.advice_result import AdviceResult
from app.schemas.meal_estimate import MealEstimateResult


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
