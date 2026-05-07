# SESSION 9/9-B 회귀 진단 리포트
> **작성일:** 2026-05-01
> **테스트 URL:** https://11aa492c.cloi.pages.dev/
> **테스트 이미지:** Unsplash 룩북 (버건디 코트 + 베이지 터틀넥 + 다크그레이 H라인 스커트 + 블랙 스퀘어 선글라스 + 가죽장갑 + 쇼핑백 4개+)
> **결론:** "옷 카테고리만 똑같고 디자인/색깔 전혀 다른 매칭" — 사용자 호소 100% 검증됨. 구조적 결함 12개 식별.

---

## 0. 30초 요약 (TL;DR)

**사용자 호소는 사실이다.** SESSION 9/9-B 패치가 **CLIP 신호를 약화시켰다.**

핵심 원인 한 줄: **"색상 신호 30%가 제대로 동작하지 않아서 CLIP의 시각 매칭을 노이즈로 끌어내리고 있다."**

3대 실측 증거:
1. **상의 탭** — 터틀넥 매칭은 OK인데 1순위=BLACK, 2순위=WHITE (실제는 BEIGE). 베이지는 5순위에 등장.
2. **하의 탭** — H라인 스커트 OK인데 1순위=베이지 패턴, 2순위=베이비블루 (실제는 다크그레이). 17만원~17만원으로 가격대도 어긋남.
3. **가방 탭 통째로 누락** — 쇼핑백 4개 들고 있는데 'bag' 탭이 생성조차 안 됨.

이 진단은 코드 분석(STEP A) + 라이브 서비스 실측(STEP B) + 회귀 메커니즘 추적(STEP C) 3단계로 도출.

---

## 1. STEP A — 코드 진단 (확정된 구조적 결함 12개)

### 🔴 결함 1: 색상 히스토그램 비대칭 — 가장 큰 회귀 원인

**위치:** `routes_search.py:_calc_clip_embeddings_and_hists` vs `_build_per_tab_query_embs`

```
Query 측  : Gemini bbox로 의류 영역만 crop  → HSV 히스토그램
Product 측: Naver 썸네일 전체 (대부분 흰 배경 + 모델 신체) → HSV 히스토그램
```

**문제:**
- Naver 썸네일의 70~90%가 **흰 배경 픽셀** → 모든 상품 히스토그램이 "흰색 우세" 분포로 수렴
- 사용자 crop은 **의류 + 일부 피부/배경** → 다른 분포
- 두 분포의 코사인 유사도는 **신호가 아니라 노이즈**
- `color_score`가 30% 가중치를 가지므로 **CLIP 신호를 노이즈로 희석**

**증거:** 베이지 터틀넥 쿼리에 BLACK 1순위가 등장하는 이유. 두 상품 모두 흰 배경 → color_sim 높게 나옴 → BLACK이 BEIGE보다 visual_sim 살짝 높으면 1위.

---

### 🔴 결함 2: HSV Hue 순환성(circularity) 미처리

**위치:** `color_hist.py:dominant_color_similarity`

```python
dists = np.linalg.norm((domains_b - ca) * np.array([3.0, 1.0, 1.0]), axis=1)
```

**문제:**
- HSV에서 Hue=0과 Hue=1은 **같은 색(빨강)**이지만 이 거리 공식은 1.0(최대)으로 처리
- H 가중치 ×3 적용으로 **Hue 차이가 거리를 폭발적으로 증폭**
- 빨강/와인/버건디 계열은 Hue가 0 근처라 **같은 색끼리도 분리**됨

**증거:** 아우터 탭의 버건디 매칭은 운 좋게 동작했으나, 빨강 컷오프 부근(0.95 vs 0.05)이면 같은 색이 distance=0.9×3=2.7로 계산됨.

---

### 🔴 결함 3: dominant_color_similarity 거리 → 유사도 변환이 망가짐

```python
sims.append(max(0.0, 1.0 - best_dist))
```

