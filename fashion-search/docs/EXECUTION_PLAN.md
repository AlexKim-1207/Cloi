# Cloi Fashion Search — 실행 계획서 (Claude 전용)

> **목적**: Claude가 추가 질문 없이 즉시 코딩 → 배포까지 자율 실행
> **최종 목표**: 패션 이미지 유사 상품 검색 Recall@10 ≥ 0.65, p50 ≤ 2초, 프로덕션 배포
> **세션 구조**: 4개 세션 분리 실행. 각 세션 끝에 SESSION_STATUS.md 업데이트 필수

---

## ⚠️ 세션 종료 시 필수 작업 (모든 세션 공통)

**세션 끝날 때 반드시 아래 순서로 실행:**

1. `git add -A && git commit -m "feat: sessionN 완료 - [내용 요약]"`
2. `SESSION_STATUS.md` 업데이트 (아래 형식 유지):
   - 완료된 세션 ✅ 표시
   - 완료된 산출물 체크박스 체크
   - 다음 세션 명령어 정확히 기재
3. `git add SESSION_STATUS.md && git commit -m "chore: session status update"`

---

## 0. 절대 원칙 (위반 시 작업 무효)

### 🚫 과거 실수 — 반복 금지

| 실수 | 결과 | 방지책 |
|------|------|--------|
| 코드 먼저, 데이터 없음 | 측정 0회 | **카탈로그 확보 먼저** |
| OpenCLIP 단독 선택 | 비교 없는 결정 | **3종 A/B 의무** |
| 평가 프레임만 만들고 안 돌림 | Recall 베이스라인 0 | **eval runner 1회 이상 실행 필수** |
| FashionCLIP/SigLIP 검토 누락 | 도메인 특화 모델 미활용 | **Marqo-FashionSigLIP 반드시 포함** |
| 라이선스 회색지대 회피 | 정확도 손해 | **라이선스 무시, 최대 효용 우선** |
| 산출물 검증 누락 | "코드만 짜놨음" | **모든 STEP 끝에 체크박스 통과** |
| 워크트리에 파일 생성 | 원본 미반영 | **항상 메인 프로젝트 루트 기준** |

### ✅ 우선순위
1. 측정 가능한 결과물 > 깔끔한 코드
2. 데이터·측정 > 파이프라인 정교화
3. 유저 즉시 실행 가능 > 부분 완성
4. 최대 효용 > 안전성

### 🔋 토큰 절약 (CLAUDE.md 규칙과 동일)
- Grep 우선 (파일 전체 Read 금지)
- 독립 작업 병렬 도구 호출
- 이미 읽은 파일 재읽기 금지

---

## 1. 환경 정보

**프로젝트 루트**: `C:\Users\Alex KIM\Desktop\사업 프로젝트\인앱토스 1\`
**작업 디렉토리**: `fashion-search/`
**Gemini 모델**: `gemini-2.5-flash` (모든 호출 고정)
**설정 파일**: `.claude/settings.json` (권한 35개 허용)

---

## SESSION 1 — 임베더 추상화 + 3종 구현

**예상 소요**: ~2시간 (Claude 작업)
**컨텍스트 예산**: ~60K 토큰

### 작업 목록

#### 1. `fashion-search/src/embedding/embedder_base.py` (신규)

```python
from abc import ABC, abstractmethod
import numpy as np
from PIL import Image

class ImageEmbedder(ABC):
    name: str
    dim: int

    @abstractmethod
    def load(self) -> None: ...

    @abstractmethod
    def embed(self, images: list[Image.Image]) -> np.ndarray:
        """L2 정규화된 (N, dim) float32 반환"""
        ...

    def embed_single(self, image: Image.Image) -> np.ndarray:
        return self.embed([image])[0]
