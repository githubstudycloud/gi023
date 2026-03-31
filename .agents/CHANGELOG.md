# Multi-Agent Collaboration Framework - Changelog

所有框架的重大变更记录在此文件中。
格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/)。

---

## [2.0.0] - 2026-03-31

### Breaking Changes
- 完全重构协作框架，从单文件改为分布式架构
- 删除 `identity.yml` 和 `config.yml`，替换为 `registry/{id}.yml`
- 删除 `.marker` 文件，信息整合进 registry
- 删除旧版模板 `_template.yml`，替换为 `.template.yml`

### Added
- `FRAMEWORK.yml` - 完整框架定义（角色、规则、状态机、分支策略）
- `INSTRUCTIONS.md` - AI Agent 通用入口指令
- `ONBOARDING.md` - 新 Agent 入驻 6 步指南
- `registry/` 目录 - 每个 Agent 独立注册文件，零合并冲突
- `signals/` 目录 - Agent 间异步信号机制（心跳、任务完成、审阅请求）
- `locks/` 目录 - 文件锁机制（同目录多 AI 实例场景）
- `reviews/.template.yml` - 审阅模板 v2（含 5 维度评分）
- `tasks/.template.yml` - 任务模板 v2（含验收标准和依赖）
- 多 CLI 指令文件：`.github/copilot-instructions.md`、`.claude/instructions.md`、`.cursorrules`、`.aider.conf.yml`
- `.gitattributes` - 强制 UTF-8 + LF
- `OPERATIONS.md` - 人类操作者并行开发操作手册

### Agents
- GLM (primary, glm-5.1) - 迁移自 v1
- Kimi (secondary, kimi-k2) - 迁移自 v1
- MiniMax (secondary, MiniMax-M2.7) - 迁移自 v1
- Opus (secondary, claude-opus-4.6) - 新注册

---

## [1.0.0] - 2026-03-31

### Added
- 初始框架：`identity.yml` + `config.yml` + `.marker` 文件
- GLM 作为 primary agent 初始化框架
- MiniMax 和 Kimi 作为 secondary agent 加入
- 基础任务和审阅模板

### Known Issues
- 单一 `identity.yml` 多人写入导致合并冲突
- MiniMax 提交存在 UTF-8 编码损坏
- 无 Agent 间通信机制
- 无多 CLI 支持
