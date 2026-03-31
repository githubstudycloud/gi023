# ============================================================
# Collect Reviews from All Agents
# 从各分支收集审阅文件，汇总评分
# 用法: .\scripts\collect-reviews.ps1 -TaskId "003"
# ============================================================

param(
    [Parameter(Mandatory=$true)][string]$TaskId,
    [string]$RepoRoot = "D:\2026033101"
)

Push-Location $RepoRoot
git fetch --all --quiet 2>$null

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  Review Summary for Task $TaskId" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

$agents = @("glm", "kimi", "minimax", "opus")
$reviews = @()

foreach ($reviewer in $agents) {
    $branch = "origin/$reviewer/dev"

    # List review files on this branch matching the task
    $files = git ls-tree --name-only -r $branch -- ".agents/reviews/" 2>$null |
        Where-Object { $_ -match "$TaskId-$reviewer-reviews-" }

    foreach ($file in $files) {
        $content = git show "${branch}:$file" 2>$null
        if (-not $content) { continue }

        # Parse reviewee
        $reviewee = if ($file -match "$TaskId-$reviewer-reviews-(\w+)\.yml") { $Matches[1] } else { "?" }

        # Parse scores
        $correctness = if ($content -match 'correctness:\s*(\d)') { [int]$Matches[1] } else { 0 }
        $quality = if ($content -match 'code_quality:\s*(\d)') { [int]$Matches[1] } else { 0 }
        $security = if ($content -match 'security:\s*(\d)') { [int]$Matches[1] } else { 0 }
        $maintain = if ($content -match 'maintainability:\s*(\d)') { [int]$Matches[1] } else { 0 }
        $tests = if ($content -match 'test_coverage:\s*(\d)') { [int]$Matches[1] } else { 0 }
        $avg = [math]::Round(($correctness + $quality + $security + $maintain + $tests) / 5, 1)

        # Parse verdict
        $verdict = if ($content -match 'verdict:\s*"?(\S+)"?') { $Matches[1] } else { "?" }

        $reviews += [PSCustomObject]@{
            Reviewer = $reviewer
            Reviewee = $reviewee
            Correctness = $correctness
            Quality = $quality
            Security = $security
            Maintain = $maintain
            Tests = $tests
            Average = $avg
            Verdict = $verdict
        }

        $verdictColor = if ($verdict -eq "approve") { "Green" } else { "Red" }
        Write-Host "  $reviewer reviews $reviewee" -ForegroundColor White -NoNewline
        Write-Host " | Score: $avg/5" -NoNewline
        Write-Host " | $verdict" -ForegroundColor $verdictColor
    }
}

if ($reviews.Count -eq 0) {
    Write-Host "  No reviews found for task $TaskId" -ForegroundColor Yellow
    Write-Host "  Make sure agents have pushed their review files." -ForegroundColor DarkGray
} else {
    # Summary: who got reviewed and their average
    Write-Host "`n--- Per-Agent Score Summary ---`n" -ForegroundColor Green

    $grouped = $reviews | Group-Object -Property Reviewee
    $ranking = @()
    foreach ($group in $grouped) {
        $agentAvg = [math]::Round(($group.Group | Measure-Object -Property Average -Average).Average, 2)
        $approvals = ($group.Group | Where-Object { $_.Verdict -eq "approve" }).Count
        $total = $group.Group.Count
        $ranking += [PSCustomObject]@{
            Agent = $group.Name
            AvgScore = $agentAvg
            Approvals = "$approvals/$total"
        }
    }

    $ranking | Sort-Object -Property AvgScore -Descending | ForEach-Object {
        $medal = if ($_.AvgScore -ge 4) { "[BEST]" } elseif ($_.AvgScore -ge 3) { "[GOOD]" } else { "[NEEDS WORK]" }
        $color = if ($_.AvgScore -ge 4) { "Green" } elseif ($_.AvgScore -ge 3) { "Yellow" } else { "Red" }
        Write-Host "  $($_.Agent)" -ForegroundColor $color -NoNewline
        Write-Host " | Avg: $($_.AvgScore)/5 | Approvals: $($_.Approvals) $medal"
    }

    Write-Host "`n  Recommended merge: " -ForegroundColor Cyan -NoNewline
    $best = $ranking | Sort-Object -Property AvgScore -Descending | Select-Object -First 1
    Write-Host "$($best.Agent)/dev" -ForegroundColor Green
}

Write-Host "`n========================================`n" -ForegroundColor Cyan

Pop-Location
