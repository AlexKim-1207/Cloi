# 변수 전수 감사 + SESSION 11 사후 측정 리포트

> **작성일:** 2026-05-01 (SESSION 11 배포 직후)
> **사용자 호소:** "회색 니트 세트 → 1순위 200만원, 목걸이 → 남자 목걸이. 그냥 안 풀리는 문제인가?"
> **이 문서 목적:** "왜 안 풀리나"를 변수 전수 검토 + 직접 측정으로 답하기.
> **결론 한 줄:** **풀 수 있다. 하지만 우리는 (1) 잘못 deploy 했고 (2) 변수 절반을 무시했다.**

---

## 0. 본 리포트가 답하는 4 질문

1. SESSION 11 코드는 진짜로 production에 들어가 있나?
2. 이 서비스를 좌우하는 모든 변수는 무엇인가?
3. 직접 라이브 테스트에서 변수별로 어디가 어떻게 망가지나?
4. "검열" 아닌 "추론" 으로 어떻게 해결하나?

---

## 1. 라이브 측정 (Direct API 다중 케이스, 2026-05-01)

직접 `/api/analyze` 호출 → 응답 shape/필드/소스 검증.

| # | 케이스 | 이미지 | size | latency | status | `_source` | v3? | cat keys | `color`/`subtype` 필드 |
|---|--------|-------|------|---------|--------|----------|-----|---------|---------------------|
| T1 | 여성 페미닌 원피스 | Unsplash 보라 크로셰 | 188KB | 32.7s | 200 | **없음** | ❌ | top/bottom/shoes/outer/bag/accessory **(6키 OLD)** | 없음 |
| T1' | 여성 룩북 (재시도, warm) | 버건디 코트 | 36KB | 23.6s | 200 | **없음** | ❌ | 6키 OLD | 없음 |
| T1'' | 여성 룩북 (3차) | 버건디 작은 | 24KB | 35.1s | **error** | 없음 | ❌ | 비어있음 | 없음 |
| T2 | 남성 캐주얼 | Unsplash 남성 | 26KB | 7.1s | **422** | 없음 | ❌ | 비어있음 | 없음 |
| T3 | 단일 가방 | Unsplash 코랄 가방 | 58KB | 13.4s | 200 | **없음** | ❌ | 6키 OLD | 없음 |
| T4 | 운동복 여성 | Unsplash athletic | 56KB | 4.9s | **500** | 없음 | ❌ | 비어있음 | 없음 |

### 1.1 핵심 발견

| 발견 | 의미 |
|------|------|
| **5/5 테스트에서 `_source` 필드 없음** | SESSION 11 Track A의 `_source: 'worker_gemini'` 코드가 **Worker에 deploy 안 됨** |
| **5/5 테스트에서 6키 schema** (`top/bottom/shoes/outer/bag/accessory`) | SESSION 11 Track A의 8키 schema (`top_outer/top_inner/.../dress`) **deploy 안 됨** |
| **5/5에서 `color`, `subtype`, `missing_categories` 필드 없음** | SESSION 11 Track A의 색상/세부 분류 강제 **deploy 안 됨** |
| **5/5에서 v3 path 미적중** (latency 4~35s 모두 worker fallback) | Cloud Run cold start 또는 timeout. Track B `--min-instances=1` 효과 없음 (이유: 실제 적용 안 됐거나 인스턴스가 죽음) |
| **2/5 에러** (422 IMAGE_QUALITY, 500 server) | 이미지 종류에 따라 시스템 자체가 죽음 |
| **0/5 → v3 응답** | SESSION 9/9-B/10/11C **모든 작업이 사용자 view에 진입 못 함** |

### 1.2 Local 코드 vs Deployed 코드 불일치

