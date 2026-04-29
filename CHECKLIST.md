# 웨어고(Whereго) 개발 체크리스트
> 최종 업데이트: 2026-04-11

---

## 🏗️ 프로젝트 기반 구조

- [x] Vite + React + TypeScript 셋업
- [x] 폴더 구조 확립 (`src/pages`, `src/components`, `src/services`, `src/hooks`, `src/types`)
- [x] 글로벌 CSS (토스 디자인 시스템 변수, 공통 버튼 스타일)
- [x] `.env.example` 생성 (API 키 템플릿)
- [x] `.gitignore` 설정 (`.env`, `*.pem`, `*.key`, `*.crt` 등 보안 파일 제외)
- [x] Vite 개발 서버 프록시 설정 (`/api` → `localhost:3001`)
- [x] 백엔드 서버 구조 (`server/src/`)

---

## 🎨 프론트엔드

### 타입 정의 (`src/types/index.ts`)
- [x] `Product` 인터페이스
- [x] `AnalysisKeywords` 인터페이스
- [x] `SearchResult` 인터페이스
- [x] `HistoryItem` 인터페이스 (P1-3)
- [x] `AppState` 타입 (`home | loading | result | error | favorites`)
- [x] `LoadingStep` 타입
- [x] `AppError` 인터페이스

### 앱 상태 관리 (`src/App.tsx`)
- [x] 페이지 라우팅 (home / loading / result / error / favorites)
- [x] 로딩 단계 관리 (`analyzing` → `searching`)
- [x] 분석 결과 상태 관리 (products, keywords, currentQuery)
- [x] 재시도(retry) 함수 등록 메커니즘
- [x] 더 보기 (페이지네이션, currentOffset)
- [x] 키워드 재검색 핸들러 (P1-5)
- [x] 즐겨찾기 토글 핸들러 (P1-2)
- [x] 검색 이력 저장 핸들러 (P1-3)
- [x] 이력에서 결과 복원 핸들러

### 훅 (`src/hooks/`)
- [x] `useLocalStorage` 훅 (favorites, history 영구 저장)

### 서비스 (`src/services/api.ts`)
- [x] `analyzeImage()` — 이미지 base64 분석 요청
- [x] `analyzeImageUrl()` — URL 분석 요청
- [x] `searchProducts()` — 상품 검색 요청 (페이지네이션 지원)

### 컴포넌트

#### `src/components/ImageUploader.tsx` (P0-1)
- [x] 파일 선택 버튼
- [x] 드래그 앤 드롭 지원
- [x] 파일 형식 검증 (JPG/PNG/WEBP)
- [x] 파일 크기 검증 (최대 10MB)
- [x] base64 변환 후 콜백

#### `src/components/ClipboardBanner.tsx` (P0-3)
- [x] 앱 포그라운드 진입 시 클립보드 감지
- [x] `visibilitychange` 이벤트 처리
- [x] Instagram URL 감지 배너 표시
- [x] "분석하기" 클릭 시 URL 전달

#### `src/components/ProductCard.tsx` (P0-6, P0-7)
- [x] 상품 이미지 (비율 유지)
- [x] 플랫폼 배지 (무신사/에이블리/지그재그)
- [x] HTML 태그 제거 (stripHtml)
- [x] 상품명·가격·쇼핑몰명 표시
- [x] 클릭 시 외부 쇼핑몰 이동 (`window.open`)
- [x] 이미지 오류 시 폴백 SVG
- [ ] 즐겨찾기 하트 버튼 (P1-2) ← **수정 필요**

#### `src/components/ErrorScreen.tsx` (P0-8)
- [x] 에러 코드별 맞춤 제목
- [x] 에러 메시지 표시
- [x] 재시도 버튼 (retryable 조건부)
- [x] 처음으로 돌아가기 버튼

### 페이지

#### `src/pages/LoadingPage.tsx` (P0-8)
- [x] 단계 인디케이터 (분석 중 / 상품 찾는 중)
- [x] 점 애니메이션
- [x] pulse 애니메이션

