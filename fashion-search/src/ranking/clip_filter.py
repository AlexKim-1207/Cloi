"""CLIP 유사도 기반 상품 필터링 + 카테고리별 TOP-K 추출.

기존 src/embedding/openclip_embed.py 모델 싱글턴 재사용 —
lifespan에서 load_clip_model()이 이미 호출되어 있음.
"""
import asyncio
import logging
from io import BytesIO

import httpx
import numpy as np
from PIL import Image

from src.config.settings import get_settings
from src.embedding.openclip_embed import embed_images, embed_single

logger = logging.getLogger(__name__)


async def _download_thumbnail(
    client: httpx.AsyncClient,
    url: str,
) -> Image.Image | None:
    """썸네일 URL → PIL Image (실패 시 None)."""
    if not url:
        return None
    try:
        r = await client.get(url, timeout=5.0)
        r.raise_for_status()
        return Image.open(BytesIO(r.content)).convert("RGB")
    except Exception:
        return None


async def filter_by_similarity(
    query_vector: np.ndarray,
    products: list[dict],
    top_k: int = 5,
    min_similarity: float = 0.20,
) -> list[dict]:
    """유저 이미지 벡터 vs 각 상품 썸네일 코사인 유사도.

    - min_similarity 미만 상품 제거 (무드 부적합)
    - 유사도 내림차순 정렬 후 top_k 반환
    """
    if not products:
        return []

    async with httpx.AsyncClient() as client:
        thumbnails = await asyncio.gather(
            *[_download_thumbnail(client, p.get("image_url", "")) for p in products]
        )

    valid_pairs: list[tuple[dict, Image.Image]] = [
        (p, t) for p, t in zip(products, thumbnails) if t is not None
    ]
    if not valid_pairs:
        return []

    valid_products, valid_images = zip(*valid_pairs)

    # 배치 임베딩 (GPU/CPU 최적화)
    product_vectors = embed_images(list(valid_images))

    scored: list[dict] = []
    for product, pvec in zip(valid_products, product_vectors):
        similarity = float(np.dot(query_vector, pvec))
        if similarity >= min_similarity:
            scored.append({**product, "similarity_score": round(similarity, 4)})

    scored.sort(key=lambda x: x["similarity_score"], reverse=True)
    return scored[:top_k]


async def rank_all_categories(
    query_image: Image.Image,
    search_results: dict[str, list[dict]],
    top_k: int | None = None,
    min_similarity: float | None = None,
) -> dict[str, list[dict]]:
    """카테고리별 CLIP 필터링.

    쿼리 이미지는 1번만 인코딩, 각 카테고리 필터링은 병렬 실행.
    """
    settings = get_settings()
    k = top_k or settings.top_k_per_category
    threshold = min_similarity if min_similarity is not None else settings.clip_min_similarity

    # 쿼리 이미지 1회 인코딩
    query_vector = embed_single(query_image.convert("RGB"))

    # 카테고리별 병렬 필터링
    tasks = {
        category: filter_by_similarity(query_vector, products, top_k=k, min_similarity=threshold)
        for category, products in search_results.items()
        if products
    }

    if not tasks:
        return {}

    results = await asyncio.gather(*tasks.values(), return_exceptions=True)

    output: dict[str, list[dict]] = {}
    for category, result in zip(tasks.keys(), results):
        if isinstance(result, Exception):
            logger.warning("[clip_filter] %s 필터링 예외: %s", category, result)
            output[category] = []
        else:
            output[category] = result
            logger.debug("[clip_filter] %s: %d개 → %d개", category, len(search_results[category]), len(result))

    total_before = sum(len(v) for v in search_results.values())
    total_after = sum(len(v) for v in output.values())
    logger.info("[clip_filter] 완료 — %d개 → %d개 (임계값=%.2f)", total_before, total_after, threshold)
    return output
