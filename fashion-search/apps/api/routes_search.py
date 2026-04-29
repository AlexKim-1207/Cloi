"""v3 검색 엔드포인트 — 멀티아이템 탐지 + FashionCLIP 속성추출 + 무드기반 소팅.

파이프라인:
    1. 이미지 bytes 해시 → 캐시 확인
    2. 병렬: Gemini 멀티아이템 탐지 + FashionCLIP 속성 추출
    3. detected_items별 네이버 병렬 검색 (searchQueries 활용)
    4. 탭별: CLIP 유사도 + mood_ranker 복합 소팅
    5. fire-and-forget GCS 저장 + 캐시 저장 + JSON 반환

엔드포인트:
    POST /api/search            — 이미지 업로드 (multipart/form-data)
    POST /api/click             — 클릭 이벤트 기록 (JSON body)
    GET  /api/popular           — 인기 TOP 10
"""
import asyncio
import hashlib
import logging
import time
from io import BytesIO
from typing import Optional

import httpx
import numpy as np
from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from PIL import Image

_MAX_UPLOAD_BYTES = 10 * 1024 * 1024
_ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}

from src.cache.result_cache import get_cached, set_cached
from src.llm.style_analyzer import analyze_style
from src.logging.search_logger import get_popular_items, log_click, log_click_v2, log_search
from src.ranking.mood_ranker import rank_products
from src.search.parallel_search import search_all_items_v2
from src.storage.user_image_store import UserImageStore

from .schemas import ClickRequest, PopularItem, ProductCard, SearchResponse, TabSection

logger = logging.getLogger(__name__)
router = APIRouter()

TAB_LABELS: dict[str, str] = {
    'top_outer': '아우터/상의',
    'top_inner': '이너',
    'outer': '아우터',
    'bottom': '하의',
    'dress': '원피스',
    'shoes': '신발',
    'bag': '가방',
    'accessory_ring': '반지',
    'accessory_necklace': '목걸이',
    'accessory_earring': '귀걸이',
    'accessory_belt': '벨트',
    'accessory_hat': '모자',
    'accessory_watch': '시계',
}

_user_image_store = UserImageStore()


async def _download_thumbnail(client: httpx.AsyncClient, url: str) -> Optional[Image.Image]:
    if not url:
        return None
    try:
        r = await client.get(url, timeout=5.0)
        r.raise_for_status()
        return Image.open(BytesIO(r.content)).convert("RGB")
    except Exception:
        return None


async def _calc_clip_scores(
    embedder,
    query_image: Image.Image,
    products: list[dict],
) -> dict[str, float]:
    """FashionCLIP query vs 상품 썸네일 코사인 유사도."""
    if not products or embedder is None:
        return {}

    query_vec: np.ndarray = await asyncio.to_thread(embedder.embed_single, query_image)

    async with httpx.AsyncClient() as client:
        thumbnails = await asyncio.gather(
            *[_download_thumbnail(client, p.get("image_url", "")) for p in products]
        )

    valid_pairs = [(p, t) for p, t in zip(products, thumbnails) if t is not None]
    if not valid_pairs:
        return {}

    valid_products, valid_images = zip(*valid_pairs)
    product_vecs: np.ndarray = await asyncio.to_thread(embedder.embed, list(valid_images))

    scores: dict[str, float] = {}
    for product, pvec in zip(valid_products, product_vecs):
        sim = float(np.dot(query_vec, pvec))
        scores[product.get("product_id", "")] = max(0.0, sim)

    return scores


def _sort_tabs(tabs: list[TabSection], sort_by: str) -> list[TabSection]:
    if sort_by == 'relevance':
        return tabs

    def _sort_items(items: list[ProductCard]) -> list[ProductCard]:
        if sort_by == 'price_asc':
            return sorted(items, key=lambda x: (x.price if x.price else 999999999, -x.match_score))
        elif sort_by == 'price_desc':
            return sorted(items, key=lambda x: (-(x.price if x.price else 0), -x.match_score))
        return items

    return [
        TabSection(
            tab_id=t.tab_id, label=t.label, description=t.description,
            items=_sort_items(t.items),
        )
        for t in tabs
    ]


async def _dummy_attributes() -> dict:
    return {
        'mood': 'casual street style daily',
        'price_tier': 'budget',
        'price_range': (10000, 60000),
        'neckline': '',
        'fit': '',
        'mood_confidence': 0.5,
    }


