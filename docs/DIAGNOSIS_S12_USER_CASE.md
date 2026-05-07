# 사용자 케이스 진단 — 체크 셔츠 + 미니 쇼츠 + 흰 이너

> **작성일:** 2026-05-02
> **사용자 호소:** "이너 반팔/민소매 모호 — 민소매로만 검색됨. 아우터는 체크 난방이여야 하는데 무관한 결과. 바지는 짧은 쇼츠인데 칠부바지 결과. 키워드는 잘 들어갔는데 결과가 다름."
> **결론 한 줄:** **SESSION 11+12에서 성별/가격/색상 신호는 추가했으나 "패턴/길이/모호성" 신호 3개가 누락. 이게 정확히 사용자가 호소한 3가지 문제와 일치.**

---

## 0. TL;DR

사용자 호소 3개 — 각각의 root cause:

| 호소 | Gemini 단계 | Worker 후처리 단계 | Root Cause |
|------|----------|----------|----------|
| 이너 반팔/민소매 모호 → 민소매만 결과 | Gemini가 단일 subtype 추정 (alternative 없음) | softScoreProducts에 길이/소매 신호 없음 | **모호성 처리 부재** |
| 아우터 체크인데 단색 결과 | searchQuery에 "체크" 들어감 (OK) | softScoreProducts가 색상만 검사, 패턴 미검사 | **패턴 신호 부재** |
| 바지 미니 쇼츠인데 칠부 결과 | searchQuery에 "미니 쇼츠" 들어감 (OK) | softScoreProducts에 길이 신호 없음 | **길이 신호 부재** |

→ 사용자 발언 "키워드는 잘 들어갔는데 결과는 다르다" = Gemini 분석은 정확, **Worker 후처리 신호 3개 부족**.

---

## 1. 코드 흐름 분석 — 어디서 깨지는가

### 현재 파이프라인 (server/src/worker.ts:580~625)

```
사용자 이미지
  ↓
Gemini analyzeImage  → categories (각 카테고리에 color, subtype, searchQueries[3])
  ↓
Worker /api/search/categories:
  ↓
ensureColorPrefix(queries, color)   ← 색상 prefix만 강제
  ↓
Naver Shopping API per query × 3   → 합치기 (60~120개)
  ↓
dedupeBySku(merged)                 ← productId/title prefix 중복 제거
  ↓
softScoreProducts(deduped, ctx)     ← 성별/가격/색상 soft signal
  ↓
slice(0, 40)                         ← 상위 40개 반환
```

### softScoreProducts 안 검사하는 4 신호

```typescript
function softScoreProducts(products, ctx) {
  // 1. ✅ Gender signal — title에 "남성/여성" 토큰 매칭 → soft penalty
  // 2. ✅ Price range — 추정 가격대 벗어나면 soft penalty  
  // 3. ✅ Color — title에 색상 단어 없으면 0.75x
  // 4. ✅ Ad keyword — "100% 정품/최저가" 0.92x
  //
  // ❌ NO pattern signal — "체크/스트라이프/플로럴/도트" 미검사
  // ❌ NO length signal — "미니/숏/롱/칠부/카프리" 미검사
  // ❌ NO sleeve signal — "반팔/민소매/긴팔/슬리브리스" 미검사
  // ❌ NO subtype hard match — Gemini가 "터틀넥"이라 했어도 "라운드넥"이 통과
}
```

이게 정확히 사용자가 호소한 3가지 문제의 코드 위치.

---

## 2. 사용자 케이스 분해 (시뮬레이션)

### 입력
- 미러 셀카, 흰 이너 (반팔 또는 민소매), 네이비 체크 셔츠 아우터, 블랙 데님 미니 쇼츠, 블랙 미니백

### Gemini 추정 분석 (예상)

