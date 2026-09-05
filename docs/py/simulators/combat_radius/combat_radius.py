"""作战半径仿真核心。

1. 用统一物理模型 (Cf0, k_e) 由几何估算巡航升阻比；
2. 根据发动机涵道比/总压比/T4/海平面军推，估算给定高度与马赫数下的可用军推；
3. 由空战重量与 L/D 求阻力，再与可用军推得到负载比，估算热/推进/总效率与 TSFC；
4. 在给定马赫下搜索 L/D×η_o 最大且阻力不超过军推 92% 的高度；
   「实用最大巡航速度」在 Ma 1.2 以上取最佳巡航高度达到最大值时的速度；
   「最大巡航速度」是 11–20 km 内仍能军推平飞的最大可能巡航马赫。
   若高度峰值与 Ma 1.2 以上作战半径最大的马赫不同，表尾插入「最大半径超音速巡航速度」。
   先按出发/返回重量算瞬时油耗，再把（冗余−降落节省）加到空重上、
   内油减去该值与爬升额外后重新做布雷盖。
"""
from __future__ import annotations

import argparse
import math
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

# 支持直接运行：python3 simulators/combat_radius/combat_radius.py
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


from utils.combat_radius.breguet import (
    average_fuel_kg_per_km,
    combat_radius_m,
    mission_fuel_budget,
    mixed_combat_radius_m,
)
from utils.combat_radius.combat_radius_config import (
    dry_to_max_thrust_ratio,
    mission_fuel_config,
    reserve_kind_label,
    reserve_min_for_mission,
)
from utils.combat_radius.cruise_load import (
    N_MISSILES_DEFAULT,
    apply_derived_planform_loads,
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
    MACH_PROFILE_STEP,
    MACH_SEARCH_HI,
    MACH_SEARCH_ITERS,
    MACH_SEARCH_LO,
    PRACTICAL_MAX_CRUISE_MACH_LO,
    THRUST_MARGIN_DEFAULT,
    CruiseContext,
    CruiseScored,
    SUPERSONIC_MACH,
    contiguous_peak_max_mach,
    evaluate_cruise_forces,
    max_ld_fields,
    scan_best_altitude_profile,
    score_cruise_point,
    scored_to_dict,
    search_best_altitude,
    search_max_possible_cruise_mach,
    search_max_ld_altitude,
    snap_mach,
)
from utils.combat_radius.engine_efficiency import (
    ACC_FRAC_DEFAULT,
    EPS_DEFAULT,
    ETAN_DEFAULT,
    T4IDLE_DEFAULT,
    compute_engine_efficiency,
    engine_result_to_dict,
    eta_o_after_install,
    parse_tsfc_install_mult,
    tsfc_from_eta_o,
)
from utils.combat_radius.lift_drag import (
    KAPPA_A,
    Aircraft,
    aircraft_from_dict,
    aircraft_mach_angle_rad,
    mach_cone_limit,
    model_coefficients,
    predict_ld,
)
from utils.combat_radius.max_speed_search import (
    ALT_COARSE_M as MAX_SPEED_ALT_COARSE_M,
    ALT_MAX_M as MAX_SPEED_ALT_MAX_M,
    ALT_MIN_M as MAX_SPEED_ALT_MIN_M,
    ALT_REFINE_M as MAX_SPEED_ALT_REFINE_M,
    MACH_SEARCH_HI as MAX_SPEED_MACH_HI,
    MACH_SEARCH_ITERS as MAX_SPEED_MACH_ITERS,
    MACH_SEARCH_LO as MAX_SPEED_MACH_LO,
    MAX_SPEED_THRUST_MARGIN,
    search_global_max_speed,
)
from utils.combat_radius.military_thrust import (
    ETA_C_DEFAULT,
    estimate_military_thrust,
    thrust_result_to_dict,
)

PRACTICAL_MAX_CRUISE_ID = 'max_cruise'
PRACTICAL_MAX_CRUISE_LABEL = '实用最大巡航速度'
MAX_POSSIBLE_CRUISE_ID = 'max_possible_cruise'
MAX_POSSIBLE_CRUISE_LABEL = '最大巡航速度'
MAX_RADIUS_CRUISE_ID = 'max_radius_cruise'
MAX_RADIUS_CRUISE_LABEL = '最大半径超音速巡航速度'
SPLIT_CRUISE_MACH_TOL = 0.005
NAMED_CRUISE_LIMITS = {
    PRACTICAL_MAX_CRUISE_ID: PRACTICAL_MAX_CRUISE_LABEL,
    MAX_RADIUS_CRUISE_ID: MAX_RADIUS_CRUISE_LABEL,
    MAX_POSSIBLE_CRUISE_ID: MAX_POSSIBLE_CRUISE_LABEL,
}


def cruise_limit_specs(
    practical_mach: float | None,
    possible_mach: float | None,
    max_radius_mach: float | None = None,
) -> list[tuple[str, str, float | None]]:
    """表尾：始终实用最大巡航，必要时插入最大半径超音速巡航，再最大可能巡航。"""
    rows: list[tuple[str, str, float | None]] = [
        (PRACTICAL_MAX_CRUISE_ID, NAMED_CRUISE_LIMITS[PRACTICAL_MAX_CRUISE_ID], practical_mach),
    ]
    if cruise_machs_differ(practical_mach, max_radius_mach):
        rows.append((
            MAX_RADIUS_CRUISE_ID,
            NAMED_CRUISE_LIMITS[MAX_RADIUS_CRUISE_ID],
            max_radius_mach,
        ))
    rows.append((
        MAX_POSSIBLE_CRUISE_ID,
        NAMED_CRUISE_LIMITS[MAX_POSSIBLE_CRUISE_ID],
        possible_mach,
    ))
    return rows


