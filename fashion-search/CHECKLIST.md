# Fashion Search v2 — 구현 현황 체크리스트

> 기준 문서: `CLAUDE_fashion_search_v2.md`
> 업데이트: 2026-04-22

---

## 범례
```
[x] 구현 완료
[ ] 미구현 (해야 할 것)
[V] 지금 바로 실행해서 확인 가능
```

---

## 1단계 — 환경 & 전제조건 (v2.md Section 10)

| 항목 | 상태 | 비고 |
|------|------|------|
| `GOOGLE_API_KEY` .env 저장 | [x] | AIzaSy... 확인 |
| `NAVER_CLIENT_ID` .env 저장 | [x] | Z8X01b... 확인 |
| `NAVER_CLIENT_SECRET` .env 저장 | [x] | C8d7tC... 확인 |
| `.venv` Python 환경 | [x] | Python 3.13, torch 2.6+cpu |
| `httpx>=0.28.1` 설치 | [x] | google-genai 1.73.1 호환 |
| `aiosqlite==0.20.0` 설치 | [x] | 비동기 SQLite |
| ML 패키지 (torch, faiss, open_clip, google-genai) | [x] | .venv에 모두 설치됨 |

---

## 2단계 — 파이프라인 구현 (v2.md Section 4 기준)

### 4.1 Gemini 스타일 분석 (`src/llm/style_analyzer.py`)

| 항목 | 상태 |
|------|------|
| 이미지 전체 1회 호출 (crop 없음) | [x] |
| `StyleContext` JSON 구조화 응답 (`response_schema`) | [x] |
| tenacity retry 3회 | [x] |
| `asyncio.to_thread` (blocking SDK 비동기 처리) | [x] |

### 4.2 네이버쇼핑 병렬 검색 (`src/search/parallel_search.py`)

| 항목 | 상태 |
|------|------|
| `build_search_query` — overall_style + category + color + fit 조합 | [x] |
| `asyncio.gather()` 아이템별 동시 검색 | [x] |
| 예외 발생 시 빈 리스트 반환 (전체 중단 방지) | [x] |
| HTML 태그 제거 (`<b>`, `</b>` 등 네이버 응답 정제) | [x] |

### 4.3 CLIP 유사도 필터 (`src/ranking/clip_filter.py`)

| 항목 | 상태 |
|------|------|
| 쿼리 이미지 1회 인코딩 | [x] |
| 썸네일 병렬 다운로드 (httpx AsyncClient) | [x] |
| 배치 임베딩 (기존 `openclip_embed.py` 재사용 — 모델 중복 로딩 없음) | [x] |
| 코사인 유사도 계산 + `min_similarity=0.20` 필터 | [x] |
| 카테고리별 TOP K 반환 | [x] |

### 4.4 검색 엔드포인트 (`apps/api/routes_search.py`)

| 항목 | 상태 |
|------|------|
| `POST /api/search` — multipart/form-data 이미지 업로드 | [x] |
| 이미지 해시 캐시 확인 (HIT시 Gemini 미호출) | [x] |
| Gemini → 네이버쇼핑 → CLIP 풀 파이프라인 연결 | [x] |
| `POST /api/search/{hash}/click/{product_id}` — 클릭 기록 | [x] |
| `GET /api/popular` — CTR 기준 인기 TOP N | [x] |

### 4.5 FastAPI 앱 (`apps/api/main.py`)

| 항목 | 상태 |
|------|------|
| lifespan — 시작 시 CLIP 모델 preload | [x] |
| lifespan — Gemini 클라이언트 초기화 | [x] |
| lifespan — 검색 로그 DB 초기화 (`init_db`) | [x] |
| lifespan — FAISS 인덱스 로드 (admin 라우터용) | [x] |
| CORS 미들웨어 (`allow_origins=["*"]`) | [x] |

---

## 3단계 — DB / 캐시 / 로그 (v2.md Section 3.3)

| 항목 | 상태 |
|------|------|
| `search_cache` 테이블 (image_hash, TTL 24h) | [x] |
| `search_logs` 테이블 (image_hash, style_context, results) | [x] |
| `product_clicks` 테이블 (image_hash, product_id, category) | [x] |
| `get_popular_items` — CTR = click/search, search_count >= 3 필터 | [x] |
| 캐시 HIT시 Gemini 호출 없음 (비용 절감) | [x] |

---

## 4단계 — 스키마 (v2.md Section 3)

