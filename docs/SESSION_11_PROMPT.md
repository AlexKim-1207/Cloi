# SESSION 11: 아키텍처 본질 회복 + 사용자 체감 정확도 회복

> **선행 필독:** `docs/DIAGNOSIS_S9_REGRESSION.md`, `docs/SESSION_10_PROMPT.md`,
> 본 세션 0번 항목(STEP B 라이브 재테스트 결과)
>
> **사용자 호소 (2026-05-01 — SESSION 10 배포 후 재테스트):**
> "정확도가 크게 올랐다고 생각이 들지는 않는다."
>
> **본질 원인 한 줄 (SESSION 10에서는 발견 못 한 것):**
> **"우리가 SESSION 9/9-B/10에서 손댄 코드(`fashion-search/`)는 Cold start로 거의 실행되지 않는다.
> UI는 99% Worker 측 Gemini-only fallback path 를 보여주고 있다."**

---

## 0. 충격적 발견 — 라이브 네트워크 재테스트 결과

같은 룩북 이미지 재테스트 (SHA256 해시 다른 두 변형 모두 시도):

```
[1] POST  /api/analyze                                           200  ← UI 진입점
[2] POST  /api/search/categories                                 200  ← 결과 노출 데이터
[3] POST  cloi-api.kyoung361207.workers.dev/api/search?sort_by=quadrant
                                                                503  ← Cloud Run cold start 실패
```

**해석:**
- UI → `/api/analyze` (Worker)
- Worker → Cloud Run `/api/search` 시도 → **30s 타임아웃 또는 503**
- Worker → Gemini-only `analyzeImage` fallback → categories 반환
- UI → `/api/search/categories` (Worker → Naver API per category)
- 결과 표시

**즉, SESSION 9 (탭별 emb), 9-B (HSV/dominant/클러스터), 10 (color 0%/4분면 동적/bag 보호) 모두
사용자에게 노출되지 않는 코드 경로다.**

증거:
- 사용자 화면 탭: `상의 / 하의 / 아우터 / 액세서리` 4개 (Worker `FASHION_PROMPT`의 6개 카테고리 중 일부)
- v3 코드의 13개 탭 (`top_outer/top_inner/outer/bottom/dress/shoes/bag/accessory_*`) 미노출
- 4분면 정렬, color_sim, cluster_size 등 v3 응답 필드 응답에 없음
- recent thumbnail에 "상의·하의·아우터·가방" 라벨 있음 = 한 번이라도 v3가 성공한 적 있는 흔적 (cache hit?), 그러나 새 이미지마다 재현 불가

---

## 1. 진단 — "왜 SESSION 10이 효과 없어 보이나"

### 1.1 진짜 production path

| 컴포넌트 | 실제 호출 빈도 | 설명 |
|---------|--------------|------|
| `server/src/worker.ts:analyzeImage` | **거의 100%** | Gemini 1회 호출 → 6개 카테고리 분류 |
| `server/src/worker.ts:/api/search/categories` | **거의 100%** | Naver Shopping API per category |
| `fashion-search/apps/api/routes_search.py` (Cloud Run) | **<5%** | Cold start 30s 타임아웃 다수 실패 |
| `fashion-search/src/ranking/*.py` (FashionCLIP/color/quadrant) | **<5%** | Cloud Run 안에서만 실행 |

### 1.2 Worker `FASHION_PROMPT` 분석 — 사용자 체감 결정자

`server/src/worker.ts:38~71`의 프롬프트가 **실제 production 분류기**:

```
"카테고리: top(상의) bottom(하의) shoes(신발) outer(아우터) bag(가방) accessory(액세서리)"
"keywords 4~7개, searchQueries 반드시 3개"
```

**한계:**
1. **6개 카테고리 고정** — top_outer/top_inner 분리 없음, 액세서리 세분화 없음
2. **bag 누락 빈번** — 룩북 이미지에서 쇼핑백을 outfit으로 보지 않으면 `null` 반환
3. **searchQueries 자유 형식** — Gemini가 색상 토큰을 항상 포함하지는 않음
4. **레이어드 인식 불가** — "셔츠 안에 티셔츠"가 top 한 항목으로 합쳐짐

