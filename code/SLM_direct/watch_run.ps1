$ErrorActionPreference = "SilentlyContinue"
$root = "E:\Desktop\CET_docment\CET_docment\py\results\SLM_direct\protocol_v2_2"

while ($true) {
    $progressFiles = Get-ChildItem -Path $root -Recurse -Filter "progress.json" |
        Where-Object { $_.FullName -match "full_exploratory_642" } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1

    if (-not $progressFiles) {
        Clear-Host
        Write-Host "No running run found under: $root" -ForegroundColor Yellow
        Write-Host "Check the log files under py\SLM_direct\logs if a process is still alive."
    } else {
        $p = Get-Content -Raw $progressFiles.FullName | ConvertFrom-Json
        $done = [int]$p.counts.terminal
        $total = [int]$p.counts.total
        $failed = [int]$p.counts.terminal_failure
        $state = $p.state
        $pct = [math]::Round(100 * $done / $total, 1)
        $runDir = $progressFiles.DirectoryName

        Clear-Host
        Write-Host "======================================================" -ForegroundColor Cyan
        Write-Host "  SLM_direct full exploratory run monitor (Qwen3-4B)"
        Write-Host "======================================================" -ForegroundColor Cyan
        Write-Host ("  Progress: {0}/{1} ({2}%)" -f $done, $total, $pct) -ForegroundColor Green
        if ($failed -gt 0) {
            Write-Host ("  Failed: {0}   State: {1}" -f $failed, $state) -ForegroundColor Red
        } else {
            Write-Host ("  Failed: {0}   State: {1}" -f $failed, $state) -ForegroundColor Green
        }
        Write-Host ("  Last update: {0} (UTC)" -f $p.updated_at_utc)
        Write-Host ("  Run dir: {0}" -f $runDir)
        Write-Host "  Logs: py\SLM_direct\logs\full_exploratory_642.stdout.log / .stderr.log"
        Write-Host "  Press Ctrl+C to stop watching (the run itself keeps going)."
        Write-Host "======================================================" -ForegroundColor Cyan

        if ($state -ne "running" -and $state -ne "interrupted") {
            Write-Host ("  Run finished: {0}" -f $state) -ForegroundColor Magenta
            break
        }
    }
    Start-Sleep -Seconds 5
}
