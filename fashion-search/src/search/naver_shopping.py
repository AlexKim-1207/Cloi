"""네이버쇼핑 API 단일 아이템 검색."""
import logging
import re

import httpx

from src.config.settings import get_settings

logger = logging.getLogger(__name__)

NAVER_SHOP_URL = "https://openapi.naver.com/v1/search/shop.json"

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    return _HTML_TAG_RE.sub("", text)


def _normalize_item(raw: dict, category: str) -> dict:
    """네이버쇼핑 응답 → ProductCard 호환 dict."""
    return {
        "product_id": raw.get("productId") or raw.get("mallProductId", ""),
        "title": _strip_html(raw.get("title", "")),
        "price": int(raw.get("lprice") or raw.get("hprice") or 0),
        "image_url": raw.get("image", ""),
        "link": raw.get("link", ""),
        "platform": raw.get("mallName", "네이버쇼핑"),
        "category": category,
        "similarity_score": 0.0,
    }


async def search_items(
    client: httpx.AsyncClient,
    query: str,
    category: str,
    display: int = 50,
    exclude: str = 'used:rental:cbshop',
) -> list[dict]:
    """네이버쇼핑 API 단일 쿼리 검색."""
    settings = get_settings()
    if not settings.naver_client_id or not settings.naver_client_secret:
        logger.warning("[naver_shopping] API 키 미설정 — 빈 결과 반환")
        return []

    try:
        params: dict = {"query": query, "display": display, "sort": "sim"}
        if exclude:
            params["exclude"] = exclude
        response = await client.get(
            NAVER_SHOP_URL,
            params=params,
            headers={
                "X-Naver-Client-Id": settings.naver_client_id,
                "X-Naver-Client-Secret": settings.naver_client_secret,
            },
            timeout=10.0,
        )
        response.raise_for_status()
        items = response.json().get("items", [])
        return [_normalize_item(item, category) for item in items]
    except Exception as exc:
        logger.warning("[naver_shopping] 검색 실패 (query=%s): %s", query, exc)
        return []