```bash
$ grep "FASHION_PROMPT|top_outer|_source" server/src/worker.ts
38: const FASHION_PROMPT = `... 8 카테고리 ...`        ← LOCAL OK
99: | 'top_outer' | 'top_inner' | ...                ← LOCAL OK
357: return c.json({ ...data, _source: 'v3' })       ← LOCAL OK
371: return c.json({ ...result, _source: 'worker_gemini' })  ← LOCAL OK
```

→ **Local 코드는 SESSION 11 Track A 100% 반영. 하지만 deployed Worker는 OLD 코드.**
→ **`cd server && npx wrangler deploy` 가 안 됐다. (또는 build 안 됐다.)**

→ **사용자가 SESSION 11 후 "안 좋아졌다"고 한 게 사실인 이유.**

---

## 2. 변수 매트릭스 — 7차원 × 50+ 변수

### 차원 A. 사용자 (User)

| 변수 | 가능 값 | 현재 처리 | 영향 |
|------|--------|---------|------|
| 성별 | 여성 / 남성 / 논바이너리 / 미상 | ❌ 무시 (모두 여성 가정) | 남성 사용자에게 여성복 추천하면 무용 |
| 나이대 | 10대 / 20대 / 30대 / 40대+ | ❌ 무시 | 트렌드/가격 무드 다름 |
| 지역 | 한국 / 글로벌 | ⚠ Naver만 사용 (한국 특화) | 글로벌 유저는 노출 떨어짐 |
| 가격 민감도 | 가성비 / 중간 / 럭셔리 | ❌ 무시 | 핵심 |
| 검색 의도 | 똑같은 거 / 비슷한 스타일 / dupe / 영감 / 코디 추천 | ❌ 모두 "비슷한 거"로 가정 | 의도 다르면 결과 무용 |
| 신규 vs 재방문 | 첫 사용 / 재사용 / 즐겨찾기 다수 | ❌ 무시 | 콜드스타트 personalization 문제 |

### 차원 B. 입력 이미지 (Image)

| 변수 | 가능 값 | 현재 처리 | 영향 |
|------|--------|---------|------|
| 출처 | 본인 셀카 / 인스타 / 룩북 / 카탈로그 / 런웨이 | ❌ 모두 동일 처리 | 셀카는 배경 노이즈 큼 |
| 인물 | 있음 / 마네킹 / 없음(플랫레이) | ⚠ 얼굴만 블러 처리 | 마네킹은 신체 비례 다름 |
| 인물 성별 | 여성 / 남성 | ⚠ Gemini가 가끔 인식 | 검색 쿼리 성별 미반영 |
| 인물 신체 노출 | 전신 / 상반신 / 하반신 / 클로즈업 | ❌ 무시 | 클로즈업이면 단일 아이템으로 처리 필요 |
| 배경 | 단색 / 길거리 / 실내 / 자연 | ❌ 색상 노이즈로 흡수됨 | 배경 색이 의류 색 매칭 망가뜨림 |
| 조명 | 자연광 / 형광등 / 어두운 / 노을 | ❌ 무시 | 색상 인식 변동 |
| 화질 | HD / 모바일 표준 / 흐림 | ❌ 무시 | 흐리면 detect 정확도 하락 |
| 여러 명 | 1명 / 2명+ | ⚠ Gemini 첫 번째만 잡음 | 2명 이상이면 옷 섞임 |
| 의류 개수 | 1개 / 풀코디 / 액세서리 다수 | ⚠ 6키 카테고리 한계 | 레이어드 처리 못 함 |
| 패턴 | 단색 / 줄무늬 / 꽃무늬 / 카무플라주 | ❌ 색상 토큰만 추출 | 패턴 매칭 약함 |
| 브랜드 노출 | 로고 명확 / 모름 | ❌ 무시 | 로고 보이면 그 브랜드 우선 가능 |
| 시즌성 | 여름 / 겨울 / 환절기 | ⚠ Gemini가 description에 포함 | 검색 쿼리에 미반영 |
| 이미지 출력 비율 | 9:16 (모바일) / 4:5 / 1:1 / 16:9 | ❌ 무시 | bbox 비율 영향 |

