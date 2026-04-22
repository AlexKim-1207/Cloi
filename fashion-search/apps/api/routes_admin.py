"""Admin 엔드포인트 — 카탈로그 관리.

엔드포인트:
    POST /admin/catalog/add     — 단일 상품 임베딩 + 인덱스 추가
    POST /admin/catalog/rebuild — 전체 인덱스 재빌드
    GET  /admin/catalog/stats   — 인덱스 통계
"""
import base64
import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from src.config.settings import get_settings
from src.embedding.openclip_embed import embed_images
from src.search.faiss_store import FAISSStore
from src.embedding.catalog_embed_job import build_embeddings

from .schemas import CatalogAddRequest, CatalogStatsResponse

import numpy as np
from PIL import Image
import io

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/catalog/add")
async def add_catalog_item(request: Request, body: CatalogAddRequest) -> dict:
    """단일 상품을 이미지 임베딩 후 FAISS 인덱스에 추가 (증분)."""
    app_state = getattr(request.app.state, "app_state", None)
    if app_state is None:
        raise HTTPException(status_code=503, detail="앱 상태 없음")

    # 이미지 디코딩
    try:
        image_bytes = base64.b64decode(body.image_base64)
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception:
        raise HTTPException(status_code=400, detail="이미지 디코딩 실패")

    # 임베딩
    vec = embed_images([image])[0]  # shape (D,)

    meta = {
        "product_id": body.product_id,
        "name": body.name,
        "brand": body.brand,
        "price": body.price,
        "category": body.category,
        "shop_url": body.shop_url,
        "path": "",
    }

    settings = get_settings()
    index_path = os.path.join(settings.artifacts_dir, "catalog.index")

    if app_state.faiss_store is None:
        # 인덱스 없음 → 새로 생성
        store = FAISSStore(dim=len(vec))
        store.build(vec.reshape(1, -1), [meta])
        app_state.faiss_store = store
    else:
        app_state.faiss_store.add(vec.reshape(1, -1), [meta])

    # 저장
    app_state.faiss_store.save(index_path)
    logger.info("[admin] 상품 추가 완료: %s (총 %d개)", body.product_id, app_state.faiss_store.size())

    return {"product_id": body.product_id, "total": app_state.faiss_store.size()}


@router.post("/catalog/rebuild")
async def rebuild_catalog(request: Request) -> dict:
    """카탈로그 전체 재빌드 (catalog_dir 기준)."""
    settings = get_settings()
    index_path = os.path.join(settings.artifacts_dir, "catalog.index")

    logger.info("[admin] 카탈로그 재빌드 시작...")
    vectors, meta = build_embeddings()

    if not meta:
        raise HTTPException(status_code=422, detail="임베딩 가능한 이미지가 없습니다.")

    store = FAISSStore(dim=vectors.shape[1])
    store.build(vectors, meta)
    store.save(index_path)

    # 앱 상태 갱신
    app_state = getattr(request.app.state, "app_state", None)
    if app_state:
        app_state.faiss_store = store

    logger.info("[admin] 재빌드 완료: %d개", store.size())
    return {"total": store.size(), "rebuilt_at": datetime.now(timezone.utc).isoformat()}


@router.get("/catalog/stats", response_model=CatalogStatsResponse)
async def catalog_stats(request: Request) -> CatalogStatsResponse:
    """FAISS 인덱스 통계."""
    settings = get_settings()
    app_state = getattr(request.app.state, "app_state", None)
    store = app_state.faiss_store if app_state else None

    index_path = os.path.join(settings.artifacts_dir, "catalog.index")
    index_size_mb = 0.0
    last_built_at = None

    if os.path.exists(index_path):
        index_size_mb = round(os.path.getsize(index_path) / 1024 / 1024, 2)
        mtime = os.path.getmtime(index_path)
        last_built_at = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()

    return CatalogStatsResponse(
        total_products=store.size() if store else 0,
        last_built_at=last_built_at,
        index_size_mb=index_size_mb,
    )
