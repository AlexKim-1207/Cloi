"""정확도+가격 4분면 소팅."""
import numpy as np

ACCURACY_THRESHOLD = 0.6


def quadrant_key(product: dict, price_median: float) -> tuple:
    """4분면 정렬 키.

    분면 번호 (낮을수록 우선):
        0: 정확도 높음 + 가격 낮음 (median 이하)
        1: 정확도 높음 + 가격 높음
        2: 정확도 낮음 + 가격 낮음
        3: 정확도 낮음 + 가격 높음

    같은 분면 내에서는 match_score 내림차순.
    """
    score = product.get('match_score', 0.0)
    price = product.get('price') or 999_999_999

    is_accurate = score >= ACCURACY_THRESHOLD
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
    """4분면 기준 정렬. 가격 중앙값 기준으로 싸/비싸 구분."""
    if not products:
        return []

    prices = [p.get('price') or 0 for p in products if p.get('price')]
    price_median = float(np.median(prices)) if prices else 50_000.0

    return sorted(products, key=lambda p: quadrant_key(p, price_median))
