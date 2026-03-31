# gi023 - Multi-Agent Collaboration Project

## 项目概述

本项目采用 **多 Agent 协作开发模式**，多个 AI Agent 同时开发相同任务，互相审阅，最终由主 Agent 合并最优方案。

## Agent 身份

| Agent | 模型 | 角色 | 状态 |
|-------|------|------|------|
| GLM | glm-5.1 | 主 Agent (Primary) | 活跃 |
| Kimi | kimi-k2 | 副 Agent (Secondary) | 活跃 |
| Opus | claude-opus-4.6 | 副 Agent (Secondary #3) | 活跃 |

> 其他 Agent 加入时将更新此表

## 协作流程

```
1. GLM 创建任务 → .agents/tasks/
2. 所有 Agent 读取任务，各自在分支上开发
3. Agent 之间互相审阅 → .agents/reviews/
4. GLM 选择最优实现，合并到 main
```

## 分支规范

- `main` - 主分支，仅由 GLM 合并
- `glm/{type}/{name}` - GLM 的开发分支
- `{agent-id}/{type}/{name}` - 其他 Agent 的开发分支

## 目录结构

```
.agents/
├── config.yml          # 协作框架配置
├── identity.yml        # Agent 身份注册表
├── glm.marker          # GLM 身份标记
├── tasks/              # 任务文件
│   └── _template.yml   # 任务模板
└── reviews/            # 审阅记录
    └── _template.yml   # 审阅模板
```

## 快速开始

### 新 Agent 加入

1. 在 `.agents/identity.yml` 中注册身份
2. 在 `.agents/` 下创建 `{agent-id}.marker` 文件
3. 使用 `git worktree` 创建独立工作目录
4. 以自己的分支前缀开始开发

### 接收任务

1. 读取 `.agents/tasks/` 下的任务文件
2. 创建自己的开发分支：`{agent-id}/{type}/{name}`
3. 独立完成开发并提交

### 互相审阅

1. 读取其他 Agent 的分支代码
2. 按审阅模板填写评分和意见
3. 保存到 `.agents/reviews/`

## 维护者

- **rdymaa05** - 项目负责人
- **GLM** - 主 Agent，流程管理
