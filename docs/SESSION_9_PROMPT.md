# SESSION 9: 매칭 정확도 본질 개선 + 액세서리 + 중복 제거 + 4분면 소팅

> **최종 목표:** "최고의 효율, 최고의 고객 경험"
> 
> **유저 핵심 요구:**
> 1. 매칭 정확도 최대화 (의류는 시각 매칭이 절대 우선)
> 2. 액세서리 검색 누락 문제 해결
> 3. 정확도+가격 4분면 소팅 (정확+싸 → 정확+비싸 → 부정확+싸 → 부정확+비싸)
> 4. 같은 상품 다른 판매처 중복 제거
> 5. 의류는 분위기 무관, 잡화(가방/액세서리)만 분위기+가격대 반영

---

## 0. 컨텍스트 (반드시 먼저 읽을 것)

### 현재 시스템 (SESSION 8 + PATCH A까지 완료)
- 인프라: CF Pages → CF Worker → Cloud Run (FastAPI 4Gi/2cpu)
- 임베더: FashionCLIP (`patrickjohncyh/fashion-clip`, 512-dim)
- LLM: Gemini 2.5 Flash (이미지 분석 + bbox detect)
- 검색: 네이버 쇼핑 API (multi-query + dedupe)
- 랭킹 (현재): `visual_sim*0.70 + mood_align*0.20 + naver_rank*0.10`
- SKU 클러스터링: rapidfuzz title 유사도 0.75+

### 발견된 문제 (구조적/본질적 원인 분석)

#### 🔴 본질 원인 1: 단일 평균 query embedding
**위치:** `routes_search.py:_build_query_emb_from_detection`
```python
query_emb = np.mean(crop_embs, axis=0)  # ← 모든 의류 crop의 평균
```
**영향:** 모든 탭이 같은 평균 벡터로 검색. 흰 크롭탑 detail이 핑크 셔츠+청바지에 희석됨.
**증거:** 사용자가 흰 라운드넥 크롭탑(이너) 입혔는데, '상의' 탭에 다른 흰 상의 노출.

#### 🔴 본질 원인 2: Gemini detect 프롬프트 한계
**위치:** `gemini_detector.py:_DETECTION_PROMPT`
```
"각 레이블당 1개만"
"top, outer, bottom, dress (의류), shoes, bag (잡화)"
```
**문제:**
- 같은 'top' 카테고리에 핑크 셔츠+흰 크롭탑 둘 다 있어도 **1개만 반환**
- 액세서리(반지/목걸이/귀걸이/벨트/모자/시계) **레이블 자체 없음** → detect 못함
- 레이어드 코디(이너+아우터) 인식 불가

#### 🔴 본질 원인 3: detect 레이블 ↔ 탭 ID 매핑 부재
**위치:** `routes_search.py` 전체
**문제:**
- Gemini detect: `top, outer, bottom, dress, shoes, bag` (6종)
- style_analyzer 탭: `top_outer, top_inner, outer, bottom, dress, shoes, bag, accessory_*` (13종)
- **`top_inner`(이너), `accessory_*`(액세서리)에 대응되는 detect 레이블 없음**

#### 🔴 본질 원인 4: 분위기/가격 신호 잘못 적용
- 모든 탭에 mood_align 20% 가중치 → 의류 매칭 정확도 희석
- price_fit 완전 폐기 → 캐주얼 outfit에 200만원 럭셔리 가방 추천됨
- **올바른 설계:** 의류는 시각만, 잡화는 시각+무드+가격대

#### 🔴 본질 원인 5: SKU 클러스터링 약함
**위치:** `pricing/normalize.py:cluster_similar_products`
**문제:**
- 제목 유사도 0.75만 봄 (rapidfuzz token_set)
- **같은 상품인데 판매처마다 제목이 달라서 다른 클러스터로 분리**
- 결과: 같은 핑크 셔츠가 5개 판매처에서 5번 노출

#### 🔴 본질 원인 6: 소팅 우선순위 미반영
**위치:** `routes_search.py` 재랭킹 로직
**문제:**
- 현재: `match_score` 단일 점수로 정렬
- 사용자 요구: 정확도+가격 4분면 우선순위

#### 🟡 부가 원인 7: FashionCLIP 일반 모델 한계
- 색 농도(찐핑크 vs 연핑크), 줄무늬 두께, 핏 차이 등 **미세 디테일 약함**
- 한국 패션 도메인 fine-tune 안 됨
- → 색상 히스토그램 보조 신호로 부분 보완 (장기적으로는 LoRA fine-tune)

---

