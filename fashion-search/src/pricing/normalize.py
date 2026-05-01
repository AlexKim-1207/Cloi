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
        # fallback: 단순 토큰 오버랩
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
    """동일 SKU 추정 클러스터링.

    같은 클러스터 = 같은 디자인의 다른 판매처.
    클러스터 내부에서만 가격 비교.
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


def lowest_price_per_cluster(clusters: list[list[dict]]) -> list[dict]:
    """클러스터별 최저가 1개씩 선택 + 다른 판매처 메타."""
    result = []
    for cluster in clusters:
        cheapest = min(cluster, key=lambda x: x.get('price') or 999999999)
        cheapest['_cluster_size'] = len(cluster)
        cheapest['_other_sellers'] = [
            {'mall_name': c.get('mall_name'), 'price': c.get('price'), 'link': c.get('link')}
            for c in cluster if c is not cheapest
        ]
        result.append(cheapest)
    return result


_MODEL_CODE_RE = re.compile(r'\b([A-Z]{2,}-?\d{3,}[A-Z0-9\-]*)\b')


def extract_model_codes(title: str) -> list[str]:
    """제목에서 모델 코드 추출 (예: A-234, VB001 등)."""
    return _MODEL_CODE_RE.findall(title.upper())


def cluster_similar_products_v2(
    products: list[dict],
    title_threshold: float = 0.70,
    image_sim_threshold: float = 0.92,
) -> list[list[dict]]:
    """이미지 임베딩 + 제목 + 브랜드 종합 클러스터링.

    같은 상품을 다른 판매처가 올렸어도 묶임:
    1. 이미지 유사도 0.92+ → 동일 상품 거의 확정
    2. 모델코드 일치 → 동일 상품
    3. 제목 유사도 0.70+ AND 같은 브랜드/판매처 → 동일 상품
    """
    clusters: list[list[dict]] = []
    used: set[int] = set()

    for i, p in enumerate(products):
        if i in used:
            continue
        cluster = [p]
        used.add(i)
        p_emb = p.get('_image_emb')
        p_codes = set(extract_model_codes(p.get('title', '')))

        for j, q in enumerate(products[i + 1:], start=i + 1):
            if j in used:
                continue

            q_emb = q.get('_image_emb')
            if p_emb is not None and q_emb is not None:
                img_sim = float(np.dot(p_emb, q_emb))
                if img_sim >= image_sim_threshold:
                    cluster.append(q)
                    used.add(j)
                    continue

            q_codes = set(extract_model_codes(q.get('title', '')))
            if p_codes and (p_codes & q_codes):
                cluster.append(q)
                used.add(j)
                continue

            title_sim = title_similarity(p.get('title', ''), q.get('title', ''))
            same_brand = (
                p.get('brand') and p['brand'] == q.get('brand')
            ) or (
                p.get('mall_name') and p['mall_name'] == q.get('mall_name')
                and title_sim >= 0.85
            )
            if title_sim >= title_threshold and same_brand:
                cluster.append(q)
                used.add(j)

        clusters.append(cluster)

    return clusters