def cruise_machs_differ(
    a: float | None,
    b: float | None,
    tol: float = SPLIT_CRUISE_MACH_TOL,
) -> bool:
    """两个巡航马赫是否视为不同，用于决定是否插入最大半径超音速巡航行。"""
    if tol < 0:
        raise ValueError('马赫容差不能为负')
    if a is None and b is None:
        return False
    if a is None or b is None:
        return True
    return abs(float(a) - float(b)) > tol


def radius_m_from_scored(
    scored: CruiseScored,
    mass_initial_kg: float,
    mass_final_kg: float,
) -> float | None:
    """由巡航评分点算布雷盖作战半径（米）；缺 TSFC 或油量不够则 None。"""
    if scored.tsfc_kg_n_s is None or scored.v0 <= 0 or scored.ld <= 0:
        return None
    try:
        return combat_radius_m(
            scored.v0, scored.tsfc_kg_n_s, scored.ld,
            mass_initial_kg, mass_final_kg,
        )
    except ValueError:
        return None


def max_radius_mach_from_profile(
    profile: list[CruiseScored],
    mass_initial_kg: float,
    mass_final_kg: float,
    mach_lo: float = PRACTICAL_MAX_CRUISE_MACH_LO,
) -> tuple[float | None, float | None]:
    """在剖面上取 Ma≥mach_lo 且布雷盖半径最大的 (马赫, 半径km)。"""
    best_mach: float | None = None
    best_radius_m: float | None = None
    for point in profile:
        if point.mach + 1e-9 < mach_lo:
            continue
        radius_m = radius_m_from_scored(point, mass_initial_kg, mass_final_kg)
        if radius_m is None:
            continue
        if best_radius_m is None or radius_m > best_radius_m:
            best_radius_m = radius_m
            best_mach = point.mach
    if best_mach is None or best_radius_m is None:
        return None, None
    return snap_mach(best_mach, MACH_PROFILE_STEP), best_radius_m / 1000.0


def format_cruise_speed_label(point: dict[str, Any]) -> str:
    """分速表第一列：固定马赫只写数字，表尾命名行写中文名称加马赫。"""
    pid = point.get('id')
    label = str(point.get('label') or '')
    mach = point.get('mach')
    if pid in NAMED_CRUISE_LIMITS:
        name = label or NAMED_CRUISE_LIMITS[pid]
        if mach is not None:
            return f'{name} {float(mach):.3f}'
        return name or '—'
    if mach is not None:
        return f'{float(mach):.3f}'
    return label or '—'


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
        'CDa': breakdown['CDa'],
        'CDs': breakdown['CDs'],
        'CD': breakdown['CD'],
    }
    if target_ld is not None:
        row['target_ld'] = target_ld
        row['error'] = ld - target_ld
    return row


def run_predict_ld(
    target: Aircraft,
    cf0: float | None = None,
    k_e: float | None = None,
) -> dict[str, Any]:
    """用统一模型系数估算目标机型 L/D。"""
    if cf0 is None or k_e is None:
        cf0, k_e = model_coefficients()
    return {
        'success': True,
        'Cf0': cf0,
        'k_e': k_e,
        'kappa_A': KAPPA_A,
        'anchors': [],
        'target': format_ld_row(target, cf0, k_e),
    }


def _require_aircraft_params(params: dict[str, Any], key: str) -> dict[str, Any]:
    """从请求中取出机型字典；缺失或类型不对时抛出 ValueError。"""
    raw = params.get(key)
    if not isinstance(raw, dict):
        raise ValueError(f'缺少机型参数 {key}')
    return raw


def _derived_target_from_params(params: dict[str, Any]) -> dict[str, Any]:
    """取出机型字典并用翼展/翼面积/空战重量覆盖展弦比与翼载荷。"""
    raw = dict(_require_aircraft_params(params, 'target'))
    n_missiles = params.get('n_missiles', N_MISSILES_DEFAULT)
    if n_missiles in (None, ''):
        n_missiles = N_MISSILES_DEFAULT
    return apply_derived_planform_loads(
        raw,
        empty_kg=params.get('empty_kg'),
        internal_fuel_kg=params.get('internal_fuel_kg'),
        n_pilots=params.get('n_pilots'),
        missile_mass_kg=params.get('missile_mass_kg'),
        n_missiles=float(n_missiles),
    )


def run_predict_ld_from_params(params: dict[str, Any]) -> dict[str, Any]:
    """从 JSON 参数运行升阻比估算（统一模型，忽略旧锚点字段）。"""
    raw = _derived_target_from_params(params)
    if raw.get('n_stores') in (None, '') and params.get('n_missiles') not in (None, ''):
        raw['n_stores'] = float(params['n_missiles'])
    target = aircraft_from_dict(raw)
    return run_predict_ld(target)


def ensure_default_anchors(params: dict[str, Any]) -> dict[str, Any]:
    """兼容旧请求：不再填入升阻比锚点，原样返回。"""
    return dict(params)


def _optional_float(value: Any) -> float | None:
    """空值视为未提供；否则转为 float。"""
    if value is None or value == '':
        return None
    return float(value)


def _positive_thrust_value(value: Any) -> float | None:
    """推力须为正；空值、0、负数、NaN 视为未提供。"""
    if value in (None, ''):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number <= 0.0 or number != number:
        return None
    return number