## 1. 작업 범위 (Fix 1~7)

### Fix 1: 탭별 query embedding 분리 (P0)
### Fix 2: Gemini detect 프롬프트 개선 — 다중 객체 + 액세서리 + 레이어드 (P0)
### Fix 3: detect 레이블 → 탭 ID 스마트 매핑 (P0)
### Fix 4: 카테고리별 점수 공식 분리 (P0)
### Fix 5: 색상 히스토그램 보조 신호 (P1)
### Fix 6: 정확도+가격 4분면 소팅 (P1)
### Fix 7: SKU 클러스터링 강화 — 이미지 임베딩 기반 (P1)

---

## Fix 1: 탭별 query embedding 분리

### 1.1 `apps/api/routes_search.py` — `_build_query_emb_from_detection` 폐기

**삭제:**
```python
async def _build_query_emb_from_detection(...):
    query_emb = np.mean(crop_embs, axis=0)  # ← 이거 폐기
    ...
```

**신규 함수 추가:**
```python
async def _build_per_tab_query_embs(
    embedder,
    pil_image: Image.Image,
    detection,
    detected_items,
) -> dict[str, np.ndarray]:
    """탭별 query embedding 생성.
    
    각 detected_item.tab_id 마다 해당 의류 crop의 임베딩 사용.
    detect 실패 시 fallback: 전체 이미지 embedding을 모든 탭에 동일 적용.
    """
    fallback_emb = await asyncio.to_thread(embedder.embed_single, pil_image)
    
    if detection is None or not detection.boxes:
        return {item.tab_id: fallback_emb for item in detected_items}
    
    from src.preprocess.gemini_detector import (
        blur_face_regions,
        crop_garment_regions,
    )
    masked_image = blur_face_regions(pil_image, detection.boxes)
    garment_crops = crop_garment_regions(masked_image, detection.boxes)
    
    if not garment_crops:
        return {item.tab_id: fallback_emb for item in detected_items}
    
    # detect label → 임베딩 사전 계산
    label_to_emb: dict[str, np.ndarray] = {}
    crop_labels = list(garment_crops.keys())
    crop_images = list(garment_crops.values())
    crop_embs = await asyncio.to_thread(embedder.embed, crop_images)
    for label, emb in zip(crop_labels, crop_embs):
        # L2 정규화
        norm = np.linalg.norm(emb) + 1e-8
        label_to_emb[label] = emb / norm
    
    # 탭 ID → detect label 매핑 (Fix 3에서 정의)
    from src.preprocess.tab_mapper import map_tab_to_label
    
    result = {}
    for item in detected_items:
        tab_id = item.tab_id
        label = map_tab_to_label(tab_id, label_to_emb.keys())
        if label and label in label_to_emb:
            result[tab_id] = label_to_emb[label]
        else:
            result[tab_id] = fallback_emb
    
    return result
```

### 1.2 `search` 엔드포인트 흐름 수정

**기존:**
```python
query_emb = await _build_query_emb_from_detection(embedder, pil_image, image_bytes, mime)
```

**변경 후:**
```python
query_embs_by_tab = await _build_per_tab_query_embs(
    embedder, pil_image, detection, style_ctx.detected_items
)

# 재랭킹 시 탭별 query_emb 사용
for item in style_ctx.detected_items:
    tab_id = item.tab_id
    query_emb = query_embs_by_tab.get(tab_id, fallback_emb)
    # ... rank_products_v3 호출 시 이 query_emb 사용
```

---

## Fix 2: Gemini detect 프롬프트 개선

### 2.1 `src/preprocess/gemini_detector.py` 프롬프트 전면 재작성

**기존 프롬프트:**
```
이미지 속 다음 영역들의 bounding box를 정수 좌표(0~1000 정규화)로 반환하라:
- face (얼굴)
- top, outer, bottom, dress (의류)
- shoes, bag (잡화)
의류가 없는 영역은 포함하지 않는다. 각 레이블당 1개만.
```

