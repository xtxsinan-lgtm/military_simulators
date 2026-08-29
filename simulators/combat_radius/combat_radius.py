"""作战半径仿真核心。

当前实现：
1. 根据几何参数与两锚点标定，估算巡航升阻比；
2. 根据发动机涵道比/总压比/T4/海平面军推，估算给定高度与马赫数下的可用军推；
3. 由空战重量与 L/D 求阻力，再与可用军推得到负载比，估算热/推进/总效率与 TSFC。
后续将接入任务剖面与作战半径积分。
"""
from __future__ import annotations

from typing import Any

from utils.combat_radius.cruise_load import (
    N_MISSILES_DEFAULT,
    clamp_load,
    combat_mass_breakdown,
    cruise_drag_n,
    engine_load_ratio,
)
from utils.combat_radius.engine_efficiency import (
    ACC_FRAC_DEFAULT,
    EPS_DEFAULT,
    ETAN_DEFAULT,
    T4IDLE_DEFAULT,
    compute_engine_efficiency,
    engine_result_to_dict,
    tsfc_from_eta_o,
)
from utils.combat_radius.lift_drag import (
    KAPPA_A,
    Aircraft,
    aircraft_from_dict,
    calibrate,
    predict_ld,
)
from utils.combat_radius.military_thrust import (
    ETA_C_DEFAULT,
    estimate_military_thrust,
    thrust_result_to_dict,
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


def _optional_float(value: Any) -> float | None:
    """空值视为未提供；否则转为 float。"""
    if value is None or value == '':
        return None
    return float(value)


def parse_sea_level_thrust_n(params: dict[str, Any]) -> float:
    """从 tsl_N 或 tsl_kN 读取海平面军推（牛顿）。"""
    if params.get('tsl_N') not in (None, ''):
        return float(params['tsl_N'])
    if params.get('tsl_kN') not in (None, ''):
        return float(params['tsl_kN']) * 1000.0
    raise ValueError('缺少海平面军推 tsl_N 或 tsl_kN')


def run_estimate_thrust_from_params(params: dict[str, Any]) -> dict[str, Any]:
    """从 JSON 参数估算可用军推。"""
    result = estimate_military_thrust(
        bpr=float(params['bpr']),
        opr=float(params['opr']),
        t4_K=float(params.get('t4_K', params.get('t4'))),
        tsl_N=parse_sea_level_thrust_n(params),
        alt_m=float(params['alt_m']),
        mach=float(params['mach']),
        eta_c=float(params['eta_c']) if params.get('eta_c') not in (None, '') else ETA_C_DEFAULT,
        fan_pr_override=_optional_float(params.get('fan_pr_override', params.get('fan_pr'))),
    )
    payload = thrust_result_to_dict(result)
    payload['success'] = True
    payload['name'] = str(params.get('name') or '')
    return payload


def _optional_int(value: Any, default: int) -> int:
    """空值用默认整数；否则转为 int。"""
    if value is None or value == '':
        return default
    return int(float(value))


def run_estimate_efficiency_from_params(params: dict[str, Any]) -> dict[str, Any]:
    """由 L/D、空战重量与可用军推估算负载比、总效率与 TSFC。

    若提供锚点+待估机几何，则在给定高度/马赫数下重算 L/D；
    也可直接传入 ld，跳过升阻比标定。
    """
    alt_m = float(params['alt_m'])
    mach = float(params['mach'])
    n_engines = _optional_int(params.get('n_engines'), 1)
    if n_engines < 1:
        raise ValueError('发动机台数须至少为 1')

    ld_override = _optional_float(params.get('ld'))
    ld_info: dict[str, Any] = {}
    if ld_override is not None:
        ld = ld_override
    else:
        target_raw = dict(_require_aircraft_params(params, 'target'))
        target_raw['mach'] = mach
        target_raw['alt_m'] = alt_m
        ld_params = {
            'anchor1': _require_aircraft_params(params, 'anchor1'),
            'ld1_target': params.get('ld1_target', params.get('ld1')),
            'anchor2': _require_aircraft_params(params, 'anchor2'),
            'ld2_target': params.get('ld2_target', params.get('ld2')),
            'target': target_raw,
        }
        ld_info = run_predict_ld_from_params(ld_params)
        ld = float(ld_info['target']['ld'])

    breakdown = combat_mass_breakdown(
        empty_kg=float(params['empty_kg']),
        internal_fuel_kg=float(params['internal_fuel_kg']),
        n_pilots=float(params.get('n_pilots', 1)),
        missile_mass_kg=float(params.get('missile_mass_kg', 0)),
        n_missiles=float(params.get('n_missiles', N_MISSILES_DEFAULT)),
    )
    drag_n = cruise_drag_n(breakdown['total_kg'], ld)

    thrust_one = estimate_military_thrust(
        bpr=float(params['bpr']),
        opr=float(params['opr']),
        t4_K=float(params.get('t4_K', params.get('t4'))),
        tsl_N=parse_sea_level_thrust_n(params),
        alt_m=alt_m,
        mach=mach,
        eta_c=float(params['eta_c']) if params.get('eta_c') not in (None, '') else ETA_C_DEFAULT,
        fan_pr_override=_optional_float(params.get('fan_pr_override', params.get('fan_pr'))),
    )
    thrust_avail_n = thrust_one.thrust_N * n_engines
    load_raw = engine_load_ratio(drag_n, thrust_avail_n)
    load = clamp_load(load_raw)

    t4max = float(params.get('t4_K', params.get('t4', params.get('T4max'))))
    eff = compute_engine_efficiency(
        bpr=float(params['bpr']),
        mach=mach,
        altitude_m=alt_m,
        load=load,
        OPR=float(params['opr']),
        FPR=_optional_float(params.get('FPR', params.get('fan_pr_override'))),
        T4max=t4max,
        T4idle=float(params['T4idle']) if params.get('T4idle') not in (None, '') else T4IDLE_DEFAULT,
        eps=float(params['eps']) if params.get('eps') not in (None, '') else EPS_DEFAULT,
        etan=float(params['etan']) if params.get('etan') not in (None, '') else ETAN_DEFAULT,
        acc_frac=float(params['acc_frac']) if params.get('acc_frac') not in (None, '') else ACC_FRAC_DEFAULT,
    )
    if not eff.valid:
        raise ValueError(f'效率循环无解（{eff.warning or "unknown"}）')

    payload: dict[str, Any] = {
        'success': True,
        'ld': ld,
        'mass_kg': breakdown['total_kg'],
        'mass_breakdown': breakdown,
        'drag_N': drag_n,
        'drag_kN': drag_n / 1000.0,
        'n_engines': n_engines,
        'thrust_per_engine_N': thrust_one.thrust_N,
        'thrust_avail_N': thrust_avail_n,
        'thrust_avail_kN': thrust_avail_n / 1000.0,
        'load_raw': load_raw,
        'load': load,
        'name': str(params.get('name') or ''),
    }
    payload.update(thrust_result_to_dict(thrust_one))
    payload.update(engine_result_to_dict(eff))
    # 整机可用推力覆盖单发 thrust_N 字段，避免与前端军推面板混淆
    payload['thrust_N'] = thrust_avail_n
    payload['thrust_kN'] = thrust_avail_n / 1000.0

    warnings: list[str] = []
    if load_raw > 1.0:
        warnings.append('load_exceeds_thrust')
    if eff.warning:
        warnings.append(eff.warning)
    payload['warning'] = ','.join(warnings) if warnings else None

    if eff.eta_o > 0 and eff.V0 > 0:
        payload.update(tsfc_from_eta_o(eff.V0, eff.eta_o))
    else:
        payload['tsfc_kg_n_s'] = None
        payload['tsfc_mg_n_s'] = None
        payload['tsfc_lb_lbf_h'] = None

    if ld_info:
        payload['Cf0'] = ld_info['Cf0']
        payload['k_e'] = ld_info['k_e']
        payload['target'] = ld_info['target']
    return payload
