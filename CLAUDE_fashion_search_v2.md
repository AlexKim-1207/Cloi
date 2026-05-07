# 패션 검색 서비스 — Claude Code 구현 가이드 v2

> **이전 문서**: `CLAUDE_fashion_search_optimized.md` (DINO+SAM2+FAISS 기반) → **이 문서로 대체**  
> **이 문서의 아키텍처**: Gemini 전체 스타일 분석 → 네이버쇼핑 병렬 검색 → CLIP 유사도 필터  
> **Claude Code는 이 문서를 읽고 아래 순서대로 구현한다**

---

## 0. 핵심 방향 (3줄 요약)

1. **Gemini가 이미지 전체를 보고 스타일 컨텍스트를 추출한다** (카테고리, 무드, 아이템 목록)
2. **네이버쇼핑 API로 아이템별 병렬 검색한다** (각 아이템 50개씩)
3. **CLIP으로 유저 사진과 시각 유사도를 계산해 무드 안 맞는 것을 제거한다** (최종 카테고리별 TOP 5~10 반환)

---

## 1. 전체 파이프라인

```
유저 이미지 업로드
        │
        ▼
[이미지 해시 캐시 확인] ──HIT──▶ 캐시 결과 반환
        │ MISS
        ▼
[Gemini 2.5 Flash]
  입력: 이미지 전체 (crop 없음)
  출력: StyleContext JSON
    {
      overall_style: "캐주얼 스트릿",
      mood_tags: ["스트릿", "빈티지"],
      items: [
        { category: "후드티", color: "그레이", fit: "오버사이즈" },
        { category: "와이드팬츠", color: "블랙" },
        { category: "스니커즈", color: "화이트" },
        { category: "백팩", color: "블랙" }
      ]
    }
        │
        ▼
[네이버쇼핑 API — 아이템별 병렬 검색]
  asyncio.gather() 로 동시 실행
  쿼리 예시: "캐주얼 스트릿 후드티 그레이 오버사이즈"
  각 아이템당 50개 수집
        │
        ▼
[CLIP — 카테고리별 시각 유사도 필터]
  유저 이미지 1회 인코딩
  각 상품 썸네일 인코딩
  유사도 < threshold 제거 (무드 안 맞는 것 제거)
  예: 캐주얼 무드 vs 명품백 → 제거
        │
        ▼
[카테고리별 TOP 5~10 반환]
  후드티 5개 + 와이드팬츠 5개 + 스니커즈 5개 + 백팩 5개
        │
        ▼
[검색 로그 저장 (SQLite)]
  image_hash, style_context, items_searched,
  results (product_id + 클릭 여부), timestamp
```

---

## 2. 디렉토리 구조

```
fashion-search/
├── CLAUDE.md                   ← 이 파일 복사 (Claude Code 자동 인식)
├── .env.example
├── requirements.txt
│
├── apps/
│   └── api/
│       ├── main.py             ← FastAPI app + lifespan (모델 preload)
│       ├── routes_search.py    ← POST /search, GET /popular
│       └── schemas.py          ← Pydantic 요청/응답 스키마
│
├── src/
│   ├── config/
│   │   └── settings.py         ← Pydantic BaseSettings (.env 로드)
│   │
│   ├── llm/
│   │   ├── gemini_client.py    ← tenacity retry 포함 클라이언트
│   │   └── style_analyzer.py  ← 이미지 → StyleContext JSON 추출
│   │
│   ├── search/
│   │   ├── naver_shopping.py   ← 네이버쇼핑 API 검색 (단일/배치)
│   │   └── parallel_search.py ← asyncio.gather() 아이템별 병렬 검색
│   │
│   ├── ranking/
│   │   └── clip_filter.py     ← CLIP 유사도 계산 + 필터링 + TOP-K 추출
│   │
│   ├── cache/
│   │   └── result_cache.py    ← SQLite image hash → 결과 캐시 (TTL 24h)
│   │
│   └── logging/
│       └── search_logger.py   ← 검색 로그 저장 + 인기 TOP 10 집계
│
├── artifacts/
│   └── search_logs.db         ← SQLite DB (로그 + 인기 집계)
│
└── scripts/
    └── smoke_test.py          ← 전체 파이프라인 latency 테스트
```

