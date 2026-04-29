"""eval/results/*.json → comparison.md 생성 + 우승 모델 결정.

Usage:
    python -m eval.compare
"""
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "eval" / "results"


def _score(r: dict) -> float:
    """0.5*R@10 + 0.2*MRR + 0.2*latency_score + 0.1*R@50. p50>2500ms → -1."""
    p50 = r.get("p50_ms", 9999)
    if p50 > 2500:
        return -1.0
    latency_score = max(0.0, (3000.0 - p50) / 3000.0)
    return (
        0.5 * r.get("recall_at_10", 0.0)
        + 0.2 * r.get("mrr", 0.0)
        + 0.2 * latency_score
        + 0.1 * r.get("recall_at_50", 0.0)
    )


def _load_latest() -> list[dict]:
    """임베더별 최신 결과 파일 1개씩 로드."""
    files = sorted(RESULTS_DIR.glob("*.json"))
    by_embedder: dict[str, dict] = {}
    for f in files:
        if f.stem.startswith("comparison"):
            continue
        data = json.loads(f.read_text(encoding="utf-8"))
        name = data.get("embedder", f.stem)
        by_embedder[name] = data
    return list(by_embedder.values())


def main() -> None:
    if not RESULTS_DIR.exists():
        print("ERROR: eval/results/ 없음 — eval.runner 먼저 실행")
        sys.exit(1)

    results = _load_latest()
    if not results:
        print("결과 없음. eval.runner 먼저 실행.")
        sys.exit(1)

    scored = sorted([(_score(r), r) for r in results], key=lambda x: x[0], reverse=True)
    winner_score, winner = scored[0]

    header = "| 모델 | Recall@10 | Recall@50 | MRR | CatPrec@10 | p50(ms) | p99(ms) | 점수 | |"
    sep = "|------|-----------|-----------|-----|------------|---------|---------|------|---|"
    rows = []
    for sc, r in scored:
        if sc < 0:
            badge = "[탈락]"
        elif r is winner:
            badge = "[우승]"
        else:
            badge = ""
        rows.append(
            f"| {r['embedder']} "
            f"| {r.get('recall_at_10', 0):.4f} "
            f"| {r.get('recall_at_50', 0):.4f} "
            f"| {r.get('mrr', 0):.4f} "
            f"| {r.get('cat_prec_at_10', 0):.4f} "
            f"| {r.get('p50_ms', 0):.1f} "
            f"| {r.get('p99_ms', 0):.1f} "
            f"| {sc:.4f} "
            f"| {badge} |"
        )

    md = f"""# Fashion Search A/B 비교 결과

> 생성: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 결과 비교

{header}
{sep}
{chr(10).join(rows)}

## 점수 산식

```
score = 0.5 × Recall@10 + 0.2 × MRR + 0.2 × latency_score + 0.1 × Recall@50
latency_score = max(0, (3000 - p50_ms) / 3000)
p50 > 2500ms → 자동 탈락
```

## 우승 모델

**{winner['embedder']}**

- Recall@10  : {winner.get('recall_at_10', 0):.4f}
- Recall@50  : {winner.get('recall_at_50', 0):.4f}
- MRR        : {winner.get('mrr', 0):.4f}
- CatPrec@10 : {winner.get('cat_prec_at_10', 0):.4f}
- p50 latency: {winner.get('p50_ms', 0):.1f}ms
- 종합 점수  : {winner_score:.4f}

## SESSION 4 명령어

```bash
claude --dangerously-skip-permissions "CLAUDE.md와 fashion-search/docs/EXECUTION_PLAN.md SESSION 4 실행. 우승모델={winner['embedder']}"
```
"""

    out_path = RESULTS_DIR / "comparison.md"
    out_path.write_text(md, encoding="utf-8")

    summary = {
        "winner": winner["embedder"],
        "winner_score": round(winner_score, 4),
        "results": [{"score": round(sc, 4), **r} for sc, r in scored],
        "generated_at": datetime.now().isoformat(),
    }
    (RESULTS_DIR / "comparison.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(md)
    print(f"저장: {out_path}")


if __name__ == "__main__":
    main()