```json
{
  "gender": "female",
  "gender_confidence": 0.95,
  "price_tier": "mid",
  "price_range_estimate": {min: 30000, max: 100000},
  "vibe": ["캐주얼", "스트리트"],
  "season": "summer",
  "categories": {
    "top_outer": {
      "color": "네이비 화이트",
      "subtype": "체크 셔츠",
      "searchQueries": [
        "네이비 화이트 체크 셔츠",
        "오버핏 체크 셔츠",
        "타탄 체크 남방"
      ]
    },
    "top_inner": {
      "color": "화이트",
      "subtype": "민소매",   ← 또는 "반팔" — Gemini가 단일 추정
      "searchQueries": [
        "화이트 민소매 탑",   ← 모호한데 단일 결과만
        "베이직 슬리브리스",
        "화이트 나시 티셔츠"
      ]
    },
    "bottom": {
      "color": "블랙",
      "subtype": "미니 데님 쇼츠",
      "searchQueries": [
        "블랙 데님 미니 쇼츠",
        "블랙 데님 반바지",
        "데미지 미니 데님 쇼츠"
      ]
    },
    "bag": { "color": "블랙", "subtype": "미니 숄더백", ... }
  }
}
```

→ **Gemini 분석은 정확.** 사용자도 "키워드 잘 들어갔다" 확인.

### Naver 검색 결과 (예상)

각 쿼리당 20개씩 검색 → 카테고리당 60개 후보 → dedupe → softScore → top 40

**문제 1: 아우터 (체크 셔츠)**

쿼리 "네이비 화이트 체크 셔츠" → Naver 응답:
- 1순위 광고: "여성 베이직 솔리드 셔츠 네이비" (단색!)
- 2순위 광고: "오버핏 화이트 셔츠"
- 3순위: 네이비 체크 셔츠 ✅
- ...

softScoreProducts는 색상 토큰 ("네이비/화이트") 매칭만 봄 → 1, 2순위 단색 셔츠도 색상 매칭됨 → 페널티 없음 → **광고가 1순위 그대로**

**문제 2: 이너 (반팔 vs 민소매)**

Gemini가 "민소매"로 추정 → 모든 쿼리가 "민소매/슬리브리스/나시" → 결과 100% 민소매. 사용자가 실제로 반팔이었다면 대체재 0.

**문제 3: 바지 (쇼츠 vs 칠부)**

쿼리 "블랙 데님 미니 쇼츠" → Naver:
- 1순위: 데님 칠부 팬츠 블랙 (Naver 검색은 토큰 OR 매칭 → "블랙 데님" 토큰만 매칭되어 노출)
- 2순위: 데님 롱 진 블랙
- 3순위: 데님 미니 쇼츠 ✅

softScoreProducts는 길이 신호 X → 1, 2순위 칠부/롱이 색상 매칭 OK라 페널티 없음 → 그대로 노출.

---

## 3. 해결 방안 — 3개 신호 추가 (SESSION 13)

### Fix 1: 패턴 신호 (Pattern Signal)

**FASHION_PROMPT 확장:**
```typescript
"pattern": "단색 / 체크 / 스트라이프 / 플로럴 / 도트 / 카무 / 페이즐리 / 그래픽 / 기타"
```

**softScoreProducts 추가:**
```typescript
// 6. 패턴 신호 — Gemini 인식 패턴이 title에 없으면 강한 페널티
if (ctx.pattern && ctx.pattern !== '단색') {
  const patternTokens = {
    '체크': /체크|타탄|플레이드|gingham|check|tartan/i,
    '스트라이프': /스트라이프|줄무늬|stripe|striped/i,
    '플로럴': /플로럴|꽃무늬|floral|flower/i,
    '도트': /도트|땡땡이|폴카|dot|polka/i,
    '카무': /카무|밀리터리|군복|camo|camouflage/i,
  };
  const re = patternTokens[ctx.pattern];
  if (re && !re.test(title)) {
    // 단색 결과는 1순위에 절대 못 옴
    score *= 0.4;
  }
}
```

**효과:** 체크 셔츠 검색 시 단색 셔츠 결과는 score 0.4x → top 5에서 사라짐.

### Fix 2: 길이 신호 (Length Signal)

**FASHION_PROMPT 확장:**
```typescript
"length": "정확한 길이 명시 — 미니/숏/3부/5부/버뮤다/7부/칠부/롱 등"
```