---

## 3. 데이터 스키마

### 3.1 Gemini 출력 스키마 (Pydantic)

```python
# src/llm/style_analyzer.py

from pydantic import BaseModel
from typing import Literal

class ItemDetail(BaseModel):
    category: str          # "후드티", "와이드팬츠", "스니커즈", "백팩" 등
    color: str | None = None
    fit: str | None = None
    material: str | None = None

class StyleContext(BaseModel):
    overall_style: str                    # "캐주얼 스트릿", "오피스룩" 등
    mood_tags: list[str]                  # ["스트릿", "빈티지", "루즈핏"]
    items: list[ItemDetail]               # 감지된 아이템 목록
    confidence: float                     # 0.0 ~ 1.0
```

### 3.2 네이버쇼핑 검색 쿼리 생성 규칙

```python
# 쿼리 = overall_style + category + color + fit (있는 것만 조합)
def build_search_query(style: StyleContext, item: ItemDetail) -> str:
    parts = [style.overall_style, item.category]
    if item.color:
        parts.append(item.color)
    if item.fit:
        parts.append(item.fit)
    return " ".join(parts)

# 예: "캐주얼 스트릿 후드티 그레이 오버사이즈"
```

### 3.3 검색 로그 SQLite 스키마

```sql
CREATE TABLE IF NOT EXISTS search_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    image_hash  TEXT NOT NULL,
    style_context TEXT NOT NULL,   -- StyleContext JSON
    items_searched TEXT NOT NULL,  -- ["후드티", "와이드팬츠", ...]
    results     TEXT NOT NULL,     -- [{product_id, category, title, price, click: false}, ...]
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS product_clicks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    image_hash  TEXT NOT NULL,
    product_id  TEXT NOT NULL,
    category    TEXT NOT NULL,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 인기 TOP 10용 집계 뷰
CREATE VIEW IF NOT EXISTS popular_items AS
    SELECT
        category,
        product_id,
        COUNT(*) as search_count,
        SUM(CASE WHEN click = 1 THEN 1 ELSE 0 END) as click_count
    FROM (
        SELECT json_each.value->>'product_id' as product_id,
               json_each.value->>'category' as category,
               json_each.value->>'click' as click
        FROM search_logs, json_each(search_logs.results)
    )
    GROUP BY category, product_id
    ORDER BY click_count DESC;
```

### 3.4 API 응답 스키마

```python
# apps/api/schemas.py

class ProductCard(BaseModel):
    product_id: str
    title: str
    price: int
    image_url: str
    link: str
    platform: str       # "무신사", "에이블리", "지그재그" 등
    category: str
    similarity_score: float

class SearchResponse(BaseModel):
    style_context: StyleContext
    results: dict[str, list[ProductCard]]  # {"후드티": [...], "스니커즈": [...]}
    cached: bool
    latency_ms: int

class PopularItem(BaseModel):
    category: str
    product_id: str
    title: str
    image_url: str
    search_count: int
    click_count: int
    ctr: float          # click_count / search_count
```

---

## 4. 구현 상세

### 4.1 Gemini 스타일 분석 (src/llm/style_analyzer.py)

```python
import os
from google import genai
from google.genai import types
from tenacity import retry, stop_after_attempt, wait_exponential
from .schemas import StyleContext

client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
async def analyze_style(image_bytes: bytes) -> StyleContext:
    """
    이미지 전체를 보고 스타일 컨텍스트 추출.
    crop 없이 전체 이미지 1번만 호출.
    """
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            types.Part.from_text(
                "이 패션 이미지에서 전체 스타일을 분석해줘. "
                "착용된 모든 의류/신발/가방 아이템을 파악하고, "
                "전반적인 스타일 무드와 각 아이템의 속성을 추출해줘. "
                "얼굴, 신체는 무시하고 의류/잡화 아이템에만 집중해."
            ),
            types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
        ],
        config=types.GenerateContentConfig(
            temperature=0,
            response_mime_type="application/json",
            response_schema=StyleContext,
        ),
    )
    return StyleContext.model_validate_json(response.text)
```

### 4.2 네이버쇼핑 병렬 검색 (src/search/parallel_search.py)

