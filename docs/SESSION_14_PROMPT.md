# SESSION 14: Deep Research Report 전면 적용 — 의류 전처리 + LTR Reranker + SKU/가격 + Gold Set + 임베딩 비교 + 법률 준수

> **출처:** `uploads/deep-research-report (1).md` — 한국 2030 여성 패션 검색 서비스 개선 보고서 (Wiseapp 데이터, 한국 저작권법, Naver API 공식 문서, Grounding DINO/SAM 2/SigLIP2 논문 등 인용)
>
> **선행 필독:**
> - `uploads/deep-research-report (1).md` (보고서 원문 — 모든 수치/근거)
> - 갱신된 `CLAUDE.md` "🚀 배포 검증 규칙" 섹션
> - `scripts/verify_deploy.sh` (Pages 배포 검증 도구)
>
> **본질 원칙 (보고서 결론 한 줄):**
> **"CLIP 튜닝이 아니라, 휴리스틱 제거 → 의류 crop/masking → 다단계 candidate retrieval → LTR reranker → SKU/가격 정규화. LoRA나 Adapter는 그다음."**
>
> **사용자 호소 매핑:**
> 1. "체크 셔츠인데 단색 결과" → Track A (의류 전처리) + Track B (LTR reranker)
> 2. "미니 쇼츠인데 칠부 결과" → Track A + Track B
> 3. "이너 반팔/민소매 모호" → Track A (Grounding DINO open-vocabulary detection)
> 4. "cropped 셀카 outer/bottom 누락" → Track A (전처리로 자동 해결)
> 5. "회색 니트 가방 200만원 / 남자 목걸이" → Track C (SKU matcher + 가격 정규화)
>
> **이미 완료된 것 (skip):**
> - mood/price 휴리스틱 제거 (SESSION 10) ✅
> - 8키 schema + 색상/패턴/길이 신호 (SESSION 11/12/13) ✅
> - 네이버 multi-query + dedupe (SESSION 11) ✅
> - softScoreProducts (SESSION 12) ✅
>
> **이 세션 작업 (보고서 P0~P2 전부):**
> Track A → G

---

## 0. 절대 원칙

1. **deploy 명령 ≠ production 적용.** `wrangler pages deploy dist` + `bash scripts/verify_deploy.sh` exit 0 만이 진짜 완료.
2. **각 Track 끝나면 git commit.** 회귀 시 정확한 revert 가능.
3. **Hard reject 금지 — soft signal로만.** 모든 신호는 confidence-weighted multiplier.
4. **위험 발견 시 깨끗하게 종료.** 무한 루프 X. `logs/overnight_log` 에 상태 기록.
5. **법적 데이터 원천 준수.** 경쟁사 무단 수집 금지. opt-in/제휴/사용자 동의만.
6. **시간 부족 시 P0 우선.** P1/P2는 SESSION_STATUS.md 에 정직하게 "다음 세션" 표기.

---

## STEP 0 — Deploy 진단 (가장 먼저)

```bash
cd "C:\Users\Alex KIM\Desktop\사업 프로젝트\인앱토스 1"

# 0-1. 현재 production 응답 baseline
bash scripts/verify_deploy.sh fashion-search/eval/queries/q001.jpg
# 기대: exit 0, _source 응답, 8키 schema, gender/price_tier 응답
# 실패 시: 0-2 진행

# 0-2. Pages 재배포 (SESSION 11~13 코드 진짜 진입 확인)
npm run build
npx wrangler pages deploy dist --project-name=cloi
sleep 30
bash scripts/verify_deploy.sh
# Exit 0 안 나오면 진단 후 재시도
```

---

## Track A — 의류 전처리 (P0, 가장 큰 임팩트)

> **보고서 인용 (가장 강한 한 줄):**
> "검색 정확도에서 가장 큰 1차 개선은 이미지 입력을 '스크린샷'에서 '의류 조각들'로 바꾸는 것"
>
> **사용자 호소 직접 해결:**
> - cropped 셀카 → 의류만 잘라서 분석 → outer/bottom 누락 사라짐
> - 얼굴/배경 노이즈 → 마스킹 → 임베딩 정확도 향상
> - 자막/UI 텍스트 → 마스킹 → 검색 노이즈 사라짐

### Fix 14A-1: Grounding DINO 의류 detect 통합

**파일:** `fashion-search/src/preprocess/garment_detect.py` (신규)

