"""A/B eval runner — 임베더별 Recall@10, MRR, latency 측정.

Usage:
    python -m eval.runner --embedder openclip_vitl14 --skip-vision
    python -m eval.runner --embedder fashion_clip --skip-vision
    python -m eval.runner --embedder marqo_fashion_siglip --skip-vision
"""
import argparse
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

import faiss
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eval.metrics import evaluate
from src.config.settings import get_settings
from src.embedding import get_embedder


def _load_faiss(faiss_path: Path) -> faiss.Index:
    """Windows non-ASCII 경로 우회 — ASCII 임시 경로 경유."""
    with tempfile.TemporaryDirectory(prefix="faiss_") as tmp:
        tmp_index = os.path.join(tmp, "tmp.faiss")
        shutil.copy2(str(faiss_path), tmp_index)
        index = faiss.read_index(tmp_index)
    return index


def _load_meta(db_path: Path) -> list[dict]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM catalog ORDER BY faiss_id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _search(
    index: faiss.Index,
    meta: list[dict],
    embedding: np.ndarray,
    k: int = 50,
) -> list[dict]:
    vec = embedding.astype(np.float32)
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    distances, indices = index.search(vec.reshape(1, -1), k)
    results = []
    for dist, idx in zip(distances[0], indices[0]):
        if 0 <= idx < len(meta):
            m = dict(meta[idx])
            m["score"] = float(dist)
            results.append(m)
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--embedder",
        required=True,
        choices=["openclip_vitl14", "fashion_clip", "marqo_fashion_siglip"],
    )
    parser.add_argument("--gt", default=None)
    parser.add_argument("--skip-vision", action="store_true")
    parser.add_argument("--k", type=int, default=50)
    args = parser.parse_args()

    settings = get_settings()
    artifacts_dir = Path(settings.artifacts_dir)
    eval_dir = ROOT / "eval"
    results_dir = eval_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    gt_path = Path(args.gt) if args.gt else (eval_dir / "ground_truth.jsonl")
    if not gt_path.exists():
        print(f"ERROR: {gt_path} 없음 — generate_eval_set.py 먼저 실행")
        sys.exit(1)

    gt_records: list[dict] = []
    with open(gt_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                gt_records.append(json.loads(line))
    print(f"Ground truth 로드: {len(gt_records)}개")

    faiss_path = artifacts_dir / f"{args.embedder}.faiss"
    db_path = artifacts_dir / f"{args.embedder}_meta.db"

    print(f"FAISS 로드: {faiss_path}")
    index = _load_faiss(faiss_path)
    index.nprobe = 10
    print(f"  ntotal={index.ntotal}")

    meta = _load_meta(db_path)
    print(f"  meta rows={len(meta)}")

    print(f"임베더 로드: {args.embedder}")
    embedder = get_embedder(args.embedder)
    embedder.load()
    print(f"  dim={embedder.dim}")

    all_predictions: list[list[dict]] = []
    latencies_ms: list[float] = []

    for i, gt in enumerate(gt_records):
        img_path = Path(gt["query_path"])
        if not img_path.exists():
            print(f"  [WARN] 쿼리 이미지 없음: {img_path}")
            all_predictions.append([])
            latencies_ms.append(0.0)
            continue

        img = Image.open(str(img_path)).convert("RGB")

        t0 = time.perf_counter()
        embedding = embedder.embed_single(img)
        preds = _search(index, meta, embedding, k=args.k)
        t1 = time.perf_counter()

        latencies_ms.append((t1 - t0) * 1000.0)
        all_predictions.append(preds)

        if (i + 1) % 10 == 0:
            print(f"  진행: {i + 1}/{len(gt_records)}")

    gt_for_eval = [
        {"relevant_ids": g["relevant_ids"], "category": g["category"]}
        for g in gt_records
    ]
    result = evaluate(gt_for_eval, all_predictions)

    sorted_lat = sorted(latencies_ms)
    p50_ms = float(np.percentile(sorted_lat, 50)) if sorted_lat else 0.0
    p99_ms = float(np.percentile(sorted_lat, 99)) if sorted_lat else 0.0

    output = {
        "embedder": args.embedder,
        "recall_at_10": result.recall_at_10,
        "recall_at_50": result.recall_at_50,
        "mrr": result.mrr,
        "cat_prec_at_10": result.category_precision_at_10,
        "p50_ms": round(p50_ms, 1),
        "p99_ms": round(p99_ms, 1),
        "n_queries": result.n_queries,
        "timestamp": datetime.now().isoformat(),
    }

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = results_dir / f"{args.embedder}_{ts}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n=== {args.embedder} 결과 ===")
    print(f"  Recall@10 : {result.recall_at_10:.4f}")
    print(f"  Recall@50 : {result.recall_at_50:.4f}")
    print(f"  MRR       : {result.mrr:.4f}")
    print(f"  CatPrec@10: {result.category_precision_at_10:.4f}")
    print(f"  p50 latency: {p50_ms:.1f}ms")
    print(f"  p99 latency: {p99_ms:.1f}ms")
    print(f"\n저장: {out_path}")


if __name__ == "__main__":
    main()
