# SESSION 12: 배포 정상화 + 성별/가격 추론 도입 + Soft Score + 다양성

> **선행 필독:** `docs/VARIABLE_AUDIT_S11.md` (변수 매트릭스 + 직접 측정 + 실패 모드)
> `docs/SESSION_11_PROMPT.md` (이전 작업 — 배포 안 된 부분 식별 필요)
> **갱신된 CLAUDE.md** "🚀 배포 검증 규칙" 섹션 — 반드시 먼저 읽을 것
>
> **사용자 핵심 통찰 (2026-05-01):**
> "남자라면 남자옷을 올릴 거잖아? 그러면 남자옷이 서칭되어야지.
> 비싼 것을 추천해줄 적절한 상황도 분명히 있는데 무작정 배제는 적절치 않다."
>
> **본질 원칙:**
> **"검열(hard exclude/cap)이 아니라 추론(soft signal weight)으로."**
>
> **충격적 발견 (Track A 시작 전 반드시 검증):**
> SESSION 11에서 작성한 Worker 코드(`server/src/worker.ts`)가 LOCAL에만 있고 production에 deploy 안 됐다.
> 라이브 응답에 `_source` 필드, 8키 schema, `color`/`subtype` 필드 모두 부재.
>
> **SESSION 11 미배포 root cause (확정):**
> - `git log --oneline -- server/`: bab17eb (FASHION_PROMPT 변경) + a22e882 (timeout 변경) 두 commit 모두 존재
> - `server/.wrangler/tmp` 마지막 활동: 2026-05-01 14:06 UTC (a22e882 commit 직전)
> - 그러나 라이브 worker는 OLD 코드 → wrangler deploy가 silent fail (인증 또는 명령 에러)
> - SESSION_STATUS.md엔 "Track A+B Worker 배포 완료" 자기 보고 → 사용자가 며칠간 옛 코드 응답 봄
>
> **재발 방지 도구 (이번 세션부터 의무):**
> - `scripts/verify_deploy.sh` — Worker + Cloud Run 응답 자동 검증
> - `CLAUDE.md` "🚀 배포 검증 규칙" 섹션 — verify 실패 시 SESSION_STATUS.md 완료 표기 금지
>
> **STEP 0 의무:** 어떤 다른 작업보다 먼저 "현재 deploy 상태 진단" 부터 시작.

---

## 0. 절대 원칙

1. **wrangler deploy 가 진짜 됐는지 응답으로 검증한다.** `_source` 필드가 보이지 않으면 어떤 다른 작업도 의미 없다.
2. **Cloud Run min-instances=1 도 응답 latency로 검증한다.** 첫 호출 5s 미만이어야 함.
3. **모든 필터는 soft score multiplier 로.** hard reject 또는 hard cap 절대 금지.
4. **각 신호는 confidence를 동반한다.** 신뢰도 낮으면 영향도 작게.
5. **배포 후 라이브 5케이스 재테스트 의무.** 회복 정량 확인.
6. **모든 deploy 명령 후 `bash scripts/verify_deploy.sh` 즉시 실행.** Exit 0 안 나오면 다른 작업 정지.
7. **`verify_deploy.sh` 실패 시 SESSION_STATUS.md "완료" 표기 절대 금지.** "시도 후 검증 실패 (사유: X)"로 정직하게 기록.

---

## STEP 0 — Deploy 상태 진단 (어떤 다른 작업보다 먼저!)

> **시간 약속: 5분.** 이 단계 통과 못 하면 SESSION 12 전체 무의미.

### 0-1. Wrangler 인증 확인 (실패 시 즉시 중단)

```bash
cd "C:\Users\Alex KIM\Desktop\사업 프로젝트\인앱토스 1\server"
npx wrangler whoami
# 기대: "kyoung361207@gmail.com" 또는 유사 이메일 출력
# 실패 시: "You are not authenticated" → 사용자에게 알림
#   → 사용자가 직접 'npx wrangler login' 실행 필요
#   → STEP 0 통과 못 함. 다른 작업 정지.
```

### 0-2. 현재 deployed Worker 응답 baseline 측정

