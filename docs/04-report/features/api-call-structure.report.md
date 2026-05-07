# 완료 보고서: 웨어고 API 호출 구조 개선

> **Feature**: api-call-structure  
> **작업일**: 2026-04-13  
> **Phase**: 긴급 버그픽스 + 구조 개선 (단일 세션)  
> **작업자**: Claude Code (Sonnet 4.6)

---

## Executive Summary

### 1.1 개요

| 항목 | 내용 |
|------|------|
| Feature | API 호출 구조 개선 (api-call-structure) |
| 작업일 | 2026-04-13 |
| 작업 유형 | 긴급 버그픽스 + 구조 개선 |
| 변경 파일 수 | 6개 |

### 1.2 결과 요약

| 항목 | 결과 |
|------|------|
| 버그 수정 | 2건 (429 오류 노출, 더블클릭 경쟁 조건) |
| 기능 추가 | 1건 (이미지 분석 캐싱) |
| 설정 수정 | 2건 (server/.env, CORS 검증) |
| 서버 상태 | 정상 운영 확인 (`gemini: true`, `naver: true`) |

### 1.3 Value Delivered (4-Perspective)

| 관점 | 문제 | 해결 | 기능/UX 효과 | 핵심 가치 |
|------|------|------|-------------|----------|
| 안정성 | Gemini 429 에러가 500으로 노출, 내부 API URL·quota 상세 클라이언트에 유출 | 에러 코드별 올바른 HTTP 상태코드(429/422/403/500) 반환, 사용자 친화적 메시지로 교체 | 에러 화면에 "AI 분석 요청이 너무 많아요. 잠시 후 다시 시도해 주세요." 표시 | 보안 강화 + UX 개선 |
| 성능 | 같은 이미지를 다시 업로드할 때마다 Gemini API 재호출 (할당량 낭비) | 모듈 레벨 Map 캐시 추가 (세션 내 동일 이미지/URL 캐싱) | 동일 이미지 재분석 시 즉시 응답 (API 호출 0회) | Gemini quota 절약 |
| 신뢰성 | React state 업데이트 비동기 특성으로 더블클릭 시 중복 API 호출 가능 | `useRef` 동기 플래그 추가로 경쟁 조건 완전 차단 | 버튼 연타해도 분석 1회만 실행 | API 호출 중복 방지 |
| 운영 | `server/.env`에 플레이스홀더 값으로 인한 혼란 가능성 | 실제 키 값으로 동기화 (gitignore 적용 확인 후 진행) | 서버 재시작 시 키 인식 문제 없음 | 운영 안정성 |

---

## 1. 현재 API 호출 구조

### 전체 흐름도

```
[프론트엔드 - localhost:5173]
        │
        │ Vite Proxy (/api → localhost:3001)
        ↓
[백엔드 서버 - localhost:3001]
        ├─ POST /api/analyze      → Gemini Flash 2.0 API
        ├─ POST /api/analyze-url  → Gemini Flash 2.0 API (URL 경유)
        ├─ POST /api/search       → 네이버 쇼핑 API
        └─ GET  /api/health       → 상태 확인
```

### 호출 시나리오별 상세

```
[시나리오 1] 이미지 업로드 → 분석 → 검색
버튼 클릭
  ├─ isAnalyzingRef.current 체크 (동기, 더블클릭 차단)
  └─ runAnalysis()
       ├─ 1. analyzeImage() → 캐시 HIT? 즉시 반환 : POST /api/analyze (Gemini)
       └─ 2. searchProducts() → POST /api/search (Naver, 20개)

[시나리오 2] 인스타그램 URL → 분석 → 검색
버튼 클릭
  └─ runAnalysis()
       ├─ 1. analyzeImageUrl() → 캐시 HIT? 즉시 반환 : POST /api/analyze-url (Gemini)
       └─ 2. searchProducts() → POST /api/search (Naver, 20개)

[시나리오 3] 결과 페이지 "더 보기"
더 보기 클릭
  └─ handleLoadMore() → POST /api/search (Naver, start=21, 20개씩 페이지네이션)

[시나리오 4] 키워드 수정 후 재검색
다시 검색 클릭
  └─ handleReSearch() → POST /api/search (Naver, 수정된 키워드로)
```

### 캐시 구조

```typescript
// src/services/api.ts (모듈 레벨 — 세션 동안 유지)
const analysisCache = new Map<string, AnalysisKeywords>();

// 캐시 키 전략
// 이미지: "img:{length}|{앞64자}|{뒤64자}"   → 전체 base64 메모리 낭비 방지
// URL:   "url:{imageUrl}"                    → URL 자체가 유일 키
```

---

## 2. 이번 세션 작업 목록

### 2.1 환경 설정

| 작업 | 파일 | 결과 |
|------|------|------|
| `server/.env` 플레이스홀더 → 실제 키 동기화 | `server/.env` | 완료 ✅ |
| gitignore `server/.env` 적용 확인 | `.gitignore:2` | `.env` 패턴으로 차단 확인 ✅ |
| CORS preflight 응답 검증 | `server/src/index.ts` | `Access-Control-Allow-Origin: http://localhost:5173` 확인 ✅ |

