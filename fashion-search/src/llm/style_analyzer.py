"""Gemini — 패션 이미지 멀티아이템 탐지 + 스타일 분석."""
import asyncio
import logging
from src.config.settings import get_settings

from google.genai import types
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from .gemini_client import get_client
from .schemas import MultiItemStyleContext

logger = logging.getLogger(__name__)

_PROMPT = (
    "이 패션 이미지에서 착용된 모든 아이템을 개별로 탐지해줘. "
    "상의/이너/아우터/하의/가방/신발/액세서리 전부 포함. "
    "레이어드된 경우 각각 별도 아이템으로 분리. "
    "같은 카테고리라도 니트 베스트 + 이너 셔츠는 별도. "
    "반지/귀걸이/목걸이/벨트/모자/시계 등 액세서리 종류별 개별 탐지. "
    "각 아이템: "
    "tab_id(top_outer/top_inner/outer/bottom/dress/shoes/bag/"
    "accessory_ring/accessory_necklace/accessory_earring/accessory_belt/accessory_hat/accessory_watch), "
    "category(한글 카테고리명), "
    "subcategory(세부 종류), "
    "description(색상+소재+핏+세부디테일 모두 포함한 한국어 설명), "
    "is_inner(이너 여부), "
    "searchQueries(네이버쇼핑 검색에 자연스러운 한국어 쿼리 3개). "
    "얼굴/신체는 무시. 옷/잡화 아이템에만 집중."
)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception(lambda e: any(k in str(e).lower() for k in ("503", "unavailable", "high demand", "resource_exhausted", "429"))),
    reraise=True,
)
async def analyze_style(image_bytes: bytes, mime_type: str = "image/jpeg") -> MultiItemStyleContext:
    """이미지 전체를 1회 호출해 MultiItemStyleContext 반환."""
    client = get_client()

    def _sync_call() -> str:
        response = client.models.generate_content(
            model=get_settings().gemini_model,
            contents=[
                types.Part.from_text(text=_PROMPT),
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            ],
            config=types.GenerateContentConfig(
                temperature=0,
                response_mime_type="application/json",
                response_schema=MultiItemStyleContext,
            ),
        )
        return response.text

    try:
        text = await asyncio.to_thread(_sync_call)
        context = MultiItemStyleContext.model_validate_json(text)
        logger.info(
            "[style_analyzer] 분석 완료: style=%s, items=%d",
            context.overall_style_context,
            len(context.detected_items),
        )
        return context
    except Exception as exc:
        logger.warning("[style_analyzer] 분석 실패: %s", exc)
        raise
