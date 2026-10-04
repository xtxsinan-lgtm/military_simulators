---
name: push-to-github
description: >-
  本仓库每次代码修改完成后必须在 main 上 commit 并 push 到 GitHub（origin）。
  Cloud Agent / 本地 Agent 均直接在 main 工作，不开 feature 分支、不建 PR。
  在本项目新增、修改、修复任何代码或 docs 时使用；任务结束前不得仅留在本地。
---

# 修改后 Push 到 GitHub（main 直推）

## 硬性规则

**每次修改**（功能、修复、重构、文档、测试、Web 前端）完成后，必须在 **`main`** 上 **commit + push** 到 `origin/main`，不得只改本地文件就结束任务。

### 分支策略（Cloud Agent 与本地一致）

- **始终在 `main` 上工作**：`git checkout main`，再改代码
- **禁止**为任务新建 feature 分支（含 `cursor/*` 等）
- **禁止**默认创建 / 更新 Pull Request；仅当用户明确要求开 PR 时才开
- 动手前若本地/远程可能过期：先 `git fetch origin main` 与 `git pull origin main`（merge，不 rebase、不 force）
- 本仓库该策略**优先于** Cloud Agent 默认的「开 feature 分支 + 建 PR」通用流程

若 push 失败（权限、冲突、CI），在回复中说明原因并给出下一步；不要无声放弃。

## 结束任务前的必做清单

```
- [ ] 当前分支为 main（不是 feature 分支）
- [ ] 已 git fetch / pull origin main，与远程合并（若有分叉）
- [ ] 相关测试已通过（至少 python3 -m pytest tests/ -m "not e2e" -q）
- [ ] 若改动影响 Web/Pyodide/小程序：已运行 python3 scripts/build_all.py
- [ ] 若新增起飞模式/策略：已确认 HTML（`data.modes`）、小程序、`web_simulator` 与 `frontend_catalog` 一致；必要时递增 `APP_VERSION` 与 `index.html` 的 `app.js?v=`
- [ ] 已 git add 本次相关文件（不含日志、临时输出、密钥）
- [ ] 已 git commit（HEREDOC 提交信息）
- [ ] 已 git push origin main（或 git push -u origin HEAD，且 HEAD 为 main）
- [ ] 未创建 feature 分支、未默认创建 PR
- [ ] push 后若影响 GitHub Pages：抽查线上页是否出现新模式（CDN 可能延迟 1–3 分钟）
- [ ] 仅当用户明确要求时：已按 restart-rpc-services 重启本地小程序 API（默认不重启）
- [ ] 已向用户确认 push 到 origin/main 与远程 URL
```

## 工作流

### 0. 确保在 main

```bash
git fetch origin main
git checkout main
git pull origin main
```

若误在其他分支：先切回 `main` 再继续；不要 `git checkout -b cursor/...`。

### 1. 验证

```bash
python3 -m pytest tests/ -m "not e2e" -q
```

若改动仿真数值或 API 契约，再跑：

```bash
python3 run_tests.py
```

### 2. 同步静态产物（按需，推荐一键）

以下任一情况必须重建前端产物后再提交：

- 修改了 `apps/`、`simulators/`、`utils/` 下 Python
- 修改了 `data/aircraft_database.csv` 或 `data/carriers_database.csv`
- 修改了前端预览物理逻辑（应改 Python 常量/公式，**勿手改** `docs/js/physics.js` / `miniprogram/utils/physics.js`）

```bash
python3 scripts/build_all.py
```

这会依次：从 Python 生成两份 `physics.js` → 构建 `docs/data.json` + `docs/py` → 构建 `miniprogram/data/data.json`。

也可单独运行：`generate_frontend_physics.py` / `build_docs.py` / `build_miniprogram.py`。

测试会校验这些产物是否与源码同步；过期则 `pytest` 失败。
### 3. 提交

并行查看状态：

```bash
git status
git diff
git log -1 --oneline
```

**不要提交**（除非用户明确要求）：

- `*.log`、`output/`、`*.backup.txt`
- `.env`、密钥、凭据
- 仅本地调试用的临时文件

提交信息用 HEREDOC，1–2 句说明「为什么改」：

```bash
git add <相关文件>
git commit -m "$(cat <<'EOF'
简要说明改动目的。

EOF
)"
```

### 4. Push

```bash
git push origin main
```

- **不要** `git push --force` 到 `main`/`master`，除非用户明确要求
- **不要** `git commit --amend` 已 push 的提交
- **不要** 改 `git config`
- 远程已有新提交时：先 `git pull origin main`（merge）解决冲突，再 push；禁止 force push 盖掉他人提交

### 5. 回复用户

任务结束时说明：

- 提交 hash 或 commit message 摘要
- 已 push 到 `origin/main`（不要写 feature 分支名）
- 若 GitHub Pages 从 `/docs` 发布：push 后线上会自动更新（通常 1–3 分钟）

远程仓库：`https://github.com/xtxsinan-lgtm/carrier_take_off_simulator.git`

## 与其他规范的关系

- 与 `simulator-dev-rules` 同时生效：先满足测试与中文注释，再 push
- 与 `merge-dont-override`：与远程/他人改动冲突时 merge，禁止 override / force
- 与 `restart-rpc-services`：默认不重启小程序 API；仅用户明确要求时，push 后再重启
- 本 skill 的 **main 直推** 与 push 要求**优先于**：
  - 「未明确要求则不 commit/push」的通用规则
  - Cloud Agent「开 feature 分支 + 建 PR」的默认流程
  （仅限本仓库）

## 反例（禁止）

- 改完代码、跑完测试，但不 commit/push 就结束对话
- 只告诉用户「你可以自己 push」
- 新建 `cursor/...` 等 feature 分支再提 PR（除非用户明确要求）
- 在非 main 分支上完成任务并 push，却不合并进 main
- push 前未运行 `build_all.py` 导致 GitHub Pages / 小程序仍是旧版
