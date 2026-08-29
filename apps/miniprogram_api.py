"""微信小程序仿真 HTTP API（供 miniprogram 通过 wx.request 调用）。

iOS App 在设备本地用 Pyodide 运行同一套 Python，不走本服务。
"""
from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

# 支持从项目根目录直接运行：python3 apps/miniprogram_api.py
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from apps.combat_radius_web import run_combat_radius_json
from apps.missile_interception_strike_web import run_missile_interception_json
from apps.web_simulator import run_simulation_json


def _guess_lan_ip() -> str | None:
    """尝试获取本机局域网 IPv4，供小程序真机调试提示。"""
    import socket

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
            if ip and not ip.startswith('127.'):
                return ip
    except OSError:
        pass
    return None


def build_data_payload() -> dict[str, Any]:
    """返回航母/战斗机数据库 JSON（与 build_miniprogram 结构一致）。"""
    from scripts.build_miniprogram import build_miniprogram_data
    return build_miniprogram_data()


def handle_request(method: str, path: str, body: bytes | None) -> tuple[int, dict[str, str], bytes]:
    """
    处理单次 HTTP 请求，返回 (status_code, headers, body_bytes)。
    便于单元测试，无需启动真实服务器。
    """
    parsed = urlparse(path)
    route = parsed.path.rstrip('/') or '/'
    cors = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
    }

    if method == 'OPTIONS':
        return 204, cors, b''

    if method == 'GET' and route == '/api/data':
        payload = build_data_payload()
        body_bytes = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        headers = {**cors, 'Content-Type': 'application/json; charset=utf-8'}
        return 200, headers, body_bytes

    if method == 'POST' and route == '/api/simulate':
        if not body:
            err = {'success': False, 'error': '请求体为空'}
            return 400, {**cors, 'Content-Type': 'application/json'}, json.dumps(err).encode()
        try:
            payload = json.loads(body.decode('utf-8'))
        except json.JSONDecodeError as exc:
            err = {'success': False, 'error': f'JSON 解析失败: {exc}'}
            return 400, {**cors, 'Content-Type': 'application/json'}, json.dumps(err).encode()
        try:
            result = run_simulation_json(payload)
            body_bytes = json.dumps(result, ensure_ascii=False).encode('utf-8')
        except Exception as exc:
            print(f'[miniprogram_api] 仿真未捕获异常: {exc}', flush=True)
            err = {'success': False, 'error': f'服务器内部错误: {exc}'}
            body_bytes = json.dumps(err, ensure_ascii=False).encode('utf-8')
        headers = {**cors, 'Content-Type': 'application/json; charset=utf-8'}
        return 200, headers, body_bytes

    if method == 'POST' and route == '/api/missile_interception/simulate':
        if not body:
            err = {'success': False, 'error': '请求体为空'}
            return 400, {**cors, 'Content-Type': 'application/json'}, json.dumps(err).encode()
        try:
            payload = json.loads(body.decode('utf-8'))
        except json.JSONDecodeError as exc:
            err = {'success': False, 'error': f'JSON 解析失败: {exc}'}
            return 400, {**cors, 'Content-Type': 'application/json'}, json.dumps(err).encode()
        try:
            result = run_missile_interception_json(payload)
            body_bytes = json.dumps(result, ensure_ascii=False).encode('utf-8')
        except Exception as exc:
            print(f'[miniprogram_api] 饱和打击未捕获异常: {exc}', flush=True)
            err = {'success': False, 'error': f'服务器内部错误: {exc}'}
            body_bytes = json.dumps(err, ensure_ascii=False).encode('utf-8')
        headers = {**cors, 'Content-Type': 'application/json; charset=utf-8'}
        return 200, headers, body_bytes

    if method == 'POST' and route == '/api/combat_radius/simulate':
        if not body:
            err = {'success': False, 'error': '请求体为空'}
            return 400, {**cors, 'Content-Type': 'application/json'}, json.dumps(err).encode()
        try:
            payload = json.loads(body.decode('utf-8'))
        except json.JSONDecodeError as exc:
            err = {'success': False, 'error': f'JSON 解析失败: {exc}'}
            return 400, {**cors, 'Content-Type': 'application/json'}, json.dumps(err).encode()
        try:
            result = run_combat_radius_json(payload)
            body_bytes = json.dumps(result, ensure_ascii=False).encode('utf-8')
        except Exception as exc:
            print(f'[miniprogram_api] 作战半径未捕获异常: {exc}', flush=True)
            err = {'success': False, 'error': f'服务器内部错误: {exc}'}
            body_bytes = json.dumps(err).encode('utf-8')
        headers = {**cors, 'Content-Type': 'application/json; charset=utf-8'}
        return 200, headers, body_bytes

    err = {'error': 'Not Found'}
    return 404, {**cors, 'Content-Type': 'application/json'}, json.dumps(err).encode()


class _ApiHandler(BaseHTTPRequestHandler):
    """stdlib HTTP 处理器，委托 handle_request。"""

    def log_message(self, format: str, *args: Any) -> None:
        print(f'[miniprogram_api] {self.address_string()} - {format % args}', flush=True)

    def _respond(self, status: int, headers: dict[str, str], body: bytes) -> None:
        self.send_response(status)
        for k, v in headers.items():
            self.send_header(k, v)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        status, headers, body = handle_request('OPTIONS', self.path, None)
        self._respond(status, headers, body)

    def do_GET(self) -> None:
        status, headers, body = handle_request('GET', self.path, None)
        self._respond(status, headers, body)

    def do_POST(self) -> None:
        length = int(self.headers.get('Content-Length', 0))
        raw = self.rfile.read(length) if length else b''
        status, headers, body = handle_request('POST', self.path, raw)
        self._respond(status, headers, body)


def serve(host: str = '127.0.0.1', port: int = 8765) -> None:
    """启动小程序仿真 API 服务。"""
    try:
        server = ThreadingHTTPServer((host, port), _ApiHandler)
    except OSError as exc:
        if getattr(exc, 'errno', None) == 48:
            print(f'端口 {port} 已被占用，小程序仿真 API 可能已在运行。', flush=True)
            print(f'  可直接访问: http://{host}:{port}/api/data', flush=True)
            print(f'  若要重启: kill $(lsof -t -i :{port}) 后再运行本脚本', flush=True)
            raise SystemExit(1) from exc
        raise

    print(f'小程序仿真 API 运行于 http://{host}:{port}', flush=True)
    print('  GET  /api/data                  — 航母/战斗机/饱和打击预设', flush=True)
    print('  POST /api/simulate              — 起飞仿真', flush=True)
    print('  POST /api/missile_interception/simulate   — 饱和打击仿真', flush=True)
    print('  POST /api/combat_radius/simulate          — 作战半径 / 升阻比与军推估算', flush=True)
    print('  （iOS App 不使用本服务，在设备本地 Pyodide 计算）', flush=True)
    if host in ('0.0.0.0', '::'):
        lan = _guess_lan_ip()
        if lan:
            print(f'  真机调试：miniprogram/config.js 中 apiBaseUrl 改为 http://{lan}:{port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n已停止', flush=True)
        server.server_close()


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='航母起飞仿真 — 微信小程序 HTTP API')
    parser.add_argument('--host', default='127.0.0.1', help='监听地址（默认 127.0.0.1；真机用 0.0.0.0）')
    parser.add_argument('--port', type=int, default=8765, help='监听端口（默认 8765）')
    args = parser.parse_args()
    serve(args.host, args.port)