def resolve_tsl_kN(params: dict[str, Any]) -> float | None:
    """解析海平面军推 (kN)：优先 tsl，缺省时用加力 × 军推/加力比例。

    前端选机后若把空军推当成 0 传来，仍应使用发动机表里的加力数字，
    避免军推循环报「参数超出有效范围」。
    """
    tsl_n = _positive_thrust_value(params.get('tsl_N'))
    if tsl_n is not None:
        return tsl_n / 1000.0
    tsl_kn = _positive_thrust_value(params.get('tsl_kN'))
    if tsl_kn is not None:
        return tsl_kn
    max_n = _positive_thrust_value(params.get('max_tsl_N'))
    if max_n is not None:
        return max_n / 1000.0 * dry_to_max_thrust_ratio()
    max_kn = _positive_thrust_value(params.get('max_tsl_kN'))
    if max_kn is not None:
        return max_kn * dry_to_max_thrust_ratio()
    return None


def parse_sea_level_thrust_n(params: dict[str, Any]) -> float:
    """从 tsl_N / tsl_kN 读取海平面军推（牛顿）；缺省则由加力按比例估计。"""
    tsl_kn = resolve_tsl_kN(params)
    if tsl_kn is None:
        raise ValueError('缺少海平面军推 tsl_N 或 tsl_kN')
    return tsl_kn * 1000.0


def parse_max_sea_level_thrust_n(params: dict[str, Any]) -> float:
    """从 max_tsl_N 或 max_tsl_kN 读取海平面加力最大推力（牛顿）。"""
    if params.get('max_tsl_N') not in (None, ''):
        return float(params['max_tsl_N'])
    if params.get('max_tsl_kN') not in (None, ''):
        return float(params['max_tsl_kN']) * 1000.0
    raise ValueError('缺少海平面加力最大推力 max_tsl_N 或 max_tsl_kN')


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


def _as_bool(value: Any, default: bool = False) -> bool:
    """解析可选布尔；空值用默认。"""
    if value is None or value == '':
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value) and value != 0
    text = str(value).strip().lower()
    if text in ('1', 'true', 'yes', 'y', '是'):
        return True
    if text in ('0', 'false', 'no', 'n', '否'):
        return False
    return default


def _parse_carrier(params: dict[str, Any]) -> bool:
    """舰载标识：优先顶层 carrier，其次待估机预设。"""
    if params.get('carrier') not in (None, ''):
        return _as_bool(params['carrier'])
    target = params.get('target')
    if isinstance(target, dict) and target.get('carrier') not in (None, ''):
        return _as_bool(target['carrier'])
    return False


def _parse_type_label(params: dict[str, Any]) -> str | None:
    """起降类型：优先顶层 type_label，其次待估机预设。"""
    raw = params.get('type_label')
    if raw not in (None, ''):
        return str(raw)
    target = params.get('target')
    if isinstance(target, dict) and target.get('type_label') not in (None, ''):
        return str(target['type_label'])
    return None


def _subsonic_scored_for_burn(
    ctx: CruiseContext,
    alt_min_m: float,
    alt_max_m: float,
    coarse_m: float,
    refine_m: float,
    fallback_alt_m: float = 12000.0,
) -> Any:
    """取 Ma 0.8 最佳高度的亚音速油耗；推力不可行时退到 12 km 仍算 TSFC。"""
    scored = search_best_altitude(
        ctx, 0.8, alt_min_m, alt_max_m, coarse_m, refine_m,
    )
    if (
        scored is not None
        and scored.tsfc_kg_n_s is not None
        and scored.v0 > 0
        and scored.ld > 0
        and scored.eta_o > 0
    ):
        return scored
    alt = min(max(fallback_alt_m, alt_min_m), alt_max_m)
    forces = evaluate_cruise_forces(ctx, 0.8, alt)
    fallback = score_cruise_point(ctx, forces)
    if (
        fallback.tsfc_kg_n_s is not None
        and fallback.v0 > 0
        and fallback.ld > 0
        and fallback.eta_o > 0
    ):
        return fallback
    return None


def _mission_fuel_note(kind: str, reserve_min: float, mf: dict[str, Any]) -> str:
    """作战半径说明：先算出发/返回瞬时油耗，再按修正质量做布雷盖。"""
    return (
        f'先按出发/返回重量算瞬时油耗（已含{kind}降落冗余 {reserve_min:g} min'
        f'，{float(mf["reserve_cruise_kph"]):g} km/h 平飞）；'
        f'爬升额外按出发瞬时 × {float(mf["climb_extra_km"]):g} km，'
        f'降落节省按返回瞬时 × {float(mf["descent_save_km"]):g} km；'
        '布雷盖终点 = 空重 +（冗余 − 降落节省），可用油 = 内油 − 该值 − 爬升额外；'
        '超音速点仍按亚音速油耗入账。'
    )


def run_estimate_efficiency_from_params(params: dict[str, Any]) -> dict[str, Any]:
    """由 L/D、空战重量与可用军推估算负载比、总效率与 TSFC。

    若提供待估机几何，则在给定高度/马赫数下用统一模型重算 L/D；
    也可直接传入 ld，跳过升阻比估算。
    """
    params = ensure_default_anchors(params)
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
        ld_info = run_predict_ld_from_params({
            'target': target_raw,
            'n_missiles': params.get('n_missiles', N_MISSILES_DEFAULT),
        })
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

    install_mult = parse_tsfc_install_mult(params.get('tsfc_install_mult'))
    if eff.eta_o > 0 and eff.V0 > 0:
        payload.update(tsfc_from_eta_o(eff.V0, eff.eta_o, install_mult=install_mult))
        payload['eta_o'] = eta_o_after_install(eff.eta_o, install_mult)
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
    """取待估机几何，并返回统一模型 (Cf0, k_e)。挂弹数默认跟 n_missiles。"""
    raw = _derived_target_from_params(params)
    if raw.get('n_stores') in (None, ''):
        raw['n_stores'] = float(params.get('n_missiles', N_MISSILES_DEFAULT))
    target = aircraft_from_dict(raw)
    cf0, k_e = model_coefficients()
    return target, cf0, k_e


