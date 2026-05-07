# Cloi — 패션 이미지 검색 서비스 기술 브리핑

> 외부 전문가 자문용 문서. 5분 안에 파악 가능하도록 정리.

---

## 0. 한 줄 요약

**사용자가 패션 사진을 업로드하면 비슷한 옷을 한국 쇼핑몰(Naver)에서 찾아주는 서비스.** 텍스트 매칭은 잘 되는데 **시각 매칭(이미지 → 비슷한 디자인 상품)** 이 핵심 결정 단계에서 동작 안 함. Cloud Run에 FashionCLIP 모델 올렸는데 처리 시간이 60~120초 걸려서 Worker 가 45초 timeout 걸고 fallback 으로 빠짐 → **시각 매칭 0% 적용.**

핵심 질문: **이 시각 매칭 path를 어떻게 빠르게 만들어 production에 진짜 가동시킬까?**

---

## 1. 현재 Stack

| 레이어 | 기술 | 역할 |
|------|------|------|
| **Frontend** | React + Vite, Cloudflare Pages | 이미지 업로드 UI, 결과 표시 |
| **Backend (Edge)** | Cloudflare Pages Functions (Hono framework, TypeScript) | API gateway, Gemini analyze, Naver Shopping API 검색, 후처리 |
| **Backend (ML)** | Google Cloud Run (Python FastAPI), 2 vCPU / 2Gi RAM, **GPU 없음** | FashionCLIP 임베딩, Lab 색상 분석, rembg segmentation, 시각 검색 |
| **LLM** | Google Gemini 2.5 Flash | 이미지 → 카테고리/색상/패턴/길이/성별/가격대 등 텍스트 추출 |
| **Vector DB** | FAISS (Cloud Run 안에 인메모리, ntotal=2725) | 자체 카탈로그 검색 (현재 거의 사용 안 됨) |
| **Search Source** | Naver Shopping API only | 한국 쇼핑몰 상품 검색 |
| **Image Embedder** | FashionCLIP (`patrickjohncyh/fashion-clip`, 512-dim, CPU inference) | 시각 임베딩 |
| **Code repo** | github.com/Alex-Kim1207/... (private 추정) | 모노레포 (서버 + Cloud Run + Pages) |

---

## 2. Architecture (사용자 요청 흐름)

```
[1] 사용자 → cloi.pages.dev/api/analyze (POST imageBase64)
              ↓
[2] CF Pages Function (functions/api/[[route]].ts)
        → import worker.ts (Hono app)
              ↓
[3] worker.ts /api/analyze handler:
    
    [3-A] Cloud Run /api/search 호출 시도 (FashionCLIP path, "v3")
          ↓
          fetch(${CLOUD_RUN_URL}/api/search, { 
              signal: AbortSignal.timeout(45000)  ← 45s timeout 
          })
          ↓
          if (upstream.ok) {
              return { ...data, _source: 'v3' }   ← 한 번도 안 옴
          }
          ↓
          ❌ 60~120초 걸려 timeout/error → fallback
              ↓
    [3-B] Fallback: worker 자체 Gemini 호출 ("worker_gemini")
          ↓
          analyzeImage(GEMINI_API_KEY, imageBase64, mimeType)
          ↓
          Gemini 2.5 Flash → JSON 응답 (categories + outfit_meta)
          ↓
          return { ...result, _source: 'worker_gemini' }
              ↓
[4] Frontend → /api/search/categories (POST categories + outfit_meta)
              ↓
[5] worker.ts /api/search/categories:
    - Per category: searchQueries 3개 + alternative_subtypes로 확장
    - Naver Shopping API 다중 호출 (display=20)
    - dedupeBySku
    - softScoreProducts (성별/가격/색상/패턴/길이 soft signal)
    - Top 40 반환
              ↓
[6] Frontend 결과 표시
```

**현재 100% 트래픽이 [3-B] fallback path로 흐름. [3-A] Cloud Run path 0% 적중.**

---

## 3. Cloud Run /api/search 처리 단계 (왜 60~120초 걸리는가)