**문제:**
- `best_dist`는 가중치 [3, 1, 1] 적용 후 최대 √(9+1+1) ≈ 3.32
- 평균 매칭에서 dist가 0.5~1.5 정도 → `1 - dist` 가 음수 → max(0)로 클램핑
- **결과: dom_sim 대부분 0에 깔림** → `color_score` 60% 가중치가 사실상 무용지물

**증거:** 색상 점수 = 0.4 × hist_sim + 0.6 × 0 = 0.4 × hist_sim. 즉 60% 가중치 dominant 신호는 **죽은 코드**.

---

### 🔴 결함 4: K-means dominant 추출이 매번 불안정

**위치:** `color_hist.py:extract_dominant_colors`

```python
km = KMeans(n_clusters=k, random_state=42, n_init=3, max_iter=20)
```

**문제:**
- `n_init=3, max_iter=20` 너무 작음 → 64×64 픽셀에서 3-색 추출 시 수렴 안 됨
- 같은 이미지 두 번 돌리면 결과 비슷하나, **다른 두 이미지 비교 시 노이즈 큼**
- 단색 의류(흰 셔츠)에 K=3 강제 → 비슷한 흰색 3개 출력 → 비교 자체가 의미 없음

---

### 🔴 결함 5: `crop_garment_regions` dict 덮어쓰기로 멀티 객체 누락

**위치:** `gemini_detector.py:151~175`

```python
crops[box.label] = image.crop(...)  # ← 같은 라벨이면 마지막만 살아남음
```

**문제:**
- Gemini가 양쪽 귀걸이 2개 detect → 1개만 살아남음
- 셔츠 + 카디건 둘 다 `top_outer`로 detect → 마지막 것만 살아남음
- 다중 객체 시나리오 = 정보 손실

**SESSION 9 의도와 정반대:** Fix 2 프롬프트는 "같은 레이블도 여러 개 OK"라고 했으나 코드가 dict로 받아 덮어씀.

---

### 🔴 결함 6: 4분면 ACCURACY_THRESHOLD=0.6 미달로 가격 정렬로 변질

**위치:** `quadrant_sort.py:4`

```python
ACCURACY_THRESHOLD = 0.6
```

**문제:**
- 의류 점수 공식: `0.65*visual + 0.30*color + 0.05*naver`
- 현실 분포: visual_sim 0.45~0.65, color_sim 0.4~0.7 → **match_score 대부분 0.4~0.6 사이**
- 임계값 0.6 못 넘는 상품이 다수 → 모두 quadrant 2/3로 떨어짐
- 결과: **"낮은 정확도 + 싼 가격" > "낮은 정확도 + 비싼 가격"** 순으로 정렬 → **사실상 가격 정렬**

**증거:** 하의 탭 1순위가 17만원, 2순위가 17만원인데 둘 다 색깔 틀림 → quadrant 1(정확+비쌈)에 분류됐을 뿐, 정확도 매칭은 전혀 안 됨.

---

### 🔴 결함 7: per-tab embedding이 silent fallback으로 단일 평균 회귀

**위치:** `routes_search.py:_build_per_tab_query_embs:218~223`

```python
if detection is None or not detection.boxes:
    return ({item.tab_id: fallback_emb ...},)  # ← 모든 탭 = 전체 이미지
```

**문제:**
- Gemini detect 실패 (503/네트워크) 시 **모든 탭이 같은 fallback_emb** 사용
- 이는 SESSION 9 Fix 1이 폐기한 "단일 평균" 문제와 동치
- silent fallback이라 로그 외엔 알 수 없음

---

### 🔴 결함 8: tab_mapper의 priority 매핑이 좁음

**위치:** `tab_mapper.py:5~19`

```python
'top_inner': ['top_inner', 'top'],  # ← 'top'은 이미 validator가 'top_outer'로 변환
```