### 1.3 Worker `/api/search/categories` 분석 — 사용자 체감 검색기

`server/src/worker.ts:371~427`:
- Per category: `searchQueries.slice(0, 3)` 으로 Naver API 3번 호출 → 합치기
- **Naver API 응답 그대로 반환** — 재랭킹 없음, 색상 필터 없음, 클러스터링 없음
- 결과는 "Naver 자체 정렬"에 100% 의존

**왜 BLACK/WHITE 터틀넥이 1순위인가:**
- 검색어 "베이지 터틀넥" → Naver는 popularity-biased
- 베이지 키워드 매칭되어도 popularity 높은 BLACK이 ranking 위
- Worker는 그대로 통과시킴 → BLACK 1위

### 1.4 Cloud Run 자체 문제

`fashion-search/deploy.sh:18`:
```
--min-instances=0
```

- Cold start 시간: 60~120s (FastAPI + FashionCLIP 모델 로드)
- Worker AbortSignal.timeout(30000) → 30s 후 가차없이 끊음
- 첫 요청은 실패 확정 → 사용자 다시 누르거나 fallback path 가는 순환

---

## 2. 작업 전략 — Triple Track 병행

| Track | 영향 범위 | 효과 시점 | 비용 |
|-------|---------|---------|------|
| **A** | Worker 측 production path 직접 개선 | 즉시 (배포 직후) | 0원 (코드만) |
| **B** | Cloud Run cold start 제거 | 즉시 (min-instances=1 적용 후) | 월 ~$5~15 |
| **C** | v3 path 색상 신호 올바르게 복원 | Track B 완료 후 가시적 | 0원 (코드만) |

**우선순위:** Track A를 1순위로. 사용자 체감 정확도가 가장 빠르게 회복됨.
Track B는 즉시 결정 필요(비용 승인). Track C는 Track B 후 의미 있음.

---

## 3. Track A — Worker 측 Production Path 직접 개선 (P0)

### Fix 11A-1: Worker `FASHION_PROMPT` 전면 재작성

**파일:** `server/src/worker.ts:38~71`

**개선 방향:**
- 카테고리: 6개 → 8개 (top_outer, top_inner 분리, dress 추가)
- 액세서리는 detect 시 sub-type 명시 (sunglasses/necklace/hat/belt 등)
- bag 강조: "들고 있는 것이 핸드백/숄더백/토트백/쇼핑백이면 반드시 bag으로 분류"
- searchQueries 첫 번째에 색상 토큰 강제 포함 ("{color} {category}" 형식)
- 레이어드 명시 처리

**새 프롬프트 (전체 교체):**
```javascript
const FASHION_PROMPT = `당신은 한국 패션 이커머스 전문 MD입니다. 이미지를 부위별로 점검하고 모든 의류/액세서리/가방을 빠짐없이 추출하세요.

## 1단계: 부위별 점검 (보이는 모든 것 나열)
- 머리: 모자/헤어밴드
- 얼굴/눈: 선글라스/안경
- 목: 목걸이/스카프
- 손목: 시계/팔찌
- 손: 반지/장갑
- 상체: 외부(셔츠/카디건/재킷) + 내부(티셔츠/이너) — 레이어드 시 분리
- 허리: 벨트
- 하체: 바지/스커트/원피스
- 발: 신발
- 손에/어깨에: 가방/숄더백/토트백/쇼핑백/클러치 (있으면 반드시 bag)

## 2단계: 카테고리별 분류 — 다음 8개 키 모두 포함 (없으면 null)
top_outer  : 외부 상의 (셔츠/카디건/재킷)
top_inner  : 안쪽 상의 (티셔츠/이너/탱크탑/터틀넥)
outer      : 두꺼운 겉옷 (코트/패딩/점퍼)
bottom     : 하의 (바지/스커트/반바지)
dress      : 원피스/점프수트
shoes      : 신발
bag        : 가방/숄더백/토트백/쇼핑백 (들고 있어도 포함)
accessory  : 액세서리 (선글라스/모자/벨트/시계/목걸이/귀걸이/반지)