#### `src/pages/HomePage.tsx` (P0-1, P0-2, P0-3, P1-3)
- [x] 헤더 (타이틀 + 즐겨찾기 버튼)
- [x] 클립보드 배너
- [x] 이미지 업로드 섹션
- [x] 이미지 미리보기 + 삭제 버튼
- [x] 분석 실행 (이미지)
- [x] 인스타그램 링크 입력 섹션
- [x] Instagram URL 유효성 검사
- [x] 분석 실행 (URL)
- [x] 최근 검색 이력 목록

#### `src/pages/ResultPage.tsx` (P0-6, P1-1, P1-2, P1-4, P1-5)
- [x] 헤더 (뒤로가기 + 결과 수)
- [x] 키워드 태그 목록
- [x] 2열 상품 그리드
- [x] 더 보기 버튼
- [x] 다른 옷 찾기 버튼
- [x] 즐겨찾기 토글 (P1-2) ← **수정 완료**
- [x] 키워드 수정 → 재검색 (P1-5) ← **수정 완료**
- [x] 가격·플랫폼 필터 (P1-1) ← **추가 완료**
- [x] 공유하기 버튼 (P1-4) ← **추가 완료**

#### `src/pages/FavoritesPage.tsx` (P1-2)
- [x] 즐겨찾기 목록 (2열 그리드) ← **신규 생성**
- [x] 비어있을 때 안내 메시지
- [x] 즐겨찾기 해제 버튼
- [x] 뒤로가기 버튼

---

## ⚙️ 백엔드 서버 (`server/`)

### 서버 설정 (`server/src/index.ts`)
- [x] Express 서버 설정
- [x] CORS 설정 (개발/프로덕션 분리)
- [x] 요청 크기 제한 (15MB)
- [x] API 키 마스킹 로그 (보안 - 값 노출 없음)
- [x] 헬스체크 엔드포인트 (`/api/health`)
- [x] 404 / 전역 에러 핸들러

### 라우터

#### `server/src/routes/analyze.ts` (P0-4)
- [x] `POST /api/analyze` — base64 이미지 분석
- [x] 입력 유효성 검증 (imageBase64, mimeType)
- [x] 이미지 크기 검증 (14MB 이하)

#### `server/src/routes/analyzeUrl.ts` (P0-2)
- [x] `POST /api/analyze-url` — URL 이미지 분석
- [x] URL 유효성 검증
- [x] Instagram 게시물 URL 분기 처리 (스크래핑 미지원 안내)

#### `server/src/routes/search.ts` (P0-5)
- [x] `POST /api/search` — 네이버 쇼핑 검색
- [x] 키워드/쿼리 유효성 검증
- [x] 페이지네이션 (start 파라미터)

### 서비스

#### `server/src/services/gemini.ts` (P0-4)
- [x] `analyzeImageWithGemini()` — base64 이미지 분석
- [x] `analyzeImageUrlWithGemini()` — URL 이미지 분석
- [x] 패션 분석 프롬프트 (색상, 실루엣, 소재, 스타일, 아이템 종류)
- [x] 마크다운 코드블록 제거 후 JSON 파싱
- [x] `IMAGE_QUALITY` 에러 처리
- [x] 재시도 로직 (Gemini 5초 타임아웃)

#### `server/src/services/naverShopping.ts` (P0-5)
- [x] `searchNaverShopping()` — 네이버 쇼핑 검색
- [x] 키워드 조합 검색 최적화
- [x] HTML 태그 제거
- [x] 5초 타임아웃
- [x] 401 인증 오류 처리

---

## 🔐 보안 체크리스트

- [x] `.env` 파일 `.gitignore` 포함
- [x] `.env.example` 제공 (실제 값 없음)
- [x] API 키를 서버사이드에서만 사용 (프론트엔드 노출 없음)
- [x] Vite 프록시로 키 보호 (클라이언트 → 서버 → 외부 API)
- [x] API 키 로그는 마스킹 처리
- [x] 요청 크기 제한으로 DoS 방어
- [x] `noopener,noreferrer` 외부 링크 보안
- [x] `*.pem`, `*.key`, `*.crt` `.gitignore` 포함

