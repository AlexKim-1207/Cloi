# SESSION 13: Item-Level Detail Signals — Pattern + Length + Ambiguity

> **선행 필독:**
> - `docs/DIAGNOSIS_S12_USER_CASE.md` (체크/쇼츠/이너 모호성 사용자 케이스 분석)
> - `docs/USER_EXPERIENCE_REPORT_V2.md` (SESSION 11+12 적용 후 4.6/5 회복)
> - 갱신된 CLAUDE.md "🚀 배포 검증 규칙"
>
> **사용자 호소 (2026-05-02):**
> "이너는 반팔/민소매 모호인데 민소매로만 검색됨. 아우터 체크인데 무관한 결과. 바지 짧은 쇼츠인데 칠부 결과. 키워드는 잘 들어갔는데 결과가 다르다."
>
> **본질 원칙:**
> **"SESSION 11+12은 outfit-level meta (성별/가격/분위기) 풀었다.
> SESSION 13은 item-level detail (패턴/길이/소매) 푼다."**
>
> **재발 방지 (CLAUDE.md 규칙):**
> - 모든 deploy 후 `bash scripts/verify_deploy.sh` exit 0 통과 의무
> - `wrangler pages deploy dist --project-name=cloi` 가 진짜 production deploy (cloi-api 단독 deploy X)

---

## 0. STEP 0 — Deploy 진단 (어떤 작업보다 먼저!)

```bash
cd "C:\Users\Alex KIM\Desktop\사업 프로젝트\인앱토스 1"

# 0-1. 현재 prod 응답 baseline
bash scripts/verify_deploy.sh fashion-search/eval/queries/q001.jpg
# 기대: exit 0, _source=worker_gemini, has_8key=YES, has_gender=YES, has_price=YES
# 실패 시: STEP 0-2 진행

# 0-2. 만약 SESSION 11/12 코드 production 빠짐 (있을 수 없는 일이지만 sanity check):
cd server && npm run build && cd ..
npx wrangler pages deploy dist --project-name=cloi   # ← Pages 배포 = 진짜 prod
sleep 30
bash scripts/verify_deploy.sh fashion-search/eval/queries/q001.jpg
```

통과해야 STEP 1 진행.

---

## 1. 절대 원칙

1. **Hard reject 금지 — soft signal로만.** 모든 새 신호도 confidence-weighted multiplier (0.3~1.1).
2. **각 fix 후 즉시 재배포 + verify.** SESSION 11에서 배운 교훈.
3. **사용자 케이스 (체크 셔츠 + 쇼츠 + 모호 이너) 가 success 기준.**
4. **Track 별 git commit 분리.** 회귀 발생 시 정확한 revert 가능.

---

## 2. Track A — Pattern Signal (P0, 30분)

### Fix 13A-1: FASHION_PROMPT 에 pattern 필드 추가

**파일:** `server/src/worker.ts`

각 카테고리 항목에 `pattern` 필드 추가:

```typescript
const FASHION_PROMPT = `... (기존 1~3단계 유지) ...

## 3단계 항목 형식 (기존 + pattern 추가):
{
  "color": "...",
  "fit": "...",
  "material": "...",
  "design": "...",
  "subtype": "...",
  "pattern": "단색 | 체크 | 스트라이프 | 플로럴 | 도트 | 카무 | 페이즐리 | 그래픽 | 기타",
  "keywords": [...],
  "searchQueries": [...]
}

규칙:
- pattern 은 의류 표면 무늬 — 색상이 아님
- 체크 패턴이면 searchQueries 첫 번째에 "체크" 토큰 반드시 포함
- 단색이면 searchQueries 에 패턴 토큰 미포함
... (기존 규칙 유지)
`;
```

JSON 예시 업데이트도 동기화:
```typescript
"top_outer": {"color": "네이비 화이트", "subtype": "체크 셔츠", "pattern": "체크", ...}
```

### Fix 13A-2: TypeScript 타입 + softScoreProducts 패턴 신호