**개선 후:**
```python
_DETECTION_PROMPT = """
이미지에서 사람의 얼굴과 모든 의류/액세서리 영역을 빠짐없이 탐지하라.
각 영역을 bounding box(정수 좌표, 0~1000 정규화)로 반환한다.

탐지 가능한 레이블 (해당하는 모든 영역 반환, 같은 레이블도 여러 개 OK):
- face (얼굴)
- top_outer (위에 걸친 셔츠/카디건/재킷 등 외곽 상의 — 단추 열려있거나 안에 다른 옷 보이면 outer)
- top_inner (안쪽 상의 — 티셔츠/탱크탑/크롭탑/이너용 셔츠. 위에 다른 옷 걸쳐도 보이면 분리 탐지)
- outer (코트/패딩/점퍼 — 두꺼운 겉옷)
- bottom (바지/스커트/반바지)
- dress (원피스/점프수트)
- shoes (신발)
- bag (가방/숄더백/토트백/크로스백)
- accessory_ring (반지)
- accessory_necklace (목걸이/펜던트)
- accessory_earring (귀걸이)
- accessory_belt (벨트)
- accessory_hat (모자/베레모/캡)
- accessory_watch (시계)

규칙:
- 레이어드 코디(셔츠 안에 티셔츠)는 top_outer + top_inner로 둘 다 탐지
- 액세서리는 작아도 보이면 반드시 탐지
- 같은 레이블도 시각적으로 다른 영역이면 여러 개 반환 (예: 양쪽 귀걸이)
- 의류가 없는 영역은 포함하지 않음
- confidence는 탐지 확신도 0.0~1.0

JSON 형식으로만 응답:
{"boxes": [{"label": "top_inner", "x1": 0, "y1": 0, "x2": 100, "y2": 100, "confidence": 0.9}]}
"""
```

### 2.2 `BoundingBox.label` 타입 확장 (validator 추가)

```python
VALID_LABELS = {
    'face',
    'top_outer', 'top_inner', 'outer', 'bottom', 'dress',
    'shoes', 'bag',
    'accessory_ring', 'accessory_necklace', 'accessory_earring',
    'accessory_belt', 'accessory_hat', 'accessory_watch',
}


class BoundingBox(BaseModel):
    label: str
    x1: int
    y1: int
    x2: int
    y2: int
    confidence: float = 1.0
    
    @field_validator('label')
    @classmethod
    def validate_label(cls, v: str) -> str:
        # 알 수 없는 레이블은 정규화 시도
        v_lower = v.lower().strip()
        # 'top'만 들어오면 'top_outer'로 fallback
        if v_lower == 'top':
            return 'top_outer'
        if v_lower not in VALID_LABELS:
            logger.warning(f"[BoundingBox] 알 수 없는 레이블: {v}")
        return v_lower
```

---

## Fix 3: detect 레이블 → 탭 ID 스마트 매핑

### 3.1 `src/preprocess/tab_mapper.py` (신규)

```python
"""detect label과 style_analyzer tab_id 간 매핑."""
from typing import Iterable, Optional


# 탭 ID → 매칭 가능한 detect 레이블 우선순위 리스트
TAB_TO_LABELS_PRIORITY: dict[str, list[str]] = {
    'top_outer': ['top_outer', 'top'],
    'top_inner': ['top_inner', 'top'],  # 'top' fallback
    'outer': ['outer', 'top_outer'],
    'bottom': ['bottom'],
    'dress': ['dress'],
    'shoes': ['shoes'],
    'bag': ['bag'],
    'accessory_ring': ['accessory_ring'],
    'accessory_necklace': ['accessory_necklace'],
    'accessory_earring': ['accessory_earring'],
    'accessory_belt': ['accessory_belt'],
    'accessory_hat': ['accessory_hat'],
    'accessory_watch': ['accessory_watch'],
}


def map_tab_to_label(tab_id: str, available_labels: Iterable[str]) -> Optional[str]:
    """탭 ID에 대응되는 detect 레이블을 우선순위 순으로 찾아 반환.
    
    Args:
        tab_id: style_analyzer가 반환한 탭 ID
        available_labels: detect 결과에서 추출 가능한 레이블 집합
    
    Returns:
        매칭되는 레이블 (없으면 None)
    """
    available = set(available_labels)
    priority = TAB_TO_LABELS_PRIORITY.get(tab_id, [])
    for label in priority:
        if label in available:
            return label
    return None
```

---

## Fix 4: 카테고리별 점수 공식 분리

### 4.1 `src/ranking/mood_ranker.py` — 카테고리별 함수 추가

