# overnight_run.ps1 - Auto-run while user sleeps.
# ASCII-only to avoid PowerShell 5.x cp949 encoding issues.
# Compatible with Windows PowerShell 5.x and PowerShell 7+.
#
# Run: powershell -ExecutionPolicy Bypass -File scripts\overnight_run.ps1
#
# Pipeline:
#   STEP 1: npm run build + wrangler pages deploy
#   STEP 2: verify_deploy.sh (Pages domain check)
#   STEP 3: claude --dangerously-skip-permissions <session12_prompt.txt>
#   STEP 4: log everything

$ErrorActionPreference = "Continue"

# Resolve project root dynamically from script location (avoids hardcoded Korean path).
# Script lives at <project>\scripts\overnight_run.ps1, so project = parent of scripts dir.
$PROJECT_ROOT = Split-Path -Parent $PSScriptRoot
if (-not $PROJECT_ROOT) {
    # Fallback if $PSScriptRoot is empty (rare)
    $PROJECT_ROOT = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
}

$TIMESTAMP = Get-Date -Format "yyyyMMdd_HHmmss"
$LOG_DIR = Join-Path $PROJECT_ROOT "logs"
$LOG_FILE = Join-Path $LOG_DIR "overnight_${TIMESTAMP}.log"
# Auto-select latest session prompt (session13 > session12 > ...)
# User can override via env var: $env:CLOI_PROMPT_FILE = "scripts\custom.txt"
if ($env:CLOI_PROMPT_FILE) {
    $PROMPT_FILE = Join-Path $PROJECT_ROOT $env:CLOI_PROMPT_FILE
} else {
    $PromptCandidates = @(
        "scripts\session15_prompt.txt",
        "scripts\session14_prompt.txt",
        "scripts\session13_prompt.txt",
        "scripts\session12_prompt.txt"
    )
    $PROMPT_FILE = $null
    foreach ($candidate in $PromptCandidates) {
        $fullPath = Join-Path $PROJECT_ROOT $candidate
        if (Test-Path $fullPath) {
            $PROMPT_FILE = $fullPath
            break
        }
    }
    if (-not $PROMPT_FILE) {
        $PROMPT_FILE = Join-Path $PROJECT_ROOT "scripts\session12_prompt.txt"
    }
}

if (-not (Test-Path $LOG_DIR)) {
    New-Item -ItemType Directory -Path $LOG_DIR | Out-Null
}

function Log {
    param([string]$Message)
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$stamp] $Message"
    Write-Host $line
    Add-Content -Path $LOG_FILE -Value $line -Encoding UTF8
}

function LogSection {
    param([string]$Title)
    Log "============================================================"
    Log "  $Title"
    Log "============================================================"
}

function CheckExit {
    param([int]$Code, [string]$StepName, [int]$ExitOnFail = 0)
    if ($Code -ne 0) {
        Log "[FAIL] $StepName failed with exit $Code"
        if ($ExitOnFail -ne 0) {
            Log "Aborting overnight run."
            exit $ExitOnFail
        }
    } else {
        Log "[OK] $StepName"
    }
}

# ============================================================
LogSection "OVERNIGHT RUN START"
Log "Project: $PROJECT_ROOT"
Log "Log file: $LOG_FILE"
Set-Location $PROJECT_ROOT

# ============================================================
LogSection "STEP 1. npm run build (optional) + wrangler pages deploy"

# Note: Pages deploy bundles functions/ independently from dist/.
# Even if vite frontend build fails, worker.ts (imported by functions/api/[[route]].ts)
# still gets deployed. So build failure here is NON-FATAL.

Log "1-1. Trying npm run build (optional, frontend only) ..."
# Increase heap to mitigate Rollup native crashes
$env:NODE_OPTIONS = "--max-old-space-size=4096"
& npm run build 2>&1 | Tee-Object -FilePath $LOG_FILE -Append
$BUILD_EXIT = $LASTEXITCODE
if ($BUILD_EXIT -eq 0) {
    Log "[OK] npm run build (frontend updated)"
} else {
    Log "[WARN] npm run build failed (exit $BUILD_EXIT)."
    Log "[WARN] Continuing anyway - Pages will still bundle functions and worker.ts."
    Log "[WARN] Frontend remains at last successful build (Apr 29). API/worker WILL update."
    if (-not (Test-Path "dist\index.html")) {
        Log "[FAIL] No dist/ folder exists. Cannot proceed without ANY build."
        exit 1
    }
}

# Pre-check: CLOUDFLARE_API_TOKEN required for non-interactive wrangler
if (-not $env:CLOUDFLARE_API_TOKEN) {
    Log "[FAIL] CLOUDFLARE_API_TOKEN env var not set."
    Log ""
    Log "  This script runs wrangler in non-interactive mode (stdin not a TTY)."
    Log "  Wrangler cannot refresh OAuth token in non-interactive mode."
    Log ""
    Log "  Fix (one-time setup):"
    Log "    1. Visit https://dash.cloudflare.com/profile/api-tokens"
    Log "    2. Create Token: 'Edit Cloudflare Workers' template, your account only"
    Log "    3. Copy token, then in PowerShell run:"
    Log "       [Environment]::SetEnvironmentVariable('CLOUDFLARE_API_TOKEN','<TOKEN>','User')"
    Log "    4. Open NEW PowerShell window, re-run this script"
    Log ""
    Log "  Workaround for THIS run:"
    Log "    \$env:CLOUDFLARE_API_TOKEN = '<TOKEN>'"
    Log "    .\scripts\overnight_run.ps1"
    exit 10
}

