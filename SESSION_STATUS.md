# Cloi 세션 상태 (Claude가 자동 업데이트)

## 현재 상태
- 완료 세션: SESSION 7 ✅
- 다음 세션: 선택사항 (Rate Limiting, Cold Start 개선, A/B 테스트)

## SESSION 7: ✅ 완료 (2026-04-29) — 멀티아이템 탐지 + FashionCLIP v3 파이프라인

### 주요 구현
- **멀티아이템 탐지**: Gemini가 이미지 전체 스캔 → top_outer/top_inner/outer/bottom/dress/shoes/bag/accessory_* 탭별 분리
- **복합 랭킹**: `final_score = clip_sim*0.45 + mood_match*0.30 + price_fit*0.25`
- **FashionCLIP 속성 분류**: AttributeClassifier — neckline/fit/sleeve/material/mood/price_tier 추출
- **GCS 유저 이미지 저장**: fire-and-forget (google-cloud-storage 없으면 graceful disable)
- **클릭 피드백 v2**: 7개 컬럼 추가 (final_score, rank_position, mood_label 등)
- **v3 UI**: 탭별 카드 + match_score % 배지 + sort_by 파라미터

### 신규 파일
| 파일 | 설명 |
|------|------|
| `fashion-search/src/ranking/attribute_classifier.py` | FashionCLIP zero-shot 속성 분류 |
| `fashion-search/src/ranking/mood_ranker.py` | 복합 랭킹 공식 |
| `fashion-search/src/storage/user_image_store.py` | GCS fire-and-forget 저장 |
| `fashion-search/src/llm/schemas.py` | DetectedItem + MultiItemStyleContext |
| `fashion-search/scripts/integration_test_v2.py` | v3 E2E 6개 TC |

### 수정 파일
- `apps/api/routes_search.py` — v3 파이프라인 전면 재작성
- `apps/api/schemas.py` — SearchResponse (tabs/ProductCard/TabSection)
- `apps/api/main.py` — AttributeClassifier 싱글턴 추가
- `src/llm/style_analyzer.py` — MultiItemStyleContext 분석
- `src/embedding/fashion_clip_embedder.py` — embed_single + encode_text
- `src/search/parallel_search.py` — search_all_items_v2
- `src/logging/search_logger.py` — 클릭 v2 컬럼 마이그레이션
- `server/src/worker.ts` — v3 프록시 + /api/click 추가
- `src/types/index.ts` + `src/services/api.ts` + UI 3파일 — v3 연동

### 배포
- Cloud Run revision: fashion-search-00009-* ✅
- GCS bucket: gs://cloi-user-images ✅
- CF Worker: cloi-api (v3 프록시) ✅
- CF Pages: https://11aa492c.cloi.pages.dev ✅

### 스키마 버그 수정
- `DetectedItem.is_inner: bool = False` → `bool` (google-genai 1.0.0 default value 비지원)

## SESSION 6: ✅ 완료 (2026-04-29) — 프로덕션 보안/안정성

### E2E 검증
- Cloud Run /health ✅ (faiss_size=2725, embedder=fashion_clip, revision 00006)
- CF Worker /api/health ✅ (Gemini+Naver 키 존재)
- CF Worker /api/search ✅ (Naver 검색 14건 정상)
- Gemini API 503 외부 장애 (클라우드 측 일시적 과부하)

