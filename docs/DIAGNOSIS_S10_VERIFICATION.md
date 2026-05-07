# SESSION 10 배포 검증 리포트 — "왜 정확도가 안 올랐나"

> **작성일:** 2026-05-01 (SESSION 10 배포 직후)
> **사용자 호소:** "정확도가 크게 올랐다고 생각이 들지는 않는다."
> **결론:** 사용자 인식 정확. SESSION 10의 코드는 정상 반영됐으나, **그 코드가 실제 사용자 트래픽에서 실행되지 않는다.**

---

## 1. 코드 반영 검증 — Fix 10-1 ~ 10-6 모두 ✅

직접 파일 확인 결과:

| Fix | 파일 | 적용 확인 |
|-----|------|---------|
| 10-1 color 0% | `mood_ranker.py:38` | ✅ `visual_sim * 0.95 + naver_rank_score * 0.05` |
| 10-2 dominant 비활성화 | `color_hist.py:99~100` | ✅ `return color_similarity(query_hist, product_hist)` (dominant 우회) |
| 10-3 quadrant 동적 임계값 | `quadrant_sort.py:36~41` | ✅ `score_threshold = max(FLOOR, score_median)` |
| 10-4 cluster color 안전장치 0 | `normalize.py:110, 117` | ✅ `'color_min_sim': 0.0` 양 카테고리 |
| 10-5 multi-crop 보존 | `gemini_detector.py:155~175` | ✅ `dict[str, list[Image.Image]]` |
| 10-5 호출자 평균화 | `routes_search.py:236~253` | ✅ 평탄화→임베딩→라벨별 평균 |
| 10-6 빈 탭 보호 + fallback | `routes_search.py:276~308, 437, 478~482` | ✅ `_ensure_tab_has_results` + 빈 탭 표시 |

**SESSION 10 patch 자체는 흠 없음.**

---

## 2. 라이브 네트워크 캡처 — 충격적 발견

같은 룩북 이미지 두 번 업로드 (해시 다른 이미지로 cache bust 포함):

```
[1차]
POST  /api/analyze                                      → 200 (CategoryAnalysisResult)
POST  /api/search/categories                            → 200 (Naver per category)
POST  cloi-api.kyoung361207.workers.dev/api/search?sort_by=quadrant  → 503 (cold start fail)

[2차]
POST  /api/analyze                                      → 200 (CategoryAnalysisResult)
POST  /api/search/categories                            → 200 (Naver per category)
```

**핵심 사실:**
- `/api/analyze`는 200을 반환하지만 응답 body는 **CategoryAnalysisResult** (`isV3Response()` false)
- 즉 Worker는 Cloud Run /api/search를 **타임아웃 30s 내 응답 못 받았거나 503으로 받음** → Gemini-only fallback 분기 진입
- UI는 `searchByCategories()` 호출 → Worker가 Naver API 직접 호출 → **FashionCLIP/색상/4분면 등 SESSION 9~10 작업 모두 미관여**

---

## 3. 결과 비교 — SESSION 10 전 vs 후

| 탭 | SESSION 10 이전 (1차 테스트) | SESSION 10 이후 (2차 테스트) | 개선? |
|----|-------------------------|---------------------------|------|
| 상의 1위 | 캣쯔 폴라나시 슬리브리스탑 (BLACK) 61,900원 | 닉앤니콜 TURTLENECK SLIM (BLACK) 14,030원 | **△ 색깔 여전히 BLACK** |
| 상의 2위 | 채핏 니키 텐션폴라 (WHITE) 17,800원 | 탑텐 메리노 립 터틀넥 (BLACK) 19,900원 | **△ 색깔 여전히 다름** |
| 하의 1위 | 모조에스핀 (BEIGE) 176,463원 | (재테스트 미수행) | — |
| **bag 탭** | **❌ 누락** | **❌ 여전히 누락** | **× 변화 없음** |
| 4 탭 라벨 | 상의/하의/아우터/액세서리 | 상의/하의/아우터/액세서리 | **× 동일** |

**해석:** 두 차례 모두 Worker fallback path를 보고 있다. SESSION 10 fix들은 Cloud Run 안에 있으나 호출이 안 됨.

---

## 4. 왜 그런가 — 진짜 production architecture