```python
# fashion-search/apps/api/routes_search.py 핵심 흐름

1. PIL 이미지 디코딩                                   < 1s
2. asyncio.gather([
     analyze_style(image),           # Gemini 호출       3~5s
     attribute_classifier.classify_all(pil_image),  # CPU FashionCLIP zero-shot  2~3s
     _safe_detect_regions(image),    # Gemini bbox     3~5s
   ])
                                                    총 5~10s (병렬)
3. _augment_detected_items_from_bbox                  < 1s
4. _build_per_tab_query_embs                          
   - blur_face_regions
   - crop_garment_regions per detected_item            
   - FashionCLIP embed each crop (CPU)                3~5s
   - Lab color hist + dominant color (rembg)          5~10s  ★
5. parallel_search.search_all_items_v3
   - Naver Shopping API per detected_item             3~5s
6. _calc_clip_embeddings_and_hists per tab
   - Naver 썸네일 다운로드 (60~120 images)            5~10s
   - FashionCLIP embed each thumbnail (CPU)         15~30s  ★★
   - rembg segmentation per thumbnail                10~20s  ★★★ (가장 느림)
   - K-means dominant color                          3~5s
7. softScoreProducts (시각/색상/Naver rank)           1~2s
8. SKU 클러스터링 + lowest_price_per_cluster          1~2s
9. quadrant_sort                                     < 1s

────────────────────────────────────────────
총합: 50~100초+
```

**Bottleneck:**
- ★★★ rembg (배경 제거 모델 inference, CPU): 가장 무거움
- ★★ 60개 썸네일 × FashionCLIP CPU inference
- ★ Lab color + dominant color K-means

---

## 4. 현재 측정 데이터 (라이브)

### 4-1. `_source` 적중률
직접 5회 호출 결과:

| Call | latency | _source | path |
|------|---------|---------|------|
| 1 | 11.9s | worker_gemini | fallback |
| 2 | 13.4s | worker_gemini | fallback |
| 3 | 15.0s | worker_gemini | fallback |
| 4 | 17.3s | worker_gemini | fallback |
| 5 | 11.5s | worker_gemini | fallback |

**Cloud Run path 적중률: 0/5**

### 4-2. Cloud Run /health
- 응답: 129ms, status 200
- body: `{"status":"ok","version":"3.0.0","embedder":"fashion_clip","attribute_classifier":true,"faiss_size":2725}`
- → **인스턴스는 살아있음 (min-instances=1 적용 추정), 모델 메모리 로드됨**
- → 하지만 /api/search (실제 처리)는 너무 느려서 timeout

### 4-3. 정확도 (사용자 페르소나 5케이스 평가, 텍스트 매칭만으로)
- SESSION 11+12+13 적용 후: **4.6/5** (정상 응답 한정)
- 사용자 호소: "디자인이 다르다, 색깔이 비슷할 뿐"
- → 시각 매칭 없이는 4.6 이상 한계

---

## 5. 우리가 이미 시도한 것 (4일간 SESSION 9~13)

전부 **Worker (TypeScript) 측 텍스트 매칭 개선**. Cloud Run 시각 매칭 미적용.

| Session | Track | 작업 | 결과 |
|---------|-------|------|------|
| S9 | - | FashionCLIP per-tab embedding, color hist (Cloud Run) | 회귀 발생 (4.0 → 3.0) |
| S10 | - | color signal 0%로 차단 (Cloud Run) | 회귀 차단 |
| S11 | A | Worker FASHION_PROMPT 8키 schema | + |
| S11 | A | ensureColorPrefix, colorAwareRerank, dedupeBySku | + |
| S11 | A | _source flag, missing_categories 필드 | + (가시성) |
| S11 | C | Cloud Run에 Lab + rembg segmentation 추가 | (Cloud Run 미적중으로 효과 X) |
| S12 | B | Worker FASHION_PROMPT outfit_meta (gender, price_tier, vibe) | + 정확도 |
| S12 | C | softScoreProducts (성별/가격/색상 soft multiplier) | + 정확도 |
| S13 | A | Worker pattern signal (체크/스트라이프 etc) + 0.4x penalty | + 정확도 |
| S13 | B | Worker length signal (미니/롱 etc) + 0.3x penalty | + 정확도 |
| S13 | C | Worker alternative_subtypes (모호 이너) | + |

