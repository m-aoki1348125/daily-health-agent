from __future__ import annotations

import json
import logging
from base64 import b64encode
from typing import Any, cast

import httpx

from app.clients.llm_base import LLMProvider
from app.config.settings import Settings
from app.schemas.advice_result import AdviceResult
from app.schemas.meal_estimate import MealEstimateResult, MealTextParseResult
from app.services.meal_image_service import prepare_meal_image_variants


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
        content = self._create_advice_content(model_name, payload)
        try:
            data = _normalize_advice_payload(_parse_json_object(content), payload)
        except Exception:
            repaired = self._repair_advice_content(model_name, content)
            data = _normalize_advice_payload(_parse_json_object(repaired), payload)
        data["provider"] = "claude"
        data["model_name"] = model_name
        return AdviceResult.model_validate(data)

    def estimate_meal(
        self,
        *,
        prompt: str,
        image_bytes: bytes,
        mime_type: str,
    ) -> MealEstimateResult:
        model_name = self._resolve_model_name()
        variants = prepare_meal_image_variants(image_bytes, mime_type)
        content_blocks: list[dict[str, Any]] = []
        for variant in variants:
            content_blocks.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": variant.mime_type,
                        "data": b64encode(variant.image_bytes).decode("utf-8"),
                    },
                }
            )
        content_blocks.append({"type": "text", "text": _meal_prompt(prompt, variants=variants)})
        message = self.client.messages.create(
            model=model_name,
            max_tokens=700,
            system=_meal_system_prompt(),
            output_config={
                "format": {
                    "type": "json_schema",
                    "schema": _meal_json_schema(),
                }
            },
            messages=[
                {
                    "role": "user",
                    "content": cast(Any, content_blocks),
                }
            ],
        )
        text_blocks = [
            cast(str, block.text)
            for block in message.content
            if hasattr(block, "text") and block.text is not None
        ]
        content = "".join(text_blocks)
        data = _parse_json_object(content)
        data["provider"] = "claude"
        data["model_name"] = model_name
        return MealEstimateResult.model_validate(data)

    def answer_health_question(
        self,
        *,
        question: str,
        context: dict[str, Any],
    ) -> str:
        model_name = self._resolve_model_name()
        message = self.client.messages.create(
            model=model_name,
            max_tokens=700,
            system=_health_question_system_prompt(),
            messages=[
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "question": question,
                            "context": context,
                        },
                        ensure_ascii=False,
                    ),
                }
            ],
        )
        return "".join(
            cast(str, block.text)
            for block in message.content
            if hasattr(block, "text") and block.text is not None
        ).strip()

    def parse_meal_text(
        self,
        *,
        text: str,
        target_date: str,
    ) -> MealTextParseResult:
        model_name = self._resolve_model_name()
        message = self.client.messages.create(
            model=model_name,
            max_tokens=900,
            system=_meal_text_system_prompt(),
            messages=[
                {
                    "role": "user",
                    "content": json.dumps(
                        {"text": text, "target_date": target_date},
                        ensure_ascii=False,
                    ),
                }
            ],
        )
        content = "".join(
            cast(str, block.text)
            for block in message.content
            if hasattr(block, "text") and block.text is not None
        )
        data = _parse_json_object(content)
        data["provider"] = "claude"
        data["model_name"] = model_name
        return MealTextParseResult.model_validate(data)

    def _resolve_model_name(self) -> str:
        preferred = self.model_name
        if self._model_exists(preferred):
            return preferred

        fallback_candidates = [
            "claude-haiku-4-5",
            "claude-sonnet-4-5",
            "claude-sonnet-4-5-20250929",
            "claude-opus-4-6",
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

    def _create_advice_content(self, model_name: str, payload: dict[str, Any]) -> str:
        message = self.client.messages.create(
            model=model_name,
            max_tokens=1200,
            system=_system_prompt(),
            output_config={
                "format": {
                    "type": "json_schema",
                    "schema": _advice_json_schema(),
                }
            },
            messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        )
        return "".join(
            cast(str, block.text)
            for block in message.content
            if hasattr(block, "text") and block.text is not None
        )

    def _repair_advice_content(self, model_name: str, content: str) -> str:
        self.logger.warning("retrying Claude advice parsing with repair prompt")
        message = self.client.messages.create(
            model=model_name,
            max_tokens=1200,
            system="壊れたJSONを厳密なJSONへ修復する役割です。JSONのみを返してください。",
            messages=[
                {
                    "role": "user",
                    "content": (
                        "次のテキストを、health advice schema に合う "
                        "JSON オブジェクトだけへ整形してください。\n"
                        f"{content}"
                    ),
                }
            ],
        )
        return "".join(
            cast(str, block.text)
            for block in message.content
            if hasattr(block, "text") and block.text is not None
        )

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
        "出力形式は API 側で JSON schema により強制されます。"
        "各フィールドの中身だけを自然な日本語で埋めてください。"
    )


