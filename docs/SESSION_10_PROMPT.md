# SESSION 10: SESSION 9/9-B 회귀 차단 + CLIP 베이스라인 회복 + bag 탭 보호

> **선행:** `docs/DIAGNOSIS_S9_REGRESSION.md` 정독 필수.
>
> **사용자 호소 (검증됨):** "옷 카테고리만 똑같고 디자인/색깔 전혀 다른 매칭. CLIP 붙이고 효율이 더 안 나옴."
>
> **본질 원인 한 줄:** 색상 30% 가중치가 노이즈를 매칭에 주입해 CLIP을 망친다. 가방 탭은 통째로 누락된다.
>
> **이번 세션 목표:** P0 4건만 — 회귀 차단 + 라이브 정성 회복.
> **명시적 비목표:** P1~P3 (HSV 순환성/Lab/segmentation/LoRA)는 다음 세션.

---

## 0. 절대 원칙 (반드시 준수)

1. **CLIP-only 베이스라인 회복이 최우선.** 색상 신호가 "도움 됐는지" 증명되지 않은 상태로 30% 가중을 두지 않는다.
2. **삭제하지 말고 비활성화하라.** color_hist 함수/모듈은 남겨둔다. 가중치만 0%로 한다. 다음 세션에서 올바르게 복원할 가능성 보존.
3. **변경 1건마다 git commit + 정량 측정.** 모든 commit 후 `make eval` (또는 동등 스크립트) 실행.
4. **라이브 재배포 후 반드시 동일 이미지 재테스트.** 회복 시그널을 사용자가 즉시 볼 수 있어야 한다.
5. **사용자 인지 신호(detected_items_meta)를 응답에 노출 유지.** 다음 세션에서 디버깅 빠르게.

---

## 1. 전제 — 진단 요약

| 결함 # | 영향 | 본 세션 처리 |
|--------|------|-----------|
| 1 (색상 비대칭) | 🔴 회귀 주범 | **Fix 10-1** color 가중치 0% |
| 2 (Hue 순환성) | 🟠 빨강 계열만 | 다음 세션 |
| 3 (dominant 거리 계산) | 🔴 60% 가중치 죽은 코드 | **Fix 10-2** dominant 비활성화 |
| 4 (K-means 불안정) | 🟠 노이즈 | (Fix 10-2로 같이 해결) |
| 5 (multi-crop 덮어쓰기) | 🟡 부수적 | **Fix 10-5** dict→list 변경 |
| 6 (4분면 임계값) | 🔴 가격 정렬화 | **Fix 10-3** 동적 임계값 |
| 7 (per-tab silent fallback) | 🟠 결함 1+8과 결합 시 치명 | (Fix 10-1로 영향 감소) |
| 8 (tab_mapper 좁음) | 🟡 부수적 | 다음 세션 |
| 9 (color penalty 죽은 코드) | 🟡 dead code | (Fix 10-1로 자연 해결) |
| 10 (클러스터 색상 안전장치) | 🟠 같은 SKU 분리 | **Fix 10-4** 색상 검증 끄기 |
| 11 (price_fit 25%) | 🟠 mood 매핑 잘못 시 페널티 | 다음 세션 |
| 12 (bag 탭 누락) | 🔴 사용자 피해 명확 | **Fix 10-6** bag 탭 보호 |

---

## 2. 작업 범위 — Fix 10-1 ~ 10-6

순서: 빠른 회복 → 부수 정리 순. 각 Fix 끝나면 git commit.

### Fix 10-1: 의류 점수 공식에서 color 가중치 0%

**파일:** `fashion-search/src/ranking/mood_ranker.py`

**변경:** `compute_clothing_score` 함수만 교체. 다른 함수 보존.

```python
def compute_clothing_score(
    visual_sim: float,
    color_sim: float,
    naver_rank_score: float,
) -> float:
    """의류: 시각 매칭 우선. color는 P0에서 비활성화 (회귀 차단).

    히스토그램 비대칭 (query=crop, product=썸네일 전체) 문제로 color가 노이즈로 작동.
    SESSION 11에서 Lab + segmentation 적용 후 가중치 부활 예정.
    """
    # 비활성화 사유: docs/DIAGNOSIS_S9_REGRESSION.md 결함 1, 9 참조
    return visual_sim * 0.95 + naver_rank_score * 0.05
```

