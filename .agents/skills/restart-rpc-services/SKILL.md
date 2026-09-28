---
name: restart-rpc-services
description: >-
  本仓库每次改完依赖后端的代码后，必须自动重启本地 RPC/HTTP 仿真服务（miniprogram_api）。
  仅针对包含 RPC/HTTP API 调用的程序（微信小程序）；纯静态 Web/Pyodide、iOS 本地引擎或纯 CLI 不在此列。
  在本项目修改 apps/、simulators/、utils/、data CSV，或用户使用小程序联调时使用。
---

# 修改后自动重启含 RPC 的本地服务

## 适用范围（务必注明）

**本规则只适用于「包含 RPC / HTTP API 调用」的程序**，例如：

- 微信小程序 → `python3 apps/miniprogram_api.py`（`http://127.0.0.1:8765`）
- 其他通过 `wx.request` / HTTP / RPC 调用本仓库 Python 后端的客户端

**不适用**（改完后不必为这条去重启进程）：

- 纯静态 GitHub Pages / Pyodide 网页（浏览器加载新 `docs/` 即可）
- **iOS App**（设备本地 Pyodide，无后端）
- 纯本地 CLI / `pytest`（每次进程本就重新 import）

若一次改动同时影响小程序 API 与静态产物：先 `build_all` → commit/push → **再重启 RPC 服务**。

## 硬性规则

在本仓库完成涉及后端仿真逻辑或 API 契约的修改后，任务结束前必须 **自动重启** 本地 `miniprogram_api`，不得只改代码、留下旧进程继续跑旧模块。

典型触发：

- 修改了 `apps/web_simulator.py`、`apps/miniprogram_api.py`
- 修改了 `simulators/`、`utils/`、`data/*.csv`（仿真结果会变）
- 修改了小程序请求契约或依赖上述后端的前端联调代码

## 结束任务前的必做清单（RPC 路径）

```
- [ ] 已按 simulator-dev-rules / push-to-github 完成测试、build、commit、push
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

顺序建议：

```text
改代码 → 测试 → build_all（如需）→ commit/push → 重启 miniprogram_api → 回复用户
```

## 反例（禁止）

- 改了 `web_simulator.py` / 仿真器，小程序仍连着旧 API 进程就结束对话
- 只说「请你自行重启 API」而不执行重启
- 把本规则套用到 iOS 本地引擎、纯静态网页或纯 pytest
