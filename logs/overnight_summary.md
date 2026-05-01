# SESSION 12 overnight 결과 요약

## 실행 결과 요약 (2026-05-02)

### ✅ 완료
1. **Pages 배포 정상화 (Track A)**
   - 문제: rollup v4 native binary + Node.js v24 → STATUS_STACK_BUFFER_OVERRUN 크래시
   - 해결: esbuild로 프론트엔드 빌드 대체 (`dist/assets/index-D4XYTDGJ.js`)
   - `wrangler pages deploy dist --project-name=cloi` 성공
   - verify_deploy.sh exit 0 통과: `_source=worker_gemini` ✅

2. **FASHION_PROMPT outfit 추론 (Track B)**
   - 4단계 추가: gender / price_tier / price_range_estimate / season / vibe
   - q003.jpg (남성 outfit): gender=male(0.95), price_tier=budget ✅
   - q010.jpg (룩북): gender=unisex(0.70), price_tier=mid ✅

3. **softScoreProducts 미들웨어 (Track C)**
   - 성별/가격/색상/광고 soft multiplier
   - /api/search/categories에 outfit_meta 전달 파이프라인 완성

4. **verify_deploy.sh 버그 수정**
   - Python cp949 기본 인코딩으로 UTF-8 JSON 파싱 실패하던 문제 수정
   - curl 직접 파일 저장으로 변경

### ⏭️ 다음 세션 우선순위

1. **Track D: 다양성 보장** (diversifyTopN)
   - top 5에 같은 브랜드 2개 이상 노출 방지
   - 구현 30분 → Pages 재배포

2. **Track E: UX 개선**
   - `_source` 배지 (FashionCLIP vs Gemini)
   - 의도 토글 (같은 컨셉/더 싸게/같은 색/업그레이드)
   - outfit_meta 표시 (성별, 가격대, 분위기)
   - 주의: UI 수정 시 esbuild 대신 vite 빌드 필요 → vite 빌드 크래시 해결 선행

3. **Track F: GitHub Actions CI/CD**
   - deploy + verify 자동화
   - 매시간 health monitor
   - vite 빌드 크래시 근본 해결 (rollup native vs wasm-node 전환)

### ⚠️ 알려진 이슈

1. **vite 빌드 크래시**: Node.js v24 + rollup v4 native binary 호환성 문제
   - 현재: esbuild로 대체 (프론트엔드 빌드)
   - 장기: rollup 업그레이드 또는 Node.js 버전 다운그레이드 또는 ROLLUP_NATIVE=0 설정

2. **소형 이미지 IMAGE_QUALITY**: q004/q005/q007.jpg 등 소형 이미지 → 에러 (예상 동작)

3. **vibe 한글 깨짐**: logs/test_results.json에서 Python terminal cp949 출력 이슈 (파일 내용은 정상)
