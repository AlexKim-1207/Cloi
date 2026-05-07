# Cloi Project — Claude 작업 규칙

## 🔋 토큰 절약 규칙 (필수 준수)

### 파일 읽기
- **Grep 우선** — 특정 심볼/패턴 찾을 때 Read 대신 Grep
- **Read offset/limit 사용** — 전체 파일 필요 없으면 필요한 줄만
- **절대 금지**: 탐색 목적으로 100줄+ 파일 전체 Read
- 패턴: `Read(file, offset=N, limit=50)` > `Read(file)` 전체

### 도구 호출 배치
- 독립적 작업은 **한 메시지에 여러 도구 동시 호출**
- 예: 파일 3개 읽기 → 순차 X, 한 번에 3개 병렬 호출

### 응답 길이
- 코드 블록 외 설명 최소화
- 산출물(파일, 코드) 중심. 설명 나중

### 컨텍스트 관리
- **STEP 경계마다 `/compact` 실행** (EXECUTION_PLAN.md STEP 1→2, 2→3, 3→4 전환 시)
- 불필요한 탐색 루프 금지 — 확신 없으면 Grep 먼저, 없으면 Read
- 이미 읽은 파일 재읽기 금지 (메모리 활용)

---

## 🏗️ 프로젝트 구조

```
인앱토스 1/
├── src/                    # 프론트엔드 (React+TS)
├── server/                 # 백엔드 (Express, Cloudflare Workers)
├── functions/              # Cloudflare Pages Functions
├── fashion-search/         # Phase 2 ML 파이프라인 (FastAPI+Python)
│   ├── apps/api/           # FastAPI 엔드포인트
│   ├── src/                # 핵심 모듈 (vision/embedding/search/llm/cache)
│   ├── scripts/            # 빌드/테스트 스크립트
│   ├── eval/               # 정확도 평가
│   └── docs/EXECUTION_PLAN.md  # ← 다음 작업 계획서
└── .claude/settings.json  # 권한 설정
```

## 🎯 현재 작업 목표

`fashion-search/docs/EXECUTION_PLAN.md` 기준으로 STEP 1~4 실행.
- STEP 1: 3종 임베더 추상화 (OpenCLIP/FashionCLIP/Marqo)
- STEP 2: 카탈로그 500장 + FAISS 인덱스 3세트
- STEP 3: Ground Truth + A/B 측정
- STEP 4: 우승 모델 채택 + 배포

## ⚡ Gemini 모델
모든 Gemini 호출 = `gemini-2.5-flash` 고정

## 🔔 세션 종료 필수 절차 (CRITICAL — 반드시 마지막에 실행)

**모든 세션은 아래 3단계로 종료. 빠뜨리면 규칙 위반.**

### 1. git commit
```bash
git add -A
git commit -m "feat: sessionN 완료 - [작업 요약]"
```

### 2. SESSION_STATUS.md 업데이트
다음 형식으로 파일 상단 업데이트:
```
## 현재 상태
- 완료 세션: SESSION N
- 다음 세션: SESSION N+1
```
완료 세션 ✅, 산출물 체크박스 체크, 다음 세션 명령어 정확히 기재.

### 3. 알람 실행 (필수)
```bash
/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe -ExecutionPolicy Bypass -File "/c/Users/Alex KIM/Desktop/사업 프로젝트/인앱토스 1/.claude/session-done.ps1"
```
→ 이 명령으로 팝업 알람 발생. 유저가 세션 완료 확인.
→ **Stop hook이 자동으로도 실행되지만, 명시적으로도 직접 실행할 것.**

### 종료 순서 요약
```
git commit → SESSION_STATUS.md 업데이트 → git commit → 알람 실행
```

---

## 🚫 금지
- 워크트리 내부에 중요 파일 생성 (`.claude/worktrees/` 경로 금지)
- `rm -rf` 확인 없이 src/ 하위 삭제
- 카탈로그/인덱스 없이 eval 실행
- 알람 실행 없이 세션 종료
- **`wrangler deploy` / `bash deploy.sh` 후 `verify_deploy.sh` 실행 없이 SESSION_STATUS.md "완료" 표기**

---

## 🚀 배포 검증 규칙 (CRITICAL — 반복 실수 차단)

### 배경 (SESSION 11에서 발생한 두 사건)
**사건 1 (가짜 deploy 보고):** SESSION 11에서 Worker 코드 변경 + `wrangler deploy` 명령 실행했으나 **실제로는 production에 반영 안 됨**. SESSION_STATUS.md엔 "Track A 배포 완료"로 자기 보고. 사용자가 며칠간 옛 코드 응답 보고 "정확도 안 올랐다" 호소.

