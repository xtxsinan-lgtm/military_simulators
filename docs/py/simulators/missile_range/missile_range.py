"""导弹射程仿真入口：按弹种估算单发，并按同一推进剂假设刷新样本表。"""
from __future__ import annotations

from typing import Any

from utils.missile_range.classes import estimate_by_class
from utils.missile_range.dataset import (
    all_missile_cases,
    build_missile_range_catalog_payload,
    evaluate_dataset,
)
from utils.missile_range.estimate import (
    DEFAULT_ISP_S,
    DEFAULT_PROPELLANT_DENSITY,
)


def opt_float(value: Any, default: float) -> float:
    """解析可选浮点；空值使用默认。"""
    if value is None or value == '':
        return default
    return float(value)


def _required_float(params: dict[str, Any], key: str) -> float:
    if key not in params or params[key] is None or params[key] == '':
        raise ValueError(f'缺少参数 {key}')
    return float(params[key])


def run_estimate_from_params(params: dict[str, Any] | None) -> dict[str, Any]:
    """按表单参数估算一发，并用同一比冲/密度重算预设表。"""
    params = params or {}
    try:
        isp = opt_float(params.get('isp_s'), DEFAULT_ISP_S)
        density = opt_float(params.get('propellant_density'), DEFAULT_PROPELLANT_DENSITY)
        result = estimate_by_class(
            missile_class=str(params.get('missile_class') or 'hgv_biconic'),
            length_m=_required_float(params, 'length_m'),
            diameter_m=_required_float(params, 'diameter_m'),
            warhead_mass_kg=_required_float(params, 'warhead_kg'),
            v_launch_mach=opt_float(params.get('v_launch_mach'), 0.85),
            h_launch_km=opt_float(params.get('h_launch_km'), 13.0),
            isp_s=isp,
            propellant_density=density,
        )
        rows = evaluate_dataset(isp_s=isp, propellant_density=density)
    except (TypeError, ValueError) as exc:
        return {'success': False, 'error': str(exc)}
    return {'success': True, 'result': result, 'rows': rows}


def run_dataset_from_params(params: dict[str, Any] | None) -> dict[str, Any]:
    """只重算预设样本表。"""
    params = params or {}
    try:
        rows = evaluate_dataset(
            isp_s=opt_float(params.get('isp_s'), DEFAULT_ISP_S),
            propellant_density=opt_float(params.get('propellant_density'), DEFAULT_PROPELLANT_DENSITY),
        )
    except (TypeError, ValueError) as exc:
        return {'success': False, 'error': str(exc)}
    return {'success': True, 'rows': rows, 'count': len(all_missile_cases())}


def run_presets_from_params(params: dict[str, Any] | None = None) -> dict[str, Any]:
    """返回目录中的弹种、默认值和默认推进剂下的样本表。"""
    del params
    payload = build_missile_range_catalog_payload()
    return {'success': True, **payload}
