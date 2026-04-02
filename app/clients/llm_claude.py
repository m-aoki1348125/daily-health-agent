from __future__ import annotations

import json
import logging
from typing import Any, cast

import httpx

from app.clients.llm_base import LLMProvider
from app.config.settings import Settings
from app.schemas.advice_result import AdviceResult


class ClaudeProvider(LLMProvider):
    def __init__(self, settings: Settings) -> None:
        from anthropic import Anthropic

        if not settings.claude_api_key:
            raise ValueError("Claude provider requires claude_api_key")
        self.api_key = settings.claude_api_key
        self.timeout = settings.llm_timeout_seconds
        self.client = Anthropic(
            api_key=self.api_key,
            timeout=self.timeout,
        )
        self.logger = logging.getLogger(__name__)
        self.model_name = settings.llm_model_name

    def generate_advice(self, payload: dict[str, Any]) -> AdviceResult:
        model_name = self._resolve_model_name()
        message = self.client.messages.create(
            model=model_name,
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
        data = _normalize_advice_payload(_parse_json_object(content), payload)
        data["provider"] = "claude"
        data["model_name"] = model_name
        return AdviceResult.model_validate(data)

    def _resolve_model_name(self) -> str:
        preferred = self.model_name
        if self._model_exists(preferred):
            return preferred

        fallback_candidates = [
            "claude-sonnet-4-20250514",
            "claude-3-7-sonnet-20250219",
            "claude-3-5-haiku-20241022",
            "claude-3-haiku-20240307",
        ]
        available_models = self._list_available_models()
        for candidate in fallback_candidates:
            if candidate in available_models:
                self.logger.warning(
                    "configured Claude model unavailable; falling back",
                    extra={"configured_model": preferred, "fallback_model": candidate},
                )
                return candidate
        if available_models:
            fallback_model = available_models[0]
            self.logger.warning(
                "configured Claude model unavailable; using first available model",
                extra={"configured_model": preferred, "fallback_model": fallback_model},
            )
            return fallback_model
        return preferred

    def _model_exists(self, model_name: str) -> bool:
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(
                    f"https://api.anthropic.com/v1/models/{model_name}",
                    headers=self._headers(),
                )
            return response.status_code == 200
        except Exception:
            self.logger.exception("failed to probe Claude model availability")
            return False

    def _list_available_models(self) -> list[str]:
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(
                    "https://api.anthropic.com/v1/models",
                    headers=self._headers(),
                )
                response.raise_for_status()
            payload = response.json()
            return [
                str(item["id"])
                for item in payload.get("data", [])
                if isinstance(item, dict) and item.get("id")
            ]
        except Exception:
            self.logger.exception("failed to list Claude models")
            return []

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }


def _system_prompt() -> str:
    return (
        "You are a conservative health coach, not a physician. "
        "Do not diagnose. Do not claim emergencies. "
        "Explain rule-based findings and provide structured daily and long-term guidance. "
        "Return strict JSON only."
    )


def _parse_json_object(content: str) -> dict[str, Any]:
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    start = content.find("{")
    end = content.rfind("}")
    if start != -1 and end != -1 and start < end:
        candidate = content[start : end + 1]
        parsed = json.loads(candidate)
        if isinstance(parsed, dict):
            return parsed
    raise json.JSONDecodeError("Claude response did not contain a JSON object", content, 0)


def _normalize_advice_payload(data: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    required_fields = {
        "risk_level",
        "summary",
        "key_findings",
        "today_actions",
        "exercise_advice",
        "sleep_advice",
        "caffeine_advice",
        "medical_note",
        "long_term_comment",
    }
    if required_fields.issubset(data.keys()):
        return data

    rule_reasons = [str(item) for item in payload.get("rule_reasons", [])]
    key_findings = _coerce_string_list(data.get("key_findings"))
    priority_actions = _coerce_string_list(data.get("priority_actions"))
    today_actions = priority_actions or _coerce_string_list(data.get("today_actions"))
    summary = _first_non_empty(
        data.get("summary"),
        data.get("advice"),
        data.get("overall_assessment"),
    )
    long_term_comment = _first_non_empty(
        data.get("long_term_comment"),
        data.get("wellness_tip"),
        data.get("sleep_pattern_note"),
    )
    normalized = {
        "risk_level": _first_non_empty(
            data.get("risk_level"),
            payload.get("rule_status"),
            "yellow",
        ),
        "summary": summary or "前日の健康データに基づくアドバイスです。",
        "key_findings": key_findings or rule_reasons or ["health trend summary"],
        "today_actions": today_actions or ["生活リズムを整えながら様子を見てください。"],
        "exercise_advice": _first_non_empty(
            data.get("exercise_advice"),
            data.get("activity_goal"),
            "運動は無理のない範囲で継続してください。",
        ),
        "sleep_advice": _first_non_empty(
            data.get("sleep_advice"),
            data.get("sleep_recommendation"),
            "睡眠時間の確保を優先してください。",
        ),
        "caffeine_advice": _first_non_empty(
            data.get("caffeine_advice"),
            "カフェインは午後早い時間までに抑えてください。",
        ),
        "medical_note": _first_non_empty(
            data.get("medical_note"),
            "症状が続く場合は医療機関への相談を検討してください。",
        ),
        "long_term_comment": long_term_comment
        or "長期的には睡眠と活動のリズムを一定に保つことが重要です。",
    }
    return normalized


def _coerce_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return []


def _first_non_empty(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None