```python
"""Grounding DINO 기반 의류 box 탐지.

보고서 추천:
- IDEA-Research/grounding-dino-base
- text prompt: "cardigan. sweater. shirt. dress. skirt. pants. shoes. bag."
- box_threshold=0.28, text_threshold=0.20
"""
from __future__ import annotations
from typing import List, Dict, Any
import torch
from PIL import Image
from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

_GARMENT_PROMPT = (
    "cardigan. sweater. knit top. blouse. shirt. jacket. coat. vest. "
    "dress. skirt. pants. jeans. shorts. shoes. bag. hat. necklace. "
    "earring. ring. belt. watch. sunglasses."
)

_processor = None
_model = None

def _load():
    global _processor, _model
    if _model is None:
        _processor = AutoProcessor.from_pretrained("IDEA-Research/grounding-dino-base")
        _model = AutoModelForZeroShotObjectDetection.from_pretrained(
            "IDEA-Research/grounding-dino-base"
        ).to(DEVICE)
        _model.eval()

def detect_garments(
    img: Image.Image,
    box_threshold: float = 0.28,
    text_threshold: float = 0.20,
) -> List[Dict[str, Any]]:
    """이미지에서 의류 box 탐지.

    Returns:
        [{label, score, box: [x1,y1,x2,y2]}, ...]
    """
    _load()
    inputs = _processor(images=img, text=_GARMENT_PROMPT, return_tensors="pt").to(DEVICE)
    with torch.no_grad():
        outputs = _model(**inputs)
    results = _processor.post_process_grounded_object_detection(
        outputs,
        inputs.input_ids,
        box_threshold=box_threshold,
        text_threshold=text_threshold,
        target_sizes=[img.size[::-1]],
    )[0]

    out = []
    for box, label, score in zip(
        results["boxes"].cpu().numpy().tolist(),
        results["labels"],
        results["scores"].cpu().numpy().tolist(),
    ):
        x1, y1, x2, y2 = map(int, box)
        out.append({
            "label": str(label),
            "score": float(score),
            "box": [x1, y1, x2, y2],
        })
    return out
```

`requirements.txt` 추가:
```
transformers>=4.45.0
torch>=2.0.0
```

### Fix 14A-2: PaddleOCR 텍스트 마스킹

**파일:** `fashion-search/src/preprocess/text_mask.py` (신규)

```python
"""PaddleOCR 한국어 OCR로 자막/UI 텍스트 마스킹.

보고서 추천: PP-OCRv5 multilingual (106개 언어 지원)
"""
from typing import List
import numpy as np
from PIL import Image, ImageFilter

_ocr = None

def _load():
    global _ocr
    if _ocr is None:
        from paddleocr import PaddleOCR
        _ocr = PaddleOCR(lang="korean", use_angle_cls=True, show_log=False)

def detect_text_boxes(img: Image.Image) -> List[List[int]]:
    _load()
    arr = np.array(img)
    result = _ocr.ocr(arr, cls=True)
    boxes = []
    for line_group in result or []:
        if not line_group:
            continue
        for item in line_group:
            poly = item[0]
            xs = [int(p[0]) for p in poly]
            ys = [int(p[1]) for p in poly]
            boxes.append([min(xs), min(ys), max(xs), max(ys)])
    return boxes

def blur_boxes(img: Image.Image, boxes: List[List[int]], radius: int = 18) -> Image.Image:
    out = img.copy()
    for x1, y1, x2, y2 in boxes:
        crop = out.crop((x1, y1, x2, y2)).filter(ImageFilter.GaussianBlur(radius=radius))
        out.paste(crop, (x1, y1))
    return out
```

`requirements.txt` 추가:
```
paddleocr>=2.7.0
paddlepaddle>=2.5.0
```

### Fix 14A-3: 얼굴 마스킹

**파일:** `fashion-search/src/preprocess/face_mask.py` (신규)

```python
"""얼굴 검출 + 블러 마스킹 (개인정보 보호 + 임베딩 노이즈 감소)."""
from typing import List
import cv2
import numpy as np
from PIL import Image, ImageFilter

_cascade = None

def _load():
    global _cascade
    if _cascade is None:
        _cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )

def detect_faces(img: Image.Image) -> List[List[int]]:
    _load()
    arr = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
    faces = _cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4)
    return [[int(x), int(y), int(x+w), int(y+h)] for (x, y, w, h) in faces]

def blur_faces(img: Image.Image, boxes: List[List[int]], radius: int = 24) -> Image.Image:
    out = img.copy()
    for x1, y1, x2, y2 in boxes:
        crop = out.crop((x1, y1, x2, y2)).filter(ImageFilter.GaussianBlur(radius=radius))
        out.paste(crop, (x1, y1))
    return out
```

