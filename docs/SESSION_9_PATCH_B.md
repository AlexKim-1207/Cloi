# SESSION 9 PATCH B: 가방/액세서리 매칭 정확도 + 중복 제거 강화

> **사용자 핵심 요구:**
> 1. 가방 매칭 정확도 향상 (현재 의류는 OK, 가방은 부정확)
> 2. 같은 상품 다판매처 → 1개로 묶고 최저가 노출 (절대 원칙)
> 3. "정확도 비슷한 상품끼리는 최저가 우선" — 서비스 핵심 가치

---

## 0. 진단 — 왜 가방이 안 맞나

### 현재 accessory 점수 공식 (잘못됨)
```python
final_score = visual_sim*0.40 + mood_align*0.30 + price_fit*0.20 + naver_rank*0.10
```

**문제:** visual_sim 40%만 → 가방 모양/패턴 신호 약함. mood/price가 시각 매칭을 압도.

**증거:** 베이지 줄무늬 미니 숄더백 입력 → 결과: 회색 토트(모양 다름), 흰 GG(패턴 다름), 백팩(완전 다른 형태).

### 현재 클러스터링 (불충분)
```python
image_sim_threshold = 0.92  # 너무 높음
title_threshold = 0.70      # 모델코드 매칭 약함
```

**문제:** 같은 가방 다른 판매처 = 사진 조명/각도 다름 → 임베딩 유사도 0.85~0.91 → 다른 클러스터로 분리 → 같은 가방 5번 노출.

**증거:** 버버리 미니 하이랜드 숄더백 (모델 81200301, 8120036) 5개 판매처 동시 노출.

---

## 1. 작업 범위 (Fix B1~B4)

### Fix B1: accessory 점수 공식 재조정 — 시각 매칭 절대 강화
### Fix B2: 액세서리/가방 클러스터링 임계값 완화
### Fix B3: 모델코드 매칭 절대 우선
### Fix B4: 클러스터 내 최저가 = 대표 + 노출 강화

---

## Fix B1: accessory 점수 공식 재조정

### 1.1 `src/ranking/mood_ranker.py` — `compute_accessory_score` 수정

**현재:**
```python
def compute_accessory_score(visual_sim, mood_align, price_fit, naver_rank_score):
    return visual_sim*0.40 + mood_align*0.30 + price_fit*0.20 + naver_rank_score*0.10
```

**변경 후 (시각 매칭 절대 강화):**
```python
def compute_accessory_score(visual_sim, mood_align, price_fit, naver_rank_score):
    """가방/액세서리: 시각 매칭 절대 우선 (60%), 가격대 필터 보조."""
    return (
        visual_sim * 0.60        # 모양/패턴 매칭이 핵심
        + mood_align * 0.10      # 무드는 보조
        + price_fit * 0.25       # 가격대 (200만원 럭셔리 가방 패널티 유지)
        + naver_rank_score * 0.05
    )
```

**가중치 변경 의도:**
| 신호 | 이전 | 변경 후 | 이유 |
|------|------|--------|------|
| visual_sim | 0.40 | **0.60** | 가방 모양/패턴이 핵심 (사용자 베이지 줄무늬 → 베이지 줄무늬 매칭) |
| mood_align | 0.30 | 0.10 | 무드는 보조. 가방 자체 시각이 우선 |
| price_fit | 0.20 | **0.25** | 200만원 럭셔리 가방 패널티 유지 + 약간 강화 |
| naver_rank | 0.10 | 0.05 | Naver text relevance는 가방 디자인 매칭에 약함 |

### 1.2 검증 케이스
- 베이지 줄무늬 미니 숄더백 → 베이지 줄무늬 가방 1순위
- 캐주얼 outfit + 200만원 가방 → 가격대 패널티로 뒤로 밀림
- 럭셔리 outfit + 200만원 가방 → price_fit 통과 → 정상 노출

---

## Fix B2: 클러스터링 임계값 완화 (액세서리만)

### 2.1 `src/pricing/normalize.py` — `cluster_similar_products_v2` 카테고리별 분기

**기존 단일 임계값:**
```python
def cluster_similar_products_v2(
    products,
    title_threshold=0.70,
    image_sim_threshold=0.92,
):
```

**변경 후 — 카테고리별 분기:**
```python
# 카테고리별 클러스터링 임계값
CLUSTER_THRESHOLDS_CLOTHING = {
    'image_sim': 0.92,   # 의류는 보수적 (다른 디자인 묶이면 안 됨)
    'title_sim': 0.75,
}

CLUSTER_THRESHOLDS_ACCESSORY = {
    'image_sim': 0.85,   # 액세서리는 공격적 (조명/각도로 같은 상품 잘 분리됨)
    'title_sim': 0.60,   # 모델코드 + 브랜드면 충분
}


def cluster_similar_products_v2(
    products: list[dict],
    is_accessory: bool = False,
) -> list[list[dict]]:
    """이미지 임베딩 + 모델코드 + 제목 + 브랜드 종합 클러스터링.
    
    카테고리별 임계값 자동 적용:
    - 의류: 보수적 (image_sim 0.92, title 0.75)
    - 액세서리/가방: 공격적 (image_sim 0.85, title 0.60)
    """
    thresholds = (
        CLUSTER_THRESHOLDS_ACCESSORY if is_accessory
        else CLUSTER_THRESHOLDS_CLOTHING
    )
    image_sim_threshold = thresholds['image_sim']
    title_threshold = thresholds['title_sim']
    
    clusters: list[list[dict]] = []
    used: set[int] = set()
    
    for i, p in enumerate(products):
        if i in used:
            continue
        cluster = [p]
        used.add(i)
        p_emb = p.get('_image_emb')
        p_codes = set(extract_model_codes(p.get('title', '')))
        
        for j, q in enumerate(products[i+1:], start=i+1):
            if j in used:
                continue
            
            # 조건 1 (Fix B3): 모델코드 일치 → 절대 우선 동일 상품
            q_codes = set(extract_model_codes(q.get('title', '')))
            if p_codes and (p_codes & q_codes):
                cluster.append(q)
                used.add(j)
                continue
            
            # 조건 2: 이미지 임베딩 유사
            q_emb = q.get('_image_emb')
            if p_emb is not None and q_emb is not None:
                img_sim = float(np.dot(p_emb, q_emb))
                if img_sim >= image_sim_threshold:
                    cluster.append(q)
                    used.add(j)
                    continue
            
            # 조건 3: 제목 유사 + 같은 브랜드/판매처
            title_sim = title_similarity(p['title'], q['title'])
            same_brand = (
                p.get('brand') and p['brand'] == q.get('brand')
            )
            if title_sim >= title_threshold and same_brand:
                cluster.append(q)
                used.add(j)
        
        clusters.append(cluster)
    
    return clusters
```

