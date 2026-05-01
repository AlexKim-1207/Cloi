"""정확도+가격 4분면 소팅 — 동적 임계값."""
import numpy as np

# Fix 10-3: 정적 0.6 → 동적 (해당 batch median + floor)
DEFAULT_ACCURACY_FLOOR = 0.40   # 모든 점수가 낮아도 quadrant 0 후보 보장


def quadrant_key(product: dict, price_median: float, score_threshold: float) -> tuple:
    """4분면 정렬 키. score_threshold는 batch마다 동적 결정."""
    score = product.get('match_score', 0.0)
    price = product.get('price') or 999_999_999

    is_accurate = score >= score_threshold
    is_cheap = price <= price_median

    if is_accurate and is_cheap:
        quadrant = 0
    elif is_accurate and not is_cheap:
        quadrant = 1
    elif not is_accurate and is_cheap:
        quadrant = 2
    else:
        quadrant = 3

    return (quadrant, -score)


def quadrant_sort(products: list) -> list:
    """4분면 기준 정렬. 임계값을 batch median으로 동적 결정."""
    if not products:
        return []

    prices = [p.get('price') or 0 for p in products if p.get('price')]
    price_median = float(np.median(prices)) if prices else 50_000.0

    scores = [p.get('match_score', 0.0) for p in products]
    if scores:
        score_median = float(np.median(scores))
        score_threshold = max(DEFAULT_ACCURACY_FLOOR, score_median)
    else:
        score_threshold = DEFAULT_ACCURACY_FLOOR

    return sorted(
        products,
        key=lambda p: quadrant_key(p, price_median, score_threshold),
    )
