"""作战半径仿真 Web/JSON API（供 Pyodide / 小程序 / iOS 调用）。"""
from __future__ import annotations

import json
from typing import Any, Callable

from simulators.combat_radius.combat_radius import (
    run_aircraft_dashboard_from_params,
    run_estimate_efficiency_from_params,
    run_estimate_engine_cycle_from_params,
    run_estimate_max_speed_from_params,
    run_estimate_radius_from_params,
    run_estimate_thrust_from_params,
    run_predict_ld_from_params,
    run_search_best_cruise_from_params,
)
from utils.combat_radius.combat_radius_presets import (
    build_combat_radius_engine_presets_payload,
    build_combat_radius_presets_payload,
)

_ACTIONS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    'predict_ld': run_predict_ld_from_params,
    'estimate_thrust': run_estimate_thrust_from_params,
    'estimate_efficiency': run_estimate_efficiency_from_params,
    'estimate_radius': run_estimate_radius_from_params,
    'estimate_max_speed': run_estimate_max_speed_from_params,
    'aircraft_dashboard': run_aircraft_dashboard_from_params,
    'search_best_cruise': run_search_best_cruise_from_params,
    'estimate_engine_cycle': run_estimate_engine_cycle_from_params,
}


def _opt_float(v: Any, default: float) -> float:
    """解析可选浮点，空值用默认。"""
    if v is None or v == '':
        return default
    return float(v)


def _opt_bool(v: Any, default: bool = False) -> bool:
    """解析可选布尔，空值用默认。"""
    if v is None or v == '':
        return default
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v) and v != 0
    text = str(v).strip().lower()
    if text in ('1', 'true', 'yes', 'y', '是'):
        return True
    if text in ('0', 'false', 'no', 'n', '否'):
        return False
    return default


def run_combat_radius(
    action: str = 'predict_ld',
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """统一入口：仪表盘、巡航搜索、效率循环，以及原有升阻比/军推/半径/极速。"""
    params = params or {}
    if action == 'presets':
        return {
            'success': True,
            'presets': build_combat_radius_presets_payload(),
            'engine_presets': build_combat_radius_engine_presets_payload(),
        }
    handler = _ACTIONS.get(action)
    if handler is None:
        return {'success': False, 'error': f'未知 action: {action}'}
    try:
        return handler(params)
    except Exception as exc:
        return {'success': False, 'error': str(exc)}


def run_combat_radius_json(payload: dict[str, Any] | str) -> dict[str, Any]:
    """解析 JSON/dict 载荷并运行作战半径 API。"""
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError as exc:
            return {'success': False, 'error': f'JSON 解析失败: {exc}'}
    if not isinstance(payload, dict):
        return {'success': False, 'error': '载荷必须为对象'}
    action = str(payload.get('action', 'predict_ld'))
    params = payload.get('params')
    if params is None:
        params = {k: v for k, v in payload.items() if k != 'action'}
    return run_combat_radius(action=action, params=params)
