# Fashion Search — 시스템 설계

## 개요

패션 이미지 업로드 → 유사 상품 검색 Phase 2 독립 웹서비스.
Phase 1(Toss 미니앱 Gemini+네이버쇼핑) 대비 정밀도·속도를 대폭 개선한 ML 파이프라인.

---

## 파이프라인

```
[이미지 업로드]
      │
      ▼
[SHA256 캐시 조회] ──hit──▶ [캐시 반환]
      │ miss
      ▼
[Grounding DINO] ── 의류 bbox 감지
      │
      ▼
[SAM 2] ── bbox → garment crop (흰 배경 PNG)
      │
      ▼
[asyncio.gather()]
  ├── [OpenCLIP ViT-L/14] ── crop 임베딩 → FAISS IVFFlat top-50
  └── [Gemini 2.5 Flash] ── 속성 추출 (sim < 0.75 일 때만)
      │
      ▼
[Reranker] ── 가중치 스코어 (sim 0.55 + cat 0.10 + color 0.10 + ...)
      │
      ▼
[top-20 결과] → SQLite 캐시 저장 → JSON 반환
```

---

## 컴포넌트

| 레이어 | 기술 | 역할 |
|--------|------|------|
| API | FastAPI + uvicorn | HTTP 엔드포인트, lifespan preload |
| Detection | Grounding DINO (groundingdino-unofficial) | 의류 bbox 감지 |
| Segmentation | SAM 2 (segment-anything-2) | bbox → crop |
| Embedding | OpenCLIP ViT-L/14 (laion2b_s32b_b82k) | 이미지 → 768-dim 벡터 |
| VectorDB | FAISS IndexIVFFlat (faiss-cpu) | 근사 최근접 이웃 검색 |
| LLM | Gemini 2.5 Flash (google-genai) | 조건부 속성 추출 |
| Cache | SQLite (aiosqlite) | image_hash → 결과 (24h TTL) |
| Reranker | Pure Python | 가중치 기반 최종 스코어링 |

---

## 성능 목표

| 지표 | 목표 |
|------|------|
| p50 레이턴시 | ≤ 2s (캐시 miss) |
| p99 레이턴시 | ≤ 5s |
| Recall@10 | ≥ 0.70 |
| MRR | ≥ 0.50 |
| Category Precision@10 | ≥ 0.80 |

---

## 확장 계획

- VectorStore ABC 구현체 교체: FAISSStore → MilvusStore (클라우드 스케일)
- Embedding 모델 교체: ViT-L/14 → 패션 특화 fine-tuned 모델
- 멀티-crop 병렬 처리: 여러 의류 아이템 동시 검색
