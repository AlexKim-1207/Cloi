"""Gemini — 패션 이미지 전체 스타일 분석."""
import asyncio
import logging
from src.config.settings import get_settings

from google.genai import types
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from .gemini_client import get_client
from .schemas import StyleContext

logger = logging.getLogger(__name__)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception(lambda e: any(k in str(e).lower() for k in ("503", "unavailable", "high demand", "resource_exhausted", "429"))),
    reraise=True,
)
async def analyze_style(image_bytes: bytes, mime_type: str = "image/jpeg") -> StyleContext:
    """이미지 전체를 1회 호출해 StyleContext 반환.

    crop 없이 전체 이미지를 Gemini에게 전달 — 아이템 목록 + 무드 추출.
    blocking SDK 호출을 asyncio.to_thread로 감싸 이벤트 루프를 블록하지 않음.
    """
    client = get_client()

    def _sync_call() -> str:
        response = client.models.generate_content(
            model=get_settings().gemini_model,
            contents=[
                types.Part.from_text(
                    text=(
                        "이 패션 이미지에서 전체 스타일을 분석해줘. "
                        "착용된 모든 의류/신발/가방 아이템을 파악하고, "
                        "전반적인 스타일 무드와 각 아이템의 카테고리·색상·핏을 추출해줘. "
                        "얼굴, 신체는 무시하고 의류/잡화 아이템에만 집중해. "
                        "confidence는 분석 확신도 (0.0~1.0)로 설정해줘."
                    )
                ),
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            ],
            config=types.GenerateContentConfig(
                temperature=0,
                response_mime_type="application/json",
                response_schema=StyleContext,
            ),
        )
        return response.text

    try:
        text = await asyncio.to_thread(_sync_call)
        context = StyleContext.model_validate_json(text)
        logger.info(
            "[style_analyzer] 분석 완료: style=%s, items=%d",
            context.overall_style,
            len(context.items),
        )
        return context
    except Exception as exc:
        logger.warning("[style_analyzer] 분석 실패: %s", exc)
        raise