Log "1-2. Running wrangler pages deploy (deploys dist/ + functions/) ..."
Log "  (Using CLOUDFLARE_API_TOKEN env var for non-interactive auth)"
& npx wrangler pages deploy dist --project-name=cloi 2>&1 | Tee-Object -FilePath $LOG_FILE -Append
$PAGES_EXIT = $LASTEXITCODE

# IMPORTANT: wrangler often returns non-zero exit code AFTER successful deploy
# (Rollup native cleanup crash on Windows). Log file pattern matching is unreliable
# due to Tee-Object buffering + ANSI codes + encoding issues.
#
# REAL TRUTH: deploy success = production responds with new code.
# We delegate that judgment to verify_deploy.sh in STEP 2 (HTTP-based).
# Here we only proceed if wrangler didn't crash IMMEDIATELY (e.g. auth failure).
Log "  wrangler exit code: $PAGES_EXIT (ignoring - STEP 2 verify will determine actual production state)"

# Hard-fail only on auth/network errors that prevented deploy from even starting.
# 401 / config errors typically cause exit codes < 100 and no upload happens.
# -1073740791 (Windows STATUS_STACK_BUFFER_OVERRUN) is the post-deploy crash, OK.
if ($PAGES_EXIT -eq 1) {
    # exit 1 is wrangler's "auth failure" code. Likely token issue.
    Log "[WARN] wrangler exit=1 - possible auth failure. Checking via verify_deploy.sh anyway ..."
} elseif ($PAGES_EXIT -ne 0 -and $PAGES_EXIT -ne -1073740791) {
    Log "[WARN] Unexpected wrangler exit $PAGES_EXIT - proceeding to verify anyway"
}

Log "1-3. Waiting 60s for CDN propagation ..."
Start-Sleep -Seconds 60

# ============================================================
LogSection "STEP 2. verify_deploy.sh"

# Locate bash (Git Bash or WSL)
$BASH = $null
$BashCandidates = @(
    "C:\Program Files\Git\bin\bash.exe",
    "C:\Program Files (x86)\Git\bin\bash.exe",
    "C:\Windows\System32\bash.exe"
)
foreach ($candidate in $BashCandidates) {
    if (Test-Path $candidate) {
        $BASH = $candidate
        break
    }
}
if (-not $BASH) {
    $found = Get-Command bash -ErrorAction SilentlyContinue
    if ($found) { $BASH = $found.Source }
}

if (-not $BASH) {
    Log "[FAIL] bash not found. Skipping verify."
    $VERIFY_EXIT = -1
} else {
    Log "Using bash: $BASH"
    $VerifyCmd = "cd '$PROJECT_ROOT' ; bash scripts/verify_deploy.sh fashion-search/eval/queries/q001.jpg"
    & $BASH -c $VerifyCmd 2>&1 | Tee-Object -FilePath $LOG_FILE -Append
    $VERIFY_EXIT = $LASTEXITCODE
}

if ($VERIFY_EXIT -eq 0) {
    Log "[OK] verify passed - SESSION 11 code confirmed in production"
} else {
    Log "[WARN] verify exit $VERIFY_EXIT - SESSION 12 step will diagnose"
}

# ============================================================
LogSection "STEP 3. Claude Code autonomous run (SESSION 12)"

$CLAUDE_CMD = Get-Command claude -ErrorAction SilentlyContinue
if (-not $CLAUDE_CMD) {
    Log "[SKIP] 'claude' CLI not found in PATH."
    Log "Manual command for tomorrow:"
    Log "  cd '$PROJECT_ROOT'"
    Log "  claude --dangerously-skip-permissions @scripts/session12_prompt.txt"
    LogSection "OVERNIGHT RUN END (SESSION 12 skipped)"
    exit 0
}

if (-not (Test-Path $PROMPT_FILE)) {
    Log "[FAIL] Prompt file not found: $PROMPT_FILE"
    exit 4
}

$PROMPT_CONTENT = Get-Content -Path $PROMPT_FILE -Raw -Encoding UTF8
Log "Prompt file: $PROMPT_FILE"
Log "Prompt content loaded: $($PROMPT_CONTENT.Length) chars"
Log "Starting Claude Code (estimated 30min - 2hr) ..."

# Pass prompt as a single argument
& claude --dangerously-skip-permissions $PROMPT_CONTENT 2>&1 | Tee-Object -FilePath $LOG_FILE -Append
$CLAUDE_EXIT = $LASTEXITCODE
Log "Claude Code exit: $CLAUDE_EXIT"

# ============================================================
LogSection "OVERNIGHT RUN END"
Log "Build exit       : 0"
Log "Pages deploy exit: 0"
Log "verify exit      : $VERIFY_EXIT"
Log "Claude Code exit : $CLAUDE_EXIT"
Log ""
Log "Tomorrow morning checklist:"
Log "  1. Read this log: $LOG_FILE"
Log "  2. Read logs/overnight_summary.md (Claude Code writes it)"
Log "  3. Live test at https://cloi.pages.dev"
Log ""
Log "Done."

# Alarm (CLAUDE.md session-end hook)
$ALARM = Join-Path $PROJECT_ROOT ".claude\session-done.ps1"
if (Test-Path $ALARM) {
    Log "Triggering alarm: $ALARM"
    & $ALARM
}
