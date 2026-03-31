# ============================================================
# Dispatch Task to Agents
# 创建任务文件并推送，可选通知 Agent
# 用法: .\scripts\dispatch-task.ps1 -Id "004" -Title "实现XXX" -Type "feature"
# ============================================================

param(
    [Parameter(Mandatory=$true)][string]$Id,
    [Parameter(Mandatory=$true)][string]$Title,
    [string]$Type = "feature",
    [string]$Priority = "medium",
    [string]$Description = "",
    [string]$AssignTo = "all",
    [string]$CreatedBy = "human",
    [string]$RepoRoot = "D:\2026033101"
)

$slug = ($Title -replace '[^\w\s-]', '' -replace '\s+', '-').ToLower()
if ($slug.Length -gt 40) { $slug = $slug.Substring(0, 40) }
$fileName = "$Id-$Type-$slug.yml"
$filePath = Join-Path $RepoRoot ".agents\tasks\$fileName"

if (Test-Path $filePath) {
    Write-Host "ERROR: Task file already exists: $filePath" -ForegroundColor Red
    exit 1
}

$date = Get-Date -Format "yyyy-MM-dd"

if (-not $Description) {
    $Description = $Title
}

$taskYaml = @"
id: "$Id"
title: "$Title"
type: "$Type"
priority: "$Priority"
status: "open"

description: |
  $Description

acceptance:
  - "TODO: 填写验收标准"

assignment:
  created_by: "$CreatedBy"
  assigned_to: "$AssignTo"
  primary_owner: ""

depends_on: []

created_at: "$date"
deadline: ""
"@

# Create task file
$taskYaml | Out-File -FilePath $filePath -Encoding utf8NoBOM
Write-Host "Created task: $filePath" -ForegroundColor Green

# Commit and push
Push-Location $RepoRoot
git add $filePath
git commit -m "task: create $Id-$Type-$slug`n`nAssigned to: $AssignTo"
git push origin HEAD
Pop-Location

Write-Host "`nTask dispatched! Now paste this to each Agent's chat:" -ForegroundColor Cyan
Write-Host @"

------ Copy Below ------
git fetch origin main.
读取 .agents/tasks/$fileName.
在你自己的分支上独立完成此任务。
完成后创建信号文件 .agents/signals/{你的id}/task-$Id-done.json。
提交推送到你的分支。
------ Copy Above ------
"@ -ForegroundColor Yellow