---

## 📦 빌드 / 배포

- [x] `npm run dev` — 프론트+서버 동시 실행 (concurrently)
- [x] `npm run build` — 프론트 빌드
- [ ] `npm run build:server` — 서버 빌드 테스트
- [ ] 프로덕션 배포 설정 (예: Railway, Fly.io 등)

---

## ✅ PRD 요구사항 달성 현황

| 항목 | 기능 | 상태 |
|------|------|------|
| P0-1 | 이미지 업로드 (JPG/PNG/WEBP, 최대 10MB) | ✅ 완료 |
| P0-2 | 인스타그램 링크 입력 | ✅ 완료 (직접 이미지 URL 지원, 게시물 링크 안내) |
| P0-3 | 클립보드 자동 감지 | ✅ 완료 |
| P0-4 | Gemini 키워드 추출 | ✅ 완료 |
| P0-5 | 네이버 쇼핑 API 검색 | ✅ 완료 |
| P0-6 | 상품 카드 UI | ✅ 완료 |
| P0-7 | 외부 구매 링크 연결 | ✅ 완료 |
| P0-8 | 로딩 및 에러 처리 | ✅ 완료 |
| P1-1 | 결과 필터링 (가격대·플랫폼) | ✅ 완료 |
| P1-2 | 상품 즐겨찾기 | ✅ 완료 |
| P1-3 | 분석 이력 | ✅ 완료 |
| P1-4 | 공유하기 | ✅ 완료 |
| P1-5 | 결과 피드백/키워드 수정 | ✅ 완료 |

---

## 🚀 Phase 2: 독립 웹서비스 (`fashion-search/`)
> CLAUDE_fashion_search_optimized.md 기반 | FastAPI + OpenCLIP + FAISS + SAM2
> **최종 완료: 2026-04-14**

### Day 1 — 프로젝트 구조 + Core 인터페이스

- [x] `fashion-search/` 루트 디렉토리 생성
- [x] `requirements.txt` (버전 고정)
- [x] `pyproject.toml`
- [x] `.env.example`
- [x] `CLAUDE.md` (프로젝트 컨텍스트)
- [x] `src/config/settings.py` (Pydantic BaseSettings)
- [x] `src/search/vector_store.py` (ABC: build, search, save, load, add)
- [x] `src/search/faiss_store.py` (IndexIVFFlat 구현)
- [x] `src/llm/gemini_client.py` (tenacity retry 포함)
- [x] `src/llm/gemini_extract.py` (GarmentAttributes Pydantic schema)
- [x] `src/cache/result_cache.py` (SQLite, image_hash → result JSON, 24h TTL)
- [x] `apps/api/main.py` (FastAPI lifespan 모델 preload)
- [x] `apps/api/schemas.py` (SearchRequest, SearchResponse)
- [x] `src/data/rights/rights_matrix.csv` (브랜드 계약 헤더)
- [x] `src/data/contracts/` (브랜드 계약 디렉토리)

### Day 2-3 — Vision 파이프라인

- [x] `src/vision/detect_gdino.py` (groundingdino-unofficial PyPI)
- [x] `src/vision/segment_sam2.py` (SAM2 PyPI, bbox → GarmentCrop)
- [x] `src/vision/cropper.py` (bbox → crop PNG)
- [x] `src/vision/pipeline.py` (async detect+segment 통합)

### Day 4-5 — 임베딩 + FAISS 검색

- [x] `src/embedding/openclip_embed.py` (ViT-L-14, batch_size=32, L2 정규화)
- [x] `src/embedding/query_embed.py`
- [x] `src/embedding/catalog_embed_job.py` (배치+체크포인트)
- [x] `src/search/retrieve.py` (async search, VectorStore inject)
- [x] `scripts/build_catalog_index.py` (tqdm + 체크포인트)