```bash
cd "C:\Users\Alex KIM\Desktop\사업 프로젝트\인앱토스 1"
bash scripts/verify_deploy.sh fashion-search/eval/queries/q001.jpg

# 기대 출력:
# - exit 0
# - _source = 'v3' 또는 'worker_gemini' (NULL 아님)
# - schema 8키 적용 (top_outer/top_inner 보임)
#
# 실패 패턴:
# - "_source 필드 부재" → SESSION 11 Worker 코드 미배포 확정. 0-3 진행.
# - "Cloud Run /health 503" → min-instances=1 미적용 또는 인스턴스 죽음.
# - "Wrangler 미인증" → 0-1으로 돌아가 인증부터.
```

### 0-3. SESSION 11 patch 재배포 (verify 실패 시)

```bash
cd "C:\Users\Alex KIM\Desktop\사업 프로젝트\인앱토스 1\server"
npm run build 2>&1 | tee build_log.txt
# build 실패 시: build_log.txt 분석 후 사용자에게 보고

npx wrangler deploy 2>&1 | tee deploy_log.txt
# deploy 실패 시 키워드 확인:
#   - "Logged out" / "Authentication" → 0-1으로
#   - "wrangler.toml" / "config" → wrangler.toml 검증
#   - "build" / "syntax" → 코드 에러 → 사용자에게 보고
# 성공 패턴:
#   "✨ Success! Deployed cloi-api ..."
#   "https://cloi-api.kyoung361207.workers.dev"

# 즉시 재검증
cd ..
bash scripts/verify_deploy.sh fashion-search/eval/queries/q001.jpg
# Exit 0 통과해야 함. 안 통과면 deploy_log.txt 보고 진단 반복.
```

### 0-4. Cloud Run min-instances 실측 확인

```bash
gcloud run services describe fashion-search \
    --region=asia-northeast3 \
    --format='value(spec.template.metadata.annotations)' \
    | grep -i minScale
# 기대: 'autoscaling.knative.dev/minScale: 1'
# 없거나 '0'이면:
gcloud run services update fashion-search \
    --region=asia-northeast3 \
    --min-instances=1
# warm 호출로 검증
time curl -s -o /dev/null -w "%{http_code} %{time_total}s\n" \
    https://fashion-search-dibvogjuma-du.a.run.app/health
# 기대: "200 0.5s" 정도
# "200 30s+" 면 cold start 발생 — min-instances 적용 안 됨
```

### 0-5. STEP 0 통과 조건

다음 모두 만족해야 STEP 1 진행:
- [ ] `npx wrangler whoami` 인증 OK
- [ ] `verify_deploy.sh` exit 0
- [ ] Cloud Run /health warm latency < 1s
- [ ] 응답에 `_source` 필드 존재
- [ ] 응답에 8키 schema 적용 (top_outer/top_inner 등)

**하나라도 실패 시: 사용자에게 즉시 보고 + 원인 + 다음 행동. SESSION 12 작업 정지.**

---

---

## 1. Track A — 배포 정상화 (P0, 30분)

### Fix 12A-1: Worker 진짜로 deploy

**현재 상태:** `server/src/worker.ts` 에 SESSION 11 코드 다 있으나 production 미배포.

**검증 명령:**
```bash
cd "C:\Users\Alex KIM\Desktop\사업 프로젝트\인앱토스 1\server"

# 1. build
npm run build

# 2. wrangler 인증 확인
npx wrangler whoami

# 3. 배포
npx wrangler deploy

# 4. 즉시 응답 검증
curl -X POST https://cloi-api.kyoung361207.workers.dev/api/analyze \
  -H "Content-Type: application/json" \
  -d "{\"imageBase64\":\"$(base64 -w 0 < tests/fixtures/lookbook_burgundy.jpg)\",\"mimeType\":\"image/jpeg\"}" | jq '._source'

# 기대: "v3" 또는 "worker_gemini"
# 실제 NULL이면 배포 실패. 다시.
```

### Fix 12A-2: Cloud Run min-instances=1 실측

```bash
# 현재 상태 확인
gcloud run services describe fashion-search \
  --region=asia-northeast3 \
  --format='value(spec.template.metadata.annotations)'

# 'autoscaling.knative.dev/minScale: 1' 확인.
# 만약 0이거나 없으면:
gcloud run services update fashion-search \
  --region=asia-northeast3 \
  --min-instances=1 \
  --max-instances=3

# 검증: warm 상태 첫 호출 latency
time curl -X POST https://fashion-search-dibvogjuma-du.a.run.app/api/search \
  -F "file=@tests/fixtures/lookbook_burgundy.jpg" -o /dev/null

# 기대: < 5s
```

