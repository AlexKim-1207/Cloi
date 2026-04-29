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