### Day 6-7 — 검색 엔드포인트 + Reranker

- [x] `src/search/rerank.py` (가중치: 0.55*sim + 0.10*cat + 0.10*color + ...)
- [x] `apps/api/routes_search.py` (`/search` 병렬 파이프라인, asyncio.gather)

### Day 8 — Admin + 스모크 테스트 + 평가

- [x] `apps/api/routes_admin.py` (catalog add/rebuild/stats)
- [x] `scripts/smoke_test.py` (3장 이미지, latency 측정)
- [x] `scripts/add_catalog_item.py` (증분 추가)
- [x] `scripts/setup_env.sh`
- [x] `eval/metrics.py` (Recall@10, Recall@50, MRR, Category Precision)
- [x] `src/llm/gemini_explain.py` (결과 설명 생성, 옵션)
- [x] `src/search/milvus_store.py` (TODO stub, 인터페이스 준수)
- [x] `docs/legal_data_policy.md`
- [x] `docs/system_design.md`
- [x] `docs/data_rights_template.md`

### 진행 현황
| 단계 | 상태 |
|------|------|
| Day 1: 구조 + Core 인터페이스 | ✅ 완료 |
| Day 2-3: Vision 파이프라인 | ✅ 완료 |
| Day 4-5: 임베딩 + FAISS | ✅ 완료 |
| Day 6-7: 검색 엔드포인트 | ✅ 완료 |
| Day 8: Admin + 테스트 + 평가 | ✅ 완료 |

---

## 🔗 Phase 3: Node.js ↔ Python API 연동 (Sprint 3)
> **완료: 2026-04-22** | Node.js 프록시 + 프론트엔드 v2 UI

### 구현 완료 항목

| 파일 | 변경 내용 | 상태 |
|------|-----------|------|
| `server/src/routes/analyze.ts` | FASHION_API_URL 환경변수 시 Python API 프록시, Gemini fallback 유지 | ✅ |
| `server/src/routes/analyze.ts` | `POST /api/analyze/click/:imageHash/:productId` 클릭 이벤트 프록시 | ✅ |
| `src/types/index.ts` | `StyleContext`, `ProductCardV2`, `SearchResponseV2` 타입 추가 | ✅ |
| `src/services/api.ts` | `analyzeImage` v2 응답 지원, `recordClick()` 함수 추가 | ✅ |
| `src/pages/HomePage.tsx` | v2 응답 감지 → searchByCategories 생략, 카테고리 매핑 | ✅ |
| `src/App.tsx` | `v2Response` 상태 추가, ResultPage에 전달 | ✅ |
| `src/pages/ResultPage.tsx` | free-form 카테고리 탭, latency/cached 뱃지, 클릭 추적 | ✅ |

### 환경변수 설정
```
# .env (루트)
FASHION_API_URL=http://localhost:8000   # Python API 사용 시 설정. 미설정 시 Gemini fallback.
```

---

## 🗺️ 시스템 아키텍처 — 유저 사진이 어디로 가는가