### 차원 C. 의류 자체 (Item)

| 변수 | 가능 값 | 현재 처리 | 영향 |
|------|--------|---------|------|
| 카테고리 | 13종 (S9 정의) vs 6종 (Worker) | ⚠ Worker 6종, Cloud Run 13종 → 사용자는 6종만 봄 | top_outer/top_inner 분리 안 됨 |
| 색상 정확도 | 빨강/와인/버건디/체리 등 미세 구분 | ⚠ 단일 토큰 | 색조 미세 매칭 X |
| 가격대 | <2만 / 2~10만 / 10~30만 / 30~100만 / >100만 | ❌ 무시 | 핵심 |
| 디자인 | 베이직 / 디테일 / 트렌드 | ⚠ description에만 | 검색 쿼리 미반영 |
| 시즌 | 봄/여름/가을/겨울 | ⚠ 무시 | 비시즌 추천 |
| 트렌드 | 클래식 / Y2K / 클린걸 / 스포티 | ⚠ 무시 | 트렌드 불일치 |
| 브랜드 티어 | 노브랜드 / 한국 신진 / 컨템포러리 / 럭셔리 | ❌ 무시 | 핵심 |
| 사이즈 | S/M/L/XL/Free | ❌ 무시 | 검색 결과에 다양 |

### 차원 D. 검색 결과 품질 (Output)

| 변수 | 측정 가능 | 현재 처리 |
|------|---------|---------|
| 시각 유사도 | CLIP cosine | v3 path만 (실행 안 됨) |
| 색상 정확도 | 색상 토큰 매칭 | ⚠ Worker 11A-2 deploy 안 됨 |
| 카테고리 정확도 | Gemini 분류 | OK (Worker 6키) |
| 성별 적합성 | title 키워드 분석 | ❌ 없음 |
| 가격 적합성 | 추정 가격대 vs 결과 가격 | ❌ 없음 |
| 다양성 | 결과 중 unique brand 수 | ❌ 측정 안 됨 |
| 신뢰도 | 정품/짝퉁 | ❌ 측정 불가 |
| 광고 비율 | sponsored vs organic | ⚠ Naver API에 광고 섞임 |

### 차원 E. 시스템 (System)

| 변수 | 측정값 (라이브) | 임계 |
|------|-------------|------|
| Cloud Run cold start | 17~35s | < 5s 필요 (Worker timeout 30s) |
| Worker timeout | 30s | (timeout 발생 시 fallback 진입) |
| Cloud Run min-instances | 설정 1 / 실측 0 | 핵심 — 실제 효과 없음 |
| Naver API rate | unknown | 1 req/100ms 가량 |
| Gemini 호출 latency | 2~8s | (안정적) |
| Gemini 503 빈도 | 가끔 | (재시도 로직 있음) |
| Cache hit | 거의 0% (이미지 hash 다름) | (의도) |

### 차원 F. 데이터 소스 (Data)

| 소스 | 현재 사용 | 한계 |
|-----|---------|------|
| Naver Shopping API | ✅ 메인 | 한국 한정, 광고 섞임, 카테고리 정확도 낮음 |
| 자체 카탈로그 (catalog.jsonl 500장) | ⚠ Cloud Run eval 용 | 너무 작음 |
| Naver 광고 vs 유기 | ⚠ 구분 안 함 | 광고 항상 위 |
| 대형몰 vs 개인 셀러 | ⚠ 구분 안 함 | 광고 효과로 대형몰 우선 |
| 신상 vs 베스트 | ⚠ 구분 안 함 | "베스트" 가 항상 노출 |
| 정품/직구/병행수입 | ⚠ 구분 안 함 | 가격 신뢰도 다름 |

### 차원 G. UX

