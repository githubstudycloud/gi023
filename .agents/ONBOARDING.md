# AI Agent 入驻指南（Onboarding Guide）

本文档指导新的 AI Agent 加入多 Agent 协作框架。
无论你是 Claude Code、Cursor、VSCode Copilot 还是其他 AI CLI，
按照以下步骤操作即可完成入驻。

---

## 前置条件

- 能访问本 Git 仓库
- 有终端执行 git 命令的能力
- 能读写工作区文件

---

## 步骤 1：选择你的 Agent ID

Agent ID 是你在本项目中的唯一标识，要求：
- 全小写英文
- 无空格，可用连字符
- 简短易记（如 `claude`, `gemini`, `gpt4`, `deepseek`）
- 不能与已有 Agent 重复（检查 `.agents/registry/`）

**已注册的 ID**: 查看 `.agents/registry/` 下所有 `.yml` 文件名（去掉 .yml 后缀）

---

## 步骤 2：创建你的分支和 worktree

### 方案 A：独立 worktree（推荐）

```bash
# 在主仓库目录执行
cd D:\2026033101
git fetch origin
git branch {你的id}/dev origin/main
git worktree add D:\{你的id}-workspace {你的id}/dev
cd D:\{你的id}-workspace
```

### 方案 B：共享目录模式

如果你和其他 Agent 在同一目录工作（如同一个 VSCode 窗口）：

```bash
git fetch origin
git checkout -b {你的id}/dev origin/main
# 注意：操作前检查 .agents/locks/
```

---

## 步骤 3：创建注册文件

在你的分支上创建 `.agents/registry/{你的id}.yml`：

```yaml
id: "{你的id}"
name: "{你的显示名}"
provider: "{提供商}"
model: "{模型名称}"
role: "secondary"
status: "active"
joined_at: "{ISO 8601 时间}"

runtime:
  cli: "{你的 CLI 工具名}"     # claude-code / cursor / vscode-copilot / aider 等
  ide: "{IDE 名}"
  os: "{操作系统}"

workspace:
  worktree_path: "{你的 worktree 路径}"
  dev_branch: "{你的id}/dev"
  branch_prefix: "{你的id}"

capabilities:
  - "code-development"
  - "code-review"
  # 添加你擅长的能力

preferences:
  language: "zh-cn"
  commit_style: "conventional-commits"
  review_depth: "standard"     # quick / standard / thorough

contact:
  co_author: "{名字} <{邮箱}>"
```

---

## 步骤 4：创建心跳信号

创建 `.agents/signals/{你的id}/heartbeat.json`：

```json
{
  "agent": "{你的id}",
  "status": "active",
  "timestamp": "{ISO 8601}",
  "current_task": null,
  "branch": "{你的id}/dev",
  "last_commit": ""
}
```

---

## 步骤 5：提交并推送

```bash
git add .agents/registry/{你的id}.yml .agents/signals/{你的id}/
git commit -m "feat: register {你的id} as secondary agent

- Add {你的id} registry entry
- Initialize heartbeat signal

Co-Authored-By: {你的名字} <{你的邮箱}>"

git push origin {你的id}/dev
```

---

## 步骤 6：验证

1. 在 GitHub 检查你的分支是否已推送
2. 确认 `.agents/registry/{你的id}.yml` 内容正确
3. 读取 `.agents/tasks/` 查看是否有待领取的任务

---

## 对于同目录下的多 Claude Code 实例

当多个 AI 在同一个目录下工作时：

### 工作流

```
AI-A 要修改文件 → 检查锁 → 创建锁 → 修改 → 提交 → 释放锁
AI-B 要修改文件 → 检查锁 → 发现被锁 → 等待或跳过 → 重试
```

### 锁文件格式

`.agents/locks/{resource}.lock`：
```json
{
  "agent": "{你的id}",
  "acquired_at": "{ISO 8601}",
  "purpose": "修改什么",
  "expires_at": "{ISO 8601, 10分钟后}"
}
```

### 关键约束

- **永远不要**在你持有锁时执行耗时操作
- 锁的粒度应尽量小（锁单个文件而非整个目录）
- 如果你发现一个过期的锁（>10分钟），可以强制删除它
- 锁文件不被 git 追踪（在 .gitignore 中）

---

## 日常工作流

```
1. git fetch origin main     # 同步最新 main
2. 读取 .agents/tasks/        # 查看新任务
3. 在你的分支上开发
4. 更新心跳信号
5. git push origin {你的id}/dev
6. 创建 task-done 信号文件
7. 读取其他 Agent 的分支进行审阅
8. 写入审阅记录到 .agents/reviews/
```

---

## FAQ

**Q: 我怎么知道有新任务？**
A: `git fetch origin main && git diff origin/main -- .agents/tasks/`

**Q: 我可以修改 FRAMEWORK.yml 吗？**
A: 可以在你的分支上提出修改，但最终合并由 primary Agent 决定。

**Q: 如果我的分支与 main 冲突了怎么办？**
A: 在你的分支上 `git rebase origin/main` 或 `git merge origin/main`。

**Q: 我可以审阅所有人的代码吗？**
A: 是的，任何 Agent 都可以审阅任何其他 Agent 的代码。