### 2.2 버그 수정

#### BUG-01: Gemini 429 에러 → 500으로 오반환 + 내부 정보 노출

**원인**: `analyze.ts`, `analyzeUrl.ts` catch 블록에서 에러 구분 없이 500 반환 + `error.message` 원문 노출

**수정 내용**:

```typescript
// server/src/services/gemini.ts — 재시도 소진 시 코드 부여
if (is429) {
  throw Object.assign(
    new Error('AI 분석 요청이 너무 많아요. 잠시 후 다시 시도해 주세요.'),
    { code: 'QUOTA_EXCEEDED' },
  );
}

// server/src/routes/analyze.ts — 코드별 올바른 HTTP 상태코드
if (error.code === 'QUOTA_EXCEEDED') return res.status(429).json(...)
if (error.code === 'IMAGE_QUALITY')  return res.status(422).json(...)
return res.status(500).json({ message: '이미지 분석 중 오류가 발생했어요.' })
```

**결과**: 500 → 429, 내부 API URL 노출 제거 ✅

#### BUG-02: 더블클릭 경쟁 조건

**원인**: `isAnalyzing` React state는 비동기 업데이트 → 재렌더 전 두 번째 클릭이 guard를 통과할 수 있음

**수정 내용**:

```typescript
// src/pages/HomePage.tsx
const isAnalyzingRef = useRef(false);

const runAnalysis = async (...) => {
  if (isAnalyzingRef.current) return;  // 동기 차단
  isAnalyzingRef.current = true;
  // ...
  finally { isAnalyzingRef.current = false; }
};
```

**결과**: 동기 플래그로 중복 호출 완전 차단 ✅

### 2.3 기능 추가

#### FEAT-01: 이미지 분석 결과 캐싱

**수정 내용**:

```typescript
// src/services/api.ts
const analysisCache = new Map<string, AnalysisKeywords>();

function imageCacheKey(base64: string): string {
  return `${base64.length}|${base64.slice(0, 64)}|${base64.slice(-64)}`;
}

export async function analyzeImage(imageBase64, mimeType) {
  const cacheKey = `img:${imageCacheKey(imageBase64)}`;
  if (analysisCache.has(cacheKey)) return analysisCache.get(cacheKey)!;  // 캐시 HIT
  // ... API 호출 후 캐싱
  analysisCache.set(cacheKey, data);
  return data;
}
```

**효과**: 동일 이미지 재업로드 시 Gemini API 호출 0회 → quota 절약 ✅

---

## 3. 변경 파일 목록

| 파일 | 변경 유형 | 주요 내용 |
|------|----------|----------|
| `server/.env` | 수정 | 플레이스홀더 → 실제 API 키 동기화 |
| `server/src/services/gemini.ts` | 수정 | 429 소진 시 `QUOTA_EXCEEDED` 코드로 throw |
| `server/src/routes/analyze.ts` | 수정 | 에러 코드별 올바른 HTTP 상태코드 반환 |
| `server/src/routes/analyzeUrl.ts` | 수정 | 에러 코드별 올바른 HTTP 상태코드 반환 (PRIVATE_ACCOUNT 포함) |
| `src/services/api.ts` | 수정 | 모듈 레벨 분석 결과 캐시 추가 |
| `src/pages/HomePage.tsx` | 수정 | `useRef` 더블클릭 차단 플래그 추가 |

---

## 4. 검증 결과

| 검증 항목 | 방법 | 결과 |
|----------|------|------|
| 서버 헬스체크 | `GET /api/health` | `{"status":"ok","apis":{"gemini":true,"naver":true}}` ✅ |
| Naver 검색 API | `POST /api/search` | 상품 목록 정상 반환 ✅ |
| CORS preflight | `OPTIONS /api/search` with Origin | `204 + Access-Control-Allow-Origin` ✅ |
| 429 에러 핸들링 | `POST /api/analyze` (quota 초과 상태) | `{"message":"AI 분석 요청이 너무 많아요...","code":"QUOTA_EXCEEDED"}` ✅ |
| HTTP 상태코드 | 위 동일 | 500 → **429** ✅ |

---

## 5. 남은 이슈

| 이슈 | 심각도 | 설명 |
|------|--------|------|
| Gemini 무료 티어 quota 소진 | 높음 | 이미지 분석 기능 현재 사용 불가. Google AI Studio에서 결제 추가 필요 |
| 캐시 만료 정책 없음 | 낮음 | 세션 새로고침 시 캐시 초기화됨 (현재는 충분) |

---

## 6. 권장 다음 단계

1. **Gemini API 결제 설정** — Google AI Studio에서 무료 티어 → 유료 전환
2. **전체 플로우 E2E 테스트** — quota 해결 후 이미지 업로드 → 분석 → 검색 전체 검증
3. **에러 화면 UX 개선** — 429 시 "잠시 후 다시 시도" 버튼 + 남은 시간 표시 고려
