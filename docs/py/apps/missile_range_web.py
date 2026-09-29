"""导弹射程估算 Web/JSON API（供 Pyodide / 小程序 / iOS 调用）。"""
from __future__ import annotations

import json
from typing import Any, Callable

from simulators.missile_range.missile_range import (
    run_dataset_from_params,
    run_estimate_from_params,
    run_presets_from_params,
)

_ACTIONS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    'estimate': run_estimate_from_params,
    'dataset': run_dataset_from_params,
    'presets': run_presets_from_params,
}


def run_missile_range(
    action: str = 'estimate',
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """统一入口：估算单发、重算样本表或读取预设。"""
    handler = _ACTIONS.get(action)
    if handler is None:
        return {'success': False, 'error': f'未知 action: {action}'}
    try:
        return handler(params or {})
    except Exception as exc:
        return {'success': False, 'error': str(exc)}


def run_missile_range_json(payload: dict[str, Any] | str) -> dict[str, Any]:
    """解析 JSON/dict 载荷并运行导弹射程 API。"""
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError as exc:
            return {'success': False, 'error': f'JSON 解析失败: {exc}'}
    if not isinstance(payload, dict):
        return {'success': False, 'error': '载荷必须为对象'}
    action = str(payload.get('action', 'estimate'))
    params = payload.get('params')
    if params is None:
        params = {k: v for k, v in payload.items() if k != 'action'}
    if not isinstance(params, dict):
        return {'success': False, 'error': 'params 必须为对象'}
    return run_missile_range(action=action, params=params)