def _optional_ab_context(ctx: CruiseContext, params: dict[str, Any]) -> CruiseContext | None:
    """若请求带了海平面加力，构造加力搜索上下文（100% 推力，与极速同一包线）。"""
    try:
        tsl_n = parse_max_sea_level_thrust_n(params)
    except (TypeError, ValueError):
        return None
    if tsl_n <= 0:
        return None
    return replace(ctx, tsl_N=tsl_n, thrust_margin=MAX_SPEED_THRUST_MARGIN)


def _attach_max_ld_to_point(
    row: dict[str, Any],
    ctx: CruiseContext,
    mach: float | None,
    ab_ctx: CruiseContext | None,
    alt_min_m: float,
    alt_max_m: float,
    coarse_m: float,
    refine_m: float,
) -> dict[str, Any]:
    """给巡航点补上可飞高度中的最大升阻比（军推优先，不足则加力）。

    加力可飞与极速同一包线：全部加力、高度可到海平面。
    """
    if mach is None or mach <= 0:
        row.update(max_ld_fields(None))
        return row
    try:
        point = search_max_ld_altitude(
            ctx, mach, alt_min_m, alt_max_m, coarse_m, refine_m, ab_ctx=ab_ctx,
            ab_alt_min_m=MAX_SPEED_ALT_MIN_M,
            ab_alt_max_m=MAX_SPEED_ALT_MAX_M,
        )
    except ValueError:
        point = None
    row.update(max_ld_fields(point))
    return row


def _radius_fail_reason(warning: str) -> str:
    """不可行巡航点的中文原因，供三端直接展示。"""
    if warning == 'insufficient_mission_fuel':
        return '任务油量不足以覆盖冗余/爬升'
    if warning == 'subsonic_burn_unavailable':
        return '无法得到亚音速油耗'
    if warning == 'tsfc_unavailable':
        return '该点无法得到 TSFC'
    return '无满足 92% 推力裕度的高度'


def _infeasible_point(
    point_id: str,
    label: str,
    mach: float | None,
    warning: str = 'no_feasible_altitude',
) -> dict[str, Any]:
    """给定马赫找不到可用巡航点，或任务油量不足以给出半径。"""
    return {
        'id': point_id,
        'label': label,
        'mach': mach,
        'feasible': False,
        'warning': warning,
        'fail_reason': _radius_fail_reason(warning),
        'radius_m': None,
        'radius_km': None,
        'fuel_kg_per_km': None,
    }


def _failed_radius_point(
    point_id: str,
    label: str,
    scored: Any,
    warning: str,
) -> dict[str, Any]:
    """高度搜索成功但无法给出布雷盖半径时，保留气动点并标失败原因。"""
    row = scored_to_dict(scored)
    row['id'] = point_id
    row['label'] = label
    row['feasible'] = False
    row['warning'] = warning
    row['fail_reason'] = _radius_fail_reason(warning)
    row['radius_m'] = None
    row['radius_km'] = None
    row['fuel_kg_per_km'] = None
    return row


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
        row['fail_reason'] = _radius_fail_reason(row['warning'])
        row['radius_m'] = None
        row['radius_km'] = None
        row['fuel_kg_per_km'] = None
        return row
    try:
        radius = combat_radius_m(
            scored.v0, scored.tsfc_kg_n_s, scored.ld, mass_initial_kg, mass_final_kg,
        )
    except ValueError:
        row['feasible'] = False
        row['warning'] = 'insufficient_mission_fuel'
        row['fail_reason'] = _radius_fail_reason(row['warning'])
        row['radius_m'] = None
        row['radius_km'] = None
        row['fuel_kg_per_km'] = None
        return row
    row['radius_m'] = radius
    row['radius_km'] = radius / 1000.0
    row['fuel_kg_per_km'] = average_fuel_kg_per_km(fuel_kg, radius)
    _clear_mixed_radius_fields(row)
    return row


def _clear_mixed_radius_fields(row: dict[str, Any]) -> None:
    """占位混合作战半径字段，供后续统一填充。"""
    row.setdefault('mixed_radius_m', None)
    row.setdefault('mixed_radius_km', None)
    row.setdefault('mixed_fuel_kg_per_km', None)


def _attach_mixed_radius(
    points: list[dict[str, Any]],
    mass_initial_kg: float,
    mass_final_kg: float,
    fuel_kg: float,
) -> None:
    """超音速巡航点补上去程该马赫、返程 Ma 0.8 的混合作战半径。"""
    subsonic = next(
        (
            p for p in points
            if p.get('id') == 'mach_0_8' and p.get('feasible')
            and p.get('tsfc_kg_n_s') and p.get('V0') and p.get('ld')
        ),
        None,
    )
    for row in points:
        _clear_mixed_radius_fields(row)
        if not row.get('feasible'):
            continue
        mach = row.get('mach')
        if mach is None or float(mach) <= SUPERSONIC_MACH:
            continue
        if subsonic is None:
            row['mixed_warning'] = 'no_subsonic_return'
            continue
        try:
            radius = mixed_combat_radius_m(
                float(row['V0']),
                float(row['tsfc_kg_n_s']),
                float(row['ld']),
                float(subsonic['V0']),
                float(subsonic['tsfc_kg_n_s']),
                float(subsonic['ld']),
                mass_initial_kg,
                mass_final_kg,
            )
        except (ValueError, TypeError, KeyError):
            row['mixed_warning'] = 'mixed_infeasible'
            continue
        if radius <= 0:
            row['mixed_warning'] = 'mixed_infeasible'
            continue
        row['mixed_radius_m'] = radius
        row['mixed_radius_km'] = radius / 1000.0
        if fuel_kg > 0 and radius > 0:
            row['mixed_fuel_kg_per_km'] = average_fuel_kg_per_km(fuel_kg, radius)


