# STEP1 Analysis — SESSION 6

## 현재 구조 요약

### Python API (Cloud Run)
- **파이프라인**: 이미지 → Gemini StyleContext → parallel_search (카테고리별) → CLIP filter → SearchResponse
- **StyleContext**: overall_style + mood_tags + items(ItemDetail) + confidence
- **응답**: `results: dict[category, list[ProductCard]]` (탭 없음, 단순 카테고리별)
- **랭킹**: CLIP 유사도만. 무드/가격 미반영

### Worker (CF)
- `/api/analyze`: Gemini 직접 호출 OR Python API 프록시 (analyze.ts via Express dev server)
- `/api/search-image`: base64 → multipart → Cloud Run 프록시
- `/api/search`: 네이버 텍스트 검색 (더보기용)
- click 라우트 없음

### 프론트엔드
- `SearchResponseV2.results: Record<string, ProductCardV2[]>` 구조 처리 중
- 탭: 6개 고정 FashionCategory (top/bottom/shoes/outer/bag/accessory)
- 매치스코어 없음, 가격만 표시

## 수정 계획

| 파일 | 변경 |
|------|------|
| `fashion_clip_embedder.py` | `encode_text()` + `embed_single()` 추가 |
| `src/llm/schemas.py` | DetectedItem + MultiItemStyleContext 추가 |
| `src/llm/style_analyzer.py` | 멀티아이템 탐지 프롬프트 + 새 스키마 |
| `src/ranking/attribute_classifier.py` | 신규: FashionCLIP zero-shot 분류 |
| `src/ranking/mood_ranker.py` | 신규: 복합 소팅 |
| `src/storage/user_image_store.py` | 신규: GCS 저장 |
| `src/logging/search_logger.py` | click 스키마 확장 |
| `src/search/parallel_search.py` | `search_all_items_v2()` 추가 |
| `apps/api/schemas.py` | 새 ProductCard/TabSection/SearchResponse |
| `apps/api/main.py` | AppState에 attribute_classifier 추가 |
| `apps/api/routes_search.py` | 전면 재구성 |
| `server/src/worker.ts` | sort_by 전달 + /api/click 추가 |
| `src/types/index.ts` | v3 타입 추가 |
| `src/services/api.ts` | search/click API 업데이트 |
| `src/pages/ResultPage.tsx` | 탭 UI + 매칭 뱃지 + 소팅 |

## 핵심 우려사항
1. FashionCLIPEmbedder encode_text: transformers CLIPModel.get_text_features() 사용
2. clip_filter.py는 OpenCLIP 사용 중 → 새 파이프라인은 FashionCLIP 사용
3. 기존 /api/analyze 경로는 유지, 새 탭 구조 자동 감지 (tabs 필드 존재 여부)
4. 캐시: sort_by 제외한 relevance 순서로 저장, 응답 시 재정렬