```python
def compute_clothing_score(
    visual_sim: float,
    naver_rank_score: float,
) -> float:
    """의류(상의/이너/아우터/하의/원피스): 시각 매칭 절대 우선, 무드 X, 가격 X."""
    return visual_sim * 0.95 + naver_rank_score * 0.05


def compute_accessory_score(
    visual_sim: float,
    mood_align: float,
    price_fit: float,
    naver_rank_score: float,
) -> float:
    """가방/액세서리: outfit 무드 + 가격대 일치."""
    return (
        visual_sim * 0.40
        + mood_align * 0.30
        + price_fit * 0.20
        + naver_rank_score * 0.10
    )


def price_fit_score(product_price: int, price_range: tuple[int, int]) -> float:
    """outfit 무드로 추정한 가격대와 상품 가격의 적합도."""
    if not product_price or product_price <= 0:
        return 0.5
    low, high = price_range
    if low <= product_price <= high:
        return 1.0
    elif product_price < low:
        ratio = (low - product_price) / max(low, 1)
        return max(0.3, 1 - ratio * 0.7)
    else:
        # 가격대 초과는 더 강하게 패널티 (200만원 가방 같은 케이스)
        ratio = (product_price - high) / max(high, 1)
        return max(0.05, 1 - ratio * 0.8)
```

### 4.2 outfit 무드 → 가격대 자동 추정 (액세서리용)

```python
# src/ranking/mood_to_price.py (신규)

MOOD_TO_PRICE_TIER: dict[str, tuple[int, int]] = {
    'casual_daily': (5_000, 80_000),
    'casual_street': (10_000, 100_000),
    'office_minimal': (30_000, 200_000),
    'office_classic': (50_000, 300_000),
    'luxury_editorial': (200_000, 5_000_000),
    'sporty_active': (10_000, 120_000),
    'feminine_romantic': (20_000, 150_000),
    'vintage_y2k': (10_000, 100_000),
}

DEFAULT_PRICE_RANGE = (10_000, 100_000)


def estimate_price_range_from_mood(mood_label: str) -> tuple[int, int]:
    """Gemini가 분석한 outfit 무드 → 적정 가격대 (가방/액세서리용).
    
    의류에는 적용 안 함.
    """
    mood_lower = mood_label.lower()
    for key, range_tuple in MOOD_TO_PRICE_TIER.items():
        if any(token in mood_lower for token in key.split('_')):
            return range_tuple
    return DEFAULT_PRICE_RANGE


def is_accessory_tab(tab_id: str) -> bool:
    """가방/액세서리 탭 여부."""
    return tab_id == 'bag' or tab_id.startswith('accessory_')
```

### 4.3 `routes_search.py` — 카테고리별 분기

```python
from src.ranking.mood_ranker import (
    compute_clothing_score,
    compute_accessory_score,
    price_fit_score,
)
from src.ranking.mood_to_price import (
    estimate_price_range_from_mood,
    is_accessory_tab,
)

# outfit 무드 → 액세서리용 가격대 추정 (의류엔 X)
mood_label = attributes.get('mood', 'casual_daily')
accessory_price_range = estimate_price_range_from_mood(mood_label)

for item in style_ctx.detected_items:
    tab_id = item.tab_id
    products = raw_results.get(tab_id, [])
    if not products:
        continue
    
    query_emb = query_embs_by_tab.get(tab_id, fallback_emb)
    product_image_embs = product_embs_by_tab.get(tab_id, {})
    
    # 카테고리별 점수 공식 분기
    if is_accessory_tab(tab_id):
        ranked = rank_accessory_products(
            products, query_emb, product_image_embs,
            mood_text_emb, accessory_price_range,
        )
    else:
        ranked = rank_clothing_products(
            products, query_emb, product_image_embs,
        )
    # ... 이후 SKU 클러스터링 + top 5
```

### 4.4 `rank_clothing_products` / `rank_accessory_products` 함수 분리

`mood_ranker.py`에 추가:

```python
def rank_clothing_products(
    products: list[dict],
    query_image_emb: np.ndarray,
    product_image_embs: dict[str, np.ndarray],
) -> list[dict]:
    """의류 재랭킹: 시각 매칭 95% + Naver 5%."""
    total = len(products)
    for i, p in enumerate(products):
        pid = p.get('product_id', '')
        prod_emb = product_image_embs.get(pid)
        
        if prod_emb is not None:
            visual_sim = max(0.0, float(np.dot(query_image_emb, prod_emb)))
        else:
            visual_sim = 0.0
        
        naver_rank = naver_rank_to_score(i, total)
        
        p['_visual_sim'] = visual_sim
        p['_mood_align'] = 0.0  # 의류는 무드 X
        p['_price_fit'] = 0.0
        p['_naver_rank'] = naver_rank
        p['match_score'] = compute_clothing_score(visual_sim, naver_rank)
    
    return sorted(products, key=lambda x: -x['match_score'])


def rank_accessory_products(
    products: list[dict],
    query_image_emb: np.ndarray,
    product_image_embs: dict[str, np.ndarray],
    mood_text_emb: np.ndarray,
    price_range: tuple[int, int],
) -> list[dict]:
    """가방/액세서리 재랭킹: 시각 40% + 무드 30% + 가격대 20% + Naver 10%."""
    total = len(products)
    for i, p in enumerate(products):
        pid = p.get('product_id', '')
        prod_emb = product_image_embs.get(pid)
        
        if prod_emb is not None:
            visual_sim = max(0.0, float(np.dot(query_image_emb, prod_emb)))
            mood_align = cross_modal_mood_score(prod_emb, mood_text_emb)
        else:
            visual_sim = 0.0
            mood_align = 0.0
        
        price_fit = price_fit_score(p.get('price', 0), price_range)
        naver_rank = naver_rank_to_score(i, total)
        
        p['_visual_sim'] = visual_sim
        p['_mood_align'] = mood_align
        p['_price_fit'] = price_fit
        p['_naver_rank'] = naver_rank
        p['match_score'] = compute_accessory_score(
            visual_sim, mood_align, price_fit, naver_rank
        )
    
    return sorted(products, key=lambda x: -x['match_score'])
```