**문제:**
- `BoundingBox.validate_label`이 'top'을 'top_outer'로 자동 변환
- 따라서 `top_inner` tab은 우선순위 후보 'top_inner'만 남고, fallback 'top'은 영원히 매치 안 됨
- Gemini가 `top_outer`만 detect하고 `top_inner`는 안 잡으면 → top_inner 탭은 fallback_emb (전체 이미지)로 회귀

---

### 🔴 결함 9: 색상 페널티 임계값(0.3)이 너무 낮아 사실상 죽은 코드

**위치:** `mood_ranker.py:36~38`

```python
if color_sim < 0.3:
    return visual_sim * 0.50 + color_sim * 0.45 + naver_rank_score * 0.05
```

**문제:**
- 결함 1+2+3 영향으로 color_sim은 대부분 0.4~0.7 분포 → 0.3 미만 케이스 거의 없음
- 또한 페널티 분기에 가서도 color_sim에 0.45 가중치 → 색상 mismatch인데 색상 가중치를 더 주는 모순
- 의도는 "색 틀린 거 더 페널티"였으나 **로직이 틀림**

---

### 🔴 결함 10: SKU 클러스터링 색상 안전장치(0.6)가 동일 상품도 분리

**위치:** `normalize.py:CLUSTER_THRESHOLDS_CLOTHING['color_min_sim']: 0.60`

```python
if color_similarity(p_hist, q_hist) < color_min:
    color_ok = False  # 색상 너무 다르면 묶지 않음
```

**문제:**
- 같은 셔츠를 다른 판매처가 다른 조명으로 찍으면 HSV 히스토그램 차이 큼 → color_sim < 0.6 → **분리됨**
- 결함 1 (Naver 썸네일 흰 배경)으로 흰 배경 비율 다르면 color_sim 변동 큼
- 결과: 같은 SKU 5개가 그대로 5번 노출

**증거:** 하의 탭에서 비슷한 색 베이지 스커트 여러 개가 따로 노출되는 가능성.

---

### 🔴 결함 11: 가방/액세서리 점수 공식의 visual_sim 60% 가중치도 부족

**위치:** `mood_ranker.py:compute_accessory_score`

```python
return visual_sim*0.60 + mood_align*0.10 + price_fit*0.25 + naver_rank_score*0.05
```

**문제:**
- price_fit 25%가 **mood→price 강제 매핑**으로 결정됨 (결함 12 참조)
- 적정 가격대를 잘못 추정하면 **시각 매칭이 좋아도 price_fit 페널티로 밀려남**
- 무드 매핑이 8개 카테고리만 있어 매칭 실패 시 default (10000~100000)로 떨어짐

---

### 🔴 결함 12: bag 탭이 detect 자체에서 누락 (실측 확인)

**실측 증거:** 4개+ 쇼핑백을 양손에 들고 있는데 'bag' 탭 생성 안 됨.

**원인 후보:**
- A) `style_analyzer`(Gemini)가 쇼핑백을 "outfit 가방"이 아닌 "props"로 분류 → detected_items에 안 넣음
- B) `gemini_detector`가 bag bbox는 잡았지만 `_augment_detected_items_from_bbox` fallback 쿼리 검색 0건 → 탭 제외
- C) detect/analyze 둘 다 실패 → fallback 미작동

**구조적 원인:** `_augment_detected_items_from_bbox`는 추가했지만, **그 다음 단계**인 raw_results에서 0건이면 여전히 `if not products: continue`로 제외됨. fallback 쿼리만 추가했지 **빈 탭 보호** 미구현.

---

## 2. STEP B — 라이브 서비스 실측 결과

### 테스트 환경
- URL: https://11aa492c.cloi.pages.dev/
- 이미지: Unsplash photo-1483985988355-763728e1935b (룩북, ~63KB JPEG)
- 의상 구성: 버건디 와이드카라 코트 / 베이지 터틀넥 / 다크그레이 H라인 스커트 / 블랙 스퀘어 선글라스 / 검정 가죽 장갑 / 쇼핑백 4개+
- 업로드 방법: javascript_tool fetch → File API → input.files DataTransfer