**누적 효과: 정확도 1.8/5 → 4.6/5. 그러나 시각 매칭이 없어 5/5 한계.**

### 시도해본 인프라 변경
- Cloud Run `--min-instances=0 → 1` (cold start 제거 시도, 효과 있었으나 처리 시간 자체 문제 해결 X)
- Worker `AbortSignal.timeout(30000) → 45000` (효과 부분적, 여전히 Cloud Run > 45초)

### 시도 안 한 것 (전문가 자문 받고 싶은 영역)
- GPU 인스턴스 도입 (Cloud Run GPU, AWS GPU, Modal Labs 등)
- ONNX 변환 / 모델 양자화 (CPU에서도 빠르게)
- 임베딩 사전 계산 + Redis/PostgreSQL 캐싱
- 썸네일 임베딩 한 번 계산 후 영구 저장 (Naver 상품 ID별 캐시)
- Progressive UX (Worker fallback 즉시 + Cloud Run 백그라운드)
- Modal Labs / Replicate 같은 serverless GPU 옮기기

---

## 6. 핵심 질문 (전문가에게)

### Q1. CPU에서 FashionCLIP inference를 5~10초 안에 끝낼 방법?
- 현재: 60개 썸네일 × CPU inference = 15~30초
- ONNX Runtime, OpenVINO, TensorRT 같은 최적화로 가능?
- 모델 양자화 (FP16, INT8) 효과는?

### Q2. 임베딩 캐싱 전략?
- Naver 상품은 productId가 있음
- 같은 productId의 임베딩을 한 번 계산 후 영구 저장하면 재사용 가능
- Redis vs PostgreSQL pgvector vs FAISS 어느 게 적합?
- 한국 쇼핑몰 상품은 자주 사라지고 새로 생김 — TTL은?

### Q3. rembg segmentation 대안?
- 의류 영역만 추출 → 색상 정확도
- rembg는 너무 무거움 (10초+/이미지)
- Lighter 모델 (MODNet, BiSeNet)?
- 아예 segmentation 없이 center crop으로 충분?

### Q4. Cloud Run vs Modal Labs vs AWS?
- Always-on GPU 비용 vs pay-per-request 비용
- 한국 사용자 대상 → 한국 region 가능 여부
- 사용량 (현재 추정 100~1000 req/day → 향후 10K+/day)

### Q5. Progressive UX 구현 패턴?
- Worker → Naver 빠른 응답 (5s)
- 백그라운드 Cloud Run → 결과 도착 시 UI 업데이트 (30~60s)
- WebSocket vs Server-Sent Events vs Long-polling?
- React에서 어떻게 stream 처리?

### Q6. FashionCLIP 한국 도메인 fine-tune?
- 한국 K-fashion 인디 브랜드 매칭 정확도 낮음
- LoRA fine-tune 하려면 데이터 1만 장+ 필요
- 데이터 수집 + 학습 비용 vs 효과?

---

## 7. 응답 sample (실제 production 응답)

`POST https://cloi.pages.dev/api/analyze` (이미지 base64 보냄)

```json
{
  "_source": "worker_gemini",
  "categories": {
    "top_inner": {
      "color": "와인 레드",
      "fit": "슬림핏",
      "material": "캐시미어 니트",
      "design": "기본 터틀넥",
      "subtype": "터틀넥 니트",
      "pattern": "단색",
      "length": "레귤러",
      "alternative_subtypes": [],
      "keywords": ["와인 레드", "터틀넥", "슬림핏"],
      "searchQueries": [
        "와인 레드 터틀넥 니트",
        "와인 슬림핏 터틀넥",
        "캐시미어 터틀넥 니트"
      ]
    },
    "outer": null,
    "bottom": null,
    "...": "..."
  },
  "gender": "female",
  "gender_confidence": 1.0,
  "gender_signals": ["여성 핏 터틀넥", "여성 셀카 구도"],
  "price_tier": "mid",
  "price_tier_confidence": 0.7,
  "price_range_estimate": { "min": 30000, "max": 80000 },
  "vibe": ["페미닌", "캐주얼"],
  "season": "fall",
  "description": "와인 레드 슬림핏 터틀넥 니트의 페미닌 캐주얼 룩",
  "missing_categories": ["top_outer", "bottom", "shoes", "bag", "accessory", "dress"]
}
```