def run_estimate_radius_from_params(params: dict[str, Any]) -> dict[str, Any]:
    """串联升阻比、军推与效率，搜索最佳巡航高度并估算作战半径。

    固定评估 Ma 0.8 / 1.0 / 1.2 / 1.35 / 1.5 / 1.75 / 2.0，表尾再给实用最大巡航与最大巡航。
    若 Ma 1.2 以上作战半径最大的马赫与实用最大巡航（高度峰值）不同，插入「最大半径超音速巡航速度」。
    超音速点额外给出混合作战半径（去程该马赫、返程 Ma 0.8）。
    巡航 L/D 仍用一半内油的空战重量。
    先按出发总重与返回总重（干重+冗余）算亚音速瞬时油耗；
    冗余为弹射/滑跃舰载 45 min，陆基与垂起/倾转 30 min，850 km/h 平飞。
    出发瞬时 × 120 km 为爬升额外，返回瞬时 × 87.5 km 为降落节省。
    布雷盖终点 = 空重 +（冗余 − 降落节省），可用油 = 内油 − 该值 − 爬升额外。
    超音速点仍用同一套亚音速任务油量。
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
        tsfc_install_mult=parse_tsfc_install_mult(params.get('tsfc_install_mult')),
    )

    alt_min = float(params['alt_min_m']) if params.get('alt_min_m') not in (None, '') else ALT_MIN_M
    alt_max = float(params['alt_max_m']) if params.get('alt_max_m') not in (None, '') else ALT_MAX_M
    coarse_m = float(params['alt_coarse_m']) if params.get('alt_coarse_m') not in (None, '') else ALT_COARSE_M
    refine_m = float(params['alt_refine_m']) if params.get('alt_refine_m') not in (None, '') else ALT_REFINE_M
    mach_lo = float(params['mach_search_lo']) if params.get('mach_search_lo') not in (None, '') else MACH_SEARCH_LO
    mach_hi = float(params['mach_search_hi']) if params.get('mach_search_hi') not in (None, '') else MACH_SEARCH_HI
    mach_iters = _optional_int(params.get('mach_search_iters'), MACH_SEARCH_ITERS)
    ab_ctx = _optional_ab_context(ctx, params)

    carrier = _parse_carrier(params)
    type_label = _parse_type_label(params)
    mf = mission_fuel_config()
    reserve_min = reserve_min_for_mission(carrier, type_label)
    subsonic = _subsonic_scored_for_burn(ctx, alt_min, alt_max, coarse_m, refine_m)
    fuel_adj: dict[str, Any] | None = None
    if (
        subsonic is not None
        and subsonic.tsfc_kg_n_s is not None
        and subsonic.v0 > 0
        and subsonic.ld > 0
    ):
        fuel_adj = mission_fuel_budget(
            internal_fuel_kg=fuel_kg,
            takeoff_mass_kg=takeoff_mass['total_kg'],
            dry_mass_kg=dry_mass['total_kg'],
            reserve_min=reserve_min,
            cruise_kph=float(mf['reserve_cruise_kph']),
            climb_extra_km=float(mf['climb_extra_km']),
            descent_save_km=float(mf['descent_save_km']),
            v_mps=subsonic.v0,
            tsfc_kg_n_s=subsonic.tsfc_kg_n_s,
            ld=subsonic.ld,
            carrier=carrier,
        )

    def pack_point(point_id: str, label: str, mach: float) -> dict[str, Any]:
        try:
            scored = search_best_altitude(
                ctx, mach, alt_min, alt_max, coarse_m, refine_m,
            )
        except ValueError:
            row = _infeasible_point(point_id, label, mach)
        else:
            if scored is None:
                row = _infeasible_point(point_id, label, mach)
            elif fuel_adj is None:
                row = _failed_radius_point(
                    point_id, label, scored, 'subsonic_burn_unavailable',
                )
            elif (
                float(fuel_adj['usable_fuel_kg']) <= 0
                or float(fuel_adj['mass_final_kg']) <= 0
            ):
                row = _failed_radius_point(
                    point_id, label, scored, 'insufficient_mission_fuel',
                )
            else:
                row = _enrich_radius_point(
                    point_id, label, scored,
                    float(fuel_adj['mass_initial_kg']),
                    float(fuel_adj['mass_final_kg']),
                    float(fuel_adj['usable_fuel_kg']),
                )
        return _attach_max_ld_to_point(
            row, ctx, mach, ab_ctx, alt_min, alt_max, coarse_m, refine_m,
        )

    points: list[dict[str, Any]] = []
    for mach in FIXED_MACHS:
        label = f'Ma {mach:g}'
        point_id = f'mach_{str(mach).replace(".", "_")}'
        points.append(pack_point(point_id, label, mach))

    # 实用最大巡航按高度极值搜；同时在同一剖面上找 Ma 1.2 以上半径最大点
    prac_lo = max(mach_lo, PRACTICAL_MAX_CRUISE_MACH_LO)
    max_mach = None
    max_radius_mach = None
    max_radius_km = None
    if prac_lo < mach_hi:
        refine_search = min(ALT_REFINE_M, coarse_m)
        profile = scan_best_altitude_profile(
            ctx, prac_lo, mach_hi, MACH_PROFILE_STEP,
            alt_min, alt_max, coarse_m, refine_search,
        )
        found = contiguous_peak_max_mach(
            [(point.mach, point.alt_m) for point in profile],
            0.0,
            mach_hi,
        )
        if found is not None:
            max_mach = snap_mach(found, MACH_PROFILE_STEP)
        if (
            fuel_adj is not None
            and float(fuel_adj['usable_fuel_kg']) > 0
            and float(fuel_adj['mass_final_kg']) > 0
        ):
            max_radius_mach, max_radius_km = max_radius_mach_from_profile(
                profile,
                float(fuel_adj['mass_initial_kg']),
                float(fuel_adj['mass_final_kg']),
                prac_lo,
            )
    possible_mach = search_max_possible_cruise_mach(
        ctx, mach_lo, mach_hi, mach_iters, alt_min, alt_max, coarse_m,
    )
    # 最大可能巡航不得低于实用最大巡航（跨声速空洞或高度网格差）
    if max_mach is not None and (possible_mach is None or possible_mach < max_mach):
        possible_mach = max_mach
    # 高度峰值与半径最佳马赫不同时，在实用最大巡航与最大可能巡航之间插入一行
    for point_id, label, mach in cruise_limit_specs(max_mach, possible_mach, max_radius_mach):
        if mach is None:
            points.append(_attach_max_ld_to_point(
                _infeasible_point(point_id, label, None),
                ctx, None, ab_ctx, alt_min, alt_max, coarse_m, refine_m,
            ))
        else:
            points.append(pack_point(point_id, label, mach))

    mach_angle_deg = None
    m_cone = None
    phi = aircraft_mach_angle_rad(target)
    if phi is not None:
        mach_angle_deg = math.degrees(phi)
        m_cone = mach_cone_limit(phi)

    breguet_initial = (
        float(fuel_adj['mass_initial_kg']) if fuel_adj else takeoff_mass['total_kg']
    )
    breguet_final = (
        float(fuel_adj['mass_final_kg']) if fuel_adj else dry_mass['total_kg']
    )
    if (
        fuel_adj is not None
        and float(fuel_adj['usable_fuel_kg']) > 0
        and float(fuel_adj['mass_final_kg']) > 0
    ):
        _attach_mixed_radius(
            points,
            float(fuel_adj['mass_initial_kg']),
            float(fuel_adj['mass_final_kg']),
            float(fuel_adj['usable_fuel_kg']),
        )
    else:
        for row in points:
            _clear_mixed_radius_fields(row)
    return {
        'success': True,
        'name': str(params.get('name') or target.name),
        'Cf0': cf0,
        'k_e': k_e,
        'n_engines': n_engines,
        'thrust_margin': ctx.thrust_margin,
        'carrier': carrier,
        'mass_cruise_kg': cruise_mass['total_kg'],
        'mass_takeoff_kg': takeoff_mass['total_kg'],
        'mass_dry_kg': dry_mass['total_kg'],
        'mass_initial_kg': breguet_initial,
        'mass_final_kg': breguet_final,
        'fuel_kg': fuel_kg,
        'fuel_usable_kg': None if fuel_adj is None else float(fuel_adj['usable_fuel_kg']),
        'n_missiles': n_missiles,
        'length_m': target.length_m,
        'wingspan_m': target.wingspan_m,
        'fuse_width_m': target.fuse_width_m,
        'fuse_height_m': target.fuse_height_m,
        'mach_angle_deg': mach_angle_deg,
        'mach_cone_limit': m_cone,
        'max_cruise_mach': max_mach,
        'max_possible_cruise_mach': possible_mach,
        'max_radius_mach': max_radius_mach,
        'max_radius_km': max_radius_km,
        'points': points,
        'mission_fuel': fuel_adj,
        'note': _mission_fuel_note(reserve_kind_label(carrier, type_label), reserve_min, mf),
    }


def run_estimate_max_speed_from_params(params: dict[str, Any]) -> dict[str, Any]:
    """加力平飞最大速度：各马赫在可飞高度上取最大升阻比，再取真速最大点。

    使用海平面加力最大推力标定，约束为阻力 = 全部可用加力（不留巡航裕度）。
    空战重量 = 空重 + 一半内油 + 飞行员 + 挂弹；不计作战半径与任务油量。
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
        tsl_N=parse_max_sea_level_thrust_n(params),
        eta_c=float(params['eta_c']) if params.get('eta_c') not in (None, '') else ETA_C_DEFAULT,
        fan_pr_override=_optional_float(params.get('fan_pr_override', params.get('fan_pr'))),
        thrust_margin=float(params['thrust_margin']) if params.get('thrust_margin') not in (None, '') else MAX_SPEED_THRUST_MARGIN,
        tsfc_install_mult=parse_tsfc_install_mult(params.get('tsfc_install_mult')),
    )

    alt_min = float(params['alt_min_m']) if params.get('alt_min_m') not in (None, '') else MAX_SPEED_ALT_MIN_M
    alt_max = float(params['alt_max_m']) if params.get('alt_max_m') not in (None, '') else MAX_SPEED_ALT_MAX_M
    coarse_m = float(params['alt_coarse_m']) if params.get('alt_coarse_m') not in (None, '') else MAX_SPEED_ALT_COARSE_M
    refine_m = float(params['alt_refine_m']) if params.get('alt_refine_m') not in (None, '') else MAX_SPEED_ALT_REFINE_M
    mach_lo = float(params['mach_search_lo']) if params.get('mach_search_lo') not in (None, '') else MAX_SPEED_MACH_LO
    mach_hi = float(params['mach_search_hi']) if params.get('mach_search_hi') not in (None, '') else MAX_SPEED_MACH_HI
    mach_iters = _optional_int(params.get('mach_search_iters'), MAX_SPEED_MACH_ITERS)

    result = search_global_max_speed(
        ctx, alt_min, alt_max, coarse_m, refine_m, mach_lo, mach_hi, mach_iters,
    )
    if result is None:
        return {
            'success': True,
            'name': str(params.get('name') or target.name),
            'Cf0': cf0,
            'k_e': k_e,
            'n_engines': n_engines,
            'mass_kg': cruise_mass['total_kg'],
            'max_tsl_kN': parse_max_sea_level_thrust_n(params) / 1000.0,
            'thrust_margin': ctx.thrust_margin,
            'feasible': False,
            'fail_reason': '全高度包线内无法满足加力推阻平衡（阻力=推力）',
            'max_speed_mach': None,
            'max_speed_kmh': None,
            'max_speed_kts': None,
            'alt_m': None,
            'profile': [],
            'note': '加力最大速度：阻力等于全部可用加力（不留巡航裕度）；各马赫取最大升阻比后再取真速最大点；不计作战半径。',
        }

    best = result['best']
    return {
        'success': True,
        'name': str(params.get('name') or target.name),
        'Cf0': cf0,
        'k_e': k_e,
        'n_engines': n_engines,
        'mass_kg': cruise_mass['total_kg'],
        'max_tsl_kN': parse_max_sea_level_thrust_n(params) / 1000.0,
        'thrust_margin': ctx.thrust_margin,
        'feasible': True,
        'max_speed_mach': best['mach'],
        'max_speed_kmh': best['v_kmh'],
        'max_speed_kts': best['v_kts'],
        'alt_m': best['alt_m'],
        'ld': best['ld'],
        'drag_kN': best['drag_kN'],
        'thrust_avail_kN': best['thrust_avail_kN'],
        'load': best['load'],
        'profile': result['profile'],
        'note': '加力最大速度：阻力等于全部可用加力（不留巡航裕度）；各马赫取最大升阻比后再取真速最大点；不计作战半径。',
    }