```typescript
interface CategoryInfo {
  // 기존 필드 +
  pattern?: '단색' | '체크' | '스트라이프' | '플로럴' | '도트' | '카무' | '페이즐리' | '그래픽' | '기타';
}

interface SoftScoreContext {
  // 기존 필드 +
  pattern?: string;
}

const PATTERN_REGEX: Record<string, RegExp> = {
  '체크': /체크|타탄|플레이드|gingham|check|tartan|plaid/i,
  '스트라이프': /스트라이프|줄무늬|stripe|striped/i,
  '플로럴': /플로럴|꽃무늬|꽃|floral|flower/i,
  '도트': /도트|땡땡이|폴카|dot|polka/i,
  '카무': /카무|밀리터리|군복|camo|camouflage/i,
  '페이즐리': /페이즐리|paisley/i,
  '그래픽': /그래픽|로고|프린트|graphic|logo|print/i,
};

// softScoreProducts 안 추가 (4번 광고 신호 다음):
// 5. 패턴 신호 — Gemini 인식 패턴이 단색 아닌데 title에 패턴 토큰 없으면 강한 페널티
if (ctx.pattern && ctx.pattern !== '단색' && ctx.pattern !== '기타') {
  const re = PATTERN_REGEX[ctx.pattern];
  if (re && !re.test(title)) {
    score *= 0.4;   // 단색 결과는 1순위에 절대 못 옴
  }
}
```

### Fix 13A-3: /api/search/categories 에서 ctx.pattern 전달

```typescript
const ctx: SoftScoreContext = {
  // 기존 +
  pattern: info.pattern,
};
```

### 배포 + 검증

```bash
cd server && npm run build && cd ..
npx wrangler pages deploy dist --project-name=cloi
sleep 30
bash scripts/verify_deploy.sh
# 검증 추가: API 호출 결과의 categories.top_outer.pattern 필드 존재 확인
git commit -m "feat(worker): pattern signal — Gemini detect + softScore penalty (Fix 13A)"
```

---

## 3. Track B — Length Signal (P0, 30분)

### Fix 13B-1: FASHION_PROMPT 에 length 필드 추가

```typescript
"length": "정확 길이 — 미니/숏/3부/5부/버뮤다/7부/칠부/구부/롱/풀렝스 중 가장 가까운 것"
```

상의: "크롭/숏/롱/오버사이즈"
하의: "미니/숏/버뮤다/5부/7부/칠부/롱/풀렝스"
원피스: "미니/미디/맥시"
아우터: "크롭/하프/롱"

### Fix 13B-2: softScoreProducts 길이 신호

```typescript
const SHORT_REGEX = /숏|미니|반바지|short|mini|3부|5부|버뮤다|크롭/i;
const LONG_REGEX = /롱|긴|long|7부|칠부|9부|구부|10부|풀렝스|카프리|capri|맥시/i;

// softScoreProducts 안 추가 (5번 패턴 다음):
// 6. 길이 신호 — 짧은 의류 추정인데 긴 결과 (역도 동일) 강한 페널티
if (ctx.length) {
  const intendedShort = SHORT_REGEX.test(ctx.length);
  const intendedLong = LONG_REGEX.test(ctx.length);
  const titleHasLong = LONG_REGEX.test(title);
  const titleHasShort = SHORT_REGEX.test(title);
  if (intendedShort && titleHasLong && !titleHasShort) score *= 0.3;
  if (intendedLong && titleHasShort && !titleHasLong) score *= 0.3;
}
```

배포 + 검증 + commit:
```bash
git commit -m "feat(worker): length signal — Gemini detect + softScore strong penalty (Fix 13B)"
```

---

## 4. Track C — Ambiguity Handling (P1, 1~2시간)

### Fix 13C-1: alternative_subtypes 필드 추가

**FASHION_PROMPT:**
```typescript
"## 4단계: 모호성 처리 (NEW)
이미지에서 명확히 안 보이는 부위는 alternative_subtypes 명시:
- top_inner.alternative_subtypes: 이너의 소매 모호 시 ['민소매', '반팔'] 같은 대체 표기
- bottom.alternative_subtypes: 길이 모호 시 ['미니 쇼츠', '버뮤다 팬츠']
- 모호성 없으면 빈 배열 또는 null
"
```

### Fix 13C-2: searchQueries 확장