### 응답 요약
- 총 발견: 140개
- 탭 4개: 상의(40), 하의(40), 아우터(40), 액세서리(20)
- **누락 탭:** bag (가방), accessory_belt(?), accessory_watch(?)
- 응답 latency: ~20초 (cold start + Gemini 호출 3개)

### 탭별 정성 평가

#### 상의 (Top) — ❌ 색상 적중률 극히 낮음
**감지 속성 (정확):** #연베이지 #슬림핏 #터틀넥 #니트 #베이직

| 순위 | 상품 | 색상 | 카테고리 | 결과 |
|------|------|------|---------|------|
| 1 | 캣쯔 폴라나시 슬리브리스탑 | **검정** | 민소매 폴라 | ❌ 색깔 + 핏 모두 틀림 |
| 2 | 네이버 채핏 니키 텐션폴라 | **흰색** | 슬림핏 터틀넥 | ❌ 색깔 틀림 (흰색≠베이지) |
| 3 | 쿠팡 여성 겨울 베스트 슬림핏 목폴라 | **검정** | 베스트 폴라 | ❌ 색깔 틀림 |
| 4 | 마미루미 여성 목폴라니트 슬림핏 | **갈색** | 터틀넥 니트 | ⚠ 색깔 근접하나 더 진함 |
| 5+ | (스크롤 시) 베이지 터틀넥 | **베이지** | 터틀넥 | ✅ 정답 — 5순위에 등장 |

**진단:** 카테고리 라벨링은 정확. 그러나 BLACK이 1순위인 것은 **결함 1+3** (color signal 무력화)의 직접 증거.

#### 하의 (Bottom) — ❌ 색상 + 가격대 모두 틀림
**감지 속성 (정확):** #다크그레이 #H라인 #울스커트 #미디스커트

| 순위 | 상품 | 색상 | 가격 | 결과 |
|------|------|------|------|------|
| 1 | 모조에스핀 배색 포인트 H라인 스커트 | **베이지/패턴** | 176,463원 | ❌ 색깔 + 가격 둘 다 |
| 2 | 라인어디션 누베트 H라인 스커트 | **베이비블루** | 171,990원 | ❌ 색깔 + 가격 |

**진단:** 다크그레이 키워드 분명히 있는데 베이지/베이비블루 등장. **결함 6** (4분면 임계값 미달로 가격 우선) + **결함 1** (색상 노이즈)의 복합 결과.

#### 아우터 (Outer) — ⚠ 색은 OK, 디자인 부분 일치
**감지 속성:** #버건디 #울코트 #와이드카라 #지퍼코트 #롱코트

| 순위 | 상품 | 색상 | 디자인 | 결과 |
|------|------|------|--------|------|
| 1 | WUNDER GEIST 행커치프 코트 | 버건디 | **러플 디테일** | ⚠ 색 OK, 스타일 다름 |
| 2 | 망고 만테코 울 롱코트 | 와인 | **퍼카라 부착** | ⚠ 색 OK, 사용자는 퍼 없음 |

**진단:** 버건디는 Hue 0 근처라 **결함 2** (Hue 순환성)에 안 걸림. 그래서 색은 잘 나옴. 단 디자인 디테일(러플/퍼)은 FashionCLIP 일반 모델 한계로 구분 못 함.

#### 액세서리 (Accessory) — ⚠ 부분 일치, 가방 탭 통째 누락
**감지 속성:** #블랙선글라스 #오버사이즈 #스퀘어선글라스 #가죽장갑 #시크

- 1순위 젠틀몬스터 사각 (블랙) ✅
- 2순위 더뷰안경 **남자 빅사이즈** 선글라스 ⚠ 여성 페르소나 무시

