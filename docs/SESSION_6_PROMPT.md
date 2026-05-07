# SESSION 6 — Cloi 정확도 +30~40% 향상 작업 지시서

CLAUDE.md 규칙 준수. 아래를 연구하고 설계하고 구현하고 배포까지 완료하라.

목표: Cloi 패션 이미지 검색 서비스 정확도 +30~40% 향상.
고객 와우포인트 = (1) 사진 속 모든 아이템 탭별 추천, (2) 첫 화면에 가장 유사하고 가격 적절한 상품, (3) 분위기 매칭.

---

## 핵심 설계 철학

### 역할 분리
- FashionCLIP = 시각 속성 담당 (zero-shot 분류)
- Gemini 2.5 Flash = 언어/맥락/검색쿼리 생성 담당
- 둘이 각자 잘하는 것만 하게 분리하면 정확도 ↑

### 멀티 아이템 탐지 (가장 중요)
사진에 보이는 모든 착장 아이템을 개별로 탐지:
- 상의 / 이너 / 아우터 / 하의 / 가방 / 신발 / 액세서리(반지/귀걸이/목걸이/벨트/모자/시계) 전부
- 각 아이템 = 별도 탭 = 개별 검색 + 추천
- 유저는 탭 전환으로 원하는 아이템만 골라서 봄

### 복합 소팅
final_score = clip_sim*0.45 + mood_match*0.30 + price_fit*0.25
1순위 = 시각 유사도 높고 + 분위기 맞고 + 가격대 적절
가격 분포 = 추출된 price_tier 기준으로 정규분포 점수화

### 자기학습 루프
유저 이미지 → GCS 저장 → 클릭 데이터 → 향후 FashionCLIP 파인튜닝 데이터셋

---

## 서비스 현황
- Cloud Run: https://fashion-search-dibvogjuma-du.a.run.app
- CF Worker: https://cloi-api.kyoung361207.workers.dev
- CF Pages: https://cloi.pages.dev
- GCP 프로젝트: cloi-fashion-search
- 우승 모델: fashion_clip (Recall@10=0.88, 파인튜닝 후 1.0)

---

## STEP 1: 현재 코드 완전 파악 (읽기만)

다음 파일 전부 정독:
- fashion-search/src/llm/style_analyzer.py
- fashion-search/apps/api/routes_search.py
- fashion-search/apps/api/main.py
- fashion-search/apps/api/schemas.py
- fashion-search/src/ranking/clip_filter.py
- fashion-search/src/search/parallel_search.py
- fashion-search/src/search/naver_shopping.py
- fashion-search/src/embedding/fashion_clip_embedder.py
- fashion-search/src/cache/result_cache.py
- fashion-search/src/logging/search_logger.py
- fashion-search/src/config/settings.py
- fashion-search/requirements.txt
- server/src/worker.ts
- server/src/routes/analyze.ts
- src/pages/ResultPage.tsx
- src/pages/HomePage.tsx
- src/services/api.ts
- src/types/index.ts

현재 구조 파악 후 수정 계획을 docs/STEP1_analysis.md에 기록 (간단하게).

---

## STEP 2: FashionCLIP Zero-shot 속성 분류기 신규 구현

파일: `fashion-search/src/ranking/attribute_classifier.py` (신규)

목적: FashionCLIP 텍스트 인코더로 시각 속성을 직접 판단. Gemini 텍스트 추론보다 정확.