```typescript
// Worker가 alternative_subtypes 받으면 searchQueries 자동 확장:
function expandQueriesWithAlternatives(
  primary: string[],
  color: string | undefined,
  alts: string[] | undefined
): string[] {
  if (!alts || alts.length === 0) return primary;
  const colorPrefix = color ? `${color} ` : '';
  const altQueries = alts.map(alt => `${colorPrefix}${alt}`);
  // 1~2 primary + 1~2 alternative — 다양성 확보
  return [...primary.slice(0, 2), ...altQueries.slice(0, 2)];
}
```

### Fix 13C-3: 결과에 source query 표시 (선택)

```typescript
// 각 product에 어떤 query에서 왔는지 _from_query 표시
// UI에서 사용자가 "이건 다른 가능성이에요" 알 수 있음
```

배포 + 검증 + commit:
```bash
git commit -m "feat(worker): ambiguity handling — alternative_subtypes + query expansion (Fix 13C)"
```

---

## 5. 라이브 검증 — 사용자 케이스 직접 테스트

### Test 5-1: 체크 셔츠 + 쇼츠 + 모호 이너 (사용자 원본)

사용자가 원본 이미지를 올린 후 결과 확인:
- top_outer 1순위: title에 "체크/타탄/플레이드" 포함되어야 함 (단색 셔츠 X)
- bottom 1순위: title에 "미니/쇼츠/반바지" 포함, "칠부/롱" X
- top_inner: 민소매 + 반팔 둘 다 결과에 등장 (alternative_subtypes 효과)

### Test 5-2: 다양한 패턴 검증

1. 플로럴 원피스 → "꽃무늬/플로럴" title 포함만 1순위
2. 줄무늬 티셔츠 → "스트라이프/줄무늬" title 포함만 1순위
3. 단색 니트 → 패턴 페널티 비활성 (정상 동작 확인)

### Test 5-3: 다양한 길이 검증

1. 미니스커트 → 1순위 미니/숏 (롱/맥시 X)
2. 롱드레스 → 1순위 롱/맥시 (미니/숏 X)
3. 버뮤다 팬츠 → 1순위 버뮤다/5부

---

## 6. 자동 5케이스 회귀 테스트

`fashion-search/scripts/live_qa_s13.py` 신규:

```python
import requests, base64, json
URL = 'https://cloi.pages.dev/api/analyze'

CASES = [
    ('check_shirt_shorts.jpg', '체크 셔츠 + 미니 쇼츠 + 흰 이너', {'top_outer.pattern': '체크', 'bottom.length': '미니'}),
    ('floral_dress.jpg', '플로럴 원피스', {'dress.pattern': '플로럴'}),
    ('stripe_top.jpg', '줄무늬 티셔츠', {'top_inner.pattern': '스트라이프'}),
    ('long_pants.jpg', '와이드 롱 팬츠', {'bottom.length': '롱'}),
    ('mini_skirt.jpg', '미니 스커트', {'bottom.length': '미니'}),
]

for img, label, expected in CASES:
    # ... API 호출 + 응답 검증 + top1 title이 expected pattern/length 포함 여부 확인
```

---

## 7. 작업 순서

```bash
cd "C:\Users\Alex KIM\Desktop\사업 프로젝트\인앱토스 1"

# === STEP 0: Deploy 진단 (먼저!) ===
bash scripts/verify_deploy.sh fashion-search/eval/queries/q001.jpg
# Exit 0 안 나오면 즉시 진단 + Pages 재배포

# === Track A: Pattern Signal ===
# Fix 13A-1: FASHION_PROMPT pattern 필드 추가
# Fix 13A-2: PATTERN_REGEX + softScoreProducts 패턴 신호
# Fix 13A-3: ctx.pattern 전달
# 빌드 + 배포 + verify
cd server && npm run build && cd ..
npx wrangler pages deploy dist --project-name=cloi
sleep 30
bash scripts/verify_deploy.sh
git commit -m "feat(worker): pattern signal (Fix 13A)"

# === Track B: Length Signal ===
# Fix 13B-1: FASHION_PROMPT length 필드
# Fix 13B-2: SHORT/LONG_REGEX + softScoreProducts 길이 신호
# 빌드 + 배포 + verify
cd server && npm run build && cd ..
npx wrangler pages deploy dist --project-name=cloi
sleep 30
bash scripts/verify_deploy.sh
git commit -m "feat(worker): length signal (Fix 13B)"

# === Track C: Ambiguity (P1) ===
# Fix 13C-1: alternative_subtypes 필드
# Fix 13C-2: expandQueriesWithAlternatives
# 빌드 + 배포 + verify
cd server && npm run build && cd ..
npx wrangler pages deploy dist --project-name=cloi
sleep 30
bash scripts/verify_deploy.sh
git commit -m "feat(worker): ambiguity handling (Fix 13C)"

# === 라이브 검증 ===
python fashion-search/scripts/live_qa_s13.py > logs/s13_results.txt

# === 종료 ===
git push origin main
# SESSION_STATUS.md 정직하게 업데이트
# 알람 실행
```

