# SESSION 8 PATCH A: Gemini 호출 병렬화로 응답 시간 단축

> **목표:** 검색 응답 시간 8~12초 → 4~6초 단축
> **방법:** Gemini detect_regions 호출을 analyze_style + classify와 병렬 실행
> **트레이드오프:** 없음 (정확도/비용 동일, 시간만 단축)

---

## 작업 내용

### 1. `fashion-search/apps/api/routes_search.py` 수정

**현재 (직렬, 라인 209~231):**
```python
# 4. 병렬: Gemini 멀티아이템 탐지 + FashionCLIP 속성 추출
try:
    attr_coro = (
        asyncio.to_thread(attribute_classifier.classify_all, pil_image)
        if attribute_classifier
        else _dummy_attributes()
    )
    style_ctx, attributes = await asyncio.gather(
        analyze_style(image_bytes, mime_type=mime),
        attr_coro,
    )
except Exception as exc:
    logger.error("[routes_search] 분석 실패: %s", exc)
    raise HTTPException(status_code=502, detail="스타일 분석 서비스에 일시적인 오류가 발생했습니다.")

if not style_ctx.detected_items:
    raise HTTPException(
        status_code=422,
        detail="의류/잡화 아이템을 감지할 수 없습니다. 패션 이미지를 업로드해 주세요.",
    )

# 5. 쿼리 임베딩 (Gemini crop 적용)
query_emb: np.ndarray = await _get_query_embedding(embedder, pil_image, image_bytes, mime)
```

**변경 후 (병렬 — Gemini 3개 호출 + FashionCLIP 속성 분류 모두 동시 실행):**
```python
# 4. 병렬: analyze_style + attribute_classifier + Gemini bbox detect (모두 동시)
from src.preprocess.gemini_detector import detect_regions, blur_face_regions, crop_garment_regions

try:
    attr_coro = (
        asyncio.to_thread(attribute_classifier.classify_all, pil_image)
        if attribute_classifier
        else _dummy_attributes()
    )
    style_ctx, attributes, detection = await asyncio.gather(
        analyze_style(image_bytes, mime_type=mime),
        attr_coro,
        detect_regions(image_bytes, mime_type=mime),
        return_exceptions=False,  # detect 실패해도 fallback 가능하도록 아래에서 처리
    )
except Exception as exc:
    logger.error("[routes_search] 분석 실패: %s", exc)
    raise HTTPException(status_code=502, detail="스타일 분석 서비스에 일시적인 오류가 발생했습니다.")

if not style_ctx.detected_items:
    raise HTTPException(
        status_code=422,
        detail="의류/잡화 아이템을 감지할 수 없습니다. 패션 이미지를 업로드해 주세요.",
    )

# 5. 쿼리 임베딩 — 미리 받아둔 detection 결과 활용 (Gemini 추가 호출 X)
query_emb: np.ndarray = await _build_query_emb_from_detection(
    embedder, pil_image, detection
)
```

### 2. `_get_query_embedding` 함수 분리/리팩토링

**기존 `_get_query_embedding` 함수를 두 함수로 분리:**

```python
async def _build_query_emb_from_detection(
    embedder,
    pil_image: Image.Image,
    detection,  # DetectionResult or None (실패 시)
) -> np.ndarray:
    """미리 받아둔 detection 결과로 query embedding 생성.
    
    detection이 None이거나 boxes 비어있으면 전체 이미지 embedding으로 fallback.
    """
    try:
        if detection is None or not detection.boxes:
            return await asyncio.to_thread(embedder.embed_single, pil_image)
        
        from src.preprocess.gemini_detector import (
            blur_face_regions,
            crop_garment_regions,
        )
        masked_image = blur_face_regions(pil_image, detection.boxes)
        garment_crops = crop_garment_regions(masked_image, detection.boxes)
        
        if garment_crops:
            crop_embs = await asyncio.to_thread(
                embedder.embed, list(garment_crops.values())
            )
            query_emb = np.mean(crop_embs, axis=0)
            query_emb = query_emb / (np.linalg.norm(query_emb) + 1e-8)
            return query_emb
        
        # crop 비어있으면 전체 이미지
        return await asyncio.to_thread(embedder.embed_single, masked_image)
    except Exception as exc:
        logger.warning("[routes_search] query emb 생성 실패, fallback: %s", exc)
        return await asyncio.to_thread(embedder.embed_single, pil_image)


# 기존 _get_query_embedding은 그대로 둬도 되지만, 사용 안 하면 삭제 가능
# (또는 deprecated 처리)
```

**중요 — `asyncio.gather` 에러 처리:**
- `return_exceptions=False` (기본): 하나라도 실패 시 전체 raise → 현재 코드와 동일 동작
- `return_exceptions=True`로 바꿀 경우: detect 실패해도 분석 진행 가능

**권장:** detection은 fallback 가능하니까 detect만 따로 try/except로 감싸기:

```python
# 더 안전한 패턴 (recommended):
try:
    attr_coro = (
        asyncio.to_thread(attribute_classifier.classify_all, pil_image)
        if attribute_classifier
        else _dummy_attributes()
    )
    
    detect_coro = _safe_detect_regions(image_bytes, mime)  # 실패 시 None 반환
    
    style_ctx, attributes, detection = await asyncio.gather(
        analyze_style(image_bytes, mime_type=mime),
        attr_coro,
        detect_coro,
    )
except Exception as exc:
    logger.error("[routes_search] 분석 실패: %s", exc)
    raise HTTPException(status_code=502, detail="...")


async def _safe_detect_regions(image_bytes: bytes, mime: str):
    """detect_regions의 안전 wrapper — 실패 시 None 반환."""
    try:
        from src.preprocess.gemini_detector import detect_regions
        return await detect_regions(image_bytes, mime_type=mime)
    except Exception as exc:
        logger.warning("[routes_search] Gemini detect 실패: %s", exc)
        return None
```

### 3. 검증

수정 후 로컬에서 import 검증:
```bash
cd "C:\Users\Alex KIM\Desktop\사업 프로젝트\인앱토스 1\fashion-search"
.venv/Scripts/python -c "from apps.api.routes_search import search; print('OK')"
```

### 4. 배포

```bash
cd "C:\Users\Alex KIM\Desktop\사업 프로젝트\인앱토스 1"
git add fashion-search/apps/api/routes_search.py
git commit -m "perf: parallelize Gemini detect with analyze_style + classify"

# Cloud Run 배포
$env:GOOGLE_API_KEY = (Get-Content fashion-search/.env | Select-String '^GOOGLE_API_KEY=' | ForEach-Object { $_.Line.Split('=')[1] })
$env:ADMIN_TOKEN = (Get-Content fashion-search/.env | Select-String '^ADMIN_TOKEN=' | ForEach-Object { $_.Line.Split('=')[1] })
$env:NAVER_CLIENT_ID = (Get-Content fashion-search/.env | Select-String '^NAVER_CLIENT_ID=' | ForEach-Object { $_.Line.Split('=')[1] })
$env:NAVER_CLIENT_SECRET = (Get-Content fashion-search/.env | Select-String '^NAVER_CLIENT_SECRET=' | ForEach-Object { $_.Line.Split('=')[1] })
bash deploy.sh
```

`bash deploy.sh`가 안 되면 직접 명령어:
```bash
gcloud run deploy fashion-search \
  --project=cloi-fashion-search \
  --source=fashion-search/ \
  --region=asia-northeast3 \
  --platform=managed \
  --allow-unauthenticated \
  --memory=2Gi \
  --cpu=2 \
  --min-instances=0 \
  --max-instances=3 \
  --port=8080 \
  --set-env-vars="EMBEDDER_NAME=fashion_clip,KMP_DUPLICATE_LIB_OK=TRUE,GOOGLE_API_KEY=$env:GOOGLE_API_KEY,ADMIN_TOKEN=$env:ADMIN_TOKEN,DEBUG=false,NAVER_CLIENT_ID=$env:NAVER_CLIENT_ID,NAVER_CLIENT_SECRET=$env:NAVER_CLIENT_SECRET"
```

### 5. 배포 검증

```bash
# Cloud Run health
curl https://fashion-search-dibvogjuma-du.a.run.app/health

# 응답 시간 측정 (실제 이미지로)
$start = Get-Date
curl -X POST https://fashion-search-dibvogjuma-du.a.run.app/api/search -F "file=@test.jpg" > result.json
$elapsed = (Get-Date) - $start
Write-Host "Latency: $($elapsed.TotalSeconds) seconds"
```

**기대 결과:**
- 이전: 8~12초
- 패치 후: 4~6초
- result.json에 `total_latency_ms` 필드도 확인

### 6. 프론트엔드 (변경 없음)

CF Worker / CF Pages는 백엔드만 바뀌므로 재배포 불필요.

### 7. 최종 git push

```bash
git push origin main
```

---

## 성공 기준

- [ ] `routes_search.py`가 `analyze_style`, `attribute_classifier`, `detect_regions`를 모두 `asyncio.gather`로 병렬 호출
- [ ] `_safe_detect_regions` wrapper 추가 (detection 실패 시 None 반환)
- [ ] `_build_query_emb_from_detection` 함수 추가 (미리 받은 detection 결과 활용)
- [ ] Cloud Run 배포 성공
- [ ] /health 응답 정상
- [ ] 실제 이미지 응답 시간 4~6초 (warm 기준)
- [ ] git push 완료

---

## 작업 후 사용자 테스트

배포 끝나면 사용자에게:
- URL: https://cloi.pages.dev
- 같은 이미지로 다시 테스트해서 시간 비교
- 응답 시간 / 정확도 변화 피드백
