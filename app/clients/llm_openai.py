from __future__ import annotations

import json
from typing import Any

from app.clients.llm_base import LLMProvider
from app.config.settings import Settings
from app.schemas.advice_result import AdviceResult


class OpenAIProvider(LLMProvider):
    def __init__(self, settings: Settings) -> None:
        from openai import OpenAI

        if not settings.openai_api_key:
            raise ValueError("OpenAI provider requires openai_api_key")
        self.client = OpenAI(api_key=settings.openai_api_key, timeout=settings.llm_timeout_seconds)
        self.model_name = settings.llm_model_name

    def generate_advice(self, payload: dict[str, Any]) -> AdviceResult:
        system_prompt = _system_prompt()
        response = self.client.responses.create(
            model=self.model_name,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            text={"format": {"type": "json_object"}},
        )
        content = response.output_text
        data = json.loads(content)
        data["provider"] = "openai"
        data["model_name"] = self.model_name
        return AdviceResult.model_validate(data)


def _system_prompt() -> str:
    return (
        "You are a conservative health coach, not a physician. "
        "Do not diagnose. Do not claim emergencies. "
        "The input facts are already computed by rules and trend analysis, "
        "so do not invent metrics. "
        "Write `summary` as a short factual recap of yesterday's health data "
        "and rule-based status. "
        "Write `long_term_comment` as a medium-term to long-term interpretation "
        "using weekly_trends, "
        "monthly_trends, and repeated patterns in the input. "
        "Make `today_actions` concrete and modest. "
        "Return strict JSON only with exactly these keys: "
        "risk_level, summary, key_findings, today_actions, exercise_advice, sleep_advice, "
        "caffeine_advice, medical_note, long_term_comment."
    )