### Fix 14A-4: 의류 crop 통합 파이프라인

**파일:** `fashion-search/src/preprocess/pipeline.py` (신규)

```python
"""전처리 파이프라인 통합:
1. 회전 보정
2. Grounding DINO → 의류 box
3. PaddleOCR → 텍스트 box → 마스킹
4. Haar Cascade → 얼굴 box → 마스킹
5. 의류 crop 추출 (8% expand)
"""
from typing import Dict, Any, List
from PIL import Image
from src.preprocess.garment_detect import detect_garments
from src.preprocess.text_mask import detect_text_boxes, blur_boxes
from src.preprocess.face_mask import detect_faces, blur_faces

def expand_box(box: List[int], w: int, h: int, ratio: float = 0.08) -> List[int]:
    x1, y1, x2, y2 = box
    dx, dy = int((x2 - x1) * ratio), int((y2 - y1) * ratio)
    return [
        max(0, x1 - dx), max(0, y1 - dy),
        min(w, x2 + dx), min(h, y2 + dy),
    ]

def preprocess_image(img: Image.Image) -> Dict[str, Any]:
    """전처리 통합:
    Returns: {
        'garments': [{label, score, box, crop}, ...],
        'face_boxes': [...],
        'text_boxes': [...],
        'masked_image': PIL.Image (얼굴/텍스트 마스킹된 원본)
    }
    """
    img = img.convert("RGB")
    w, h = img.size

    # 1. detection
    garments = detect_garments(img)
    faces = detect_faces(img)
    texts = detect_text_boxes(img)

    # 2. masking (얼굴 + 텍스트)
    masked = blur_faces(img, faces)
    masked = blur_boxes(masked, texts)

    # 3. 의류 crop (마스킹된 이미지에서)
    crops = []
    for g in garments:
        box = expand_box(g["box"], w, h, ratio=0.08)
        x1, y1, x2, y2 = box
        crop = masked.crop((x1, y1, x2, y2))
        crops.append({**g, "crop_box": box, "crop": crop})

    return {
        "garments": crops,
        "face_boxes": faces,
        "text_boxes": texts,
        "masked_image": masked,
    }
```

### Fix 14A-5: routes_search.py 통합

`fashion-search/apps/api/routes_search.py` 수정:

```python
from src.preprocess.pipeline import preprocess_image

# /api/search 핸들러 안:
# 기존 detect_regions 호출 대체

pp = await asyncio.to_thread(preprocess_image, pil_image)
masked_image = pp["masked_image"]
garment_crops = {g["label"]: g["crop"] for g in pp["garments"]}

# garment_crops 를 _build_per_tab_query_embs 에 전달
# 또는 새 함수 _build_per_tab_query_embs_v2 작성
```

### 배포 + 검증 + commit

```bash
cd fashion-search
pip install -r requirements.txt  # 새 dependency 설치 확인
bash deploy.sh  # Cloud Run 재배포 (의존성 무거우니 빌드 시간 증가)
cd ..
sleep 60  # propagation
bash scripts/verify_deploy.sh
# v3 path 적중 확인 (Cloud Run 처리 시간 새 의존성 추가로 증가 — Worker timeout 90초로 늘려야 할 수도)

git add -A
git commit -m "feat(preprocess): Grounding DINO + PaddleOCR + face mask (Track 14A)"
```

---

## Track B — XGBoost LTR Reranker (P0)

> **보고서 인용:**
> "fine-tuning보다 reranker를 먼저. XGBoost rank:ndcg 또는 LightGBM lambdarank가 현실적"

### Fix 14B-1: feature_builder.py

**파일:** `fashion-search/src/retrieval/feature_builder.py` (신규)

