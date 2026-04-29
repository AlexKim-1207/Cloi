"""Gemini 스타일 분석 출력 스키마."""
from pydantic import BaseModel


class ItemDetail(BaseModel):
    category: str
    color: str | None = None
    fit: str | None = None
    material: str | None = None


class StyleContext(BaseModel):
    overall_style: str
    mood_tags: list[str]
    items: list[ItemDetail]
    confidence: float


# ── v3: 멀티아이템 탐지 스키마 ───────────────────────────────────────────────────

class DetectedItem(BaseModel):
    tab_id: str
    category: str
    subcategory: str
    description: str
    is_inner: bool
    searchQueries: list[str]


class MultiItemStyleContext(BaseModel):
    overall_style_context: str
    detected_items: list[DetectedItem]