**검증:** 같은 lookbook 이미지로 상의 탭 1순위가 베이지 터틀넥에 가까워졌는지 확인.

```bash
git commit -m "fix(ranking): clothing score color weight 30% to 0% (regression block)"
```

---

### Fix 10-2: dominant_color_similarity 죽이기 + color_score 단순화

**파일:** `fashion-search/src/ranking/color_hist.py`

**`color_score` 함수 변경 — dominant 우회:**

```python
def color_score(
    query_hist: np.ndarray,
    product_hist: np.ndarray,
    query_dominant: Optional[np.ndarray] = None,
    product_dominant: Optional[np.ndarray] = None,
) -> float:
    """색상 점수 — P0에서 dominant 비활성화 (거리 계산 결함).

    SESSION 11에서 HSV Hue 순환성 + Lab 변환 후 dominant 부활 예정.
    """
    # 비활성화 사유: docs/DIAGNOSIS_S9_REGRESSION.md 결함 2, 3, 4 참조
    return color_similarity(query_hist, product_hist)
```

**`extract_dominant_colors` 함수 — 호출 비용 절감:**

`routes_search.py`에서 `extract_dominant_colors` 호출을 stub으로 대체:

```python
# routes_search.py
async def _calc_clip_embeddings_and_hists(embedder, products):
    # ... 기존 로직 유지하되 dominants는 None 처리
    embs, hists = {}, {}
    for p, vec, img in zip(valid_products, product_vecs, valid_images):
        pid = p.get("product_id", "")
        embs[pid] = vec
        hists[pid] = compute_color_histogram(img)
    return embs, hists, {}  # ← dominants 빈 dict
```

`_build_per_tab_query_embs`에서 `extract_dominant_colors` 호출 모두 제거하고 None/빈값 반환.

**검증:** Cloud Run 응답 latency 감소 확인 (K-means 호출 제거).

```bash
git commit -m "perf(color): disable dominant color (broken distance calc + slow K-means)"
```

---

### Fix 10-3: 4분면 ACCURACY_THRESHOLD 동적화

**파일:** `fashion-search/src/ranking/quadrant_sort.py`

**기존 ACCURACY_THRESHOLD=0.6 상수 제거. 동적 계산으로 변경:**

```python
"""정확도+가격 4분면 소팅 — 동적 임계값."""
import numpy as np

# Fix 10-3: 정적 0.6 → 동적 (해당 batch median + 0.05)
DEFAULT_ACCURACY_FLOOR = 0.40   # 모든 점수가 낮아도 quadrant 0 후보 보장


def quadrant_key(product: dict, price_median: float, score_threshold: float) -> tuple:
    """4분면 정렬 키. score_threshold는 batch마다 동적 결정."""
    score = product.get('match_score', 0.0)
    price = product.get('price') or 999_999_999

    is_accurate = score >= score_threshold
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


def quadrant_sort(products: list) -> list:
    """4분면 기준 정렬. 임계값을 batch median으로 동적 결정."""
    if not products:
        return []

    prices = [p.get('price') or 0 for p in products if p.get('price')]
    price_median = float(np.median(prices)) if prices else 50_000.0

    scores = [p.get('match_score', 0.0) for p in products]
    if scores:
        # 동적: median 기준. 점수 분포가 낮으면 floor 보장
        score_median = float(np.median(scores))
        score_threshold = max(DEFAULT_ACCURACY_FLOOR, score_median)
    else:
        score_threshold = DEFAULT_ACCURACY_FLOOR

    return sorted(
        products,
        key=lambda p: quadrant_key(p, price_median, score_threshold),
    )
```

**검증:** 하의 탭 1순위가 17만원 베이지 스커트에서 다른 (더 정확한) 상품으로 바뀌는지.

```bash
git commit -m "fix(sort): quadrant accuracy threshold 0.6 to dynamic median+floor"
```

---

### Fix 10-4: SKU 클러스터링 색상 안전장치 임시 비활성화

**파일:** `fashion-search/src/pricing/normalize.py`