@router.post("/search", response_model=SearchResponse)
async def search(
    request: Request,
    file: UploadFile = File(...),
    sort_by: str = 'relevance',
) -> SearchResponse:
    """패션 이미지 → 멀티아이템 탐지 → 탭별 추천."""
    start = time.monotonic()
    app_state = request.app.state.app_state
    embedder = app_state.embedder
    attribute_classifier = app_state.attribute_classifier

    # 1. 이미지 읽기 + 해시
    mime = file.content_type or "image/jpeg"
    if mime not in _ALLOWED_MIME:
        raise HTTPException(status_code=415, detail=f"지원하지 않는 파일 형식: {mime}")

    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")
    if len(image_bytes) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="파일이 너무 큽니다. 10MB 이하로 업로드해 주세요.")

    image_hash = hashlib.sha256(image_bytes).hexdigest()

    # 2. 캐시 확인 (sort_by 무관 — 캐시 후 재정렬)
    cached = await get_cached(image_hash)
    if cached:
        latency_ms = int((time.monotonic() - start) * 1000)
        cached["cache_hit"] = True
        cached["total_latency_ms"] = latency_ms
        resp = SearchResponse(**cached)
        resp.tabs = _sort_tabs(resp.tabs, sort_by)
        logger.info("[routes_search] 캐시 HIT — latency=%dms", latency_ms)
        return resp

    # 3. PIL 이미지
    try:
        pil_image = Image.open(BytesIO(image_bytes)).convert("RGB")
    except Exception:
        raise HTTPException(status_code=400, detail="이미지 디코딩 실패")

    # 4. 병렬: Gemini 멀티아이템 탐지 + FashionCLIP 속성 추출
    try:
        attr_coro = (
            asyncio.to_thread(attribute_classifier.classify_all, pil_image)
            if attribute_classifier
            else _dummy_attributes()
        )
        style_ctx, attributes = await asyncio.gather(
            analyze_style(image_bytes, mime_type=mime),
            attr_coro,
        )
    except Exception as exc:
        logger.error("[routes_search] 분석 실패: %s", exc)
        raise HTTPException(status_code=502, detail="스타일 분석 서비스에 일시적인 오류가 발생했습니다.")

    if not style_ctx.detected_items:
        raise HTTPException(
            status_code=422,
            detail="의류/잡화 아이템을 감지할 수 없습니다. 패션 이미지를 업로드해 주세요.",
        )

    # 5. detected_items별 병렬 네이버 검색
    raw_results = await search_all_items_v2(style_ctx.detected_items)

    # 6. 탭별: CLIP 유사도 + 무드 랭킹
    mood_label: str = attributes.get('mood', 'casual street style daily')
    price_range: tuple = tuple(attributes.get('price_range', (10000, 60000)))

    # 탭별 clip_score 병렬 계산
    tab_products = {
        item.tab_id: raw_results.get(item.tab_id, [])
        for item in style_ctx.detected_items
        if raw_results.get(item.tab_id)
    }

    clip_score_tasks = {
        tab_id: _calc_clip_scores(embedder, pil_image, prods)
        for tab_id, prods in tab_products.items()
    }
    clip_scores_by_tab: dict[str, dict[str, float]] = {}
    if clip_score_tasks:
        tab_ids = list(clip_score_tasks.keys())
        results_list = await asyncio.gather(*clip_score_tasks.values(), return_exceptions=True)
        for tid, r in zip(tab_ids, results_list):
            clip_scores_by_tab[tid] = r if not isinstance(r, Exception) else {}

    tabs: list[TabSection] = []
    for item in style_ctx.detected_items:
        tab_id = item.tab_id
        products = raw_results.get(tab_id, [])
        if not products:
            continue

        clip_scores = clip_scores_by_tab.get(tab_id, {})
        ranked = rank_products(
            products, clip_scores, mood_label, price_range, sort_by='relevance'
        )[:5]

        product_cards = [
            ProductCard(
                id=p.get('product_id', ''),
                title=p.get('title', ''),
                image=p.get('image_url', ''),
                price=p.get('price'),
                link=p.get('link', ''),
                mall_name=p.get('platform', ''),
                match_score=round(p.get('match_score', 0.0), 4),
                clip_similarity=round(p.get('_clip_sim', 0.0), 4),
                mood_match=round(p.get('_mood_match', 0.0), 4),
                price_fit=round(p.get('_price_fit', 0.0), 4),
            )
            for p in ranked
        ]

        tabs.append(TabSection(
            tab_id=tab_id,
            label=TAB_LABELS.get(tab_id, item.subcategory),
            description=item.description,
            items=product_cards,
        ))

    latency_ms = int((time.monotonic() - start) * 1000)
    response = SearchResponse(
        image_hash=image_hash,
        overall_style=style_ctx.overall_style_context,
        detected_attributes={
            'mood': mood_label,
            'price_tier': attributes.get('price_tier', ''),
            'price_range': list(price_range),
            'neckline': attributes.get('neckline', ''),
            'fit': attributes.get('fit', ''),
        },
        tabs=tabs,
        total_latency_ms=latency_ms,
        cache_hit=False,
    )

    # 7. GCS 저장 (fire-and-forget)
    asyncio.create_task(_user_image_store.save_async(
        image_bytes=image_bytes,
        image_hash=image_hash,
        style_context={'overall_style': style_ctx.overall_style_context},
        attributes=attributes,
    ))

    # 8. 캐시 저장 (relevance 순서로)
    await log_search(image_hash, style_ctx, raw_results)
    await set_cached(image_hash, response.model_dump())

    # sort_by 적용 후 반환
    response.tabs = _sort_tabs(response.tabs, sort_by)

    logger.info("[routes_search] 완료 — tabs=%d, latency=%dms", len(tabs), latency_ms)
    return response


@router.post("/click", status_code=204)
async def record_click_v2(body: ClickRequest) -> None:
    """클릭 이벤트 기록 (v3 — 풍부한 데이터 수집)."""
    await log_click_v2(
        image_hash=body.image_hash,
        product_id=body.product_id,
        category=body.category,
        product_title=body.product_title,
        product_image_url=body.product_image_url,
        product_price=body.product_price,
        final_score=body.final_score,
        rank_position=body.rank_position,
        mood_label=body.mood_label,
        price_tier=body.price_tier,
    )


@router.post("/search/{image_hash}/click/{product_id}", status_code=204)
async def record_click_legacy(image_hash: str, product_id: str, category: str = "") -> None:
    """클릭 이벤트 기록 (레거시 호환)."""
    await log_click(image_hash, product_id, category)


@router.get("/popular", response_model=list[PopularItem])
async def get_popular(category: str | None = None, limit: int = 10) -> list[PopularItem]:
    """클릭률 기준 인기 TOP N 상품 반환."""
    items = await get_popular_items(category=category, limit=limit)
    return [PopularItem(**item) for item in items]
