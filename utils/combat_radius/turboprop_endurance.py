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
    loiter_fuel_kg: float
    endurance_h: float


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
) -> EnduranceSearchResult | None:
    """搜索最小 ṁ 工况并估算待战续航（小时）。"""
    found = search_min_fuel_flow_cruise(
        ctx, alt_min_m, alt_max_m, mach_lo, mach_hi,
    )
    if found is None:
        return None
    scored, flow = found
    loiter = loiter_burnable_fuel_kg(internal_fuel_kg, reserve_fuel_kg)
    hours = endurance_hours(loiter, flow)
    return EnduranceSearchResult(
        scored=scored,
        fuel_flow_kg_s=flow,
        loiter_fuel_kg=loiter,
        endurance_h=hours,
    )


def endurance_block_to_dict(result: EnduranceSearchResult | None) -> dict[str, Any]:
    """续航摘要 → JSON。"""
    if result is None:
        return {
            'success': True,
            'feasible': False,
            'fail_reason': '包线内无满足推力裕度的最小流量工况',
        }
    s = result.scored
    v0 = s.v0
    row = scored_to_dict(s)
    row.update({
        'success': True,
        'feasible': True,
        'label': '最大续航（最小流量速度）',
        'fuel_flow_kg_s': result.fuel_flow_kg_s,
        'fuel_flow_kg_h': result.fuel_flow_kg_s * 3600.0,
        'loiter_fuel_kg': result.loiter_fuel_kg,
        'endurance_h': result.endurance_h,
        'endurance_min': result.endurance_h * 60.0,
        'speed_kmh': v0 * 3.6 if v0 > 0 else None,
        'speed_kts': v0 * KTS_PER_MPS if v0 > 0 else None,
        'note': (
            '待战续航：内油扣除降落余油，在使 TSFC×阻力 最小的马赫/高度下平飞；'
            '与表内作战半径（单位航程油耗最优）不同。'
        ),
    })
    return row
