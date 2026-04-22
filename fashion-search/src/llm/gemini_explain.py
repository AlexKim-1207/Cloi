"""검색 결과 설명 생성 (옵션 기능).

Gemini로 상위 결과에 대한 간략한 설명을 생성.
비용 절감을 위해 기본적으로 비활성화 — 명시적 호출 시에만 사용.
"""
import logging

from .gemini_client import generate_with_retry

logger = logging.getLogger(__name__)

EXPLAIN_PROMPT = """당신은 패션 스타일리스트입니다.
아래 검색 조건에 가장 잘 맞는 의류 상품들을 찾았습니다.
왜 이 상품들이 추천되었는지 2~3문장으로 간결하게 설명해 주세요. 한국어로 답변하세요.

검색 조건:
- 카테고리: {category}
- 색상: {color}
- 스타일: {style}
- 핏: {fit}

상위 결과 (product_id 목록): {product_ids}"""


async def generate_explanation(
    category: str = "",
    color: str = "",
    style: str = "",
    fit: str = "",
    product_ids: list[str] | None = None,
) -> str:
    """검색 조건 + 결과 상품 목록 → 자연어 설명 생성.

    Returns:
        설명 문자열, 실패 시 빈 문자열
    """
    try:
        prompt = EXPLAIN_PROMPT.format(
            category=category or "미지정",
            color=color or "미지정",
            style=style or "미지정",
            fit=fit or "미지정",
            product_ids=", ".join(product_ids or []) or "없음",
        )
        text = await generate_with_retry(prompt=prompt)
        return text or ""
    except Exception as exc:
        logger.warning("[gemini_explain] 설명 생성 실패: %s", exc)
        return ""
