"""涡桨巡航续航：按最小燃油流量（单位时间）速度估算待战时间。"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from utils.combat_radius.cruise_search import (
    CruiseContext,
    CruiseScored,
    altitude_grid,
    evaluate_cruise_forces,
    score_cruise_point,
    scored_to_dict,
)
from utils.combat_radius.breguet import landing_reserve_fuel_kg, reserve_loiter_km
from utils.combat_radius.combat_radius_config import (
    mission_fuel_config,
    turboprop_endurance_config,
)
from utils.combat_radius.cruise_load import combat_mass_breakdown, payload_mass_from_params
from utils.combat_radius.propulsion import (
    TURBOPROP_ALT_MAX_M,
    TURBOPROP_ALT_MIN_M,
    TURBOPROP_MACH_SEARCH_HI,
    TURBOPROP_MACH_SEARCH_LO,
)

KTS_PER_MPS = 1.94384
ENDURANCE_MACH_STEP = 0.02
ENDURANCE_MACH_REFINE = 0.005


@dataclass
class EnduranceSearchResult:
    """最小油耗流量巡航点与续航时间。"""

    scored: CruiseScored
    fuel_flow_kg_s: float
    fuel_flow_raw_kg_s: float
    loiter_fuel_kg: float
    endurance_h: float
    internal_fuel_kg: float
    reserve_fuel_kg: float
    reserve_min: float
    scenario: str


def fuel_flow_kg_s_from_scored(scored: CruiseScored) -> float | None:
    """平飞瞬时燃油流量 ṁ = TSFC × 阻力（推力平衡时 T=D）。"""
    if scored.tsfc_kg_n_s is None or scored.tsfc_kg_n_s <= 0:
        return None
    if scored.drag_N <= 0:
        return None
    return scored.tsfc_kg_n_s * scored.drag_N


def _mach_grid(lo: float, hi: float, step: float) -> list[float]:
    if step <= 0:
        raise ValueError('马赫步长须为正')
    if hi < lo:
        raise ValueError('马赫上界不能低于下界')
    n = int(round((hi - lo) / step))
    grid = [lo + i * step for i in range(n + 1)]
    if grid[-1] < hi - 1e-9:
        grid.append(hi)
    return grid


def search_min_fuel_flow_cruise(
    ctx: CruiseContext,
    alt_min_m: float = TURBOPROP_ALT_MIN_M,
    alt_max_m: float = TURBOPROP_ALT_MAX_M,
    mach_lo: float = TURBOPROP_MACH_SEARCH_LO,
    mach_hi: float = TURBOPROP_MACH_SEARCH_HI,
    mach_step: float = ENDURANCE_MACH_STEP,
    alt_step_m: float = 500.0,
) -> tuple[CruiseScored, float] | None:
    """在可行包线内搜索使 ṁ=TSFC·D 最小的 (马赫, 高度)。"""
    best_scored: CruiseScored | None = None
    best_flow: float | None = None
    for mach in _mach_grid(mach_lo, mach_hi, mach_step):
        for alt in altitude_grid(alt_min_m, alt_max_m, alt_step_m):
            forces = evaluate_cruise_forces(ctx, mach, alt)
            if not forces.feasible:
                continue
            scored = score_cruise_point(ctx, forces)
            flow = fuel_flow_kg_s_from_scored(scored)
            if flow is None or flow <= 0:
                continue
            if best_flow is None or flow < best_flow:
                best_flow = flow
                best_scored = scored
    if best_scored is None or best_flow is None:
        return None
    # 马赫细化
    lo_m = max(mach_lo, best_scored.mach - mach_step)
    hi_m = min(mach_hi, best_scored.mach + mach_step)
    for mach in _mach_grid(lo_m, hi_m, ENDURANCE_MACH_REFINE):
        lo_a = max(alt_min_m, best_scored.alt_m - alt_step_m)
        hi_a = min(alt_max_m, best_scored.alt_m + alt_step_m)
        for alt in altitude_grid(lo_a, hi_a, 200.0):
            forces = evaluate_cruise_forces(ctx, mach, alt)
            if not forces.feasible:
                continue
            scored = score_cruise_point(ctx, forces)
            flow = fuel_flow_kg_s_from_scored(scored)
            if flow is None or flow <= 0:
                continue
            if flow < best_flow:
                best_flow = flow
                best_scored = scored
    return best_scored, best_flow


def endurance_dry_mass_kg(params: dict[str, Any]) -> float:
    """待战续航用干重：空重 + 机组 + 任务载荷，不含燃油。"""
    target = params.get('target') if isinstance(params.get('target'), dict) else {}
    return combat_mass_breakdown(
        empty_kg=float(params['empty_kg']),
        internal_fuel_kg=float(params['internal_fuel_kg']),
        n_pilots=float(params.get('n_pilots', target.get('n_pilots', 1))),
        missile_mass_kg=float(params.get('missile_mass_kg', 0.0)),
        n_missiles=float(params.get('n_missiles', 0.0)),
        fuel_fraction=0.0,
        payload_mass_kg=payload_mass_from_params(params),
    )['total_kg']


def endurance_internal_fuel_kg(params: dict[str, Any], *, land_scenario: bool) -> float:
    """待战可用内油：舰载用库内油；陆基可取 MTOW 允许的最大燃油（公开 8 h 口径）。"""
    internal = float(params['internal_fuel_kg'])
    if not land_scenario:
        return internal
    te_cfg = turboprop_endurance_config()
    if not te_cfg.get('land_use_mtow_fuel', True):
        return internal
    mtow = params.get('mtow_kg')
    if mtow in (None, ''):
        return internal
    max_fuel = max(0.0, float(mtow) - endurance_dry_mass_kg(params))
    if max_fuel <= internal:
        return internal
    return max_fuel


def endurance_loiter_flow_mult(params: dict[str, Any]) -> float:
    """留航油耗校准乘数（机型字段优先，否则按 aircraft_role）。"""
    raw = params.get('endurance_loiter_flow_mult')
    if raw not in (None, ''):
        mult = float(raw)
        if mult <= 0:
            raise ValueError('endurance_loiter_flow_mult 须为正')
        return mult
    target = params.get('target') if isinstance(params.get('target'), dict) else {}
    role = str(params.get('aircraft_role') or target.get('aircraft_role') or '').strip().lower()
    te_cfg = turboprop_endurance_config()
    by_role = te_cfg.get('loiter_flow_mult_by_role') or {}
    if role and role in by_role:
        return float(by_role[role])
    return float(te_cfg.get('default_loiter_flow_mult', 1.0))


def loiter_landing_reserve_fuel_kg(
    dry_mass_kg: float,
    reserve_min: float,
    scored: CruiseScored,
) -> float:
    """按留航点速度与 TSFC/L/D 闭合降落余油（不用作战半径 850 km/h 冗余）。"""
    if reserve_min <= 0:
        return 0.0
    if scored.tsfc_kg_n_s is None or scored.tsfc_kg_n_s <= 0:
        raise ValueError('留航点缺少 TSFC')
    if scored.v0 <= 0 or scored.ld <= 0:
        raise ValueError('留航点速度或升阻比无效')
    loiter_km = reserve_loiter_km(reserve_min, scored.v0 * 3.6)
    return landing_reserve_fuel_kg(
        dry_mass_kg, loiter_km, scored.v0, scored.tsfc_kg_n_s, scored.ld,
    )


def loiter_burnable_fuel_kg(internal_fuel_kg: float, reserve_fuel_kg: float) -> float:
    """待战可消耗燃油：内油扣除须保留的降落余油（不计爬升额外）。"""
    if internal_fuel_kg < 0:
        raise ValueError('内油不能为负')
    if reserve_fuel_kg < 0:
        raise ValueError('余油不能为负')
    return max(internal_fuel_kg - reserve_fuel_kg, 0.0)


def endurance_hours(loiter_fuel_kg: float, fuel_flow_kg_s: float) -> float:
    """由可消耗油量与瞬时流量求续航小时数。"""
    if loiter_fuel_kg <= 0 or fuel_flow_kg_s <= 0:
        return 0.0
    return loiter_fuel_kg / fuel_flow_kg_s / 3600.0


def compute_turboprop_endurance(
    ctx: CruiseContext,
    internal_fuel_kg: float,
    reserve_fuel_kg: float,
    alt_min_m: float = TURBOPROP_ALT_MIN_M,
    alt_max_m: float = TURBOPROP_ALT_MAX_M,
    mach_lo: float = TURBOPROP_MACH_SEARCH_LO,
    mach_hi: float = TURBOPROP_MACH_SEARCH_HI,
    *,
    flow_mult: float = 1.0,
    reserve_min: float = 0.0,
    scenario: str = 'custom',
) -> EnduranceSearchResult | None:
    """搜索最小 ṁ 工况并估算待战续航（小时）。"""
    found = search_min_fuel_flow_cruise(
        ctx, alt_min_m, alt_max_m, mach_lo, mach_hi,
    )
    if found is None:
        return None
    scored, raw_flow = found
    mult = float(flow_mult)
    if mult <= 0:
        raise ValueError('flow_mult 须为正')
    eff_flow = raw_flow * mult
    loiter = loiter_burnable_fuel_kg(internal_fuel_kg, reserve_fuel_kg)
    hours = endurance_hours(loiter, eff_flow)
    return EnduranceSearchResult(
        scored=scored,
        fuel_flow_kg_s=eff_flow,
        fuel_flow_raw_kg_s=raw_flow,
        loiter_fuel_kg=loiter,
        endurance_h=hours,
        internal_fuel_kg=internal_fuel_kg,
        reserve_fuel_kg=reserve_fuel_kg,
        reserve_min=reserve_min,
        scenario=scenario,
    )


def compute_turboprop_endurance_scenario(
    ctx: CruiseContext,
    params: dict[str, Any],
    *,
    land_scenario: bool,
    reserve_min: float,
    alt_min_m: float,
    alt_max_m: float,
    mach_lo: float,
    mach_hi: float,
) -> EnduranceSearchResult | None:
    """单套待战口径：留航速度闭合余油 + 可选陆基 MTOW 满油 + 角色校准乘数。"""
    scenario = 'land' if land_scenario else 'carrier'
    dry = endurance_dry_mass_kg(params)
    internal = endurance_internal_fuel_kg(params, land_scenario=land_scenario)
    found = search_min_fuel_flow_cruise(ctx, alt_min_m, alt_max_m, mach_lo, mach_hi)
    if found is None:
        return None
    scored, raw_flow = found
    reserve_kg = loiter_landing_reserve_fuel_kg(dry, reserve_min, scored)
    mult = endurance_loiter_flow_mult(params)
    eff_flow = raw_flow * mult
    loiter = loiter_burnable_fuel_kg(internal, reserve_kg)
    return EnduranceSearchResult(
        scored=scored,
        fuel_flow_kg_s=eff_flow,
        fuel_flow_raw_kg_s=raw_flow,
        loiter_fuel_kg=loiter,
        endurance_h=endurance_hours(loiter, eff_flow),
        internal_fuel_kg=internal,
        reserve_fuel_kg=reserve_kg,
        reserve_min=float(reserve_min),
        scenario=scenario,
    )


def build_turboprop_endurance_pack(
    params: dict[str, Any],
    ctx: CruiseContext,
    envelope: dict[str, Any],
) -> dict[str, Any]:
    """舰载/陆基双口径待战续航；主显示字段与 preset.carrier 一致。"""
    mf = mission_fuel_config()
    alt_min = float(envelope['alt_min_m'])
    alt_max = float(envelope['alt_max_m'])
    mach_lo = float(envelope['mach_search_lo'])
    mach_hi = float(envelope['mach_search_hi'])
    variants: dict[str, Any] = {}
    for scenario, land, reserve_min in (
        ('carrier', False, float(mf['carrier_reserve_min'])),
        ('land', True, float(mf['land_reserve_min'])),
    ):
        result = compute_turboprop_endurance_scenario(
            ctx,
            params,
            land_scenario=land,
            reserve_min=reserve_min,
            alt_min_m=alt_min,
            alt_max_m=alt_max,
            mach_lo=mach_lo,
            mach_hi=mach_hi,
        )
        variants[scenario] = endurance_block_to_dict(result, scenario=scenario)
    primary_key = 'carrier' if params.get('carrier') else 'land'
    primary = dict(variants.get(primary_key) or endurance_block_to_dict(None))
    primary['variants'] = variants
    primary['scenario'] = primary_key
    return primary


def endurance_block_to_dict(
    result: EnduranceSearchResult | None,
    *,
    scenario: str | None = None,
) -> dict[str, Any]:
    """续航摘要 → JSON。"""
    if result is None:
        return {
            'success': True,
            'feasible': False,
            'fail_reason': '包线内无满足推力裕度的最小流量工况',
        }
    s = result.scored
    v0 = s.v0
    scen = scenario or result.scenario
    if scen == 'land':
        title = '陆基待战续航（30 min 余油·MTOW 满油）'
        note = (
            '陆基口径：余油按留航速度闭合；燃油取 MTOW 允许的最大内油；'
            '油耗经 awacs 角色校准，对齐公开约 8 h 量级。'
        )
    elif scen == 'carrier':
        title = '舰载待战续航（45 min 余油）'
        note = (
            '舰载口径：余油按留航速度闭合（非 850 km/h 作战冗余）；'
            '在 TSFC×阻力 最小工况平飞；油耗经 awacs 校准，对齐公开约 6 h。'
        )
    else:
        title = '最大续航（最小流量速度）'
        note = (
            '待战续航：内油扣除降落余油，在使 TSFC×阻力 最小的马赫/高度下平飞；'
            '与表内作战半径（单位航程油耗最优）不同。'
        )
    row = scored_to_dict(s)
    row.update({
        'success': True,
        'feasible': True,
        'scenario': scen,
        'label': title,
        'fuel_flow_kg_s': result.fuel_flow_kg_s,
        'fuel_flow_kg_h': result.fuel_flow_kg_s * 3600.0,
        'fuel_flow_raw_kg_h': result.fuel_flow_raw_kg_s * 3600.0,
        'internal_fuel_kg': result.internal_fuel_kg,
        'reserve_fuel_kg': result.reserve_fuel_kg,
        'reserve_min': result.reserve_min,
        'loiter_fuel_kg': result.loiter_fuel_kg,
        'endurance_h': result.endurance_h,
        'endurance_min': result.endurance_h * 60.0,
        'speed_kmh': v0 * 3.6 if v0 > 0 else None,
        'speed_kts': v0 * KTS_PER_MPS if v0 > 0 else None,
        'note': note,
    })
    return row
