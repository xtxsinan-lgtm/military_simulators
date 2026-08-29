"""作战半径仿真核心。

当前实现第一部分：根据几何参数与两锚点标定，估算巡航升阻比。
后续将接入燃油消耗、任务剖面与作战半径积分。
"""
from __future__ import annotations

from typing import Any

from utils.combat_radius.lift_drag import (
    KAPPA_A,
    Aircraft,
    aircraft_from_dict,
    calibrate,
    predict_ld,
)


def format_ld_row(
    ac: Aircraft,
    cf0: float,
    k_e: float,
    target_ld: float | None = None,
) -> dict[str, Any]:
    """单机 L/D 与阻力分解，供前端表格渲染。"""
    ld, breakdown = predict_ld(ac, cf0, k_e)
    row: dict[str, Any] = {
        'name': ac.name,
        'ld': ld,
        'CL': breakdown['CL'],
        'e_used': breakdown['e_used'],
        'CD0': breakdown['CD0'],
        'CDi': breakdown['CDi'],
        'CDw': breakdown['CDw'],
        'CD': breakdown['CD'],
    }
    if target_ld is not None:
        row['target_ld'] = target_ld
        row['error'] = ld - target_ld
    return row


def run_predict_ld(
    anchor1: Aircraft,
    ld1_target: float,
    anchor2: Aircraft,
    ld2_target: float,
    target: Aircraft,
) -> dict[str, Any]:
    """标定两锚点并估算目标机型 L/D。"""
    cf0, k_e = calibrate(anchor1, ld1_target, anchor2, ld2_target)
    return {
        'success': True,
        'Cf0': cf0,
        'k_e': k_e,
        'kappa_A': KAPPA_A,
        'anchors': [
            format_ld_row(anchor1, cf0, k_e, ld1_target),
            format_ld_row(anchor2, cf0, k_e, ld2_target),
        ],
        'target': format_ld_row(target, cf0, k_e),
    }


def _require_aircraft_params(params: dict[str, Any], key: str) -> dict[str, Any]:
    """从请求中取出机型字典；缺失或类型不对时抛出 ValueError。"""
    raw = params.get(key)
    if not isinstance(raw, dict):
        raise ValueError(f'缺少机型参数 {key}')
    return raw


def run_predict_ld_from_params(params: dict[str, Any]) -> dict[str, Any]:
    """从 JSON 参数运行升阻比估算。"""
    anchor1 = aircraft_from_dict(_require_aircraft_params(params, 'anchor1'))
    anchor2 = aircraft_from_dict(_require_aircraft_params(params, 'anchor2'))
    target = aircraft_from_dict(_require_aircraft_params(params, 'target'))
    ld1 = float(params.get('ld1_target', params.get('ld1')))
    ld2 = float(params.get('ld2_target', params.get('ld2')))
    return run_predict_ld(anchor1, ld1, anchor2, ld2, target)