```python
"""LTR feature 생성.

보고서 추천 14개 feature:
img_sim_crop, img_sim_context, category_match, color_match,
neckline_match, fit_match, title_sim_norm, brand_exact, maker_exact,
product_type, seller_score, stock_freshness, shipping_speed_score, explicit_budget_fit
"""
from typing import Dict, Any, List
import numpy as np

FEATURE_NAMES = [
    "img_sim_crop",
    "img_sim_context",
    "category_match",
    "color_match",
    "neckline_match",
    "fit_match",
    "title_sim_norm",
    "brand_exact",
    "maker_exact",
    "product_type",
    "seller_score",
    "stock_freshness",
    "shipping_speed_score",
    "explicit_budget_fit",
]

def build_features(
    query_attrs: Dict[str, Any],
    products: List[Dict[str, Any]],
    query_emb: np.ndarray,
    product_embs: Dict[str, np.ndarray],
) -> np.ndarray:
    """각 product 마다 14-dim feature vector 생성.

    Returns: (N, 14) numpy array
    """
    rows = []
    for p in products:
        pid = p.get("product_id", "")
        prod_emb = product_embs.get(pid)

        img_sim_crop = float(np.dot(query_emb, prod_emb)) if prod_emb is not None else 0.0
        # img_sim_context: 전체 이미지 vs 전체 thumbnail (별도 계산 필요)
        img_sim_context = 0.0  # TODO: pp.masked_image 임베딩 vs thumbnail 임베딩

        category_match = 1.0 if p.get("category", "") == query_attrs.get("category", "") else 0.0
        color_match = 1.0 if any(c in p.get("title", "") for c in [query_attrs.get("color", "")]) else 0.0
        # ... (각 feature 정의 따라 계산)

        rows.append([
            img_sim_crop,
            img_sim_context,
            category_match,
            color_match,
            0.0,  # neckline_match (Gemini attr 비교)
            0.0,  # fit_match
            0.0,  # title_sim_norm (rapidfuzz)
            0.0,  # brand_exact
            0.0,  # maker_exact
            float(p.get("product_type", 0)),
            0.0,  # seller_score (mall_name 기반)
            0.0,  # stock_freshness
            0.0,  # shipping_speed_score
            0.0,  # explicit_budget_fit (사용자 명시 예산 시만)
        ])
    return np.array(rows)
```

### Fix 14B-2: ranker.py

**파일:** `fashion-search/src/retrieval/ranker.py` (신규)

```python
"""XGBoost LTR ranker.

보고서 권장:
- objective=rank:ndcg (LambdaMART 계열)
- learning_rate=0.05, max_depth=6, n_estimators=300
"""
from typing import List
import numpy as np
import xgboost as xgb

class FashionRanker:
    def __init__(self):
        self.model = None

    def train(self, X, y, qid, X_val=None, y_val=None, qid_val=None):
        self.model = xgb.XGBRanker(
            objective="rank:ndcg",
            learning_rate=0.05,
            max_depth=6,
            n_estimators=300,
            subsample=0.8,
            colsample_bytree=0.8,
            tree_method="hist",
        )
        kw = {"qid": qid}
        if X_val is not None:
            kw.update({"eval_set": [(X_val, y_val)], "eval_qid": [qid_val], "verbose": True})
        self.model.fit(X, y, **kw)

    def predict(self, X) -> np.ndarray:
        return self.model.predict(X)

    def save(self, path: str):
        self.model.save_model(path)

    def load(self, path: str):
        self.model = xgb.XGBRanker()
        self.model.load_model(path)
```

`requirements.txt` 추가:
```
xgboost>=2.0.0
lightgbm>=4.0.0
```

### Fix 14B-3: routes_search.py 통합 (training data 부족 시 fallback)

```python
# 학습된 모델 있으면 사용, 없으면 기존 softScoreProducts fallback
from src.retrieval.ranker import FashionRanker
from src.retrieval.feature_builder import build_features

_ranker = None
def _load_ranker():
    global _ranker
    if _ranker is None:
        try:
            _ranker = FashionRanker()
            _ranker.load("artifacts/ranker_v1.json")
        except FileNotFoundError:
            _ranker = None  # fallback to softScoreProducts
    return _ranker

# rank_products_v3 안:
ranker = _load_ranker()
if ranker:
    features = build_features(...)
    scores = ranker.predict(features)
    # scores 로 정렬
else:
    # 기존 softScoreProducts (Worker 측 휴리스틱)
    ...
```

### 배포 + commit

```bash
git add -A
git commit -m "feat(retrieval): XGBoost LTR reranker scaffolding (Track 14B)"
```

→ 학습 데이터 부족하므로 모델 파일은 다음 세션 생성. 이번엔 scaffolding 만.

---

## Track C — SKU Matcher + Effective Price (P0)

> **보고서 인용:**
> "최저가 매칭은 검색 정확도와 분리. same SKU vs same design vs similar item 구분 후 가격 비교"

### Fix 14C-1: SKU matcher 강화

**파일:** `fashion-search/src/pricing/sku_matcher.py` (신규)

