"""LTR feature vector 생성.

보고서 추천 14개 feature:
img_sim_crop, img_sim_context, category_match, color_match,
neckline_match, fit_match, title_sim_norm, brand_exact, maker_exact,
product_type, seller_score, stock_freshness, shipping_speed_score, explicit_budget_fit
"""
from __future__ import annotations
from typing import Dict, Any, List

import numpy as np

FEATURE_NAMES = [
    "img_sim_crop",        # 의류 crop 임베딩 코사인 유사도
    "img_sim_context",     # 전체 이미지 임베딩 코사인 유사도
    "category_match",      # 카테고리 일치 여부
    "color_match",         # 색상 토큰 title 포함 여부
    "neckline_match",      # 넥라인 일치
    "fit_match",           # 핏 일치
    "title_sim_norm",      # rapidfuzz token_set_ratio
    "brand_exact",         # 브랜드 정확 일치
    "maker_exact",         # 메이커 정확 일치
    "product_type",        # productType 정수 (1=일반, 2=복수옵션)
    "seller_score",        # 판매자 신뢰도 (mall_name 기반)
    "stock_freshness",     # 재고 신선도 (0~1)
    "shipping_speed_score", # 배송 속도 점수 (0~1)
    "explicit_budget_fit",  # 명시 예산 적합 여부
]

TRUSTED_MALLS = {
    "무신사": 0.9, "지그재그": 0.85, "29cm": 0.85, "W컨셉": 0.8,
    "에이블리": 0.8, "패션플러스": 0.7, "네이버쇼핑": 0.6,
}


def _color_match(query_color: str, title: str) -> float:
    if not query_color:
        return 0.0
    return 1.0 if query_color.lower() in title.lower() else 0.0


def _seller_score(mall_name: str) -> float:
    return TRUSTED_MALLS.get(mall_name, 0.5)


def build_features(
    query_attrs: Dict[str, Any],
    products: List[Dict[str, Any]],
    query_emb: np.ndarray,
    product_embs: Dict[str, np.ndarray],
    context_emb: np.ndarray | None = None,
) -> np.ndarray:
    """각 product 마다 14-dim feature vector 생성.

    Returns: (N, 14) numpy array
    """
    from rapidfuzz import fuzz  # lazy import

    rows = []
    for p in products:
        pid = str(p.get("product_id", p.get("productId", "")))
        prod_emb = product_embs.get(pid)

        img_sim_crop = float(np.dot(query_emb, prod_emb)) if prod_emb is not None else 0.0
        img_sim_context = float(np.dot(context_emb, prod_emb)) if (context_emb is not None and prod_emb is not None) else 0.0

        category_match = 1.0 if p.get("category", "") == query_attrs.get("category", "") else 0.0
        color_match = _color_match(query_attrs.get("color", ""), p.get("title", ""))
        neckline_match = 0.0   # TODO: Gemini attr 비교
        fit_match = 0.0        # TODO: Gemini attr 비교

        title_sim = fuzz.token_set_ratio(
            query_attrs.get("title_hint", ""),
            p.get("title", ""),
        ) / 100.0

        brand_exact = 1.0 if (
            query_attrs.get("brand") and query_attrs.get("brand") == p.get("brand")
        ) else 0.0
        maker_exact = 1.0 if (
            query_attrs.get("maker") and query_attrs.get("maker") == p.get("maker")
        ) else 0.0

        product_type = float(p.get("productType", 1) or 1)
        seller = _seller_score(p.get("mallName", p.get("mall_name", "")))
        stock_fresh = 0.5      # TODO: 실시간 재고 API 연동 시 구현
        ship_speed = 0.5       # TODO: 배송 정보 파싱 시 구현

        budget = query_attrs.get("budget_max")
        lprice = int(p.get("lprice", 0) or 0)
        explicit_budget_fit = 1.0 if (budget and lprice <= int(budget)) else 0.0

        rows.append([
            img_sim_crop, img_sim_context, category_match, color_match,
            neckline_match, fit_match, title_sim, brand_exact, maker_exact,
            product_type, seller, stock_fresh, ship_speed, explicit_budget_fit,
        ])

    return np.array(rows, dtype=np.float32)