| 스키마 | 파일 | 상태 |
|--------|------|------|
| `ItemDetail` (category, color, fit, material) | `src/llm/schemas.py` | [x] |
| `StyleContext` (overall_style, mood_tags, items, confidence) | `src/llm/schemas.py` | [x] |
| `ProductCard` (product_id, title, price, image_url, link, platform, category, similarity_score) | `apps/api/schemas.py` | [x] |
| `SearchResponse` (style_context, results dict, cached, latency_ms) | `apps/api/schemas.py` | [x] |
| `PopularItem` (category, product_id, title, search_count, click_count, ctr) | `apps/api/schemas.py` | [x] |

---

## 5단계 — 서버 기동 검증

| 항목 | 상태 | 실측값 |
|------|------|--------|
| uvicorn 기동 성공 | [x] | 에러 없음 |
| CLIP 모델 로드 | [x] | clip_loaded: true |
| FAISS 인덱스 로드 | [x] | faiss_size: 2725 |
| /health 응답 | [x] | {"status":"ok","version":"2.0.0"} |
| /api/popular 응답 | [x] | [] (로그 없음 — 정상) |
| /docs Swagger UI | [x] | 7개 엔드포인트 등록 확인 |
| smoke_test --mock | [x] | All [OK] (250ms) |

---

## Sprint 3 — 프론트엔드 UI (v2.md Section 7)

| 항목 | 우선순위 | 상태 |
|------|---------|------|
| 프론트엔드 프레임워크 결정 (Next.js 권장) | P0 | [ ] |
| 이미지 업로드 UI (multipart -> POST /api/search) | P0 | [ ] |
| 상품 카드 컴포넌트 (이미지 + 가격 + 쇼핑몰 링크) | P0 | [ ] |
| 카테고리 탭 UI (후드티 / 바지 / 스니커즈 전환) | P1 | [ ] |
| 스타일 분석 결과 표시 (overall_style, mood_tags) | P1 | [ ] |
| 상품 클릭 -> POST /api/search/{hash}/click/{id} 연결 | P1 | [ ] |
| 인기 TOP 10 화면 (GET /api/popular 연동) | P2 | [ ] |
| 모바일 반응형 레이아웃 | P2 | [ ] |

---

## 기타 미구현

| 항목 | 상태 |
|------|------|
| 실 이미지 E2E 테스트 (Gemini + Naver + CLIP 실 응답 확인) | [ ] |
| 배포 설정 (Docker / Railway / Fly.io) | [ ] |
| 에러 모니터링 (Sentry 또는 로그 파일) | [ ] |
| 네이버쇼핑 API Rate Limit 대응 (일 25,000건 한도) | [ ] |
| CLIP threshold 튜닝 (현재 0.20 — 실 결과 보고 조정) | [ ] |
| 캐시 TTL 튜닝 (현재 24h) | [ ] |

---

## 지금 바로 실행해서 확인할 수 있는 것 [V]

> 서버를 먼저 켜야 합니다:
> ```
> .venv\Scripts\python.exe -m uvicorn apps.api.main:app --host 0.0.0.0 --port 8000
> ```

```
[V-1] 서버 Health 확인
curl http://localhost:8000/health
예상: {"status":"ok","version":"2.0.0","clip_loaded":true,"faiss_size":2725}

[V-2] Swagger UI 확인
브라우저: http://localhost:8000/docs
예상: 7개 엔드포인트 나열됨

[V-3] Mock 스모크 테스트 (서버 없이)
.venv\Scripts\python.exe -m scripts.smoke_test --mock
예상: Gemini/Naver/CLIP 단계 모두 [OK]

[V-4] 실제 이미지 업로드 검색 (패션 사진 필요)
curl -X POST http://localhost:8000/api/search -F "file=@사진경로.jpg"
예상: style_context + results(카테고리별 상품 목록) JSON 반환

[V-5] Admin 카탈로그 통계
curl http://localhost:8000/admin/catalog/stats
예상: {"total_products":2725,"last_built_at":"...","index_size_mb":...}

[V-6] 인기 상품 (검색 후)
curl http://localhost:8000/api/popular
예상: 검색 누적 후 CTR 기준 상품 목록 반환 (지금은 [] — 정상)
```

---

## 전체 진행률

```
구현 완료  ████████████████████░░░░░  Sprint 1 + Sprint 2 = 백엔드 100%
미구현     ░░░░░░░░░░░░░░░░████████░  Sprint 3 = 프론트엔드 0%

백엔드 API:  7 / 7 엔드포인트 완성
프론트엔드:  0 / 8 화면 완성
```