**softScoreProducts 추가:**
```typescript
// 7. 길이 신호 — 짧은 의류에 긴 결과 강한 페널티 (역도 마찬가지)
if (ctx.length) {
  const SHORT = /숏|미니|반바지|short|mini|3부|5부|버뮤다/i;
  const LONG = /롱|긴|long|7부|칠부|구부|10부|풀렝스|카프리|capri/i;
  const isShortIntended = SHORT.test(ctx.length);
  const isLongIntended = LONG.test(ctx.length);
  const titleIsLong = LONG.test(title);
  const titleIsShort = SHORT.test(title);
  if (isShortIntended && titleIsLong) score *= 0.3;   // 짧은 거 원했는데 긴 결과 → 강한 페널티
  if (isLongIntended && titleIsShort) score *= 0.3;
}
```

**효과:** "미니 데님 쇼츠" 검색 시 "데님 칠부 팬츠" 결과는 score 0.3x → top 5에서 사라짐.

### Fix 3: 모호성 처리 (Ambiguity Handling)

**FASHION_PROMPT 확장:**
```typescript
"ambiguity": "이미지에서 명확히 안 보이는 부위는 'unsure_사항' 명시. 예: 'unsure_sleeve' (소매 길이 모름)"
"alternative_subtypes": ["대체 가능 subtype 1~3개"]
```

**searchQueries 확장:**
- Gemini가 alternative_subtypes에 ["민소매", "반팔"] 명시 시:
  - searchQueries[0] = 1순위 추정 ("민소매")
  - searchQueries[1] = 2순위 추정 ("반팔")
  - searchQueries[2] = generic ("이너")

**Worker /api/search/categories 수정:**
- alternative_subtypes 있으면 결과를 "추정 1순위 + 대체재" 두 그룹으로 분리해서 보여주거나, 통합 후 다양성 가중치

**효과:** 이너가 모호할 때 민소매 + 반팔 둘 다 결과에 등장 → 사용자가 본인 outfit에 맞는 것 선택 가능.

---

## 4. SESSION 11+12 평가 vs 사용자 호소 갭

| 신호 | SESSION 11+12 적용 | 사용자 케이스 적용 |
|------|------------------|------------------|
| Gender (성별) | ✅ | ✅ female 정확 |
| Price tier (가격대) | ✅ | ✅ mid 정확 |
| Color (색상) | ✅ | ✅ 색상 매칭 |
| Vibe / Season | ✅ | ✅ 캐주얼/스트리트 |
| Subtype (세부 분류) | ⚠ 정의만 됨, 매칭 약함 | ❌ "체크" 인식되나 결과는 단색 |
| **Pattern (패턴)** | ❌ | **❌ 사용자 호소 1** |
| **Length (길이)** | ❌ | **❌ 사용자 호소 2** |
| **Ambiguity (모호성)** | ❌ | **❌ 사용자 호소 3** |

→ **SESSION 11+12는 "outfit-level meta (성별/가격/분위기)" 잘 풀었음. 이제 SESSION 13은 "item-level detail (패턴/길이/소매)" 풀어야 함.**

---

## 5. 우선순위 권장

| Fix | 영향 | 구현 난이도 | 검증 난이도 | 우선 |
|-----|-----|----------|----------|------|
| 패턴 신호 (체크/스트라이프/플로럴) | 🔴 매우 큼 — 사용자 호소 핵심 | 낮음 (단순 정규식) | 쉬움 | 🥇 P0 |
| 길이 신호 (쇼츠/롱) | 🔴 매우 큼 — 사용자 호소 핵심 | 낮음 (단순 정규식) | 쉬움 | 🥇 P0 |
| 모호성 처리 (alternative subtypes) | 🟠 큼 — 결과 다양성 | 중간 (Gemini 프롬프트 + Worker 재구성) | 어려움 | 🥈 P1 |
| Subtype hard match | 🟠 보조 | 중간 | 중간 | 🥈 P1 |

P0 둘은 30분 안에 끝남. P1은 1~2시간.

---

## 6. 다음 행동

→ **`docs/SESSION_13_PROMPT.md`** 정독 후 Track A (패턴 + 길이 신호) 즉시 실행.

P0만 적용해도 사용자 케이스 핵심 호소 즉시 해결.

---

# 끝
