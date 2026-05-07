# SESSION 8: 매칭 정확도 본격 개선 + 학습 데이터 파이프라인 구축

> **목표:** 유저가 "어 이건 내가 원하는 옷이 아닌데" → "오 이거 딱이다, 좋다!" 라고 느낄 정도의 매칭 정확도 달성
> 
> **핵심 전략:** SESSION 7 휴리스틱(mood_match, price_fit) 폐기 + 벡터 기반 재랭킹 + 유저 데이터 학습 파이프라인 인프라 구축

---

## 0. 컨텍스트 (Claude Code 터미널이 반드시 먼저 읽을 것)

### 현재 시스템 (SESSION 7 결과물)
- **인프라:** Cloudflare Pages (React) → CF Worker → Cloud Run (FastAPI) → FashionCLIP + Gemini 2.5 Flash + Naver Shopping API
- **점수 공식 (현재, 잘못됨):** `final_score = clip_sim * 0.45 + mood_match * 0.30 + price_fit * 0.25`
- **문제:**
  1. `mood_match`가 **상품 제목s 한글 키워드 매칭** (캐주얼/데일리 substring) → 30% 가중치가 노이즈
  2. `price_fit`이 **mood → 가격대 강제 매핑** (casual=6만원 이하) → 사용자 의사 무시
  3. clip_sim이 45%만 → 실제 시각 유사도 신호 약화
  4. AttributeClassifier zero-shot 8개 무드 강제 분류 → 'casual'로 편향

### 사용자 핵심 요구
> "옷들을 벡터 값으로 변환해서 분위기와 스타일을 종합적으로 검증하고, 검증된 정보들을 바탕으로 옷들을 추천해라. 텍스트 키워드 매칭이 아닌 순수 비전-언어 임베딩 기반."

### 제약 조건
- 월 인프라 비용 **$20 이하** 유지
- Cloud Run 메모리 **2GB 한계** (현재 2Gi 설정)
- 일 트래픽 100건 미만 (베타)
- Cold start 10초 허용
- Warm 응답 3초 이내 목표
- **Grounding DINO / SAM 2 / PaddleOCR 사용 금지** (PyPI 미존재 + 메모리 초과 + 과거 빌드 실패 이력)
- Florence-2 또는 **Gemini 2.5 Flash bounding box 추출** 활용 (이미 호출 중, 추가 비용 0)

### 참고할 외부 분석
- `C:\Users\Alex KIM\Downloads\deep-research-report.md` — Deep research 보고서 (선별 적용)

---

## 1. 작업 범위 (Phase 1~6)

### Phase 1: 휴리스틱 제거 + 벡터 기반 재랭킹 (P0, 즉시)
### Phase 2: 학습용 데이터 수집 인프라 강화 (P0, 즉시)
### Phase 3: Naver multi-query + dedupe + 옵션 활용 (P1)
### Phase 4: Gemini 기반 의류 crop + 얼굴 마스킹 (P1)
### Phase 5: SKU 정규화 + 가격 비교 분리 (P2)
### Phase 6: 학습 파이프라인 스캐폴딩 (P3, 데이터 축적 대기)

---

## Phase 1: 휴리스틱 제거 + 벡터 기반 재랭킹

### 1.1 `src/ranking/mood_ranker.py` 전면 재작성

**파일 경로:** `fashion-search/src/ranking/mood_ranker.py`

**삭제할 함수:**
- `mood_match_score(product_title, mood_keywords)` — 텍스트 키워드 매칭 폐기
- `price_fit_score(product_price, price_range)` — 강제 가격 패널티 폐기
- `MOOD_KEYWORDS` dict — 사용 안 함

**새로운 함수 추가:**
```python
def cross_modal_mood_score(
    product_image_emb: np.ndarray,
    mood_text_emb: np.ndarray,
) -> float:
    """이미지-텍스트 cross-modal 유사도 (FashionCLIP).
    
    상품 이미지 임베딩과 detected mood 텍스트 임베딩의 코사인 유사도.
    텍스트 키워드 매칭이 아닌 벡터 공간에서 무드 일치도 측정.
    """
    sim = float(np.dot(product_image_emb, mood_text_emb))
    return max(0.0, min(1.0, sim))


def compute_final_score(
    visual_sim: float,        # 쿼리 이미지 ↔ 상품 이미지 직접 유사도
    mood_align: float,        # 상품 이미지 ↔ mood 텍스트 cross-modal 유사도
    naver_rank_score: float,  # Naver 원래 순위 기반 (1.0 ~ 0.0 선형 감소)
) -> float:
    """벡터 기반 복합 점수 — 텍스트 휴리스틱 완전 제거.
    
    가중치:
    - visual_sim: 0.70 (핵심 신호)
    - mood_align: 0.20 (벡터 기반 무드 일치)
    - naver_rank_score: 0.10 (텍스트 검색 relevance 보조)
    """
    return visual_sim * 0.70 + mood_align * 0.20 + naver_rank_score * 0.10


def naver_rank_to_score(rank: int, total: int) -> float:
    """Naver 검색 결과 순위를 0~1 점수로 변환 (선형 감소)."""
    if total <= 0:
        return 0.5
    return max(0.0, 1.0 - rank / total)


def rank_products_v3(
    products: list[dict],
    query_image_emb: np.ndarray,
    product_image_embs: dict[str, np.ndarray],  # product_id → embedding
    mood_text_emb: np.ndarray,
    sort_by: str = 'relevance',
) -> list[dict]:
    """벡터 기반 재랭킹 (v3)."""
    total = len(products)
    
    for i, p in enumerate(products):
        pid = p.get('product_id', '')
        prod_emb = product_image_embs.get(pid)
        
        if prod_emb is not None:
            visual_sim = float(np.dot(query_image_emb, prod_emb))
            mood_align = cross_modal_mood_score(prod_emb, mood_text_emb)
        else:
            # 썸네일 다운로드 실패 시 Naver 순위에만 의존
            visual_sim = 0.0
            mood_align = 0.0
        
        naver_rank = naver_rank_to_score(i, total)
        
        p['_visual_sim'] = visual_sim
        p['_mood_align'] = mood_align
        p['_naver_rank'] = naver_rank
        p['match_score'] = compute_final_score(visual_sim, mood_align, naver_rank)
    
    if sort_by == 'price_asc':
        return sorted(products, key=lambda x: (x.get('price', 999999999), -x['match_score']))
    elif sort_by == 'price_desc':
        return sorted(products, key=lambda x: (-x.get('price', 0), -x['match_score']))
    else:
        return sorted(products, key=lambda x: -x['match_score'])
```