```python
from typing import Dict, List, Tuple
import numpy as np
import torch
from PIL import Image
from src.embedding.fashion_clip_embedder import FashionCLIPEmbedder

NECKLINE_OPTIONS = [
    'v-neck top', 'round neck top', 'turtleneck sweater',
    'off-shoulder top', 'square neck top', 'collared shirt',
    'henley neck top', 'crew neck'
]
FIT_OPTIONS = [
    'oversized loose fit clothing', 'slim fit clothing',
    'regular fit clothing', 'cropped fit top', 'boxy fit'
]
SLEEVE_OPTIONS = [
    'short sleeve', 'long sleeve', 'sleeveless',
    'three quarter sleeve', 'puff sleeve'
]
MATERIAL_OPTIONS = [
    'cable knit sweater', 'denim', 'linen fabric', 'chiffon',
    'leather', 'cotton', 'satin', 'wool', 'tweed', 'lace'
]
PATTERN_OPTIONS = [
    'solid color', 'striped pattern', 'floral pattern',
    'check pattern', 'graphic print', 'animal print'
]
BAG_OPTIONS = [
    'chain shoulder bag', 'tote bag', 'crossbody bag',
    'clutch bag', 'backpack', 'mini bag', 'bucket bag'
]
SHOE_OPTIONS = [
    'sneakers', 'heels', 'loafers', 'boots',
    'sandals', 'flats', 'mules'
]
MOOD_OPTIONS = [
    'luxury fashion editorial elegant',
    'casual street style daily',
    'minimal office professional clean',
    'sporty athletic wear',
    'feminine romantic look',
    'vintage retro style',
    'y2k playful trendy',
    'classic timeless preppy'
]
PRICE_TIER_BY_MOOD = {
    'luxury fashion editorial elegant': ('luxury', 200000, 9999999),
    'casual street style daily': ('budget', 10000, 60000),
    'minimal office professional clean': ('mid', 40000, 150000),
    'sporty athletic wear': ('mid', 20000, 100000),
    'feminine romantic look': ('mid', 20000, 120000),
    'vintage retro style': ('budget', 15000, 80000),
    'y2k playful trendy': ('budget', 10000, 70000),
    'classic timeless preppy': ('mid', 50000, 200000),
}

class AttributeClassifier:
    def __init__(self, embedder: FashionCLIPEmbedder):
        self.embedder = embedder
        self._text_cache: Dict[str, np.ndarray] = {}

    def _encode_texts(self, texts: List[str]) -> np.ndarray:
        key = '||'.join(texts)
        if key not in self._text_cache:
            self._text_cache[key] = self.embedder.encode_text(texts)
        return self._text_cache[key]

    def _top_k(self, image_emb: np.ndarray, options: List[str], k: int = 1) -> List[Tuple[str, float]]:
        text_embs = self._encode_texts(options)
        scores = (image_emb @ text_embs.T).flatten()
        top_idx = scores.argsort()[::-1][:k]
        return [(options[i], float(scores[i])) for i in top_idx]

    def classify_all(self, image: Image.Image) -> Dict:
        image_emb = self.embedder.embed_single(image)
        if image_emb.ndim == 1:
            image_emb = image_emb[np.newaxis, :]

        mood_top = self._top_k(image_emb, MOOD_OPTIONS, k=1)[0]
        tier_name, low, high = PRICE_TIER_BY_MOOD[mood_top[0]]

        return {
            'neckline': self._top_k(image_emb, NECKLINE_OPTIONS, k=1)[0][0],
            'fit': self._top_k(image_emb, FIT_OPTIONS, k=1)[0][0],
            'sleeve': self._top_k(image_emb, SLEEVE_OPTIONS, k=1)[0][0],
            'material': self._top_k(image_emb, MATERIAL_OPTIONS, k=2),
            'pattern': self._top_k(image_emb, PATTERN_OPTIONS, k=1)[0][0],
            'mood': mood_top[0],
            'mood_confidence': mood_top[1],
            'price_tier': tier_name,
            'price_range': (low, high),
        }
```

`FashionCLIPEmbedder`에 `encode_text` 메서드 없으면 추가 (open_clip 또는 transformers 텍스트 인코더 활용).

---

## STEP 3: Gemini 프롬프트 강화 - 멀티 아이템 탐지 (핵심)

파일: `fashion-search/src/llm/style_analyzer.py` 수정

Gemini가 사진 속 모든 아이템을 개별로 탐지하게 함.