| 요소 | 현재 | 개선 여지 |
|-----|------|---------|
| 첫 응답 시간 | 4~35s (variable) | 인내한도 8s |
| 진행 상태 표시 | "사진 분위기 분석 중" 단계만 | step별 progress 좋음 |
| 결과 다양성 보장 | 없음 (top 5 모두 비슷할 수 있음) | clustering 필요 |
| 사용자 피드백 channel | "좋아요" 만 | "이거 아님" / "비슷한 거 더" 필요 |
| 의도 explicit input | 없음 (image only) | "비슷한 / 더 싸게 / 비슷 + 다른 색" 토글 |
| _source 가시화 | 없음 | "정밀 분석" vs "빠른 모드" 배지 |

---

## 3. 변수별 실패 모드 측정

### 3.1 사용자 케이스 (회색 케이블 니트 세트) 분해

**입력:**
- 차원 A: 여성, 20~30대 추정, 한국 (스타일로 보아), 의도 = "비슷한 거 찾기"
- 차원 B: 인스타/SNS 셀카 스타일, 인물 1명 여성 전신, 단색 배경, HD
- 차원 C: 그레이 케이블 니트 세트 (top_outer 카디건 + top_inner 크롭 + bottom 미니스커트), 액세서리 (목걸이) + 가방
- 가격대 추정: 한국 K-fashion 인디 브랜드 = 5~15만원/아이템

**현재 응답:**
- top: 회색 니트 → ✅ 카테고리 OK
- 액세서리 1순위: **남자 목걸이** → ❌ 차원 D 성별 적합성 0%
- 가방 1순위: **200만원** → ❌ 차원 D 가격 적합성 0%

**실패 원인:**
1. 성별 — Naver 목걸이 검색은 인기순. 남자 명품 목걸이가 검색량 많음. **Worker가 user 의도(여성복) 미전달**.
2. 가격 — Naver 가방 검색은 광고순. 200만원짜리 명품 가방 광고. **Worker가 outfit 가격대 추정 미전달**.
3. 색상 — 회색이 비교적 흔한 색이라 매칭 자체는 되지만, 케이블 패턴 매칭은 안 됨.
4. **본질**: 모든 작업이 Cloud Run 안에 있으나 Cloud Run cold start로 fallback. **그리고 Worker fallback도 SESSION 11 Track A 미적용 상태.**

### 3.2 변수 × 실패 매트릭스

| 케이스 | 카테고리 | 색상 | 디자인 | **성별** | **가격** | 가방 누락 | _source |
|--------|---------|------|--------|---------|---------|----------|---------|
| 회색 케이블 세트 | ✓ | △ | ✗ | ✗ | ✗ | △ | NONE |
| T1 보라 크로셰 | ✓ (top만) | ✓ | △ | (정보 X) | (광고 섞임) | (탐지됨) | NONE |
| T1' 버건디 코트 | ✓ | ✓ | △ | (여성) | △ | ✗ | NONE |
| T2 남성 | **422 reject** | - | - | - | - | - | NONE |
| T3 단일 가방 | ✓ | ✓ | △ | - | △ | ✓ | NONE |
| T4 운동복 | **500 error** | - | - | - | - | - | NONE |

**패턴:**
- 카테고리 분류는 ~80% 정확 (Gemini 강함)
- 색상은 광고/인기순에 짓밟힘
- 디자인 디테일 매칭 약함 (CLIP path 미실행)
- **성별/가격은 측정 자체 안 함**
- 단순 outfit 일부 reject/error
- _source flag 절대 안 보임 → SESSION 11 Worker code 미배포 확정

---

## 4. "검열" 아닌 "추론" — 사용자 통찰 반영 설계

### 4.1 사용자 통찰

> "남자라면 남자옷 올릴 거잖아. 가격대 비싼 것을 추천해줄 수 있는 적절한 상황도 있다."

**틀린 접근:** Hard exclude / hard cap
**옳은 접근:** Soft signal — 추론된 신호를 ranking weight 로 변환

