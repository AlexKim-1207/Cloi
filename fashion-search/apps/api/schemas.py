from pydantic import BaseModel, Field

from src.llm.schemas import ItemDetail, StyleContext

__all__ = ["ItemDetail", "StyleContext"]


# ── v2 API 스키마 ──────────────────────────────────────────────────────────────

class ProductCard(BaseModel):
    product_id: str
    title: str
    price: int
    image_url: str
    link: str
    platform: str
    category: str
    similarity_score: float


class SearchResponse(BaseModel):
    style_context: StyleContext
    results: dict[str, list[ProductCard]]
    cached: bool
    latency_ms: int


class PopularItem(BaseModel):
    category: str
    product_id: str
    title: str
    image_url: str
    search_count: int
    click_count: int
    ctr: float


# ── Admin 스키마 (routes_admin.py) ─────────────────────────────────────────────

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
    """Phase 2 FAISS 파이프라인용 (base64 입력)."""
    image_base64: str = Field(..., description="base64 인코딩된 이미지 데이터")
    mime_type: str = Field(default="image/jpeg")
    top_k: int = Field(default=20, ge=1, le=50)
    contribute_to_catalog: bool = Field(default=False, description="True이면 검색 후 이미지를 카탈로그에 추가")


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
