"""한국 패션 상품명 정규화 + SKU 매칭."""
import re

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
    """클러스터별 최저가 1개씩 선택."""
    result = []
    for cluster in clusters:
        cheapest = min(cluster, key=lambda x: x.get('price') or 999999999)
        cheapest['_cluster_size'] = len(cluster)
        result.append(cheapest)
    return result
