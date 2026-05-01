"""벡터 기반 복합 소팅 모듈 v3 — 텍스트 휴리스틱 완전 제거."""
from typing import Dict, List, Optional

import numpy as np

from src.ranking.color_hist import color_score


def cross_modal_mood_score(
    product_image_emb: np.ndarray,
    mood_text_emb: np.ndarray,
) -> float:
    """이미지-텍스트 cross-modal 유사도 (FashionCLIP)."""
    sim = float(np.dot(product_image_emb, mood_text_emb))
    return max(0.0, min(1.0, sim))


def compute_final_score(
    visual_sim: float,
    mood_align: float,
    naver_rank_score: float,
) -> float:
    """[레거시] 단일 점수 공식. 신규: compute_clothing_score / compute_accessory_score 사용."""
    return visual_sim * 0.70 + mood_align * 0.20 + naver_rank_score * 0.10


def compute_clothing_score(
    visual_sim: float,
    color_sim: float,
    naver_rank_score: float,
) -> float:
    """의류: 시각 85% + Lab 색상 10% + Naver 5% (SESSION 11C-1: 5%→10% 단계적 부활)."""
    return visual_sim * 0.85 + color_sim * 0.10 + naver_rank_score * 0.05


def compute_accessory_score(
    visual_sim: float,
    mood_align: float,
    price_fit: float,
    naver_rank_score: float,
) -> float:
    """가방/액세서리: 시각 매칭 절대 우선 (60%), 가격대 필터 보조."""
    return (
        visual_sim * 0.60
        + mood_align * 0.10
        + price_fit * 0.25
        + naver_rank_score * 0.05
    )


def price_fit_score(product_price: int, price_range: tuple) -> float:
    """outfit 무드로 추정한 가격대와 상품 가격의 적합도."""
    if not product_price or product_price <= 0:
        return 0.5
    low, high = price_range
    if low <= product_price <= high:
        return 1.0
    elif product_price < low:
        ratio = (low - product_price) / max(low, 1)
        return max(0.3, 1 - ratio * 0.7)
    else:
        ratio = (product_price - high) / max(high, 1)
        return max(0.05, 1 - ratio * 0.8)


def naver_rank_to_score(rank: int, total: int) -> float:
    """Naver 검색 결과 순위를 0~1 점수로 변환 (선형 감소)."""
    if total <= 0:
        return 0.5
    return max(0.0, 1.0 - rank / total)


def rank_clothing_products(
    products: List[Dict],
    query_image_emb: np.ndarray,
    query_color_hist: np.ndarray,
    query_dominant_colors: Optional[np.ndarray],
    product_image_embs: Dict[str, np.ndarray],
    product_color_hists: Dict[str, np.ndarray],
    product_dominant_colors: Dict[str, np.ndarray],
) -> List[Dict]:
    """의류 재랭킹: 시각 65% + 색상 30% (HSV+dominant) + Naver 5%."""
    total = len(products)
    for i, p in enumerate(products):
        pid = p.get('product_id', '')
        prod_emb = product_image_embs.get(pid)
        prod_hist = product_color_hists.get(pid)
        prod_dom = product_dominant_colors.get(pid)

        visual_sim = max(0.0, float(np.dot(query_image_emb, prod_emb))) if prod_emb is not None else 0.0
        if prod_hist is not None:
            color_sim = color_score(query_color_hist, prod_hist, query_dominant_colors, prod_dom)
        else:
            color_sim = 0.5
        naver_rank = naver_rank_to_score(i, total)

        p['_visual_sim'] = visual_sim
        p['_color_sim'] = color_sim
        p['_mood_align'] = 0.0
        p['_price_fit'] = 0.0
        p['_naver_rank'] = naver_rank
        p['match_score'] = compute_clothing_score(visual_sim, color_sim, naver_rank)

    return sorted(products, key=lambda x: -x['match_score'])


def rank_accessory_products(
    products: List[Dict],
    query_image_emb: np.ndarray,
    product_image_embs: Dict[str, np.ndarray],
    mood_text_emb: np.ndarray,
    price_range: tuple,
) -> List[Dict]:
    """가방/액세서리 재랭킹: 시각 40% + 무드 30% + 가격대 20% + Naver 10%."""
    total = len(products)
    for i, p in enumerate(products):
        pid = p.get('product_id', '')
        prod_emb = product_image_embs.get(pid)

        if prod_emb is not None:
            visual_sim = max(0.0, float(np.dot(query_image_emb, prod_emb)))
            mood_align = cross_modal_mood_score(prod_emb, mood_text_emb)
        else:
            visual_sim = 0.0
            mood_align = 0.0

        pf = price_fit_score(p.get('price', 0), price_range)
        naver_rank = naver_rank_to_score(i, total)

        p['_visual_sim'] = visual_sim
        p['_mood_align'] = mood_align
        p['_price_fit'] = pf
        p['_naver_rank'] = naver_rank
        p['match_score'] = compute_accessory_score(visual_sim, mood_align, pf, naver_rank)

    return sorted(products, key=lambda x: -x['match_score'])


def rank_products_v3(
    products: List[Dict],
    query_image_emb: np.ndarray,
    product_image_embs: Dict[str, np.ndarray],
    mood_text_emb: np.ndarray,
    sort_by: str = 'relevance',
) -> List[Dict]:
    """[레거시] 벡터 기반 재랭킹 (v3). 신규 코드는 rank_clothing/accessory_products 사용."""
    total = len(products)

    for i, p in enumerate(products):
        pid = p.get('product_id', '')
        prod_emb = product_image_embs.get(pid)

        if prod_emb is not None:
            visual_sim = float(np.dot(query_image_emb, prod_emb))
            visual_sim = max(0.0, visual_sim)
            mood_align = cross_modal_mood_score(prod_emb, mood_text_emb)
        else:
            visual_sim = 0.0
            mood_align = 0.0

        naver_rank = naver_rank_to_score(i, total)

        p['_visual_sim'] = visual_sim
        p['_mood_align'] = mood_align
        p['_naver_rank'] = naver_rank
        p['match_score'] = compute_final_score(visual_sim, mood_align, naver_rank)

    if sort_by == 'price_asc':
        return sorted(products, key=lambda x: (x.get('price', 999999999), -x['match_score']))
    elif sort_by == 'price_desc':
        return sorted(products, key=lambda x: (-x.get('price', 0), -x['match_score']))
    else:
        return sorted(products, key=lambda x: -x['match_score'])


def rank_products(products, clip_scores, mood_label, price_range, sort_by='relevance'):
    """[DEPRECATED] Use rank_clothing_products / rank_accessory_products."""
    raise DeprecationWarning("rank_products is deprecated.")
