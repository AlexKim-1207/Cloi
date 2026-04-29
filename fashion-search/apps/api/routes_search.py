"""v2 검색 엔드포인트 — Gemini 스타일 분석 → 네이버쇼핑 병렬 검색 → CLIP 필터.

파이프라인:
    1. 이미지 bytes 해시 → 캐시 확인 (HIT: 즉시 반환)
    2. Gemini 2.5 Flash: 이미지 전체 → StyleContext JSON
    3. 네이버쇼핑 API: 아이템별 asyncio.gather 병렬 검색
    4. CLIP: 유저 이미지 vs 상품 썸네일 유사도 → 카테고리별 TOP 5
    5. 검색 로그 저장 + 캐시 저장 + JSON 반환

엔드포인트:
    POST /api/search                     — 이미지 업로드 (multipart/form-data)
    POST /api/search/{hash}/click/{id}   — 클릭 이벤트 기록
    GET  /api/popular                    — 인기 TOP 10
"""
import hashlib
import logging
import time
from io import BytesIO

from fastapi import APIRouter, File, HTTPException, UploadFile
from PIL import Image

_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB
_ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}

from src.cache.result_cache import get_cached, set_cached
from src.llm.style_analyzer import analyze_style
from src.logging.search_logger import get_popular_items, log_click, log_search
from src.ranking.clip_filter import rank_all_categories
from src.search.parallel_search import search_all_items

from .schemas import PopularItem, ProductCard, SearchResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/search", response_model=SearchResponse)
async def search(file: UploadFile = File(...)) -> SearchResponse:
    """패션 이미지 업로드 → 스타일 분석 → 아이템별 쇼핑 추천."""
    start = time.monotonic()

    # ── 1. 이미지 읽기 + 해시 ─────────────────────────────────────────────────
    mime = file.content_type or "image/jpeg"
    if mime not in _ALLOWED_MIME:
        raise HTTPException(status_code=415, detail=f"지원하지 않는 파일 형식: {mime}")

    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")
    if len(image_bytes) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="파일이 너무 큽니다. 10MB 이하로 업로드해 주세요.")

    image_hash = hashlib.sha256(image_bytes).hexdigest()

    # ── 2. 캐시 확인 ──────────────────────────────────────────────────────────
    cached = await get_cached(image_hash)
    if cached:
        latency_ms = int((time.monotonic() - start) * 1000)
        cached["cached"] = True
        cached["latency_ms"] = latency_ms
        logger.info("[routes_search] 캐시 HIT — latency=%dms", latency_ms)
        return SearchResponse(**cached)

    # ── 3. PIL 이미지 변환 (CLIP용) ───────────────────────────────────────────
    try:
        pil_image = Image.open(BytesIO(image_bytes)).convert("RGB")
    except Exception:
        raise HTTPException(status_code=400, detail="이미지 디코딩 실패")

    # ── 4. Gemini 스타일 분석 ─────────────────────────────────────────────────
    try:
        style_context = await analyze_style(image_bytes, mime_type=mime)
    except Exception as exc:
        logger.error("[routes_search] Gemini 분석 실패: %s", exc)
        raise HTTPException(status_code=502, detail="스타일 분석 서비스에 일시적인 오류가 발생했습니다.")

    if not style_context.items:
        raise HTTPException(
            status_code=422,
            detail="의류/잡화 아이템을 감지할 수 없습니다. 패션 이미지를 업로드해 주세요.",
        )

    # ── 5. 네이버쇼핑 병렬 검색 ──────────────────────────────────────────────
    raw_results = await search_all_items(style_context)

    # ── 6. CLIP 유사도 필터 (카테고리별 TOP 5) ────────────────────────────────
    ranked_results = await rank_all_categories(pil_image, raw_results)

    # ── 7. ProductCard 변환 ───────────────────────────────────────────────────
    product_cards: dict[str, list[ProductCard]] = {
        category: [ProductCard(**item) for item in items]
        for category, items in ranked_results.items()
        if items
    }

    latency_ms = int((time.monotonic() - start) * 1000)
    response = SearchResponse(
        style_context=style_context,
        results=product_cards,
        cached=False,
        latency_ms=latency_ms,
    )

    # ── 8. 로그 + 캐시 저장 ──────────────────────────────────────────────────
    await log_search(image_hash, style_context, ranked_results)
    await set_cached(image_hash, response.model_dump())

    logger.info(
        "[routes_search] 완료 — style=%s, categories=%d, latency=%dms",
        style_context.overall_style,
        len(product_cards),
        latency_ms,
    )
    return response


@router.post("/search/{image_hash}/click/{product_id}", status_code=204)
async def record_click(image_hash: str, product_id: str, category: str = "") -> None:
    """상품 클릭 이벤트 기록 (CTR 집계용)."""
    await log_click(image_hash, product_id, category)


@router.get("/popular", response_model=list[PopularItem])
async def get_popular(category: str | None = None, limit: int = 10) -> list[PopularItem]:
    """클릭률 기준 인기 TOP N 상품 반환."""
    items = await get_popular_items(category=category, limit=limit)
    return [PopularItem(**item) for item in items]