```python
"""SKU matching with model code + brand + image similarity.

보고서 추천 score weights:
- model_code exact: 0.35
- brand/maker exact: 0.15 each
- normalized title sim: 0.20
- image sim: 0.15
- option overlap: 0.10
- productType confidence: 0.05
"""
import re
from typing import Dict, Any, List
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
    (r"\b(차콜|먹색)\b", "charcoal"),
]

MODEL_CODE_RE = re.compile(r"\b[A-Z0-9]{2,}[-_/]?[A-Z0-9]{2,}\b")
TOKEN_RE = re.compile(r"[a-zA-Z0-9_가-힣]+")

def normalize_title(title: str) -> str:
    s = title.lower()
    s = re.sub(r"<[^>]+>", " ", s)
    for pat, rep in REPLACERS:
        s = re.sub(pat, rep, s, flags=re.IGNORECASE)
    toks = [t for t in TOKEN_RE.findall(s) if t not in STOPWORDS]
    return " ".join(toks)

def extract_model_codes(text: str) -> List[str]:
    return list(set(MODEL_CODE_RE.findall(text.upper())))

def title_similarity(a: str, b: str) -> float:
    return fuzz.token_set_ratio(normalize_title(a), normalize_title(b)) / 100.0

def sku_score(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, float]:
    """SKU 일치 점수 + 분류.

    Returns: {score, category: 'same_sku' | 'same_design' | 'similar_item'}
    """
    score = 0.0
    if a.get("brand") and a.get("brand") == b.get("brand"):
        score += 0.15
    if a.get("maker") and a.get("maker") == b.get("maker"):
        score += 0.15
    a_codes = set(extract_model_codes(a.get("title", "")))
    b_codes = set(extract_model_codes(b.get("title", "")))
    if a_codes and (a_codes & b_codes):
        score += 0.35
    score += 0.20 * title_similarity(a.get("title", ""), b.get("title", ""))
    score += 0.15 * float(b.get("img_sim", 0.0))

    # 분류
    if score >= 0.70:
        category = "same_sku"
    elif score >= 0.50:
        category = "same_design"
    else:
        category = "similar_item"
    return {"score": min(score, 1.0), "category": category}
```

### Fix 14C-2: Effective price 계산

**파일:** `fashion-search/src/pricing/effective_price.py` (신규)

```python
"""effective price = base + shipping - coupons - payment_discount + tax + fx.

MVP: lprice 만 사용 (used:rental:cbshop exclude로 환율/관세 제거)
확장: 제휴 판매처 피드 또는 seller page parser 필요
"""
from typing import Dict, Any

def compute_effective_price(product: Dict[str, Any]) -> int:
    """현재 MVP — lprice + shipping_fee (있으면) 만."""
    base = int(product.get("lprice", 0) or 0)
    shipping = int(product.get("shipping_fee", 0) or 0)
    return base + shipping

def cluster_by_sku(products: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    """SKU score 기반 클러스터링.

    같은 same_sku 끼리 묶고, 그 안에서 effective price 비교.
    """
    from src.pricing.sku_matcher import sku_score

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
            res = sku_score(p, q)
            if res["category"] == "same_sku":
                cluster.append(q)
                used.add(j)
        clusters.append(cluster)
    return clusters

def lowest_price_per_cluster(clusters):
    """각 클러스터에서 effective price 최저인 product 1개 + 다른 판매처 메타."""
    result = []
    for cluster in clusters:
        for p in cluster:
            p["_effective_price"] = compute_effective_price(p)
        cheapest = min(cluster, key=lambda x: x["_effective_price"])
        cheapest["_cluster_size"] = len(cluster)
        cheapest["_min_price"] = min(p["_effective_price"] for p in cluster)
        cheapest["_max_price"] = max(p["_effective_price"] for p in cluster)
        cheapest["_other_sellers"] = [
            {"mall_name": p.get("mall_name"), "price": p["_effective_price"], "link": p.get("link")}
            for p in cluster if p is not cheapest
        ]
        result.append(cheapest)
    return result
```

### Fix 14C-3: Naver search exclude 강제

**파일:** `server/src/worker.ts` (`/api/search/categories` 안)

```typescript
// 보고서 P0: 네이버 검색 exclude=used:rental:cbshop 기본 강제
// 또한 productType 기반 신뢰도 추가
const NAVER_EXCLUDE = "used:rental:cbshop";  // 중고/렌탈/해외직구 제외
```

→ 이미 SESSION 11에서 일부 적용됨. 보강 확인.

### 배포 + commit

```bash
git add -A
git commit -m "feat(pricing): SKU matcher + effective price + cluster (Track 14C)"
```

---

## Track D — Gold Set 600개 + 자동 회귀 평가 (P0)

> **보고서 추천:**
> - 200개 셀럽 단일 상의 스크린샷
> - 150개 레이어드 다중 아이템
> - 150개 아우터/기장/핏 중요
> - 100개 가방/신발/액세서리