**기존 `rank_products` 함수는 deprecated 처리 (호환성 유지용 한 줄 wrapper로):**
```python
def rank_products(products, clip_scores, mood_label, price_range, sort_by='relevance'):
    """[DEPRECATED] Use rank_products_v3 instead."""
    raise DeprecationWarning("rank_products v2 is deprecated. Use rank_products_v3.")
```

### 1.2 `apps/api/routes_search.py` 재랭킹 로직 교체

**기존 코드 (라인 200~250):**
```python
ranked = rank_products(
    products, clip_scores, mood_label, price_range, sort_by='relevance'
)[:5]
```

**교체 후:**
```python
# 1. 쿼리 이미지 임베딩
query_emb = await asyncio.to_thread(embedder.embed_single, pil_image)

# 2. mood 텍스트 임베딩 (Gemini가 분석한 mood 문자열)
mood_text = attributes.get('mood', 'casual style')
mood_text_emb = await asyncio.to_thread(embedder.encode_text, [mood_text])
mood_text_emb = mood_text_emb[0] if mood_text_emb.ndim > 1 else mood_text_emb

# 3. 상품 이미지 임베딩 (썸네일 다운로드 + 임베딩, 기존 _calc_clip_scores 재사용 가능)
product_image_embs = await _calc_clip_embeddings(embedder, products)

# 4. 재랭킹
from src.ranking.mood_ranker import rank_products_v3
ranked = rank_products_v3(
    products, query_emb, product_image_embs, mood_text_emb, sort_by='relevance'
)[:5]
```

**기존 `_calc_clip_scores` 함수를 `_calc_clip_embeddings`로 변경** (점수 dict 대신 임베딩 dict 반환):
```python
async def _calc_clip_embeddings(
    embedder,
    products: list[dict],
) -> dict[str, np.ndarray]:
    """썸네일 다운로드 + FashionCLIP 임베딩. product_id → embedding dict 반환."""
    if not products or embedder is None:
        return {}

    async with httpx.AsyncClient() as client:
        thumbnails = await asyncio.gather(
            *[_download_thumbnail(client, p.get("image_url", "")) for p in products]
        )

    valid_pairs = [(p, t) for p, t in zip(products, thumbnails) if t is not None]
    if not valid_pairs:
        return {}

    valid_products, valid_images = zip(*valid_pairs)
    product_vecs = await asyncio.to_thread(embedder.embed, list(valid_images))

    return {
        p.get("product_id", ""): vec
        for p, vec in zip(valid_products, product_vecs)
    }
```

### 1.3 `src/ranking/attribute_classifier.py` — `PRICE_TIER_BY_MOOD` 제거

**삭제:**
```python
PRICE_TIER_BY_MOOD = { ... }  # 전체 dict 삭제
```

**`classify_all` 메서드 수정 (price_tier/price_range 반환 제거):**
```python
def classify_all(self, image: Image.Image) -> Dict:
    image_emb = self.embedder.embed_single(image)
    if image_emb.ndim == 1:
        image_emb = image_emb[np.newaxis, :]

    mood_top = self._top_k(image_emb, MOOD_OPTIONS, k=1)[0]

    return {
        'neckline': self._top_k(image_emb, NECKLINE_OPTIONS, k=1)[0][0],
        'fit': self._top_k(image_emb, FIT_OPTIONS, k=1)[0][0],
        'sleeve': self._top_k(image_emb, SLEEVE_OPTIONS, k=1)[0][0],
        'material': self._top_k(image_emb, MATERIAL_OPTIONS, k=2),
        'pattern': self._top_k(image_emb, PATTERN_OPTIONS, k=1)[0][0],
        'mood': mood_top[0],
        'mood_confidence': mood_top[1],
        # price_tier, price_range 필드 제거
    }
```

### 1.4 `apps/api/schemas.py` — `ProductCard` 필드 변경

**기존:**
```python
class ProductCard(BaseModel):
    ...
    clip_similarity: float
    mood_match: float
    price_fit: float
```

**변경 후:**
```python
class ProductCard(BaseModel):
    ...
    visual_similarity: float  # 쿼리-상품 직접 시각 유사도
    mood_alignment: float     # cross-modal 무드 일치도
    naver_rank_score: float   # Naver 검색 순위 점수
```

`SearchResponse.detected_attributes`에서 `price_tier`, `price_range` 키 제거.

### 1.5 검증
- `pytest fashion-search/tests/` (기존 테스트가 있다면)
- `python fashion-search/scripts/integration_test_v2.py` (있으면)
- 수동 테스트: V넥 니트 + 흰 와이셔츠 이너 코디 이미지 → 결과 5개 정성 평가

---

## Phase 2: 학습용 데이터 수집 인프라 강화

### 2.1 `src/storage/user_image_store.py` 확장 — 상품 스냅샷 저장

**`UserImageStore`에 메서드 추가:**

