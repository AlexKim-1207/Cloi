"""아이템별 asyncio.gather 병렬 검색."""
import asyncio
import logging

import httpx

from src.llm.schemas import DetectedItem, ItemDetail, StyleContext

from .naver_shopping import search_items

logger = logging.getLogger(__name__)


def build_search_query(style: StyleContext, item: ItemDetail) -> str:
    """쿼리 = overall_style + category + color + fit (있는 것만)."""
    parts = [style.overall_style, item.category]
    if item.color:
        parts.append(item.color)
    if item.fit:
        parts.append(item.fit)
    return " ".join(parts)


async def search_all_items(
    style: StyleContext,
    display: int | None = None,
) -> dict[str, list[dict]]:
    """아이템별 병렬 검색 → {category: [상품, ...]} 반환."""
    from src.config.settings import get_settings

    settings = get_settings()
    per_item = display or settings.search_results_per_item

    async with httpx.AsyncClient() as client:
        tasks = {
            item.category: search_items(
                client=client,
                query=build_search_query(style, item),
                category=item.category,
                display=per_item,
            )
            for item in style.items
        }

        results = await asyncio.gather(*tasks.values(), return_exceptions=True)

    output: dict[str, list[dict]] = {}
    for category, result in zip(tasks.keys(), results):
        if isinstance(result, Exception):
            logger.warning("[parallel_search] %s 검색 예외: %s", category, result)
            output[category] = []
        else:
            output[category] = result
            logger.debug("[parallel_search] %s: %d개", category, len(result))

    logger.info(
        "[parallel_search] 완료 — %d개 카테고리, 총 %d개 상품",
        len(output),
        sum(len(v) for v in output.values()),
    )
    return output


async def _naver_search_single(
    query: str,
    category: str,
    display: int = 40,
    exclude: str = 'used:rental:cbshop',
) -> list[dict]:
    """단일 쿼리 Naver Shopping API 호출 (exclude 옵션 지원)."""
    async with httpx.AsyncClient() as client:
        return await search_items(
            client=client,
            query=query,
            category=category,
            display=display,
            exclude=exclude,
        )


async def _execute_queries(
    queries: list[str],
    category: str,
    display: int,
    exclude: str,
) -> list[dict]:
    """쿼리 목록 병렬 실행 + dedupe."""
    tasks = [
        _naver_search_single(q, category=category, display=display, exclude=exclude)
        for q in queries
    ]
    all_results = await asyncio.gather(*tasks, return_exceptions=True)

    seen_ids: set[str] = set()
    merged: list[dict] = []
    for r in all_results:
        if isinstance(r, Exception):
            continue
        for p in r:
            pid = p.get('product_id', '') or p.get('link', '')
            if pid in seen_ids:
                continue
            seen_ids.add(pid)
            merged.append(p)
    return merged


async def _search_multi_query_dedupe(
    queries: list[str],
    category: str,
    display: int = 40,
    exclude: str = 'used:rental:cbshop',
) -> list[dict]:
    """3~5개 쿼리 병렬 검색 → productId 기반 dedupe. 0건 시 fallback 쿼리 시도."""
    merged = await _execute_queries(queries, category, display, exclude)
    if merged:
        return merged[:60]

    # 2차: 카테고리만으로 광범위 검색 (탭 살리기)
    fallback_queries = [category, f'여성 {category}', f'{category} 추천']
    logger.info(
        "[parallel_search] %s 검색 0건 → fallback 쿼리 시도: %s",
        category, fallback_queries,
    )
    merged = await _execute_queries(fallback_queries, category, display, exclude)
    return merged[:60]


async def search_all_items_v2(
    detected_items: list[DetectedItem],
) -> dict[str, list[dict]]:
    """멀티아이템 병렬 검색 → {tab_id: [상품, ...]} 반환 (v2, legacy)."""
    async with httpx.AsyncClient() as client:
        tasks = {
            item.tab_id: _search_for_item_legacy(client, item)
            for item in detected_items
        }
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)

    output: dict[str, list[dict]] = {}
    for tab_id, result in zip(tasks.keys(), results):
        if isinstance(result, Exception):
            logger.warning("[parallel_search_v2] %s 검색 예외: %s", tab_id, result)
            output[tab_id] = []
        else:
            output[tab_id] = result
            logger.debug("[parallel_search_v2] %s: %d개", tab_id, len(result))

    logger.info(
        "[parallel_search_v2] 완료 — %d개 탭, 총 %d개 상품",
        len(output),
        sum(len(v) for v in output.values()),
    )
    return output


async def _search_for_item_legacy(
    client: httpx.AsyncClient,
    item: DetectedItem,
    display_per_query: int = 20,
) -> list[dict]:
    """단일 DetectedItem — searchQueries별 검색 + 중복 제거 병합 (legacy)."""
    queries = item.searchQueries[:3]
    search_tasks = [
        search_items(client=client, query=q, category=item.category, display=display_per_query)
        for q in queries
    ]
    results = await asyncio.gather(*search_tasks, return_exceptions=True)

    seen_ids: set[str] = set()
    merged: list[dict] = []
    for r in results:
        if isinstance(r, Exception):
            continue
        for p in r:
            pid = p.get("product_id", "")
            if pid and pid not in seen_ids:
                seen_ids.add(pid)
                merged.append(p)
    return merged[:50]


async def search_all_items_v3(
    detected_items: list[DetectedItem],
) -> dict[str, list[dict]]:
    """탭별 multi-query union + dedupe + Naver 옵션 활용 (v3)."""
    tasks = {}
    for item in detected_items:
        queries = item.searchQueries[:5] if item.searchQueries else [item.subcategory or item.category]
        tasks[item.tab_id] = _search_multi_query_dedupe(
            queries,
            category=item.category,
            exclude='used:rental:cbshop',
        )

    tab_ids = list(tasks.keys())
    results_list = await asyncio.gather(*tasks.values(), return_exceptions=True)

    output: dict[str, list[dict]] = {}
    for tab_id, result in zip(tab_ids, results_list):
        if isinstance(result, Exception):
            logger.warning("[parallel_search_v3] %s 검색 예외: %s", tab_id, result)
            output[tab_id] = []
        else:
            output[tab_id] = result
            logger.debug("[parallel_search_v3] %s: %d개", tab_id, len(result))

    logger.info(
        "[parallel_search_v3] 완료 — %d개 탭, 총 %d개 상품",
        len(output),
        sum(len(v) for v in output.values()),
    )
    return output
