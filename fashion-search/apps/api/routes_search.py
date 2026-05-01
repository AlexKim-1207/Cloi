"""v3 검색 엔드포인트 — 탭별 query embedding + 카테고리별 랭킹 + 4분면 소팅.

파이프라인:
    1. 이미지 bytes 해시 → 캐시 확인
    2. 병렬: Gemini 멀티아이템 탐지 + FashionCLIP 속성 추출 + Gemini bbox 탐지
    3. bbox 결과로 detected_items 보강 (누락 액세서리 복구)
    4. 탭별 query embedding 분리 (각 탭의 의류 crop 임베딩 사용)
    5. detected_items별 네이버 병렬 검색 (multi-query + dedupe + fallback)
    6. 탭별: 의류(시각65%+색상30%+Naver5%) / 잡화(시각60%+무드10%+가격25%+Naver5%)
    7. SKU 클러스터링 v2 (카테고리별 임계값 + 색상 안전장치) + 4분면 소팅 + GCS 스냅샷

엔드포인트:
    POST /api/search            — 이미지 업로드 (multipart/form-data)
    POST /api/click             — 클릭 이벤트 기록 (JSON body)
    GET  /api/popular           — 인기 TOP 10
"""
import asyncio
import hashlib
import logging
import time
import uuid
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
from src.logging.search_logger import (
    get_popular_items,
    log_click,
    log_click_v2,
    log_impressions,
    log_search,
    mark_impression_clicked,
)
from src.pricing.normalize import cluster_similar_products_v2, lowest_price_per_cluster
from src.ranking.color_hist import compute_color_histogram
from src.ranking.mood_ranker import rank_clothing_products, rank_accessory_products
from src.ranking.mood_to_price import estimate_price_range_from_mood, is_accessory_tab
from src.ranking.quadrant_sort import quadrant_sort
from src.search.parallel_search import search_all_items_v3
from src.storage.user_image_store import UserImageStore

from .schemas import ClickRequest, OtherSeller, PopularItem, ProductCard, SearchResponse, TabSection

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

# Fix B5-2: bbox label → tab_id 매핑
_BBOX_TO_TAB: dict[str, str] = {
    'top_outer': 'top_outer',
    'top_inner': 'top_inner',
    'outer': 'outer',
    'bottom': 'bottom',
    'dress': 'dress',
    'shoes': 'shoes',
    'bag': 'bag',
    'accessory_ring': 'accessory_ring',
    'accessory_necklace': 'accessory_necklace',
    'accessory_earring': 'accessory_earring',
    'accessory_belt': 'accessory_belt',
    'accessory_hat': 'accessory_hat',
    'accessory_watch': 'accessory_watch',
}

_FALLBACK_QUERIES: dict[str, list[str]] = {
    'bag': ['{style} 가방', '{style} 숄더백', '{style} 토트백'],
    'shoes': ['{style} 신발', '{style} 스니커즈', '{style} 로퍼'],
    'accessory_ring': ['{style} 반지', '데일리 반지', '미니멀 반지'],
    'accessory_necklace': ['{style} 목걸이', '미니멀 목걸이', '데일리 목걸이'],
    'accessory_earring': ['{style} 귀걸이', '미니멀 귀걸이'],
    'accessory_belt': ['{style} 벨트', '여성 벨트'],
    'accessory_hat': ['{style} 모자', '버킷햇', '캡모자'],
    'accessory_watch': ['{style} 시계', '여성 시계'],
    'top_inner': ['{style} 이너', '베이직 티셔츠', '크롭 탑'],
    'top_outer': ['{style} 셔츠', '{style} 카디건'],
    'outer': ['{style} 자켓', '{style} 코트'],
    'bottom': ['{style} 바지', '{style} 스커트'],
    'dress': ['{style} 원피스'],
}


