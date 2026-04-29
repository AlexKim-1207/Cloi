# Fashion Search A/B 비교 결과

> 생성: 2026-04-29 17:28:55

## 결과 비교

| 모델 | Recall@10 | Recall@50 | MRR | CatPrec@10 | p50(ms) | p99(ms) | 점수 | |
|------|-----------|-----------|-----|------------|---------|---------|------|---|
| fashion_clip | 0.8800 | 1.0000 | 0.3514 | 0.9340 | 130.8 | 493.5 | 0.8016 | [우승] |
| openclip_vitl14 | 0.8600 | 1.0000 | 0.3495 | 0.9440 | 1126.2 | 1665.5 | 0.7248 |  |
| marqo_fashion_siglip | 0.0000 | 0.2200 | 0.0097 | 0.2660 | 264.6 | 386.5 | 0.2063 |  |

## 점수 산식

```
score = 0.5 × Recall@10 + 0.2 × MRR + 0.2 × latency_score + 0.1 × Recall@50
latency_score = max(0, (3000 - p50_ms) / 3000)
p50 > 2500ms → 자동 탈락
```

## 우승 모델

**fashion_clip**

- Recall@10  : 0.8800
- Recall@50  : 1.0000
- MRR        : 0.3514
- CatPrec@10 : 0.9340
- p50 latency: 130.8ms
- 종합 점수  : 0.8016

## SESSION 4 명령어

```bash
claude --dangerously-skip-permissions "CLAUDE.md와 fashion-search/docs/EXECUTION_PLAN.md SESSION 4 실행. 우승모델=fashion_clip"
```
