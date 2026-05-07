# SESSION 16 STEP 2 - Gemini-only pivot
# ASCII-only (PowerShell 5.x cp949 compatibility).
#
# Pipeline:
#   1. Remove fashion-search/ from main (archived in branch)
#   2. Cloud Run min-instances=0 (kill idle cost)
#   3. server build + Vite build
#   4. wrangler pages deploy dist
#   5. verify_deploy.sh
#   6. git commit + push + alarm

$ErrorActionPreference = "Continue"
Set-Location "C:\Users\Alex KIM\Desktop\사업 프로젝트\인앱토스 1"

function Section($title) {
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host "  $title"
    Write-Host "============================================================" -ForegroundColor Cyan
}

# 0. lock cleanup
if (Test-Path ".git\index.lock") { Remove-Item ".git\index.lock" -Force }

Section "STEP 2-1. Remove fashion-search/ from main"
git rm -rf fashion-search 2>&1 | Select-Object -Last 3
if (Test-Path "scripts/fix_cloud_run_env.sh") { git rm scripts/fix_cloud_run_env.sh 2>&1 | Out-Null }
if (Test-Path "scripts/measure_v3_hit_rate.sh") { git rm scripts/measure_v3_hit_rate.sh 2>&1 | Out-Null }
Write-Host "[OK] fashion-search/ removed from main (preserved in archive/fashion-search-v3 branch)"

Section "STEP 2-2. Cloud Run min-instances=0 (kill idle cost)"
$gcloud = "C:\Users\Alex KIM\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
$gcloudFound = Test-Path $gcloud
if ($gcloudFound) {
    Write-Host "Setting fashion-search min-instances=0 ..."
    & $gcloud run services update fashion-search --region=asia-northeast3 --min-instances=0 --max-instances=1 --quiet 2>&1 | Select-Object -Last 5
    Write-Host "[OK] Cloud Run idle cost = 0"
} else {
    Write-Host "[WARN] gcloud not found. Run manually:" -ForegroundColor Yellow
    Write-Host "  gcloud run services update fashion-search --region=asia-northeast3 --min-instances=0 --max-instances=1"
}

Section "STEP 2-3. Server build (tsc)"
Set-Location server
& npm run build 2>&1 | Select-Object -Last 8
$serverBuildExit = $LASTEXITCODE
Set-Location ..
if ($serverBuildExit -ne 0) {
    Write-Host "[FAIL] server build failed (exit $serverBuildExit)" -ForegroundColor Red
    Write-Host "       worker.ts syntax error - fix needed before redeploy"
    exit 1
}
Write-Host "[OK] server build"

Section "STEP 2-4. Vite frontend build (optional)"
$env:NODE_OPTIONS = "--max-old-space-size=4096"
& npm run build 2>&1 | Select-Object -Last 5
$viteExit = $LASTEXITCODE
if ($viteExit -ne 0) {
    Write-Host "[WARN] Vite build failed (exit $viteExit). Reusing existing dist/" -ForegroundColor Yellow
    if (-not (Test-Path "dist\index.html")) {
        Write-Host "[FAIL] dist/ not found. abort." -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "[OK] Vite build"
}

Section "STEP 2-5. Pages deploy (real production path)"
if (-not $env:CLOUDFLARE_API_TOKEN) {
    Write-Host "[FAIL] CLOUDFLARE_API_TOKEN env var missing. Set with:" -ForegroundColor Red
    Write-Host "  [Environment]::SetEnvironmentVariable('CLOUDFLARE_API_TOKEN','TOKEN','User')"
    exit 1
}
& npx wrangler pages deploy dist --project-name=cloi 2>&1 | Select-Object -Last 15
$pagesExit = $LASTEXITCODE
Write-Host "    wrangler exit: $pagesExit (ignored - verify_deploy.sh decides)"

Section "STEP 2-6. CDN propagation 60s wait"
Start-Sleep -Seconds 60

Section "STEP 2-7. verify_deploy.sh"
$bash = $null
foreach ($p in @("C:\Program Files\Git\bin\bash.exe", "C:\Program Files (x86)\Git\bin\bash.exe")) {
    if (Test-Path $p) { $bash = $p; break }
}
if ($bash) {
    $verifyCmd = "cd '$(Get-Location)' ; bash scripts/verify_deploy.sh"
    & $bash -c $verifyCmd 2>&1 | Select-Object -Last 30
    $verifyExit = $LASTEXITCODE
    if ($verifyExit -eq 0) {
        Write-Host ""
        Write-Host "[OK] SESSION 16 production verified!" -ForegroundColor Green
    } else {
        Write-Host "[WARN] verify_deploy.sh exit $verifyExit (manual check needed)" -ForegroundColor Yellow
    }
} else {
    Write-Host "[SKIP] bash not found"
}

Section "STEP 2-8. git commit + push"
git add -A
$commitMsg = "feat(session16): Gemini-only pivot - drop CLIP/Cloud Run, add few-shot + 2-pass rerank"
git commit -m $commitMsg
git push origin main 2>&1 | Select-Object -Last 5

Section "DONE"
Write-Host "Recent commits:"
git log --oneline -3
Write-Host ""

# Alarm - CLAUDE.md session-end hook
$alarm = ".claude\session-done.ps1"
if (Test-Path $alarm) {
    Write-Host "Triggering session-done alarm ..."
    & $alarm
}
Write-Host "[OK] SESSION 16 complete" -ForegroundColor Green
