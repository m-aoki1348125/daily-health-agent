from __future__ import annotations

from typing import Any

from app.clients.llm_base import LLMProvider
from app.clients.llm_claude import ClaudeProvider
from app.clients.llm_openai import OpenAIProvider
from app.config.settings import Settings
from app.schemas.advice_result import AdviceResult
from app.schemas.meal_estimate import MealEstimateResult


class MockLLMProvider(LLMProvider):
    def __init__(self, model_name: str = "mock-llm") -> None:
        self.model_name = model_name

    def generate_advice(self, payload: dict[str, Any]) -> AdviceResult:
        risk_level = str(payload.get("rule_status", "yellow"))
        reasons = payload.get("rule_reasons", [])
        today_actions = [
            "午前は無理に負荷を上げず、体調の立ち上がりを確認する",
            "カフェインは午後早い時間までにとどめる",
            "就寝時刻をいつもより15分だけ前倒しする",
        ]
        return AdviceResult(
            risk_level=risk_level,
            summary="前日の睡眠と回復傾向を踏まえ、今日は無理を避けながら整える日です。",
            key_findings=[str(reason) for reason in reasons] or ["fallback to rule-based summary"],
            today_actions=today_actions,
            exercise_advice="高強度運動は避け、散歩や軽い有酸素を優先してください。",
            sleep_advice="今夜は画面時間を短くし、就寝を少し早めてください。",
            caffeine_advice="カフェインは14時までを目安にしてください。",
            medical_note="不調が数日続く場合や症状が強い場合は医療機関に相談してください。",
            long_term_comment="平日の睡眠不足が続く兆候があるため、就寝リズムを一定に保つ工夫が有効です。",
            provider="mock",
            model_name=self.model_name,
        )

    def estimate_meal(
        self,
        *,
        prompt: str,
        image_bytes: bytes,
        mime_type: str,
    ) -> MealEstimateResult:
        del prompt, image_bytes, mime_type
        return MealEstimateResult(
            estimated_calories=650,
            confidence="medium",
            summary="主食と主菜、副菜が含まれる定食スタイルの食事と推定しました。",
            meal_items=["ごはん", "肉料理", "サラダ"],
            rationale="画像内に主食とたんぱく質源、野菜が確認できるため中程度の食事量と推定しました。",
            provider="mock",
            model_name=self.model_name,
        )

    def answer_health_question(
        self,
        *,
        question: str,
        context: dict[str, Any],
    ) -> str:
        del context
        return (
            f"昨日までの記録を踏まえると、{question}への答えは、"
            "軽めに無理なく進めるのがよさそうです。"
        )


def build_llm_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "openai":
        return OpenAIProvider(settings)
    if settings.llm_provider == "claude":
        return ClaudeProvider(settings)
    return MockLLMProvider(settings.llm_model_name)
