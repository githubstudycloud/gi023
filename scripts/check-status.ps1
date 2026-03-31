# ============================================================
# Multi-Agent Status Dashboard
# 检查所有 Agent 的分支状态、信号、任务情况
# 用法: .\scripts\check-status.ps1
# ============================================================

param(
    [string]$RepoRoot = "D:\2026033101"
)

$ErrorActionPreference = "SilentlyContinue"

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  Multi-Agent Status Dashboard" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

Push-Location $RepoRoot

# Fetch all remotes
Write-Host "[*] Fetching all remotes..." -ForegroundColor Yellow
git fetch --all --quiet 2>$null

# Get registered agents
Write-Host "`n--- Registered Agents ---`n" -ForegroundColor Green
$registryPath = ".agents\registry"
$agents = @()

if (Test-Path $registryPath) {
    Get-ChildItem "$registryPath\*.yml" | ForEach-Object {
        $id = $_.BaseName
        $content = Get-Content $_.FullName -Raw
        $role = if ($content -match 'role:\s*"?(\w+)"?') { $Matches[1] } else { "unknown" }
        $model = if ($content -match 'model:\s*"?([^"]+)"?') { $Matches[1] } else { "unknown" }
        $status = if ($content -match 'status:\s*"?(\w+)"?') { $Matches[1] } else { "unknown" }
        $agents += $id

        $roleColor = if ($role -eq "primary") { "Magenta" } else { "White" }
        Write-Host "  $id" -ForegroundColor $roleColor -NoNewline
        Write-Host " | $model | $role | $status"
    }
} else {
    Write-Host "  No registry found!" -ForegroundColor Red
}

# Branch status
Write-Host "`n--- Branch Status ---`n" -ForegroundColor Green
foreach ($agent in $agents) {
    $branch = "$agent/dev"
    $remoteBranch = "origin/$branch"

    $localExists = git rev-parse --verify $branch 2>$null
    $remoteExists = git rev-parse --verify $remoteBranch 2>$null

    if ($remoteExists) {
        $ahead = git rev-list --count "origin/main..$remoteBranch" 2>$null
        $lastCommit = git log -1 --format="%h %s" $remoteBranch 2>$null
        $lastDate = git log -1 --format="%ci" $remoteBranch 2>$null
        Write-Host "  $branch" -ForegroundColor White -NoNewline
        Write-Host " | +$ahead ahead of main | $lastCommit"
    } elseif ($localExists) {
        Write-Host "  $branch" -ForegroundColor Yellow -NoNewline
        Write-Host " | LOCAL ONLY (not pushed)"
    } else {
        Write-Host "  $branch" -ForegroundColor Red -NoNewline
        Write-Host " | NOT FOUND"
    }
}

# Signals check
Write-Host "`n--- Agent Signals ---`n" -ForegroundColor Green
foreach ($agent in $agents) {
    $branch = "origin/$agent/dev"
    $heartbeat = git show "${branch}:.agents/signals/$agent/heartbeat.json" 2>$null
    if ($heartbeat) {
        $ts = if ($heartbeat -match '"timestamp"\s*:\s*"([^"]+)"') { $Matches[1] } else { "?" }
        Write-Host "  $agent" -ForegroundColor White -NoNewline
        Write-Host " | heartbeat: $ts" -ForegroundColor Green
    } else {
        Write-Host "  $agent" -ForegroundColor White -NoNewline
        Write-Host " | no heartbeat" -ForegroundColor DarkGray
    }

    # Check task-done signals
    $doneSignals = git ls-tree --name-only "${branch}:.agents/signals/$agent/" 2>$null |
        Where-Object { $_ -match "task-.*-done" }
    if ($doneSignals) {
        foreach ($sig in $doneSignals) {
            Write-Host "           | signal: $sig" -ForegroundColor Cyan
        }
    }
}

# Tasks
Write-Host "`n--- Tasks ---`n" -ForegroundColor Green
$tasksPath = ".agents\tasks"
if (Test-Path $tasksPath) {
    Get-ChildItem "$tasksPath\*.yml" | Where-Object { $_.Name -ne ".template.yml" } | ForEach-Object {
        $content = Get-Content $_.FullName -Raw
        $title = if ($content -match 'title:\s*"?([^"\n]+)"?') { $Matches[1] } else { $_.BaseName }
        $taskStatus = if ($content -match 'status:\s*"?(\w+)"?') { $Matches[1] } else { "?" }
        $assignee = if ($content -match 'assigned_to:\s*"?([^"\n]+)"?') { $Matches[1] } else { "?" }

        $statusColor = switch ($taskStatus) {
            "open" { "Yellow" }
            "claimed" { "Cyan" }
            "done" { "Green" }
            "merged" { "DarkGreen" }
            default { "White" }
        }
        Write-Host "  [$taskStatus]" -ForegroundColor $statusColor -NoNewline
        Write-Host " $title | assigned: $assignee"
    }
} else {
    Write-Host "  No tasks directory found" -ForegroundColor Red
}

# Locks
Write-Host "`n--- Active Locks ---`n" -ForegroundColor Green
$locksPath = ".agents\locks"
$lockFiles = Get-ChildItem "$locksPath\*.lock" 2>$null
if ($lockFiles) {
    foreach ($lock in $lockFiles) {
        $lockContent = Get-Content $lock.FullName -Raw | ConvertFrom-Json
        Write-Host "  LOCKED: $($lock.BaseName)" -ForegroundColor Red -NoNewline
        Write-Host " | by $($lockContent.agent) | since $($lockContent.acquired_at)"
    }
} else {
    Write-Host "  No active locks" -ForegroundColor DarkGray
}

Write-Host "`n========================================`n" -ForegroundColor Cyan

Pop-Location