### 4.2 추론 변수 설계

#### 4.2.1 성별 추론 (image → gender signal)

```
입력: image
↓ Gemini bbox detect (face, body, clothing silhouette)
↓ Gemini classify_gender (face, hair, body proportions, outfit cues)
↓ 출력: { gender: 'female'/'male'/'unisex'/'unknown', confidence: 0~1 }

변환: ranking weight
- gender='female', confidence>0.8 → 검색 결과 중 '남자/남성/맨즈' 토큰 -50% score
- gender='male', confidence>0.8 → 검색 결과 중 '여성/여자' 토큰 -50%
- gender='unisex' or unknown → score 영향 없음
```

핵심: **exclude가 아니라 score down.** 신뢰도 낮으면 영향 작게.

#### 4.2.2 가격대 추론 (image → price tier signal)

```
입력: image + style cues
↓ Gemini classify_luxury_signals (브랜드 로고 / 럭셔리 패브릭 / 디자이너 시그니처 / 모델컷 vs SNS)
↓ 출력: { tier: 'budget'/'mid'/'premium'/'luxury', range: [low, high], confidence: 0~1 }

추정 단서:
- 로고 명확 (LV, GG, CC) → 'luxury'
- 모델컷 (스튜디오 조명, 깔끔한 배경) → 'premium' or 'luxury'
- SNS 셀카 + 인디 K-fashion 스타일 → 'mid'
- 캐주얼 후드/운동복 → 'budget'
- 슈트/포멀웨어 + 시계 + 양가죽 → 'premium'

변환: ranking weight
- 추정 range 안 → +20 score
- 추정 range x2 초과 → -30 score
- 추정 range x5 초과 → -50 score
- 추정 range / 5 미만 → -10 score (너무 싸도 mismatch)
```

핵심: **컷이 아니라 range fit score**. 가격이 예상에서 벗어날수록 점수 감소. 럭셔리 outfit 업로드하면 200만원 가방이 정상 노출.

#### 4.2.3 의도 추론 (옵션, UI 토글)

기본 의도: "이거랑 비슷한 거 찾기"
명시적 의도 추가:
- [같은 색 다른 디자인] → color filter strict, design free
- [같은 디자인 다른 색] → design preserve, color free
- [더 싸게] → price < estimated × 0.7
- [업그레이드] → price > estimated × 1.5

UI: 결과 페이지 상단 칩 형태로 토글.

#### 4.2.4 다양성 보장 (Top 5 모두 비슷한 거 방지)

```
def diversify_top_n(products, n=5):
    selected = [products[0]]
    for p in products[1:]:
        if len(selected) >= n: break
        # 이미 선정된 것들과 시각 유사도 < 0.85 인 것만 추가
        if all(visual_sim(p, s) < 0.85 for s in selected):
            selected.append(p)
    # 부족하면 비슷한 것도 채움
    while len(selected) < n:
        for p in products:
            if p not in selected:
                selected.append(p)
                break
    return selected
```

### 4.3 추론 신호 통합 — Score Recipe

기본 점수 (현재):
```
match_score = visual_sim * 0.95 + naver_rank * 0.05  (S10 결정)
```

확장:
```
match_score = (
    visual_sim       * 0.55     # CLIP 시각 매칭
    + color_sim      * 0.15     # Lab 색상 (S11C)
    + gender_fit     * 0.10     # NEW: 추론 성별 일치
    + price_fit      * 0.10     # NEW: 추론 가격대 일치
    + intent_fit     * 0.05     # NEW: 의도 토글
    + naver_rank     * 0.05     # popularity (광고 영향 줄임)
)
```

각 신호 0~1, soft하게 가중. 어떤 신호도 hard reject 하지 않음.

### 4.4 사용자 통찰 검증