## 3단계: 각 카테고리 항목 형식
{
  "color": "구체적 색상명 (예: 라이트 베이지, 다크 그레이)",
  "fit": "오버핏/슬림핏/레귤러/와이드 등",
  "material": "코튼/울/캐시미어/가죽 등",
  "design": "디테일 (예: 와이드카라, H라인, 사각프레임)",
  "subtype": "세부 분류 (top_inner=터틀넥/크롭탑, bag=숄더백/토트백, accessory=선글라스/벨트)",
  "keywords": ["색상 토큰", "subtype", "fit", "material", "design"],
  "searchQueries": [
    "{color} {subtype}",
    "{color} {fit} {subtype}",
    "{material} {subtype}"
  ]
}

## 출력 규칙
- 8개 키 모두 응답에 포함 (없는 항목은 반드시 null)
- searchQueries 첫 번째는 반드시 색상 + subtype 조합 (예: "베이지 터틀넥")
- 작은 액세서리도 보이면 포함
- 가방을 손에 들고 있으면 무시하지 말 것
- 패션 아이템 0개거나 품질 낮으면 {"error": "IMAGE_QUALITY"}

JSON 예시:
{
  "categories": {
    "top_outer": null,
    "top_inner": {"color": "라이트 베이지", "fit": "슬림핏", "material": "캐시미어 니트", "design": "기본 터틀넥", "subtype": "터틀넥", "keywords": ["라이트 베이지", "터틀넥", "슬림핏", "캐시미어 니트"], "searchQueries": ["라이트 베이지 터틀넥", "베이지 슬림핏 터틀넥", "캐시미어 터틀넥 니트"]},
    "outer": {"color": "버건디", "fit": "레귤러", "material": "울", "design": "와이드카라 지퍼 롱코트", "subtype": "롱코트", "keywords": ["버건디", "롱코트", "와이드카라", "울"], "searchQueries": ["버건디 롱코트", "버건디 와이드카라 코트", "울 롱코트 여성"]},
    "bottom": {"color": "다크 그레이", "fit": "H라인", "material": "울", "design": "미디 길이 H라인", "subtype": "미디스커트", "keywords": ["다크 그레이", "미디스커트", "H라인"], "searchQueries": ["다크 그레이 미디스커트", "그레이 H라인 스커트", "울 미디스커트 여성"]},
    "dress": null, "shoes": null,
    "bag": {"color": "다양", "fit": "다양", "material": "다양", "design": "쇼핑백 들고 있음", "subtype": "쇼핑백/핸드백", "keywords": ["여성 가방", "토트백"], "searchQueries": ["여성 토트백", "캐주얼 핸드백", "여성 데일리 가방"]},
    "accessory": {"color": "블랙", "fit": "오버사이즈", "material": "플라스틱", "design": "사각 프레임", "subtype": "선글라스", "keywords": ["블랙 선글라스", "사각", "오버사이즈"], "searchQueries": ["블랙 사각 선글라스", "오버사이즈 선글라스", "여성 선글라스"]}
  },
  "description": "버건디 코트 + 베이지 터틀넥 + 그레이 H라인 스커트의 시크한 가을 룩"
}`;
```

**TypeScript 타입 동시 수정:**
```typescript
type FashionCategoryKey =
  | 'top_outer' | 'top_inner' | 'outer' | 'bottom' | 'dress'
  | 'shoes' | 'bag' | 'accessory';
```

`FashionCategoryKey` enum을 사용하는 모든 위치 (worker.ts + frontend types/index.ts) 동기화.

```bash
git commit -m "feat(worker): rewrite FASHION_PROMPT with 8 categories + color enforcement"
```

---

### Fix 11A-2: `/api/search/categories` 라우트에 색상 단어 강제 주입

**파일:** `server/src/worker.ts:371~427`

**현재:** searchQueries 그대로 Naver에 던짐.

**변경:** 응답된 `info.color`가 있으면 모든 searchQueries 앞에 색상 토큰 강제 prefix.