```python
async def save_session_snapshot(
    self,
    image_hash: str,
    session_id: str,
    products_shown: list[dict],  # 노출된 모든 상품 (탭별 평탄화)
    query_attributes: dict,
) -> None:
    """검색 세션 전체 스냅샷 저장.
    
    Naver URL 만료 대비 + impression-level 학습 데이터 확보.
    클릭 안 된 상품(negative)도 모두 저장하여 contrastive learning 가능.
    
    저장 구조:
        gs://cloi-user-images/sessions/{YYYY/MM/DD}/{image_hash}.json
            - session_id, image_hash, query_attributes
            - products_shown: [{product_id, title, image_url, price, rank, tab_id}]
        
        gs://cloi-user-images/product-thumbs/{product_id_hash}.jpg  (캐시)
    """
    if not self.enabled:
        return
    try:
        now = datetime.utcnow()
        prefix = f'sessions/{now.year}/{now.month:02d}/{now.day:02d}'
        
        snapshot = {
            'session_id': session_id,
            'image_hash': image_hash,
            'timestamp': now.isoformat(),
            'query_attributes': query_attributes,
            'products_shown': products_shown,
        }
        
        blob = self.bucket.blob(f'{prefix}/{image_hash}.json')
        blob.upload_from_string(
            json.dumps(snapshot, ensure_ascii=False),
            content_type='application/json',
        )
    except Exception as e:
        logger.warning(f"[UserImageStore] 세션 스냅샷 저장 실패: {e}")


async def cache_product_thumbnail(
    self,
    product_id: str,
    image_bytes: bytes,
) -> Optional[str]:
    """클릭된 상품 썸네일 캐시 저장 (Naver URL 만료 대비).
    
    중복 방지: product_id 해시 기반 경로.
    """
    if not self.enabled:
        return None
    try:
        # product_id 해시 (안전한 파일명)
        pid_hash = hashlib.md5(product_id.encode()).hexdigest()[:16]
        blob = self.bucket.blob(f'product-thumbs/{pid_hash}.jpg')
        
        # 이미 존재하면 스킵
        if blob.exists():
            return f'gs://cloi-user-images/product-thumbs/{pid_hash}.jpg'
        
        blob.upload_from_string(image_bytes, content_type='image/jpeg')
        return f'gs://cloi-user-images/product-thumbs/{pid_hash}.jpg'
    except Exception:
        return None
```

### 2.2 `src/logging/search_logger.py` — impression 로그 컬럼 추가

**`product_clicks` 테이블에 컬럼 추가:**
```python
_NEW_CLICK_COLUMNS = [
    # 기존 컬럼들...
    ("session_id", "TEXT"),  # 세션 추적
    ("visual_similarity", "REAL"),  # v3 점수 분리
    ("mood_alignment", "REAL"),
    ("naver_rank_score", "REAL"),
]
```

**새 테이블 추가 (impressions):**
```python
"""
CREATE TABLE IF NOT EXISTS product_impressions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT NOT NULL,
    image_hash      TEXT NOT NULL,
    product_id      TEXT NOT NULL,
    tab_id          TEXT,
    rank_position   INTEGER,
    visual_similarity REAL,
    mood_alignment  REAL,
    match_score     REAL,
    clicked         INTEGER DEFAULT 0,  -- 0: 미클릭, 1: 클릭됨
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_impressions_session ON product_impressions(session_id);
CREATE INDEX IF NOT EXISTS idx_impressions_image ON product_impressions(image_hash);
"""
```

**새 함수:**
```python
async def log_impressions(
    session_id: str,
    image_hash: str,
    products: list[dict],  # 탭별 평탄화된 노출 상품
) -> None:
    """검색 결과 노출 시 모든 상품을 impression으로 기록 (negative pair 데이터)."""
    try:
        async with aiosqlite.connect(_get_db_path()) as db:
            for p in products:
                await db.execute(
                    """
                    INSERT INTO product_impressions (
                        session_id, image_hash, product_id, tab_id, rank_position,
                        visual_similarity, mood_alignment, match_score
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id, image_hash,
                        p.get('product_id', ''),
                        p.get('tab_id', ''),
                        p.get('rank_position', 0),
                        p.get('_visual_sim', 0.0),
                        p.get('_mood_align', 0.0),
                        p.get('match_score', 0.0),
                    ),
                )
            await db.commit()
    except Exception as exc:
        logger.warning("[search_logger] impression 기록 실패: %s", exc)


async def mark_impression_clicked(session_id: str, product_id: str) -> None:
    """클릭 시 해당 impression 레코드의 clicked=1로 업데이트."""
    try:
        async with aiosqlite.connect(_get_db_path()) as db:
            await db.execute(
                """
                UPDATE product_impressions
                SET clicked = 1
                WHERE session_id = ? AND product_id = ?
                """,
                (session_id, product_id),
            )
            await db.commit()
    except Exception as exc:
        logger.warning("[search_logger] impression 업데이트 실패: %s", exc)
```

### 2.3 `apps/api/routes_search.py` — 세션 ID 생성 + impression 로깅

**`/search` 엔드포인트:**
```python
import uuid

# response 생성 직전
session_id = str(uuid.uuid4())

# 모든 탭의 상품을 평탄화하여 impression 로깅
all_products = []
for tab in tabs:
    for rank, item in enumerate(tab.items):
        all_products.append({
            'product_id': item.id,
            'tab_id': tab.tab_id,
            'rank_position': rank,
            '_visual_sim': item.visual_similarity,
            '_mood_align': item.mood_alignment,
            'match_score': item.match_score,
        })

await log_impressions(session_id, image_hash, all_products)

# 세션 스냅샷도 GCS에 저장
asyncio.create_task(_user_image_store.save_session_snapshot(
    image_hash=image_hash,
    session_id=session_id,
    products_shown=all_products,
    query_attributes={
        'mood': mood_label,
        'overall_style': style_ctx.overall_style_context,
    },
))

# response에 session_id 포함
response.session_id = session_id
```

