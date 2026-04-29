"""무드 기반 복합 소팅 모듈."""
from typing import Dict, List, Tuple


def price_fit_score(product_price: int, price_range: Tuple[int, int]) -> float:
    if product_price is None or product_price <= 0:
        return 0.5
    low, high = price_range
    if low <= product_price <= high:
        return 1.0
    elif product_price < low:
        ratio = (low - product_price) / max(low, 1)
        return max(0.3, 1 - ratio * 0.7)
    else:
        ratio = (product_price - high) / max(high, 1)
        return max(0.1, 1 - ratio * 0.5)


def mood_match_score(product_title: str, mood_keywords: List[str]) -> float:
    if not product_title:
        return 0.5
    title_lower = product_title.lower()
    hits = sum(1 for kw in mood_keywords if kw.lower() in title_lower)
    return min(1.0, 0.5 + hits * 0.15)


MOOD_KEYWORDS = {
    'luxury': ['프리미엄', '럭셔리', '명품', '하이엔드', 'luxury', 'premium'],
    'casual': ['데일리', '캐주얼', 'casual', '베이직'],
    'office': ['오피스', '정장', '포멀', 'office', '클래식'],
    'sporty': ['스포츠', '액티브', '트레이닝', 'sport'],
    'feminine': ['페미닌', '러블리', '로맨틱', '걸리시'],
    'vintage': ['빈티지', '레트로', 'vintage', 'retro'],
    'y2k': ['y2k', '트렌디', '힙'],
    'classic': ['클래식', '베이직', 'classic'],
}


def get_mood_keywords(mood_label: str) -> List[str]:
    for key, kws in MOOD_KEYWORDS.items():
        if key in mood_label.lower():
            return kws
    return []


def compute_final_score(clip_sim: float, mood: float, price_fit: float) -> float:
    return clip_sim * 0.45 + mood * 0.30 + price_fit * 0.25


def rank_products(
    products: List[Dict],
    clip_scores: Dict[str, float],
    mood_label: str,
    price_range: Tuple[int, int],
    sort_by: str = 'relevance',
) -> List[Dict]:
    mood_kws = get_mood_keywords(mood_label)

    for p in products:
        clip = clip_scores.get(p.get('product_id', ''), 0.5)
        mood_score = mood_match_score(p.get('title', ''), mood_kws)
        pfit = price_fit_score(p.get('price', 0), price_range)
        p['_clip_sim'] = clip
        p['_mood_match'] = mood_score
        p['_price_fit'] = pfit
        p['match_score'] = compute_final_score(clip, mood_score, pfit)

    if sort_by == 'price_asc':
        return sorted(products, key=lambda x: (x.get('price', 999999999), -x['match_score']))
    elif sort_by == 'price_desc':
        return sorted(products, key=lambda x: (-x.get('price', 0), -x['match_score']))
    else:
        return sorted(products, key=lambda x: (-x['match_score'], x.get('price', 999999999)))
