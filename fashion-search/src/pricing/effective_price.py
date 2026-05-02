"""Effective price = base + shipping. SKU 클러스터별 최저가 계산.

MVP: lprice + shipping_fee 만 사용 (used/rental/cbshop exclude 필수).
확장: 제휴 판매처 피드 또는 seller page parser 추가 예정.
"""
from __future__ import annotations
from typing import Dict, Any, List


def compute_effective_price(product: Dict[str, Any]) -> int:
    base = int(product.get("lprice", 0) or 0)
    shipping = int(product.get("shipping_fee", 0) or 0)
    return base + shipping


def cluster_by_sku(products: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    """same_sku 기준 클러스터링. 나머지는 단독 클러스터."""
    from src.pricing.sku_matcher import sku_score

    clusters: List[List[Dict[str, Any]]] = []
    used: set[int] = set()
    for i, p in enumerate(products):
        if i in used:
            continue
        cluster = [p]
        used.add(i)
        for j, q in enumerate(products[i + 1:], start=i + 1):
            if j in used:
                continue
            if sku_score(p, q)["category"] == "same_sku":
                cluster.append(q)
                used.add(j)
        clusters.append(cluster)
    return clusters


def lowest_price_per_cluster(clusters: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """각 클러스터에서 effective price 최저 product + 판매처 메타 추가."""
    result: List[Dict[str, Any]] = []
    for cluster in clusters:
        for p in cluster:
            p["_effective_price"] = compute_effective_price(p)
        cheapest = min(cluster, key=lambda x: x["_effective_price"])
        cheapest["_cluster_size"] = len(cluster)
        cheapest["_min_price"] = min(p["_effective_price"] for p in cluster)
        cheapest["_max_price"] = max(p["_effective_price"] for p in cluster)
        cheapest["_other_sellers"] = [
            {
                "mall_name": p.get("mall_name"),
                "price": p["_effective_price"],
                "link": p.get("link"),
            }
            for p in cluster if p is not cheapest
        ]
        result.append(cheapest)
    return result