**`/click` 엔드포인트:**
```python
@router.post("/click", status_code=204)
async def record_click_v2(body: ClickRequest) -> None:
    await log_click_v2(
        image_hash=body.image_hash,
        product_id=body.product_id,
        # ...
        session_id=body.session_id,  # 신규 필드
    )
    
    # impression 테이블의 clicked=1 업데이트
    if body.session_id:
        await mark_impression_clicked(body.session_id, body.product_id)
```

### 2.4 `apps/api/schemas.py` — `SearchResponse.session_id` + `ClickRequest.session_id` 추가

```python
class SearchResponse(BaseModel):
    session_id: str  # 신규
    image_hash: str
    # ...

class ClickRequest(BaseModel):
    session_id: str  # 신규
    image_hash: str
    product_id: str
    # ...
```

### 2.5 프론트엔드 — `cloi/src/services/api.ts` + UI 컴포넌트
- `SearchResponse.session_id`를 받아서 클릭 시 함께 전송
- `ClickRequest`에 session_id 포함

---

## Phase 3: Naver multi-query + dedupe + 옵션

### 3.1 `src/search/parallel_search.py` — multi-query 확장

**현재:** `detected_items`별 단일 쿼리만 사용
**변경:** 각 아이템당 3~5개 multi-query 생성 후 union

```python
async def search_all_items_v3(
    detected_items: list[DetectedItem],
) -> dict[str, list[dict]]:
    """탭별 multi-query union + dedupe + Naver 옵션 활용."""
    tasks = {}
    for item in detected_items:
        # Gemini가 생성한 search_queries가 이미 있다면 활용
        queries = item.search_queries[:5] if item.search_queries else [item.subcategory]
        tasks[item.tab_id] = _search_multi_query_dedupe(queries, exclude='used:rental:cbshop')
    
    results_list = await asyncio.gather(*tasks.values())
    return dict(zip(tasks.keys(), results_list))


async def _search_multi_query_dedupe(
    queries: list[str],
    display: int = 40,
    exclude: str = 'used:rental:cbshop',
) -> list[dict]:
    """3~5개 쿼리 병렬 검색 → productId 기반 dedupe."""
    tasks = [
        _naver_search_single(q, display=display, exclude=exclude)
        for q in queries
    ]
    all_results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # union + dedupe
    seen_ids = set()
    merged = []
    for r in all_results:
        if isinstance(r, Exception):
            continue
        for p in r:
            pid = p.get('product_id', '') or p.get('link', '')
            if pid in seen_ids:
                continue
            seen_ids.add(pid)
            merged.append(p)
    
    return merged[:60]  # 상위 60개 후보로 압축


async def _naver_search_single(
    query: str,
    display: int = 40,
    exclude: str = 'used:rental:cbshop',
) -> list[dict]:
    """단일 쿼리 Naver Shopping API 호출 (exclude 옵션 지원)."""
    # 기존 _naver_search에 exclude 파라미터 추가
    # ?query=...&display=40&exclude=used:rental:cbshop
    ...
```

### 3.2 Naver `productType` 활용 — 가격비교 상품 우선

```python
def boost_price_compared_products(products: list[dict]) -> list[dict]:
    """productType=1(가격비교 상품)에 약간의 부스트.
    동일 SKU 가격 비교 가능성이 높음.
    """
    for p in products:
        if p.get('productType') == 1:  # 가격비교 매칭
            p['_naver_boost'] = 0.05
        else:
            p['_naver_boost'] = 0.0
    return products
```

---

## Phase 4: Gemini 기반 의류 crop + 얼굴 마스킹

### 4.1 `src/preprocess/gemini_detector.py` (신규)

**Grounding DINO 대신 Gemini 2.5 Flash로 bbox 추출.** 이미 호출 중인 모델 활용 → 추가 비용 0.

```python
"""Gemini 2.5 Flash 기반 의류 bbox 탐지 + 얼굴 영역 추출."""
from PIL import Image, ImageFilter
from pydantic import BaseModel
from google import genai
from google.genai import types


class BoundingBox(BaseModel):
    label: str  # 'face', 'top', 'outer', 'bottom', 'shoes', 'bag'
    x1: int
    y1: int
    x2: int
    y2: int
    confidence: float


class DetectionResult(BaseModel):
    boxes: list[BoundingBox]


async def detect_regions(
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
) -> DetectionResult:
    """Gemini 2.5 Flash로 의류/얼굴 bbox 추출.
    
    좌표는 0~1000 정규화 → 실제 픽셀 변환은 호출자 책임.
    """
    prompt = """
    이미지 속 다음 영역들의 bounding box를 정수 좌표(0~1000 정규화)로 반환하라:
    - face (얼굴)
    - top, outer, bottom, dress (의류)
    - shoes, bag (잡화)
    
    JSON 형식: {"boxes": [{"label": "face", "x1": ..., "y1": ..., "x2": ..., "y2": ..., "confidence": 0.0~1.0}]}
    """
    
    client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
    resp = await asyncio.to_thread(
        client.models.generate_content,
        model="gemini-2.5-flash",
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            prompt,
        ],
        config=types.GenerateContentConfig(
            temperature=0.1,
            response_mime_type="application/json",
            response_schema=DetectionResult,
        ),
    )
    return DetectionResult.model_validate_json(resp.text)


def blur_face_regions(image: Image.Image, boxes: list[BoundingBox]) -> Image.Image:
    """얼굴 영역만 블러 처리 (개인정보 보호 + 임베딩 노이즈 감소)."""
    out = image.copy()
    w, h = image.size
    for box in boxes:
        if box.label != 'face':
            continue
        # 0~1000 → 실제 픽셀
        x1 = int(box.x1 * w / 1000)
        y1 = int(box.y1 * h / 1000)
        x2 = int(box.x2 * w / 1000)
        y2 = int(box.y2 * h / 1000)
        crop = out.crop((x1, y1, x2, y2)).filter(ImageFilter.GaussianBlur(radius=20))
        out.paste(crop, (x1, y1))
    return out


def crop_garment_regions(
    image: Image.Image,
    boxes: list[BoundingBox],
    expand_ratio: float = 0.08,
) -> dict[str, Image.Image]:
    """의류별 crop 이미지 dict 반환. 카테고리 → PIL Image."""
    w, h = image.size
    crops = {}
    for box in boxes:
        if box.label in ('face',):
            continue
        x1 = int(box.x1 * w / 1000)
        y1 = int(box.y1 * h / 1000)
        x2 = int(box.x2 * w / 1000)
        y2 = int(box.y2 * h / 1000)
        # 확장
        dx = int((x2 - x1) * expand_ratio)
        dy = int((y2 - y1) * expand_ratio)
        x1, y1 = max(0, x1 - dx), max(0, y1 - dy)
        x2, y2 = min(w, x2 + dx), min(h, y2 + dy)
        crops[box.label] = image.crop((x1, y1, x2, y2))
    return crops
```

