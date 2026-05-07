$root = Split-Path $PSScriptRoot -Parent
$statusFile = Join-Path $root 'SESSION_STATUS.md'
if (Test-Path $statusFile) {
    $lines = Get-Content $statusFile | Select-Object -First 12
    $msg = $lines -join "`n"
} else {
    $msg = 'SESSION_STATUS.md not found'
}
$wshell = New-Object -ComObject Wscript.Shell
$wshell.Popup($msg, 0, 'Cloi - Session Done', 64) | Out-Null
