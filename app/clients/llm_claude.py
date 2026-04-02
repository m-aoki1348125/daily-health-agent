from __future__ import annotations

import json
from typing import Any, cast

from app.clients.llm_base import LLMProvider
from app.config.settings import Settings
from app.schemas.advice_result import AdviceResult


class ClaudeProvider(LLMProvider):
    def __init__(self, settings: Settings) -> None:
        from anthropic import Anthropic

        if not settings.claude_api_key:
            raise ValueError("Claude provider requires claude_api_key")
        self.client = Anthropic(
            api_key=settings.claude_api_key,
            timeout=settings.llm_timeout_seconds,
        )
        self.model_name = settings.llm_model_name

    def generate_advice(self, payload: dict[str, Any]) -> AdviceResult:
        message = self.client.messages.create(
            model=self.model_name,
            max_tokens=1000,
            system=_system_prompt(),
            messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        )
        text_blocks = [
            cast(str, block.text)
            for block in message.content
            if hasattr(block, "text") and block.text is not None
        ]
        content = "".join(text_blocks)
        data = json.loads(content)
        data["provider"] = "claude"
        data["model_name"] = self.model_name
        return AdviceResult.model_validate(data)


def _system_prompt() -> str:
    return (
        "You are a conservative health coach, not a physician. "
        "Do not diagnose. Do not claim emergencies. "
        "Explain rule-based findings and provide structured daily and long-term guidance. "
        "Return strict JSON only."
    )
