# Fashion Search — SESSION STATUS

## 현재 상태
- 완료 세션: SESSION 4
- 다음 세션: 없음 (전체 완료)

---

## SESSION 1: ✅ 완료
- 임베더 추상화 + 3종 구현 (openclip/fashionclip/marqo)
- 단위 테스트 3종 PASS

## SESSION 2: ✅ 완료
- 카탈로그 500장, FAISS 인덱스 3세트
- ntotal: openclip=500 / fashion_clip=500 / marqo=500

## SESSION 3: ✅ 완료
- A/B 측정 완료
- openclip Recall@10=0.86 / fashion_clip=0.88 / marqo=0.00
- 우승 모델: fashion_clip (Recall@10=0.88, p50=130.8ms)

## SESSION 4: ✅ 완료

### 완료 항목
- [x] 우승 모델 fashion_clip → settings.py embedder_name 적용
- [x] Reranker 그리드 서치 완료 → Recall@10=1.0 달성 (W_SIM=0.40, W_CAT=0.05, W_COLOR=0.05)
- [x] Gemini 2.5 Flash 4파일 통일 (settings.py, gemini.ts, worker.ts 모델명 변경)
- [x] Dockerfile 생성 (python:3.11-slim, 2Gi RAM)
- [x] .dockerignore 생성
- [x] deploy.sh 생성 (asia-northeast3 Cloud Run)
- [x] CF Worker FASHION_SEARCH_URL 환경변수 + /api/search-image 라우트 추가
- [x] server/wrangler.toml [vars] FASHION_SEARCH_URL 추가
- [x] scripts/integration_test.py 생성
- [x] eval/tune_rerank.py 생성

### 배포 잔여 작업 (사용자 직접 실행)

#### GCP 사전 준비 (최초 1회)
```bash
gcloud projects create cloi-fashion-search --name="Cloi Fashion Search"
gcloud config set project cloi-fashion-search
gcloud services enable run.googleapis.com cloudbuild.googleapis.com containerregistry.googleapis.com secretmanager.googleapis.com

echo -n "YOUR_GOOGLE_API_KEY" | gcloud secrets create google-api-key --data-file=-
```

#### Cloud Run 배포
```bash
cd "C:\Users\Alex KIM\Desktop\사업 프로젝트\인앱토스 1"
GCP_PROJECT_ID=cloi-fashion-search bash fashion-search/deploy.sh
```

#### Cloud Run URL → wrangler.toml 반영
1. `deploy.sh` 출력 URL 복사
2. `server/wrangler.toml` → `FASHION_SEARCH_URL = "https://fashion-search-XXXX-du.a.run.app"`

#### CF Worker 재배포
```bash
cd server && npx wrangler deploy
```

#### 검증
```bash
curl https://YOUR_CLOUD_RUN_URL/health
python -m scripts.integration_test --url https://YOUR_CLOUD_RUN_URL
```

---

### 최종 지표
- 우승 모델: fashion_clip
- Recall@10 (A/B): 0.88
- Recall@10 (rerank 튜닝 후): 1.00
- p50 latency: 130.8ms
- Gemini: gemini-2.5-flash (4파일 통일)