---

## 8. 성공 정의

- [ ] STEP 0: verify exit 0 통과
- [ ] Track A: 응답에 categories.*.pattern 필드 존재
- [ ] Track A: 체크 패턴 검색 시 단색 결과 top 5 진입 X
- [ ] Track B: 응답에 categories.*.length 필드 존재
- [ ] Track B: 미니 쇼츠 검색 시 칠부 결과 top 5 진입 X
- [ ] Track C: 응답에 alternative_subtypes 필드 존재
- [ ] Track C: 모호 이너 (반팔/민소매) 검색 시 결과에 두 종류 모두 등장
- [ ] 사용자 원본 이미지 (체크 셔츠 + 쇼츠) 라이브 재테스트 → 1순위 매칭 정확
- [ ] git push + SESSION_STATUS.md + 알람

---

## 9. 위험 + 대응

| 위험 | 대응 |
|------|------|
| Gemini가 pattern 필드 잘못 응답 (단색을 체크로 등) | confidence 신호 부재 → 일단 적용. 잘못된 케이스 발견 시 다음 세션 |
| Pattern 페널티 0.4 너무 강함 (정상 결과도 사라짐) | 라이브 5케이스 측정 후 조정 (0.4 → 0.5 등) |
| Length 페널티 0.3 너무 강함 | 동일 — 측정 후 조정 |
| alternative_subtypes 가 검색 결과 다양성 너무 줘서 핵심 결과 묻힘 | 첫 2개 primary + 첫 2개 alt 으로 균형 |
| FASHION_PROMPT 너무 길어져 Gemini 응답 형식 깨짐 | TypeScript validator로 조기 catch + dryrun |
| Track A/B/C 모두 적용 시 결과가 너무 적음 | softScoreProducts 최솟값 보장 (0.05 + score*0.95) 유지 |

---

## 10. 본질 원칙

1. **신호는 detail 단위로 분해된다 — pattern/length/sleeve 각각 독립.**
2. **추정만 하지 말고 모호성 명시.** Gemini가 자신 없으면 alternative 표기 → 결과 다양성.
3. **Naver는 OR 매칭 — Worker가 AND 매칭 시뮬레이션 필요.** 검색 후 후처리로 강한 신호 부여.
4. **모든 추가 신호는 soft.** Hard reject 절대 금지 (사용자 통찰).

---

## 11. SESSION 14 사전 노트

이번 세션 후 남는 과제:
- **Subtype hard match** — Gemini가 "터틀넥"이라 했는데 "라운드넥" 노출되는 경우
- **사용자 클릭 데이터로 LightGBM ranker** — pattern/length/color/gender weight 학습
- **Track D (다양성, 브랜드 dedupe)** — 같은 브랜드 2개 이상 X
- **Track E (UX)** — _source 배지, 의도 토글, alternative_subtypes 칩 표시
- **vite 빌드 크래시 영구 해결**
- **Cloud Run min-instances=1 비용 검토**

---

## 12. Claude Code 실행 명령어

```bash
cd "C:\Users\Alex KIM\Desktop\사업 프로젝트\인앱토스 1" && claude --dangerously-skip-permissions @scripts/session13_prompt.txt
```

(또는 overnight 스크립트 한 번 더 실행 시 prompt 파일 갱신 필요)

---

## END OF SESSION 13 PROMPT
