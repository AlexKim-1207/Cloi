"""SKU matching — model code + brand + title similarity.

보고서 추천 score weights:
- model_code exact: 0.35
- brand/maker exact: 0.15 each
- normalized title sim: 0.20
- image sim: 0.15
- option overlap: 0.10
- productType confidence: 0.05
"""
from __future__ import annotations
import re
from typing import Dict, Any, List

from rapidfuzz import fuzz

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
    (r"\b(차콜|먹색)\b", "charcoal"),
]

MODEL_CODE_RE = re.compile(r"\b[A-Z0-9]{2,}[-_/]?[A-Z0-9]{2,}\b")
TOKEN_RE = re.compile(r"[a-zA-Z0-9_가-힣]+")


def normalize_title(title: str) -> str:
    s = title.lower()
    s = re.sub(r"<[^>]+>", " ", s)
    for pat, rep in REPLACERS:
        s = re.sub(pat, rep, s, flags=re.IGNORECASE)
    tokens = [t for t in TOKEN_RE.findall(s) if t not in STOPWORDS]
    return " ".join(tokens)


def extract_model_codes(text: str) -> List[str]:
    return list(set(MODEL_CODE_RE.findall(text.upper())))


def title_similarity(a: str, b: str) -> float:
    return fuzz.token_set_ratio(normalize_title(a), normalize_title(b)) / 100.0


def sku_score(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    """SKU 일치 점수 + 분류.

    Returns: {score, category: 'same_sku' | 'same_design' | 'similar_item'}
    """
    score = 0.0

    if a.get("brand") and a.get("brand") == b.get("brand"):
        score += 0.15
    if a.get("maker") and a.get("maker") == b.get("maker"):
        score += 0.15

    a_codes = set(extract_model_codes(a.get("title", "")))
    b_codes = set(extract_model_codes(b.get("title", "")))
    if a_codes and (a_codes & b_codes):
        score += 0.35

    score += 0.20 * title_similarity(a.get("title", ""), b.get("title", ""))
    score += 0.15 * float(b.get("img_sim", 0.0))

    if score >= 0.70:
        category = "same_sku"
    elif score >= 0.50:
        category = "same_design"
    else:
        category = "similar_item"

    return {"score": min(score, 1.0), "category": category}
