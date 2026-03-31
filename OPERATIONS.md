# 多 AI Agent 并行开发操作手册

> **目标读者**：你（人类），同时操控多个 AI CLI 窗口进行并行开发  
> **前提**：已按 `.agents/ONBOARDING.md` 完成所有 Agent 注册  
> **仓库**：https://github.com/githubstudycloud/gi023

---

## 目录

- [环境总览](#环境总览)
- [自动化脚本（推荐）](#自动化脚本推荐)
- [场景一：同一任务多 Agent 并行开发](#场景一同一任务多-agent-并行开发)
- [场景二：不同任务分发给不同 Agent](#场景二不同任务分发给不同-agent)
- [场景三：只给主 Agent 下达任务，其他 Agent 自动跟进](#场景三只给主-agent-下达任务其他-agent-自动跟进)
- [交叉审阅流程](#交叉审阅流程)
- [合并流程](#合并流程)
- [Prompt 模板库](#prompt-模板库)
- [故障排除](#故障排除)

---

## 环境总览

### 当前 Agent 和窗口

| 窗口 | Agent | 模型 | 工作目录 | 分支 |
|------|-------|------|---------|------|
| VSCode 窗口 1 | GLM | glm-5.1 | `D:\glm-workspace` | glm/dev |
| VSCode 窗口 2 | Kimi | kimi-k2 | `D:\kimi-workspace` | kimi/dev |
| VSCode 窗口 3 | MiniMax | MiniMax-M2.7 | `D:\2026033101\minimax-workspace` | minimax/dev |
| VSCode 窗口 4 | Opus | claude-opus-4.6 | `D:\opus-workspace` | opus/dev |

### Worktree 验证命令

```powershell
# 在主仓库目录执行
cd D:\2026033101
git worktree list
# 应该看到所有 Agent 的 worktree
```

---

## 自动化脚本（推荐）

> 以下脚本封装了常用操作，免去手动执行 git 命令。在主仓库 `D:\2026033101` 下运行。

```powershell
# 一键打开全部 Agent 工作区
.\scripts\open-workspaces.ps1

# 查看所有 Agent 状态仪表盘（分支、信号、任务、锁）
.\scripts\check-status.ps1

# 创建并分发任务（自动生成文件名、提交推送、输出可复制的 prompt）
.\scripts\dispatch-task.ps1 -Id "004" -Title "实现用户认证" -Type "feature"

# 汇总所有 Agent 的交叉审阅评分，推荐最优实现
.\scripts\collect-reviews.ps1 -TaskId "004"

# 合并后通知全员同步
.\scripts\sync-all.ps1
```

---

## 场景一：同一任务多 Agent 并行开发

> 你给所有 AI 发相同任务，它们各自独立完成，最后你选最优方案合并。

### 第 1 步：创建任务文件（你在任意窗口执行）

在主 Agent (GLM) 窗口中对 AI 说：

```
创建一个新任务文件 .agents/tasks/003-feature-xxx.yml，
内容是：实现 XXX 功能。分配给所有 Agent。
然后提交推送到 glm/dev。
```

或者你自己手动创建（更可控）：

```powershell
# 在主仓库或任意 worktree 中
cd D:\2026033101
cat > .agents/tasks/003-feature-user-auth.yml << 'EOF'
id: "003"
title: "实现用户认证模块"
type: "feature"
priority: "high"
status: "open"

description: |
  实现基于 JWT 的用户认证模块，包括：
  - 用户注册（邮箱+密码）
  - 用户登录（返回 JWT token）
  - Token 验证中间件
  - 密码加密存储

acceptance:
  - "注册接口: POST /api/auth/register"
  - "登录接口: POST /api/auth/login"
  - "中间件能正确验证和拒绝 token"
  - "密码使用 bcrypt 加密"
  - "包含单元测试"

assignment:
  created_by: "glm"
  assigned_to: "all"
  primary_owner: ""

created_at: "2026-04-01"
EOF

git add .agents/tasks/003-feature-user-auth.yml
git commit -m "task: create 003-feature-user-auth

Assigned to all agents for parallel development."
git push origin main
```

### 第 2 步：通知所有 Agent（给每个 AI 窗口发消息）

**复制粘贴以下 prompt 到每个 AI 窗口**（改一下 Agent 名字）：

---

**发给 GLM 窗口**（主 Agent）：
```
git fetch origin main 拉取最新任务。
读取 .agents/tasks/003-feature-user-auth.yml。
在 glm/dev 分支上独立完成这个任务。
完成后在 .agents/signals/glm/ 下创建 task-003-done.json。
提交推送到 glm/dev。
```

**发给 Kimi 窗口**：
```
git fetch origin main 拉取最新任务。
读取 .agents/tasks/003-feature-user-auth.yml。
在 kimi/dev 分支上独立完成这个任务。
完成后在 .agents/signals/kimi/ 下创建 task-003-done.json。
提交推送到 kimi/dev。
```

**发给 MiniMax 窗口**：
```
git fetch origin main 拉取最新任务。
读取 .agents/tasks/003-feature-user-auth.yml。
在 minimax/dev 分支上独立完成这个任务。
完成后在 .agents/signals/minimax/ 下创建 task-003-done.json。
提交推送到 minimax/dev。
```

**发给 Opus 窗口**：
```
git fetch origin main 拉取最新任务。
读取 .agents/tasks/003-feature-user-auth.yml。
在 opus/dev 分支上独立完成这个任务。
完成后在 .agents/signals/opus/ 下创建 task-003-done.json。
提交推送到 opus/dev。
```

> **技巧**：这 4 条消息可以**同时发**，不需要等上一个完成。
> 每个 Agent 在自己的 worktree 和分支上工作，互不干扰。

### 第 3 步：等待所有 Agent 完成

你可以随时检查进度：

```powershell
# 查看哪些 Agent 已完成
cd D:\2026033101
git fetch --all
# 检查各分支的 signals 目录
git show glm/dev:.agents/signals/glm/task-003-done.json 2>$null && echo "GLM: DONE" || echo "GLM: working..."
git show kimi/dev:.agents/signals/kimi/task-003-done.json 2>$null && echo "Kimi: DONE" || echo "Kimi: working..."
git show minimax/dev:.agents/signals/minimax/task-003-done.json 2>$null && echo "MiniMax: DONE" || echo "MiniMax: working..."
git show opus/dev:.agents/signals/opus/task-003-done.json 2>$null && echo "Opus: DONE" || echo "Opus: working..."
```

### 第 4 步：交叉审阅 → [跳转到审阅流程](#交叉审阅流程)

### 第 5 步：合并 → [跳转到合并流程](#合并流程)

---

## 场景二：不同任务分发给不同 Agent

> 你有多个任务，每个 Agent 负责不同的部分。

### 创建多个任务，分别指定

```powershell
# 任务 A → GLM + Opus
# 任务 B → Kimi + MiniMax
```

任务文件中 `assigned_to` 指定具体 Agent：

```yaml
# .agents/tasks/004-feature-database.yml
assignment:
  assigned_to: ["glm", "opus"]     # 只分配给这两个
```

```yaml
# .agents/tasks/005-feature-frontend.yml
assignment:
  assigned_to: ["kimi", "minimax"] # 只分配给这两个
```

然后只给对应 Agent 发 prompt。

---

## 场景三：只给主 Agent 下达任务，其他 Agent 自动跟进

> 你只跟主 Agent (GLM) 对话，其他 Agent 定期拉取任务自行执行。

### 第 1 步：在 GLM 窗口创建并推送任务

```
创建任务 006: 实现日志系统。推送到 main 分支。
```

### 第 2 步：给其他 Agent 发「巡检」指令

给每个副 Agent 发这个**通用 prompt**（可以存为模板反复使用）：

```
执行日常巡检：
1. git fetch origin main
2. 对比 .agents/tasks/ 查看是否有新任务
   命令: git diff HEAD...origin/main -- .agents/tasks/
3. 如果有新任务，读取任务内容
4. 在你的分支上独立完成
5. 完成后创建信号文件并推送
如果没有新任务，报告"无新任务"即可。
```

> **高级用法**：把这段 prompt 写入各 AI 工具的 instructions 文件，
> 让 AI 每次启动时自动执行巡检。

---

## 交叉审阅流程

> 所有 Agent 完成开发后，让它们互相审阅。

### 审阅分配方案

推荐**环形审阅**（每人审一个，被一个审）：

```
GLM 审阅 → Kimi 的代码
Kimi 审阅 → MiniMax 的代码
MiniMax 审阅 → Opus 的代码
Opus 审阅 → GLM 的代码
```

### 发给每个 AI 的审阅 Prompt

**发给 GLM**：
```
审阅 Kimi 的 task 003 实现。

操作步骤：
1. git fetch origin kimi/dev
2. 对比代码: git diff main...origin/kimi/dev
3. 重点检查：功能正确性、安全性、代码质量、测试覆盖
4. 创建审阅文件 .agents/reviews/003-glm-reviews-kimi.yml
   按 .agents/reviews/.template.yml 模板填写
5. verdict 填 approve 或 request-changes
6. 提交推送到 glm/dev
```

**发给 Kimi**：
```
审阅 MiniMax 的 task 003 实现。

操作步骤：
1. git fetch origin minimax/dev
2. 对比代码: git diff main...origin/minimax/dev
3. 重点检查：功能正确性、安全性、代码质量、测试覆盖
4. 创建审阅文件 .agents/reviews/003-kimi-reviews-minimax.yml
5. 提交推送到 kimi/dev
```

**发给 MiniMax**：
```
审阅 Opus 的 task 003 实现。

操作步骤：
1. git fetch origin opus/dev
2. 对比代码: git diff main...origin/opus/dev
3. 重点检查：功能正确性、安全性、代码质量、测试覆盖
4. 创建审阅文件 .agents/reviews/003-minimax-reviews-opus.yml
5. 提交推送到 minimax/dev
```

**发给 Opus**：
```
审阅 GLM 的 task 003 实现。

操作步骤：
1. git fetch origin glm/dev
2. 对比代码: git diff main...origin/glm/dev
3. 重点检查：功能正确性、安全性、代码质量、测试覆盖
4. 创建审阅文件 .agents/reviews/003-opus-reviews-glm.yml
5. 提交推送到 opus/dev
```

> 这 4 条同样可以**同时发**。

### 查看审阅结果

```powershell
git fetch --all
# 查看所有审阅文件
git show glm/dev:.agents/reviews/003-glm-reviews-kimi.yml
git show kimi/dev:.agents/reviews/003-kimi-reviews-minimax.yml
git show minimax/dev:.agents/reviews/003-minimax-reviews-opus.yml
git show opus/dev:.agents/reviews/003-opus-reviews-glm.yml
```

---

## 合并流程

> 审阅完成后，选择最优实现合并到 main。

### 方案 A：人工选择最优（推荐）

你自己对比所有实现，选一个最好的：

```powershell
cd D:\2026033101
git fetch --all

# 对比各 Agent 的实现差异
git diff main...glm/dev -- ":(exclude).agents"
git diff main...kimi/dev -- ":(exclude).agents"
git diff main...minimax/dev -- ":(exclude).agents"
git diff main...opus/dev -- ":(exclude).agents"

# 统计各分支代码变更量
git diff main...glm/dev --stat
git diff main...kimi/dev --stat
git diff main...minimax/dev --stat
git diff main...opus/dev --stat
```

选定后合并（假设选 Opus 的实现）：

```powershell
cd D:\2026033101     # main 分支
git merge opus/dev --no-ff -m "merge: task 003 user-auth (opus implementation)

Selected opus implementation based on cross-review scores.
Reviews: 003-*-reviews-*.yml"
git push origin main
```

### 方案 B：让主 Agent 决策

给 GLM 发：

```
所有 Agent 已完成 task 003 并互相审阅。

请执行合并决策：
1. git fetch --all
2. 阅读所有审阅文件:
   git show kimi/dev:.agents/reviews/003-kimi-reviews-minimax.yml
   git show minimax/dev:.agents/reviews/003-minimax-reviews-opus.yml
   git show opus/dev:.agents/reviews/003-opus-reviews-glm.yml
3. 对比所有实现的代码差异
4. 选择最优方案或 cherry-pick 各方案的最佳部分
5. 合并到 main 并推送
6. 更新任务状态为 merged
```

### 方案 C：Cherry-pick 组合最优

从不同 Agent 中挑选各自最好的部分：

```powershell
cd D:\2026033101
# 从 opus 取认证逻辑
git cherry-pick <opus-commit-hash>
# 从 kimi 取测试用例
git cherry-pick <kimi-commit-hash>
git push origin main
```

### 合并后通知所有 Agent 同步

给每个 AI 发：

```
main 分支已更新（task 003 merged），请同步：
git fetch origin main
git rebase origin/main
git push origin {你的分支} --force-with-lease
```

---

## Prompt 模板库

以下是你可以直接复制粘贴的 prompt 模板。

### 模板 1：通用任务下发

```
git fetch origin main 同步最新状态。
读取 .agents/tasks/{TASK_FILE}。
在你的分支上独立完成此任务。
完成后：
1. 创建信号文件 .agents/signals/{你的id}/task-{TASK_ID}-done.json
2. 提交并推送到你的分支
```

### 模板 2：通用审阅指令

```
审阅 {TARGET_AGENT} 的 task {TASK_ID} 实现：
1. git fetch origin {TARGET_AGENT}/dev
2. git diff main...origin/{TARGET_AGENT}/dev
3. 按 .agents/reviews/.template.yml 模板创建审阅文件
   .agents/reviews/{TASK_ID}-{你的id}-reviews-{TARGET_AGENT}.yml
4. 提交推送
```

### 模板 3：巡检指令（定期发给副 Agent）

```
日常巡检：
1. git fetch origin main
2. 检查新任务: git diff HEAD...origin/main -- .agents/tasks/
3. 有新任务则读取并执行，无则报告"无新任务"
4. 检查是否有需要你审阅的内容
5. 更新心跳 .agents/signals/{你的id}/heartbeat.json
```

### 模板 4：合并后同步

```
main 已更新，请同步你的分支：
git fetch origin main
git rebase origin/main
处理冲突（如果有）后：
git push origin {你的分支} --force-with-lease
```

### 模板 5：一键全流程（发给每个 Agent）

```
完整执行以下流程：
1. git fetch origin main 同步
2. 读取 .agents/tasks/ 下最新的 open 状态任务
3. 独立完成开发
4. 创建 done 信号文件
5. git fetch --all 拉取其他 Agent 的分支
6. 审阅排在你后面的 Agent 的代码（环形：glm→kimi→minimax→opus→glm）
7. 创建审阅文件
8. 全部提交推送
```

---

## 故障排除

### Q: Agent 的分支落后 main 太多怎么办？

给对应 Agent 发：
```
你的分支落后 main，请 rebase：
git fetch origin main
git rebase origin/main
如果有冲突，以 main 为准解决。
git push origin {你的分支} --force-with-lease
```

### Q: 两个 Agent 修改了同一个文件怎么合并？

```powershell
# 先合并第一个
git merge agent-a/dev --no-ff
# 再合并第二个（可能有冲突）
git merge agent-b/dev --no-ff
# 手动解决冲突后
git add .
git commit
```

或者让 AI 帮你解决：
```
当前 main 合并 kimi/dev 时出现冲突，请查看冲突文件并解决：
优先保留功能更完整的版本，合并两者的优点。
```

### Q: 某个 Agent 一直没完成怎么办？

不用等它。其他 Agent 完成审阅后直接合并即可。
给慢的 Agent 发：
```
task 003 已由其他 Agent 完成并合并到 main。
请放弃当前开发，同步 main：
git fetch origin main
git reset --hard origin/main
git push origin {你的分支} --force-with-lease
```

### Q: 怎么新增一个 AI Agent？

1. 打开一个新的 VSCode/CLI 窗口
2. 给新 AI 发送：
```
阅读 .agents/ONBOARDING.md 并按步骤完成入驻注册。
你的 Agent ID 是 {新id}。
```

### Q: 多个 Claude Code 在同一目录怎么办？

每个 Claude Code 实例使用不同的 worktree：
```powershell
# 实例 1 用 claude-a
git worktree add D:\claude-a-workspace claude-a/dev
# 实例 2 用 claude-b
git worktree add D:\claude-b-workspace claude-b/dev
```

如果必须共享目录，操作前告诉 AI：
```
操作前检查 .agents/locks/ 是否有锁。
如果无锁，创建 .agents/locks/editing.lock 内容为你的 id。
操作完成后删除锁文件。
```

---

## 一张图总结

```
你（人类操作者）
│
├─ 窗口1 [GLM]──────── glm/dev ──────┐
├─ 窗口2 [Kimi]─────── kimi/dev ─────┤
├─ 窗口3 [MiniMax]──── minimax/dev ──┤   并行开发
├─ 窗口4 [Opus]─────── opus/dev ─────┘   （互不干扰）
│
│  全部完成后
│
├─ GLM 审阅 Kimi ────────────────────┐
├─ Kimi 审阅 MiniMax ────────────────┤   并行审阅
├─ MiniMax 审阅 Opus ────────────────┤   （环形分配）
├─ Opus 审阅 GLM ────────────────────┘
│
│  审阅完成后
│
└─ 你选最优方案 → merge 到 main → 通知全员同步
```

---

*操作手册 v1.1 | 2026-04-01 | by Opus (claude-opus-4.6)*