```bash
git commit -m "ops: verify worker + cloud-run deployment (SESSION 11 reality check)"
```

---

## 2. Track B — Worker FASHION_PROMPT 에 추론 신호 추가 (P0, 2시간)

### Fix 12B-1: gender + price_tier 추론 추가

**파일:** `server/src/worker.ts:38~71`

**기존 8키 schema 유지하면서 outfit-level 메타 추가:**

```typescript
const FASHION_PROMPT = `당신은 한국 패션 이커머스 전문 MD입니다. 이미지를 부위별로 점검하고 모든 의류/액세서리/가방을 빠짐없이 추출하세요.

(...기존 1단계, 2단계, 3단계 프롬프트 유지...)

## 4단계: outfit 전체 추론 (NEW — 사용자 의도 매칭용)
다음 메타 정보 함께 출력:
- gender: 'female' | 'male' | 'unisex' | 'unknown' (눈에 띄는 단서로만 판단)
- gender_confidence: 0.0~1.0
- gender_signals: ["하이힐", "메이크업", "여성 특유 핏"] 등 판단 근거 2~5개
- price_tier: 'budget' | 'mid' | 'premium' | 'luxury'
  budget = 5만원 미만 평균 / mid = 5~30만원 / premium = 30~100만원 / luxury = 100만원+
- price_tier_confidence: 0.0~1.0
- price_signals: ["로고 명확", "모델컷", "럭셔리 패브릭"] 등 판단 근거 2~5개
- price_range_estimate: { "min": 30000, "max": 200000 } (1 아이템 평균 추정)
- season: 'spring' | 'summer' | 'fall' | 'winter' | 'all'
- vibe: ["시크", "캐주얼", "페미닌", "스트리트", "오피스", "스포티"] 중 1~3개

(...기존 출력 형식 유지하되, 응답 root 에 위 메타 추가...)

JSON 예시:
{
  "categories": { /* 8키 */ },
  "description": "...",
  "gender": "female",
  "gender_confidence": 0.9,
  "gender_signals": ["여성 핏 크롭탑", "하이힐", "여성형 액세서리"],
  "price_tier": "mid",
  "price_tier_confidence": 0.7,
  "price_signals": ["인디 K-fashion 스타일", "단순 프린트 없음", "신발 캐주얼"],
  "price_range_estimate": { "min": 30000, "max": 200000 },
  "season": "fall",
  "vibe": ["시크", "오피스"]
}`;
```

**TypeScript 타입 동기화:**
```typescript
interface OutfitMeta {
  gender?: 'female' | 'male' | 'unisex' | 'unknown';
  gender_confidence?: number;
  gender_signals?: string[];
  price_tier?: 'budget' | 'mid' | 'premium' | 'luxury';
  price_tier_confidence?: number;
  price_signals?: string[];
  price_range_estimate?: { min: number; max: number };
  season?: string;
  vibe?: string[];
}

interface AnalysisResult {
  categories: Partial<Record<FashionCategoryKey, CategoryInfo | null>>;
  description: string;
}
type FullAnalysisResult = AnalysisResult & OutfitMeta;
```

```bash
git commit -m "feat(worker): add outfit-level inference (gender + price_tier + season + vibe)"
```

---

## 3. Track C — Soft Score 미들웨어 (P0, 2시간)

### Fix 12C-1: `softScoreProducts` 함수 + 적용

**파일:** `server/src/worker.ts` (`/api/search/categories` 핸들러 안)