새 출력 스키마:
```json
{
  "overall_style_context": "미니멀 캐주얼 레이어드 룩",
  "detected_items": [
    {
      "tab_id": "top_outer",
      "category": "top",
      "subcategory": "knit_vest",
      "description": "베이지 케이블 니트 베스트, 오버핏",
      "is_inner": false,
      "searchQueries": ["베이지 케이블 니트 베스트 여성", "오버핏 니트조끼", "니트 베스트 여자"]
    },
    {
      "tab_id": "top_inner",
      "category": "top",
      "subcategory": "shirt",
      "description": "화이트 오버사이즈 셔츠",
      "is_inner": true,
      "searchQueries": ["화이트 오버사이즈 셔츠 여성", "루즈핏 셔츠", "화이트 셔츠 데일리"]
    },
    {
      "tab_id": "bag",
      "category": "bag",
      "subcategory": "crossbody",
      "description": "베이지 퀼팅 체인 크로스백",
      "is_inner": false,
      "searchQueries": ["베이지 퀼팅 체인백", "크로스백 미니", "체인 숄더백"]
    }
  ]
}
```

탭 ID 규칙:
- `top_outer` / `top_inner` / `outer` / `bottom` / `dress` / `shoes`
- `bag` / `accessory_ring` / `accessory_necklace` / `accessory_earring` / `accessory_belt` / `accessory_hat` / `accessory_watch`

Gemini 프롬프트 핵심 지시:
- 사진에서 보이는 아이템 모두 분리 탐지
- 같은 카테고리라도 레이어드면 별도 아이템 (예: 니트 베스트 + 셔츠)
- 액세서리 종류별 개별 탐지 (반지/귀걸이/목걸이/벨트 등)
- 각 아이템에 한국어 검색에 자연스러운 searchQueries 3개씩
- description은 색상+소재+핏+세부디테일 모두 포함

---

## STEP 4: 복합 소팅 모듈 신규 구현

파일: `fashion-search/src/ranking/mood_ranker.py` (신규)

```python
import re
from typing import Tuple, List, Dict

def price_fit_score(product_price: int, price_range: Tuple[int, int]) -> float:
    if product_price is None or product_price <= 0:
        return 0.5
    low, high = price_range
    if low <= product_price <= high:
        return 1.0
    elif product_price < low:
        ratio = (low - product_price) / max(low, 1)
        return max(0.3, 1 - ratio * 0.7)
    else:
        ratio = (product_price - high) / max(high, 1)
        return max(0.1, 1 - ratio * 0.5)

def mood_match_score(product_title: str, mood_keywords: List[str]) -> float:
    if not product_title:
        return 0.5
    title_lower = product_title.lower()
    hits = sum(1 for kw in mood_keywords if kw.lower() in title_lower)
    return min(1.0, 0.5 + hits * 0.15)

MOOD_KEYWORDS = {
    'luxury': ['프리미엄', '럭셔리', '명품', '하이엔드', 'luxury', 'premium'],
    'casual': ['데일리', '캐주얼', 'casual', '베이직'],
    'office': ['오피스', '정장', '포멀', 'office', '클래식'],
    'sporty': ['스포츠', '액티브', '트레이닝', 'sport'],
    'feminine': ['페미닌', '러블리', '로맨틱', '걸리시'],
    'vintage': ['빈티지', '레트로', 'vintage', 'retro'],
    'y2k': ['y2k', '트렌디', '힙'],
    'classic': ['클래식', '베이직', 'classic'],
}

def get_mood_keywords(mood_label: str) -> List[str]:
    for key, kws in MOOD_KEYWORDS.items():
        if key in mood_label.lower():
            return kws
    return []

def compute_final_score(clip_sim: float, mood: float, price_fit: float) -> float:
    return clip_sim * 0.45 + mood * 0.30 + price_fit * 0.25

def rank_products(
    products: List[Dict],
    clip_scores: Dict[str, float],
    mood_label: str,
    price_range: Tuple[int, int],
    sort_by: str = 'relevance',
) -> List[Dict]:
    mood_kws = get_mood_keywords(mood_label)

    for p in products:
        clip = clip_scores.get(p.get('id', ''), 0.5)
        mood_score = mood_match_score(p.get('title', ''), mood_kws)
        pfit = price_fit_score(p.get('price', 0), price_range)
        p['_clip_sim'] = clip
        p['_mood_match'] = mood_score
        p['_price_fit'] = pfit
        p['match_score'] = compute_final_score(clip, mood_score, pfit)

    if sort_by == 'price_asc':
        return sorted(products, key=lambda x: (x.get('price', 999999999), -x['match_score']))
    elif sort_by == 'price_desc':
        return sorted(products, key=lambda x: (-x.get('price', 0), -x['match_score']))
    else:
        return sorted(products, key=lambda x: (-x['match_score'], x.get('price', 999999999)))
```