def _augment_detected_items_from_bbox(style_ctx, detection):
    """gemini_detector의 bbox 결과로 style_analyzer의 detected_items 보강.

    bbox에는 있지만 detected_items에는 없는 탭 발견 시,
    fallback 검색쿼리와 함께 자동 추가.
    """
    if detection is None or not detection.boxes:
        return style_ctx

    from src.llm.schemas import DetectedItem

    existing_tabs = {item.tab_id for item in style_ctx.detected_items}

    bbox_tabs: set[str] = set()
    for box in detection.boxes:
        if getattr(box, 'label', '') == 'face':
            continue
        tab_id = _BBOX_TO_TAB.get(box.label)
        if tab_id and tab_id not in existing_tabs:
            bbox_tabs.add(tab_id)

    style_label = style_ctx.overall_style_context or '캐주얼'

    for tab_id in bbox_tabs:
        templates = _FALLBACK_QUERIES.get(tab_id, [f'{tab_id} 추천'])
        queries = [t.format(style=style_label) for t in templates]
        new_item = DetectedItem(
            tab_id=tab_id,
            category=tab_id,
            subcategory=tab_id,
            description=f'(자동보강) bbox 탐지: {tab_id}',
            is_inner=(tab_id == 'top_inner'),
            searchQueries=queries,
        )
        style_ctx.detected_items.append(new_item)
        logger.info(
            "[routes_search] bbox 보강: %s 탭 추가 (style_analyzer 누락)",
            tab_id,
        )

    return style_ctx


async def _download_thumbnail(client: httpx.AsyncClient, url: str) -> Optional[Image.Image]:
    if not url:
        return None
    try:
        r = await client.get(url, timeout=5.0)
        r.raise_for_status()
        return Image.open(BytesIO(r.content)).convert("RGB")
    except Exception:
        return None


async def _calc_clip_embeddings_and_hists(
    embedder,
    products: list[dict],
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray], dict[str, np.ndarray]]:
    """썸네일 다운로드 → FashionCLIP 임베딩 + HSV 히스토그램 + dominant color 동시 계산."""
    if not products or embedder is None:
        return {}, {}, {}

    async with httpx.AsyncClient() as client:
        thumbnails = await asyncio.gather(
            *[_download_thumbnail(client, p.get("image_url", "")) for p in products]
        )

    valid_pairs = [(p, t) for p, t in zip(products, thumbnails) if t is not None]
    if not valid_pairs:
        return {}, {}, {}

    valid_products, valid_images = zip(*valid_pairs)
    product_vecs: np.ndarray = await asyncio.to_thread(embedder.embed, list(valid_images))

    embs: dict[str, np.ndarray] = {}
    hists: dict[str, np.ndarray] = {}
    for p, vec, img in zip(valid_products, product_vecs, valid_images):
        pid = p.get("product_id", "")
        embs[pid] = vec
        hists[pid] = compute_color_histogram(img)

    return embs, hists, {}  # dominants: 빈 dict (Fix 10-2: K-means 비활성화)


