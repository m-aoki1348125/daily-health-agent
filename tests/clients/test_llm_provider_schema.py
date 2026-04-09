from __future__ import annotations

from app.clients.llm_factory import MockLLMProvider


def test_mock_llm_provider_matches_schema() -> None:
    provider = MockLLMProvider()
    advice = provider.generate_advice(
        {
            "rule_status": "yellow",
            "rule_reasons": ["sleep deficit detected"],
        }
    )

    assert advice.risk_level == "yellow"
    assert isinstance(advice.today_actions, list)
    assert advice.provider == "mock"


def test_mock_llm_provider_estimates_meal_schema() -> None:
    provider = MockLLMProvider()

    result = provider.estimate_meal(
        prompt="昼食の写真です。",
        image_bytes=b"fake-image",
        mime_type="image/jpeg",
    )

    assert result.estimated_calories > 0
    assert result.provider == "mock"
    assert isinstance(result.meal_items, list)