---

## STEP 5: GCS 유저 이미지 저장 + 임베딩 저장

파일: `fashion-search/src/storage/user_image_store.py` (신규)

```python
import io
import json
from datetime import datetime
from typing import Optional

try:
    from google.cloud import storage
    GCS_AVAILABLE = True
except ImportError:
    GCS_AVAILABLE = False

class UserImageStore:
    def __init__(self, bucket_name: str = 'cloi-user-images'):
        self.enabled = GCS_AVAILABLE
        if not self.enabled:
            return
        try:
            self.client = storage.Client()
            self.bucket = self.client.bucket(bucket_name)
        except Exception:
            self.enabled = False

    async def save_async(
        self,
        image_bytes: bytes,
        image_hash: str,
        style_context: dict,
        attributes: dict,
        clip_embedding: Optional[list] = None,
    ) -> Optional[str]:
        if not self.enabled:
            return None
        try:
            now = datetime.utcnow()
            prefix = f'user-images/{now.year}/{now.month:02d}/{now.day:02d}'

            img_blob = self.bucket.blob(f'{prefix}/{image_hash}.jpg')
            img_blob.upload_from_string(image_bytes, content_type='image/jpeg')

            meta = {
                'hash': image_hash,
                'timestamp': now.isoformat(),
                'style_context': style_context,
                'attributes': attributes,
                'embedding': clip_embedding,
            }
            meta_blob = self.bucket.blob(f'{prefix}/{image_hash}.json')
            meta_blob.upload_from_string(json.dumps(meta, ensure_ascii=False), content_type='application/json')

            return f'gs://cloi-user-images/{prefix}/{image_hash}.jpg'
        except Exception:
            return None
```

`requirements.txt`에 추가: `google-cloud-storage==2.18.0`

---

## STEP 6: 클릭 피드백 수집 강화

파일: `fashion-search/src/logging/search_logger.py` 수정

기존 click 로그 스키마에 컬럼 추가:
- `image_hash TEXT`
- `clicked_product_title TEXT`
- `clicked_product_image_url TEXT`
- `clicked_product_price INTEGER`
- `final_score REAL`
- `rank_position INTEGER`
- `mood_label TEXT`
- `price_tier TEXT`

데이터베이스 마이그레이션 코드 추가 (`CREATE TABLE IF NOT EXISTS` + `ALTER TABLE`).

이 데이터가 향후 파인튜닝 positive pair로 사용됨:
- (image_hash → clicked_product_image) 쌍이 contrastive learning의 positive

---

## STEP 7: routes_search.py 전면 재구성