async def _build_per_tab_query_embs(
    embedder,
    pil_image: Image.Image,
    detection,
    detected_items,
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray], dict[str, Optional[np.ndarray]]]:
    """탭별 query embedding + HSV color histogram + dominant color 생성.

    Returns:
        (tab_id → query_emb, tab_id → query_color_hist, tab_id → query_dominant)
    """
    if embedder is None:
        zeros = np.zeros(512)
        empty_hist = np.zeros(192)  # 12*4*4 HSV bins
        return (
            {item.tab_id: zeros for item in detected_items},
            {item.tab_id: empty_hist for item in detected_items},
            {item.tab_id: None for item in detected_items},
        )

    fallback_emb = await asyncio.to_thread(embedder.embed_single, pil_image)
    fallback_hist = compute_color_histogram(pil_image)

    if detection is None or not detection.boxes:
        return (
            {item.tab_id: fallback_emb for item in detected_items},
            {item.tab_id: fallback_hist for item in detected_items},
            {item.tab_id: None for item in detected_items},
        )

    try:
        from src.preprocess.gemini_detector import blur_face_regions, crop_garment_regions
        from src.preprocess.tab_mapper import map_tab_to_label

        masked_image = blur_face_regions(pil_image, detection.boxes)
        garment_crops = crop_garment_regions(masked_image, detection.boxes)

        if not garment_crops:
            return (
                {item.tab_id: fallback_emb for item in detected_items},
                {item.tab_id: fallback_hist for item in detected_items},
                {item.tab_id: None for item in detected_items},
            )

        crop_labels = list(garment_crops.keys())
        crop_images = list(garment_crops.values())
        crop_embs = await asyncio.to_thread(embedder.embed, crop_images)

        label_to_emb: dict[str, np.ndarray] = {}
        label_to_hist: dict[str, np.ndarray] = {}
        for label, emb, crop_img in zip(crop_labels, crop_embs, crop_images):
            norm = np.linalg.norm(emb) + 1e-8
            label_to_emb[label] = emb / norm
            label_to_hist[label] = compute_color_histogram(crop_img)
            # Fix 10-2: dominant 비활성화 — K-means 호출 제거

        result_embs: dict[str, np.ndarray] = {}
        result_hists: dict[str, np.ndarray] = {}
        result_doms: dict[str, Optional[np.ndarray]] = {}
        for item in detected_items:
            tab_id = item.tab_id
            label = map_tab_to_label(tab_id, label_to_emb.keys())
            result_embs[tab_id] = label_to_emb.get(label, fallback_emb) if label else fallback_emb
            result_hists[tab_id] = label_to_hist.get(label, fallback_hist) if label else fallback_hist
            result_doms[tab_id] = None  # Fix 10-2: dominants 비활성화

        return result_embs, result_hists, result_doms

    except Exception as exc:
        logger.warning("[routes_search] per-tab emb 생성 실패, fallback: %s", exc)
        return (
            {item.tab_id: fallback_emb for item in detected_items},
            {item.tab_id: fallback_hist for item in detected_items},
            {item.tab_id: None for item in detected_items},
        )


def _sort_tabs(tabs: list[TabSection], sort_by: str) -> list[TabSection]:
    if sort_by in ('relevance', 'quadrant'):
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
        'neckline': '',
        'fit': '',
        'mood_confidence': 0.5,
    }


async def _safe_detect_regions(image_bytes: bytes, mime: str):
    """detect_regions의 안전 wrapper — 실패 시 None 반환."""
    try:
        from src.preprocess.gemini_detector import detect_regions
        return await detect_regions(image_bytes, mime_type=mime)
    except Exception as exc:
        logger.warning("[routes_search] Gemini detect 실패: %s", exc)
        return None


