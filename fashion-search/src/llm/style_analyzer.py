"""Gemini — 패션 이미지 멀티아이템 탐지 + 스타일 분석."""
import asyncio
import logging
from src.config.settings import get_settings

from google.genai import types
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from .gemini_client import get_client
from .schemas import MultiItemStyleContext

logger = logging.getLogger(__name__)

_PROMPT = """이 패션 이미지를 다음 절차로 빠짐없이 분석하라.

## 1단계: 영역별 점검 (각 영역에 시각적으로 보이는 모든 것 나열)
- 머리: 모자/헤어밴드/헤어핀 등
- 얼굴/귀: 귀걸이/안경
- 목: 목걸이/스카프/넥타이
- 손목: 시계/팔찌
- 손가락: 반지
- 상체: 셔츠/티셔츠/니트/카디건/재킷/코트 (레이어드 시 각각 분리)
- 허리: 벨트
- 하체: 바지/스커트/원피스
- 발: 신발
- 들고/메고 있는 것: 가방/백팩/클러치

## 2단계: 각 보이는 아이템마다 1개 DetectedItem 생성
필수 필드:
- tab_id: 다음 중 정확히 하나
  top_outer, top_inner, outer, bottom, dress, shoes, bag,
  accessory_ring, accessory_necklace, accessory_earring,
  accessory_belt, accessory_hat, accessory_watch
- category: 한글 카테고리명 (예: 셔츠, 청바지, 숄더백)
- subcategory: 세부 종류 (예: 오버사이즈 셔츠, 스트레이트 데님)
- description: 색상+소재+핏+세부디테일 한국어 설명 (충분히 상세하게)
- is_inner: 이너 여부 (true/false)
- searchQueries: 네이버쇼핑 자연 한국어 쿼리 3개

## 3단계: 자기 검토
- 작은 액세서리 (반지/귀걸이) 빠뜨리지 않았나?
- 레이어드된 상의 분리했나? (예: 셔츠 + 안의 티셔츠)
- 가방을 손에 들고 있어도 탐지했나?

## 출력 규칙
- 보이는 모든 것 포함. 자신없어도 가능성 있으면 포함.
- 같은 카테고리(top_inner)도 여러 개 가능.
- 얼굴/신체 자체는 무시.
- overall_style_context는 outfit 전체 무드 한국어 1~2문장.

JSON으로만 응답하라."""


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
