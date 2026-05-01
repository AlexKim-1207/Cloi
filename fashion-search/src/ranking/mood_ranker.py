"""벡터 기반 복합 소팅 모듈 v3 — 텍스트 휴리스틱 완전 제거."""
from typing import Dict, List, Optional

import numpy as np


def cross_modal_mood_score(
    product_image_emb: np.ndarray,
    mood_text_emb: np.ndarray,
) -> float:
    """이미지-텍스트 cross-modal 유사도 (FashionCLIP).

    상품 이미지 임베딩과 detected mood 텍스트 임베딩의 코사인 유사도.
    텍스트 키워드 매칭이 아닌 벡터 공간에서 무드 일치도 측정.
    """
    sim = float(np.dot(product_image_emb, mood_text_emb))
    return max(0.0, min(1.0, sim))


def compute_final_score(
    visual_sim: float,
    mood_align: float,
    naver_rank_score: float,
) -> float:
    """벡터 기반 복합 점수 — 텍스트 휴리스틱 완전 제거.

    가중치:
    - visual_sim: 0.70 (핵심 신호)
    - mood_align: 0.20 (벡터 기반 무드 일치)
    - naver_rank_score: 0.10 (텍스트 검색 relevance 보조)
    """
    return visual_sim * 0.70 + mood_align * 0.20 + naver_rank_score * 0.10


def naver_rank_to_score(rank: int, total: int) -> float:
    """Naver 검색 결과 순위를 0~1 점수로 변환 (선형 감소)."""
    if total <= 0:
        return 0.5
    return max(0.0, 1.0 - rank / total)


def rank_products_v3(
    products: List[Dict],
    query_image_emb: np.ndarray,
    product_image_embs: Dict[str, np.ndarray],
    mood_text_emb: np.ndarray,
    sort_by: str = 'relevance',
) -> List[Dict]:
    """벡터 기반 재랭킹 (v3)."""
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
    """[DEPRECATED] Use rank_products_v3 instead."""
    raise DeprecationWarning("rank_products v2 is deprecated. Use rank_products_v3.")
