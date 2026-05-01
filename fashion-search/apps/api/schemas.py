from typing import Optional
from pydantic import BaseModel, Field

from src.llm.schemas import ItemDetail, StyleContext, DetectedItem, MultiItemStyleContext

__all__ = ["ItemDetail", "StyleContext", "DetectedItem", "MultiItemStyleContext"]


# ── v3 API 스키마 ──────────────────────────────────────────────────────────────

class ProductCard(BaseModel):
    id: str
    title: str
    image: str
    price: Optional[int] = None
    link: str
    mall_name: Optional[str] = None
    match_score: float = 0.0
    visual_similarity: float = 0.0
    mood_alignment: float = 0.0
    naver_rank_score: float = 0.0


class TabSection(BaseModel):
    tab_id: str
    label: str
    description: str
    items: list[ProductCard]


class SearchResponse(BaseModel):
    session_id: str = ""
    image_hash: str
    overall_style: str
    detected_attributes: dict
    tabs: list[TabSection]
    total_latency_ms: int
    cache_hit: bool = False


class ClickRequest(BaseModel):
    session_id: str = ""
    image_hash: str
    product_id: str
    category: str = ""
    product_title: str = ""
    product_image_url: str = ""
    product_price: int = 0
    final_score: float = 0.0
    rank_position: int = 0
    mood_label: str = ""


class PopularItem(BaseModel):
    category: str
    product_id: str
    title: str
    image_url: str
    search_count: int
    click_count: int
    ctr: float


# ── Admin 스키마 ───────────────────────────────────────────────────────────────

class CatalogAddRequest(BaseModel):
    image_base64: str
    mime_type: str = "image/jpeg"
    product_id: str
    name: str
    brand: str = ""
    price: int = 0
    category: str = ""
    shop_url: str = ""


class CatalogStatsResponse(BaseModel):
    total_products: int
    last_built_at: str | None
    index_size_mb: float


# ── 레거시 Phase 2 FAISS 스키마 ────────────────────────────────────────────────

class SearchRequest(BaseModel):
    image_base64: str = Field(..., description="base64 인코딩된 이미지 데이터")
    mime_type: str = Field(default="image/jpeg")
    top_k: int = Field(default=20, ge=1, le=50)
    contribute_to_catalog: bool = Field(default=False)


class ProductResult(BaseModel):
    product_id: str
    image_url: str = ""
    name: str = ""
    brand: str = ""
    price: int = 0
    category: str = ""
    shop_url: str = ""
    vector_similarity: float = 0.0
    final_score: float = 0.0
