# Cloi 세션 상태 (Claude가 자동 업데이트)

## 현재 상태
- 완료 세션: SESSION 5 ✅
- 다음 세션: 없음 (전체 완료)

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