---

## Fix 5: 색상 히스토그램 보조 신호

### 5.1 `src/ranking/color_hist.py` (신규)

```python
"""색상 히스토그램 기반 보조 유사도 신호.

FashionCLIP의 미세 색상 농도(찐핑크 vs 연핑크) 약점 보완.
"""
import numpy as np
from PIL import Image


def compute_color_histogram(image: Image.Image, bins: int = 8) -> np.ndarray:
    """RGB 3채널 각각 bins개로 히스토그램. 정규화된 1D 벡터 반환.
    
    Returns:
        (3 * bins,) 형태 정규화된 히스토그램.
    """
    arr = np.array(image.convert('RGB'))  # (H, W, 3)
    hist_r, _ = np.histogram(arr[:, :, 0], bins=bins, range=(0, 256), density=True)
    hist_g, _ = np.histogram(arr[:, :, 1], bins=bins, range=(0, 256), density=True)
    hist_b, _ = np.histogram(arr[:, :, 2], bins=bins, range=(0, 256), density=True)
    hist = np.concatenate([hist_r, hist_g, hist_b])
    norm = np.linalg.norm(hist) + 1e-8
    return hist / norm


def color_similarity(hist_a: np.ndarray, hist_b: np.ndarray) -> float:
    """두 히스토그램 코사인 유사도 (0~1)."""
    sim = float(np.dot(hist_a, hist_b))
    return max(0.0, min(1.0, sim))
```

### 5.2 의류 점수에 색상 신호 추가

`compute_clothing_score`를 다음으로 교체:

```python
def compute_clothing_score(
    visual_sim: float,
    color_sim: float,
    naver_rank_score: float,
) -> float:
    """의류: 시각 매칭 + 색상 매칭."""
    return visual_sim * 0.80 + color_sim * 0.15 + naver_rank_score * 0.05
```

`rank_clothing_products`에 색상 비교 추가:

```python
def rank_clothing_products(
    products: list[dict],
    query_image_emb: np.ndarray,
    query_color_hist: np.ndarray,
    product_image_embs: dict[str, np.ndarray],
    product_color_hists: dict[str, np.ndarray],
) -> list[dict]:
    total = len(products)
    for i, p in enumerate(products):
        pid = p.get('product_id', '')
        prod_emb = product_image_embs.get(pid)
        prod_hist = product_color_hists.get(pid)
        
        visual_sim = max(0.0, float(np.dot(query_image_emb, prod_emb))) if prod_emb is not None else 0.0
        color_sim = color_similarity(query_color_hist, prod_hist) if prod_hist is not None else 0.5
        naver_rank = naver_rank_to_score(i, total)
        
        p['_visual_sim'] = visual_sim
        p['_color_sim'] = color_sim
        p['_naver_rank'] = naver_rank
        p['match_score'] = compute_clothing_score(visual_sim, color_sim, naver_rank)
    
    return sorted(products, key=lambda x: -x['match_score'])
```

`routes_search.py` — 썸네일 다운로드 시 색상 히스토그램도 함께 계산:

```python
async def _calc_clip_embeddings_and_hists(
    embedder,
    products: list[dict],
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    """썸네일 다운로드 → FashionCLIP 임베딩 + 색상 히스토그램 동시 계산."""
    # ... 기존 임베딩 로직 +
    embs = {}
    hists = {}
    for p, vec, img in zip(valid_products, product_vecs, valid_images):
        pid = p.get("product_id", "")
        embs[pid] = vec
        hists[pid] = compute_color_histogram(img)
    return embs, hists
```

