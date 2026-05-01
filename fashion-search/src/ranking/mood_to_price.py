"""Outfit 무드 → 가격대 추정 (가방/액세서리용)."""

MOOD_TO_PRICE_TIER: dict[str, tuple[int, int]] = {
    'casual_daily': (5_000, 80_000),
    'casual_street': (10_000, 100_000),
    'office_minimal': (30_000, 200_000),
    'office_classic': (50_000, 300_000),
    'luxury_editorial': (200_000, 5_000_000),
    'sporty_active': (10_000, 120_000),
    'feminine_romantic': (20_000, 150_000),
    'vintage_y2k': (10_000, 100_000),
}

DEFAULT_PRICE_RANGE = (10_000, 100_000)


def estimate_price_range_from_mood(mood_label: str) -> tuple[int, int]:
    """Gemini 분석한 outfit 무드 → 적정 가격대 (가방/액세서리 전용)."""
    mood_lower = mood_label.lower()
    for key, range_tuple in MOOD_TO_PRICE_TIER.items():
        if any(token in mood_lower for token in key.split('_')):
            return range_tuple
    return DEFAULT_PRICE_RANGE


def is_accessory_tab(tab_id: str) -> bool:
    """가방/액세서리 탭 여부."""
    return tab_id == 'bag' or tab_id.startswith('accessory_')
