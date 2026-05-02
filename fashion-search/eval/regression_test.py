"""Gold set 자동 회귀 평가.

PR마다 실행 → baseline 대비 5% 이상 regression 시 exit 1.
Usage: cd fashion-search && python eval/regression_test.py
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

import requests

GOLD_SET_FILE = Path(__file__).parent / "gold_set" / "labels.jsonl"
BASELINE_FILE = Path(__file__).parent / "results" / "baseline.json"
API_URL = "https://cloi.pages.dev/api/analyze"
SAMPLE_SIZE = 50  # 빠른 평가 — 전체 600개는 --full 플래그


def load_gold(sample: int = SAMPLE_SIZE) -> list[dict]:
    if not GOLD_SET_FILE.exists():
        print(f"SKIP: gold set 없음 ({GOLD_SET_FILE})")
        return []
    items = []
    with open(GOLD_SET_FILE) as f:
        for line in f:
            items.append(json.loads(line.strip()))
    return items[:sample]


def call_api(query_id: str) -> list[str]:
    """API 호출 후 product_id 리스트 반환."""
    img_path = Path(__file__).parent / "gold_set" / "queries" / f"{query_id}.jpg"
    if not img_path.exists():
        return []
    try:
        with open(img_path, "rb") as f:
            resp = requests.post(
                API_URL.replace("/analyze", "/analyze"),
                files={"file": (f"{query_id}.jpg", f, "image/jpeg")},
                timeout=90,
            )
        resp.raise_for_status()
        data = resp.json()
        ids: list[str] = []
        for tab_data in (data.get("categories") or {}).values():
            if not tab_data:
                continue
            for item in tab_data.get("products") or []:
                pid = str(item.get("productId") or item.get("product_id") or "")
                if pid:
                    ids.append(pid)
        return ids[:20]
    except Exception as e:
        print(f"  API error {query_id}: {e}", file=sys.stderr)
        return []


def recall_at_k(predicted: list[str], gold: list[dict], k: int) -> float:
    relevant = {c["product_id"] for c in gold if c["label"] > 0}
    if not relevant:
        return 0.0
    top_k = set(predicted[:k])
    return len(top_k & relevant) / len(relevant)


def mrr(predicted: list[str], gold: list[dict]) -> float:
    relevant = {c["product_id"] for c in gold if c["label"] > 0}
    for i, pid in enumerate(predicted):
        if pid in relevant:
            return 1.0 / (i + 1)
    return 0.0


def evaluate(full: bool = False) -> dict[str, float]:
    sample = None if full else SAMPLE_SIZE
    gold = load_gold(sample or 9999)
    if not gold:
        return {}

    metrics: dict[str, list[float]] = {
        "recall@1": [], "recall@5": [], "recall@20": [], "mrr": []
    }

    for i, q in enumerate(gold):
        qid = q["query_id"]
        candidates = q.get("candidates", [])
        predicted = call_api(qid)
        metrics["recall@1"].append(recall_at_k(predicted, candidates, 1))
        metrics["recall@5"].append(recall_at_k(predicted, candidates, 5))
        metrics["recall@20"].append(recall_at_k(predicted, candidates, 20))
        metrics["mrr"].append(mrr(predicted, candidates))
        if (i + 1) % 10 == 0:
            print(f"  {i+1}/{len(gold)} queries evaluated...")

    summary = {k: sum(v) / len(v) if v else 0.0 for k, v in metrics.items()}
    return summary


def main() -> None:
    full = "--full" in sys.argv
    print(f"=== Regression Test ({'full' if full else f'sample {SAMPLE_SIZE}'}) ===")
    summary = evaluate(full=full)
    if not summary:
        print("SKIP: no gold set data")
        sys.exit(0)

    print(json.dumps(summary, indent=2))

    # baseline 비교
    if BASELINE_FILE.exists():
        baseline = json.loads(BASELINE_FILE.read_text())
        regressions = []
        for metric, value in summary.items():
            threshold = baseline.get(metric, 0.0) * 0.95
            if value < threshold:
                regressions.append(f"  REGRESSION {metric}: {baseline[metric]:.4f} → {value:.4f}")
        if regressions:
            print("\n".join(regressions))
            sys.exit(1)
        print("PASS: no regressions")
    else:
        BASELINE_FILE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE_FILE.write_text(json.dumps(summary, indent=2))
        print(f"Baseline saved: {BASELINE_FILE}")


if __name__ == "__main__":
    main()