```python
import asyncio
import httpx
from ..llm.schemas import StyleContext, ItemDetail
from ..config.settings import settings

async def search_item(client: httpx.AsyncClient, query: str, display: int = 50) -> list[dict]:
    """네이버쇼핑 API 단일 아이템 검색"""
    response = await client.get(
        "https://openapi.naver.com/v1/search/shop.json",
        params={"query": query, "display": display, "sort": "sim"},
        headers={
            "X-Naver-Client-Id": settings.NAVER_CLIENT_ID,
            "X-Naver-Client-Secret": settings.NAVER_CLIENT_SECRET,
        },
    )
    response.raise_for_status()
    return response.json().get("items", [])


async def search_all_items(style: StyleContext) -> dict[str, list[dict]]:
    """
    아이템별 병렬 검색.
    asyncio.gather()로 모든 아이템 동시 검색.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        tasks = {
            item.category: search_item(
                client,
                query=build_search_query(style, item),
                display=50,
            )
            for item in style.items
        }
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)

    return {
        category: result if not isinstance(result, Exception) else []
        for category, result in zip(tasks.keys(), results)
    }


def build_search_query(style: StyleContext, item: ItemDetail) -> str:
    parts = [style.overall_style, item.category]
    if item.color:
        parts.append(item.color)
    if item.fit:
        parts.append(item.fit)
    return " ".join(parts)
```

### 4.3 CLIP 유사도 필터 (src/ranking/clip_filter.py)

```python
import open_clip
import torch
import numpy as np
from PIL import Image
import httpx
import asyncio

# 모델은 앱 시작 시 1회 로드 (lifespan에서)
_model = None
_preprocess = None

def load_clip_model():
    global _model, _preprocess
    model, _, preprocess = open_clip.create_model_and_transforms(
        "ViT-L-14", pretrained="laion2b_s32b_b82k"
    )
    model.eval()
    _model = model
    _preprocess = preprocess


def encode_image(image: Image.Image) -> np.ndarray:
    """PIL Image → 정규화된 벡터"""
    tensor = _preprocess(image).unsqueeze(0)
    with torch.no_grad():
        features = _model.encode_image(tensor)
        features /= features.norm(dim=-1, keepdim=True)
    return features.cpu().numpy()[0]


async def download_thumbnail(url: str) -> Image.Image | None:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(url)
            from io import BytesIO
            return Image.open(BytesIO(r.content)).convert("RGB")
    except Exception:
        return None


async def filter_by_similarity(
    query_vector: np.ndarray,
    products: list[dict],
    top_k: int = 5,
    min_similarity: float = 0.20,
) -> list[dict]:
    """
    유저 이미지 벡터와 각 상품 썸네일 유사도 계산.
    min_similarity 미만 제거 후 top_k 반환.
    """
    # 썸네일 병렬 다운로드
    thumbnails = await asyncio.gather(*[
        download_thumbnail(p.get("image", "")) for p in products
    ])

    scored = []
    for product, thumb in zip(products, thumbnails):
        if thumb is None:
            continue
        product_vector = encode_image(thumb)
        similarity = float(np.dot(query_vector, product_vector))
        if similarity >= min_similarity:
            scored.append({**product, "similarity_score": similarity})

    # 유사도 높은 순 정렬 후 top_k 반환
    scored.sort(key=lambda x: x["similarity_score"], reverse=True)
    return scored[:top_k]


async def rank_all_categories(
    query_image: Image.Image,
    search_results: dict[str, list[dict]],
    top_k: int = 5,
) -> dict[str, list[dict]]:
    """
    카테고리별 CLIP 필터링.
    쿼리 이미지는 1번만 인코딩.
    """
    query_vector = encode_image(query_image)

    tasks = {
        category: filter_by_similarity(query_vector, products, top_k)
        for category, products in search_results.items()
        if products
    }
    results = await asyncio.gather(*tasks.values())

    return dict(zip(tasks.keys(), results))
```

### 4.4 메인 검색 엔드포인트 (apps/api/routes_search.py)