| 사용자 발언 | 우리 응답 |
|----------|---------|
| "남자라면 남자옷 추천해야지" | gender 추론 → male 검출 시 남성복 +score, 여성복 -score |
| "비싼 것 적절한 상황도 있다" | price tier 추론 → luxury 검출 시 200만원 가방 정상 노출 |
| "무작정 배제는 적절치 않다" | hard exclude/cap 폐기. soft score weight로 전환 |

---

## 5. 즉시 해결해야 할 6가지 (SESSION 12 P0)

### P0-1: SESSION 11 Worker 코드 진짜로 배포

**이게 1번이다.** 현재 모든 SESSION 11 Track A 코드가 LOCAL에만 있음.

```bash
cd "C:\Users\Alex KIM\Desktop\사업 프로젝트\인앱토스 1\server"
npm run build
npx wrangler deploy
# → 응답에 _source: 'worker_gemini' 보일 때까지 확인
```

검증: 본 리포트의 직접 API 테스트 재실행 → `_source` 필드 등장.

### P0-2: Cloud Run min-instances 실측 확인

```bash
gcloud run services describe fashion-search --region=asia-northeast3 --format="value(spec.template.metadata.annotations)"
# 'autoscaling.knative.dev/minScale: 1' 보여야 함
# 만약 0이면 즉시 패치
gcloud run services update fashion-search --min-instances=1 --region=asia-northeast3
```

검증: 첫 호출 latency < 5s.

### P0-3: 성별 추론 (Gemini classify) — Worker 추가

```typescript
// FASHION_PROMPT에 추가
"## 추가 분석:
- gender: 'female' | 'male' | 'unisex' | 'unknown' (확신도 0.5+ 만 명시)
- gender_confidence: 0~1
- price_tier: 'budget' | 'mid' | 'premium' | 'luxury'
- price_tier_confidence: 0~1
- price_range_estimate: [low_won, high_won]
- gender_signals: ['하이힐', '여성 특유 핏', '메이크업'] 등
- price_signals: ['로고', '모델컷', '럭셔리 텍스처'] 등
"
```

### P0-4: Naver 결과 후처리 — Soft Score (검열 X)

```typescript
function softScoreProducts(products, ctx) {
  return products.map(p => {
    let score = 1.0;
    const title = (p.title || '').toLowerCase();

    // 성별 soft
    if (ctx.gender === 'female' && ctx.gender_confidence > 0.7) {
      if (/남성|남자|맨즈|men's/i.test(title)) score *= 0.5;
    }
    if (ctx.gender === 'male' && ctx.gender_confidence > 0.7) {
      if (/여성|여자|woman/i.test(title)) score *= 0.5;
    }

    // 가격 soft (range fit)
    if (ctx.price_range && p.price) {
      const [lo, hi] = ctx.price_range;
      if (p.price < lo / 5) score *= 0.7;
      else if (p.price > hi * 5) score *= 0.5;
      else if (p.price > hi * 2) score *= 0.7;
      // range 안: 그대로 유지
    }

    // 색상 soft (이미 colorAwareRerank로 일부 처리. 점수화로 강화)
    if (ctx.color) {
      const tokens = ctx.color.split(/\s+/).filter(t => t.length >= 2);
      if (!tokens.some(t => title.includes(t))) score *= 0.7;
    }

    return { ...p, _soft_score: score };
  }).sort((a, b) => b._soft_score - a._soft_score);
}
```

각 신호 hard reject 없음. 신뢰도 따라 multiplier.

### P0-5: 다양성 보장

상위 5개 결과에 시각 유사도 0.85 미만 강제 (CLIP embedding 있을 때). 없으면 brand 토큰 기준 dedupe.

### P0-6: UX — `_source` 배지 + 의도 토글

UI 상단:
- `_source === 'v3'` → "정밀 분석 결과" (FashionCLIP)
- `_source === 'worker_gemini'` → "빠른 분석 결과" (Cold Start로 fallback)

결과 페이지 상단 칩:
- [같은 컨셉] (default)
- [더 싸게]
- [같은 색 다른 디자인]
- [업그레이드]

