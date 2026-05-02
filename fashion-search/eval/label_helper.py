"""Gold set labeling helper.

API 호출 → top-20 product_id/title 출력 → draft labels.jsonl 생성.
사람이 label 0/1/2 직접 채워야 함 (2=same_sku, 1=acceptable, 0=wrong).

Usage:
    cd fashion-search
    python eval/label_helper.py --out eval/gold_set/labels.jsonl
    # → draft 생성 (모든 label=0, product_id 채워짐)
    # → 사람이 label 수정 후 regression_test.py 실행
"""
from __future__ import annotations
import argparse
import json
import sys
import time
from pathlib import Path

import requests

GOLD_QUERIES = Path(__file__).parent / "gold_set" / "queries"
API_URL = "https://cloi.pages.dev/api/analyze"


def call_api(img_path: Path) -> list[dict]:
    try:
        with open(img_path, "rb") as f:
            resp = requests.post(
                API_URL,
                files={"file": (img_path.name, f, "image/jpeg")},
                timeout=90,
            )
        resp.raise_for_status()
        data = resp.json()
        products = []
        for tab_data in (data.get("categories") or {}).values():
            for item in (tab_data or {}).get("products") or []:
                pid = str(item.get("productId") or item.get("product_id") or "")
                title = str(item.get("title") or item.get("name") or "")
                if pid and pid not in {p["product_id"] for p in products}:
                    products.append({"product_id": pid, "title": title})
        return products[:20]
    except Exception as e:
        print(f"  ERROR {img_path.name}: {e}", file=sys.stderr)
        return []


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="eval/gold_set/labels.jsonl")
    parser.add_argument("--start", type=int, default=1, help="Start from query N")
    parser.add_argument("--end", type=int, default=50, help="End at query N")
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    existing: dict[str, dict] = {}
    if out_path.exists():
        with open(out_path) as f:
            for line in f:
                item = json.loads(line.strip())
                existing[item["query_id"]] = item

    imgs = sorted(GOLD_QUERIES.glob("*.jpg"))
    imgs = [p for p in imgs if args.start <= int(p.stem[1:]) <= args.end]
    print(f"Processing {len(imgs)} queries ({args.start}~{args.end})...")

    with open(out_path, "a") as out_f:
        for i, img in enumerate(imgs):
            qid = img.stem
            if qid in existing:
                print(f"  SKIP {qid} (already labeled)")
                continue

            print(f"\n[{i+1}/{len(imgs)}] {qid}")
            products = call_api(img)
            if not products:
                print(f"  SKIP {qid} (API returned 0 results)")
                continue

            for j, p in enumerate(products):
                print(f"  {j+1:2d}. [{p['product_id']}] {p['title'][:60]}")

            candidates = [{"product_id": p["product_id"], "label": 0} for p in products]
            row = {"query_id": qid, "candidates": candidates}
            out_f.write(json.dumps(row, ensure_ascii=False) + "\n")
            out_f.flush()
            time.sleep(1.5)

    print(f"\nDraft saved: {out_path}")
    print("Next: open labels.jsonl, set label=2 (same SKU), 1 (acceptable), 0 (wrong)")
    print("Then: python eval/regression_test.py")


if __name__ == "__main__":
    main()