```
[유저]
  │
  │  사진 업로드 (JPG/PNG/WEBP, 최대 10MB)
  ▼
[프론트엔드 — Vite/React, localhost:5173]
  │  base64 인코딩
  │  POST /api/analyze  { imageBase64, mimeType }
  ▼
[Node.js 백엔드 — Express, localhost:3001]
  │
  ├─ FASHION_API_URL 설정됨?
  │    YES ──────────────────────────────────────────────┐
  │                                                      │
  │    NO (Gemini 직접 호출 fallback)                    │
  │      │                                               │
  │      ▼                                               ▼
  │  [Gemini API]                         [Python API — FastAPI, localhost:8000]
  │  키워드 추출                            │
  │  → categories JSON                     │  1. SHA256 해시로 캐시 확인 (SQLite)
  │                                        │  2. Gemini 2.5 Flash: 전체 이미지 스타일 분석
  │  POST /api/search/categories           │     → StyleContext { overall_style, mood_tags, items }
  │  → Naver Shopping 검색                 │  3. asyncio.gather: 아이템별 네이버쇼핑 병렬 검색
  │  → CategorySearchResult[]             │  4. OpenCLIP ViT-L/14: 썸네일 유사도 필터 (min 0.20)
  │                                        │  5. 응답 캐시 저장 (24h TTL)
  │                                        │     → SearchResponseV2 { style_context, results, cached, latency_ms }
  │                                        │
  │    ◄───────────────────────────────────┘
  │  Node.js: { ...SearchResponseV2, _source:'v2', _imageHash }
  │
  ▼
[프론트엔드 — ResultPage]
  │
  ├─ v2Response 있음 → free-form 카테고리 탭 (후드티 | 스니커즈 | 와이드팬츠 ...)
  │                    latency_ms + cached 뱃지 표시
  │                    상품 클릭 → POST /api/analyze/click/:hash/:id (클릭 추적)
  │
  └─ v2Response 없음 → 기존 FashionCategory 탭 (상의 | 하의 | 신발 ...)
                       키워드 수정 / 더 보기 기능 유지
```

---

## 🏛️ 서버 관계도

```
┌─────────────────────────────────────────────────────────────────┐
│                      Toss 미니앱 (프론트엔드)                      │
│                   Vite + React + TypeScript                      │
│                       localhost:5173                             │
└───────────────────────────┬─────────────────────────────────────┘
                            │  /api/* (Vite 프록시)
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Node.js 백엔드 서버                            │
│                  Express (server/src/)                           │
│                       localhost:3001                             │
│                                                                  │
│  /api/analyze       → routes/analyze.ts (이미지 분석 프록시)      │
│  /api/analyze-url   → routes/analyzeUrl.ts (URL 분석)           │
│  /api/search        → routes/search.ts (Naver 쇼핑 검색)        │
│  /api/health        → inline (헬스체크)                          │
│                                                                  │
│  FASHION_API_URL 설정 시: Python API로 포워딩                     │
│  미설정 시: Gemini + Naver 직접 호출 (fallback)                   │
└───────┬──────────────────────────────────┬────────────────────┘
        │ FASHION_API_URL=http://...8000    │ fallback
        ▼                                  ▼
┌───────────────────────────┐   ┌──────────────────────────────┐
│   Python API (fashion-search/) │   │   외부 API                   │
│   FastAPI, localhost:8000  │   │   - Gemini (google-genai)    │
│                            │   │   - Naver Shopping API       │
│  /api/search POST          │   └──────────────────────────────┘
│  /api/search/{h}/click/{p} │
│  /admin/catalog/*          │
│  /health                   │
│                            │
│  내부 파이프라인:           │
│  Gemini 2.5 Flash          │
│  → Naver Shopping API      │
│  → OpenCLIP ViT-L/14       │
│  → FAISS IVFFlat (2725개)  │
│  → SQLite 캐시 (24h TTL)   │
└───────────────────────────┘

유저 사진 저장 경로:
  - 카탈로그 자동 추가: fashion-search/src/data/catalog/images/{sha256}.jpg
  - Python 캐시 DB:     fashion-search/artifacts/search_cache.db
  - 검색 로그 DB:       fashion-search/artifacts/search_logs.db
  - FAISS 인덱스:       fashion-search/artifacts/catalog.index
```

---

## ✅ 전체 진행률

```
Phase 1 (토스 미니앱 기본):  ████████████████████  100%  완료
Phase 2 (Python ML 파이프):  ████████████████████  100%  완료
Phase 3 (연동 + 프론트 v2):  ████████████████████  100%  완료
```

| 서버 | 실행 명령 | 상태 확인 |
|------|-----------|-----------|
| 프론트엔드 | `npm run dev` | http://localhost:5173 |
| Node.js 서버 | `npm run server` | http://localhost:3001/api/health |
| Python API | `fashion-search/.venv/Scripts/python.exe -m uvicorn apps.api.main:app --host 0.0.0.0 --port 8000` | http://localhost:8000/health |