이 응답이 Worker 자체 Gemini fallback. Cloud Run path가 적중하면 추가로 `tabs` 배열에 시각 유사도 기반 재정렬된 상품 + match_score 가 들어감.

---

## 8. 사용자 케이스 — "왜 디자인이 다르다고 호소하나"

**케이스 A: 회색 케이블 니트 세트 + 십자가 목걸이 + 검정 미니백**
- 텍스트 매칭: "회색 니트 / 회색 스커트 / 목걸이 / 가방" 분류 OK
- Naver 검색: 1순위 가방 200만원 알라이아 (luxury 광고)
- 1순위 목걸이 남자 명품 목걸이
- → 사용자 "디자인 비슷한 게 안 나옴"

**케이스 B: 흰 끈나시 + 베이지 카디건 + 와이드 팬츠 (cropped 셀카)**
- Gemini가 끈나시만 detect (카디건 사이드, 팬츠 잘림 → 무시)
- Worker 결과: top_inner만 등장
- → 사용자 "outer/bottom 안 나옴"

**케이스 C: 네이비 체크 셔츠 + 흰 이너 + 데님 미니 쇼츠**
- "체크" 키워드 들어감
- Naver 결과: 단색 셔츠 1순위 (광고)
- "미니 쇼츠" 키워드 들어감
- Naver 결과: 데님 칠부 1순위
- → 사용자 "키워드는 들어갔는데 결과는 다름"

**모든 케이스 공통: 텍스트로는 분류 OK, 시각으로는 매칭 X.**

---

## 9. 비용 / 우선순위 제약

- **현재 사용자 수**: 데모/테스트 단계 (수십~수백/일)
- **목표 사용자 수**: 향후 1만+/일
- **수용 가능 월 비용 (현재)**: $50~200
- **수용 가능 응답 시간 (사용자 인내 한도)**: 5~10초
- **수용 가능한 정확도**: 5/5 (특히 디자인 매칭)

---

## 10. 코드 + 환경 접근

### Repo 구조
```
인앱토스 1/
├── src/                    # React frontend
├── server/                 # CF Worker (Hono, TypeScript)
│   ├── src/worker.ts       # /api/analyze, /api/search/categories 핸들러
│   └── wrangler.toml
├── functions/              # CF Pages Functions
│   └── api/[[route]].ts    # catch-all → import worker.ts
├── fashion-search/         # Cloud Run (Python FastAPI)
│   ├── apps/api/
│   │   ├── main.py
│   │   └── routes_search.py    # /api/search, ML pipeline
│   ├── src/
│   │   ├── embedding/      # FashionCLIP, OpenCLIP embedder
│   │   ├── ranking/        # color_hist, mood_ranker, quadrant_sort
│   │   ├── preprocess/     # gemini_detector, segmentation
│   │   └── search/         # parallel_search, naver_shopping
│   ├── Dockerfile
│   └── deploy.sh
├── docs/                   # 진단 리포트, SESSION 별 PROMPT
└── scripts/                # verify_deploy.sh, overnight_run.ps1
```

### 환경 변수
```
GEMINI_API_KEY        # Gemini 2.5 Flash
NAVER_CLIENT_ID       # Naver Shopping API
NAVER_CLIENT_SECRET
CLOUDFLARE_API_TOKEN  # Pages deploy
GOOGLE_API_KEY        # Cloud Run에서도 Gemini 호출
ADMIN_TOKEN           # 관리자 endpoint
FASHION_SEARCH_URL    # Cloud Run URL (Worker → Cloud Run 호출)
```