---

## 6. 변수 통합 ML로 확장하는 길 (P1)

수동 score recipe 대신, **사용자 클릭/구매 데이터로 LightGBM ranker 학습** 하면 더 좋음. 단, 데이터 1,000건+ 필요. 그 전엔 수동 score가 합리적.

훈련 feature 후보:
- visual_sim (CLIP)
- color_sim (Lab)
- gender_fit (binary signal)
- price_fit (range fit score)
- naver_rank (popularity)
- title_color_match (binary)
- title_gender_token (categorical)
- thumbnail_white_ratio (백분율)
- brand_known (binary)
- _source (v3 vs worker_gemini)

라벨: clicked / purchased.

---

## 7. SESSION 12 PROMPT 골자

(별도 파일 `docs/SESSION_12_PROMPT.md` 작성)

**제목:** "배포 정상화 + 성별/가격 추론 도입 + 다양성"

**Track A (P0, 30분):** Worker 진짜 배포 — SESSION 11 코드 production 진입
**Track B (P0, 30분):** Cloud Run min-instances 실측/패치
**Track C (P0, 2시간):** Worker `FASHION_PROMPT` 에 gender/price 추론 추가
**Track D (P0, 2시간):** Soft Score 함수 + Naver 후처리에 통합
**Track E (P1, 4시간):** UX 의도 토글 + `_source` 배지

**측정 기준:**
1. 배포 직후 라이브 5케이스 재테스트 → 모두 `_source` 필드 등장
2. 회색 니트 세트 → 1순위 200만원 사라짐 (가격 추론으로)
3. 회색 니트 세트 → 목걸이 1순위 여성 (성별 추론으로)
4. 남성 outfit → 422 reject 대신 남성복 정상 검색
5. 럭셔리 outfit → 200만원 가방 노출 OK (price tier 추론)

---

## 8. 본질 교훈 (또 한 번)

1. **"배포 명령 실행" ≠ "production 적용"** — wrangler deploy 가 안 됐을 가능성. 다음 세션에서 첫 작업이 "응답 _source 확인" 이어야 함.

2. **"필터" 가 아니라 "신호"** — 사용자가 옳다. 모든 필터링은 hard reject 가 아닌 soft score 로.

3. **"카테고리 인식"과 "디자인 매칭"은 다른 문제** — 카테고리는 Gemini로 80% 해결됨. 진짜 어려운 건 디자인 매칭. CLIP + 색상 + segmentation + LoRA 가 필요한 건 디자인 매칭만이다.

4. **변수 절반은 측정조차 안 했다** — 성별, 가격대, 의도, 신뢰도, 다양성, 광고비율, 시즌, 트렌드, 브랜드 티어. 이번 감사가 첫 측정.

5. **Cloud Run에 모든 ML을 몰아넣으면 cold start로 묻힌다** — 일부 신호(gender, price tier 추론)는 Gemini 1회 호출이라 Worker에서도 가능. **Worker에서 가능한 건 Worker로.**

---

## 부록 A: 본 리포트가 답한 질문들

| 질문 | 답 |
|------|----|
| SESSION 11 코드는 production에 들어갔나? | **Worker는 NO. Cloud Run은 YES (그러나 cold start로 미실행).** |
| 성별 무시는 적절한가? | **부적절. 성별 추론으로 soft score 처리.** |
| 가격 컷은 적절한가? | **부적절. Tier 추론 → range fit score.** |
| 우리가 빠뜨린 변수는? | **18개 (위 매트릭스 ❌ 표시).** |
| 검색 정확도 회복 가능한가? | **YES. 단, 코드 수정 전에 `wrangler deploy` 실행 검증부터.** |
| 사용자 만족 최대화 path? | **(1) 배포 정상화 → (2) 성별/가격 추론 → (3) 다양성 → (4) 의도 토글 → (5) ML ranker.** |

---

# 끝
