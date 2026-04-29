"""HuggingFace ashraq/fashion-product-images-small -> 500장 시드 카탈로그.

Usage:
    python -m scripts.seed_catalog [--target 500]

출력:
    src/data/catalog/{product_id}.jpg
    src/data/catalog/catalog.jsonl
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config.settings import get_settings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=int, default=500)
    return parser.parse_args()


def stratified_sample(ds, target: int) -> list:
    bucket: dict[str, list] = defaultdict(list)
    for item in ds:
        key = (item.get("subCategory") or item.get("masterCategory") or "Unknown")
        bucket[key].append(item)

    selected = []
    n_cats = len(bucket)
    per_cat = max(1, target // n_cats)
    seen_ids: set = set()

    for items in bucket.values():
        for item in items[:per_cat]:
            pid = str(item.get("id", ""))
            if pid not in seen_ids:
                selected.append(item)
                seen_ids.add(pid)

    # Fill remaining
    if len(selected) < target:
        for item in ds:
            if len(selected) >= target:
                break
            pid = str(item.get("id", ""))
            if pid not in seen_ids:
                selected.append(item)
                seen_ids.add(pid)

    return selected[:target]


def main() -> None:
    args = parse_args()
    settings = get_settings()

    catalog_dir = Path(settings.catalog_dir)
    catalog_dir.mkdir(parents=True, exist_ok=True)

    jsonl_path = catalog_dir / "catalog.jsonl"

    print("HuggingFace 데이터셋 로드 중 (ashraq/fashion-product-images-small)...")
    from datasets import load_dataset
    ds = load_dataset("ashraq/fashion-product-images-small", split="train")
    print(f"전체 데이터셋 크기: {len(ds)}")
    print(f"컬럼: {ds.column_names}")

    selected = stratified_sample(ds, args.target)
    print(f"stratified 샘플링 완료: {len(selected)}개")

    saved = 0
    skipped = 0

    with open(jsonl_path, "w", encoding="utf-8") as f:
        for item in selected:
            raw_id = item.get("id", "")
            pid_str = str(raw_id)
            product_id = f"p{int(pid_str):05d}" if pid_str.isdigit() else pid_str

            img = item.get("image")
            if img is None:
                skipped += 1
                continue

            img_path = catalog_dir / f"{product_id}.jpg"
            try:
                img.convert("RGB").save(str(img_path), "JPEG", quality=90)
            except Exception as e:
                print(f"저장 실패 {product_id}: {e}")
                skipped += 1
                continue

            record = {
                "product_id": product_id,
                "category": item.get("masterCategory", ""),
                "subcategory": item.get("subCategory", item.get("articleType", "")),
                "color": item.get("baseColour", ""),
                "gender": item.get("gender", ""),
                "name": item.get("productDisplayName", ""),
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            saved += 1

            if saved % 50 == 0:
                print(f"  진행: {saved}/{len(selected)}")

    print(f"\n완료: {saved}장 저장, {skipped}개 스킵")
    print(f"catalog.jsonl: {saved}줄")
    print(f"디렉토리: {catalog_dir}")


if __name__ == "__main__":
    main()
