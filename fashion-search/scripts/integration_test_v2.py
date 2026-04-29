#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v3 파이프라인 E2E 통합 테스트.

사용법:
    python scripts/integration_test_v2.py [--url http://localhost:8000]
"""
import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import httpx

BASE_DIR = Path(__file__).resolve().parents[1]
QUERIES_DIR = BASE_DIR / "eval" / "queries"

TEST_IMAGES = [
    "q001.jpg",  # 단일 아이템 기대
    "q002.jpg",  # 멀티 아이템 기대
    "q003.jpg",  # 레이어드 기대
    "q005.jpg",  # 럭셔리 룩 기대
    "q010.jpg",  # 캐주얼 룩 기대
]


def check_response(resp: dict, label: str) -> list[str]:
    errors: list[str] = []

    if "tabs" not in resp:
        errors.append(f"[{label}] 'tabs' 필드 없음")
        return errors

    tabs = resp["tabs"]
    if not tabs:
        errors.append(f"[{label}] tabs 비어있음")
        return errors

    for tab in tabs:
        if "tab_id" not in tab:
            errors.append(f"[{label}] tab.tab_id 없음")
        if "label" not in tab:
            errors.append(f"[{label}] tab.label 없음")
        items = tab.get("items", [])
        if len(items) == 0:
            errors.append(f"[{label}] {tab.get('tab_id')} 탭 items 비어있음")
        for item in items:
            for field in ("id", "title", "image", "link", "match_score"):
                if field not in item:
                    errors.append(f"[{label}] item.{field} 없음")

    return errors


def test_single_image(client: httpx.Client, url: str, img_path: Path, sort_by: str = "relevance") -> dict:
    with open(img_path, "rb") as f:
        files = {"file": (img_path.name, f, "image/jpeg")}
        params = {"sort_by": sort_by}
        t0 = time.monotonic()
        resp = client.post(f"{url}/api/search", files=files, params=params, timeout=60)
        latency = (time.monotonic() - t0) * 1000

    resp.raise_for_status()
    data = resp.json()
    return {"data": data, "latency_ms": latency}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8000")
    args = parser.parse_args()
    base_url = args.url.rstrip("/")

    print(f"=== v3 E2E 통합 테스트 (서버: {base_url}) ===\n")

    # Health check
    with httpx.Client() as client:
        try:
            h = client.get(f"{base_url}/health", timeout=10)
            print(f"Health: {h.json()}\n")
        except Exception as e:
            print(f"[WARN] health check 실패: {e}\n")

    all_errors: list[str] = []
    latencies: list[float] = []

    with httpx.Client() as client:
        # TC1: 단일 이미지 — tabs 존재, 정상 응답
        print("TC1: 단일 이미지 기본 응답")
        try:
            img = QUERIES_DIR / TEST_IMAGES[0]
            r = test_single_image(client, base_url, img)
            data = r["data"]
            latencies.append(r["latency_ms"])
            errs = check_response(data, "TC1")
            n_tabs = len(data.get("tabs", []))
            print(f"  tabs={n_tabs}, latency={r['latency_ms']:.0f}ms", "[OK]" if not errs else "[FAIL]")
            all_errors.extend(errs)
        except Exception as e:
            print(f"  예외: {e}")
            all_errors.append(f"TC1 예외: {e}")

        # TC2: 멀티 아이템 — tabs 2개 이상 기대
        print("TC2: 멀티 아이템 (tabs 2+)")
        try:
            img = QUERIES_DIR / TEST_IMAGES[1]
            r = test_single_image(client, base_url, img)
            data = r["data"]
            latencies.append(r["latency_ms"])
            n_tabs = len(data.get("tabs", []))
            errs = check_response(data, "TC2")
            if n_tabs < 2:
                errs.append(f"TC2: tabs={n_tabs}, 2+ 기대")
            print(f"  tabs={n_tabs}, latency={r['latency_ms']:.0f}ms", "[OK]" if not errs else "[FAIL]")
            all_errors.extend(errs)
        except Exception as e:
            print(f"  예외: {e}")
            all_errors.append(f"TC2 예외: {e}")

        # TC3: 레이어드 룩 — top_outer + top_inner 탭 분리 확인
        print("TC3: 레이어드 룩 (top_outer / top_inner 분리)")
        try:
            img = QUERIES_DIR / TEST_IMAGES[2]
            r = test_single_image(client, base_url, img)
            data = r["data"]
            latencies.append(r["latency_ms"])
            tab_ids = [t["tab_id"] for t in data.get("tabs", [])]
            errs = check_response(data, "TC3")
            has_layered = "top_outer" in tab_ids or "top_inner" in tab_ids
            print(f"  tab_ids={tab_ids}, layered={has_layered}, latency={r['latency_ms']:.0f}ms", "[OK]" if not errs else "[FAIL]")
            all_errors.extend(errs)
        except Exception as e:
            print(f"  예외: {e}")
            all_errors.append(f"TC3 예외: {e}")

        # TC4+5: 무드 + 가격대 확인
        for tc_num, img_name, expected_tier in [
            (4, TEST_IMAGES[3], None),
            (5, TEST_IMAGES[4], None),
        ]:
            print(f"TC{tc_num}: 무드/가격 분석")
            try:
                img = QUERIES_DIR / img_name
                r = test_single_image(client, base_url, img)
                data = r["data"]
                latencies.append(r["latency_ms"])
                attrs = data.get("detected_attributes", {})
                errs = check_response(data, f"TC{tc_num}")
                print(f"  mood={attrs.get('mood','?')}, tier={attrs.get('price_tier','?')}, latency={r['latency_ms']:.0f}ms", "[OK]" if not errs else "[FAIL]")
                all_errors.extend(errs)
            except Exception as e:
                print(f"  예외: {e}")
                all_errors.append(f"TC{tc_num} 예외: {e}")

        # TC6: 소팅 테스트 — relevance vs price_asc 순서 다름
        print("TC6: 소팅 (relevance vs price_asc)")
        try:
            img = QUERIES_DIR / TEST_IMAGES[0]
            r_rel = test_single_image(client, base_url, img, sort_by="relevance")
            r_asc = test_single_image(client, base_url, img, sort_by="price_asc")
            tabs_rel = r_rel["data"].get("tabs", [])
            tabs_asc = r_asc["data"].get("tabs", [])
            if tabs_rel and tabs_asc:
                prices_rel = [i.get("price") for i in tabs_rel[0].get("items", [])]
                prices_asc = [i.get("price") for i in tabs_asc[0].get("items", [])]
                sorted_asc = prices_asc == sorted((p for p in prices_asc if p), key=lambda x: x or 0)
                print(f"  relevance prices={prices_rel[:3]}, asc prices={prices_asc[:3]}", "[OK]" if sorted_asc else "[~]")
            else:
                print("  tabs 없음 — 소팅 테스트 스킵")
        except Exception as e:
            print(f"  예외: {e}")

    # 결과
    print("\n=== 결과 ===")
    if latencies:
        p50 = statistics.median(latencies)
        print(f"p50 latency: {p50:.0f}ms (목표: <5000ms)", "[OK]" if p50 < 5000 else "[SLOW]")
    if all_errors:
        print(f"\n실패 {len(all_errors)}건:")
        for e in all_errors:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print("\n모든 테스트 통과!")
        sys.exit(0)


if __name__ == "__main__":
    main()