---

## Fix 6: 정확도+가격 4분면 소팅

### 6.1 사용자 요구 정확히 구현

**우선순위:**
1. 정확도 높음 + 가격 싸 (최우선)
2. 정확도 높음 + 가격 비싸
3. 정확도 낮음 + 가격 싸
4. 정확도 낮음 + 가격 비싸 (최후순위)

### 6.2 `src/ranking/quadrant_sort.py` (신규)

```python
"""정확도+가격 4분면 소팅."""

ACCURACY_THRESHOLD = 0.6  # match_score >= 0.6 → 정확도 높음


def quadrant_key(product: dict, price_median: float) -> tuple[int, float]:
    """4분면 정렬 키.
    
    분면 번호 (낮을수록 우선):
        0: 정확도 높음 + 가격 낮음 (median 이하)
        1: 정확도 높음 + 가격 높음
        2: 정확도 낮음 + 가격 낮음
        3: 정확도 낮음 + 가격 높음
    
    같은 분면 내에서는 match_score 내림차순 (정확도 높을수록 위).
    """
    score = product.get('match_score', 0.0)
    price = product.get('price') or 999_999_999
    
    is_accurate = score >= ACCURACY_THRESHOLD
    is_cheap = price <= price_median
    
    if is_accurate and is_cheap:
        quadrant = 0
    elif is_accurate and not is_cheap:
        quadrant = 1
    elif not is_accurate and is_cheap:
        quadrant = 2
    else:
        quadrant = 3
    
    return (quadrant, -score)


def quadrant_sort(products: list[dict]) -> list[dict]:
    """4분면 기준 정렬. 가격 중앙값을 기준으로 싸/비싸 구분."""
    if not products:
        return []
    
    prices = [p.get('price') or 0 for p in products if p.get('price')]
    price_median = float(np.median(prices)) if prices else 50_000
    
    return sorted(products, key=lambda p: quadrant_key(p, price_median))
```

### 6.3 `routes_search.py` — 재랭킹 후 4분면 적용

```python
from src.ranking.quadrant_sort import quadrant_sort

# 재랭킹 → SKU 클러스터링 → 4분면 소팅 → top 5
ranked_20 = rank_clothing_products(...)[:20]  # or rank_accessory_products
clusters = cluster_similar_products_v2(ranked_20)  # Fix 7
deduped = lowest_price_per_cluster(clusters)
final_5 = quadrant_sort(deduped)[:5]
```

### 6.4 sort_by 옵션 확장

```python
# schemas.py
class SearchRequest(BaseModel):
    sort_by: Literal['relevance', 'quadrant', 'price_asc', 'price_desc'] = 'quadrant'
    # 'quadrant'를 기본값으로 설정
```

---

## Fix 7: SKU 클러스터링 강화 — 이미지 임베딩 기반

### 7.1 `src/pricing/normalize.py` — 새 함수 추가

```python
def cluster_similar_products_v2(
    products: list[dict],
    title_threshold: float = 0.70,
    image_sim_threshold: float = 0.92,  # 매우 높은 유사도 = 같은 상품
) -> list[list[dict]]:
    """이미지 임베딩 + 제목 + 브랜드 종합 클러스터링.
    
    같은 상품을 다른 판매처가 올렸어도 묶이도록:
    1. 이미지 유사도 0.92+ → 동일 상품 거의 확정
    2. 제목 유사도 0.70+ AND 같은 브랜드 → 동일 상품
    3. 모델코드 일치 → 동일 상품
    """
    clusters: list[list[dict]] = []
    used: set[int] = set()
    
    for i, p in enumerate(products):
        if i in used:
            continue
        cluster = [p]
        used.add(i)
        p_emb = p.get('_image_emb')  # 미리 계산된 임베딩
        p_codes = set(extract_model_codes(p.get('title', '')))
        
        for j, q in enumerate(products[i+1:], start=i+1):
            if j in used:
                continue
            
            # 조건 1: 이미지 임베딩 매우 유사
            q_emb = q.get('_image_emb')
            if p_emb is not None and q_emb is not None:
                img_sim = float(np.dot(p_emb, q_emb))
                if img_sim >= image_sim_threshold:
                    cluster.append(q)
                    used.add(j)
                    continue
            
            # 조건 2: 모델코드 일치
            q_codes = set(extract_model_codes(q.get('title', '')))
            if p_codes and (p_codes & q_codes):
                cluster.append(q)
                used.add(j)
                continue
            
            # 조건 3: 제목 유사 + 같은 브랜드
            title_sim = title_similarity(p['title'], q['title'])
            same_brand = (
                p.get('brand') and p['brand'] == q.get('brand')
            ) or (
                p.get('mall_name') and p['mall_name'] == q.get('mall_name')
                and title_sim >= 0.85
            )
            if title_sim >= title_threshold and same_brand:
                cluster.append(q)
                used.add(j)
        
        clusters.append(cluster)
    
    return clusters
```

