"""한국 패션 상품명 정규화 + SKU 매칭."""
import re

import numpy as np

try:
    from rapidfuzz import fuzz  # type: ignore
    _RAPIDFUZZ_AVAILABLE = True
except ImportError:
    _RAPIDFUZZ_AVAILABLE = False

STOPWORDS = {
    "무료배송", "당일출고", "오늘출발", "최저가", "특가", "행사", "세일",
    "여성", "남성", "봄신상", "신상", "추천", "인기", "베스트",
}

REPLACERS = [
    (r"\b(v[\s-]?neck|브이넥|v넥)\b", "v_neck"),
    (r"\b(라운드넥|round[\s-]?neck|crew[\s-]?neck)\b", "crew_neck"),
    (r"\b(오버핏|루즈핏|박시)\b", "oversized"),
    (r"\b(슬림핏|타이트핏)\b", "slim_fit"),
    (r"\b(오프화이트|아이보리)\b", "white"),
]

TOKEN_RE = re.compile(r"[a-zA-Z0-9_가-힣]+")


def normalize_title(title: str) -> str:
    s = title.lower()
    s = re.sub(r"<[^>]+>", " ", s)
    for pat, rep in REPLACERS:
        s = re.sub(pat, rep, s, flags=re.IGNORECASE)
    toks = [t for t in TOKEN_RE.findall(s) if t not in STOPWORDS]
    return " ".join(toks)


def title_similarity(a: str, b: str) -> float:
    if not _RAPIDFUZZ_AVAILABLE:
        a_toks = set(normalize_title(a).split())
        b_toks = set(normalize_title(b).split())
        if not a_toks and not b_toks:
            return 1.0
        if not a_toks or not b_toks:
            return 0.0
        return len(a_toks & b_toks) / len(a_toks | b_toks)
    return fuzz.token_set_ratio(normalize_title(a), normalize_title(b)) / 100.0


def cluster_similar_products(
    products: list[dict],
    title_threshold: float = 0.75,
) -> list[list[dict]]:
    """동일 SKU 추정 클러스터링 (레거시).

    같은 클러스터 = 같은 디자인의 다른 판매처.
    """
    clusters: list[list[dict]] = []
    used: set[int] = set()

    for i, p in enumerate(products):
        if i in used:
            continue
        cluster = [p]
        used.add(i)
        for j, q in enumerate(products[i + 1:], start=i + 1):
            if j in used:
                continue
            sim = title_similarity(p.get('title', ''), q.get('title', ''))
            brand_match = (
                p.get('brand') and p['brand'] == q.get('brand')
            )
            if sim >= title_threshold or brand_match:
                cluster.append(q)
                used.add(j)
        clusters.append(cluster)

    return clusters


# Fix B3: 다양한 모델코드 패턴 매칭
_MODEL_CODE_PATTERNS = [
    re.compile(r'\b[A-Z]{2,}[\-_/]?[A-Z0-9]{2,}\b'),              # ABCDE-1234
    re.compile(r'\b[0-9]{6,}\b'),                                    # 81200301 (6자리+)
    re.compile(r'\b[A-Z0-9]+[\-_/][A-Z0-9]+(?:[\-_/][A-Z0-9]+)*\b'),  # 739682-AABZC-001
]


def extract_model_codes(title: str) -> list[str]:
    """제목에서 모델코드 추출. 다양한 패턴 지원.

    추출 대상:
    - 6자리 이상 순수 숫자 (예: 81200301)
    - 영문+숫자 혼합 (예: 739682-AABZC)
    - 슬래시/언더바 구분 (예: ABC_123_XYZ)
    """
    if not title:
        return []
    text_upper = title.upper()
    codes: set[str] = set()
    for pattern in _MODEL_CODE_PATTERNS:
        codes.update(pattern.findall(text_upper))
    return [c for c in codes if len(c) >= 5]


# Fix B2+B7: 카테고리별 클러스터링 임계값
CLUSTER_THRESHOLDS_CLOTHING = {
    'image_sim_strong': 0.90,   # 단독으로 묶기 충분 (이전 0.92 → 0.90)
    'image_sim_weak': 0.82,     # 추가 신호 있을 때 묶기
    'title_sim': 0.65,          # 이전 0.70 → 0.65
    'color_min_sim': 0.60,      # 색상 너무 다르면 분리 (안전장치)
}