### 4.2 `apps/api/routes_search.py` — Gemini detect 추가

**파이프라인 흐름 (기존 +α):**
```
1. 이미지 업로드
2. Gemini detect_regions (병렬로 style 분석과 함께)
3. 얼굴 블러 + 의류 crop 생성
4. 의류 crop별로 FashionCLIP 임베딩
5. crop별 임베딩을 평균 또는 max-pool → 최종 query embedding
6. Naver 검색 → 상품 임베딩 → 재랭킹 (Phase 1)
```

**로직 추가:**
```python
from src.preprocess.gemini_detector import detect_regions, blur_face_regions, crop_garment_regions

# Gemini detect (style_analyzer + attribute_classifier와 병렬)
detect_coro = detect_regions(image_bytes, mime_type=mime)
style_ctx, attributes, detection = await asyncio.gather(
    analyze_style(image_bytes, mime_type=mime),
    attr_coro,
    detect_coro,
)

# 얼굴 블러 + crop
masked_image = blur_face_regions(pil_image, detection.boxes)
garment_crops = crop_garment_regions(masked_image, detection.boxes)

# crop별 임베딩 후 평균 (의류 영역만 집중)
if garment_crops:
    crop_embs = await asyncio.to_thread(
        embedder.embed, list(garment_crops.values())
    )
    query_emb = np.mean(crop_embs, axis=0)
    query_emb = query_emb / np.linalg.norm(query_emb)  # L2 정규화
else:
    # fallback: 전체 이미지 임베딩
    query_emb = await asyncio.to_thread(embedder.embed_single, masked_image)
```

---

## Phase 5: SKU 정규화 + 가격 비교 분리

### 5.1 `src/pricing/normalize.py` (신규)

```python
"""한국 패션 상품명 정규화 + SKU 매칭."""
import re
from rapidfuzz import fuzz

STOPWORDS = {
    "무료배송", "당일출고", "오늘출발", "최저가", "특가", "행사", "세일",
    "여성", "남성", "봄신상", "신상", "추천", "인기", "베스트",
}

REPLACERS = [
    (r"\b(v[\s-]?neck|브이넥|v넥)\b", "v_neck"),
    (r"\b(라운드넥|round[\s-]?neck|crew[\s-]?neck)\b", "crew_neck"),
    (r"\b(오버핏|루즈핏|박시)\b", "oversized"),
    (r"\b(슬림핏|타이트핏)\b", "slim_fit"),
    (r"\b(오프화이트|아이보리)\b", "white"),
]

MODEL_CODE_RE = re.compile(r"\b[A-Z0-9]{2,}[-_/]?[A-Z0-9]{2,}\b")
TOKEN_RE = re.compile(r"[a-zA-Z0-9_가-힣]+")


def normalize_title(title: str) -> str:
    s = title.lower()
    s = re.sub(r"<[^>]+>", " ", s)  # html tag 제거
    for pat, rep in REPLACERS:
        s = re.sub(pat, rep, s, flags=re.IGNORECASE)
    toks = [t for t in TOKEN_RE.findall(s) if t not in STOPWORDS]
    return " ".join(toks)


def title_similarity(a: str, b: str) -> float:
    return fuzz.token_set_ratio(normalize_title(a), normalize_title(b)) / 100.0


def cluster_similar_products(
    products: list[dict],
    title_threshold: float = 0.75,
    image_sim_threshold: float = 0.85,
) -> list[list[dict]]:
    """동일 SKU 추정 클러스터링.
    
    같은 클러스터 = 같은 디자인의 다른 판매처.
    클러스터 내부에서만 가격 비교.
    """
    clusters = []
    used = set()
    
    for i, p in enumerate(products):
        if i in used:
            continue
        cluster = [p]
        used.add(i)
        for j, q in enumerate(products[i+1:], start=i+1):
            if j in used:
                continue
            title_sim = title_similarity(p['title'], q['title'])
            brand_match = (
                p.get('brand') and p['brand'] == q.get('brand')
            )
            if title_sim >= title_threshold or brand_match:
                cluster.append(q)
                used.add(j)
        clusters.append(cluster)
    
    return clusters


def lowest_price_per_cluster(clusters: list[list[dict]]) -> list[dict]:
    """클러스터별 최저가 1개씩 선택."""
    result = []
    for cluster in clusters:
        cheapest = min(cluster, key=lambda x: x.get('price') or 999999999)
        cheapest['_cluster_size'] = len(cluster)
        result.append(cheapest)
    return result
```