```typescript
interface SoftScoreContext {
  color?: string;
  gender?: string;
  gender_confidence?: number;
  price_range?: { min: number; max: number };
  price_tier?: string;
  category: string;  // top_outer, bottom, bag, accessory 등
}

function softScoreProducts(
  products: NaverProduct[],
  ctx: SoftScoreContext,
): NaverProduct[] {
  return products
    .map((p) => {
      let score = 1.0;
      const title = (p.title || '').replace(/<[^>]+>/g, '').toLowerCase();

      // ─── 1. 성별 신호 (soft) ───
      if (ctx.gender && (ctx.gender_confidence ?? 0) > 0.6) {
        const oppositeTokens =
          ctx.gender === 'female' ? /남성|남자|맨즈|men's|man's|신랑|아빠/i :
          ctx.gender === 'male'   ? /여성|여자|woman|girl|wife|와이프/i :
          null;
        if (oppositeTokens && oppositeTokens.test(title)) {
          // 신뢰도 비례 페널티 (0.6 → 0.3 multiplier, 1.0 → 0.4)
          const multiplier = 0.3 + 0.1 * Math.min(1, ctx.gender_confidence!);
          score *= multiplier;
        }
        // 같은 성별 명시 토큰 있으면 작은 보너스
        const sameTokens =
          ctx.gender === 'female' ? /여성|여자|woman/i :
          ctx.gender === 'male'   ? /남성|남자|men's/i : null;
        if (sameTokens && sameTokens.test(title)) score *= 1.1;
      }

      // ─── 2. 가격 신호 (soft, range fit) ───
      if (ctx.price_range && p.price && p.price > 0) {
        const { min: lo, max: hi } = ctx.price_range;
        if (p.price < lo / 5) score *= 0.7;
        else if (p.price < lo / 2) score *= 0.85;
        else if (p.price > hi * 5) score *= 0.5;
        else if (p.price > hi * 2) score *= 0.7;
        else if (p.price > hi) score *= 0.9;
        // range 안: 그대로
      }

      // ─── 3. 색상 신호 (soft) ───
      if (ctx.color) {
        const tokens = ctx.color.split(/\s+/).filter((t) => t.length >= 2);
        const matched = tokens.some((t) => title.includes(t.toLowerCase()));
        if (!matched) score *= 0.75;
      }

      // ─── 4. 광고/스팸 신호 (soft, heuristic) ───
      // "100% 정품", "최저가", "당일출고" 같은 광고 키워드 - 약하게 페널티
      if (/100%\s*정품|최저가|역대급|행사가|당일출고/i.test(title)) {
        score *= 0.92;
      }

      // ─── 5. 기본 score 0.05 + soft × 0.95 (안전 장치) ───
      // soft 0이어도 완전히 사라지지 않게 (사용자가 어디 매칭됐는지 보여줄 가치)
      const final = 0.05 + score * 0.95;

      return { ...p, _soft_score: final };
    })
    .sort((a, b) => (b._soft_score ?? 0) - (a._soft_score ?? 0));
}
```

### Fix 12C-2: `/api/search/categories` 적용

```typescript
// 분석 결과에서 메타 받기 (UI가 보내거나 Worker가 분석 시 함께 저장)
// 옵션 1: UI가 categories와 함께 outfit_meta 도 보냄
// 옵션 2: Worker가 분석 결과 cache (30s TTL)에 저장 후 재사용

// 일단 옵션 1 (UI 변경) — 더 명시적
app.post('/api/search/categories', async (c) => {
  const { categories, outfit_meta } = await c.req.json();

  // ... 기존 로직 ...

  for each category:
    const ctx: SoftScoreContext = {
      color: info.color,
      gender: outfit_meta?.gender,
      gender_confidence: outfit_meta?.gender_confidence,
      price_range: outfit_meta?.price_range_estimate,
      price_tier: outfit_meta?.price_tier,
      category,
    };

    const softScored = softScoreProducts(merged, ctx);
    const deduped = dedupeBySku(softScored);
    // colorAwareRerank 는 이제 softScored 와 중복 → 폐지하거나 약하게
    return { ..., products: deduped };
});
```

### Fix 12C-3: UI api.ts 동기화

**파일:** `src/services/api.ts`

```typescript
// analyzeImage 응답에 outfit_meta 가 포함됨
export interface CategoryAnalysisResult {
  categories: Record<string, CategoryInfo | null>;
  description: string;
  outfit_meta?: {
    gender?: string;
    gender_confidence?: number;
    price_range_estimate?: { min: number; max: number };
    price_tier?: string;
    season?: string;
    vibe?: string[];
  };
}

// searchByCategories 호출 시 outfit_meta 함께 전송
export async function searchByCategories(
  categories: CategoryAnalysisResult['categories'],
  outfitMeta?: CategoryAnalysisResult['outfit_meta'],
) {
  const res = await fetch(`${API_BASE}/api/search/categories`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ categories, outfit_meta: outfitMeta }),
  });
  // ...
}
```

```bash
git commit -m "feat(worker): softScoreProducts — gender/price/color signals (no hard filter)"
```

---

## 4. Track D — 다양성 보장 (P1, 1시간)