### 라이브 endpoint
- Production: https://cloi.pages.dev
- Worker (legacy 단독): https://cloi-api.kyoung361207.workers.dev
- Cloud Run: https://fashion-search-dibvogjuma-du.a.run.app

### 테스트 명령어
```bash
# 응답 직접 확인
curl -X POST https://cloi.pages.dev/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"imageBase64":"...","mimeType":"image/jpeg"}'

# verify 스크립트
bash scripts/verify_deploy.sh fashion-search/eval/queries/q001.jpg

# Cloud Run 직접 (timeout 길게)
curl -X POST -F "file=@image.jpg" \
  https://fashion-search-dibvogjuma-du.a.run.app/api/search \
  --max-time 180
```

---

## 11. 우리가 생각한 옵션 (전문가 검토 부탁)

| 옵션 | 비용 | 처리시간 | 코드 변경 | 위험 |
|-----|-----|---------|---------|------|
| A. Cloud Run에 GPU 추가 (NVIDIA L4) | $200~400/월 | 60s → 5s | 0 | 비용 부담 |
| B. Modal Labs로 ML 부분만 이전 | $50~200/월 | 60s → 5s | Python 데코레이터 | learning curve |
| C. 무료 — 무거운 단계 제거 (rembg, K-means 끄기) | $0 | 60s → 25s | Python 1~2시간 | 정확도 약간 하락 |
| D. ONNX 변환 + 양자화 | $0 (CPU 그대로) | 60s → 15~25s | Python 4~8시간 | 모델 품질 약간 하락 |
| E. 임베딩 영구 캐싱 | $5~20/월 (Redis) | 첫 호출 60s, 이후 3s | DB 추가 | 한국 쇼핑몰 상품 turnover 빠름 |
| F. Progressive UX (병렬 path + UI streaming) | $0 | 5s 초기 + 60s 업데이트 | UI 큰 변경 | 복잡도 |

---

## 12. 부가 정보

### Naver Shopping API 한계
- 한 쿼리당 max display=100, 우리는 20 사용
- popularity bias (광고 우선)
- AND 매칭 안 됨 (OR만)
- 한국 쇼핑몰 거의 다 cover

### FAISS 자체 카탈로그
- ntotal=2725 (Naver에서 미리 수집한 상품)
- 현재 Cloud Run 안에 인메모리, 실제 사용 안 함 (Cloud Run path 미적중으로)
- 향후 자체 인덱스 확장 가능 (10만+)

### Gemini 2.5 Flash 사용량
- 호출당 약 $0.001 (input 1500 tokens + image)
- 일 100명 사용 시 월 $30 정도
- 이건 부담 없음

---

## 13. 요약 — 전문가에게 묻고 싶은 한 가지

> **"FashionCLIP CPU inference를 60개 이미지에 대해 5초 안에 끝내는 방법, 그리고 임베딩 캐싱 전략. 인프라 비용 월 $50~200 안에서 시각 매칭 path 적중률 100% 만드는 길."**

GPU 도입이 답이라면 어느 platform (Cloud Run GPU vs Modal vs AWS) 추천?
GPU 안 쓰고 가능하다면 어떤 최적화 (ONNX, 양자화, 캐싱)?

---

## 14. 참고 — 기존 진단 리포트

상세 분석 필요 시:
- `docs/DIAGNOSIS_S9_REGRESSION.md` — 시각 매칭 회귀 분석
- `docs/USER_EXPERIENCE_REPORT_V2.md` — SESSION 11+12 적용 후 측정
- `docs/DIAGNOSIS_S12_USER_CASE.md` — 사용자 케이스 root cause
- `docs/SESSION_13_PROMPT.md` — 최근 작업 사양

---

# 끝

**예상 자문 시간:** 30분~1시간
**전문가에게 가장 도움 될 자료:** 본 문서 + `fashion-search/apps/api/routes_search.py` (Cloud Run 처리 흐름) + `server/src/worker.ts` (Worker 로직)