### 5.2 `routes_search.py` — SKU 클러스터 적용

```python
from src.pricing.normalize import cluster_similar_products, lowest_price_per_cluster

# 재랭킹 후 SKU 클러스터링
ranked = rank_products_v3(...)[:20]  # top 20
clusters = cluster_similar_products(ranked)
deduped_top = lowest_price_per_cluster(clusters)[:5]  # 클러스터별 최저가만 노출
```

---

## Phase 6: 학습 파이프라인 스캐폴딩

> **주의:** 데이터 1,000건 이상 쌓이기 전까지는 실제 학습 X. 인프라만 미리 구축.

### 6.1 `fashion-search/training/` 디렉토리 생성

```
fashion-search/
  training/
    __init__.py
    data_curator.py          # GCS + SQLite → 학습 데이터셋
    pair_generator.py        # positive/negative pair 추출
    lora_trainer.py          # FashionCLIP LoRA 미세조정
    evaluator.py             # gold set 평가
    deploy_new_model.py      # 평가 통과 시 배포
  gold_set/
    queries/                 # 100개 쿼리 이미지
    ground_truth.jsonl       # query_image_hash → relevant product_ids
```

### 6.2 `training/data_curator.py`

```python
"""GCS 세션 스냅샷 + SQLite impression/click → 학습 데이터셋."""
import asyncio
import json
from pathlib import Path

import aiosqlite
from google.cloud import storage


async def export_training_data(
    output_path: str,
    min_clicks_per_session: int = 1,
) -> dict:
    """모든 세션 데이터를 학습 가능한 jsonl로 export.
    
    각 라인:
    {
        "query_image_hash": "abc...",
        "query_image_gcs": "gs://cloi-user-images/user-images/...",
        "positives": ["product_id_1", ...],  # 클릭된 상품
        "negatives": ["product_id_2", ...],  # 노출되었지만 클릭 안 됨 (hard negative)
        "session_id": "...",
        "query_attributes": {"mood": "...", ...}
    }
    """
    db_path = "fashion-search/data/search.db"
    
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        
        # 세션별 클릭/임프레션 집계
        query = """
        SELECT 
            i.session_id,
            i.image_hash,
            i.product_id,
            i.tab_id,
            i.rank_position,
            i.match_score,
            i.clicked
        FROM product_impressions i
        WHERE i.session_id IN (
            SELECT session_id 
            FROM product_impressions 
            WHERE clicked = 1
            GROUP BY session_id
            HAVING COUNT(*) >= ?
        )
        ORDER BY i.session_id, i.rank_position
        """
        
        async with db.execute(query, (min_clicks_per_session,)) as cursor:
            rows = await cursor.fetchall()
    
    # 세션별 그룹핑
    sessions = {}
    for row in rows:
        sid = row['session_id']
        if sid not in sessions:
            sessions[sid] = {
                'session_id': sid,
                'image_hash': row['image_hash'],
                'positives': [],
                'negatives': [],
            }
        if row['clicked']:
            sessions[sid]['positives'].append(row['product_id'])
        else:
            sessions[sid]['negatives'].append(row['product_id'])
    
    # jsonl 저장
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        for sess in sessions.values():
            f.write(json.dumps(sess, ensure_ascii=False) + '\n')
    
    return {
        'sessions_exported': len(sessions),
        'total_positives': sum(len(s['positives']) for s in sessions.values()),
        'total_negatives': sum(len(s['negatives']) for s in sessions.values()),
    }


if __name__ == "__main__":
    stats = asyncio.run(export_training_data('training/data/raw/sessions.jsonl'))
    print(f"Exported: {stats}")
```

### 6.3 `training/pair_generator.py`

```python
"""positive/negative pair 생성 + hard negative mining."""
import json
from pathlib import Path


def generate_pairs(
    sessions_jsonl: str,
    output_jsonl: str,
    hard_negative_top_k: int = 5,  # 클릭 안 된 상품 중 상위 5개를 hard negative로
) -> dict:
    """세션 jsonl → (query, positive, negative) triplet jsonl.
    
    각 라인: {"query": "image_hash", "positive": "product_id", "negative": "product_id"}
    """
    pairs = []
    with open(sessions_jsonl) as f:
        for line in f:
            sess = json.loads(line)
            for pos in sess['positives']:
                # hard negative: 같은 세션에서 클릭 안 된 상품
                negs = sess['negatives'][:hard_negative_top_k]
                for neg in negs:
                    pairs.append({
                        'query': sess['image_hash'],
                        'positive': pos,
                        'negative': neg,
                    })
    
    Path(output_jsonl).parent.mkdir(parents=True, exist_ok=True)
    with open(output_jsonl, 'w') as f:
        for p in pairs:
            f.write(json.dumps(p) + '\n')
    
    return {'total_pairs': len(pairs)}


if __name__ == "__main__":
    stats = generate_pairs(
        'training/data/raw/sessions.jsonl',
        'training/data/pairs/triplets.jsonl',
    )
    print(f"Generated: {stats}")
```

### 6.4 `training/lora_trainer.py`