def compact_max_speed(result: dict[str, Any]) -> dict[str, Any]:
    """仪表盘用的极速摘要，去掉高度剖面以控制体积。"""
    return {
        'success': bool(result.get('success', True)),
        'feasible': result.get('feasible'),
        'fail_reason': result.get('fail_reason'),
        'max_speed_mach': result.get('max_speed_mach'),
        'max_speed_kmh': result.get('max_speed_kmh'),
        'max_speed_kts': result.get('max_speed_kts'),
        'alt_m': result.get('alt_m'),
        'ld': result.get('ld'),
        'load': result.get('load'),
        'thrust_avail_kN': result.get('thrust_avail_kN'),
        'note': result.get('note'),
    }


def run_aircraft_dashboard_from_params(params: dict[str, Any]) -> dict[str, Any]:
    """机型仪表盘：最大巡航、极速、各马赫作战半径与混合作战半径。

    升阻比用统一物理模型；缺少海平面加力时极速标为不可行。
    """
    params = ensure_default_anchors(params)
    radius = run_estimate_radius_from_params(params)
    max_speed_block = {
        'success': True,
        'feasible': False,
        'fail_reason': '缺少海平面加力最大推力',
        'max_speed_mach': None,
        'max_speed_kmh': None,
        'max_speed_kts': None,
        'alt_m': None,
        'ld': None,
        'load': None,
        'thrust_avail_kN': None,
        'note': None,
    }
    try:
        max_speed_block = compact_max_speed(run_estimate_max_speed_from_params(params))
    except ValueError as exc:
        max_speed_block['fail_reason'] = str(exc)
    radius['max_speed'] = max_speed_block
    return radius


