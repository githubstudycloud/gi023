# Multi-Agent Collaboration Instructions
# =============================================
# 本文件是所有 AI Agent / CLI 的入口指令。
# 当你（AI）被要求参与此项目协作时，请完整阅读此文件。
# =============================================

## 你是谁

你是一个参与多 Agent 协作开发的 AI 助手。本项目由多个 AI 模型（可能运行在
不同的 Claude Code / Cursor / VSCode Copilot 实例中）共同开发。

## 第一步：确认你的身份

1. 检查 `.agents/registry/` 目录，查看你是否已注册
2. 如果已注册，读取你的注册文件确认信息
3. 如果未注册，按照 `ONBOARDING.md` 步骤加入

## 核心规则

### 文件隔离（最重要）

- 你**只能修改** `.agents/registry/{你的id}.yml`
- 你**只能写入** `.agents/signals/{你的id}/` 目录
- 你**只能在自己的分支**上修改项目代码
- 你**绝对不能**修改其他 Agent 的注册文件或信号文件

### 分支规则

- 你有一个持久分支: `{你的id}/dev`（绑定 worktree）
- 具体任务分支: `{你的id}/task/{task-id}`
- **永远不要**直接提交到 `main` 分支
- 合并到 main 只能由 primary Agent 执行

### 任务流程

1. 读取 `.agents/tasks/` 下的任务文件
2. 在你的分支上开发
3. 完成后在 `.agents/signals/{你的id}/` 下创建 `task-{task-id}-done.json`
4. 审阅其他 Agent 的实现，写入 `.agents/reviews/`
5. 等待 primary Agent 合并

### 提交规范

```
{type}: {description}

Co-Authored-By: {你的名字} <{你的邮箱}>
```

type: feat | fix | refactor | docs | test | chore

### 同目录操作（多个 Claude Code 共享一个目录时）

如果你和其他 AI 在同一个目录下工作：
1. 操作前检查 `.agents/locks/` 是否有活跃锁
2. 创建锁文件: `.agents/locks/{resource}.lock`
3. 完成操作后删除锁文件
4. 锁超过 10 分钟视为过期

## 文件结构速查

```
.agents/
├── FRAMEWORK.yml           # 框架完整定义（规则、流程、状态机）
├── registry/               # Agent 注册（每人一文件，互不冲突）
│   ├── glm.yml
│   ├── kimi.yml
│   ├── minimax.yml
│   └── opus.yml
├── tasks/                  # 任务文件（所有 Agent 可读）
│   └── .template.yml
├── reviews/                # 审阅记录
│   └── .template.yml
├── signals/                # Agent 间信号通信
│   └── {agent-id}/
│       ├── heartbeat.json
│       └── task-{id}-done.json
└── locks/                  # 文件锁（同目录操作时使用）
```

## 当前团队

查看 `.agents/registry/` 下所有 `.yml` 文件获取完整团队列表。
Primary Agent 拥有合并权限，Secondary Agent 负责开发和审阅。
