from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .config import settings
from .images import image_to_data_url
from .models import MomentAnalysis


ANALYSIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "category": {"type": "string"},
        "title": {"type": "string"},
        "objects": {"type": "array", "items": {"type": "string"}},
        "tags": {"type": "array", "items": {"type": "string"}},
        "is_food": {"type": "boolean"},
        "calories_estimate": {"type": ["integer", "null"]},
        "portion_guess": {"type": ["string", "null"]},
        "confidence": {"type": "number"},
        "caption": {"type": "string"},
        "mood_color": {"type": "string"},
    },
    "required": [
        "category",
        "title",
        "objects",
        "tags",
        "is_food",
        "calories_estimate",
        "portion_guess",
        "confidence",
        "caption",
        "mood_color",
    ],
}


def fallback_analysis(reason: str = "missing_api_key") -> MomentAnalysis:
    return MomentAnalysis(
        category="daily",
        title="待识别的小记录",
        objects=[],
        tags=["待识别"],
        is_food=False,
        calories_estimate=None,
        portion_guess=None,
        confidence=0,
        caption="照片已经保存好了，配置 AI 后可以重新识别。",
        mood_color="#f3a6a6",
        ai_status=reason,
    )


def analyze_image(image_path: Path) -> MomentAnalysis:
    if not settings.openai_api_key:
        return fallback_analysis()

    prompt = (
        "你是一个温柔、审美敏感的私人生活记录助手。"
        "请识别照片中的主要物品、场景或食物，并为中文手机记录卡片生成内容。"
        "如果是食物，请估算卡路里和份量，但必须保守表达为估算。"
        "标题要短，标签 2 到 6 个，caption 像私人相册里的轻柔一句话。"
        "mood_color 返回适合这张照片的十六进制颜色。"
    )
    body = {
        "model": settings.openai_model,
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_image", "image_url": image_to_data_url(image_path), "detail": "auto"},
                ],
            }
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "moment_analysis",
                "schema": ANALYSIS_SCHEMA,
                "strict": True,
            }
        },
    }

    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        return fallback_analysis(f"ai_error_{exc.code}:{detail[:120]}")
    except Exception as exc:  # Network and JSON edge cases should not block saving.
        return fallback_analysis(f"ai_error:{exc.__class__.__name__}")

    text = extract_output_text(payload)
    try:
        parsed = json.loads(text)
        parsed["ai_status"] = "ok"
        return MomentAnalysis(**parsed)
    except Exception:
        return fallback_analysis("ai_parse_error")


def extract_output_text(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    chunks: list[str] = []
    for item in payload.get("output", []):
        for content in item.get("content", []):
            if isinstance(content.get("text"), str):
                chunks.append(content["text"])
    joined = "\n".join(chunks).strip()
    if joined:
        return joined
    text = json.dumps(payload, ensure_ascii=False)
    match = re.search(r"\{.*\}", text, re.S)
    return match.group(0) if match else "{}"
