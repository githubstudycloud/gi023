# gi023 - Multi-Agent Collaboration Project

## 概述

本项目由多个 AI Agent 协同开发。每个 Agent 可能运行在不同的 CLI 工具中
（Claude Code / Cursor / VSCode Copilot / Aider 等），使用不同的底层模型，
在各自的分支上独立完成相同任务，互相审阅，由主 Agent 合并最优方案。

## 团队

| Agent | Model | Role | Branch | CLI |
|-------|-------|------|--------|-----|
| GLM | glm-5.1 | Primary | glm/dev | claude-code |
| MiniMax | MiniMax-M2.7 | Secondary | minimax/dev | claude-code |
| Kimi | kimi-k2 | Secondary | kimi/dev | claude-code |
| Opus | claude-opus-4.6 | Secondary | opus/dev | claude-code |

> 查看 `.agents/registry/` 获取完整信息

## 架构 v2

```
.agents/                        ← 协作框架根目录
├── FRAMEWORK.yml               ← 框架定义（规则、角色、状态机）
├── INSTRUCTIONS.md             ← AI Agent 必读指令
├── ONBOARDING.md               ← 新 Agent 入驻指南
├── CHANGELOG.md                ← 框架版本变更记录
├── registry/                   ← Agent 注册（每人一文件，零冲突）
│   ├── glm.yml
│   ├── kimi.yml
│   ├── minimax.yml
│   └── opus.yml
├── tasks/                      ← 任务定义
│   └── .template.yml
├── reviews/                    ← 交叉审阅记录
│   └── .template.yml
├── signals/                    ← Agent 间信号通信
│   ├── glm/
│   ├── kimi/
│   ├── minimax/
│   └── opus/
│       ├── heartbeat.json
│       └── task-{id}-done.json
└── locks/                      ← 文件锁（同目录多实例）

scripts/                        ← 人类操作者自动化脚本
├── check-status.ps1            ← 全局 Agent 状态仪表盘
├── dispatch-task.ps1           ← 创建并分发任务
├── collect-reviews.ps1         ← 汇总审阅评分
├── sync-all.ps1                ← 合并后通知全员同步
└── open-workspaces.ps1         ← 一键打开所有 worktree 窗口

.github/copilot-instructions.md ← GitHub Copilot 自动读取
.claude/instructions.md         ← Claude Code 自动读取
.cursorrules                    ← Cursor 自动读取
.windsurfrules                  ← Windsurf 自动读取
.trae/rules                     ← Trae 自动读取
.augment/instructions.md        ← Augment Code 自动读取
.aider.conf.yml                 ← Aider 自动读取

OPERATIONS.md                   ← 并行开发操作手册（人类必读）
QUICKSTART.md                   ← 5 分钟快速上手
```

## 工作流

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  Task Open  │────▶│ Agent Claims │────▶│  Develops   │
└─────────────┘     └──────────────┘     └──────┬──────┘
                                                │
                    ┌──────────────┐     ┌──────▼──────┐
                    │   Merged     │◀────│  Reviewed   │
                    └──────────────┘     └─────────────┘
```

1. **任务创建** → `.agents/tasks/{NNN}-{type}-{slug}.yml`
2. **Agent 认领** → 在自己分支上开发
3. **完成信号** → `.agents/signals/{id}/task-{NNN}-done.json`
4. **交叉审阅** → `.agents/reviews/{task-id}-{reviewer}-reviews-{reviewee}.yml`
5. **合并** → Primary Agent 选择最优实现合并到 main

## 新 Agent 加入

```bash
# 1. 克隆/进入仓库
# 2. 创建分支和 worktree
git branch {你的id}/dev origin/main
git worktree add D:\{你的id}-workspace {你的id}/dev

# 3. 按 .agents/ONBOARDING.md 完成注册
# 4. 推送分支
git push origin {你的id}/dev
```

详见 [.agents/ONBOARDING.md](.agents/ONBOARDING.md)

## 自动化脚本

```powershell
# 查看所有 Agent 状态
.\scripts\check-status.ps1

# 创建并分发任务
.\scripts\dispatch-task.ps1 -Id "004" -Title "实现XXX" -Type "feature"

# 汇总审阅评分
.\scripts\collect-reviews.ps1 -TaskId "003"

# 合并后通知全员同步
.\scripts\sync-all.ps1

# 一键打开所有 Agent 的编辑器窗口
.\scripts\open-workspaces.ps1
```

## 分支规范

| 分支 | 用途 | 权限 |
|------|------|------|
| `main` | 稳定版本 | 仅 Primary 合并 |
| `{id}/dev` | Agent 持久开发分支 | 对应 Agent |
| `{id}/task/{NNN}` | 具体任务分支 | 对应 Agent |

## 支持的 AI CLI

| CLI | 配置文件 | 自动加载 |
|-----|---------|---------|
| GitHub Copilot | `.github/copilot-instructions.md` | ✅ |
| Claude Code | `.claude/instructions.md` | ✅ |
| Cursor | `.cursorrules` | ✅ |
| Windsurf | `.windsurfrules` | ✅ |
| Trae | `.trae/rules` | ✅ |
| Augment Code | `.augment/instructions.md` | ✅ |
| Aider | `.aider.conf.yml` | ✅ |

## 同目录多 Agent

当多个 AI CLI 实例在同一目录工作时，使用 `.agents/locks/` 文件锁协调。
详见 `FRAMEWORK.yml` 和 `ONBOARDING.md` 中的锁机制说明。

---

*Framework v2.1 by Opus (claude-opus-4.6) | 2026-04-01*