### Fix 14D-1: Gold set 디렉토리 + 라벨링 도구

**파일:** `fashion-search/eval/gold_set/README.md` (신규)

```markdown
# Gold Set 600 queries

## 구성
- 200 single_top
- 150 layered_multi
- 150 outer_fit
- 100 accessory

## 라벨
- 2점: same SKU
- 1점: same design / acceptable substitute
- 0점: wrong

## 디렉토리
gold_set/
  queries/        # 600 .jpg
  labels.jsonl    # {"query_id": "q001", "candidates": [{"product_id":..., "label": 0|1|2}]}
  splits/
    train.txt
    valid.txt
    test.txt
```

### Fix 14D-2: 자동 회귀 평가 스크립트

**파일:** `fashion-search/eval/regression_test.py` (신규)

```python
"""Gold set 자동 회귀 평가.

PR마다 실행 → baseline 대비 metric regression 시 fail.
"""
import json, sys, asyncio, requests
from pathlib import Path

BASELINE_FILE = "eval/results/baseline.json"
URL = "https://cloi.pages.dev/api/analyze"

def load_gold():
    with open("eval/gold_set/labels.jsonl") as f:
        return [json.loads(l) for l in f]

def recall_at_k(predicted_ids, gold_labels, k):
    relevant = {p["product_id"] for p in gold_labels if p["label"] > 0}
    top_k = set(predicted_ids[:k])
    if not relevant:
        return 0.0
    return len(top_k & relevant) / len(relevant)

def mrr(predicted_ids, gold_labels):
    relevant = {p["product_id"] for p in gold_labels if p["label"] > 0}
    for i, pid in enumerate(predicted_ids):
        if pid in relevant:
            return 1.0 / (i + 1)
    return 0.0

def evaluate():
    gold = load_gold()
    results = {"recall@1": [], "recall@5": [], "recall@20": [], "mrr": []}
    for q in gold[:50]:  # 50개 샘플로 빠르게
        # ... API 호출 + predicted_ids 추출
        # ... metric 계산
        pass

    summary = {k: sum(v)/len(v) if v else 0 for k, v in results.items()}

    # baseline 비교
    if Path(BASELINE_FILE).exists():
        with open(BASELINE_FILE) as f:
            baseline = json.load(f)
        for metric, value in summary.items():
            if value < baseline.get(metric, 0) * 0.95:  # 5% 이상 regression
                print(f"REGRESSION: {metric} {baseline[metric]} → {value}")
                sys.exit(1)

    print(json.dumps(summary, indent=2))
    with open(BASELINE_FILE, "w") as f:
        json.dump(summary, f, indent=2)

if __name__ == "__main__":
    evaluate()
```

### Fix 14D-3: GitHub Actions PR 자동 평가

**파일:** `.github/workflows/regression.yml` (신규)

```yaml
name: Regression Test
on:
  pull_request:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install requests
      - run: cd fashion-search && python eval/regression_test.py
```

### commit

```bash
git add -A
git commit -m "feat(eval): gold set 600 + regression test scaffold (Track 14D)"
```

→ 실제 600개 라벨링은 별도 작업. 이번엔 scaffold + 첫 50개 빠른 평가.

---

## Track E — 임베딩 모델 비교 (P1)

> **보고서 추천:** OpenCLIP vs SigLIP2 vs FashionCLIP 오프라인 Recall@K/MRR 비교

### Fix 14E-1: benchmark 스크립트

**파일:** `fashion-search/eval/benchmark_models.py` (신규)

```python
"""3 임베딩 모델 비교: FashionCLIP, OpenCLIP, SigLIP2.

보고서 권장 메트릭: Recall@1/5/20, MRR
"""
import torch
import open_clip
from transformers import AutoModel, AutoProcessor

MODELS = [
    {
        "name": "fashion_clip",
        "loader": lambda: ("patrickjohncyh/fashion-clip", "transformers"),
    },
    {
        "name": "openclip_vitb16",
        "loader": lambda: ("ViT-B-16", "openai", "open_clip"),
    },
    {
        "name": "siglip2_base",
        "loader": lambda: ("google/siglip2-base-patch16-224", "transformers"),
    },
]

def benchmark(model_config, gold_set):
    # ... 각 모델 로드 + gold set 임베딩 + Recall/MRR 계산
    pass

if __name__ == "__main__":
    results = {}
    for cfg in MODELS:
        results[cfg["name"]] = benchmark(cfg, load_gold())
    print(json.dumps(results, indent=2))
```

`requirements.txt` 추가:
```
open_clip_torch>=2.20.0
```