```typescript
// Fix 11A-2: 색상 토큰 강제 주입
function ensureColorPrefix(queries: string[], color?: string): string[] {
  if (!color) return queries;
  const colorTokens = color.split(/\s+/).filter(t => t.length > 0);
  return queries.map(q => {
    const hasColor = colorTokens.some(t => q.includes(t));
    return hasColor ? q : `${color} ${q}`;
  });
}

// /api/search/categories handler 안에서
const queries = Array.isArray(info.searchQueries) && info.searchQueries.length > 0
  ? info.searchQueries.slice(0, 3)
  : info.searchQuery ? [info.searchQuery]
  : [info.keywords.slice(0, 3).join(' ')];

const colorEnforcedQueries = ensureColorPrefix(queries, info.color);
// 이하 colorEnforcedQueries 사용
```

**검증:** 요청에 "라이트 베이지" 색상 명시되면 모든 Naver 검색 쿼리에 "라이트 베이지" 포함됨 → 결과 후보군 자체가 베이지로 좁혀짐.

```bash
git commit -m "feat(worker): force color token prefix in naver search queries"
```

---

### Fix 11A-3: Naver 결과 후처리 — 색상 단어 미포함 상품 강한 후순위화

**파일:** `server/src/worker.ts:/api/search/categories` 핸들러 안

```typescript
// Fix 11A-3: 색상 단어가 product title에 없으면 후순위
function colorAwareRerank(products: NaverProduct[], color?: string): NaverProduct[] {
  if (!color) return products;
  const colorTokens = color.split(/\s+/).filter(t => t.length >= 2);
  if (colorTokens.length === 0) return products;

  const titleHasColor = (p: NaverProduct) =>
    colorTokens.some(t => (p.title || '').toLowerCase().includes(t.toLowerCase()));

  // 1pass: 색상 매치 먼저, 미매치 뒤로
  const matched = products.filter(titleHasColor);
  const unmatched = products.filter(p => !titleHasColor(p));
  return [...matched, ...unmatched];
}

// 검색 후 적용
const reranked = colorAwareRerank(searchResult.products, info.color);
```

**검증:** "베이지" 검색 결과 중 title에 "베이지/라이트베이지/연베이지" 들어간 상품이 위로 올라옴.

```bash
git commit -m "feat(worker): color-aware rerank — title-matching products first"
```

---

### Fix 11A-4: 같은 SKU 클러스터링 (Worker 단순 구현)

**파일:** `server/src/worker.ts:/api/search/categories` 핸들러 안

```typescript
// Fix 11A-4: 같은 상품 다판매처 묶기 — productId 또는 title prefix 일치
function dedupeBySku(products: NaverProduct[]): NaverProduct[] {
  const seen = new Set<string>();
  const out: NaverProduct[] = [];
  for (const p of products) {
    // productId가 있으면 그대로
    const pidKey = p.productId || '';
    // title 정규화: 처음 6단어 + 핵심 토큰
    const titleKey = (p.title || '')
      .replace(/<[^>]+>/g, '')
      .toLowerCase()
      .split(/\s+/)
      .slice(0, 6)
      .sort()
      .join(' ');
    const key = pidKey || titleKey;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(p);
  }
  return out;
}
```

**검증:** 같은 셔츠 5개 판매처 → 1개로 묶임.

```bash
git commit -m "feat(worker): dedupe same-SKU across sellers (productId or title prefix)"
```

---

### Fix 11A-5: 응답에 detected categories 보강 (UI 디버깅 + 사용자 인지)

**파일:** `server/src/worker.ts:/api/search/categories` 응답 직전

```typescript
return c.json({
  results: filtered,
  // 신규: 분석 단계 누락 카테고리 알림
  missing_categories: Object.entries(categories)
    .filter(([_, v]) => v === null)
    .map(([k]) => k),
});
```

UI는 (선택) "이 이미지에서 [bag] 카테고리는 분석되지 않았어요" 같은 메타 표시.

```bash
git commit -m "feat(worker): expose missing_categories in search response"
```

---

## 4. Track B — Cloud Run cold start 제거 (P0)

### Fix 11B-1: Cloud Run min-instances=1

