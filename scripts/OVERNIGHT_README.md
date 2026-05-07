# 🌙 Overnight 실행 가이드

> 자기 전 한 번 실행 → 자동으로 SESSION 11 production 적용 + SESSION 12 Track B+C 진행
> 아침에 결과 확인

---

## 자기 전 (1분)

### 1. PowerShell 열기

`Win + X` → "Windows PowerShell" 또는 "터미널"

### 2. 한 줄 입력

```powershell
powershell -ExecutionPolicy Bypass -File "C:\Users\Alex KIM\Desktop\사업 프로젝트\인앱토스 1\scripts\overnight_run.ps1"
```

> **자동 prompt 선택:** 스크립트가 `scripts/session13_prompt.txt` 가 있으면 그걸 사용 (SESSION 13).
> 없으면 `session12_prompt.txt` fallback. 환경변수 `$env:CLOI_PROMPT_FILE` 로 override 가능.

### 3. 자기

- 스크립트가 30분~2시간 동안 자동 실행
- PowerShell 창은 그대로 두기 (닫으면 중단됨)
- 노트북 절전 모드 OFF 권장 (실행 중단됨)

---

## 스크립트가 하는 일

```
[STEP 1] npm run build
         ↓
         npx wrangler pages deploy dist --project-name=cloi
         ↓
         60초 propagation 대기
         ↓
[STEP 2] bash scripts/verify_deploy.sh fashion-search/eval/queries/q001.jpg
         ↓
         _source 필드 확인 → SESSION 11 진짜 production 진입 검증
         ↓
[STEP 3] claude --dangerously-skip-permissions "<SESSION 12 prompt>"
         ↓
         Claude Code 자율 실행:
           - Track A skip (이미 STEP 1에서 배포됨)
           - Track B: FASHION_PROMPT 에 gender/price_tier 추론 추가 + 재배포 + verify
           - Track C: softScoreProducts 함수 + 적용 + 재배포 + verify
           - Track D/E/F skip (사용자 승인 필요한 작업)
           - 5케이스 라이브 테스트 + logs/test_results.json 저장
           - git commit + push
           - SESSION_STATUS.md 정직하게 업데이트
         ↓
[STEP 4] logs/overnight_YYYYMMDD_HHMMSS.log 에 모든 출력 저장
         알람 (.claude/session-done.ps1) 실행
```

---

## 아침에 확인 (5분)

### 1. 로그 파일 열기

```
C:\Users\Alex KIM\Desktop\사업 프로젝트\인앱토스 1\logs\overnight_YYYYMMDD_HHMMSS.log
```

핵심 라인:
- `✅ Pages deploy OK` — STEP 1 성공
- `✅ verify 통과` — SESSION 11 진짜 production 적용
- `Claude Code exit: 0` — SESSION 12 자율 실행 성공

### 2. 라이브 테스트

브라우저로 https://cloi.pages.dev 접속 → 회색 케이블 니트 세트 이미지 업로드 → 결과 확인

기대:
- 1순위 가방이 200만원짜리 아님 (가격 추론 적용)
- 목걸이 검색에 남자 목걸이 1순위 X (성별 추론 적용)
- 응답 시간 5~10초 (cold start 없음)

### 3. SESSION_STATUS.md 확인

`SESSION_STATUS.md` 파일 열어서 SESSION 12 진행 상태 확인. Claude Code가 정직하게 작성:
- "Track B 완료 + verify 통과 ✅" — 잘 됨
- "Track B 시도 후 verify 실패 (사유: X) ⚠" — 다음 세션에서 사용자와 함께

---

## 만약 실패하면

### 시나리오 1: STEP 1 (Pages deploy) 실패

로그에서 wrangler 에러 메시지 확인. 가장 흔한 원인:
- Wrangler 인증 만료 → `cd server && npx wrangler login` 후 재시도
- 빌드 실패 → `npm install` 후 재시도

### 시나리오 2: STEP 2 (verify) 실패

`_source missing` 보이면 → Pages deploy 가 실제로 안 됐거나 캐시 문제
- 5분 더 기다린 후 수동으로 `bash scripts/verify_deploy.sh` 다시 실행
- 그래도 안 되면 CF Dashboard 에서 cloi.pages.dev 의 최근 배포 확인

### 시나리오 3: STEP 3 (Claude Code) 실패

로그에서 어디서 멈췄는지 확인. Claude Code는 위험 발견 시 깨끗하게 종료하도록 prompt 됐음. 다음 세션에서 사용자와 함께 진단.

---

## 비상 — 모든 것이 안 됐을 때

새 PowerShell에서 수동 진단:

```powershell
cd "C:\Users\Alex KIM\Desktop\사업 프로젝트\인앱토스 1"

# 1. Pages 수동 재배포
npm run build
npx wrangler pages deploy dist --project-name=cloi

# 2. 60초 후 verify
Start-Sleep -Seconds 60
bash scripts/verify_deploy.sh

# 3. 로그 살펴보기
Get-Content logs\overnight_*.log | Select-Object -Last 100
```

---

## 비용/안전 안내

- **Cloud Run min-instances=1**: 월 $20~30 발생 (이미 사용자가 한 번 승인). 변경 X
- **Claude Code API 호출**: Anthropic 플랜에 따라 다름. 30분 ~ 2시간 분량
- **Wrangler Pages deploy**: 무료 한도 내 (CF Pages 100,000 builds/month)
- **GCS / Cloud Run 호출**: 자동 작업으로 약간 발생 (1달러 미만 예상)

스크립트는 **사용자 승인이 필요한 작업 (gcloud, GitHub Actions secrets 설정 등) 모두 SKIP**. 안전.

---

## END