### Fix 12D-1: 결과 5개 시각/브랜드 다양성

**파일:** `server/src/worker.ts` (`/api/search/categories`)

```typescript
function diversifyTopN(products: NaverProduct[], n: number = 5): NaverProduct[] {
  if (products.length <= n) return products;

  const selected: NaverProduct[] = [products[0]];
  const seenBrands = new Set<string>();
  const firstBrand = extractBrandToken(products[0]);
  if (firstBrand) seenBrands.add(firstBrand);

  for (const p of products.slice(1)) {
    if (selected.length >= n) break;
    const brand = extractBrandToken(p);
    // 같은 브랜드 2개 이상 X
    if (brand && seenBrands.has(brand)) continue;
    selected.push(p);
    if (brand) seenBrands.add(brand);
  }

  // 부족하면 채우기
  for (const p of products) {
    if (selected.length >= n) break;
    if (!selected.includes(p)) selected.push(p);
  }
  return selected;
}

function extractBrandToken(p: NaverProduct): string | null {
  // mall_name 또는 title 첫 단어
  if (p.mallName) return p.mallName.toLowerCase();
  const firstWord = (p.title || '').split(/\s+/)[0];
  return firstWord ? firstWord.toLowerCase() : null;
}
```

### Fix 12D-2: 적용 위치

```typescript
const softScored = softScoreProducts(merged, ctx);
const deduped = dedupeBySku(softScored);
const diversified = diversifyTopN(deduped, 8);  // top 8 다양성 보장
return { ..., products: diversified };
```

```bash
git commit -m "feat(worker): brand diversification in top results"
```

---

## 5. Track E — UX (P1, 2시간)

### Fix 12E-1: `_source` 배지

**파일:** UI 결과 페이지 컴포넌트 (`src/pages/...` 적절한 곳)

```tsx
{response._source === 'v3' ? (
  <Badge variant="success">정밀 분석 (FashionCLIP)</Badge>
) : response._source === 'worker_gemini' ? (
  <Badge variant="warning">빠른 분석 (Cold Start로 fallback)</Badge>
) : null}
```

### Fix 12E-2: 의도 토글

상단 칩 4개:
```tsx
<ChipGroup>
  <Chip selected={intent === 'similar'} onClick={() => setIntent('similar')}>같은 컨셉</Chip>
  <Chip selected={intent === 'cheaper'} onClick={() => setIntent('cheaper')}>더 싸게</Chip>
  <Chip selected={intent === 'sameColor'} onClick={() => setIntent('sameColor')}>같은 색 다른 디자인</Chip>
  <Chip selected={intent === 'upgrade'} onClick={() => setIntent('upgrade')}>업그레이드</Chip>
</ChipGroup>
```

intent 별 score 보정:
- `cheaper`: price multiplier 강화 (price < estimated × 0.7 → +score)
- `sameColor`: color match 미스 → 강한 페널티
- `upgrade`: price > estimated × 1.5 → +score

### Fix 12E-3: 분석 메타 표시

```tsx
{outfit_meta && (
  <MetaBar>
    <span>👤 {outfit_meta.gender || '미상'} ({Math.round((outfit_meta.gender_confidence || 0) * 100)}%)</span>
    <span>💰 {outfit_meta.price_tier} (~{outfit_meta.price_range_estimate?.max?.toLocaleString()}원)</span>
    <span>🎨 {outfit_meta.vibe?.join(' · ')}</span>
  </MetaBar>
)}
```

```bash
git commit -m "feat(ui): _source badge + intent toggle + outfit_meta display"
```

---

## 6. 측정 — SESSION 12 회복 검증

### 6.1 자동 5케이스 라이브 테스트

`fashion-search/scripts/live_qa_s12.py` (신규):