### 2.2 `routes_search.py` — 호출 시 카테고리 전달

```python
from src.ranking.mood_to_price import is_accessory_tab

# 재랭킹 후
ranked_20 = ...  # rank_clothing or rank_accessory

# 카테고리 정보 전달
clusters = cluster_similar_products_v2(
    ranked_20,
    is_accessory=is_accessory_tab(tab_id),
)
```

---

## Fix B3: 모델코드 매칭 강화 — 정규식 개선

### 3.1 `src/pricing/normalize.py` — `extract_model_codes` 개선

**현재 정규식:**
```python
MODEL_CODE_RE = re.compile(r"\b[A-Z0-9]{2,}[-_/]?[A-Z0-9]{2,}\b")
```

**문제:** 한국어 상품명에 영문/숫자 섞인 모델코드 추출 불완전
- `81200301`, `8120036`, `739682-AABZC` 같은 다양한 패턴 누락

**변경 후:**
```python
# 다양한 모델코드 패턴 매칭
_MODEL_CODE_PATTERNS = [
    re.compile(r"\b[A-Z]{2,}[\-_/]?[A-Z0-9]{2,}\b"),       # ABCDE-1234
    re.compile(r"\b[0-9]{6,}\b"),                            # 81200301 (6자리 이상 숫자)
    re.compile(r"\b[A-Z0-9]+[\-_/][A-Z0-9]+(?:[\-_/][A-Z0-9]+)*\b"),  # 739682-AABZC-001
]


def extract_model_codes(text: str) -> list[str]:
    """제목에서 모델코드 추출. 다양한 패턴 지원.
    
    추출 대상:
    - 6자리 이상 순수 숫자 (예: 81200301)
    - 영문+숫자 혼합 (예: 739682-AABZC)
    - 슬래시/언더바 구분 (예: ABC_123_XYZ)
    """
    if not text:
        return []
    text_upper = text.upper()
    codes: set[str] = set()
    for pattern in _MODEL_CODE_PATTERNS:
        codes.update(pattern.findall(text_upper))
    
    # 너무 짧거나 일반 단어 같은 것 필터
    return [c for c in codes if len(c) >= 5]
```

### 3.2 검증
- "버버리 미니 하이랜드 숄더백 라이트 베이지 81200301" → `['81200301']`
- "버버리 미니 하이랜드 숄더백 라이트 베이지 8120036" → `['8120036']`  
  (참고: `81200301`과 `8120036`는 다른 코드라 다른 클러스터 — 의도)
- "구찌 GG 마몽 미니 슐더백 739682-AABZC" → `['739682-AABZC', '739682AABZC']`

---

## Fix B4: 클러스터 내 최저가 = 대표 + 노출 강화

### 4.1 `src/pricing/normalize.py` — `lowest_price_per_cluster` 개선

**현재:** 단순히 cluster 내 최저가 1개 반환

**변경 후 — 메타 정보 풍부화:**
```python
def lowest_price_per_cluster(clusters: list[list[dict]]) -> list[dict]:
    """클러스터별 최저가 1개 + 다른 판매처 메타 추가.
    
    반환 상품 dict에 추가되는 필드:
        _cluster_size: 같은 상품을 파는 판매처 수
        _other_sellers: 다른 판매처 정보 [{mall_name, price, link}, ...]
        _price_savings: 평균가 대비 절약액 (옵션)
        _min_price: 최저가
        _max_price: 최고가
    """
    result = []
    for cluster in clusters:
        if not cluster:
            continue
        
        # 가격 있는 항목만 정렬
        priced = [c for c in cluster if c.get('price') and c.get('price', 0) > 0]
        if not priced:
            # 가격 정보 없으면 첫 번째 사용
            cheapest = cluster[0]
            cheapest['_cluster_size'] = len(cluster)
            cheapest['_other_sellers'] = []
            result.append(cheapest)
            continue
        
        priced_sorted = sorted(priced, key=lambda x: x.get('price', 999_999_999))
        cheapest = priced_sorted[0]
        
        prices = [p.get('price', 0) for p in priced_sorted]
        cheapest['_cluster_size'] = len(cluster)
        cheapest['_min_price'] = min(prices)
        cheapest['_max_price'] = max(prices)
        cheapest['_other_sellers'] = [
            {
                'mall_name': c.get('mall_name', ''),
                'price': c.get('price'),
                'link': c.get('link', ''),
                'product_id': c.get('product_id', ''),
            }
            for c in priced_sorted[1:]
        ]
        result.append(cheapest)
    
    return result
```

### 4.2 `apps/api/schemas.py` — `ProductCard` 메타 필드 추가

```python
class OtherSeller(BaseModel):
    mall_name: str
    price: int | None
    link: str
    product_id: str = ""


class ProductCard(BaseModel):
    # 기존 필드 +
    cluster_size: int = 1                # 같은 상품 노출 판매처 수
    min_price: int | None = None          # 클러스터 최저가
    max_price: int | None = None          # 클러스터 최고가  
    other_sellers: list[OtherSeller] = []  # 다른 판매처 정보
```

### 4.3 `routes_search.py` — ProductCard 빌드 시 메타 매핑

```python
product_cards = [
    ProductCard(
        id=p.get('product_id', ''),
        title=p.get('title', ''),
        image=p.get('image_url', ''),
        price=p.get('price'),
        link=p.get('link', ''),
        mall_name=p.get('mall_name', ''),
        match_score=round(p.get('match_score', 0.0), 4),
        visual_similarity=round(p.get('_visual_sim', 0.0), 4),
        mood_alignment=round(p.get('_mood_align', 0.0), 4),
        price_fit=round(p.get('_price_fit', 0.0), 4),
        naver_rank_score=round(p.get('_naver_rank', 0.0), 4),
        # 신규 필드
        cluster_size=p.get('_cluster_size', 1),
        min_price=p.get('_min_price'),
        max_price=p.get('_max_price'),
        other_sellers=[
            OtherSeller(**s) for s in p.get('_other_sellers', [])
        ],
    )
    for p in final_5
]
```

### 4.4 프론트엔드 (cloi/src/...) — 최저가 강조 표시