**파일:** `fashion-search/deploy.sh:18`

```bash
# 변경 전
--min-instances=0 \

# 변경 후
--min-instances=1 \
```

**비용 영향:** asia-northeast3, 2Gi RAM, 2 vCPU, 1 instance always-on
- 약 월 $20~30 (Cloud Run pricing 기준)
- → 사용자 체감 latency 30s+ → 1~3s로 회복
- → v3 path가 실제로 호출되며 SESSION 9/9-B/10 작업이 살아남

**대안 (비용 절감):** Cloud Run scheduled "warming" — Cloud Scheduler가 매 5분마다 /health ping
- 비용 거의 0
- 단, 단점: 실제 사용 없을 때도 컴퓨팅
- min-instances=1 가 더 안정적

```bash
# 배포
bash fashion-search/deploy.sh

git commit -m "ops(cloud-run): min-instances 0 to 1 (eliminate cold start)"
```

### Fix 11B-2: Worker timeout 30s → 45s + 더 친절한 fallback 메시지

**파일:** `server/src/worker.ts:310`

```typescript
const upstream = await fetch(`${fashionSearchUrl}/api/search`, {
  method: 'POST',
  body: form,
  signal: AbortSignal.timeout(45000),  // 30000 → 45000
});
```

**의도:** min-instances=1로 cold start 거의 없지만, 모델 reload 시 안전 마진.

```bash
git commit -m "fix(worker): cloud-run timeout 30s to 45s for safety margin"
```

### Fix 11B-3: 응답에 source flag 노출 (어떤 path 실행됐는지 사용자 인지)

**파일:** `server/src/worker.ts:/api/analyze` 두 가지 분기 모두

```typescript
// v3 분기
return c.json({ ...data, _source: 'v3', _imageHash: imageHash });

// fallback Gemini 분기 (현재 source 표시 없음)
const result = await analyzeImage(c.env.GEMINI_API_KEY, imageBase64, mimeType);
return c.json({ ...result, _source: 'worker_gemini' });
```

UI는 _source가 'worker_gemini'면 작은 배지 "빠른 모드 (정밀 분석 미적용)" 표시. 디버깅 + 사용자 기대치 조정.

```bash
git commit -m "feat(api): expose _source flag (v3 vs worker_gemini)"
```

---

## 5. Track C — Cloud Run v3 path 색상 신호 올바르게 복원 (P1)

> Track A+B 완료 후 v3 path가 실제로 가동되면 이 작업이 의미를 가짐.

### Fix 11C-1: HSV Hue 순환성 + Lab 색공간 변환

**파일:** `fashion-search/src/ranking/color_hist.py`

```python
"""Lab + HSV-circular 색상 매칭 (SESSION 11 Track C 부활).

기존 결함 해결:
- Hue 0.0과 1.0 같은 색 → min(d, 1-d) 처리
- Lab 색공간 = 인간 시각 거리에 가까움
- 의류 영역만 segmentation (rembg) 후 색 추출
"""
from typing import Optional
import numpy as np
from PIL import Image


def _rgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    """RGB [0,255] → CIE Lab. 공식 변환 (sRGB → XYZ → Lab)."""
    arr = rgb.astype(np.float32) / 255.0
    # sRGB linearization
    mask = arr > 0.04045
    arr = np.where(mask, ((arr + 0.055) / 1.055) ** 2.4, arr / 12.92)
    # sRGB → XYZ (D65)
    M = np.array([
        [0.4124564, 0.3575761, 0.1804375],
        [0.2126729, 0.7151522, 0.0721750],
        [0.0193339, 0.1191920, 0.9503041],
    ])
    xyz = arr @ M.T
    # XYZ → Lab (D65 ref white)
    ref = np.array([0.95047, 1.0, 1.08883])
    xyz_ref = xyz / ref
    eps = 0.008856
    f = np.where(xyz_ref > eps, xyz_ref ** (1/3), (7.787 * xyz_ref) + 16/116)
    L = 116 * f[..., 1] - 16
    a = 500 * (f[..., 0] - f[..., 1])
    b = 200 * (f[..., 1] - f[..., 2])
    return np.stack([L, a, b], axis=-1)


def compute_lab_histogram(image: Image.Image, l_bins: int = 8, ab_bins: int = 8) -> np.ndarray:
    """Lab 3D 히스토그램. L 8 bins (0~100), a/b 8 bins each (-128~127)."""
    rgb = np.array(image.convert('RGB'))
    lab = _rgb_to_lab(rgb).reshape(-1, 3)
    hist, _ = np.histogramdd(
        lab,
        bins=[l_bins, ab_bins, ab_bins],
        range=[(0, 100), (-128, 127), (-128, 127)],
    )
    flat = hist.flatten()
    norm = np.linalg.norm(flat) + 1e-8
    return flat / norm


def hue_circular_distance(h1: float, h2: float) -> float:
    """HSV Hue [0,1] 순환 거리. 빨강 0과 1은 같은 색 → 거리 0."""
    d = abs(h1 - h2)
    return min(d, 1.0 - d)


def color_score_v2(query_hist: np.ndarray, product_hist: np.ndarray) -> float:
    """Lab 히스토그램 코사인 유사도. Hue 순환성 자동 해결 (Lab은 순환 없음)."""
    sim = float(np.dot(query_hist, product_hist))
    return max(0.0, min(1.0, sim))
```