**`cluster_similar_products_v2` 안 색상 검증 코드 비활성화 (주석 처리 또는 임계값 0):**

```python
CLUSTER_THRESHOLDS_CLOTHING = {
    'image_sim_strong': 0.90,
    'image_sim_weak': 0.82,
    'title_sim': 0.65,
    'color_min_sim': 0.0,  # ← Fix 10-4: 0으로 — color signal 회복 전까지 비활성화
}

CLUSTER_THRESHOLDS_ACCESSORY = {
    'image_sim_strong': 0.85,
    'image_sim_weak': 0.75,
    'title_sim': 0.60,
    'color_min_sim': 0.0,  # ← Fix 10-4
}
```

**부수 효과:** 같은 SKU가 더 잘 묶임 (색상 변동에 의한 분리 사라짐). 단, 다른 디자인이 image_sim 높을 때 묶일 위험 있음 → 다음 세션에서 image_sim 임계값 자체 재검토.

```bash
git commit -m "fix(pricing): disable color safety in clustering (color signal disabled)"
```

---

### Fix 10-5: `crop_garment_regions` 멀티 객체 보존 (dict → list)

**파일:** `fashion-search/src/preprocess/gemini_detector.py`

**현재 (정보 손실):**
```python
def crop_garment_regions(image, boxes, expand_ratio=0.08) -> dict[str, Image.Image]:
    crops: dict[str, Image.Image] = {}
    for box in boxes:
        ...
        crops[box.label] = image.crop(...)  # ← 같은 라벨 덮어쓰기
    return crops
```

**변경 — 같은 레이블도 보존:**
```python
def crop_garment_regions(image, boxes, expand_ratio=0.08) -> dict[str, list[Image.Image]]:
    """레이블 → crop 이미지 리스트. 같은 레이블 여러 박스 모두 보존."""
    w, h = image.size
    crops: dict[str, list[Image.Image]] = {}
    for box in boxes:
        if box.label == 'face':
            continue
        x1 = int(box.x1 * w / 1000)
        y1 = int(box.y1 * h / 1000)
        x2 = int(box.x2 * w / 1000)
        y2 = int(box.y2 * h / 1000)
        if x2 <= x1 or y2 <= y1:
            continue
        dx = int((x2 - x1) * expand_ratio)
        dy = int((y2 - y1) * expand_ratio)
        x1 = max(0, x1 - dx)
        y1 = max(0, y1 - dy)
        x2 = min(w, x2 + dx)
        y2 = min(h, y2 + dy)
        crops.setdefault(box.label, []).append(image.crop((x1, y1, x2, y2)))
    return crops
```

**호출자 수정 — `routes_search.py:_build_per_tab_query_embs`:**

```python
# 변경 전: garment_crops = {label: Image, ...}
# 변경 후: garment_crops = {label: [Image, Image, ...], ...}

crop_labels = list(garment_crops.keys())
# 같은 라벨 여러 crop이면 임베딩 평균 사용 (멀티 객체 표현)
crops_per_label: list[list[Image.Image]] = [garment_crops[l] for l in crop_labels]

# 평탄화 + 임베딩
flat_images = [img for sublist in crops_per_label for img in sublist]
flat_embs = await asyncio.to_thread(embedder.embed, flat_images)

# 라벨별 평균 임베딩으로 복원
label_to_emb: dict[str, np.ndarray] = {}
idx = 0
for label, sublist in zip(crop_labels, crops_per_label):
    n = len(sublist)
    avg = np.mean(flat_embs[idx:idx + n], axis=0)
    norm = np.linalg.norm(avg) + 1e-8
    label_to_emb[label] = avg / norm
    idx += n

# label_to_hist도 같은 방식 — 첫 crop 또는 평균
label_to_hist: dict[str, np.ndarray] = {
    label: compute_color_histogram(garment_crops[label][0])
    for label in crop_labels
}
```

```bash
git commit -m "fix(detect): preserve multi-box per label (no more dict overwrite)"
```

---

### Fix 10-6: bag 탭 보호 — Naver fallback 검색 강제 + 빈 결과 빈 탭 표시

**파일:** `fashion-search/apps/api/routes_search.py`