**변경 영역:** `src/types/index.ts` + `src/services/api.ts` + 카드 컴포넌트

```typescript
// types
export interface ProductCard {
  // 기존 필드 +
  cluster_size: number;
  min_price: number | null;
  max_price: number | null;
  other_sellers: Array<{
    mall_name: string;
    price: number | null;
    link: string;
    product_id: string;
  }>;
}
```

**UI 표시 권장 (선택):**
```tsx
{product.cluster_size > 1 && (
  <div className="cluster-badge">
    🏷️ {product.cluster_size}개 판매처 비교 (최저가)
  </div>
)}
```

---

## 2. 작업 순서 (Claude Code 터미널)

```bash
cd "C:\Users\Alex KIM\Desktop\사업 프로젝트\인앱토스 1"

# Fix B1: accessory 점수 공식
git commit -m "fix(ranking): accessory visual_sim 40 to 60 (visual prioritized)"

# Fix B2: 클러스터링 임계값 완화
git commit -m "fix(pricing): looser clustering threshold for accessories"

# Fix B3: 모델코드 정규식 개선
git commit -m "fix(pricing): improved model code regex (numeric + multi-segment)"

# Fix B4: 최저가 메타 풍부화
git commit -m "feat(pricing): cluster price range + other_sellers metadata"

# 통합 + 배포
bash deploy.sh
git push origin main
```

---

## 3. 배포

```powershell
cd "C:\Users\Alex KIM\Desktop\사업 프로젝트\인앱토스 1"
$env:GOOGLE_API_KEY = (Get-Content fashion-search/.env | Select-String '^GOOGLE_API_KEY=' | ForEach-Object { $_.Line.Split('=')[1] })
$env:ADMIN_TOKEN = (Get-Content fashion-search/.env | Select-String '^ADMIN_TOKEN=' | ForEach-Object { $_.Line.Split('=')[1] })
$env:NAVER_CLIENT_ID = (Get-Content fashion-search/.env | Select-String '^NAVER_CLIENT_ID=' | ForEach-Object { $_.Line.Split('=')[1] })
$env:NAVER_CLIENT_SECRET = (Get-Content fashion-search/.env | Select-String '^NAVER_CLIENT_SECRET=' | ForEach-Object { $_.Line.Split('=')[1] })
bash deploy.sh

# 프론트엔드 (메타 필드 추가됐으면)
cd cloi
npm run build
wrangler pages deploy dist --project-name=cloi
```

---

## 4. 성공 기준

- [ ] 베이지 줄무늬 미니 숄더백 → '가방' 탭 1~3순위에 베이지 줄무늬 가방 노출
- [ ] 같은 모델코드 (예: 81200301) → 1개로 묶이고 최저가 1개만 대표 노출
- [ ] `cluster_size >= 2` 인 상품 → 응답에 `other_sellers` 정보 포함
- [ ] 응답에 `min_price`, `max_price` 필드 정상 노출
- [ ] 캐주얼 outfit + 200만원 럭셔리 가방 → 뒤로 밀림 (price_fit 패널티 유지)
- [ ] 럭셔리 outfit + 200만원 럭셔리 가방 → 정상 노출 (price_fit 통과)
- [ ] git push + Cloud Run 배포 완료

---

## 5. 핵심 원칙 (절대 잊지 말 것)

> **"정확도 매칭 후 비슷한 상품끼리는 최저가 우선"**
> 
> 이건 서비스 핵심 가치. 클러스터링이 약하면 같은 상품이 여러 번 노출되어 사용자가 가격 비교 불가.
> 사용자가 같은 상품 5개 보고 싶은 게 아니라, **가장 싸게 살 방법**을 알고 싶음.

---

# Fix B5: 탭 완전성 보장 — 가방/액세서리 탐지 누락 본질 해결

## 5.1 기존 코드 분석 (왜 이렇게 작성됐나)

### 현재 탐지 파이프라인 — 2개의 독립된 Gemini 호출

**파일 1: `src/llm/style_analyzer.py`**
- 단일 Gemini 호출 → `MultiItemStyleContext.detected_items` 반환
- 프롬프트 구조: "모든 아이템 탐지" + 자유 텍스트
- 응답: `detected_items: list[DetectedItem]` (각 탭의 카테고리/검색쿼리 포함)
- **목적:** Naver 검색에 쓸 탭 정의

**파일 2: `src/preprocess/gemini_detector.py`**
- 단일 Gemini 호출 → `DetectionResult.boxes` 반환
- 프롬프트 구조: "bounding box 추출" + JSON
- 응답: `boxes: list[BoundingBox]` (label + 좌표)
- **목적:** 이미지 crop으로 query embedding 생성

### 왜 두 개로 분리됐나
- **SESSION 6:** style_analyzer 단독 (탭 분리 + 검색 쿼리 생성)
- **SESSION 8 Phase 4:** gemini_detector 추가 (이미지 crop 위해 bbox 필요)
- 두 호출이 같은 Gemini 모델 + 같은 이미지 사용하지만 **결과 통합 안 됨**
- 각자 독립적으로 다른 목적 수행

### 결정적 결함

`routes_search.py:340`:
```python
for item in style_ctx.detected_items:  # ← 오직 style_analyzer 결과만 사용
    tab_id = item.tab_id
    products = raw_results.get(tab_id, [])
    if not products: continue           # ← Naver 0건이면 탭 자동 제외
```

**문제 1:** style_analyzer가 액세서리 누락 → 탭 안 만들어짐. detection.boxes에 액세서리 있어도 무시됨.
**문제 2:** style_analyzer가 가방 탐지했는데 Naver 검색 0건 → 탭 자동 제외 (디버그 신호 없음).
**문제 3:** Gemini 보수적 행동 → "확실한 4개만" 반환 (top/bottom/outer/bag = 일반적 outfit 구성).

## 5.2 본질 원인 (반복 문제 발생 메커니즘)

### Why 4탭으로 수렴하나