### commit

```bash
git add -A
git commit -m "feat(eval): embedding model benchmark scaffold — FashionCLIP vs OpenCLIP vs SigLIP2 (Track 14E)"
```

→ 실제 비교 실행은 GPU 환경 필요 (CPU에서도 가능하나 느림). scaffold 만 이번 세션.

---

## Track F — 법률 / opt-in 문서 (P1)

> **보고서 인용:** "한국 저작권법 + 개인정보보호위원회 + 한국저작권위원회 가이드. 경쟁사 무단 수집 금지. 제휴/opt-in 필수."

### Fix 14F-1: 사용자 동의 문구

**파일:** `app/legal/consent_ko.md` (신규)

```markdown
# 사용자 동의서

## [필수] 이미지 사용 권한
본인은 업로드한 이미지 및 관련 메타데이터(상품 태그, 링크, 설명)에 대해 본 서비스가 검색 정확도 향상, 유사 상품 추천, 모델 평가 및 재학습을 위해 저장·가공·분석할 수 있는 권한을 보유하고 있음을 확인합니다.

## [선택] 학습 데이터 활용 동의
본인은 업로드한 이미지에서 얼굴/문자 영역이 자동 마스킹된 파생 데이터와 의류 속성 태그가 검색 품질 향상 및 AI 모델 학습에 사용되는 것에 동의합니다. 본 동의는 언제든지 철회할 수 있으며, 철회 시 향후 학습 파이프라인에서 제외됩니다.

## [필수] 제3자 권리 보호
제3자의 저작권, 상표권, 초상권 또는 퍼블리시티권을 침해하는 자료를 업로드하지 않겠습니다.
```

### Fix 14F-2: Takedown 정책

**파일:** `app/legal/takedown_policy.md` (신규)

```markdown
# 권리침해 신고 (Notice and Takedown)

## 신고 채널
- 이메일: takedown@cloi.kr
- 신고 양식: https://cloi.pages.dev/takedown

## 처리 절차
1. 신고 접수 (24시간 이내 확인)
2. 침해 의심 콘텐츠 임시 삭제 (48시간 이내)
3. 권리자 검증 + 게시자 통지
4. 최종 결정 (7일 이내)

근거: 한국 저작권법 제103조 (온라인서비스제공자 책임 제한)
```

### Fix 14F-3: 데이터 수집 체크리스트

**파일:** `app/legal/checklist.md` (신규) — 보고서 8항목 그대로

```markdown
# 데이터 수집 합법성 체크리스트

1. [ ] 얼굴 자동 마스킹 적용?
2. [ ] 원본 이미지 저장과 파생 특성 저장 분리?
3. [ ] 경쟁사 marketplace bulk scraping 0건?
4. [ ] Creator/brand 계약 또는 opt-in 증빙 보유?
5. [ ] 저작권/상표권/초상권 침해 신고 채널 운영?
6. [ ] 학습 동의가 inference 동의와 분리?
7. [ ] 삭제 요청 시 재학습 제외 정책 보유?
8. [ ] "최저가" 표기가 과장 광고가 아닌 범위 명시?
```

### commit

```bash
git add -A
git commit -m "docs(legal): consent + takedown + checklist (Track 14F)"
```

---

## Track G — Worker timeout 90초 + Cloud Run path 적중률 측정 (P0)

### Fix 14G-1: Worker timeout 연장

**파일:** `server/src/worker.ts` (`/api/analyze` 핸들러)

```typescript
// 보고서 인용: Cloud Run 처리 시간 새 의존성 (Grounding DINO + PaddleOCR) 추가로 늘어남
// timeout 45 → 90초로 연장
const upstream = await fetch(`${fashionSearchUrl}/api/search`, {
  signal: AbortSignal.timeout(90000),  // 45 → 90초
});
```

### Fix 14G-2: Cloud Run path 적중률 측정 스크립트

**파일:** `scripts/measure_v3_hit_rate.sh` (신규)

```bash
#!/usr/bin/env bash
# Cloud Run v3 path 적중률 측정 — 10회 호출 후 _source 분포

ITERATIONS=10
PAGES_URL="https://cloi.pages.dev"
TEST_IMG="fashion-search/eval/queries/q010.jpg"

v3_count=0
worker_count=0
none_count=0

for i in $(seq 1 $ITERATIONS); do
    B64=$(base64 -w 0 < "$TEST_IMG")
    SRC=$(curl -s -X POST "$PAGES_URL/api/analyze" \
        -H "Content-Type: application/json" \
        -d "{\"imageBase64\":\"$B64\",\"mimeType\":\"image/jpeg\"}" \
        --max-time 120 \
        | python3 -c "import json,sys;print(json.load(sys.stdin).get('_source','NONE'))")
    case "$SRC" in
        v3) v3_count=$((v3_count+1));;
        worker_gemini) worker_count=$((worker_count+1));;
        *) none_count=$((none_count+1));;
    esac
    echo "Call $i: $SRC"
done

echo ""
echo "=== Summary (n=$ITERATIONS) ==="
echo "v3:            $v3_count"
echo "worker_gemini: $worker_count"
echo "none/error:    $none_count"
```