```

#### 2. `fashion-search/src/embedding/openclip_embedder.py` (기존 래핑)
- `open_clip.create_model_and_transforms("ViT-L-14", "laion2b_s32b_b82k")`
- `name = "openclip_vitl14"`, `dim = 768`
- 기존 `openclip_embed.py` 로직 이전

#### 3. `fashion-search/src/embedding/fashion_clip_embedder.py`
- `CLIPModel.from_pretrained("patrickjohncyh/fashion-clip")`
- `CLIPProcessor.from_pretrained("patrickjohncyh/fashion-clip")`
- `name = "fashion_clip"`, `dim = 512`
- `processor(images=batch, return_tensors="pt")` → `model.get_image_features()`
- L2 정규화 후 numpy float32 반환

#### 4. `fashion-search/src/embedding/marqo_siglip_embedder.py`
- `AutoModel.from_pretrained("Marqo/marqo-fashionSigLIP", trust_remote_code=True)`
- `AutoProcessor.from_pretrained("Marqo/marqo-fashionSigLIP", trust_remote_code=True)`
- `name = "marqo_fashion_siglip"`, `dim = 768`
- SigLIP: `model.get_image_features()` 사용
- L2 정규화 후 numpy float32 반환

#### 5. `fashion-search/src/embedding/__init__.py` 팩토리
```python
def get_embedder(name: str) -> ImageEmbedder:
    if name == "openclip_vitl14": return OpenCLIPEmbedder()
    if name == "fashion_clip": return FashionCLIPEmbedder()
    if name == "marqo_fashion_siglip": return MarqoSigLIPEmbedder()
    raise ValueError(f"Unknown embedder: {name}")
```

#### 6. `fashion-search/src/config/settings.py` 수정
- `embedder_name: str = "marqo_fashion_siglip"` 추가
- `embedder_device: str = "cpu"` 추가

#### 7. 단위 검증 스크립트 `fashion-search/scripts/test_embedders.py`
```python
# 더미 PIL 이미지 1장으로 3종 embed 실행
# 각각 L2 norm ≈ 1.0 검증 (허용오차 1e-5)
# 차원 768/512/768 검증
# 결과 출력: PASS/FAIL
```

#### 8. `apps/api/main.py` lifespan 수정
- `get_settings().embedder_name` 기준으로 분기 preload

### 산출물 체크 (통과 후 SESSION 2 진입)
- [ ] `embedder_base.py` 존재
- [ ] 3종 임베더 파일 존재
- [ ] `python -m scripts.test_embedders` 실행 → 3종 모두 PASS
- [ ] `git commit: feat: step1 embedder abstraction`

### 세션 종료 시 SESSION_STATUS.md 업데이트 내용
```
SESSION 1: ✅ 완료
- 임베더 추상화 + 3종 구현 (openclip/fashionclip/marqo)
- 단위 테스트 3종 PASS

다음 세션 명령어:
claude --dangerously-skip-permissions "CLAUDE.md + fashion-search/docs/EXECUTION_PLAN.md SESSION 2 실행"
```

---

## SESSION 2 — 카탈로그 시드 + 인덱스 3세트 빌드

**예상 소요**: ~1시간 (Claude 코드) + ~4~6시간 (CPU 임베딩 실행)
**컨텍스트 예산**: ~40K 토큰 (Claude 작업 부분만)

### 작업 목록

#### 1. `fashion-search/scripts/seed_catalog.py` (신규)

**전략**: HuggingFace `ashraq/fashion-product-images-small` 자동 다운로드
```python
# datasets.load_dataset("ashraq/fashion-product-images-small")
# 첫 500개 stratified sampling (카테고리별 균형)
# 출력:
#   fashion-search/src/data/catalog/{product_id}.jpg
#   fashion-search/src/data/catalog/catalog.jsonl
# catalog.jsonl 형식:
# {"product_id":"p00001","category":"Topwear","subcategory":"Tshirts",
#  "color":"Black","gender":"Men","name":"..."}
```

#### 2. `fashion-search/scripts/build_catalog_index.py` 수정
- `--embedder {openclip_vitl14|fashion_clip|marqo_fashion_siglip}` 인자 추가
- 출력: `artifacts/{embedder_name}.faiss` + `artifacts/{embedder_name}_meta.db`
- tqdm 진행률, 100개마다 체크포인트

#### 3. `fashion-search/artifacts/` 디렉토리 생성

#### 4. 실행 순서
```bash
python -m scripts.seed_catalog --target 500
python -m scripts.build_catalog_index --embedder openclip_vitl14
python -m scripts.build_catalog_index --embedder fashion_clip
python -m scripts.build_catalog_index --embedder marqo_fashion_siglip
```

⚠️ 임베딩 빌드 중 Claude 세션 종료해도 됨. 체크포인트로 재시작 가능.

### 산출물 체크
- [ ] `src/data/catalog/` 이미지 500장+
- [ ] `catalog.jsonl` 라인 수 = 이미지 수
- [ ] `artifacts/openclip_vitl14.faiss` ntotal ≥ 400
- [ ] `artifacts/fashion_clip.faiss` ntotal ≥ 400
- [ ] `artifacts/marqo_fashion_siglip.faiss` ntotal ≥ 400
- [ ] `git commit: feat: step2 catalog and index build`

### 세션 종료 시 SESSION_STATUS.md 업데이트
```
SESSION 2: ✅ 완료
- 카탈로그 {N}장, FAISS 인덱스 3세트
- ntotal: openclip={N} / fashion_clip={N} / marqo={N}