CLUSTER_THRESHOLDS_ACCESSORY = {
    'image_sim_strong': 0.85,   # 공격적: 조명/각도로 같은 상품 잘 분리됨
    'image_sim_weak': 0.75,
    'title_sim': 0.60,          # 모델코드 + 브랜드면 충분
    'color_min_sim': 0.55,
}


def cluster_similar_products_v2(
    products: list[dict],
    is_accessory: bool = False,
) -> list[list[dict]]:
    """이미지 + 모델코드 + 제목 + 색상 종합 클러스터링.

    카테고리별 임계값 자동 적용:
    - 의류: 보수적 (image_sim_strong 0.90, title 0.65)
    - 액세서리/가방: 공격적 (image_sim_strong 0.85, title 0.60)
    """
    thresholds = (
        CLUSTER_THRESHOLDS_ACCESSORY if is_accessory
        else CLUSTER_THRESHOLDS_CLOTHING
    )
    img_strong = thresholds['image_sim_strong']
    img_weak = thresholds['image_sim_weak']
    title_th = thresholds['title_sim']
    color_min = thresholds['color_min_sim']

    clusters: list[list[dict]] = []
    used: set[int] = set()

    for i, p in enumerate(products):
        if i in used:
            continue
        cluster = [p]
        used.add(i)
        p_emb = p.get('_image_emb')
        p_hist = p.get('_color_hist')
        p_codes = set(extract_model_codes(p.get('title', '')))

        for j, q in enumerate(products[i + 1:], start=i + 1):
            if j in used:
                continue

            # 1. 모델코드 일치 → 절대 동일 (색상 검증 없이)
            q_codes = set(extract_model_codes(q.get('title', '')))
            if p_codes and (p_codes & q_codes):
                cluster.append(q)
                used.add(j)
                continue

            # 2. 색상 검증 (둘 다 히스토그램 있을 때만)
            q_hist = q.get('_color_hist')
            color_ok = True
            if p_hist is not None and q_hist is not None:
                from src.ranking.color_hist import color_similarity
                if color_similarity(p_hist, q_hist) < color_min:
                    color_ok = False

            if not color_ok:
                continue

            # 3. 이미지 임베딩 강한 유사 (단독)
            q_emb = q.get('_image_emb')
            if p_emb is not None and q_emb is not None:
                img_sim = float(np.dot(p_emb, q_emb))
                if img_sim >= img_strong:
                    cluster.append(q)
                    used.add(j)
                    continue

                # 4. 이미지 약한 유사 + 제목 유사
                title_sim = title_similarity(p.get('title', ''), q.get('title', ''))
                if img_sim >= img_weak and title_sim >= title_th:
                    cluster.append(q)
                    used.add(j)
                    continue

            # 5. fallback: 제목 + 같은 브랜드/판매처
            title_sim = title_similarity(p.get('title', ''), q.get('title', ''))
            same_brand = (
                p.get('brand') and p['brand'] == q.get('brand')
            ) or (
                p.get('mall_name') and p['mall_name'] == q.get('mall_name')
                and title_sim >= 0.85
            )
            if title_sim >= title_th and same_brand:
                cluster.append(q)
                used.add(j)

        clusters.append(cluster)

    return clusters


def lowest_price_per_cluster(clusters: list[list[dict]]) -> list[dict]:
    """클러스터별 최저가 1개 + 다른 판매처 메타 추가.

    반환 상품 dict에 추가 필드:
        _cluster_size: 같은 상품을 파는 판매처 수
        _other_sellers: [{mall_name, price, link, product_id}, ...]
        _min_price: 최저가
        _max_price: 최고가
    """
    result = []
    for cluster in clusters:
        if not cluster:
            continue

        priced = [c for c in cluster if c.get('price') and c.get('price', 0) > 0]
        if not priced:
            cheapest = cluster[0]
            cheapest['_cluster_size'] = len(cluster)
            cheapest['_other_sellers'] = []
            result.append(cheapest)
            continue

        priced_sorted = sorted(priced, key=lambda x: x.get('price', 999_999_999))
        cheapest = priced_sorted[0]

        prices = [p.get('price', 0) for p in priced_sorted]
        cheapest['_cluster_size'] = len(cluster)
        cheapest['_min_price'] = min(prices)
        cheapest['_max_price'] = max(prices)
        cheapest['_other_sellers'] = [
            {
                'mall_name': c.get('mall_name', ''),
                'price': c.get('price'),
                'link': c.get('link', ''),
                'product_id': c.get('product_id', ''),
            }
            for c in priced_sorted[1:]
        ]
        result.append(cheapest)

    return result