def _cruise_context_from_params(params: dict[str, Any]) -> tuple[CruiseContext, Aircraft]:
    """由请求参数标定并构造巡航搜索上下文（空战半油重量）。"""
    params = ensure_default_anchors(params)
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
        tsfc_install_mult=parse_tsfc_install_mult(params.get('tsfc_install_mult')),
    )
    return ctx, target


def run_search_best_cruise_from_params(params: dict[str, Any]) -> dict[str, Any]:
    """给定马赫，搜索 L/D×η_o 最大且满足推力裕度的巡航高度。

    无论能否军推巡航，都附带可飞高度上的最大升阻比。
    加力可飞与极速同一包线：全部加力、高度可到海平面。
    """
    mach = float(params['mach'])
    if mach <= 0:
        raise ValueError('马赫数须为正')
    ctx, target = _cruise_context_from_params(params)
    alt_min = float(params['alt_min_m']) if params.get('alt_min_m') not in (None, '') else ALT_MIN_M
    alt_max = float(params['alt_max_m']) if params.get('alt_max_m') not in (None, '') else ALT_MAX_M
    coarse_m = float(params['alt_coarse_m']) if params.get('alt_coarse_m') not in (None, '') else ALT_COARSE_M
    refine_m = float(params['alt_refine_m']) if params.get('alt_refine_m') not in (None, '') else ALT_REFINE_M
    ab_ctx = _optional_ab_context(ctx, params)
    try:
        scored = search_best_altitude(ctx, mach, alt_min, alt_max, coarse_m, refine_m)
    except ValueError:
        scored = None
    if scored is None:
        row = {
            'success': True,
            'feasible': False,
            'mach': mach,
            'name': str(params.get('name') or target.name),
            'fail_reason': _radius_fail_reason('no_feasible_altitude'),
        }
        return _attach_max_ld_to_point(
            row, ctx, mach, ab_ctx, alt_min, alt_max, coarse_m, refine_m,
        )
    row = scored_to_dict(scored)
    row['success'] = True
    row['name'] = str(params.get('name') or target.name)
    return _attach_max_ld_to_point(
        row, ctx, mach, ab_ctx, alt_min, alt_max, coarse_m, refine_m,
    )


