# Claude Code Instructions

本项目使用多 AI Agent 协作开发框架。

## 启动时必读

1. `.agents/INSTRUCTIONS.md` - 协作规则
2. `.agents/registry/` - 所有 Agent 注册信息
3. `.agents/tasks/` - 当前任务列表
4. `.agents/FRAMEWORK.yml` - 完整框架定义

## 如果你是新加入的 Claude Code 实例

按 `.agents/ONBOARDING.md` 完成入驻。

## 如果你是已注册的 Agent

1. 确认你在正确的分支上（{你的id}/dev）
2. 更新你的心跳: `.agents/signals/{你的id}/heartbeat.json`
3. 检查新任务: `.agents/tasks/`
4. 开发、提交、推送到你的分支

## 同目录多实例特别注意

如果有多个 Claude Code 操作同一目录:
- 操作共享文件前检查 `.agents/locks/`
- 使用文件锁避免冲突
- 锁超时 10 分钟自动过期
