# SESSION 16 STEP 1: archive/fashion-search-v3 브랜치 생성 + push
# 목적: fashion-search/ + worker.ts CLIP path 코드를 archive 브랜치에 보존
# 그 후 main에서 fashion-search/ 제거 + worker.ts 정리 가능

$ErrorActionPreference = "Continue"
Set-Location "C:\Users\Alex KIM\Desktop\사업 프로젝트\인앱토스 1"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  SESSION 16 STEP 1 — Archive Branch Creation"
Write-Host "============================================================" -ForegroundColor Cyan

# 0. lock 파일 정리
if (Test-Path ".git\index.lock") {
    Write-Host "[0] Removing stale .git/index.lock ..."
    Remove-Item ".git\index.lock" -Force
}

# 1. user config
git config user.email "kyoung361207@gmail.com"
git config user.name "kyoung soo"

# 2. 현재 변경사항 스냅샷 commit (archive 보존용)
Write-Host ""
Write-Host "[1] Staging all changes (gitignore 적용됨)..."
git add -A
$staged = (git diff --cached --name-only | Measure-Object -Line).Lines
Write-Host "    staged $staged files"

if ($staged -gt 0) {
    Write-Host "[2] Committing snapshot ..."
    git commit -m "snapshot: SESSION 15 state before gemini-only pivot"
} else {
    Write-Host "[2] No changes to commit, skipping"
}

# 3. archive 브랜치 생성 (현재 HEAD에서 분기)
Write-Host ""
Write-Host "[3] Creating archive/fashion-search-v3 branch ..."
git branch -f archive/fashion-search-v3 HEAD
Write-Host "    archive branch points to: $(git rev-parse --short archive/fashion-search-v3)"

# 4. push
Write-Host ""
Write-Host "[4] Pushing main + archive/fashion-search-v3 to origin ..."
git push origin main 2>&1 | Out-String | Write-Host
git push origin archive/fashion-search-v3 2>&1 | Out-String | Write-Host

# 5. 검증
Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  결과 확인"
Write-Host "============================================================" -ForegroundColor Green
Write-Host "현재 브랜치: $(git branch --show-current)"
Write-Host "최근 커밋:"
git log --oneline -3
Write-Host ""
Write-Host "Archive 브랜치 (보존):"
git log --oneline archive/fashion-search-v3 -3
Write-Host ""
Write-Host "[OK] STEP 1 완료. 다음: Claude가 fashion-search/ 제거 + worker.ts 정리"
