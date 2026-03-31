# 快速开始（5分钟上手）

> 面向人类操作者的极简版。完整手册见 [OPERATIONS.md](OPERATIONS.md)。

## 1. 环境准备（一次性）

```powershell
cd D:\2026033101
git fetch --all

# 为每个 Agent 创建 worktree（如果尚未创建）
git worktree add D:\glm-workspace glm/dev 2>$null
git worktree add D:\kimi-workspace kimi/dev 2>$null
git worktree add D:\opus-workspace opus/dev 2>$null
# minimax 已在子目录: D:\2026033101\minimax-workspace
```

## 2. 开 4 个 VSCode 窗口

```powershell
code D:\glm-workspace
code D:\kimi-workspace
code D:\2026033101\minimax-workspace
code D:\opus-workspace
```

## 3. 发任务（复制粘贴到每个 AI 聊天窗口）

```
git fetch origin main。
读取 .agents/tasks/ 下最新的 open 任务。
在你自己的分支上独立完成。
完成后创建信号文件 .agents/signals/{你的id}/task-{id}-done.json。
提交推送。
```

## 4. 等完成 → 发审阅

```
审阅 {其他 Agent} 的实现。
git fetch origin {other}/dev
git diff main...origin/{other}/dev
创建审阅文件，提交推送。
```

## 5. 合并最优方案

```powershell
cd D:\2026033101
git merge {最佳Agent}/dev --no-ff
git push origin main
```

完成！详细操作见 [OPERATIONS.md](OPERATIONS.md)。
