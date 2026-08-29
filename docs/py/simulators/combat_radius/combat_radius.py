"""作战半径仿真核心。

1. 根据几何参数与两锚点标定，估算巡航升阻比；
2. 根据发动机涵道比/总压比/T4/海平面军推，估算给定高度与马赫数下的可用军推；
3. 由空战重量与 L/D 求阻力，再与可用军推得到负载比，估算热/推进/总效率与 TSFC；
4. 在给定马赫下搜索 L/D×η_o 最大且阻力不超过军推 92% 的高度，用布雷盖公式估作战半径。
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from typing import Any

# 支持直接运行：python3 simulators/combat_radius/combat_radius.py
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


from utils.combat_radius.breguet import average_fuel_kg_per_km, combat_radius_m
from utils.combat_radius.cruise_load import (
    N_MISSILES_DEFAULT,
    clamp_load,
    combat_mass_breakdown,
    cruise_drag_n,
    engine_load_ratio,
)
from utils.combat_radius.cruise_search import (
    ALT_COARSE_M,
    ALT_MAX_M,
    ALT_MIN_M,
    ALT_REFINE_M,
    FIXED_MACHS,
    MACH_SEARCH_HI,
    MACH_SEARCH_ITERS,
    MACH_SEARCH_LO,
    THRUST_MARGIN_DEFAULT,
    CruiseContext,
    scored_to_dict,
    search_best_altitude,
    search_max_cruise_mach,
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
    mach_angle_rad,
    mach_cone_limit,
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


def _calibrate_from_params(params: dict[str, Any]) -> tuple[Aircraft, float, float]:
    """从请求标定 (Cf0, k_e)，并返回覆盖了待估机几何的 Aircraft。"""
    target = aircraft_from_dict(_require_aircraft_params(params, 'target'))
    ld_info = run_predict_ld_from_params({
        'anchor1': _require_aircraft_params(params, 'anchor1'),
        'ld1_target': params.get('ld1_target', params.get('ld1')),
        'anchor2': _require_aircraft_params(params, 'anchor2'),
        'ld2_target': params.get('ld2_target', params.get('ld2')),
        'target': _require_aircraft_params(params, 'target'),
    })
    return target, float(ld_info['Cf0']), float(ld_info['k_e'])


def _infeasible_point(point_id: str, label: str, mach: float | None) -> dict[str, Any]:
    """给定马赫在搜索高度带内找不到满足推力裕度的点。"""
    return {
        'id': point_id,
        'label': label,
        'mach': mach,
        'feasible': False,
        'warning': 'no_feasible_altitude',
        'radius_m': None,
        'radius_km': None,
        'fuel_kg_per_km': None,
    }


def _enrich_radius_point(
    point_id: str,
    label: str,
    scored: Any,
    mass_initial_kg: float,
    mass_final_kg: float,
    fuel_kg: float,
) -> dict[str, Any]:
    """把评分点补上布雷盖作战半径与平均油耗。"""
    row = scored_to_dict(scored)
    row['id'] = point_id
    row['label'] = label
    if scored.tsfc_kg_n_s is None or scored.v0 <= 0 or scored.eta_o <= 0:
        row['feasible'] = False
        row['warning'] = row.get('warning') or 'tsfc_unavailable'
        row['radius_m'] = None
        row['radius_km'] = None
        row['fuel_kg_per_km'] = None
        return row
    radius = combat_radius_m(
        scored.v0, scored.tsfc_kg_n_s, scored.ld, mass_initial_kg, mass_final_kg,
    )
    row['radius_m'] = radius
    row['radius_km'] = radius / 1000.0
    row['fuel_kg_per_km'] = average_fuel_kg_per_km(fuel_kg, radius)
    return row


def run_estimate_radius_from_params(params: dict[str, Any]) -> dict[str, Any]:
    """串联升阻比、军推与效率，搜索最佳巡航高度并估算作战半径。

    固定评估 Ma 0.8 / 1.5 / 1.76，以及阻力不超过军推 92% 的最大巡航马赫。
    布雷盖质量：起飞 = 空重 + 飞行员×0.1 t + 满内油 + 默认 4 枚中距弹；
    终了 = 空重 + 飞行员×0.1 t + 4 枚中距弹（燃油耗尽，不抛弹）。
    巡航 L/D 仍用一半内油的空战重量。
    """
    n_engines = _optional_int(params.get('n_engines'), 1)
    if n_engines < 1:
        raise ValueError('发动机台数须至少为 1')

    target, cf0, k_e = _calibrate_from_params(params)
    n_missiles = float(params.get('n_missiles', N_MISSILES_DEFAULT))
    cruise_mass = combat_mass_breakdown(
        empty_kg=float(params['empty_kg']),
        internal_fuel_kg=float(params['internal_fuel_kg']),
        n_pilots=float(params.get('n_pilots', 1)),
        missile_mass_kg=float(params.get('missile_mass_kg', 0)),
        n_missiles=n_missiles,
        fuel_fraction=0.5,
    )
    takeoff_mass = combat_mass_breakdown(
        empty_kg=float(params['empty_kg']),
        internal_fuel_kg=float(params['internal_fuel_kg']),
        n_pilots=float(params.get('n_pilots', 1)),
        missile_mass_kg=float(params.get('missile_mass_kg', 0)),
        n_missiles=n_missiles,
        fuel_fraction=1.0,
    )
    dry_mass = combat_mass_breakdown(
        empty_kg=float(params['empty_kg']),
        internal_fuel_kg=float(params['internal_fuel_kg']),
        n_pilots=float(params.get('n_pilots', 1)),
        missile_mass_kg=float(params.get('missile_mass_kg', 0)),
        n_missiles=n_missiles,
        fuel_fraction=0.0,
    )
    fuel_kg = float(params['internal_fuel_kg'])

    t4max = float(params.get('t4_K', params.get('t4', params.get('T4max'))))
    ctx = CruiseContext(
        target=target,
        cf0=cf0,
        k_e=k_e,
        mass_kg=cruise_mass['total_kg'],
        n_engines=n_engines,
        bpr=float(params['bpr']),
        opr=float(params['opr']),
        t4_K=t4max,
        tsl_N=parse_sea_level_thrust_n(params),
        eta_c=float(params['eta_c']) if params.get('eta_c') not in (None, '') else ETA_C_DEFAULT,
        fan_pr_override=_optional_float(params.get('fan_pr_override', params.get('fan_pr'))),
        fpr=_optional_float(params.get('FPR', params.get('fan_pr_override'))),
        eps=float(params['eps']) if params.get('eps') not in (None, '') else EPS_DEFAULT,
        etan=float(params['etan']) if params.get('etan') not in (None, '') else ETAN_DEFAULT,
        acc_frac=float(params['acc_frac']) if params.get('acc_frac') not in (None, '') else ACC_FRAC_DEFAULT,
        t4idle=float(params['T4idle']) if params.get('T4idle') not in (None, '') else T4IDLE_DEFAULT,
        thrust_margin=float(params['thrust_margin']) if params.get('thrust_margin') not in (None, '') else THRUST_MARGIN_DEFAULT,
    )

    alt_min = float(params['alt_min_m']) if params.get('alt_min_m') not in (None, '') else ALT_MIN_M
    alt_max = float(params['alt_max_m']) if params.get('alt_max_m') not in (None, '') else ALT_MAX_M
    coarse_m = float(params['alt_coarse_m']) if params.get('alt_coarse_m') not in (None, '') else ALT_COARSE_M
    refine_m = float(params['alt_refine_m']) if params.get('alt_refine_m') not in (None, '') else ALT_REFINE_M
    mach_lo = float(params['mach_search_lo']) if params.get('mach_search_lo') not in (None, '') else MACH_SEARCH_LO
    mach_hi = float(params['mach_search_hi']) if params.get('mach_search_hi') not in (None, '') else MACH_SEARCH_HI
    mach_iters = _optional_int(params.get('mach_search_iters'), MACH_SEARCH_ITERS)

    def pack_point(point_id: str, label: str, mach: float) -> dict[str, Any]:
        scored = search_best_altitude(
            ctx, mach, alt_min, alt_max, coarse_m, refine_m,
        )
        if scored is None:
            return _infeasible_point(point_id, label, mach)
        return _enrich_radius_point(
            point_id, label, scored,
            takeoff_mass['total_kg'], dry_mass['total_kg'], fuel_kg,
        )

    points: list[dict[str, Any]] = []
    for mach in FIXED_MACHS:
        label = f'Ma {mach:g}'
        point_id = f'mach_{str(mach).replace(".", "_")}'
        points.append(pack_point(point_id, label, mach))

    max_mach = search_max_cruise_mach(
        ctx, mach_lo, mach_hi, mach_iters, alt_min, alt_max, coarse_m,
    )
    if max_mach is None:
        points.append(_infeasible_point('max_cruise', '最大巡航', None))
    else:
        max_row = pack_point('max_cruise', '最大巡航', max_mach)
        points.append(max_row)

    mach_angle_deg = None
    m_cone = None
    if target.length_m > 0 and target.wingspan_m > 0:
        phi = mach_angle_rad(target.length_m, target.wingspan_m)
        mach_angle_deg = math.degrees(phi)
        m_cone = mach_cone_limit(phi)

    return {
        'success': True,
        'name': str(params.get('name') or target.name),
        'Cf0': cf0,
        'k_e': k_e,
        'n_engines': n_engines,
        'thrust_margin': ctx.thrust_margin,
        'mass_cruise_kg': cruise_mass['total_kg'],
        'mass_initial_kg': takeoff_mass['total_kg'],
        'mass_final_kg': dry_mass['total_kg'],
        'fuel_kg': fuel_kg,
        'n_missiles': n_missiles,
        'length_m': target.length_m,
        'wingspan_m': target.wingspan_m,
        'mach_angle_deg': mach_angle_deg,
        'mach_cone_limit': m_cone,
        'max_cruise_mach': max_mach,
        'points': points,
        'note': '全程平飞布雷盖估算，未计入爬升、下降、起飞、降落与返场余油。',
    }


def main() -> None:
    """命令行入口：默认用 F-22 + F119 打印四个巡航点的作战半径。"""
    parser = argparse.ArgumentParser(description='飞机作战半径估算（全程平飞布雷盖）')
    parser.add_argument('--aircraft', default='F-22', help='待估机型预设 id')
    parser.add_argument('--engine', default='f119', help='发动机预设 id')
    parser.add_argument('--anchor1', default='F-35C')
    parser.add_argument('--anchor2', default='F-22')
    args = parser.parse_args()

    from utils.combat_radius.combat_radius_presets import (
        get_preset_by_id,
        load_engine_presets,
        load_presets,
    )

    presets = load_presets()
    engines = load_engine_presets()
    tgt = get_preset_by_id(presets, args.aircraft)
    a1 = get_preset_by_id(presets, args.anchor1)
    a2 = get_preset_by_id(presets, args.anchor2)
    eng = get_preset_by_id(engines, args.engine)
    if tgt is None or a1 is None or a2 is None:
        raise SystemExit('找不到机型预设')
    if eng is None:
        raise SystemExit('找不到发动机预设')
    if eng.get('tsl_kN') is None:
        raise SystemExit(f'发动机 {args.engine} 未填写海平面军推 tsl_kN')

    params = {
        'anchor1': a1,
        'ld1_target': a1.get('ld_known', 8.8),
        'anchor2': a2,
        'ld2_target': a2.get('ld_known', 8.0),
        'target': tgt,
        'empty_kg': tgt['empty_kg'],
        'internal_fuel_kg': tgt['internal_fuel_kg'],
        'n_pilots': tgt.get('n_pilots', 1),
        'missile_mass_kg': tgt.get('missile_mass_kg', 0),
        'n_missiles': N_MISSILES_DEFAULT,
        'n_engines': tgt.get('n_engines', 1),
        'bpr': eng['bpr'],
        'opr': eng['opr'],
        't4_K': eng['t4_K'],
        'tsl_kN': eng['tsl_kN'],
        'name': f'{tgt["name"]} / {eng["name"]}',
    }
    result = run_estimate_radius_from_params(params)
    print(f'{result["name"]}')
    if result['mach_angle_deg'] is not None:
        max_m = result['max_cruise_mach']
        max_txt = f'{max_m:.3f}' if max_m is not None else '—'
        print(
            f'马赫角 {result["mach_angle_deg"]:.1f}° · '
            f'锥限 Ma {result["mach_cone_limit"]:.2f} · '
            f'最大巡航 Ma {max_txt}'
        )
    print(
        f'{"点":<10} {"Ma":>6} {"高度km":>8} {"L/D":>7} {"η_o%":>7} '
        f'{"TSFC":>8} {"军推kN":>8} {"负载%":>7} {"半径km":>8} {"kg/km":>7}'
    )
    for p in result['points']:
        if not p.get('feasible'):
            mach_txt = f'{p["mach"]:>6.3f}' if p.get('mach') is not None else f'{"—":>6}'
            print(f'{p["label"]:<10} {mach_txt}  （无满足 92% 推力裕度的高度）')
            continue
        print(
            f'{p["label"]:<10} {p["mach"]:>6.3f} {p["alt_m"]/1000:>8.1f} '
            f'{p["ld"]:>7.2f} {100*p["eta_o"]:>7.1f} {p["tsfc_mg_n_s"]:>8.2f} '
            f'{p["thrust_avail_kN"]:>8.1f} {100*p["load"]:>7.1f} '
            f'{p["radius_km"]:>8.0f} {p["fuel_kg_per_km"]:>7.2f}'
        )
    print(result['note'])


if __name__ == '__main__':
    main()