### 7.2 클러스터 내 대표 = 최저가 (기존 유지)

```python
def lowest_price_per_cluster(clusters: list[list[dict]]) -> list[dict]:
    """클러스터별 최저가 1개 + 클러스터 크기 메타 추가."""
    result = []
    for cluster in clusters:
        cheapest = min(cluster, key=lambda x: x.get('price') or 999_999_999)
        cheapest['_cluster_size'] = len(cluster)
        cheapest['_other_sellers'] = [
            {'mall_name': c.get('mall_name'), 'price': c.get('price'), 'link': c.get('link')}
            for c in cluster if c is not cheapest
        ]
        result.append(cheapest)
    return result
```

### 7.3 응답에 다른 판매처 정보 노출 (선택)

```python
# schemas.py
class ProductCard(BaseModel):
    # 기존 필드 +
    cluster_size: int = 1  # 같은 상품 노출 판매처 수
    other_sellers: list[dict] = []  # 다른 판매처 가격 정보 (선택 노출)
```

---

## 2. 작업 순서 (Claude Code 터미널)

순차 실행, 각 Fix 끝나면 git commit:

```bash
cd "C:\Users\Alex KIM\Desktop\사업 프로젝트\인앱토스 1"

# Fix 1: 탭별 query embedding 분리
# - routes_search.py: _build_per_tab_query_embs 신규, _build_query_emb_from_detection 폐기
git commit -m "fix(ranking): per-tab query embedding (no more averaging)"

# Fix 2: Gemini detect 프롬프트 개선
# - gemini_detector.py: 프롬프트 재작성, BoundingBox label validator
git commit -m "fix(detect): support layered + accessories + multi-instance bbox"

# Fix 3: detect label → tab_id 매핑
# - src/preprocess/tab_mapper.py 신규
git commit -m "feat(preprocess): tab_id to detect label smart mapping"

# Fix 4: 카테고리별 점수 공식
# - mood_ranker.py: rank_clothing_products / rank_accessory_products
# - mood_to_price.py 신규
# - routes_search.py: 분기 적용
git commit -m "fix(ranking): split scoring by category (clothing vs accessory)"

# Fix 5: 색상 히스토그램
# - color_hist.py 신규
# - routes_search.py: _calc_clip_embeddings_and_hists
git commit -m "feat(ranking): RGB color histogram as secondary signal"

# Fix 6: 4분면 소팅
# - quadrant_sort.py 신규
# - routes_search.py: 재랭킹 후 quadrant_sort
git commit -m "feat(sort): accuracy-price 4-quadrant sorting (default)"

# Fix 7: SKU 클러스터링 강화
# - normalize.py: cluster_similar_products_v2
# - routes_search.py: v2 호출
git commit -m "fix(pricing): image-embedding based SKU clustering (drop duplicates)"

# 배포
git push origin main
bash deploy.sh   # 또는 직접 gcloud run deploy
```

---

## 3. 배포

### 3.1 Cloud Run 재배포

```powershell
cd "C:\Users\Alex KIM\Desktop\사업 프로젝트\인앱토스 1"

# 환경 변수 로드
$env:GOOGLE_API_KEY = (Get-Content fashion-search/.env | Select-String '^GOOGLE_API_KEY=' | ForEach-Object { $_.Line.Split('=')[1] })
$env:ADMIN_TOKEN = (Get-Content fashion-search/.env | Select-String '^ADMIN_TOKEN=' | ForEach-Object { $_.Line.Split('=')[1] })
$env:NAVER_CLIENT_ID = (Get-Content fashion-search/.env | Select-String '^NAVER_CLIENT_ID=' | ForEach-Object { $_.Line.Split('=')[1] })
$env:NAVER_CLIENT_SECRET = (Get-Content fashion-search/.env | Select-String '^NAVER_CLIENT_SECRET=' | ForEach-Object { $_.Line.Split('=')[1] })

bash deploy.sh
```

### 3.2 검증

