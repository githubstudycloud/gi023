# ============================================================
# Open All Agent Workspaces
# 一键打开所有 Agent 的 VSCode 窗口
# 用法: .\scripts\open-workspaces.ps1
# ============================================================

param(
    [string]$Editor = "code"   # code / cursor / windsurf
)

$workspaces = @(
    @{ Agent = "GLM";     Path = "D:\glm-workspace" },
    @{ Agent = "Kimi";    Path = "D:\kimi-workspace" },
    @{ Agent = "MiniMax"; Path = "D:\2026033101\minimax-workspace" },
    @{ Agent = "Opus";    Path = "D:\opus-workspace" }
)

Write-Host "`nOpening all agent workspaces with $Editor...`n" -ForegroundColor Cyan

foreach ($ws in $workspaces) {
    if (Test-Path $ws.Path) {
        Write-Host "  Opening $($ws.Agent): $($ws.Path)" -ForegroundColor Green
        & $Editor $ws.Path
        Start-Sleep -Milliseconds 500
    } else {
        Write-Host "  SKIP $($ws.Agent): $($ws.Path) not found" -ForegroundColor Yellow
    }
}

Write-Host "`nAll workspaces opened.`n" -ForegroundColor Cyan