```python
import time
import hashlib
from fastapi import APIRouter, UploadFile, File, HTTPException
from PIL import Image
from io import BytesIO

from src.llm.style_analyzer import analyze_style
from src.search.parallel_search import search_all_items
from src.ranking.clip_filter import rank_all_categories
from src.cache.result_cache import get_cached, set_cached
from src.logging.search_logger import log_search
from .schemas import SearchResponse

router = APIRouter()


@router.post("/search", response_model=SearchResponse)
async def search(file: UploadFile = File(...)):
    start = time.monotonic()

    image_bytes = await file.read()
    image_hash = hashlib.sha256(image_bytes).hexdigest()

    # 1. 캐시 확인
    cached = await get_cached(image_hash)
    if cached:
        return {**cached, "cached": True, "latency_ms": 0}

    # 2. Gemini 스타일 분석
    style_context = await analyze_style(image_bytes)

    # 3. 네이버쇼핑 병렬 검색
    raw_results = await search_all_items(style_context)

    # 4. CLIP 유사도 필터 (카테고리별 TOP 5)
    image = Image.open(BytesIO(image_bytes)).convert("RGB")
    ranked_results = await rank_all_categories(image, raw_results, top_k=5)

    latency_ms = int((time.monotonic() - start) * 1000)

    # 5. 검색 로그 저장
    await log_search(image_hash, style_context, ranked_results)

    # 6. 캐시 저장
    response = SearchResponse(
        style_context=style_context,
        results=ranked_results,
        cached=False,
        latency_ms=latency_ms,
    )
    await set_cached(image_hash, response)

    return response


@router.post("/search/{image_hash}/click/{product_id}")
async def record_click(image_hash: str, product_id: str, category: str):
    """상품 클릭 이벤트 기록"""
    from src.logging.search_logger import log_click
    await log_click(image_hash, product_id, category)
    return {"ok": True}


@router.get("/popular")
async def get_popular(category: str | None = None, limit: int = 10):
    """인기 TOP 10 반환 (클릭률 기준)"""
    from src.logging.search_logger import get_popular_items
    return await get_popular_items(category=category, limit=limit)
```

### 4.5 FastAPI 앱 + 모델 preload (apps/api/main.py)

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from src.ranking.clip_filter import load_clip_model
from src.cache.result_cache import init_cache
from src.logging.search_logger import init_db
from .routes_search import router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 시작 시 1회 로드 (요청 시 lazy load 금지)
    load_clip_model()
    await init_cache()
    await init_db()
    yield
    # 종료 시 정리 (필요 시)

app = FastAPI(title="패션 검색 API", lifespan=lifespan)
app.include_router(router)
```

---

## 5. 환경 설정

### requirements.txt
```
fastapi==0.115.0
uvicorn[standard]==0.30.0
pillow==10.4.0
numpy==1.26.4
pydantic==2.7.0
pydantic-settings==2.3.0
python-dotenv==1.0.1
python-multipart==0.0.9
httpx==0.27.0
open_clip_torch==2.26.1
google-genai==1.0.0
tenacity==8.3.0
aiofiles==23.2.1
aiosqlite==0.20.0
```

### .env.example
```bash
# Gemini
GOOGLE_API_KEY=your_gemini_key

# 네이버 검색 API
NAVER_CLIENT_ID=your_naver_client_id
NAVER_CLIENT_SECRET=your_naver_client_secret

# CLIP
CLIP_MODEL=ViT-L-14
CLIP_PRETRAINED=laion2b_s32b_b82k
CLIP_MIN_SIMILARITY=0.20

# 검색
SEARCH_RESULTS_PER_ITEM=50
TOP_K_PER_CATEGORY=5

# 캐시
CACHE_TTL_HOURS=24

# DB
DB_PATH=artifacts/search_logs.db
```

---

## 6. Claude Code 구현 프롬프트 순서

### 프롬프트 1 — 프로젝트 골격 (Day 1)
```text
이 저장소는 패션 이미지 업로드 → Gemini 스타일 분석 → 네이버쇼핑 병렬 검색 → CLIP 필터 → TOP 5 반환하는 서비스다.
CLAUDE.md를 읽었다면, 아래 파일을 생성해줘. 함수 시그니처와 TODO 주석 포함, import 오류 없게.