def run_estimate_engine_cycle_from_params(params: dict[str, Any]) -> dict[str, Any]:
    """给定速度、高度与负载，只算发动机热效率、推进效率与总效率。"""
    load = float(params['load'])
    if load > 1.0 and load <= 100.0:
        load = load / 100.0
    t4_raw = params.get('t4_K', params.get('t4', params.get('T4max')))
    if t4_raw in (None, ''):
        raise ValueError('缺少涡轮前温度 t4_K')
    alt_raw = params.get('alt_m', params.get('altitude_m'))
    if alt_raw in (None, ''):
        raise ValueError('缺少高度 alt_m')
    opr = _optional_float(params.get('opr'))
    eff = compute_engine_efficiency(
        bpr=float(params['bpr']),
        mach=float(params['mach']),
        altitude_m=float(alt_raw),
        load=load,
        OPR=opr,
        FPR=_optional_float(params.get('FPR', params.get('fan_pr_override', params.get('fan_pr')))),
        T4max=float(t4_raw),
        T4idle=float(params['T4idle']) if params.get('T4idle') not in (None, '') else T4IDLE_DEFAULT,
        eps=float(params['eps']) if params.get('eps') not in (None, '') else EPS_DEFAULT,
        etan=float(params['etan']) if params.get('etan') not in (None, '') else ETAN_DEFAULT,
        acc_frac=float(params['acc_frac']) if params.get('acc_frac') not in (None, '') else ACC_FRAC_DEFAULT,
    )
    if not eff.valid:
        raise ValueError(f'效率循环无解（{eff.warning or "unknown"}）')
    payload = engine_result_to_dict(eff)
    payload['success'] = True
    payload['load'] = load
    payload['name'] = str(params.get('name') or '')
    install_mult = parse_tsfc_install_mult(params.get('tsfc_install_mult'))
    if eff.eta_o > 0 and eff.V0 > 0:
        payload.update(tsfc_from_eta_o(eff.V0, eff.eta_o, install_mult=install_mult))
        payload['eta_o'] = eta_o_after_install(eff.eta_o, install_mult)
    return payload


def main() -> None:
    """命令行入口：默认用 F-22 + F119 打印四个巡航点的作战半径。"""
    parser = argparse.ArgumentParser(description='飞机作战半径估算（布雷盖 + 任务油量）')
    parser.add_argument('--aircraft', default='F-22', help='待估机型预设 id')
    parser.add_argument('--engine', default='f119', help='发动机预设 id')
    args = parser.parse_args()

    from utils.combat_radius.combat_radius_presets import (
        get_preset_by_id,
        load_engine_presets,
        load_presets,
    )

    presets = load_presets()
    engines = load_engine_presets()
    tgt = get_preset_by_id(presets, args.aircraft)
    eng = get_preset_by_id(engines, args.engine)
    if tgt is None:
        raise SystemExit('找不到机型预设')
    if eng is None:
        raise SystemExit('找不到发动机预设')
    tsl_kn = resolve_tsl_kN(eng)
    if tsl_kn is None:
        raise SystemExit(f'发动机 {args.engine} 未填写海平面军推 tsl_kN')

    params = {
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
        'tsl_kN': tsl_kn,
        'tsfc_install_mult': eng.get('tsfc_install_mult', 1.0),
        'name': f'{tgt["name"]} / {eng["name"]}',
    }
    result = run_estimate_radius_from_params(params)
    print(f'{result["name"]}')
    if result['mach_angle_deg'] is not None:
        max_m = result['max_cruise_mach']
        max_txt = f'{max_m:.3f}' if max_m is not None else '—'
        possible_m = result.get('max_possible_cruise_mach')
        possible_txt = f'{possible_m:.3f}' if possible_m is not None else '—'
        print(
            f'马赫角 {result["mach_angle_deg"]:.1f}° · '
            f'锥限 Ma {result["mach_cone_limit"]:.2f} · '
            f'实用最大巡航 Ma {max_txt} · 最大巡航 Ma {possible_txt}'
        )
    print(
        f'{"速度/马赫":<22} {"高度km":>8} {"L/D":>7} {"η_o%":>7} '
        f'{"TSFC":>8} {"军推kN":>8} {"负载%":>7} {"半径km":>8} {"kg/km":>7}'
    )
    for p in result['points']:
        speed = format_cruise_speed_label(p)
        if not p.get('feasible'):
            warn = p.get('warning') or 'no_feasible_altitude'
            reason = p.get('fail_reason') or _radius_fail_reason(warn)
            print(f'{speed:<22}  （{reason}）')
            continue
        print(
            f'{speed:<22} {p["alt_m"]/1000:>8.1f} '
            f'{p["ld"]:>7.2f} {100*p["eta_o"]:>7.1f} {p["tsfc_mg_n_s"]:>8.2f} '
            f'{p["thrust_avail_kN"]:>8.1f} {100*p["load"]:>7.1f} '
            f'{p["radius_km"]:>8.0f} {p["fuel_kg_per_km"]:>7.2f}'
        )
    print(result['note'])


if __name__ == '__main__':
    main()

