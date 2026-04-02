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
        "Explain rule-based findings and provide structured daily and long-term guidance. "
        "Return strict JSON only."
    )