def _advice_json_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "risk_level",
            "summary",
            "key_findings",
            "today_actions",
            "exercise_advice",
            "sleep_advice",
            "caffeine_advice",
            "medical_note",
            "long_term_comment",
        ],
        "properties": {
            "risk_level": {
                "type": "string",
                "enum": ["green", "yellow", "red", "Green", "Yellow", "Red"],
            },
            "summary": {"type": "string"},
            "key_findings": {
                "type": "array",
                "items": {"type": "string"},
            },
            "today_actions": {
                "type": "array",
                "items": {"type": "string"},
            },
            "exercise_advice": {"type": "string"},
            "sleep_advice": {"type": "string"},
            "caffeine_advice": {"type": "string"},
            "medical_note": {"type": "string"},
            "long_term_comment": {"type": "string"},
        },
    }


def _meal_system_prompt() -> str:
    return (
        "あなたは食事写真から摂取カロリーを推定する栄養ログ補助AIです。"
        "医師ではありません。画像に写る事実だけを使い、見えない情報は保守的に扱ってください。"
        "与えられる画像には元画像に加えてズーム用の切り抜きが含まれることがあります。"
        "複数画像は同じ1食を別視点で見たものとして統合し、重複カウントしないでください。"
        "まず料理ごとに分解して量を推定し、その合計として総カロリーを出してください。"
        "容器サイズ、弁当の区画、丼や皿の面積、衣の厚さ、米の量、ソース量、半皿表現を丁寧に見てください。"
        "飲み物、汁物、小鉢、付け合わせが見える場合は含めてください。"
        "判断が難しいときは、一般的な日本の外食・弁当の一人前を基準にしつつ、過大推定を避けてください。"
        "few-shot examples:\n"
        "<example>\n"
        "input: 唐揚げ弁当の写真\n"
        "output: 唐揚げ 320kcal, ごはん 280kcal, 副菜 40kcal, 合計 640kcal\n"
        "</example>\n"
        "<example>\n"
        "input: 牛丼並盛の写真\n"
        "output: 牛丼 680kcal, 味噌汁 35kcal, 合計 715kcal\n"
        "</example>\n"
        "<example>\n"
        "input: 炒飯半皿の写真\n"
        "output: 炒飯半皿 310kcal, 合計 310kcal\n"
        "</example>\n"
        "出力形式は API 側で JSON schema により強制されます。"
    )


def _meal_prompt(prompt: str, *, variants: list[Any]) -> str:
    labels = ", ".join(str(variant.label) for variant in variants)
    return (
        "<instructions>"
        "画像をよく観察し、見える料理を料理単位で列挙してください。"
        "各料理について推定kcalと量の根拠を短く出し、最後に合計kcalを返してください。"
        "summary には食事全体の説明を1文で、meal_items には料理名だけを入れてください。"
        "components には料理ごとの kcal と portion_basis を入れてください。"
        "calorie_range_low/high は保守的な下限・上限を整数で返してください。"
        "estimated_calories は components の合計と整合する値にしてください。"
        "</instructions>"
        f"<image_set>{labels}</image_set>"
        f"<meal_context>{prompt}</meal_context>"
    )


def _meal_json_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "estimated_calories",
            "calorie_range_low",
            "calorie_range_high",
            "confidence",
            "summary",
            "meal_items",
            "components",
            "rationale",
        ],
        "properties": {
            "estimated_calories": {"type": "integer", "minimum": 0},
            "calorie_range_low": {"type": "integer", "minimum": 0},
            "calorie_range_high": {"type": "integer", "minimum": 0},
            "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
            "summary": {"type": "string"},
            "meal_items": {"type": "array", "items": {"type": "string"}},
            "components": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["item_name", "estimated_calories", "portion_basis"],
                    "properties": {
                        "item_name": {"type": "string"},
                        "estimated_calories": {"type": "integer", "minimum": 0},
                        "portion_basis": {"type": "string"},
                    },
                },
            },
            "rationale": {"type": "string"},
        },
    }


def _health_question_system_prompt() -> str:
    return (
        "あなたは個人向けの健康ログアシスタントです。"
        "入力される question と context だけに基づいて、自然な日本語で簡潔に答えてください。"
        "医師ではないため診断はせず、断定的な医療判断は避けてください。"
        "運動の質問には、睡眠、心拍、歩数、食事、直近アドバイスを踏まえて"
        "今日無理なくできる具体策を 2〜4 文で返してください。"
        "記録参照の質問には、context にある数値だけを使って答えてください。"
        "Markdown や JSON ではなく、LINE にそのまま返せる平文だけを返してください。"
    )


def _meal_text_system_prompt() -> str:
    return (
        "あなたは食事の手入力メモを構造化し、概算カロリーを保守的に見積もるAIです。"
        "入力は日本語の自由文で、朝食・昼食・夕食・間食と時間のヒントが含まれます。"
        "厳密なJSONのみを返し、キーは meals, note のみです。"
        "meals は配列で、各要素は time_text, summary, meal_items, "
        "estimated_calories, confidence を持ちます。"
        "time_text は '07:30' のような時刻、または '朝' '昼' '夕方' '夜' のような簡単な表現です。"
        "summary と meal_items は日本語、estimated_calories は整数kcal、"
        "confidence は low/medium/high です。"
        "食事が明確でない文は無理に増やさず、食事として読み取れる内容だけを返してください。"
    )


def _parse_json_object(content: str) -> dict[str, Any]:
    content = content.strip()
    if content.startswith("```"):
        lines = content.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        content = "\n".join(lines).strip()
        if content.startswith("json"):
            content = content[4:].strip()
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