```python
import requests, base64, json
URL = 'https://cloi-api.kyoung361207.workers.dev/api/analyze'

CASES = [
    ('lookbook_burgundy.jpg', 'female', 'mid'),       # 버건디 코트
    ('lookbook_knit_set.jpg', 'female', 'mid'),       # 회색 케이블 세트 (사용자 케이스)
    ('lookbook_men_casual.jpg', 'male', 'mid'),       # 남성 캐주얼
    ('lookbook_luxury.jpg', 'female', 'luxury'),      # 럭셔리 outfit
    ('lookbook_athletic.jpg', 'female', 'budget'),    # 운동복
]

for img, expected_gender, expected_tier in CASES:
    with open(f'tests/fixtures/{img}', 'rb') as f:
        b64 = base64.b64encode(f.read()).decode()
    r = requests.post(URL, json={'imageBase64': b64, 'mimeType': 'image/jpeg'}, timeout=60)
    j = r.json()
    print(f"\n=== {img} ===")
    print(f"_source: {j.get('_source', 'NONE')}")
    print(f"gender: {j.get('gender')} (conf={j.get('gender_confidence')}) — expected={expected_gender}")
    print(f"price_tier: {j.get('price_tier')} (conf={j.get('price_tier_confidence')}) — expected={expected_tier}")
    print(f"price_range: {j.get('price_range_estimate')}")
    print(f"vibe: {j.get('vibe')}")
    print(f"categories: {[k for k, v in (j.get('categories') or {}).items() if v]}")
```

### 6.2 회복 체크리스트

| # | 항목 | 회복 기준 |
|---|------|---------|
| C1 | `_source` 필드 응답 | 5/5 케이스 모두 (NULL 0건) |
| C2 | `gender` 필드 응답 | 5/5 케이스 모두 |
| C3 | `price_range_estimate` 응답 | 5/5 케이스 모두 |
| C4 | 회색 니트 + 가방 검색 → 200만원 가방 1순위 X | 1순위 가격 < 50만원 |
| C5 | 회색 니트 + 목걸이 검색 → 남자 목걸이 1순위 X | 1순위 title에 '남자/남성' 부재 |
| C6 | 남성 outfit → 422 reject 안 함 | 422 0건, 남성복 검색 결과 노출 |
| C7 | 럭셔리 outfit → 200만원 가방 정상 노출 OK | tier=luxury 시 가격 cap 미적용 확인 |
| C8 | Cloud Run latency < 5s (warm) | min-instances=1 효과 검증 |
| C9 | v3 path 적중률 ≥ 50% | 5번 호출 중 2회+ `_source: v3` |

---

## 7. 작업 순서 (한 번에 보기)

```bash
cd "C:\Users\Alex KIM\Desktop\사업 프로젝트\인앱토스 1"

# === STEP 0: Deploy 진단 (반드시 먼저!) ===
bash scripts/verify_deploy.sh fashion-search/eval/queries/q001.jpg
# Exit 0 안 나오면 STEP 0 진단 따라 해결. 0 나올 때까지 다른 작업 정지.

# === Track A: 배포 정상화 (STEP 0 완료 후) ===
cd server && npm run build && npx wrangler deploy && cd ..
bash scripts/verify_deploy.sh    # 즉시 재검증. 실패 시 다시.
gcloud run services describe fashion-search --region=asia-northeast3 --format='value(spec.template.metadata.annotations)' | grep -i minScale
# minScale=1 미확인 시:
# gcloud run services update fashion-search --region=asia-northeast3 --min-instances=1

# 검증
curl -X POST https://cloi-api.kyoung361207.workers.dev/api/analyze \
  -H "Content-Type: application/json" \
  -d "$(jq -n --arg b64 "$(base64 -w 0 < tests/fixtures/lookbook_burgundy.jpg)" '{imageBase64: $b64, mimeType: "image/jpeg"}')" | jq '._source, ._imageHash'
# → "v3" 또는 "worker_gemini" 보여야 함

# === Track B: FASHION_PROMPT 추론 추가 ===
# server/src/worker.ts:38 의 FASHION_PROMPT 교체
# (...코드 작성 + 테스트...)
cd server && npm run build && npx wrangler deploy && cd ..

# === Track C: Soft Score ===
# server/src/worker.ts 에 softScoreProducts 함수 추가
# /api/search/categories 핸들러 안에 적용
# src/services/api.ts 에 outfit_meta 전송
cd server && npm run build && npx wrangler deploy && cd ..
cd cloi && npm run build && npx wrangler pages deploy dist --project-name=cloi && cd ..

# === Track D: 다양성 ===
# Track C 와 함께 worker.ts 에 추가
# (위와 같이 deploy)

# === Track E: UX ===
# UI 컴포넌트 수정
cd cloi && npm run build && npx wrangler pages deploy dist --project-name=cloi && cd ..

# === 측정 ===
python fashion-search/scripts/live_qa_s12.py > s12_results.txt

# === Push ===
git push origin main

# === SESSION_STATUS.md 업데이트 + 알람 ===
```

