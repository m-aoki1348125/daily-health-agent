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
        "あなたは保守的な健康コーチです。医師ではありません。"
        "診断しないでください。緊急性を断定しないでください。"
        "入力にはルール判定済みの事実とトレンドだけが含まれるため、"
        "数値や症状を捏造しないでください。"
        "出力する文章は summary、key_findings、today_actions、exercise_advice、"
        "sleep_advice、caffeine_advice、medical_note、long_term_comment の"
        "すべてを自然な日本語で書いてください。"
        "summary は前日の事実と当日の判定を短く要約してください。"
        "key_findings は『今日の体調』として表示するための短い箇条書きにしてください。"
        "各要素は必ず ☀️、⛅、🌧️ のいずれかで始め、"
        "続けて『睡眠回復』『心拍コンディション』『活動リズム』のような短い項目名と"
        "一言の見立てを書いてください。"
        "key_findings は 2〜4 件にしてください。"
        "数値は必ず入力値をそのまま使い、割合やパーセントへ勝手に変換しないでください。"
        "睡眠は時間と分、心拍は bpm、歩数は歩で表現してください。"
        "today_actions は今日すぐ実行できる控えめで具体的な行動提案にしてください。"
        "long_term_comment は weekly_trends、monthly_trends、過去パターンを踏まえた"
        "中長期の分析コメントにしてください。"
        "厳密な JSON のみを返し、キーは "
        "risk_level, summary, key_findings, today_actions, exercise_advice, sleep_advice, "
        "caffeine_advice, medical_note, long_term_comment のみを含めてください。"
    )