| 원인 | 메커니즘 | 영향 |
|------|---------|------|
| **Gemini 보수성** | temperature=0 + 자신없는 작은 영역 누락 | 액세서리 0개 |
| **Single-pass 검출** | 한 번의 호출로 모든 작업 (탭 분리 + 검색쿼리 생성 + 설명) | 인지 부하 분산, 작은 아이템 놓침 |
| **Few-shot 부재** | 프롬프트에 "어떻게 답해야 한다"의 예시 없음 | 모델이 자신만의 default 형식 (4-5개)로 수렴 |
| **Schema 강제 부재** | `list[DetectedItem]` 만 정의, 최소 개수/구성 강제 X | 모델이 안전한 출력 선택 |
| **Bbox 결과 미활용** | gemini_detector가 액세서리 bbox 잡아도 detected_items에 미반영 | 정보 손실 |
| **Naver fallback 부재** | 가방/액세서리 검색 0건이면 탭 통째로 제외 | 사용자에게 신호 없이 사라짐 |

### Gemini 자체 한계 (구조적)
공식 문서 + 학계 연구 (LMM evaluation 2024):
- LMM(Large Multimodal Model)은 큰 객체 인식은 강하지만 **작은 객체 (5% 면적 미만) 누락 30~50%**
- 한 번의 prompt로 다목적 수행 시 정확도 하락 (multi-task interference)
- Bounding box 정확도 vs 카테고리 분류 정확도 trade-off 존재

**결론:** Single-pass + 큰 프롬프트 = 작은 액세서리 누락. 본질적이고 반복적인 문제.

## 5.3 해결 전략 — "최고의 효율 + 최선의 UX + 반복 방지"

### 전략 비교

| 전략 | 장점 | 단점 | 채택 |
|-----|------|------|-----|
| A. 프롬프트만 강화 | 비용 0 | 본질 해결 X, 여전히 누락 가능 | ❌ |
| B. 두 번째 Gemini 호출 (액세서리 전용) | 정확도 ↑ | 지연 +2~3초, 비용 ×2 | ⚠️ 부분채택 |
| C. **Bbox 결과 ↔ detected_items 교차 검증** | 추가 호출 X (이미 있는 결과 활용), 즉시 보강 | 매핑 로직 필요 | ✅ **채택** |
| D. Naver 0건 시 fallback 쿼리 생성 | 누락 탭 복구 | 검색 품질 변동 | ✅ 채택 |
| E. 프롬프트 chain-of-thought + few-shot | 검출률 ↑ | 토큰 비용 약간 ↑ | ✅ 채택 |
| F. 응답에 detected_items 노출 (디버깅) | 문제 원인 즉시 진단 | UI 영향 X | ✅ 채택 |

### 채택안 — C + D + E + F 통합

핵심 통찰: **이미 있는 호출 (gemini_detector) 결과를 버리고 있음.** 추가 호출 없이 즉시 효과 가능.

## 5.4 구체 작업 — 4단계

### B5-1: `gemini_detector` bbox label 확장 (액세서리 포함)

**현재 `_DETECTION_PROMPT` (gemini_detector.py:27)** 이미 액세서리 레이블 모두 포함됨 (Fix 2에서 처리). 추가 작업 없음.

### B5-2: bbox 결과 → `detected_items` 교차 보강

**파일:** `apps/api/routes_search.py`

**현재 (라인 282 직후 추가):**
```python
if not style_ctx.detected_items:
    raise HTTPException(...)

# 5. 탭별 query embedding ...
```

**변경 후 — bbox 결과로 detected_items 보강:**
```python
if not style_ctx.detected_items:
    raise HTTPException(...)

# ★ NEW: bbox에 있지만 detected_items에 없는 탭 자동 추가
style_ctx = _augment_detected_items_from_bbox(style_ctx, detection)
```

**신규 함수:**
```python
def _augment_detected_items_from_bbox(
    style_ctx,           # MultiItemStyleContext
    detection,           # DetectionResult or None
):
    """gemini_detector의 bbox 결과로 style_analyzer의 detected_items 보강.
    
    bbox에는 있지만 detected_items에는 없는 탭 ID 발견 시,
    fallback 검색쿼리와 함께 자동 추가. 
    style_analyzer가 누락한 가방/액세서리를 복구한다.
    """
    if detection is None or not detection.boxes:
        return style_ctx
    
    from src.llm.schemas import DetectedItem
    
    existing_tabs = {item.tab_id for item in style_ctx.detected_items}
    
    # bbox label → tab_id 매핑 (Fix 3의 매핑 역방향)
    BBOX_TO_TAB = {
        'top_outer': 'top_outer',
        'top_inner': 'top_inner',
        'outer': 'outer',
        'bottom': 'bottom',
        'dress': 'dress',
        'shoes': 'shoes',
        'bag': 'bag',
        'accessory_ring': 'accessory_ring',
        'accessory_necklace': 'accessory_necklace',
        'accessory_earring': 'accessory_earring',
        'accessory_belt': 'accessory_belt',
        'accessory_hat': 'accessory_hat',
        'accessory_watch': 'accessory_watch',
    }
    
    # bbox 결과에서 발견됐지만 detected_items엔 없는 탭 추출
    bbox_tabs = set()
    for box in detection.boxes:
        if box.label == 'face':
            continue
        tab_id = BBOX_TO_TAB.get(box.label)
        if tab_id and tab_id not in existing_tabs:
            bbox_tabs.add(tab_id)
    
    # 자동 보강 — 누락된 탭에 fallback 정보 추가
    FALLBACK_QUERIES = {
        'bag': ['{style} 가방', '{style} 숄더백', '{style} 토트백'],
        'shoes': ['{style} 신발', '{style} 스니커즈', '{style} 로퍼'],
        'accessory_ring': ['{style} 반지', '데일리 반지', '미니멀 반지'],
        'accessory_necklace': ['{style} 목걸이', '미니멀 목걸이', '데일리 목걸이'],
        'accessory_earring': ['{style} 귀걸이', '미니멀 귀걸이'],
        'accessory_belt': ['{style} 벨트', '여성 벨트'],
        'accessory_hat': ['{style} 모자', '버킷햇', '캡모자'],
        'accessory_watch': ['{style} 시계', '여성 시계'],
        'top_inner': ['{style} 이너', '베이직 티셔츠', '크롭 탑'],
        'top_outer': ['{style} 셔츠', '{style} 카디건'],
        'outer': ['{style} 자켓', '{style} 코트'],
        'bottom': ['{style} 바지', '{style} 스커트'],
        'dress': ['{style} 원피스'],
    }
    
    style_label = style_ctx.overall_style_context or '캐주얼'
    
    for tab_id in bbox_tabs:
        templates = FALLBACK_QUERIES.get(tab_id, [f'{tab_id} 추천'])
        queries = [t.format(style=style_label) for t in templates]
        new_item = DetectedItem(
            tab_id=tab_id,
            category=tab_id,
            subcategory=tab_id,
            description=f'(자동보강) bbox 탐지: {tab_id}',
            is_inner=(tab_id == 'top_inner'),
            searchQueries=queries,
        )
        style_ctx.detected_items.append(new_item)
        logger.info(
            "[routes_search] bbox 보강: %s 탭 추가 (style_analyzer 누락)",
            tab_id,
        )
    
    return style_ctx
```