---

## 8. 성공 정의

- [ ] **STEP 0: `bash scripts/verify_deploy.sh` exit 0 통과**
- [ ] **STEP 0: Worker `_source` 필드 응답 (SESSION 11 코드 진짜 배포 증명)**
- [ ] Track A: `_source` 필드 5/5 응답
- [ ] Track A: Cloud Run warm latency < 5s
- [ ] Track B: 5/5 응답에 gender, price_tier, price_range_estimate 포함
- [ ] Track C: 회색 니트 케이스 1순위 가격 < 50만원, 1순위 title 남자 토큰 부재
- [ ] Track C: 럭셔리 케이스 200만원 가방 정상 노출 (price tier 추론 작동)
- [ ] Track D: top 5 같은 브랜드 2개 이상 노출 X
- [ ] Track E: `_source` 배지 + 의도 토글 UI 노출
- [ ] **Track F: GitHub Actions deploy + verify 워크플로우 도입 (영구 차단)**
- [ ] **Track F: 매시간 health monitor 워크플로우 가동 (회귀 즉시 감지)**
- [ ] **모든 deploy 후 verify_deploy.sh 통과 — 통과 못 하면 SESSION_STATUS.md 완료 표기 X**
- [ ] git push origin main
- [ ] SESSION_STATUS.md 업데이트 (정직하게 — verify 실패한 부분은 "시도 후 검증 실패"로)
- [ ] **알람 실행**

---

## 9. 위험 요소 + 대응

| 위험 | 대응 |
|------|------|
| Worker FASHION_PROMPT에 메타 추가 → Gemini 응답 파싱 실패 | TypeScript 옵셔널 + 첫 5건 dryrun 후 본격 배포 |
| 새 응답 형식이 UI 파싱 실패 | `outfit_meta` 옵셔널, 없어도 UI 정상 동작 |
| Cloud Run min-instances=1 비용 부담 | (사용자 결정) 약 $20~30/월 |
| Gemini 메타 추론 정확도 낮음 | confidence < 0.5 시 메타 무시 |
| Soft score 너무 약하게 적용 → 변화 못 느낌 | 첫 5케이스 측정 후 multiplier 조정 (0.5 → 0.3 등) |
| Soft score 너무 강하게 → 모두 비슷한 결과 | 다양성(Track D) 함께 적용 |

---

## 10. 본질 원칙 (반복 방지)

1. **"deploy 명령" ≠ "production 적용"** — 응답에 새 필드 없으면 다시.
2. **사용자가 옳다 — hard filter 가 아닌 soft signal로.**
3. **Gemini는 빠르고 정확한 추론 가능 (image → gender/price tier 1회 호출).** Cloud Run의 무거운 ML 안 거쳐도 됨.
4. **모든 신호에 confidence 동반.** 신뢰도 낮으면 영향도 낮게.
5. **다양성은 별도 단계.** soft score 만으로는 비슷한 거 5개 나옴.

---

## 11. 영구 방지책 — CI/CD 자동화 (SESSION 12 마지막 단계)

이번 세션 끝나기 전에 반드시 도입:

### Fix 12F-1: GitHub Actions 자동 deploy + verify

**파일:** `.github/workflows/deploy-worker.yml` (신규)

```yaml
name: Deploy Worker + Verify
on:
  push:
    branches: [main]
    paths:
      - 'server/src/**'
      - 'server/wrangler.toml'
      - 'server/package.json'

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20' }

      - name: Install
        working-directory: server
        run: npm ci

      - name: Deploy Worker
        working-directory: server
        run: npx wrangler deploy
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}

      - name: Verify Deploy
        run: |
          sleep 10  # CDN propagation
          bash scripts/verify_deploy.sh fashion-search/eval/queries/q001.jpg

      - name: Notify on failure
        if: failure()
        run: |
          echo "::error::Deploy or verify FAILED. Manual intervention required."
          exit 1
```

**필요 secrets (GitHub repo settings → Actions → Secrets):**
- `CLOUDFLARE_API_TOKEN` — Workers Edit 권한
- `CLOUDFLARE_ACCOUNT_ID`

**효과:** 사용자 또는 Claude Code가 push 만 하면 자동 deploy + verify. 실패 시 PR/main에서 명확한 알림.

