from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    image_base64: str = Field(..., description="base64 인코딩된 이미지 데이터")
    mime_type: str = Field(default="image/jpeg", description="image/jpeg | image/png | image/webp")
    top_k: int = Field(default=20, ge=1, le=50)


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


class SearchResponse(BaseModel):
    results: list[ProductResult]
    total: int
    cached: bool = False
    latency_ms: float = 0.0


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