**현재 문제:**
```python
for item in style_ctx.detected_items:
    products = raw_results.get(tab_id, [])
    if not products:
        continue   # ← 빈 결과면 탭 제외 → 사용자에게 신호 없음
```

**변경 1 — bbox 보강된 탭은 Naver 0건이어도 fallback 한 번 더 시도:**

`_augment_detected_items_from_bbox` 호출 직후, 결과가 비어있는 탭에 대해 카테고리만으로 강제 검색:

```python
# 7-A. (신규) bag/accessory 탭 raw_results 0건이면 카테고리만으로 fallback
async def _ensure_tab_has_results(
    detected_items,
    raw_results: dict[str, list[dict]],
):
    """bbox 보강된 탭이 Naver 0건이면 카테고리만으로 한 번 더 검색."""
    from src.search.parallel_search import _execute_queries

    empty_critical_tabs = [
        item for item in detected_items
        if not raw_results.get(item.tab_id)
        and (item.tab_id == 'bag' or item.tab_id.startswith('accessory_'))
    ]
    if not empty_critical_tabs:
        return raw_results

    # 카테고리 단일 쿼리로 강제 검색
    fallback_tasks = {}
    for item in empty_critical_tabs:
        cat = item.category or item.tab_id
        queries = [cat, f'여성 {cat}', f'{cat} 추천']
        fallback_tasks[item.tab_id] = _execute_queries(
            queries, category=cat, display=20, exclude='used:rental:cbshop',
        )

    results_list = await asyncio.gather(*fallback_tasks.values(), return_exceptions=True)
    for tab_id, res in zip(fallback_tasks.keys(), results_list):
        if not isinstance(res, Exception) and res:
            raw_results[tab_id] = res
            logger.info("[routes_search] %s 탭 fallback 검색 %d건", tab_id, len(res))

    return raw_results
```

**`/search` 핸들러 안에 호출 추가** (raw_results 받은 직후):
```python
raw_results = await search_all_items_v3(style_ctx.detected_items)

# Fix 10-6: bag/accessory 탭 안전망
raw_results = await _ensure_tab_has_results(style_ctx.detected_items, raw_results)
```

**변경 2 — 빈 탭도 응답에 포함 (디버깅 + 사용자 인지):**

`for item in style_ctx.detected_items:` 루프 안에서 `if not products: continue` 제거 후, 빈 탭도 빈 items 리스트로 추가:

```python
for item in style_ctx.detected_items:
    tab_id = item.tab_id
    products = raw_results.get(tab_id, [])

    if not products:
        # 빈 탭도 표시 — 사용자에게 "탐지는 됐지만 검색 결과 없음" 신호
        tabs.append(TabSection(
            tab_id=tab_id,
            label=TAB_LABELS.get(tab_id, item.subcategory),
            description=item.description,
            items=[],
        ))
        continue

    # ... 이하 기존 랭킹 로직
```

**검증:** lookbook 이미지 재테스트 시 'bag' 탭이 등장. 검색 결과 0건이어도 탭 자체는 표시.

```bash
git commit -m "fix(api): protect bag/accessory tabs (fallback search + empty tab display)"
```

---

## 3. 정량 측정 — eval set으로 회귀 정량화

### 3.1 사전 측정 (변경 전)

```bash
cd "C:\Users\Alex KIM\Desktop\사업 프로젝트\인앱토스 1\fashion-search"

# 현재 settings 그대로
python -m eval.runner --embedder fashion_clip --tag baseline_s9b
python -m eval.compare --tags baseline_s9b
# → eval/results/baseline_s9b_*.jsonl
# → Recall@10 / Recall@50 / MRR / p50 latency 기록
```

### 3.2 Fix 적용 후 측정

```bash
# 각 Fix 끝나면 동일 명령으로 측정. tag로 구분.
python -m eval.runner --embedder fashion_clip --tag s10_fix1
python -m eval.runner --embedder fashion_clip --tag s10_fix3
python -m eval.runner --embedder fashion_clip --tag s10_fix6

python -m eval.compare --tags baseline_s9b s10_fix1 s10_fix3 s10_fix6
# → 각 Fix가 Recall@10에 어떻게 기여했는지 정량 비교
```