다음 세션 명령어:
claude --dangerously-skip-permissions "CLAUDE.md + fashion-search/docs/EXECUTION_PLAN.md SESSION 3 실행"
```

---

## SESSION 3 — Ground Truth + A/B 측정 + 비교표

**예상 소요**: ~3시간
**컨텍스트 예산**: ~80K 토큰

### 작업 목록

#### 1. `fashion-search/scripts/generate_eval_set.py` (신규)
```python
# catalog.jsonl에서 50개 무작위 샘플 → queries/
# 나머지 450개 중 같은 category+subcategory+color → relevant_ids
# 출력:
#   eval/queries/{query_id}.jpg (카탈로그에서 복사)
#   eval/ground_truth.jsonl
# 형식: {"query_id":"q001","query_path":"eval/queries/q001.jpg",
#         "relevant_ids":["p00042","p00118"],"category":"Topwear"}
```

#### 2. `fashion-search/eval/runner.py` (신규)
```python
# --embedder {name} --gt eval/ground_truth.jsonl
# 각 쿼리 → embed → FAISS search → metrics.evaluate()
# DINO+SAM2 파이프라인은 선택 (--skip-vision 플래그로 생략 가능, 속도↑)
# 출력: eval/results/{embedder}_{timestamp}.json
# {recall_at_10, recall_at_50, mrr, cat_prec_at_10, p50_ms, p99_ms, n_queries}
```

#### 3. 3종 측정 실행
```bash
python -m scripts.generate_eval_set --n-queries 50
python -m eval.runner --embedder openclip_vitl14 --skip-vision
python -m eval.runner --embedder fashion_clip --skip-vision
python -m eval.runner --embedder marqo_fashion_siglip --skip-vision
```

#### 4. `fashion-search/eval/compare.py` (신규)
- `eval/results/*.json` 로드 → `eval/results/comparison.md` 생성
- 우승 모델 자동 결정: `0.5*Recall@10 + 0.2*MRR + 0.2*latency_score + 0.1*Recall@50`
- `latency_score = max(0, (3000 - p50_ms) / 3000)`
- latency p50 > 2500ms 자동 탈락

### 산출물 체크
- [ ] `eval/queries/` 50장
- [ ] `eval/ground_truth.jsonl` 50라인
- [ ] `eval/results/` JSON 3개
- [ ] `eval/results/comparison.md` (우승 모델 명시)
- [ ] 우승 모델 Recall@10 ≥ 0.40 (미달 시 카탈로그 1000장으로 확장)
- [ ] `git commit: feat: step3 eval baseline`

### 세션 종료 시 SESSION_STATUS.md 업데이트
```
SESSION 3: ✅ 완료
- A/B 측정 완료
- openclip Recall@10={X} / fashion_clip={X} / marqo={X}
- 우승 모델: {모델명} (Recall@10={X}, p50={X}ms)

다음 세션 명령어:
claude --dangerously-skip-permissions "CLAUDE.md + fashion-search/docs/EXECUTION_PLAN.md SESSION 4 실행. 우승모델={모델명}"
```

---

## SESSION 4 — 우승 모델 채택 + Reranker 튜닝 + Cloud Run 배포

**예상 소요**: ~4시간
**컨텍스트 예산**: ~80K 토큰

### 배포 구조 (중요)

```
CF Pages (프론트)  →  CF Worker cloi-api  →  Cloud Run (fashion-search FastAPI)
     ↑                      ↑                        ↑
  기존 유지              기존 유지 +              Python ML 서버
                      FASHION_SEARCH_URL 추가      GCP asia-northeast3 배포
```

- **CF Pages + CF Worker**: 기존 그대로. `wrangler deploy`만 다시 실행
- **fashion-search**: Google Cloud Run에 신규 배포 (Python + FAISS + 임베더)
- **CF Worker**: `FASHION_SEARCH_URL` 환경변수 추가 → Cloud Run 호출
- **Cloud Run 스펙**: `--memory 2Gi --cpu 2 --min-instances 0 --max-instances 3`
- **리전**: `asia-northeast3` (서울)

### 작업 목록

#### 1. 우승 모델 채택
- `SESSION 3 comparison.md`에서 우승 모델 확인
- `settings.py` `embedder_name` = 우승 모델로 변경
- `apps/api/main.py` 우승 임베더만 preload

#### 2. Reranker 가중치 그리드 서치
`fashion-search/eval/tune_rerank.py` (신규)
- W_SIM ∈ {0.40, 0.55, 0.70, 0.85}
- W_CAT, W_COLOR ∈ {0.05, 0.10, 0.15}
- 가중치 합 = 1.0 유지
- 같은 GT 셋 기준 Recall@10 최대 조합 채택
- `src/search/rerank.py` 상수 자동 업데이트

#### 3. Gemini 2.5 Flash 전체 통일
다음 4파일 모두 `model="gemini-2.5-flash"` 확인/수정:
- `fashion-search/src/llm/gemini_client.py`
- `fashion-search/src/llm/gemini_extract.py`
- `fashion-search/src/llm/gemini_explain.py`
- `server/src/services/gemini.ts`

#### 4. `fashion-search/Dockerfile`
```dockerfile
FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir transformers==4.44.2 fastapi uvicorn[standard]
COPY . .
COPY artifacts/ ./artifacts/
ENV PORT=8080
EXPOSE 8080
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

#### 5. `fashion-search/.dockerignore`
```
.venv/
__pycache__/
*.pyc
.env
src/data/catalog/
eval/queries/
.git/
```

#### 6. `fashion-search/deploy.sh` (신규)
```bash
#!/usr/bin/env bash
set -e
PROJECT_ID=${GCP_PROJECT_ID:-cloi-fashion-search}
REGION="asia-northeast3"
SERVICE_NAME="fashion-search"
IMAGE="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

echo "=== Cloud Run 배포: ${SERVICE_NAME} (${REGION}) ==="

# Docker 이미지 빌드 + GCR 푸시
gcloud builds submit \
  --project="${PROJECT_ID}" \
  --tag="${IMAGE}" \
  fashion-search/

# Cloud Run 배포
gcloud run deploy "${SERVICE_NAME}" \
  --project="${PROJECT_ID}" \
  --image="${IMAGE}" \
  --region="${REGION}" \
  --platform=managed \
  --allow-unauthenticated \
  --memory=2Gi \
  --cpu=2 \
  --min-instances=0 \
  --max-instances=3 \
  --port=8080 \
  --set-env-vars="EMBEDDER_NAME=fashion_clip,KMP_DUPLICATE_LIB_OK=TRUE" \
  --set-secrets="GOOGLE_API_KEY=google-api-key:latest"

# URL 출력
URL=$(gcloud run services describe "${SERVICE_NAME}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --format="value(status.url)")
echo "=== 배포 완료: ${URL} ==="
```

#### 7. CF Worker 연결 (`server/src/worker.ts` 수정)
- `FASHION_SEARCH_URL` 환경변수 추가 (Cloud Run URL)
- `/api/search` 라우트: Phase 2 우선 호출 → 5초 초과 or 결과 0 → 네이버 fallback
- `server/wrangler.toml`에 `[vars]` 섹션 추가:
  ```toml
  [vars]
  FASHION_SEARCH_URL = "https://fashion-search-HASH-du.a.run.app"  # deploy.sh 출력 URL로 교체
  ```

#### 8. GCP 사전 준비 (최초 1회)
```bash
# 프로젝트 생성 & API 활성화
gcloud projects create cloi-fashion-search --name="Cloi Fashion Search"
gcloud config set project cloi-fashion-search
gcloud services enable run.googleapis.com cloudbuild.googleapis.com containerregistry.googleapis.com secretmanager.googleapis.com

# Secret Manager에 API 키 저장
echo -n "${GOOGLE_API_KEY}" | gcloud secrets create google-api-key --data-file=-
```

#### 9. Cloud Run 배포 실행
```bash
chmod +x fashion-search/deploy.sh
GCP_PROJECT_ID=cloi-fashion-search bash fashion-search/deploy.sh
# 출력된 URL을 server/wrangler.toml FASHION_SEARCH_URL에 복붙
```

#### 10. CF 재배포
```bash
# 프론트엔드 (CF Pages)
npm run build
wrangler pages deploy dist

# 백엔드 (CF Worker)
cd server && wrangler deploy
```

#### 10. `fashion-search/scripts/integration_test.py`
- 로컬 서버 5장 이미지 테스트
- 응답 구조 검증 + latency 출력

### 산출물 체크
- [ ] `deploy.sh` 존재
- [ ] `Dockerfile` 빌드 성공 (`docker build -t fashion-search fashion-search/`)
- [ ] `gcloud builds submit` 성공 (GCR 이미지 푸시)
- [ ] `gcloud run deploy` 완료 + URL 응답 200
- [ ] `{CLOUD_RUN_URL}/health` → 200
- [ ] CF Worker `FASHION_SEARCH_URL` = Cloud Run URL 설정 완료
- [ ] `wrangler deploy` 완료
- [ ] Gemini 2.5 Flash 4파일 통일
- [ ] `git commit: feat: step4 cloud-run deploy`

### 세션 종료 시 SESSION_STATUS.md 업데이트
```
SESSION 4: ✅ 완료 — 모든 작업 완료

ML 서버 URL: https://fashion-search-HASH-du.a.run.app  (실제 URL로 교체)
CF Worker: https://cloi-api.{계정}.workers.dev
CF Pages: https://cloi.pages.dev
우승 모델: fashion_clip
최종 Recall@10: {값}
최종 p50: {값}ms
Gemini 2.5 Flash: 4파일 통일 완료

유저 최종 확인:
curl {CLOUD_RUN_URL}/health
```

---

## 유저 RUN COMMANDS (개발 완료 후)

```bash
# 환경 설정 (1회)
cd "C:\Users\Alex KIM\Desktop\사업 프로젝트\인앱토스 1\fashion-search"
cp .env.example .env
# .env: GOOGLE_API_KEY, GCP_PROJECT_ID 입력

# 배포
export GCP_PROJECT_ID=your-project-id
export GOOGLE_API_KEY=your-key
bash deploy.sh

# 검증
curl https://cloi-fashion-search-xxxx.run.app/health
```

---

## 실패 대응

| 상황 | 조치 |
|------|------|
| Recall@10 < 0.40 | 카탈로그 1000장 확장 후 SESSION 2 재실행 |
| latency > 3초 | FashionCLIP(더 작음)으로 교체 |
| Cloud Run OOM | memory 8Gi로 증가 |
| HF 다운로드 실패 | `huggingface-cli login` 후 재시도 |
| Docker 빌드 실패 | requirements.txt 패키지 버전 확인 |
