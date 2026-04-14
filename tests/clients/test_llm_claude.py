from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

from app.clients.llm_claude import ClaudeProvider, _advice_json_schema


def test_advice_json_schema_requires_expected_fields() -> None:
    schema = _advice_json_schema()

    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert "risk_level" in schema["required"]
    assert "summary" in schema["required"]
    assert "key_findings" in schema["properties"]
    assert "today_actions" in schema["properties"]


def test_claude_provider_uses_structured_output_for_advice() -> None:
    captured: dict[str, object] = {}
    provider = ClaudeProvider.__new__(ClaudeProvider)
    provider.model_name = "claude-haiku-4-5"
    response_text = (
        '{"risk_level":"green","summary":"ok","key_findings":'
        '["☀️ 睡眠回復: 良好です","☀️ 活動リズム: 安定しています"],'
        '"today_actions":["朝に日光を浴びる","昼食を整える"],'
        '"exercise_advice":"軽い散歩を続けてください。",'
        '"sleep_advice":"就寝時刻をそろえてください。",'
        '"caffeine_advice":"午後の摂りすぎを避けてください。",'
        '"medical_note":"症状が続く場合は受診を検討してください。",'
        '"long_term_comment":"安定した習慣を維持してください。"}'
    )

    class FakeMessages:
        def create(self, **kwargs: object) -> object:
            captured.update(kwargs)
            return SimpleNamespace(content=[SimpleNamespace(text=response_text)])

    provider.client = cast(Any, SimpleNamespace(messages=FakeMessages()))

    result = provider._create_advice_content("claude-haiku-4-5", {"date": "2026-04-14"})

    assert '"summary":"ok"' in result
    output_config = captured["output_config"]
    assert isinstance(output_config, dict)
    format_config = output_config["format"]
    assert isinstance(format_config, dict)
    assert format_config["type"] == "json_schema"
    assert format_config["schema"] == _advice_json_schema()