```
                   ┌─────────────┐
사용자 ─────────→  │ CF Pages UI │
                   └──────┬──────┘
                          │ 1) POST /api/analyze
                          ▼
                   ┌─────────────────────┐
                   │  CF Worker          │
                   │  (cloi-api)         │
                   └──────┬──────────────┘
                          │
              ┌───────────┴───────────┐
              │ 2) try Cloud Run      │
              │    /api/search        │
              │    (timeout 30s)      │
              ▼                       │
       ❌ cold start                  │ fallback
       (FastAPI + FashionCLIP         │
        모델 로드 60~120s)            │
              │                       ▼
              ▼              ┌────────────────────┐
          v3 응답?           │ Gemini analyzeImage│
          YES → tabs 반환    │ (Worker 자체 호출) │
          NO  → fallback     └─────────┬──────────┘
                                        │ CategoryAnalysisResult
                                        ▼
                              ┌─────────────────┐
                              │ UI calls        │
                              │ /api/search/    │
                              │   categories    │
                              └────────┬────────┘
                                       ▼
                              ┌─────────────────┐
                              │ Worker → Naver  │
                              │ API per category│
                              └────────┬────────┘
                                       ▼
                                   결과 노출
                                  (SESSION 9~10
                                   작업 미반영)
```

### 발생 빈도

- 첫 요청 (인스턴스 0): **거의 100% fallback path**
- 인스턴스 warm 상태에서 두 번째 이내 요청: **v3 path 가능**
- 30분 idle 후 다시 첫 요청: **다시 fallback**

→ **사용자는 거의 항상 fallback path 결과를 본다.**

---

## 5. 사용자 호소 정확 분석

### "정확도가 안 올랐다" — **사실**
- 사용자가 본 것은 SESSION 9 이전부터 동일한 Worker Gemini + Naver path
- SESSION 9, 9-B, 10의 `fashion-search/` 패치는 보지 못했음
- 즉, "안 올랐다"가 아니라 **"손댄 적 없다"**

### "CLIP 붙이고 효율 안 나옴" — **부분 사실**
- CLIP은 살아있지만 사용자 시야 밖
- 사용자가 보는 path에는 CLIP이 아예 없음
- 따라서 "CLIP 효과"를 체감할 기회 자체가 없었음

---

## 6. 즉시 결론 — 무엇부터 고쳐야 하나

**우선순위 재조정:**

| 우선 | 작업 | 이유 |
|------|------|------|
| 🥇 P0 | Worker `FASHION_PROMPT` 강화 + `searchByCategories` 색상 강제 | 사용자 99%가 보는 path |
| 🥇 P0 | Cloud Run `--min-instances=1` 설정 | v3 path를 실제로 가동 |
| 🥈 P1 | Worker timeout 30s → 45s + _source flag | v3/fallback 가시화 |
| 🥉 P2 | v3 path 색상 신호 올바르게 부활 (Lab + segmentation) | v3 정확도 진짜 향상 |

→ 이 우선순위로 **`docs/SESSION_11_PROMPT.md`** 작성됨.

---

## 7. 본질 교훈 (이번 세션 회고)

1. **"코드 반영" ≠ "production 적용"**
   - 코드 push, build, deploy 성공해도 사용자 path와 다르면 무관
   - 라이브 테스트 시 반드시 Network 탭으로 endpoint 확인

2. **Cold start는 production 인프라 결함**
   - 알고리즘 개선보다 영향 큰 경우가 흔함
   - min-instances=1은 비용($20~30/월)이지만 사용자 체감 정확도의 가장 큰 결정 변수

3. **Triple architecture (UI → Worker → Cloud Run) 의 함정**
   - Worker가 fallback 분기 가지면 Cloud Run 작업이 silent하게 무시됨
   - 사용자/개발자 둘 다 알기 어려움 → `_source` 같은 명시적 flag 필요

4. **항상 사용자 시야로 검증**
   - eval set 1.0 의미 없음 (eval은 v3 path 가정)
   - 라이브 정성 테스트 + Network 탭 = 진짜 진단

---

## 8. 다음 행동

→ **`docs/SESSION_11_PROMPT.md`** 정독 후 Track A → B → C 실행.

본 진단의 핵심 메시지:
> **"이번엔 Worker 코드부터 손대고 Cloud Run을 살려라.
> 그 다음에야 색상 신호가 의미 있다."**

---

# 끝
