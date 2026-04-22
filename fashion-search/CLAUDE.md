# fashion-search — Claude Code 프로젝트 컨텍스트

## 프로젝트 개요
패션 이미지 유사 상품 검색 Phase 2 독립 웹서비스.
Phase 1(Toss 미니앱, Gemini + 네이버쇼핑)의 고도화 버전.

## 핵심 파이프라인
```
이미지 업로드
→ content hash 캐시 확인 (SQLite)
→ Grounding DINO: 의류 bbox 감지
→ SAM 2: bbox → garment crop (PNG)
→ OpenCLIP ViT-L/14: 배치 임베딩 (batch_size=32)
→ asyncio.gather():
    ├─ FAISS IVFFlat: top-50 벡터 검색
    └─ Gemini 2.5 Flash: 속성 추출 (confidence<0.7인 crop만)
→ Reranker: weighted score → top-20
→ 결과 캐시 저장 + JSON 반환
```

## 기술 스택
- Detection: groundingdino-unofficial (PyPI, git clone 아님)
- Segmentation: segment-anything-2 (PyPI)
- Embedding: open_clip_torch ViT-L/14 (laion2b_s32b_b82k)
- VectorDB: faiss-cpu IndexIVFFlat (VectorStore ABC 인터페이스)
- LLM: google-genai Gemini 2.5 Flash (conditional call only)
- Backend: FastAPI + asyncio
- Cache: SQLite (image_hash → result, 24h TTL)

## 핵심 원칙
- VectorStore는 ABC로 정의. FAISSStore가 구현. MilvusStore는 TODO stub.
- FastAPI lifespan으로 모델 preload (요청 시 lazy load 금지)
- Pydantic v2 사용, async/await 패턴
- Gemini는 조건부 호출 (confidence < 0.7 or FAISS 유사도 < 0.75일 때만)
- 배치 처리 + 체크포인트로 카탈로그 인덱스 빌드

## 디렉토리 구조
- `apps/api/` — FastAPI 앱
- `src/vision/` — DINO + SAM2 파이프라인
- `src/embedding/` — OpenCLIP 임베딩
- `src/search/` — VectorStore 인터페이스, FAISS, Reranker
- `src/llm/` — Gemini 클라이언트
- `src/cache/` — SQLite 결과 캐시
- `src/data/` — 카탈로그, 계약서, 업로드 임시
- `artifacts/` — FAISS 인덱스, 메타 DB, 캐시 DB
- `scripts/` — 카탈로그 빌드, 스모크 테스트
- `eval/` — Recall@10, MRR 평가 지표

## 금지사항
- 경쟁사 앱 크롤링 학습 금지
- 유저 업로드 이미지 동의 없이 학습셋 전환 금지
- DeepFashion 상업 서비스 학습 코어 사용 금지
- 처음부터 커스텀 대형 모델 학습 금지
- 초반 Milvus/S3/K8s 과투자 금지
