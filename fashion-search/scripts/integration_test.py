"""Cloud Run 통합 테스트 — 5장 이미지 검색 결과 + latency 검증.

Usage:
    FASHION_SEARCH_URL=https://... python -m scripts.integration_test
    python -m scripts.integration_test --url http://localhost:8080
"""
import argparse
import os
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def _pick_images(n: int = 5) -> list[Path]:
    catalog = ROOT / "src" / "data" / "catalog"
    imgs = sorted(catalog.glob("*.jpg"))[:n]
    return imgs


def run_test(base_url: str) -> None:
    base_url = base_url.rstrip("/")
    client = httpx.Client(timeout=30)

    print(f"=== Integration Test: {base_url} ===\n")

    # 1. Health check
    r = client.get(f"{base_url}/health")
    assert r.status_code == 200, f"Health failed: {r.status_code}"
    print(f"[health] {r.json()}\n")

    # 2. Image search tests
    images = _pick_images(5)
    if not images:
        print("이미지 없음 — src/data/catalog/*.jpg 필요")
        return

    latencies = []
    for img_path in images:
        with open(img_path, "rb") as f:
            img_bytes = f.read()

        import base64
        img_b64 = base64.b64encode(img_bytes).decode()

        t0 = time.perf_counter()
        r = client.post(
            f"{base_url}/api/search",
            json={"image_b64": img_b64, "top_k": 10},
            timeout=30,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000
        latencies.append(elapsed_ms)

        status = r.status_code
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        n_results = len(body.get("results", body.get("items", [])))
        print(f"[{img_path.name}] status={status}, results={n_results}, latency={elapsed_ms:.0f}ms")

    if latencies:
        p50 = sorted(latencies)[len(latencies) // 2]
        print(f"\np50={p50:.0f}ms  max={max(latencies):.0f}ms  min={min(latencies):.0f}ms")

    print("\n=== 완료 ===")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=os.environ.get("FASHION_SEARCH_URL", "http://localhost:8080"))
    args = parser.parse_args()
    run_test(args.url)


if __name__ == "__main__":
    main()