### 3.3 성공 기준

| 지표 | 목표 | 비고 |
|------|------|------|
| Recall@10 | ≥ 0.85 | S3 0.88, S4 1.0 (rerank 튜닝 후)에서 회귀 회복 |
| MRR | ≥ 0.30 | S3 0.35 |
| p50 latency | ≤ 150ms | S3 130ms, dominant 제거로 감소 기대 |

---

## 4. 라이브 정성 평가 — 동일 lookbook 이미지 재테스트

배포 후 https://11aa492c.cloi.pages.dev/ 에서 **반드시** 다음 이미지로 재테스트:

```
이미지: Unsplash photo-1483985988355-763728e1935b
구성: 버건디 코트 + 베이지 터틀넥 + 다크그레이 H라인 스커트 + 블랙 사각 선글라스 + 가죽장갑 + 쇼핑백 4개
```

### 4.1 회복 체크리스트

| # | 항목 | 회복 기준 |
|---|------|---------|
| C1 | 상의 탭 1순위 색상 | 베이지 또는 크림 (BLACK/WHITE 아님) |
| C2 | 하의 탭 1순위 색상 | 다크그레이 또는 블랙 (베이지/베이비블루 아님) |
| C3 | 하의 탭 1순위 가격 | 5만~12만원대 (17만원대 아님) |
| C4 | 아우터 탭 1순위 디자인 | 깔끔한 라인 (러플/퍼 우선순위 하락) |
| C5 | bag 탭 등장 | 'bag' 탭 응답에 포함 (items 0건이어도 OK) |
| C6 | 액세서리 탭 1순위 | 여성용 선글라스 (남성용 빅사이즈 하락) |
| C7 | latency | 20초 이내 (cold start 제외) |

### 4.2 재테스트 절차 (Claude Code 자동화)

```python
# scripts/live_qa_test.py (신규 생성 권장)
import requests, json, sys
URL = 'https://YOUR_CF_WORKER_URL/api/search'
IMG_PATH = 'tests/fixtures/lookbook_burgundy.jpg'

with open(IMG_PATH, 'rb') as f:
    r = requests.post(URL, files={'file': f}, data={'sort_by': 'quadrant'})

resp = r.json()
print('Tabs:', [t['tab_id'] for t in resp['tabs']])
print('Detected meta:', json.dumps(resp.get('detected_items_meta', []), indent=2, ensure_ascii=False))
for tab in resp['tabs']:
    print(f"\n[{tab['tab_id']}] {tab['label']}")
    for i, item in enumerate(tab['items'][:3], 1):
        print(f"  {i}. {item['title'][:50]} - {item['price']}원 (visual={item['visual_similarity']}, color={item.get('color_sim', 'n/a')})")
```

기대 결과:
```
Tabs: ['top_inner', 'bottom', 'top_outer', 'accessory_*', 'bag', ...]
[top_inner] 이너
  1. 베이지 터틀넥 ... - 25,000원 (visual=0.72, color=n/a)
  ...
[bag] 가방
  1. (검색 결과 또는 빈 표시)
```

---

## 5. 배포

```powershell
cd "C:\Users\Alex KIM\Desktop\사업 프로젝트\인앱토스 1"

# 환경 변수 (기존과 동일)
$env:GOOGLE_API_KEY = (Get-Content fashion-search/.env | Select-String '^GOOGLE_API_KEY=' | ForEach-Object { $_.Line.Split('=')[1] })
$env:ADMIN_TOKEN = (Get-Content fashion-search/.env | Select-String '^ADMIN_TOKEN=' | ForEach-Object { $_.Line.Split('=')[1] })
$env:NAVER_CLIENT_ID = (Get-Content fashion-search/.env | Select-String '^NAVER_CLIENT_ID=' | ForEach-Object { $_.Line.Split('=')[1] })
$env:NAVER_CLIENT_SECRET = (Get-Content fashion-search/.env | Select-String '^NAVER_CLIENT_SECRET=' | ForEach-Object { $_.Line.Split('=')[1] })

# Cloud Run
bash fashion-search/deploy.sh

# 확인
curl https://fashion-search-dibvogjuma-du.a.run.app/health

# (UI 변경 없음 — Pages 재배포 불필요)

# Push
git push origin main
```