### 발견된 취약점 (전체 수정 완료)
| 심각도 | 취약점 | 수정 |
|--------|--------|------|
| Critical | Admin 엔드포인트 인증 없음 | APIKeyHeader + Depends(_require_admin) ✅ |
| High | CORS allow_origins=["*"] (Cloud Run) | 도메인 화이트리스트 ✅ |
| High | 파일 업로드 크기 제한 없음 | 10MB 제한 (HTTP 413) ✅ |
| High | Gemini 에러 내부 정보 노출 | 제네릭 메시지 반환 ✅ |
| High | CF Worker → Cloud Run 포맷 불일치 (JSON vs multipart) | base64→multipart 변환 ✅ |
| Medium | MIME 타입 검증 없음 | image/* 허용 목록 (HTTP 415) ✅ |
| Medium | FastAPI /docs 프로덕션 공개 | DEBUG=false → 404 ✅ |
| Low | 미사용 import (numpy), 타입 누락 | 제거 + 타입 추가 ✅ |

### 검증 결과
- Admin auth: 토큰 없음 → 401 ✅, 올바른 토큰 → 200 ✅
- 파일 크기: 11MB → 413 ✅
- MIME: application/pdf → 415 ✅
- /docs: 404 ✅
- /openapi.json: 404 ✅

### 배포 완료
- Cloud Run revision: fashion-search-00006-frs ✅
- CF Worker: cloi-api ✅
- CF Pages: https://f350f967.cloi.pages.dev ✅
- git push: 6a11add ✅

### 향후 과제
- Rate Limiting (Cloudflare Rate Limiting Rules 또는 middleware)
- Gemini API 503 fallback 전략 (이미지 분석 실패 시 키워드 기반 대체)
- Cold Start 최적화 (Cloud Run min-instances=1 고려)

## SESSION 5: ✅ 완료 (2026-04-29)
- E2E 테스트: Cloud Run /health ✅ (faiss_size=2725), CF Worker /health ✅
- Cloud Run /api/search: Gemini 503 외부 장애 (코드 로직 정상)
- [보안] worker.ts 에러 응답 stack trace 제거 (4곳)
- [버그픽스] gemini_client.py + style_analyzer.py retry 범위 축소 (일시적 오류만)
- [빌드] Rollup WASM 교체 (Node v24 sandbox 호환) + build.mjs 추가
- CF Pages 배포: https://5b59c50c.cloi.pages.dev ✅
- CF Worker 재배포: https://cloi-api.kyoung361207.workers.dev ✅
- git push origin main ✅

## SESSION 4: ✅ 완료
- 우승 모델 fashion_clip → settings.py 반영
- Reranker 그리드 서치 → Recall@10=1.0 (W_SIM=0.40)
- Gemini 2.5 Flash 4파일 통일
- Cloud Run 배포 완료: https://fashion-search-dibvogjuma-du.a.run.app (faiss_size=2725)
- CF Worker 배포 완료: https://cloi-api.kyoung361207.workers.dev
- FASHION_SEARCH_URL 연결 완료

---

## 세션 진행 현황

| 세션 | 내용 | 상태 | 소요시간 |
|------|------|------|----------|
| SESSION 1 | 임베더 3종 구현 + 추상화 | ✅ 완료 | - |
| SESSION 2 | 카탈로그 500장 + 인덱스 3세트 | ✅ 완료 | - |
| SESSION 3 | Ground Truth + A/B 측정 + 비교표 | ✅ 완료 | - |
| SESSION 4 | 우승모델 채택 + 배포 + 연동 | ⏳ 대기 | - |

---

## SESSION 3: ✅ 완료
- Ground Truth 50쿼리 생성 (`eval/queries/` 50장, `eval/ground_truth.jsonl`)
- A/B 측정 완료 (3종 임베더, --skip-vision 플래그):
  - openclip_vitl14  → Recall@10=0.8600, Recall@50=1.0000, MRR=0.3495, p50=1126ms
  - fashion_clip     → Recall@10=0.8800, Recall@50=1.0000, MRR=0.3514, p50=130ms
  - marqo_fashion_siglip → Recall@10=0.0000 (모델 가중치 불일치 — SiglipModel random init)
- 우승 모델: **fashion_clip** (종합점수=0.8016, Recall@10=0.88, p50=130ms)
- 스크립트: `scripts/generate_eval_set.py`, `eval/runner.py`, `eval/compare.py`
- 결과: `eval/results/comparison.md`

---

## SESSION 2: ✅ 완료
- 카탈로그 500장 (HF `ashraq/fashion-product-images-small`, stratified by subCategory)
- `src/data/catalog/catalog.jsonl` 500줄 생성
- FAISS 인덱스 3세트 빌드 완료:
  - `artifacts/openclip_vitl14.faiss` ntotal=500 / `openclip_vitl14_meta.db` 500rows
  - `artifacts/fashion_clip.faiss` ntotal=500 / `fashion_clip_meta.db` 500rows
  - `artifacts/marqo_fashion_siglip.faiss` ntotal=500 / `marqo_fashion_siglip_meta.db` 500rows
- 스크립트: `scripts/seed_catalog.py`, `scripts/build_catalog_index.py` (--embedder 인자 추가)
- KMP_DUPLICATE_LIB_OK=TRUE 필요 (Windows OMP 충돌)

---

## SESSION 1: ✅ 완료
- 임베더 추상화 + 3종 구현 (openclip/fashionclip/marqo-siglip)
- `ImageEmbedder` ABC → `embedder_base.py`
- `OpenCLIPEmbedder` (dim=768), `FashionCLIPEmbedder` (dim=512), `MarqoSigLIPEmbedder` (dim=768)
- 팩토리 함수 `get_embedder(name)` → `src/embedding/__init__.py`
- 단위 테스트 스크립트 `scripts/test_embedders.py` (L2 norm + dim 검증) → **3종 PASS 확인**
- `settings.py` `embedder_name=marqo_fashion_siglip`, `embedder_device=cpu` 추가
- `apps/api/main.py` lifespan → `get_embedder()` 기반 preload
- 수정: `requirements.txt` → `transformers>=4.44.2,<5.0` 추가 (누락 패키지)
- 수정: `FashionCLIPEmbedder` → `visual_projection` 적용 (512-dim 정확)
- 수정: `MarqoSigLIPEmbedder` → `SiglipModel` 사용 (meta tensor 버그 우회)

---

## 다음 실행 명령어

```bash
cd "C:\Users\Alex KIM\Desktop\사업 프로젝트\인앱토스 1"
claude --dangerously-skip-permissions "CLAUDE.md와 fashion-search/docs/EXECUTION_PLAN.md SESSION 4 실행. 우승모델=fashion_clip"
```

---

## 산출물 체크 (완료 시 Claude가 업데이트)

### SESSION 1 산출물
- [x] `fashion-search/src/embedding/embedder_base.py`
- [x] `fashion-search/src/embedding/openclip_embedder.py`
- [x] `fashion-search/src/embedding/fashion_clip_embedder.py`
- [x] `fashion-search/src/embedding/marqo_siglip_embedder.py`
- [x] `fashion-search/src/embedding/__init__.py` (팩토리)
- [x] `fashion-search/scripts/test_embedders.py` (L2 norm + dim 검증)
- [x] `settings.py` embedder_name / embedder_device 추가
- [x] git commit: `feat: step1 embedder abstraction`
- [x] 단위 테스트 실행 검증 (3종 모두 PASS: openclip/fashion_clip/marqo_siglip)

### SESSION 2 산출물
- [x] `fashion-search/scripts/seed_catalog.py`
- [x] `fashion-search/src/data/catalog/` 500장+
- [x] `fashion-search/src/data/catalog/catalog.jsonl`
- [x] `fashion-search/artifacts/openclip_vitl14.faiss` (ntotal=500)
- [x] `fashion-search/artifacts/fashion_clip.faiss` (ntotal=500)
- [x] `fashion-search/artifacts/marqo_fashion_siglip.faiss` (ntotal=500)
- [x] git commit: `feat: step2 catalog seed and index build`

### SESSION 3 산출물
- [x] `fashion-search/scripts/generate_eval_set.py`
- [x] `fashion-search/eval/queries/` 50장
- [x] `fashion-search/eval/ground_truth.jsonl`
- [x] `fashion-search/eval/runner.py`
- [x] `fashion-search/eval/compare.py`
- [x] `fashion-search/eval/results/comparison.md` (우승 모델: fashion_clip)
- [x] git commit: `feat: step3 eval baseline measurement`

### SESSION 4 산출물
- [ ] 우승 모델 settings.py 반영
- [ ] `fashion-search/eval/tune_rerank.py` + 최적 가중치 적용
- [ ] Gemini 2.5 Flash 전체 통일
- [ ] `fashion-search/Dockerfile`
- [ ] `fashion-search/deploy.sh`
- [ ] Cloud Run 배포 URL
- [ ] Phase 1 토스앱 연결 완료
- [ ] git commit: `feat: step4 deploy production`
