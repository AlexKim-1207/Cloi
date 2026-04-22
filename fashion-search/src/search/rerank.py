"""Reranker — 벡터 유사도 + Gemini 속성 가중치 기반 최종 스코어링.

가중치 (합 = 1.0):
    sim      0.55  벡터 코사인 유사도 (FAISS inner product, L2 norm 후)
    category 0.10  카테고리 일치 보너스
    color    0.10  색상 일치 보너스
    fit      0.08  핏 일치 보너스
    style    0.07  스타일 일치 보너스
    shipping 0.05  배송 속도 (메타 데이터 기반)
    stock    0.05  재고 여부 (메타 데이터 기반)
"""
import logging
from dataclasses import dataclass, field

from .retrieve import SearchCandidate
from ..llm.gemini_extract import GarmentAttributes

logger = logging.getLogger(__name__)

# 가중치 상수
W_SIM = 0.55
W_CAT = 0.10
W_COLOR = 0.10
W_FIT = 0.08
W_STYLE = 0.07
W_SHIPPING = 0.05
W_STOCK = 0.05


@dataclass
class RankedResult:
    """최종 랭킹 결과."""
    product_id: str
    path: str
    vector_similarity: float
    final_score: float
    meta: dict = field(default_factory=dict)


def _match_score(a: str, b: str) -> float:
    """두 속성 문자열이 같으면 1.0, 빈 값이면 0.5 (중립), 다르면 0.0."""
    if not a or not b:
        return 0.5  # 속성 미지정 → 페널티 없음
    return 1.0 if a.strip().lower() == b.strip().lower() else 0.0


def _shipping_score(meta: dict) -> float:
    """메타에서 배송 점수 추출 (0~1). 없으면 0.5 중립."""
    days = meta.get("shipping_days")
    if days is None:
        return 0.5
    if days <= 1:
        return 1.0
    if days <= 3:
        return 0.7
    return 0.3


def _stock_score(meta: dict) -> float:
    """메타에서 재고 점수 추출 (0~1). 없으면 0.5 중립."""
    in_stock = meta.get("in_stock")
    if in_stock is None:
        return 0.5
    return 1.0 if in_stock else 0.0


def rerank(
    candidates: list[SearchCandidate],
    query_attrs: GarmentAttributes | None,
    top_n: int = 20,
) -> list[RankedResult]:
    """후보 리스트를 최종 스코어로 재랭킹.

    Args:
        candidates: FAISS 검색 결과
        query_attrs: Gemini가 추출한 쿼리 이미지 속성 (없으면 벡터 유사도만 사용)
        top_n: 반환할 최대 결과 수

    Returns:
        final_score 내림차순 RankedResult 리스트
    """
    if not candidates:
        return []

    results: list[RankedResult] = []

    for c in candidates:
        sim = max(0.0, min(1.0, c.score))  # inner product → [0, 1] 클리핑

        if query_attrs is None:
            # 속성 없음 → 벡터 유사도만 (가중치 합 재분배)
            final = sim
        else:
            cat_s = _match_score(query_attrs.category, c.meta.get("category", ""))
            color_s = _match_score(query_attrs.color, c.meta.get("color", ""))
            fit_s = _match_score(query_attrs.fit, c.meta.get("fit", ""))
            style_s = _match_score(query_attrs.style, c.meta.get("style", ""))
            ship_s = _shipping_score(c.meta)
            stock_s = _stock_score(c.meta)

            final = (
                W_SIM * sim
                + W_CAT * cat_s
                + W_COLOR * color_s
                + W_FIT * fit_s
                + W_STYLE * style_s
                + W_SHIPPING * ship_s
                + W_STOCK * stock_s
            )

        results.append(
            RankedResult(
                product_id=c.product_id,
                path=c.path,
                vector_similarity=sim,
                final_score=round(final, 4),
                meta=c.meta,
            )
        )

    results.sort(key=lambda r: r.final_score, reverse=True)
    logger.debug("[rerank] 상위 %d개 / 전체 %d개", min(top_n, len(results)), len(results))
    return results[:top_n]
