---
name: restart-rpc-services
description: >-
  本仓库默认不自动重启本地 RPC/HTTP 仿真服务（miniprogram_api）；
  仅当用户明确要求重启/联调小程序 API 时才执行重启。
  仅针对包含 RPC/HTTP API 调用的程序（微信小程序）；纯静态 Web/Pyodide、iOS 本地引擎或纯 CLI 不在此列。
  在用户明确要求重启小程序 API、或明确说要小程序联调并需要刷新后端时使用。
---

# 按需重启含 RPC 的本地服务（默认不重启）

## 默认策略

**除非用户明确要求，否则不要重启** 本地 `miniprogram_api`（或其它 RPC/HTTP 后端）。

改完 `apps/`、`simulators/`、`utils/`、CSV 后，照常完成测试、`build_all`、commit/push 即可；**不要**顺手杀端口、拉起 API、或在回复里暗示「必须重启才能生效」。

用户明确要求的示例（命中任一即可重启）：

- 「重启 API」「重启小程序后端」「把 8765 拉起来」
- 「我要联调小程序，帮我把服务跑起来」
- 「改完后顺便重启 miniprogram_api」

未点名则**跳过**本 skill 的重启步骤。

## 适用范围（务必注明）

**本规则只适用于「包含 RPC / HTTP API 调用」的程序**，例如：

- 微信小程序 → `python3 apps/miniprogram_api.py`（`http://127.0.0.1:8765`）
- 其他通过 `wx.request` / HTTP / RPC 调用本仓库 Python 后端的客户端

**不适用**（改完后不必为这条去重启进程）：

- 纯静态 GitHub Pages / Pyodide 网页（浏览器加载新 `docs/` 即可）
- **iOS App**（设备本地 Pyodide，无后端）
- 纯本地 CLI / `pytest`（每次进程本就重新 import）

若用户要求重启，且一次改动同时影响小程序 API 与静态产物：先 `build_all` → commit/push → **再重启 RPC 服务**。

## 何时重启（仅用户明确要求时）

仅在用户明确要求后，才在任务结束前重启本地 `miniprogram_api`，避免旧进程继续跑旧模块。

典型场景（仍须用户先点名）：

- 修改了 `apps/web_simulator.py`、`apps/miniprogram_api.py`
- 修改了 `simulators/`、`utils/`、`data/*.csv`（仿真结果会变）
- 修改了小程序请求契约或依赖上述后端的前端联调代码

## 用户要求重启时的必做清单（RPC 路径）

```
- [ ] 已按 simulator-dev-rules / push-to-github 完成测试、build、commit、push
- [ ] 用户已明确要求重启或拉起小程序 API
- [ ] 已重启本地含 RPC 的服务：python3 apps/miniprogram_api.py（默认端口 8765；真机用 --host 0.0.0.0）
- [ ] 已确认服务打印「小程序仿真 API 运行于 …」或等价就绪日志
- [ ] 已在回复中告知用户：服务已重启、地址与端口
```

## 重启步骤

在项目根目录执行（先释放端口，再后台启动）：

```bash
if lsof -t -iTCP:8765 -sTCP:LISTEN >/dev/null 2>&1; then
  kill $(lsof -t -iTCP:8765 -sTCP:LISTEN) 2>/dev/null || true
  sleep 0.5
fi

python3 apps/miniprogram_api.py --host 0.0.0.0
```

就绪判据（stdout）：

```text
小程序仿真 API 运行于 http://0.0.0.0:8765
```

## 与其他 skill 的关系

顺序建议（仅当用户要求重启时多最后一步）：

```text
改代码 → 测试 → build_all（如需）→ commit/push →（仅用户明确要求时）重启 miniprogram_api → 回复用户
```

## 反例（禁止）

- 用户未要求时，改完后端就自动杀端口/重启 `miniprogram_api`
- 用户明确要求重启时，只说「请你自行重启 API」而不执行
- 把本规则套用到 iOS 本地引擎、纯静态网页或纯 pytest