```python
"""FashionCLIP LoRA 미세조정 (PEFT 라이브러리).
실행 조건: GCP T4 GPU 인스턴스에서 수동 실행.
배치당 ~30분, 데이터 5,000 pair 기준.
"""
# 스캐폴딩만 — 실제 구현은 데이터 1,000건 쌓인 후
# Reference: https://github.com/huggingface/peft

import torch
from peft import LoraConfig, get_peft_model
from transformers import CLIPModel, CLIPProcessor


def train_lora(
    pairs_jsonl: str,
    base_model: str = "patrickjohncyh/fashion-clip",
    output_dir: str = "training/checkpoints/lora_v1",
    rank: int = 8,
    epochs: int = 3,
    batch_size: int = 32,
):
    """LoRA fine-tuning 메인 함수.
    
    Args:
        pairs_jsonl: triplet 학습 데이터
        base_model: pretrained FashionCLIP
        output_dir: LoRA weight 저장 경로
        rank: LoRA rank (낮을수록 빠름, 8~16 권장)
        epochs: 학습 에포크
        batch_size: GPU 메모리 따라 조정
    """
    # TODO: 데이터 1,000건 쌓인 후 구현
    raise NotImplementedError("데이터 축적 대기 중. 1,000+ pair 시점에 구현.")


if __name__ == "__main__":
    train_lora('training/data/pairs/triplets.jsonl')
```

### 6.5 `training/evaluator.py`

```python
"""gold set 100개 회귀 테스트 — 새 모델 vs 현재 모델."""
import json
from pathlib import Path


def evaluate_model(
    model_path: str,
    gold_set_path: str = "training/gold_set/ground_truth.jsonl",
) -> dict:
    """Recall@5, Recall@10, MRR 계산.
    
    gold_set 형식 (각 라인):
        {
            "query_image_path": "training/gold_set/queries/001.jpg",
            "relevant_product_ids": ["pid_1", "pid_2"]
        }
    """
    # TODO: 데이터 1,000건 + gold set 100개 라벨링 후 구현
    raise NotImplementedError("Gold set 100개 수동 라벨링 필요.")
```

### 6.6 `training/README.md`

```markdown
# Cloi 학습 파이프라인

## 데이터 흐름
1. 유저 검색 → impression + click 로그 (SQLite)
2. 유저 이미지 + 세션 스냅샷 → GCS
3. `data_curator.py` → 세션 jsonl
4. `pair_generator.py` → triplet pairs
5. `lora_trainer.py` → LoRA 가중치 (T4 GPU 인스턴스)
6. `evaluator.py` → gold set 회귀
7. 평가 통과 시 → `deploy_new_model.py` → Cloud Run 핫스왑

## 실행 시점
- 데이터 1,000+ click 쌓일 때까지 학습 X
- 매월 1회 새 LoRA 학습 + 배포

## 비용
- T4 GPU: 시간당 $0.35
- 학습 1회: 30분 (배치) + 평가 10분 = ~$0.30
- 월 1회 학습 = 월 ~$0.30 추가
```

---

## 2. 배포 단계

### 2.1 의존성 추가

`fashion-search/requirements.txt`에 추가:
```
rapidfuzz==3.10.0
```

학습 파이프라인은 별도 requirements (Cloud Run에 포함하지 않음):
`fashion-search/training/requirements.txt`:
```
peft>=0.13.0
transformers>=4.44.2,<5.0
torch==2.3.0
google-cloud-storage==2.18.0
aiosqlite==0.20.0
```

### 2.2 빌드 + 배포

```bash
# 1. 로컬 검증
cd "C:\Users\Alex KIM\Desktop\사업 프로젝트\인앱토스 1\fashion-search"
python -c "from src.ranking.mood_ranker import rank_products_v3; print('OK')"
python -c "from src.preprocess.gemini_detector import detect_regions; print('OK')"
python -c "from src.pricing.normalize import normalize_title; print(normalize_title('<b>브이넥 니트</b> 무료배송'))"

# 2. Cloud Run 배포
cd ".."
$env:GOOGLE_API_KEY = "<현재 키>"
$env:ADMIN_TOKEN = "<현재 토큰>"
bash deploy.sh

# 3. CF Worker 재배포
cd server
wrangler deploy

# 4. CF Pages 빌드 + 배포
cd ../cloi
npm run build
wrangler pages deploy dist --project-name=cloi
```

### 2.3 검증

```bash
# Cloud Run /health
curl https://fashion-search-dibvogjuma-du.a.run.app/health

# Cloud Run /api/search (실제 이미지)
curl -X POST https://fashion-search-dibvogjuma-du.a.run.app/api/search \
  -F "file=@test.jpg" \
  -F "sort_by=relevance"

# CF Worker /api/health
curl https://cloi-api.kyoung361207.workers.dev/api/health

# 응답 검증:
# - response.session_id 존재
# - response.tabs[].items[].visual_similarity 존재 (0~1)
# - response.tabs[].items[].mood_alignment 존재 (0~1)
# - response.detected_attributes에 price_tier/price_range 없음 ✓
```

### 2.4 정성 평가 — 5개 테스트 이미지

| 테스트 이미지 | 기대 결과 |
|--------------|----------|
| V넥 니트 + 흰 와이셔츠 이너 | top_outer/top_inner 분리, 색상/넥라인 정확 |
| 오버사이즈 후드 + 와이드 데님 | 핏 매칭, 캐주얼 스타일 |
| 쉬폰 블라우스 + A라인 스커트 | 페미닌 무드, 소재 일치 |
| 블레이저 + 슬랙스 (오피스룩) | 클래식 무드, 가격대 무관 |
| 럭셔리 코트 (모델컷) | 얼굴 마스킹 적용, 럭셔리 무드 |

각 이미지에 대해:
- ✅ 이전 SESSION 7 결과 vs SESSION 8 결과 스크린샷 비교
- ✅ "딱이다" 느낌 5점 척도 평가
- ✅ visual_similarity 분포 확인 (Top-1이 0.7+ 나오는지)

---

## 3. SESSION_STATUS.md 업데이트

작업 완료 후 `SESSION_STATUS.md`에 다음 추가:

```markdown
## SESSION 8: ✅ 완료 (YYYY-MM-DD) — 휴리스틱 제거 + 학습 데이터 인프라

### 핵심 변경
- mood_match (텍스트 키워드) + price_fit (강제 매핑) 폐기
- 벡터 기반 점수: visual_sim*0.70 + mood_align*0.20 + naver_rank*0.10
- Gemini bbox 기반 의류 crop + 얼굴 블러
- Naver multi-query (3~5개) + dedupe + exclude=used:rental:cbshop
- SKU 정규화 + 동일 디자인 클러스터링

### 데이터 인프라
- impression 로그 테이블 (session_id 추적)
- 상품 스냅샷 GCS 저장 (Naver URL 만료 대비)
- 학습 파이프라인 스캐폴딩 (training/) — 데이터 1,000건 후 활성화

### 신규 파일
- src/preprocess/gemini_detector.py
- src/pricing/normalize.py
- training/data_curator.py
- training/pair_generator.py
- training/lora_trainer.py (스캐폴드)
- training/evaluator.py (스캐폴드)
- training/README.md

### 배포
- Cloud Run revision: fashion-search-000XX-* ✅
- CF Worker: cloi-api ✅
- CF Pages: https://XXXXXXXX.cloi.pages.dev ✅
```

---

## 4. 작업 순서 (Claude Code 터미널 실행)

순차 실행 (각 Phase 끝나면 git commit):

```bash
# Phase 1: 휴리스틱 제거
# - src/ranking/mood_ranker.py 재작성
# - src/ranking/attribute_classifier.py 수정
# - apps/api/routes_search.py 재랭킹 로직 교체
# - apps/api/schemas.py 필드 변경
git commit -m "feat(ranking): replace heuristic ranker with vector-based v3"

# Phase 2: 학습 데이터 인프라
# - src/storage/user_image_store.py 확장
# - src/logging/search_logger.py impression 추가
# - apps/api/routes_search.py session_id + impression 로깅
# - apps/api/schemas.py session_id 필드
# - cloi/src/services/api.ts session_id 연동
git commit -m "feat(data): add impression log + session snapshot for training pipeline"

# Phase 3: Naver multi-query
# - src/search/parallel_search.py 확장
git commit -m "feat(search): naver multi-query union + dedupe + exclude options"

# Phase 4: Gemini detect
# - src/preprocess/gemini_detector.py 신규
# - apps/api/routes_search.py crop 적용
git commit -m "feat(preprocess): gemini-based bbox detection + face blur + garment crop"

# Phase 5: SKU 정규화
# - src/pricing/normalize.py 신규
# - routes_search.py 클러스터링 적용
git commit -m "feat(pricing): SKU normalization + similar design clustering"

# Phase 6: 학습 파이프라인 스캐폴딩
# - training/ 디렉토리 전체
git commit -m "feat(training): scaffold lora training pipeline (waiting for data)"

# 의존성 + 배포
# - requirements.txt 업데이트
# - deploy.sh 실행
# - wrangler deploy
git commit -m "chore: deploy session 8 — accuracy improvement + training infra"
git push origin main
```

---

## 5. 주의사항

1. **PRICE_TIER_BY_MOOD, MOOD_KEYWORDS 완전히 삭제할 것** — 호환성 유지하지 말고 깨끗이 제거
2. **얼굴 블러 처리는 필수** — GCS 저장 전에 적용 (개인정보 보호)
3. **Cloud Run 메모리 한계 (2Gi)** — Gemini 호출 늘어나도 모델 추가 X
4. **min-instances=0 유지** — Cold start 허용 (비용 절감)
5. **학습 파이프라인은 스캐폴딩만** — 실제 학습은 데이터 1,000+ pair 쌓인 후
6. **Phase 4 (Gemini detect)는 응답 시간 영향 큼** — 병렬 호출 필수, 캐시 적극 활용

---

## 6. 성공 기준

- [ ] SESSION 7 대비 정성 평가 5개 이미지에서 4개 이상 "딱이다" 응답
- [ ] visual_similarity Top-1이 평균 0.65 이상
- [ ] mood_match / price_fit 필드 응답에서 사라짐
- [ ] session_id 응답에 포함, 클릭 시 함께 전송
- [ ] product_impressions 테이블에 레코드 적재 확인
- [ ] GCS sessions/ 경로에 스냅샷 JSON 저장 확인
- [ ] training/ 디렉토리 구조 완성 (스캐폴드)
- [ ] 모든 배포 성공 (Cloud Run + CF Worker + CF Pages)
- [ ] git push 완료

---

## 7. 외부 참고 자료

- Deep Research 보고서: `C:\Users\Alex KIM\Downloads\deep-research-report.md`
  - 적용한 부분: Phase 1 (휴리스틱 제거), Phase 3 (multi-query + exclude), Phase 5 (SKU 정규화), 데이터 수집 합법성
  - 보류한 부분: Grounding DINO/SAM2/PaddleOCR (메모리/PyPI 문제), 600개 gold set (솔로 파운더 비현실), 5개 마이크로서비스 분리 (오버킬), OpenCLIP/SigLIP2 모델 교체 (휴리스틱 제거가 100배 효과 큼)

- 사용자 핵심 요구: "옷들을 벡터 값으로 변환해서 분위기와 스타일을 종합적으로 검증" → Phase 1의 cross-modal mood score로 구현

- 학습 데이터 축적 전략: 일 100건 트래픽 기준 6개월 = 9,000건 → 의미 있는 LoRA 학습 가능

---

## END OF SESSION 8 PROMPT

Claude Code 터미널이 이 파일을 읽고 Phase 1~6을 순서대로 실행하면 됨.
의문점 있으면 작업 시작 전 사용자에게 확인 요청.
