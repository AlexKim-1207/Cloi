"""Reranker 가중치 그리드 서치 (fashion_clip 기준).

Usage:
    python -m eval.tune_rerank

출력:
    최적 가중치 + Recall@10 표
    src/search/rerank.py 상수 자동 업데이트
"""
import itertools
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

import faiss
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eval.metrics import recall_at_k, reciprocal_rank
from src.embedding import get_embedder

ARTIFACTS = ROOT / "artifacts"
GT_PATH = ROOT / "eval" / "ground_truth.jsonl"
RERANK_PY = ROOT / "src" / "search" / "rerank.py"

# 고정 소수 가중치
W_FIT = 0.08
W_STYLE = 0.07
W_SHIPPING = 0.05
W_STOCK = 0.05
FIXED_REST = W_FIT + W_STYLE + W_SHIPPING + W_STOCK  # 0.25

W_SIM_GRID = [0.40, 0.55, 0.70, 0.85]
W_CAT_GRID = [0.05, 0.10, 0.15]
W_COLOR_GRID = [0.05, 0.10, 0.15]


def _load_index(name: str) -> faiss.Index:
    path = ARTIFACTS / f"{name}.faiss"
    with tempfile.TemporaryDirectory(prefix="faiss_") as tmp:
        dst = os.path.join(tmp, "tmp.faiss")
        shutil.copy2(str(path), dst)
        return faiss.read_index(dst)


def _load_meta(name: str) -> list[dict]:
    db = ARTIFACTS / f"{name}_meta.db"
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM catalog ORDER BY faiss_id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _search(index: faiss.Index, meta: list[dict], vec: np.ndarray, k: int = 50) -> list[dict]:
    v = vec.astype(np.float32)
    norm = np.linalg.norm(v)
    if norm > 0:
        v = v / norm
    dists, idxs = index.search(v.reshape(1, -1), k)
    results = []
    for dist, idx in zip(dists[0], idxs[0]):
        if 0 <= idx < len(meta):
            m = dict(meta[idx])
            m["score"] = float(dist)
            results.append(m)
    return results


def _match(a: str, b: str) -> float:
    if not a or not b:
        return 0.5
    return 1.0 if a.strip().lower() == b.strip().lower() else 0.0


def _apply_weights(candidates: list[dict], q_cat: str, q_color: str,
                   w_sim: float, w_cat: float, w_color: float) -> list[dict]:
    w_rest = 1.0 - w_sim - w_cat - w_color
    w_fit = w_rest * (W_FIT / FIXED_REST)
    w_style = w_rest * (W_STYLE / FIXED_REST)
    w_ship = w_rest * (W_SHIPPING / FIXED_REST)
    w_stock = w_rest * (W_STOCK / FIXED_REST)

    scored = []
    for c in candidates:
        sim = max(0.0, min(1.0, c["score"]))
        cat_s = _match(q_cat, c.get("category", ""))
        color_s = _match(q_color, c.get("color", ""))
        final = (w_sim * sim + w_cat * cat_s + w_color * color_s
                 + w_fit * 0.5 + w_style * 0.5 + w_ship * 0.5 + w_stock * 0.5)
        scored.append({**c, "final": final})
    scored.sort(key=lambda x: x["final"], reverse=True)
    return scored


def main() -> None:
    print("=== tune_rerank: fashion_clip 가중치 그리드 서치 ===")
    print("인덱스 로드 중...")
    index = _load_index("fashion_clip")
    meta = _load_meta("fashion_clip")
    print(f"FAISS ntotal={index.ntotal}, meta={len(meta)}")

    gt = []
    with open(GT_PATH, encoding="utf-8") as f:
        for line in f:
            gt.append(json.loads(line.strip()))
    print(f"GT 쿼리 수: {len(gt)}")

    print("임베더 로드 중...")
    embedder = get_embedder("fashion_clip")
    embedder.load()

    # 각 쿼리별 FAISS 검색 결과 캐시
    print("FAISS 검색 중...")
    query_candidates: list[tuple[dict, list[dict]]] = []
    for item in gt:
        img_path = item["query_path"]
        if not os.path.exists(img_path):
            # 상대경로 시도
            img_path = str(ROOT / img_path)
        try:
            img = Image.open(img_path).convert("RGB")
            emb = embedder.embed_single(img)
            cands = _search(index, meta, emb, k=50)
            query_candidates.append((item, cands))
        except Exception as e:
            print(f"  SKIP {item['query_id']}: {e}")

    print(f"유효 쿼리: {len(query_candidates)}")

    # 그리드 서치
    best_recall = -1.0
    best_combo = None
    results_table = []

    for w_sim, w_cat, w_color in itertools.product(W_SIM_GRID, W_CAT_GRID, W_COLOR_GRID):
        if w_sim + w_cat + w_color > 0.975:
            continue

        r10_sum = 0.0
        for item, cands in query_candidates:
            q_cat = item.get("category", "")
            q_color = item.get("color", "")
            scored = _apply_weights(cands, q_cat, q_color, w_sim, w_cat, w_color)
            pred_ids = [c["product_id"] for c in scored]
            r10_sum += recall_at_k(item["relevant_ids"], pred_ids, 10)

        recall = round(r10_sum / len(query_candidates), 4)
        results_table.append((w_sim, w_cat, w_color, recall))

        if recall > best_recall:
            best_recall = recall
            best_combo = (w_sim, w_cat, w_color)

    results_table.sort(key=lambda x: x[3], reverse=True)

    print("\n── 상위 10 조합 ──────────────────────────────")
    print(f"{'W_SIM':>6} {'W_CAT':>6} {'W_COLOR':>8} {'Recall@10':>10}")
    for row in results_table[:10]:
        marker = " ← 우승" if row[:3] == best_combo else ""
        print(f"{row[0]:>6.2f} {row[1]:>6.2f} {row[2]:>8.2f} {row[3]:>10.4f}{marker}")

    w_sim, w_cat, w_color = best_combo
    print(f"\n최적 가중치: W_SIM={w_sim}, W_CAT={w_cat}, W_COLOR={w_color}")
    print(f"Recall@10: {best_recall}")

    # rerank.py 자동 업데이트
    _update_rerank(w_sim, w_cat, w_color)
    print(f"\nsrc/search/rerank.py 업데이트 완료.")


def _update_rerank(w_sim: float, w_cat: float, w_color: float) -> None:
    text = RERANK_PY.read_text(encoding="utf-8")
    import re
    text = re.sub(r"^W_SIM\s*=\s*[\d.]+", f"W_SIM = {w_sim}", text, flags=re.MULTILINE)
    text = re.sub(r"^W_CAT\s*=\s*[\d.]+", f"W_CAT = {w_cat}", text, flags=re.MULTILINE)
    text = re.sub(r"^W_COLOR\s*=\s*[\d.]+", f"W_COLOR = {w_color}", text, flags=re.MULTILINE)
    RERANK_PY.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