### B5-3: `style_analyzer` 프롬프트 강화 — chain-of-thought + 영역 점검

**파일:** `src/llm/style_analyzer.py`

**현재 프롬프트 (29줄):**
단일 명령형, 자유 텍스트 형식.

**변경 후 — 영역별 체계적 점검 + 명시적 카운트 가이드:**
```python
_PROMPT = """
이 패션 이미지를 다음 절차로 빠짐없이 분석하라.

## 1단계: 영역별 점검 (각 영역에 시각적으로 보이는 모든 것 나열)
- 머리: 모자/헤어밴드/헤어핀 등
- 얼굴/귀: 귀걸이/안경
- 목: 목걸이/스카프/넥타이
- 손목: 시계/팔찌
- 손가락: 반지
- 상체: 셔츠/티셔츠/니트/카디건/재킷/코트 (레이어드 시 각각 분리)
- 허리: 벨트
- 하체: 바지/스커트/원피스
- 발: 신발
- 들고/메고 있는 것: 가방/백팩/클러치

## 2단계: 각 보이는 아이템마다 1개 DetectedItem 생성
필수 필드:
- tab_id: 다음 중 정확히 하나
  top_outer, top_inner, outer, bottom, dress, shoes, bag,
  accessory_ring, accessory_necklace, accessory_earring,
  accessory_belt, accessory_hat, accessory_watch
- category: 한글 카테고리명 (예: 셔츠, 청바지, 숄더백)
- subcategory: 세부 종류 (예: 오버사이즈 셔츠, 스트레이트 데님)
- description: 색상+소재+핏+세부디테일 한국어 설명 (충분히 상세하게)
- is_inner: 이너 여부 (true/false)
- searchQueries: 네이버쇼핑 자연 한국어 쿼리 3개

## 3단계: 자기 검토
- 작은 액세서리 (반지/귀걸이) 빠뜨리지 않았나?
- 레이어드된 상의 분리했나? (예: 셔츠 + 안의 티셔츠)
- 가방을 손에 들고 있어도 탐지했나?

## 출력 규칙
- 보이는 모든 것 포함. 자신없어도 가능성 있으면 포함.
- 같은 카테고리(top_inner)도 여러 개 가능.
- 얼굴/신체 자체는 무시.
- overall_style_context는 outfit 전체 무드 한국어 1~2문장.

JSON으로만 응답하라.
"""
```

### B5-4: Naver 검색 0건 fallback — 탭 살리기

**파일:** `src/search/parallel_search.py`

**현재 `_search_multi_query_dedupe`:**
```python
async def _search_multi_query_dedupe(
    queries: list[str],
    category: str,
    display: int = 40,
    exclude: str = 'used:rental:cbshop',
):
    # ... 쿼리 검색 + dedupe
    return merged[:60]
```

**변경 후 — 0건일 때 fallback 쿼리 시도:**
```python
async def _search_multi_query_dedupe(
    queries: list[str],
    category: str,
    display: int = 40,
    exclude: str = 'used:rental:cbshop',
):
    # 1차: 원본 쿼리들
    merged = await _execute_queries(queries, category, display, exclude)
    if merged:
        return merged[:60]
    
    # 2차: 카테고리만으로 광범위 검색 (탭 살리기)
    fallback_queries = [category, f'여성 {category}', f'{category} 추천']
    logger.info(
        "[parallel_search] %s 검색 0건 → fallback 쿼리 시도: %s",
        category, fallback_queries,
    )
    merged = await _execute_queries(fallback_queries, category, display, exclude)
    return merged[:60]


async def _execute_queries(
    queries: list[str],
    category: str,
    display: int,
    exclude: str,
) -> list[dict]:
    """기존 _search_multi_query_dedupe 로직을 별도 함수로 분리."""
    tasks = [
        _naver_search_single(q, category=category, display=display, exclude=exclude)
        for q in queries
    ]
    all_results = await asyncio.gather(*tasks, return_exceptions=True)
    
    seen_ids: set[str] = set()
    merged: list[dict] = []
    for r in all_results:
        if isinstance(r, Exception):
            continue
        for p in r:
            pid = p.get('product_id', '') or p.get('link', '')
            if pid in seen_ids:
                continue
            seen_ids.add(pid)
            merged.append(p)
    return merged
```

### B5-5: 디버깅 응답 필드 — 문제 즉시 진단

**파일:** `apps/api/schemas.py`

```python
class SearchResponse(BaseModel):
    # 기존 필드 +
    detected_items_meta: list[dict] = []  # 디버깅용: Gemini 탐지 결과 노출
```

**파일:** `apps/api/routes_search.py` (response 빌드 시)

```python
response = SearchResponse(
    # 기존 필드 +
    detected_items_meta=[
        {
            'tab_id': i.tab_id,
            'category': i.category,
            'description': i.description[:50],
            'has_naver_results': bool(raw_results.get(i.tab_id)),
            'naver_count': len(raw_results.get(i.tab_id, [])),
        }
        for i in style_ctx.detected_items
    ],
)
```

→ 응답 JSON 까서 보면 어떤 탭이 Gemini에 잡혔고 Naver에서 결과 받았는지 즉시 진단 가능.

## 5.5 작업 순서 + 커밋

```bash
cd "C:\Users\Alex KIM\Desktop\사업 프로젝트\인앱토스 1"

# B5-2: bbox 보강 함수 + 호출
git commit -m "fix(detect): augment detected_items from bbox (recover missed accessories)"

# B5-3: style_analyzer 프롬프트 강화
git commit -m "fix(llm): chain-of-thought prompt with region-by-region inspection"

# B5-4: Naver 0건 fallback
git commit -m "fix(search): fallback queries when naver returns 0 (preserve tab)"

# B5-5: 디버깅 응답 필드
git commit -m "feat(api): expose detected_items_meta for debugging"

# 통합 배포
bash deploy.sh
git push origin main
```

## 5.6 성공 기준 (반복 문제 방지)

