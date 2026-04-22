"""검색 엔드포인트 — /search (병렬 FAISS + Gemini 파이프라인).

파이프라인:
    1. 이미지 bytes 디코딩
    2. SHA256 캐시 확인 → hit 시 즉시 반환
    3. Vision 파이프라인: Grounding DINO → SAM2 crop
    4. 각 crop에 대해 asyncio.gather():
        a. OpenCLIP 임베딩 → FAISS top-50 검색
        b. Gemini 속성 추출 (confidence < 0.7 or sim < 0.75 일 때만)
    5. Reranker → top-20
    6. 결과 캐시 저장 + JSON 반환
"""
import asyncio
import base64
import logging
import time

from fastapi import APIRouter, HTTPException, Request

from src.cache.result_cache import get_cached_result, get_image_hash, set_cached_result
from src.config.settings import get_settings
from src.embedding.query_embed import embed_query_crop
from src.llm.gemini_extract import GarmentAttributes, extract_attributes
from src.search.rerank import rerank
from src.search.retrieve import search_similar
from src.vision.cropper import crop_to_bytes
from src.vision.pipeline import run_vision_pipeline

from .schemas import ProductResult, SearchRequest, SearchResponse

logger = logging.getLogger(__name__)
router = APIRouter()


async def _maybe_extract(
    image_bytes: bytes,
    top_score: float,
    confidence_threshold: float,
    sim_threshold: float = 0.75,
) -> GarmentAttributes | None:
    """조건부 Gemini 호출 (confidence 또는 FAISS 유사도가 낮을 때만)."""
    if top_score >= sim_threshold:
        logger.debug("[routes_search] FAISS 유사도 %.3f ≥ %.3f → Gemini 스킵", top_score, sim_threshold)
        return None
    logger.debug("[routes_search] FAISS 유사도 %.3f < %.3f → Gemini 호출", top_score, sim_threshold)
    return await extract_attributes(image_bytes, mime_type="image/jpeg")


@router.post("/search", response_model=SearchResponse)
async def search(request: Request, body: SearchRequest) -> SearchResponse:
    """패션 이미지 유사 상품 검색."""
    start_ts = time.perf_counter()
    settings = get_settings()

    # ── 1. 이미지 디코딩 ──────────────────────────────────────────────────────
    try:
        image_bytes = base64.b64decode(body.image_base64)
    except Exception:
        raise HTTPException(status_code=400, detail="이미지 base64 디코딩 실패")

    # ── 2. 캐시 확인 ──────────────────────────────────────────────────────────
    img_hash = get_image_hash(image_bytes)
    cached = get_cached_result(img_hash)
    if cached:
        latency = (time.perf_counter() - start_ts) * 1000
        cached["cached"] = True
        cached["latency_ms"] = round(latency, 1)
        logger.info("[routes_search] 캐시 HIT — latency=%.1fms", latency)
        return SearchResponse(**cached)

    # ── 3. FAISS 스토어 확인 ──────────────────────────────────────────────────
    app_state = getattr(request.app.state, "app_state", None)
    if app_state is None or app_state.faiss_store is None:
        raise HTTPException(
            status_code=503,
            detail="FAISS 인덱스가 로드되지 않았습니다. build_catalog_index.py 실행 후 재시작 필요.",
        )
    store = app_state.faiss_store

    # ── 4. Vision 파이프라인 ──────────────────────────────────────────────────
    crops = await run_vision_pipeline(image_bytes)
    if not crops:
        raise HTTPException(
            status_code=422,
            detail="의류를 감지할 수 없습니다. 의류가 포함된 이미지를 업로드해 주세요.",
        )

    all_results: list = []

    for crop in crops:
        crop_img = crop.crop_image

        # ── 5. asyncio.gather: 임베딩+FAISS 검색 & 조건부 Gemini ────────────
        crop_bytes = crop_to_bytes(crop_img)
        query_vec = embed_query_crop(crop_img)

        # FAISS 검색 먼저 (await, 동기 blocking 없이)
        candidates = await search_similar(query_vec, store, k=settings.faiss_top_k)
        top_score = candidates[0].score if candidates else 0.0

        # Gemini 조건부 호출 (유사도 낮으면)
        query_attrs = await _maybe_extract(
            crop_bytes,
            top_score,
            settings.gemini_confidence_threshold,
        )

        # ── 6. Reranker ────────────────────────────────────────────────────
        ranked = rerank(candidates, query_attrs, top_n=body.top_k)
        all_results.extend(ranked)

    # 여러 crop이 있을 경우 재정렬 + 중복 제거
    seen: set[str] = set()
    deduped = []
    for r in sorted(all_results, key=lambda x: x.final_score, reverse=True):
        if r.product_id not in seen:
            seen.add(r.product_id)
            deduped.append(r)
        if len(deduped) >= body.top_k:
            break

    # ── 7. ProductResult 변환 ─────────────────────────────────────────────
    product_results = [
        ProductResult(
            product_id=r.product_id,
            image_url=r.meta.get("image_url", ""),
            name=r.meta.get("name", r.product_id),
            brand=r.meta.get("brand", ""),
            price=int(r.meta.get("price", 0)),
            category=r.meta.get("category", ""),
            shop_url=r.meta.get("shop_url", ""),
            vector_similarity=round(r.vector_similarity, 4),
            final_score=r.final_score,
        )
        for r in deduped
    ]

    latency = (time.perf_counter() - start_ts) * 1000
    response = SearchResponse(
        results=product_results,
        total=len(product_results),
        cached=False,
        latency_ms=round(latency, 1),
    )

    # ── 8. 결과 캐시 저장 ─────────────────────────────────────────────────
    set_cached_result(img_hash, response.model_dump())

    logger.info(
        "[routes_search] 완료 — crops=%d, results=%d, latency=%.1fms",
        len(crops),
        len(product_results),
        latency,
    )
    return response
