# ============================================================
# Sync All Agents - 通知所有 Agent 从 main 同步
# 在 main 合并后执行，输出需要发给各 Agent 的同步指令
# 用法: .\scripts\sync-all.ps1
# ============================================================

param(
    [string]$RepoRoot = "D:\2026033101"
)

Push-Location $RepoRoot
git fetch --all --quiet 2>$null

$mainHead = git rev-parse --short origin/main 2>$null
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  Sync All Agents to main ($mainHead)" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

$agents = @("glm", "kimi", "minimax", "opus")

foreach ($agent in $agents) {
    $branch = "origin/$agent/dev"
    $exists = git rev-parse --verify $branch 2>$null

    if ($exists) {
        $behind = git rev-list --count "$branch..origin/main" 2>$null
        if ([int]$behind -gt 0) {
            Write-Host "  $agent/dev" -ForegroundColor Yellow -NoNewline
            Write-Host " | $behind commits behind main - NEEDS SYNC"
        } else {
            Write-Host "  $agent/dev" -ForegroundColor Green -NoNewline
            Write-Host " | up to date"
        }
    } else {
        Write-Host "  $agent/dev" -ForegroundColor Red -NoNewline
        Write-Host " | branch not found"
    }
}

Write-Host "`n--- Paste to each Agent's chat to sync ---`n" -ForegroundColor Green
Write-Host @"
main 分支已更新 (commit: $mainHead)，请同步你的分支：
git fetch origin main
git rebase origin/main
如果有冲突，以 main 的内容为准解决。
git push origin {你的分支} --force-with-lease
"@ -ForegroundColor Yellow

Write-Host "`n========================================`n" -ForegroundColor Cyan

Pop-Location