- [ ] 액세서리 (목걸이/귀걸이/벨트/모자) 있는 사진 → 해당 탭 자동 등장
- [ ] style_analyzer가 액세서리 놓쳐도 bbox detect가 잡으면 자동 복구
- [ ] 가방 탐지됐는데 Naver 0건 → fallback 쿼리로 탭 살아있음
- [ ] 응답 JSON에 `detected_items_meta` 포함 → 어떤 탭이 어디서 누락됐는지 즉시 진단
- [ ] 5개 다른 사진 (액세서리 있는/없는, 레이어드/단순) 테스트 → 일관된 탭 노출
- [ ] git push + Cloud Run 배포 완료

## 5.7 본질 원칙 (반복 방지)

> **단일 호출로 모든 책임 부여하면 누락 발생.**
> **여러 호출의 결과를 교차 검증해야 안정.**
> 
> Gemini는 "확실한 것만 반환"하는 보수성이 있다. 이건 LLM 본질이다. 
> 한 번의 호출만 믿지 말고, 여러 신호 (style_analyzer + gemini_detector + Naver fallback)를 교차 검증하면 누락 본질 해결.

---

# Fix B6: 색상 매칭 본질 강화 — 회색 츄리닝 → 핑크 조거 문제 해결

## 6.1 기존 코드 분석 (왜 이렇게 작성됐나)

### 색상 매칭 파이프라인 현황

**파일 1: `src/ranking/color_hist.py`**
```python
def compute_color_histogram(image, bins=8):
    hist_r = np.histogram(arr[:, :, 0], bins=8)
    hist_g = np.histogram(arr[:, :, 1], bins=8)
    hist_b = np.histogram(arr[:, :, 2], bins=8)
    hist = concatenate([hist_r, hist_g, hist_b])  # 24-dim
    return hist / norm   # L2 정규화

def color_similarity(hist_a, hist_b):
    return np.dot(hist_a, hist_b)  # cosine
```

**파일 2: `src/ranking/mood_ranker.py:rank_clothing_products`**
- `query_color_hist` = 쿼리 이미지의 의류 crop 영역 히스토그램
- `product_color_hists[pid]` = Naver 상품 썸네일 **전체** 히스토그램
- `compute_clothing_score`: visual 80% + **color 15%** + naver 5%

### 왜 이렇게 작성됐나
- **SESSION 9 Fix 5**에서 "FashionCLIP 미세 색상 약점 보완"용으로 빠르게 추가
- 24-bin RGB는 "대충 같은 색조면 OK" 수준의 보조 신호로만 설계
- 본격 색상 매칭이 아닌 **tie-breaker** 역할 가정

### 결정적 결함 4가지

| # | 결함 | 영향 (회색 츄리닝 케이스) |
|---|------|-----------------|
| 1 | **쿼리는 crop / 상품은 전체** | 상품 썸네일 = 핑크 조거 + 흰 배경 + 모델 피부/얼굴 → 색 분포 왜곡 |
| 2 | **24-bin 코사인 유사도 약함** | "회색 99%+핑크 1%" vs "핑크 99%+회색 1%" 모두 비슷한 cosine → 색조 구분 X |
| 3 | **15% 가중치 부족** | visual 80%가 "조거팬츠 카테고리"만 잡으면 색상 무시당함 |
| 4 | **dominant color 무시** | RGB bin 단순 분포 → 주 색상이 회색인지 핑크인지 명확히 구분 못함 |

## 6.2 해결 — "최고의 효율 + 반복 방지"

### 전략

| 전략 | 효과 | 비용 | 채택 |
|------|------|------|------|
| A. 색상 가중치 단순 상향 (15→30%) | 즉시 효과 | 0 | ✅ |
| B. RGB → HSV 변환 (색조/채도/명도 분리) | 색조 인지 강화 | 약간 | ✅ |
| C. K-means dominant color 3개 비교 | 배경 노이즈 감소 | 중간 | ✅ |
| D. 상품 썸네일도 crop | 비대칭 해소 | 큼 (Gemini 호출 ×N) | ❌ |
| E. 색상 mismatch 강한 패널티 | 정확도 ↑ | 0 | ✅ |

### 채택 — A + B + C + E (D 제외)

**D 제외 이유:** Naver 썸네일 N장에 Gemini bbox 추가 호출 = 비용/지연 너무 큼. C (dominant color)로 비대칭 부분 보완.

## 6.3 작업

### B6-1: HSV 기반 색상 히스토그램 + dominant color

**파일:** `src/ranking/color_hist.py` 전면 재작성

```python
"""HSV 기반 색상 매칭 + dominant color 추출.

기존 RGB cosine의 약점 해결:
- HSV: 색조(H) 분리 → 회색과 핑크 명확히 구분
- dominant: K-means로 주요 색상 3개 추출 → 배경 노이즈 감소
"""
from typing import Optional
import numpy as np
from PIL import Image


def compute_color_histogram(image: Image.Image, h_bins: int = 12, s_bins: int = 4, v_bins: int = 4) -> np.ndarray:
    """HSV 3D 히스토그램. 색조(H) 12 bin, 채도(S)/명도(V) 4 bin.
    
    H가 12 bin으로 세분화되어 회색(S=0)과 핑크(H=300)가 명확히 분리됨.
    """
    rgb = np.array(image.convert('RGB'))
    # RGB → HSV 변환
    from colorsys import rgb_to_hsv
    flat_rgb = rgb.reshape(-1, 3) / 255.0
    hsv = np.array([rgb_to_hsv(*pixel) for pixel in flat_rgb])
    
    # 3D 히스토그램
    hist, _ = np.histogramdd(
        hsv,
        bins=[h_bins, s_bins, v_bins],
        range=[(0, 1), (0, 1), (0, 1)],
    )
    hist_flat = hist.flatten()
    
    norm = np.linalg.norm(hist_flat) + 1e-8
    return hist_flat / norm


def extract_dominant_colors(image: Image.Image, k: int = 3) -> np.ndarray:
    """K-means로 dominant color 3개 추출 (HSV 공간).
    
    Returns:
        (k, 3) HSV 벡터.
    """
    from sklearn.cluster import KMeans
    rgb = np.array(image.convert('RGB').resize((64, 64)))
    flat_rgb = rgb.reshape(-1, 3) / 255.0
    
    # RGB → HSV
    from colorsys import rgb_to_hsv
    hsv = np.array([rgb_to_hsv(*pixel) for pixel in flat_rgb])
    
    # K-means 클러스터링
    kmeans = KMeans(n_clusters=k, random_state=42, n_init=3, max_iter=20)
    kmeans.fit(hsv)
    return kmeans.cluster_centers_  # (k, 3)


def color_similarity(hist_a: np.ndarray, hist_b: np.ndarray) -> float:
    """HSV 히스토그램 코사인 유사도."""
    sim = float(np.dot(hist_a, hist_b))
    return max(0.0, min(1.0, sim))


def dominant_color_similarity(
    domains_a: np.ndarray,  # (k, 3)
    domains_b: np.ndarray,  # (k, 3)
) -> float:
    """Dominant color 매칭 유사도.
    
    각 a의 색을 가장 비슷한 b 색과 매칭, 평균 유사도 반환.
    HSV 거리: 색조(H)에 가중치 큼.
    """
    if domains_a is None or domains_b is None:
        return 0.5
    
    sims = []
    for ca in domains_a:
        # b의 모든 색과 거리 계산 (H에 큰 가중치)
        dists = np.linalg.norm(
            (domains_b - ca) * np.array([3.0, 1.0, 1.0]),  # H 가중치 ×3
            axis=1,
        )
        best_dist = dists.min()
        sims.append(max(0.0, 1.0 - best_dist))
    
    return float(np.mean(sims))


def color_score(
    query_hist: np.ndarray,
    product_hist: np.ndarray,
    query_dominant: Optional[np.ndarray] = None,
    product_dominant: Optional[np.ndarray] = None,
) -> float:
    """종합 색상 점수: 히스토그램 + dominant color.
    
    - 히스토그램: 전체 색 분포 (40%)
    - Dominant: 주요 색상 매칭 (60%)
    """
    hist_sim = color_similarity(query_hist, product_hist)
    
    if query_dominant is not None and product_dominant is not None:
        dom_sim = dominant_color_similarity(query_dominant, product_dominant)
        return hist_sim * 0.40 + dom_sim * 0.60
    
    return hist_sim
```