```bash
# 헬스 체크
curl https://fashion-search-dibvogjuma-du.a.run.app/health

# 실제 검색 테스트 (테스트 이미지 필요)
curl -X POST https://fashion-search-dibvogjuma-du.a.run.app/api/search \
  -F "file=@test.jpg" \
  -F "sort_by=quadrant" -o result.json

# 응답 검증 항목:
# - response.tabs[].items[].visual_similarity (0~1, 의류는 높을수록 좋음)
# - response.tabs[].items[].color_sim (의류 응답에 추가됨)
# - response.tabs[].items[].cluster_size (같은 상품 다판매처 수)
# - 액세서리 탭에 mood_alignment, price_fit 노출
# - 의류 탭에는 mood_alignment 0.0
```

### 3.3 정성 평가 — 5개 케이스

| 케이스 | 기대 |
|--------|------|
| 핑크 줄무늬 셔츠 + 흰 크롭탑 + 청바지 | top_outer/top_inner 분리, 색농도 매칭, 액세서리 없음 OK |
| 검정 미니드레스 + 빨간 가방 (캐주얼) | dress 탭 정확, bag 탭에 5~10만원대 빨간 가방 (200만원 X) |
| 럭셔리 코트 + 명품가방 (모델컷) | outer 탭 정확, bag 탭에 럭셔리 가격대 가방 |
| 후드티 + 진주 목걸이 + 모자 | accessory_necklace, accessory_hat 탭 등장 |
| 흰 셔츠 + 검정 와이드 + 운동화 | shoes 탭 정확, 같은 운동화 다판매처 1개로 묶임 |

---

## 4. 성공 기준

- [ ] 사용자가 흰 라운드넥 크롭탑 업로드 → '상의' 탭 1순위 = 흰 라운드넥 크롭탑 (다른 흰 상의 X)
- [ ] 캐주얼 outfit 업로드 → '가방' 탭에 200만원 가방 노출 안 됨 (5~10만원대)
- [ ] 액세서리 (목걸이/귀걸이/벨트/모자) 있는 이미지 → 해당 탭 자동 생성
- [ ] 같은 상품을 5개 판매처가 올려도 1순위에 1번만 노출 (cluster_size=5 표시)
- [ ] 정확도 높고 가격 싼 상품이 정확도 높고 비싼 상품보다 먼저 노출
- [ ] 색농도 (찐핑크 vs 연핑크) 매칭 개선됨
- [ ] git push 완료
- [ ] Cloud Run revision: fashion-search-000XX 배포 성공

---

## 5. 주의사항

1. **Gemini detect 프롬프트 변경 후 응답 파싱 재검증** — 새 레이블이 모두 처리되는지
2. **`accessory_*` 카테고리는 style_analyzer도 알아야 함** — 기존 코드 호환 확인
3. **`compute_clothing_score` 색상 히스토그램 추가는 메모리 영향 적음** — bins=8 × 3 = 24개 float만 추가
4. **4분면 소팅의 ACCURACY_THRESHOLD=0.6** — 실측 후 조정 가능
5. **클러스터링 v2의 image_sim_threshold=0.92** — 너무 낮으면 다른 상품도 묶임, 너무 높으면 같은 상품도 분리
6. **SKU 클러스터링 시 _image_emb 필드** — 재랭킹 시 미리 product에 저장해야 함
7. **cluster_size, other_sellers 노출** — 프론트엔드 UI에 표시할지 선택

---

## 6. 본질 원인 한 줄 요약 (사용자 학습용)

> **현재 매칭 실패의 근본 원인은 "탭별로 다른 옷을 찾아야 하는데, 모든 탭이 같은 평균 벡터로 검색"하고, "분위기/가격을 모든 카테고리에 잘못 적용"하기 때문이다. SESSION 9는 이 두 본질을 분해한다 — (1) 의류는 탭별 시각 매칭에 집중하고, (2) 잡화만 무드+가격대를 본다.**

---

## Claude Code 실행 명령어

새 터미널에서:

```bash
cd "C:\Users\Alex KIM\Desktop\사업 프로젝트\인앱토스 1"
claude --dangerously-skip-permissions "docs/SESSION_9_PROMPT.md 파일 정독 후 Fix 1~7 순서대로 정확히 실행. 각 Fix 끝나면 git commit. 모두 끝나면 deploy.sh 실행해서 Cloud Run 재배포 후 git push origin main. 작업 끝나면 https://cloi.pages.dev URL 출력하고 5개 정성 평가 케이스 결과 보고. 반드시 SESSION_9_PROMPT.md의 본질 원인 분석을 먼저 이해하고 시작하라. '최고의 효율, 최고의 고객 경험' 원칙을 항상 기억하라."
```

---

## END OF SESSION 9 PROMPT