### commit

```bash
git add -A
git commit -m "ops(worker): timeout 45->90s + v3 hit rate measurement (Track 14G)"
```

---

## 빌드 + 통합 배포 + 검증

```bash
# Cloud Run 재배포 (Track A 의존성 무거움, 빌드 시간 길어짐)
cd fashion-search
pip install -r requirements.txt  # 로컬 검증
bash deploy.sh
cd ..

# Worker 재배포 (Track G timeout 변경)
cd server && npm run build && cd ..
npx wrangler pages deploy dist --project-name=cloi
sleep 60

# Verify
bash scripts/verify_deploy.sh
bash scripts/measure_v3_hit_rate.sh

# 라이브 5케이스 회귀 테스트
python fashion-search/scripts/live_qa_s14.py > logs/s14_results.json

git push origin main
```

---

## 성공 정의 (Done Criteria)

### P0 (필수)
- [ ] Track A: Grounding DINO + PaddleOCR + 얼굴 마스킹 코드 작성 + Cloud Run 배포
- [ ] Track A: 사용자 cropped 셀카 케이스 (이전: outer/bottom 누락) → 이제 detect됨
- [ ] Track C: SKU matcher + effective price 코드 작성 + commit
- [ ] Track D: gold set scaffold + regression test 첫 실행
- [ ] Track G: Worker timeout 90s + v3 적중률 측정 (목표: 30%+ 적중)
- [ ] verify_deploy.sh 통과
- [ ] git push

### P1 (가능하면)
- [ ] Track B: XGBoost LTR scaffold + commit (학습 데이터는 다음 세션)
- [ ] Track E: benchmark scaffold + commit (실제 비교는 별도)
- [ ] Track F: legal/consent + takedown + checklist 문서

### P2 (다음 세션)
- [ ] Track B: 실제 학습 데이터 1000건+ 모은 후 LTR 학습
- [ ] Track E: GPU 환경에서 OpenCLIP/SigLIP2 실측
- [ ] Track A: SAM 2 도입 (현재는 box crop만)

---

## 위험 요소 + 대응

| 위험 | 대응 |
|------|------|
| Cloud Run 빌드 시간 폭증 (Grounding DINO 무거움) | requirements.txt 추가 후 한 번 deploy 검증. 실패 시 image size optimization |
| Cloud Run 처리 시간 90s 초과 | 다음 세션에서 Modal Labs 같은 GPU serverless 검토 |
| PaddleOCR 의존성 (paddlepaddle) Docker 빌드 실패 | pre-built wheel 사용 또는 alternative (EasyOCR) |
| Grounding DINO 모델 다운로드 (수백 MB) | Cloud Run startup 시 cache. min-instances=1 유지 |
| XGBoost 학습 데이터 부족 | 이번 세션은 scaffold만. 학습은 다음 세션 |

---

## 본질 원칙 (보고서 결론)

1. **시스템 설계 > 모델 튜닝** — Grounding DINO + LTR이 LoRA fine-tune보다 빠른 ROI
2. **GPU 안 써도 됨** — request-based Cloud Run + 오프라인 학습 분리
3. **휴리스틱 제거 + 학습 신호** — softScoreProducts 같은 manual multiplier → XGBoost 자동 학습
4. **검색 정확도 ≠ 가격 매칭** — same SKU/same design/similar item 분리
5. **법적 준수 = 비즈니스 생존** — 경쟁사 무단 수집 = 침해

---

## Claude Code 자율 실행 명령어

```bash
cd "C:\Users\Alex KIM\Desktop\사업 프로젝트\인앱토스 1" && claude --dangerously-skip-permissions @scripts/session14_prompt.txt
```

또는 overnight 스크립트 자동 (session14_prompt.txt 자동 선택):

```powershell
powershell -ExecutionPolicy Bypass -File "C:\Users\Alex KIM\Desktop\사업 프로젝트\인앱토스 1\scripts\setup_token_and_run.bat"
```

---

## END OF SESSION 14 PROMPT