`mood_ranker.py`에서 사용:
```python
from src.ranking.color_hist import compute_lab_histogram, color_score_v2

def compute_clothing_score(visual_sim, color_sim, naver_rank_score):
    # SESSION 11C: Lab 색상 신호 부활. 단계별 가중치 5%부터 시작.
    return visual_sim * 0.85 + color_sim * 0.10 + naver_rank_score * 0.05
```

**색상 가중치는 단계별로 부활:**
- 11C-1: 5% (회귀 검증)
- 11C-2: 10% (회귀 없으면)
- 11C-3 (다음 세션): 15~20% (segmentation 후)

```bash
git commit -m "feat(color): Lab histogram + Hue-circular distance (Track C revival)"
```

### Fix 11C-2: 의류 segmentation — `rembg` 통합

**파일:** `fashion-search/src/preprocess/segmentation.py` (신규)

```python
"""의류 영역만 추출 — 배경/피부 제거 후 색 분포 정확화."""
from io import BytesIO
from PIL import Image

try:
    from rembg import remove, new_session
    _RMBG_SESSION = new_session("u2netp")  # 빠른 모델
    _RMBG_AVAILABLE = True
except ImportError:
    _RMBG_AVAILABLE = False


def remove_background(image: Image.Image) -> Image.Image:
    """배경 제거. rembg 없으면 원본 반환."""
    if not _RMBG_AVAILABLE:
        return image
    buf = BytesIO()
    image.save(buf, format='PNG')
    out = remove(buf.getvalue(), session=_RMBG_SESSION)
    return Image.open(BytesIO(out)).convert('RGB')
```

**`requirements.txt` 추가:**
```
rembg==2.0.59
```

**`routes_search.py:_calc_clip_embeddings_and_hists` 수정:**
- 상품 썸네일 다운로드 후 `remove_background` 적용 → 흰 배경 제거
- 그 위에서 Lab 히스토그램 계산

```bash
git commit -m "feat(preprocess): rembg-based background removal for color extraction"
```

### Fix 11C-3: 상품 썸네일 center crop fallback

**파일:** `fashion-search/src/ranking/color_hist.py` 또는 routes_search

rembg가 실패/느린 경우 단순 center crop (중앙 60% 영역)으로 흰 여백 비율 감소:

```python
def center_crop(image: Image.Image, ratio: float = 0.6) -> Image.Image:
    w, h = image.size
    cw, ch = int(w * ratio), int(h * ratio)
    left = (w - cw) // 2
    top = (h - ch) // 2
    return image.crop((left, top, left + cw, top + ch))
```

```bash
git commit -m "feat(color): center-crop fallback when segmentation unavailable"
```

---

## 6. 정량 측정

### 6.1 Track A 측정 — 라이브 정성 (eval set 부적합, lookbook 직접)

