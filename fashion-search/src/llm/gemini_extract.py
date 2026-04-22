import json
import logging
from pydantic import BaseModel, Field

from .gemini_client import generate_with_retry

logger = logging.getLogger(__name__)

EXTRACT_PROMPT = """당신은 패션 전문가입니다. 이미지 속 의류 아이템을 분석해 아래 JSON 형식으로만 응답하세요.

{
  "category": "top|bottom|shoes|outer|bag|accessory",
  "color": "주요 색상",
  "fit": "오버핏|슬림핏|와이드|레귤러|크롭",
  "material": "소재 추정",
  "style": "캐주얼|미니멀|빈티지|스트릿|오피스룩|페미닌",
  "confidence": 0.0~1.0
}

의류가 없거나 이미지 품질이 낮으면: {"error": "NO_GARMENT"}"""


class GarmentAttributes(BaseModel):
    category: str = Field(default="unknown")
    color: str = Field(default="")
    fit: str = Field(default="")
    material: str = Field(default="")
    style: str = Field(default="")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


async def extract_attributes(image_bytes: bytes, mime_type: str = "image/jpeg") -> GarmentAttributes | None:
    """Gemini로 의류 속성 추출 (재시도 포함).

    Returns:
        GarmentAttributes 또는 None (실패 시 fallback)
    """
    try:
        text = await generate_with_retry(
            prompt=EXTRACT_PROMPT,
            image_bytes=image_bytes,
            mime_type=mime_type,
        )
        if not text:
            return None

        clean = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        parsed = json.loads(clean)

        if parsed.get("error"):
            return None

        return GarmentAttributes.model_validate(parsed)

    except Exception as exc:
        logger.warning("[gemini_extract] 속성 추출 실패: %s", exc)
        return None  # fallback: rerank without attributes
