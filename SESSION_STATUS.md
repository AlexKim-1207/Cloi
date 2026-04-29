# Cloi 세션 상태 (Claude가 자동 업데이트)

## 현재 상태
- 완료 세션: SESSION 1
- 다음 세션: SESSION 2

---

## 세션 진행 현황

| 세션 | 내용 | 상태 | 소요시간 |
|------|------|------|----------|
| SESSION 1 | 임베더 3종 구현 + 추상화 | ✅ 완료 | - |
| SESSION 2 | 카탈로그 500장 + 인덱스 3세트 | ⏳ 대기 | - |
| SESSION 3 | Ground Truth + A/B 측정 + 비교표 | ⏳ 대기 | - |
| SESSION 4 | 우승모델 채택 + 배포 + 연동 | ⏳ 대기 | - |

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
claude --dangerously-skip-permissions "CLAUDE.md와 fashion-search/docs/EXECUTION_PLAN.md를 읽고 SESSION 2 작업을 진행해. 완료 후 SESSION_STATUS.md를 업데이트하고 git commit해."
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
- [ ] `fashion-search/scripts/seed_catalog.py`
- [ ] `fashion-search/src/data/catalog/` 500장+
- [ ] `fashion-search/src/data/catalog/catalog.jsonl`
- [ ] `fashion-search/artifacts/openclip_vitl14.faiss`
- [ ] `fashion-search/artifacts/fashion_clip.faiss`
- [ ] `fashion-search/artifacts/marqo_fashion_siglip.faiss`
- [ ] git commit: `feat: step2 catalog seed and index build`

### SESSION 3 산출물
- [ ] `fashion-search/scripts/generate_eval_set.py`
- [ ] `fashion-search/eval/queries/` 50장
- [ ] `fashion-search/eval/ground_truth.jsonl`
- [ ] `fashion-search/eval/runner.py`
- [ ] `fashion-search/eval/results/comparison.md` (우승 모델 명시)
- [ ] git commit: `feat: step3 eval baseline measurement`

### SESSION 4 산출물
- [ ] 우승 모델 settings.py 반영
- [ ] `fashion-search/eval/tune_rerank.py` + 최적 가중치 적용
- [ ] Gemini 2.5 Flash 전체 통일
- [ ] `fashion-search/Dockerfile`
- [ ] `fashion-search/deploy.sh`
- [ ] Cloud Run 배포 URL
- [ ] Phase 1 토스앱 연결 완료
- [ ] git commit: `feat: step4 deploy production`