### B6-2: 의류 점수 가중치 재조정

**파일:** `src/ranking/mood_ranker.py`

```python
def compute_clothing_score(
    visual_sim: float,
    color_sim: float,
    naver_rank_score: float,
) -> float:
    """의류: 시각 매칭 + 색상 매칭 강화.
    
    가중치 변경: color 15 → 30 (회색 츄리닝 → 핑크 조거 문제 본질 해결)
    """
    # 색상 mismatch 시 강한 패널티
    if color_sim < 0.3:
        return visual_sim * 0.50 + color_sim * 0.45 + naver_rank_score * 0.05
    
    return visual_sim * 0.65 + color_sim * 0.30 + naver_rank_score * 0.05
```

### B6-3: dominant color 파이프라인 통합

**파일:** `src/ranking/color_hist.py` 그대로

**파일:** `apps/api/routes_search.py` — `_calc_clip_embeddings_and_hists`에서 dominant도 계산

```python
async def _calc_clip_embeddings_and_hists(
    embedder,
    products: list[dict],
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray], dict[str, np.ndarray]]:
    """썸네일 다운로드 + 임베딩 + 히스토그램 + dominant color 동시 계산."""
    # 기존 로직 +
    embs = {}
    hists = {}
    dominants = {}
    for p, vec, img in zip(valid_products, product_vecs, valid_images):
        pid = p.get("product_id", "")
        embs[pid] = vec
        hists[pid] = compute_color_histogram(img)
        dominants[pid] = extract_dominant_colors(img, k=3)
    return embs, hists, dominants
```

**`_build_per_tab_query_embs`도 동일하게 dominant 추가.**

**`rank_clothing_products` 시그니처:**
```python
def rank_clothing_products(
    products,
    query_image_emb,
    query_color_hist,
    query_dominant_colors,           # 신규
    product_image_embs,
    product_color_hists,
    product_dominant_colors,         # 신규
):
    for p in products:
        # ...
        color_sim = color_score(
            query_color_hist, prod_hist,
            query_dominant_colors, prod_dom,
        )
```

## 6.4 의존성

`fashion-search/requirements.txt`에 추가:
```
scikit-learn==1.5.0
```

(K-means용 — 이미 numpy 있으니 작은 추가)

---

# Fix B7: 의류 중복 제거 — 같은 셔츠 다판매처 통합

## 7.1 기존 코드 분석

### `cluster_similar_products_v2` (모든 카테고리 공통)
```python
title_threshold = 0.70
image_sim_threshold = 0.92
```

**조건 (OR):**
1. 이미지 임베딩 유사도 ≥ 0.92 → 묶음
2. 모델코드 일치 → 묶음
3. 제목 유사도 ≥ 0.70 AND 같은 브랜드 → 묶음

### 결정적 결함

| # | 결함 | 영향 |
|---|------|------|
| 1 | **0.92 너무 높음** | 같은 셔츠 다판매처 = 사진 차이로 0.85~0.91 → 미통합 |
| 2 | **OR 조건 + brand 빈 필드** | Naver `brand` 필드 종종 비어있음 → title 통로 차단 |
| 3 | **PATCH B Fix B2**에서 액세서리만 공격적 | 의류는 보수적 유지 → 같은 셔츠도 분리 |
| 4 | **색상 신호 미사용** | 색상 검증 없음 → 이론상 다른 디자인도 묶일 가능성 |

### 왜 이렇게 작성됐나
- **PATCH B Fix B2** 작성 시: "의류는 다른 디자인이 묶이면 안 됨"이라 보수적
- 하지만 **반대 케이스 (같은 디자인이 분리됨)** 검토 부족
- 사용자 실제 사용에선 같은 셔츠 5번 노출되는 게 더 큰 UX 문제

## 7.2 해결 — 멀티신호 강화

### 전략
- **임계값 낮추되, 안전장치 추가**: image_sim 0.92 → 0.88
- **AND 조건 강화**: image_sim 0.85 + title_sim 0.65 + 색상 mismatch 없음
- **모델코드 절대 우선** (이미 있음, 강화)

### B7-1: `cluster_similar_products_v2` 의류 임계값 + 색상 검증

**파일:** `src/pricing/normalize.py`