- src/config/settings.py          (Pydantic BaseSettings)
- apps/api/schemas.py              (StyleContext, ProductCard, SearchResponse, PopularItem)
- apps/api/main.py                 (lifespan으로 CLIP 모델 preload)
- src/llm/style_analyzer.py        (Gemini → StyleContext, tenacity retry)
- src/search/naver_shopping.py     (단일 아이템 검색)
- src/search/parallel_search.py    (asyncio.gather 병렬 검색)
- src/ranking/clip_filter.py       (CLIP 인코딩 + 유사도 필터)
- src/cache/result_cache.py        (SQLite image hash 캐시)
- src/logging/search_logger.py     (검색 로그 + 클릭 기록 + 인기 집계)
- apps/api/routes_search.py        (POST /search, POST /click, GET /popular)
```

### 프롬프트 2 — 핵심 로직 구현 (Day 2)
```text
style_analyzer.py, parallel_search.py, clip_filter.py 함수를 완전히 구현해줘.
- style_analyzer: CLAUDE.md의 Gemini 코드 예시 그대로 구현
- parallel_search: build_search_query 포함, 예외 발생 시 빈 리스트 반환
- clip_filter: 썸네일 병렬 다운로드 + encode + cosine 유사도 계산
CLIP 모델은 앱 시작 시 이미 로드된 글로벌 인스턴스를 사용할 것.
```

### 프롬프트 3 — DB + 캐시 + 라우터 완성 (Day 3)
```text
아래를 완성해줘.

result_cache.py:
- init_cache(): artifacts/search_logs.db에 캐시 테이블 생성
- get_cached(image_hash): TTL 24시간 체크
- set_cached(image_hash, response): JSON 직렬화 저장

search_logger.py:
- init_db(): search_logs, product_clicks 테이블 + popular_items 뷰 생성
- log_search(image_hash, style_context, results): 검색 기록 저장
- log_click(image_hash, product_id, category): 클릭 기록
- get_popular_items(category, limit): 클릭률 기준 인기 상품 반환

routes_search.py:
- CLAUDE.md의 코드 예시 그대로 구현
```

### 프롬프트 4 — 스모크 테스트 (Day 4)
```text
scripts/smoke_test.py를 만들어줘.
테스트 이미지 1장으로 전체 파이프라인 실행하고 각 단계 latency를 출력해.
목표 latency:
- Gemini 분석: 3초 이내
- 네이버쇼핑 병렬 검색 (4개 아이템): 2초 이내
- CLIP 필터 (200개 썸네일): 5초 이내
- 전체 파이프라인: 10초 이내
```
extract(r_each.value, '$') r
    LEFT JOIN product_clicks pc
        ON pc.product_id = json_extract(r_each.value, '$.product_id')
        AND pc.image_hash = sl.image_hash
    WHERE COUNT(DISTINCT sl.id) >= 3
    """
    if category:
        query += f" AND json_extract(r_each.value, '$.category') = ?"
    query += " GROUP BY r.product_id ORDER BY ctr DESC, search_count DESC LIMIT ?"
    ...
```

---

## 9. Gemini API 비용 관리

| 조건 | Gemini 호출 여부 |
|------|-----------------|
| 캐시 HIT | ❌ 호출 안 함 |
| 동일 image_hash | ❌ 호출 안 함 |
| 신규 이미지 | ✅ 1회 호출 |

**예상 비용**: Gemini 2.5 Flash 이미지 1장당 약 $0.0003~0.001  
DAU 1,000명 기준 일 $0.3~1.0 예상 (캐시 히트율에 따라 달라짐)

---

## 10. 지금 당장 할 것 (착수 체크리스트)

- [ ] `GOOGLE_API_KEY` 발급 → `.env`에 저장
- [ ] 네이버 개발자 센터 검색 API 신청 → https://developers.naver.com/apps/#/register
- [ ] `mkdir fashion-search && cd fashion-search` 후 `claude` 실행
- [ ] 이 파일 내용을 `CLAUDE.md`로 복사 후 프롬프트 1 실행

---

*이 문서는 `fashion_search_claude_code_playbook.md`의 신규 아키텍처(Gemini + 네이버쇼핑 + CLIP) 구현 가이드입니다.*  
*이전 DINO+SAM2+FAISS 기반 문서는 `CLAUDE_fashion_search_optimized.md` 참조.*  
*최종 업데이트: 2026-04-22*
