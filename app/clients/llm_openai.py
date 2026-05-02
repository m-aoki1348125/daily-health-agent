from __future__ import annotations

import json
from base64 import b64encode
from typing import Any, cast

from app.clients.llm_base import LLMProvider
from app.config.settings import Settings
from app.schemas.advice_result import AdviceResult
from app.schemas.meal_estimate import MealEstimateResult, MealTextParseResult
from app.services.meal_image_service import prepare_meal_image_variants


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
        content = response.output_text.strip()
        if content.startswith("```"):
            lines = content.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            content = "\n".join(lines).strip()
            if content.startswith("json"):
                content = content[4:].strip()
        data = json.loads(content)
        data["provider"] = "openai"
        data["model_name"] = self.model_name
        return AdviceResult.model_validate(data)

    def estimate_meal(
        self,
        *,
        prompt: str,
        image_bytes: bytes,
        mime_type: str,
    ) -> MealEstimateResult:
        variants = prepare_meal_image_variants(image_bytes, mime_type)
        user_content: list[dict[str, str]] = []
        for variant in variants:
            image_base64 = b64encode(variant.image_bytes).decode("utf-8")
            data_url = f"data:{variant.mime_type};base64,{image_base64}"
            user_content.append({"type": "input_image", "image_url": data_url})
        variant_labels = [variant.label for variant in variants]
        user_content.append(
            {"type": "input_text", "text": _meal_prompt(prompt, variant_labels)}
        )
        meal_input = cast(
            Any,
            [
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": _meal_system_prompt()}],
                },
                {
                    "role": "user",
                    "content": user_content,
                },
            ],
        )
        response = self.client.responses.create(
            model=self.model_name,
            input=meal_input,
            text={"format": {"type": "json_object"}},
        )
        data = json.loads(response.output_text)
        data["provider"] = "openai"
        data["model_name"] = self.model_name
        return MealEstimateResult.model_validate(data)

    def answer_health_question(
        self,
        *,
        question: str,
        context: dict[str, Any],
    ) -> str:
        response = self.client.responses.create(
            model=self.model_name,
            input=[
                {"role": "system", "content": _health_question_system_prompt()},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "question": question,
                            "context": context,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        )
        return response.output_text.strip()

    def parse_meal_text(
        self,
        *,
        text: str,
        target_date: str,
    ) -> MealTextParseResult:
        response = self.client.responses.create(
            model=self.model_name,
            input=[
                {"role": "system", "content": _meal_text_system_prompt()},
                {
                    "role": "user",
                    "content": json.dumps(
                        {"text": text, "target_date": target_date},
                        ensure_ascii=False,
                    ),
                },
            ],
            text={"format": {"type": "json_object"}},
        )
        data = json.loads(response.output_text)
        data["provider"] = "openai"
        data["model_name"] = self.model_name
        return MealTextParseResult.model_validate(data)


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
        "睡眠は時間と分、心拍は bpm、歩数は歩、食事は kcal で表現してください。"
        "weight_kg、bmi、body_fat_percent、weight_kg_vs_30d_avg がある場合は、"
        "体重や体脂肪を短期の増減だけで過度に評価せず、睡眠・活動・食事と合わせて"
        "中長期の傾向として控えめに反映してください。"
        "体重は kg、体脂肪は % で表現してください。"
        "meal_calories、meal_count、average_meal_calories、largest_meal_calories、meal_entries、"
        "meal_trends、meal_calories_vs_7d_avg がある場合は、"
        "一日の合計摂取量だけでなく、食事回数、1回ごとの量、最も重い食事、最近の傾向も"
        "今日の見立てと助言に反映してください。"
        "today_actions は今日すぐ実行できる控えめで具体的な行動提案にしてください。"
        "long_term_comment は weekly_trends、monthly_trends、過去パターンを踏まえた"
        "中長期の分析コメントにしてください。"
        "厳密な JSON のみを返し、キーは "
        "risk_level, summary, key_findings, today_actions, exercise_advice, sleep_advice, "
        "caffeine_advice, medical_note, long_term_comment のみを含めてください。"
    )


def _meal_system_prompt() -> str:
    return (
        "あなたは食事写真から摂取カロリーを推定する栄養ログ補助AIです。"
        "画像は元画像に加えてズーム用の切り抜きが含まれることがあります。"
        "同じ料理を重複カウントせず、料理単位で内訳を見積もってから合計kcalを算出してください。"
        "見えない情報は断定せず、一般的な日本の一人前を保守的に前提にしてください。"
        "厳密な JSON のみを返し、キーは estimated_calories, calorie_range_low, calorie_range_high, "
        "confidence, summary, meal_items, components, rationale のみを含めてください。"
        "components は item_name, estimated_calories, portion_basis を持つ配列です。"
    )


def _meal_prompt(prompt: str, variant_labels: list[str]) -> str:
    return (
        "画像をよく観察し、料理ごとに分解して推定してください。"
        f"画像セット: {', '.join(variant_labels)}。"
        "容器サイズ、米量、衣、ソース、半皿表現、付け合わせも確認してください。"
        "estimated_calories は components の合計と整合するように返してください。"
        f"食事コンテキスト: {prompt}"
    )


def _health_question_system_prompt() -> str:
    return (
        "あなたは個人向けの健康ログアシスタントです。"
        "入力される question と context の事実だけを使って、日本語で簡潔に返答してください。"
        "診断はせず、医療判断は控えめにしてください。"
        "運動相談には、今日無理なくできる実行案を短く具体的に返してください。"
        "LINE 向けの平文のみを返し、JSON や Markdown は使わないでください。"
    )


def _meal_text_system_prompt() -> str:
    return (
        "あなたは食事の手入力メモを構造化し、概算カロリーを保守的に見積もるAIです。"
        "厳密なJSONのみを返し、キーは meals, note のみです。"
        "meals は配列で、各要素は time_text, summary, meal_items, "
        "estimated_calories, confidence を持ちます。"
        "time_text は '07:30' のような時刻、または '朝' '昼' '夕方' '夜' のような簡単な表現です。"
        "summary と meal_items は日本語、estimated_calories は整数kcal、"
        "confidence は low/medium/high です。"
        "食事として読み取れる内容だけを返してください。"
    )