새 파이프라인:
```python
@router.post('/search')
async def search(file: UploadFile = File(...), sort_by: str = 'relevance'):
    # 1. 이미지 읽기 + hash 계산
    # 2. 캐시 조회 (sort_by 다르면 재정렬만)
    # 3. 병렬 실행:
    #    a. style_analyzer.analyze_style(image) -> Gemini 분석 (detected_items)
    #    b. attribute_classifier.classify_all(image) -> FashionCLIP 속성
    # 4. detected_items 각각에 대해:
    #    - searchQueries로 네이버 병렬 검색 (parallel_search)
    #    - 검색 결과 이미지 임베딩 + clip_sim 계산
    #    - mood_ranker.rank_products(sort_by 적용)
    # 5. 응답 구조:
    #    {
    #      'image_hash': '...',
    #      'overall_style': '...',
    #      'attributes': {neckline, fit, mood, price_tier, ...},
    #      'tabs': [
    #        {tab_id, label, items: [ProductCard, ...]},
    #      ]
    #    }
    # 6. asyncio.create_task(user_image_store.save_async(...))  # fire-and-forget
    # 7. 캐시 저장
    # 8. 응답 반환
```

---

## STEP 8: schemas.py 재정의

```python
class ProductCard(BaseModel):
    id: str
    title: str
    image: str
    price: Optional[int]
    link: str
    mall_name: Optional[str]
    match_score: float
    clip_similarity: float
    mood_match: float
    price_fit: float

class TabSection(BaseModel):
    tab_id: str
    label: str
    description: str
    items: List[ProductCard]

class SearchResponse(BaseModel):
    image_hash: str
    overall_style: str
    detected_attributes: dict
    tabs: List[TabSection]
    total_latency_ms: int
    cache_hit: bool
```

---

## STEP 9: CF Worker 수정

파일: `server/src/worker.ts`, `server/src/routes/analyze.ts`

- `/api/search` 라우트: `sort_by` 쿼리파라미터 받아서 Cloud Run에 그대로 전달
- `/api/click` 라우트 강화: `image_hash`, `rank_position`, `match_score` 받아서 Cloud Run `/click`에 전달
- 새 응답 스키마(tabs 구조) 그대로 프론트에 전달

---

## STEP 10: 프론트엔드 - 탭 UI + 소팅 토글

`src/types/index.ts`:
- `ProductCard`, `TabSection`, `SearchResponse` 타입 추가

`src/services/api.ts`:
- `search(file, sortBy?: 'relevance' | 'price_asc' | 'price_desc')`

`src/pages/ResultPage.tsx` 전면 개편:
- 상단: detected_attributes 표시 (분위기 뱃지 + 추천 가격대)
- 탭 네비게이션: tabs 배열을 가로 스크롤 탭으로 (니트/이너/하의/가방/반지 등)
- 탭별 컨텐츠: 상품 카드 그리드
- 각 카드: match_score 뱃지 (매칭 92% 형태) + 가격 + 상품명
- 첫 번째 카드: 하이라이트 (테두리/배지/약간 큰 사이즈)
- 소팅 토글 버튼: [유사도순] [낮은가격순] [높은가격순]
- 카드 클릭 시 `/api/click`에 image_hash, rank_position, match_score 전송

`src/pages/HomePage.tsx`: 소팅 옵션 안내 문구 추가 (선택)

스타일은 기존 디자인 시스템 유지.

---

## STEP 11: deploy.sh GCS 권한 추가

deploy.sh에 추가:
```bash
# GCS 버킷 생성 (이미 있으면 무시)
gsutil mb -p "${PROJECT_ID}" -l asia-northeast3 gs://cloi-user-images 2>/dev/null || true

# Cloud Run 서비스 계정에 storage.objectAdmin 권한 부여
PROJECT_NUMBER=$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role="roles/storage.objectAdmin" \
  --condition=None 2>/dev/null || true
```

---

## STEP 12: E2E 테스트 (필수)

`fashion-search/scripts/integration_test_v2.py` 신규 생성.