**테스트 이미지 5장 준비 (`fashion-search/tests/fixtures/lookbook_*.jpg`):**
1. 버건디 코트 + 베이지 터틀넥 + 다크그레이 H라인 (이번 회귀 검증 대표)
2. 화이트 셔츠 + 데님 + 스니커즈 + 토트백 (간결 캐주얼)
3. 블랙 미니드레스 + 빨간 가방 (선명한 색)
4. 후드티 + 진주 목걸이 + 모자 (액세서리 다수)
5. 핑크 코트 + 화이트 이너 + 청바지 (중간 색)

**자동 테스트 스크립트:**
```python
# fashion-search/scripts/live_qa_track_a.py
import requests, json
URL = 'https://cloi-api.kyoung361207.workers.dev/api/analyze'
IMAGES = ['lookbook_burgundy.jpg', 'lookbook_casual.jpg', 'lookbook_dress.jpg',
          'lookbook_hood.jpg', 'lookbook_pink.jpg']

for img_path in IMAGES:
    with open(f'tests/fixtures/{img_path}', 'rb') as f:
        b64 = base64.b64encode(f.read()).decode()
    r = requests.post(URL, json={'imageBase64': b64, 'mimeType': 'image/jpeg'})
    j = r.json()
    print(f"\n=== {img_path} ===")
    print(f"_source: {j.get('_source', '?')}")
    if 'categories' in j:
        for cat, info in j['categories'].items():
            if info:
                print(f"  {cat}: color={info.get('color')}, queries={info.get('searchQueries', [])[:1]}")
```

기대: bag 누락률, 색상 일치율 정량화.

### 6.2 Track B+C 측정 — eval set 정량

```bash
cd fashion-search
python -m eval.runner --embedder fashion_clip --tag s11_track_bc
python -m eval.compare --tags baseline_s9b s10_final s11_track_bc
```

**성공 기준:**
| 지표 | Track A 후 | Track B+C 후 |
|------|----------|--------------|
| 라이브 베이지 터틀넥 → 1위 색상 매칭 | ≥ 60% | ≥ 80% |
| 라이브 bag 탭 누락률 | < 20% | < 10% |
| eval Recall@10 | (Track A 영향 거의 없음) | ≥ 0.85 |
| Cloud Run 응답 latency p50 | (변동 없음) | ≤ 2s (cold start 제거 효과) |
| Worker fallback 비율 | (Track A 영향 없음) | < 10% |

---

## 7. 작업 순서 (Claude Code 한 번에 보기)

```bash
cd "C:\Users\Alex KIM\Desktop\사업 프로젝트\인앱토스 1"

# === Track A: Worker 즉효 개선 ===
# Fix 11A-1: FASHION_PROMPT 8 카테고리 + 색상 강제
# Fix 11A-2: ensureColorPrefix 함수 + 적용
# Fix 11A-3: colorAwareRerank 함수 + 적용
# Fix 11A-4: dedupeBySku 함수 + 적용
# Fix 11A-5: missing_categories 응답 추가

# Worker 빌드 + 배포
cd server && npm run build && npx wrangler deploy && cd ..

# === Track B: Cloud Run cold start 제거 ===
# Fix 11B-1: deploy.sh --min-instances=1
# Fix 11B-2: Worker timeout 45s
# Fix 11B-3: _source flag

bash fashion-search/deploy.sh
cd server && npx wrangler deploy && cd ..

# === Track C: 색상 신호 올바르게 부활 ===
# Fix 11C-1: Lab histogram + Hue circular
# Fix 11C-2: rembg segmentation
# Fix 11C-3: center crop fallback

bash fashion-search/deploy.sh

# === 측정 ===
python fashion-search/scripts/live_qa_track_a.py > track_a_results.txt
cd fashion-search && python -m eval.compare --tags baseline_s9b s10_final s11_track_bc

# === 라이브 재테스트 ===
# 사람 또는 자동 — 5개 lookbook 이미지로 회복 확인

# === Push ===
git push origin main

# === SESSION_STATUS.md 업데이트 + 알람 ===
```

---