@router.post("/search", response_model=SearchResponse)
async def search(
    request: Request,
    file: UploadFile = File(...),
    sort_by: str = 'quadrant',
) -> SearchResponse:
    """패션 이미지 → 탭별 쿼리 임베딩 + 카테고리별 랭킹 → 4분면 소팅."""
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

    # 2. 캐시 확인
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

    # 4. 병렬: analyze_style + attribute_classifier + Gemini bbox detect
    try:
        attr_coro = (
            asyncio.to_thread(attribute_classifier.classify_all, pil_image)
            if attribute_classifier
            else _dummy_attributes()
        )
        style_ctx, attributes, detection = await asyncio.gather(
            analyze_style(image_bytes, mime_type=mime),
            attr_coro,
            _safe_detect_regions(image_bytes, mime),
        )
    except Exception as exc:
        logger.error("[routes_search] 분석 실패: %s", exc)
        raise HTTPException(status_code=502, detail="스타일 분석 서비스에 일시적인 오류가 발생했습니다.")

    if not style_ctx.detected_items:
        raise HTTPException(
            status_code=422,
            detail="의류/잡화 아이템을 감지할 수 없습니다. 패션 이미지를 업로드해 주세요.",
        )

    # Fix B5-2: bbox 결과로 detected_items 보강 (누락 액세서리 복구)
    style_ctx = _augment_detected_items_from_bbox(style_ctx, detection)

    # 5. 탭별 query embedding + color histogram + dominant (탭마다 해당 의류 crop 사용)
    query_embs_by_tab, query_hists_by_tab, query_doms_by_tab = await _build_per_tab_query_embs(
        embedder, pil_image, detection, style_ctx.detected_items
    )

    # 6. mood 텍스트 임베딩
    mood_label: str = attributes.get('mood', 'casual street style daily')
    if embedder is not None:
        mood_text_emb: np.ndarray = await asyncio.to_thread(
            embedder.encode_text, [mood_label]
        )
        if mood_text_emb.ndim > 1:
            mood_text_emb = mood_text_emb[0]
    else:
        first_emb = next(iter(query_embs_by_tab.values()), np.zeros(512))
        mood_text_emb = first_emb

    # 7. detected_items별 병렬 네이버 검색
    raw_results = await search_all_items_v3(style_ctx.detected_items)

    # 8. 탭별: 썸네일 임베딩 + 색상 히스토그램 + dominant 병렬 계산
    tab_products = {
        item.tab_id: raw_results.get(item.tab_id, [])
        for item in style_ctx.detected_items
        if raw_results.get(item.tab_id)
    }

    emb_tasks = {
        tab_id: _calc_clip_embeddings_and_hists(embedder, prods)
        for tab_id, prods in tab_products.items()
    }
    product_embs_by_tab: dict[str, dict[str, np.ndarray]] = {}
    product_hists_by_tab: dict[str, dict[str, np.ndarray]] = {}
    product_doms_by_tab: dict[str, dict[str, np.ndarray]] = {}
    if emb_tasks:
        tab_ids = list(emb_tasks.keys())
        results_list = await asyncio.gather(*emb_tasks.values(), return_exceptions=True)
        for tid, r in zip(tab_ids, results_list):
            if not isinstance(r, Exception):
                embs, hists, doms = r
                product_embs_by_tab[tid] = embs
                product_hists_by_tab[tid] = hists
                product_doms_by_tab[tid] = doms
            else:
                product_embs_by_tab[tid] = {}
                product_hists_by_tab[tid] = {}
                product_doms_by_tab[tid] = {}

    # 액세서리용 가격대 추정
    accessory_price_range = estimate_price_range_from_mood(mood_label)

    session_id = str(uuid.uuid4())
    tabs: list[TabSection] = []
    all_impression_products: list[dict] = []

    for item in style_ctx.detected_items:
        tab_id = item.tab_id
        products = raw_results.get(tab_id, [])
        if not products:
            continue

        product_image_embs = product_embs_by_tab.get(tab_id, {})
        product_color_hists = product_hists_by_tab.get(tab_id, {})
        product_dominant_colors = product_doms_by_tab.get(tab_id, {})
        query_emb = query_embs_by_tab.get(tab_id, np.zeros(512))
        query_color_hist = query_hists_by_tab.get(tab_id, np.zeros(192))
        query_dominant = query_doms_by_tab.get(tab_id)

        # Fix B7-2: _image_emb + _color_hist 주입 (SKU clustering용)
        for p in products:
            pid = p.get('product_id', '')
            if pid in product_image_embs:
                p['_image_emb'] = product_image_embs[pid]
            if pid in product_color_hists:
                p['_color_hist'] = product_color_hists[pid]

        # 카테고리별 랭킹
        if is_accessory_tab(tab_id):
            ranked_20 = rank_accessory_products(
                products, query_emb, product_image_embs,
                mood_text_emb, accessory_price_range,
            )[:20]
        else:
            ranked_20 = rank_clothing_products(
                products, query_emb, query_color_hist, query_dominant,
                product_image_embs, product_color_hists, product_dominant_colors,
            )[:20]

        # Fix B2: SKU 클러스터링 v2 — 카테고리별 임계값
        clusters = cluster_similar_products_v2(ranked_20, is_accessory=is_accessory_tab(tab_id))
        deduped = lowest_price_per_cluster(clusters)

        # 4분면 소팅 → top 5
        final_5 = quadrant_sort(deduped)[:5]

        for rank_pos, p in enumerate(final_5):
            all_impression_products.append({
                'product_id': p.get('product_id', ''),
                'tab_id': tab_id,
                'rank_position': rank_pos,
                '_visual_sim': p.get('_visual_sim', 0.0),
                '_mood_align': p.get('_mood_align', 0.0),
                'match_score': p.get('match_score', 0.0),
            })

        # Fix B4: ProductCard 빌드 — cluster 메타 + other_sellers
        product_cards = [
            ProductCard(
                id=p.get('product_id', ''),
                title=p.get('title', ''),
                image=p.get('image_url', ''),
                price=p.get('price'),
                link=p.get('link', ''),
                mall_name=p.get('platform', ''),
                match_score=round(p.get('match_score', 0.0), 4),
                visual_similarity=round(p.get('_visual_sim', 0.0), 4),
                mood_alignment=round(p.get('_mood_align', 0.0), 4),
                price_fit=round(p.get('_price_fit', 0.0), 4),
                naver_rank_score=round(p.get('_naver_rank', 0.0), 4),
                cluster_size=p.get('_cluster_size', 1),
                min_price=p.get('_min_price'),
                max_price=p.get('_max_price'),
                other_sellers=[
                    OtherSeller(**s) for s in p.get('_other_sellers', [])
                ],
            )
            for p in final_5
        ]

        tabs.append(TabSection(
            tab_id=tab_id,
            label=TAB_LABELS.get(tab_id, item.subcategory),
            description=item.description,
            items=product_cards,
        ))

    latency_ms = int((time.monotonic() - start) * 1000)

    # Fix B5-5: detected_items_meta — 디버깅용 탐지 결과 노출
    detected_items_meta = [
        {
            'tab_id': i.tab_id,
            'category': i.category,
            'description': (i.description or '')[:50],
            'has_naver_results': bool(raw_results.get(i.tab_id)),
            'naver_count': len(raw_results.get(i.tab_id, [])),
        }
        for i in style_ctx.detected_items
    ]

    response = SearchResponse(
        session_id=session_id,
        image_hash=image_hash,
        overall_style=style_ctx.overall_style_context,
        detected_attributes={
            'mood': mood_label,
            'neckline': attributes.get('neckline', ''),
            'fit': attributes.get('fit', ''),
        },
        tabs=tabs,
        total_latency_ms=latency_ms,
        cache_hit=False,
        detected_items_meta=detected_items_meta,
    )

    asyncio.create_task(log_impressions(session_id, image_hash, all_impression_products))

    asyncio.create_task(_user_image_store.save_async(
        image_bytes=image_bytes,
        image_hash=image_hash,
        style_context={'overall_style': style_ctx.overall_style_context},
        attributes=attributes,
    ))
    asyncio.create_task(_user_image_store.save_session_snapshot(
        image_hash=image_hash,
        session_id=session_id,
        products_shown=all_impression_products,
        query_attributes={
            'mood': mood_label,
            'overall_style': style_ctx.overall_style_context,
        },
    ))

    await log_search(image_hash, style_ctx, raw_results)
    await set_cached(image_hash, response.model_dump())

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
        session_id=body.session_id,
    )

    if body.session_id:
        await mark_impression_clicked(body.session_id, body.product_id)


@router.post("/search/{image_hash}/click/{product_id}", status_code=204)
async def record_click_legacy(image_hash: str, product_id: str, category: str = "") -> None:
    """클릭 이벤트 기록 (레거시 호환)."""
    await log_click(image_hash, product_id, category)


@router.get("/popular", response_model=list[PopularItem])
async def get_popular(category: str | None = None, limit: int = 10) -> list[PopularItem]:
    """클릭률 기준 인기 TOP N 상품 반환."""
    items = await get_popular_items(category=category, limit=limit)
    return [PopularItem(**item) for item in items]