**사건 2 (잘못된 worker deploy):** SESSION 11/12 진단 중 발견 — 사용자 트래픽은 **`cloi-api` Worker가 아닌 Cloudflare Pages Function** 으로 흐름. `functions/api/[[route]].ts` 가 catch-all로 `worker.ts` 를 import. 즉 `cloi.pages.dev/api/*` 모든 요청은 Pages 빌드의 worker.ts 코드로 처리됨. **`npx wrangler deploy` (cloi-api) 는 사용 안 되는 worker에 deploy하는 의미 없는 작업.** 진짜 production 배포는 `npx wrangler pages deploy dist`.

**원인 정리:**
- wrangler 인증 만료 또는 deploy 명령 silent fail — Claude가 stderr 무시 + 응답 검증 안 함
- 그리고 worker.ts 변경 후 `wrangler pages deploy dist` 안 함 → Pages site는 OLD build 그대로

### ⚠️ 진짜 Production Path (반드시 기억)

```
사용자 → cloi.pages.dev/api/analyze
         ↓
       functions/api/[[route]].ts  ← Pages Function (catch-all)
         ↓ import app from '../../server/src/worker'
       worker.ts 코드 실행 (Pages build에 포함된 버전)
```

→ **`server/src/worker.ts` 수정 시 반드시 다음 두 단계 모두 실행:**
```bash
# 1. (선택) Worker 단독 배포 — legacy. 안 해도 됨.
cd server && npx wrangler deploy && cd ..

# 2. ★ 필수 ★ Pages 재빌드 + 재배포 — 이게 진짜 production
npm run build
npx wrangler pages deploy dist --project-name=cloi
```

→ **Pages 재배포 안 하면 worker.ts 변경이 production에 들어가지 않음. SESSION 9~11 모두 이 함정에 걸림.**

### 영구 차단 규칙

#### 1. 모든 배포 명령 후 즉시 검증
```bash
# ★ Worker 코드 (worker.ts) 수정 후 — Pages 재배포가 진짜 production
npm run build
npx wrangler pages deploy dist --project-name=cloi
sleep 30   # Pages CDN propagation
bash scripts/verify_deploy.sh        # cloi.pages.dev 응답으로 검증

# (legacy, 옵션) cloi-api Worker 단독 배포 — Pages Function 안 쓰는 path 만 영향
cd server && npx wrangler deploy && cd ..

# Cloud Run 배포 후
bash fashion-search/deploy.sh
bash scripts/verify_deploy.sh        # v3 path 적중 확인
```

#### 2. `verify_deploy.sh` 실패 시 행동
- ❌ SESSION_STATUS.md "완료" 표기 금지
- ❌ git commit 메시지 "deploy 완료" 표현 금지
- ❌ 다음 작업 진행 금지
- ✅ 실패 원인 진단 (인증 / 빌드 에러 / wrangler.toml 경로) 후 재배포
- ✅ 재배포 + verify 통과까지 반복

#### 3. 수동 응답 검증 (verify_deploy.sh 실패 시 보조)
```bash
# Worker가 새 코드로 응답하는지 직접 확인
curl -X POST https://cloi-api.kyoung361207.workers.dev/api/analyze \
  -H "Content-Type: application/json" \
  -d "{\"imageBase64\":\"$(base64 -w 0 < fashion-search/eval/queries/q001.jpg)\",\"mimeType\":\"image/jpeg\"}" \
  | python -m json.tool | head -30

# 응답에서 확인:
# - _source 필드 ('v3' 또는 'worker_gemini') ← SESSION 11 적용 증거
# - categories 키 8개 (top_outer/top_inner/...) ← SESSION 11 schema 증거
# - gender, price_tier 필드 ← SESSION 12 적용 증거
```

#### 4. SESSION_STATUS.md 정직 규칙
"배포 완료" 적기 전 반드시 verify_deploy.sh 출력 확인.
배포 시도했으나 검증 실패 시 다음 형식 사용:
```
- Cloud Run: 배포 완료 + verify_deploy.sh 통과 ✅
- Worker: 배포 시도 후 verify 실패 (사유: wrangler 인증 만료) ⚠ 다음 세션 first work
```

#### 5. CI/CD 자동화 도입 (장기)
GitHub Actions로 `push to main` → 자동 wrangler deploy + verify_deploy.sh 실행.
실패 시 PR comment로 알림. 수동 deploy 의존 영구 제거.

### 추가 도구
- `scripts/verify_deploy.sh` — Worker + Cloud Run 응답/latency/schema 자동 검증
- `scripts/live_qa_*.py` — 5케이스 lookbook 정성 평가 자동화 (SESSION 12+ 추가)
