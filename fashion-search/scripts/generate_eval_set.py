"""Ground truth 평가셋 생성.

catalog.jsonl에서 N개 샘플 → eval/queries/ 복사 + eval/ground_truth.jsonl 생성.

Usage:
    python -m scripts.generate_eval_set --n-queries 50
"""
import argparse
import json
import random
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config.settings import get_settings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-queries", type=int, default=50)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    settings = get_settings()
    catalog_dir = Path(settings.catalog_dir)
    eval_dir = ROOT / "eval"
    queries_dir = eval_dir / "queries"
    queries_dir.mkdir(parents=True, exist_ok=True)

    jsonl_path = catalog_dir / "catalog.jsonl"
    if not jsonl_path.exists():
        print(f"ERROR: {jsonl_path} 없음")
        sys.exit(1)

    records: list[dict] = []
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    print(f"카탈로그 로드: {len(records)}개")

    random.seed(args.seed)
    n = min(args.n_queries, len(records))
    query_indices = random.sample(range(len(records)), n)
    query_records = [records[i] for i in query_indices]

    gt_lines: list[dict] = []
    for i, qr in enumerate(query_records):
        query_id = f"q{i + 1:03d}"
        pid = qr["product_id"]

        # 같은 category+subcategory+color 기준 정답
        relevant_ids = [
            r["product_id"]
            for r in records
            if r["product_id"] != pid
            and r["category"] == qr["category"]
            and r["subcategory"] == qr["subcategory"]
            and r["color"] == qr["color"]
        ]

        # color 매칭 너무 좁으면 subcategory만으로 fallback
        if not relevant_ids:
            relevant_ids = [
                r["product_id"]
                for r in records
                if r["product_id"] != pid
                and r["category"] == qr["category"]
                and r["subcategory"] == qr["subcategory"]
            ]

        src = catalog_dir / f"{pid}.jpg"
        dst = queries_dir / f"{query_id}.jpg"
        if src.exists():
            shutil.copy2(str(src), str(dst))
        else:
            print(f"  [WARN] 이미지 없음: {src}")

        gt_lines.append(
            {
                "query_id": query_id,
                "query_path": str(dst),
                "product_id": pid,
                "relevant_ids": relevant_ids,
                "category": qr["category"],
                "subcategory": qr["subcategory"],
                "color": qr["color"],
            }
        )

    gt_path = eval_dir / "ground_truth.jsonl"
    with open(gt_path, "w", encoding="utf-8") as f:
        for gt in gt_lines:
            f.write(json.dumps(gt, ensure_ascii=False) + "\n")

    empty = sum(1 for g in gt_lines if not g["relevant_ids"])
    print(f"쿼리 {len(gt_lines)}개 생성 → {queries_dir}")
    print(f"Ground truth → {gt_path}")
    print(f"relevant_ids 빈 쿼리: {empty}/{len(gt_lines)}")


if __name__ == "__main__":
    main()