## 8. 성공 정의 (Done Criteria)

- [ ] Track A 5건 commit + Worker 배포 완료
- [ ] Track B 3건 commit + Cloud Run min-instances=1 적용 (cold start 측정 < 5s)
- [ ] Track C 3건 commit + Cloud Run 배포
- [ ] 라이브 5개 lookbook 테스트 — 색상 매칭 1위 적중률 ≥ 60% (Track A 후)
- [ ] 라이브 lookbook bag 탭 누락률 < 20% (Track A 후)
- [ ] eval Recall@10 ≥ 0.85 (Track C 후)
- [ ] git push origin main
- [ ] SESSION_STATUS.md 업데이트
- [ ] **알람 실행** (CLAUDE.md 종료 절차)

---

## 9. 위험 요소 + 대응

| 위험 | 대응 |
|------|------|
| Worker FASHION_PROMPT 변경으로 Gemini 응답 형식 깨짐 | TypeScript 타입 엄격 검증 + 8키 모두 null 허용 |
| `searchQueries`에 색상 강제 주입으로 검색 결과 0건 | colorEnforcedQueries 시도 후 0건이면 원본 queries로 재시도 (graceful fallback) |
| Cloud Run min-instances=1 비용 부담 | 월 $20~30 결제 가능 여부 사전 확인. 불가 시 Cloud Scheduler warming 대안 |
| rembg 의존성 추가로 빌드 깨짐 | requirements.txt 추가 후 dockerfile 빌드 검증 (rembg는 onnxruntime 의존) |
| Lab 변환 perf 저하 | numpy 행렬 연산이라 빠름. 그래도 hist 계산만 1차로 적용, dominant는 다음 세션 |
| Worker fallback 결과가 v3보다 좋아 보이는 사용자 혼란 | _source 배지로 명시 |

---

## 10. 본질 원칙 (반복 방지)

> **"우리가 손댄 코드와 사용자가 보는 코드가 같은지 항상 검증한다."**
>
> SESSION 9/9-B/10에서 우리는 `fashion-search/`만 수정했지만 사용자는 99% Worker fallback path를 본다.
> **모든 변경 후 Network 탭으로 어느 endpoint가 호출되는지 직접 확인**해야 한다.
>
> 라이브 테스트 시 반드시 확인:
> - `/api/analyze` 응답 `_source` 필드
> - `/api/search/categories` 호출 여부 (있으면 Cloud Run path 미사용)
> - 응답에 `tabs` 필드 (v3) vs `categories` 필드 (Worker fallback) 어느 것 들어왔는지

---

## 11. SESSION 12 사전 노트 (이번 세션 후 잔여)

- 사용자 클릭 데이터로 LightGBM ranker 학습 (impression 테이블 활용)
- FashionCLIP LoRA fine-tune (한국 패션 1~2만장)
- Cloud Run 응답 streaming (Worker가 부분 결과부터 보여주기)
- 가격 정렬/관련도 정렬 토글 UI 강화

---

## 12. Claude Code 실행 명령어 (한 줄 복사)

```bash
cd "C:\Users\Alex KIM\Desktop\사업 프로젝트\인앱토스 1" && claude --dangerously-skip-permissions "docs/SESSION_11_PROMPT.md 정독 후 Track A → B → C 순서대로 정확히 실행. Track A는 server/src/worker.ts 수정 + npm run build + wrangler deploy. Track B는 fashion-search/deploy.sh 수정 + bash deploy.sh + worker.ts timeout 수정 + 재배포. Track C는 fashion-search/src/ranking/color_hist.py + segmentation.py + mood_ranker.py 수정 + Cloud Run 재배포. 각 Fix 끝나면 git commit. Track A 끝나면 라이브 5개 lookbook 테스트. 종료 시 SESSION_STATUS.md 업데이트 + 알람. 본질 원칙: '사용자가 보는 코드 path가 우리가 수정한 코드 path와 같은지 항상 확인'. /api/analyze 응답에 _source='v3'가 보일 때까지 Track B를 끝까지 밀어붙일 것."
```

---

## END OF SESSION 11 PROMPT