테스트 케이스:
1. 단일 아이템 (니트만): tabs 1개, 정상 응답
2. 멀티 아이템 (니트+셔츠+가방+반지): tabs 4개+, 각 탭에 5개 이상
3. 레이어드 룩 (이너 감지): top_outer + top_inner 탭 분리 확인
4. 럭셔리 룩: mood=luxury, 추천 상품 가격대 비싼 쪽
5. 캐주얼 룩: mood=casual, 추천 상품 가격대 저렴한 쪽
6. 소팅 테스트: relevance vs price_asc vs price_desc 순서 다름 확인
7. GCS 저장 확인: `gsutil ls gs://cloi-user-images/` 로 파일 생성 확인

`eval/queries/` 에서 5장 골라서 실행. p50 < 5초 목표.

---

## STEP 13: 배포 (순서 엄수)

```bash
# 1. Cloud Run 재배포
export GCP_PROJECT_ID=cloi-fashion-search
bash fashion-search/deploy.sh

# 2. CF Worker 재배포
cd server && npx wrangler deploy && cd ..

# 3. CF Pages 재배포
npm run build && npx wrangler pages deploy dist --project-name=cloi
```

배포 후 검증:
- `curl https://fashion-search-dibvogjuma-du.a.run.app/health`
- `curl -X POST https://cloi-api.kyoung361207.workers.dev/api/search -F file=@테스트이미지.jpg`
- https://cloi.pages.dev 브라우저 확인

---

## STEP 14: git commit + push

```bash
git add -A
git commit -m "feat: 멀티아이템 탐지 + FashionCLIP 속성추출 + 무드기반 소팅 + 유저이미지 수집"
git push origin main
```

---

## STEP 15: SESSION_STATUS.md 업데이트 + 알람 (반드시)

SESSION 6 완료 항목 기록:
- 변경된 파일 목록
- 추가된 기능
- 측정된 latency / 정확도
- GCS 버킷 활성 여부
- 배포 URL

알람 실행:
```bash
/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe -ExecutionPolicy Bypass -File "/c/Users/Alex KIM/Desktop/사업 프로젝트/인앱토스 1/.claude/session-done.ps1"
```

---

## 절대 원칙 (위반 금지)

1. Gemini 모델 = `gemini-2.5-flash` 고정
2. FashionCLIP 인스턴스는 lifespan에서 로드된 것만 재사용 (새로 만들지 말 것)
3. `/api/search` 응답이 변경되므로 프론트도 동시에 수정 필수
4. 네이버 API 결과 0개일 때 fallback 로직 건드리지 말 것
5. GCS 저장은 fire-and-forget. 실패해도 검색 응답 막지 말 것
6. `google-cloud-storage` import 실패 시 조용히 disable
7. 캐시 키에 sort_by 포함하지 말 것 (캐시 후 재정렬)
8. 탭 ID는 영문 snake_case, 표시 라벨은 한국어
9. 액세서리는 종류별 개별 탭 (반지/목걸이/귀걸이 합치지 말 것)
10. CLAUDE.md 토큰 절약 규칙 준수 (Grep 우선, 병렬 도구 호출, 재읽기 금지)

---

## 산출물 요약

신규 파일:
- `fashion-search/src/ranking/attribute_classifier.py`
- `fashion-search/src/ranking/mood_ranker.py`
- `fashion-search/src/storage/user_image_store.py`
- `fashion-search/scripts/integration_test_v2.py`
- `docs/STEP1_analysis.md`

수정 파일:
- `fashion-search/src/llm/style_analyzer.py`
- `fashion-search/apps/api/routes_search.py`
- `fashion-search/apps/api/schemas.py`
- `fashion-search/src/embedding/fashion_clip_embedder.py` (encode_text 추가)
- `fashion-search/src/logging/search_logger.py`
- `fashion-search/requirements.txt`
- `fashion-search/deploy.sh`
- `server/src/worker.ts`
- `server/src/routes/analyze.ts`
- `src/pages/ResultPage.tsx`
- `src/services/api.ts`
- `src/types/index.ts`
- `SESSION_STATUS.md`

배포 완료:
- Cloud Run / CF Worker / CF Pages 전부
- GCS 버킷 `cloi-user-images` 활성화