---

## 6. 작업 순서 (한 번에 보기)

```bash
cd "C:\Users\Alex KIM\Desktop\사업 프로젝트\인앱토스 1"

# 0. 사전 측정
cd fashion-search
python -m eval.runner --embedder fashion_clip --tag baseline_s9b
cd ..

# 1. P0 패치 6건 (각각 commit)
# Fix 10-1 ~ 10-6 순서대로

# 2. 통합 측정
cd fashion-search
python -m eval.runner --embedder fashion_clip --tag s10_final
python -m eval.compare --tags baseline_s9b s10_final
cd ..

# 3. 배포
bash fashion-search/deploy.sh

# 4. 라이브 재테스트
python fashion-search/scripts/live_qa_test.py

# 5. 결과 확인 후 push
git push origin main

# 6. SESSION_STATUS.md 업데이트
# 완료 세션: SESSION 10
# 다음 세션: SESSION 11 (HSV Hue 순환성 + Lab + segmentation)
```

---

## 7. 성공 정의 (Done Criteria)

- [ ] git push origin main 완료
- [ ] Cloud Run revision: fashion-search-000XX 배포 성공
- [ ] eval Recall@10 ≥ 0.85 (baseline_s9b 대비 회복)
- [ ] 라이브 재테스트 회복 체크리스트 C1, C2, C3, C5 중 **3개 이상** 통과
- [ ] `SESSION_STATUS.md` 업데이트
- [ ] **알람 실행** (CLAUDE.md 종료 절차 준수)

---

## 8. 위험 요소 + 대응

| 위험 | 대응 |
|------|------|
| color 끄면 의류 정확도 급락하는 경우 | eval로 즉시 확인. 회복 안 되면 visual_sim 80% + color 5% (아주 작게) 시도 |
| 4분면 동적 임계값으로 가격 정렬 약화 | 의도한 동작. 사용자가 가격 우선 원하면 sort_by=price_asc 사용 가능 (기존 옵션 유지) |
| bag 탭 fallback 검색이 무관한 결과 노출 | 카테고리 단일 쿼리는 약함. 일단은 빈 탭으로라도 노출하는 게 미노출보다 낫다는 판단 |
| dominant 비활성화로 모종의 회귀 | dominant는 60% 가중인데 best_dist=0 케이스에서만 동작 → 사실상 죽은 코드. 회귀 확률 낮음 |
| eval set이 lookbook 다양성 부족 | SESSION 11 산출물에 lookbook 5장 추가 영향도 측정 |

---

## 9. 다음 세션(SESSION 11) 사전 노트

이번 세션은 **회귀 차단**만. 다음에 **올바른 색상 신호 부활**:

- HSV Hue 순환성: `min(|h1-h2|, 1-|h1-h2|)` 거리 함수
- Lab 색공간으로 변환 (CIE Lab은 인간 시각에 더 가까움)
- 의류 영역 segmentation (rembg 또는 Gemini bbox 정밀도 향상)
- 상품 썸네일도 center-crop 후 색 추출
- 색상 가중치 단계별 부활 (5% → 10% → 15%)

이번 세션 완료 후 위 작업을 `docs/SESSION_11_PROMPT.md`에 정리하여 다음 세션에 인계한다.

---

## 10. Claude Code 실행 명령어 (한 줄 복사)

```bash
cd "C:\Users\Alex KIM\Desktop\사업 프로젝트\인앱토스 1" && claude --dangerously-skip-permissions "docs/SESSION_10_PROMPT.md 정독 후 Fix 10-1 ~ 10-6 순서대로 정확히 실행. 각 Fix 끝나면 git commit. 모두 끝나면 fashion-search/eval로 baseline_s9b vs s10_final 정량 비교. 배포 후 https://11aa492c.cloi.pages.dev/ 에서 룩북 이미지 재테스트로 회복 체크리스트 C1~C7 검증. 종료 시 SESSION_STATUS.md 업데이트 + 알람. 본질 원칙: '잘못된 색상 신호 30%가 CLIP을 망친다. 회귀 차단이 우선'."
```

---

## END OF SESSION 10 PROMPT