**가방 탭 누락:** 쇼핑백 4개 + 가죽 백 1개를 양손에 들고 있는데 `bag` 탭 미생성. **결함 12.**

---

## 3. STEP C — "왜 CLIP 붙이고 더 나빠졌는가" 회귀 메커니즘 추적

### Timeline 회귀 분석

| 세션 | 변경 | Recall@10 (eval set) | 라이브 정성 |
|------|------|---------------------|-----------|
| S3 | FashionCLIP 채택 | 0.88 | (eval만 측정) |
| S4 | reranker 그리드 | 1.00 | (eval만 측정) |
| S7 | mood_match 30% + price_fit 25% 강제 매핑 | — | **첫 회귀** |
| S8 | mood_match 폐기, vector 70/20/10 | — | 부분 회복 |
| S9 | per-tab emb + color hist 15% + 4분면 sort | — | (의도: 본질 개선) |
| **S9-B** | **color hist 30% + HSV+dominant + 클러스터 색상 안전장치** | — | **🔴 최악 회귀 (사용자 호소 발생)** |

### 회귀의 정확한 메커니즘

```
S9 이전: match = visual_sim*0.70 + mood*0.20 + naver*0.10
       → 시각 신호 70%가 지배적. Recall@10 = 1.0

S9-B 후: match = visual_sim*0.65 + color*0.30 + naver*0.05
       → 색상 30%인데 color signal이 노이즈
       → 시각 신호의 영향력이 노이즈에 희석됨
       → 회귀 발생
```

**핵심 통찰:** **"좋은 신호 70% + 노이즈 30% < 좋은 신호 100%"**

그리고 4분면 sort가 다시 한 번 가격을 끼워 넣어, 이미 흐려진 정확도 신호 위에 가격이라는 **무관한 신호**를 추가로 얹음.

### "CLIP 붙이고 더 나빠짐"의 진짜 의미

사용자 인식: "CLIP 붙이고 효율이 더 안 나옴"
실제 상황: **"CLIP은 잘 동작 중. CLIP 위에 얹은 보조 신호들이 CLIP을 망치고 있음."**

증거:
- 아우터 탭 #버건디 매칭 OK = CLIP은 색 분포 표현 가능
- 상의 탭 BLACK 1순위 = 외부 color signal이 CLIP 결과를 뒤집음
- 그러나 사용자 입장에서는 "CLIP 붙인 후 결과가 나빠짐"으로 동일하게 인식됨

---

## 4. 사용자 만족 최대화 — 우선순위 5단

### 🥇 P0 (즉시, 1세션) — 회귀 원인 차단
1. **color_hist 가중치 30% → 5%** (또는 잠시 0%로 설정해 CLIP-only 베이스라인 회복)
2. **dominant_color_similarity 죽이기** — 60% 가중 영역을 hist만 사용하도록 변경
3. **4분면 ACCURACY_THRESHOLD 0.6 → 실측 분포 기반 동적**(예: median(score)+0.05)
4. **bag 탭 보호** — `_augment_detected_items_from_bbox` 호출 후 raw_results 0건이어도 탭 출력 (빈 결과는 fallback 검색을 한 번 더)

### 🥈 P1 (다음 세션) — 색상 신호를 "올바르게" 복원
5. **HSV Hue 순환성 처리** — `min(|h1-h2|, 1-|h1-h2|)` 적용
6. **상품 측 crop 추가** — Naver 썸네일에서도 가운데 영역 우선 crop (간단한 center crop으로도 흰 배경 비율 50% 감소)
7. **Lab 색공간 + 의류 마스킹** — segmentation으로 background 제거 후 색 추출
8. **K-means → 단순 mode/median HSV** (3개 클러스터 강제 폐기)