### Fix 12F-2: Cloud Run 도 동일 자동화

**파일:** `.github/workflows/deploy-cloudrun.yml` (신규)

```yaml
name: Deploy Cloud Run + Verify
on:
  push:
    branches: [main]
    paths:
      - 'fashion-search/**'

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: google-github-actions/auth@v2
        with:
          credentials_json: ${{ secrets.GCP_SA_KEY }}
      - uses: google-github-actions/setup-gcloud@v2

      - name: Deploy Cloud Run
        run: bash fashion-search/deploy.sh
        env:
          GCP_PROJECT_ID: cloi-fashion-search
          GOOGLE_API_KEY: ${{ secrets.GOOGLE_API_KEY }}
          ADMIN_TOKEN: ${{ secrets.ADMIN_TOKEN }}
          NAVER_CLIENT_ID: ${{ secrets.NAVER_CLIENT_ID }}
          NAVER_CLIENT_SECRET: ${{ secrets.NAVER_CLIENT_SECRET }}

      - name: Verify
        run: bash scripts/verify_deploy.sh
```

### Fix 12F-3: 매시간 health check (회귀 즉시 감지)

**파일:** `.github/workflows/health-monitor.yml` (신규)

```yaml
name: Hourly Health Monitor
on:
  schedule:
    - cron: '0 * * * *'   # 매시간
  workflow_dispatch:

jobs:
  health:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: bash scripts/verify_deploy.sh
      - name: Notify on regression
        if: failure()
        run: |
          # Slack/Email/Discord webhook 호출
          curl -X POST $SLACK_WEBHOOK_URL -d '{"text":"⚠ Cloi production regression detected"}'
        env:
          SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
```

### Fix 12F-4: 배포 실패 audit log

**파일:** `scripts/log_deploy_attempt.sh` (신규)

```bash
#!/usr/bin/env bash
# 모든 deploy 시도를 logs/deploy_history.jsonl 에 기록
echo "{\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"actor\":\"$1\",\"command\":\"$2\",\"exit_code\":$3,\"verify_passed\":$4}" >> logs/deploy_history.jsonl
```

Claude Code가 deploy 명령 실행 후 무조건 호출:
```bash
npx wrangler deploy; CODE=$?
bash scripts/verify_deploy.sh; VERIFY=$?
bash scripts/log_deploy_attempt.sh "claude_code_session_12" "wrangler deploy" $CODE $VERIFY
```

→ 시간 지난 후 "지난 24시간 deploy 시도 vs 성공률" 추적 가능.

```bash
git commit -m "ops: GitHub Actions auto-deploy + hourly health monitor + audit log"
```

---

## 12. SESSION 13 사전 노트

이번 세션 끝나도 남는 과제:
- ML ranker (LightGBM 학습) — 데이터 1000건+ 필요
- FashionCLIP 한국 도메인 LoRA fine-tune
- 다중 source (Naver + 무신사 + 29CM) 통합
- 광고 vs 유기 결과 정확한 분리
- 짝퉁 detection
- 사용자 personalization (즐겨찾기/구매내역 기반)

---

## 13. Claude Code 실행 명령어 (한 줄 복사)

```bash
cd "C:\Users\Alex KIM\Desktop\사업 프로젝트\인앱토스 1" && claude --dangerously-skip-permissions "docs/SESSION_12_PROMPT.md 정독 + 갱신된 CLAUDE.md '🚀 배포 검증 규칙' 섹션 정독. STEP 0 → Track A → B → C → D → E → F 순서로 정확히 실행. STEP 0은 'bash scripts/verify_deploy.sh' 즉시 실행, exit 0 안 나오면 다른 작업 정지 후 사용자에게 보고. Track A 끝난 후도 verify_deploy.sh 무조건 재실행. Track F는 GitHub Actions 자동 deploy + 매시간 health monitor 워크플로우 도입. SESSION_STATUS.md엔 verify 통과한 것만 '완료'로 적기 — 실패한 부분은 '시도 후 검증 실패 (사유)'로 정직하게 기록. 본질 원칙 두 개: (1) '검열이 아니라 추론. hard exclude/cap 절대 금지. 모든 신호는 soft score multiplier로.' (2) 'deploy 명령 실행 ≠ production 적용. verify_deploy.sh exit 0 만이 진짜 완료.'"
```

---

## END OF SESSION 12 PROMPT