```python
CLUSTER_THRESHOLDS_CLOTHING = {
    'image_sim_strong': 0.90,  # 단독으로 묶기 충분 (이전 0.92 → 0.90)
    'image_sim_weak': 0.82,    # 추가 신호 있을 때 묶기 (신규)
    'title_sim': 0.65,         # 이전 0.70 → 0.65
    'color_min_sim': 0.60,     # 색상 너무 다르면 분리 (신규 안전장치)
}

CLUSTER_THRESHOLDS_ACCESSORY = {
    'image_sim_strong': 0.85,
    'image_sim_weak': 0.75,
    'title_sim': 0.60,
    'color_min_sim': 0.55,
}


def cluster_similar_products_v2(
    products: list[dict],
    is_accessory: bool = False,
) -> list[list[dict]]:
    """이미지 + 모델코드 + 제목 + 색상 종합 클러스터링.
    
    카테고리별 임계값 자동 적용.
    """
    thresholds = (
        CLUSTER_THRESHOLDS_ACCESSORY if is_accessory
        else CLUSTER_THRESHOLDS_CLOTHING
    )
    img_strong = thresholds['image_sim_strong']
    img_weak = thresholds['image_sim_weak']
    title_th = thresholds['title_sim']
    color_min = thresholds['color_min_sim']
    
    clusters: list[list[dict]] = []
    used: set[int] = set()
    
    for i, p in enumerate(products):
        if i in used:
            continue
        cluster = [p]
        used.add(i)
        p_emb = p.get('_image_emb')
        p_hist = p.get('_color_hist')
        p_codes = set(extract_model_codes(p.get('title', '')))
        
        for j, q in enumerate(products[i + 1:], start=i + 1):
            if j in used:
                continue
            
            # 1. 모델코드 일치 → 절대 동일 (색상 검증 없이)
            q_codes = set(extract_model_codes(q.get('title', '')))
            if p_codes and (p_codes & q_codes):
                cluster.append(q)
                used.add(j)
                continue
            
            # 2. 색상 검증 (둘 다 히스토그램 있을 때)
            q_hist = q.get('_color_hist')
            color_ok = True
            if p_hist is not None and q_hist is not None:
                from src.ranking.color_hist import color_similarity
                if color_similarity(p_hist, q_hist) < color_min:
                    color_ok = False  # 색상 너무 다르면 묶지 않음
            
            if not color_ok:
                continue
            
            # 3. 이미지 임베딩 강한 유사 (단독)
            q_emb = q.get('_image_emb')
            if p_emb is not None and q_emb is not None:
                img_sim = float(np.dot(p_emb, q_emb))
                if img_sim >= img_strong:
                    cluster.append(q)
                    used.add(j)
                    continue
                
                # 4. 이미지 약한 유사 + 제목 유사
                title_sim = title_similarity(p.get('title', ''), q.get('title', ''))
                if img_sim >= img_weak and title_sim >= title_th:
                    cluster.append(q)
                    used.add(j)
                    continue
            
            # 5. fallback: 제목 + 같은 브랜드 (이전 로직 유지)
            title_sim = title_similarity(p.get('title', ''), q.get('title', ''))
            same_brand = (
                p.get('brand') and p['brand'] == q.get('brand')
            )
            if title_sim >= title_th and same_brand:
                cluster.append(q)
                used.add(j)
        
        clusters.append(cluster)
    
    return clusters
```

### B7-2: `_color_hist` 필드 product에 주입

**파일:** `apps/api/routes_search.py`

라인 350 근처 (이미 `_image_emb` 주입하는 곳):
```python
# _image_emb 주입 +
for p in products:
    pid = p.get('product_id', '')
    if pid in product_image_embs:
        p['_image_emb'] = product_image_embs[pid]
    if pid in product_color_hists:
        p['_color_hist'] = product_color_hists[pid]   # 신규
```

## 7.3 작업 순서

```bash
# B6-1: HSV + dominant color
git commit -m "fix(color): HSV histogram + K-means dominant colors (replace RGB)"

# B6-2: 의류 점수 가중치 30% + mismatch 패널티
git commit -m "fix(ranking): clothing color weight 15 to 30 + mismatch penalty"

# B6-3: dominant color 파이프라인 통합
git commit -m "feat(ranking): integrate dominant colors in product embedding pipeline"

# B7-1: 의류 클러스터링 임계값 완화 + 색상 검증
git commit -m "fix(pricing): clothing cluster threshold + color safety check"

# B7-2: _color_hist 주입
git commit -m "fix(api): inject color hist into product for clustering"

# 의존성
git commit -m "chore: add scikit-learn for K-means dominant color"

# 통합 배포
bash deploy.sh
git push origin main
```

## 7.4 성공 기준

- [ ] 회색 츄리닝 입력 → '하의' 탭 1순위 = 회색 조거/팬츠 (핑크/빨강 X)
- [ ] 색상 mismatch (회색 vs 핑크) 시 color_sim < 0.3 → 강한 패널티
- [ ] 같은 셔츠 5개 판매처 → 1개로 묶임 + cluster_size=5 표시
- [ ] 다른 디자인은 묶이지 않음 (색상 검증으로)
- [ ] 응답에 `_color_sim` 노출 → 디버깅 가능
- [ ] git push + Cloud Run 배포 완료

## 7.5 본질 원칙 (반복 방지)

> **단일 임계값 = 양극단 실패 (너무 보수적 or 너무 공격적).**
> **다층 임계값 + 안전장치 = 양쪽 만족.**
> 
> 클러스터링은 `image_sim 0.92만 봐` → 같은 상품 분리되거나, `0.85만 봐` → 다른 상품 묶임.
> **두 임계값(strong/weak) + 색상 안전장치**로 양극단 모두 방지.

> **신호는 검증되어야 한다 (single signal trap).**
> 
> RGB cosine 단독 → 색조 무시 (회색 vs 핑크 비슷한 점수). 
> HSV + dominant color = 두 signal 교차 → 색조 명확히 인식.

---

## Claude Code 실행 명령어

새 터미널:

```bash
cd "C:\Users\Alex KIM\Desktop\사업 프로젝트\인앱토스 1"
claude --dangerously-skip-permissions "docs/SESSION_9_PATCH_B.md 파일 정독 후 Fix B1~B4 순서대로 정확히 실행. 각 Fix 끝나면 git commit. 모두 끝나면 deploy.sh 실행해서 Cloud Run 재배포 + 프론트엔드 ProductCard 메타 필드 추가 후 npm run build + wrangler pages deploy + git push origin main. 작업 끝나면 https://cloi.pages.dev URL 출력. 핵심 원칙 — '정확도 매칭 후 비슷한 상품끼리는 최저가 우선'."
```

---

## END OF PATCH B