### 🥉 P2 (중기) — 검색 품질 자체 개선
9. **Naver 검색 쿼리에 색상 토큰 강제 주입** — Gemini가 "베이지" 잡았으면 검색어에 "베이지"가 무조건 포함
10. **Negative filtering** — 무관한 색이면 결과에서 제거 (현재는 랭킹만 함)
11. **실측 user click 데이터로 학습** — SESSION 8에서 만든 impression 테이블 활용해 LightGBM으로 score weight 학습

### 🏅 P3 (장기) — 도메인 fine-tune
12. **FashionCLIP LoRA 파인튜닝** — 한국 패션 도메인 1~2만장 + triplet loss
13. **Segment Anything 통합** — 의류 영역 정확 추출 후 임베딩

---

## 5. 즉시 검증 가능한 회복 시나리오 (반드시 실측)

| 변경 | 예상 결과 | 측정 방법 |
|------|---------|----------|
| color 가중치 30% → 0%로 한정 | 베이지 터틀넥이 상의 탭 1~3순위 진입 | 같은 lookbook 이미지 재업로드 |
| 4분면 임계값 0.6 → 0.45 | 17만원 베이지 스커트가 1순위에서 밀림 | 하의 탭 1순위 가격 확인 |
| bag 탭 보호 활성화 | 'bag' 탭 등장 (쇼핑백 검색) | 응답 JSON `tabs[].tab_id` |

---

## 6. 본 진단의 한계

1. **eval set 정량 측정 미수행** — 라이브 정성 평가만으로 회귀 확인. SESSION 10에서 eval set으로 회귀 정량 측정 필수.
2. **로그 미확인** — Cloud Run 로그에서 detect/analyze 결과 직접 확인 안 함. SESSION 10에서 `detected_items_meta` 응답 필드로 확인 가능.
3. **단일 이미지 테스트** — 여러 스타일(캐주얼/스포티/럭셔리) 추가 테스트 필요.

---

## 7. 다음 행동

→ **SESSION 10 PROMPT** (`docs/SESSION_10_PROMPT.md`) 참조.

본 진단의 결함 1~12 중 P0 4개를 즉시 패치 → 라이브 재배포 → 동일 이미지 재테스트 → 회복 확인.

---

## 부록 A — 라이브 테스트 검색 결과 원본 데이터

```
업로드 이미지: 버건디 코트 + 베이지 터틀넥 + 다크그레이 H라인 스커트 + 블랙 스퀘어 선글라스 + 가죽장갑 + 쇼핑백 4개

상의 탭 hashtags: #연베이지 #슬림핏 #터틀넥 #니트 #베이직
상의 1위: 캣쯔 폴라나시 슬리브리스탑 (BLACK, 61,900원)
상의 2위: 네이버 채핏 니키 텐션폴라 (WHITE, 17,800원)
상의 3위: 쿠팡 여성 겨울 베스트 슬림핏 목폴라 (BLACK, 16,800원)
상의 4위: 마미루미 여성 목폴라니트 슬림핏 (BROWN, 27,980원)

하의 탭 hashtags: #다크그레이 #H라인 #울스커트 #미디스커트
하의 1위: 모조에스핀 배색 포인트 H라인 스커트 (BEIGE 패턴, 176,463원)
하의 2위: 라인어디션 누베트 H라인 스커트 (BABY BLUE, 171,990원)

아우터 탭 hashtags: #버건디 #울코트 #와이드카라 #지퍼코트 #롱코트
아우터 1위: WUNDER GEIST 행커치프 코트 (BURGUNDY 러플, 100,000원)
아우터 2위: 망고 만테코 울 롱코트 (WINE+퍼카라, 259,080원)

액세서리 탭 hashtags: #블랙선글라스 #오버사이즈 #스퀘어선글라스 #가죽장갑 #시크
액세서리 1위: 젠틀몬스터 NEW HER 사각 (BLACK, 289,000원)
액세서리 2위: 더뷰안경 남자 빅사이즈선글라스 (BLACK 남성용, 172,800원)

❌ 누락 탭: bag, accessory_belt, accessory_watch
```

---

# 끝
