"""加力最大速度搜索：各马赫在可飞高度上取最大升阻比，再取真速最大点。

约束：平飞阻力 ≤ 该高度全部加力可用推力（默认 100%，不留巡航裕度）。
每个马赫只在能飞的高度里选升阻比最大的点（阻力最小），再比较真速。
推力由海平面加力标定经理想循环外推；空战重量与作战半径巡航一致。
"""
from __future__ import annotations

import math
from typing import Any

from utils.combat_radius.cruise_search import (
    CruiseContext,
    CruiseForces,
    altitude_grid,
    evaluate_cruise_forces,
    search_max_ld_altitude,
)
from utils.combat_radius.military_thrust import GAMMA, R, isa

ALT_MIN_M = 0.0
ALT_MAX_M = 20000.0
ALT_COARSE_M = 1000.0
ALT_REFINE_M = 200.0
MACH_SEARCH_LO = 0.30
MACH_SEARCH_HI = 3.00
MACH_SEARCH_ITERS = 16
MACH_COARSE = 0.10
MACH_REFINE = 0.02
KTS_PER_MPS = 1.94384
# 加力极速是推阻拉平，不留军推巡航用的 8% 裕度
MAX_SPEED_THRUST_MARGIN = 1.0


def true_airspeed_mps(mach: float, alt_m: float) -> float:
    """给定高度与马赫数，返回真速 m/s。"""
    if mach <= 0:
        raise ValueError('马赫数须为正')
    if alt_m < 0:
        raise ValueError('高度不能为负')
    t0, _ = isa(alt_m)
    a0 = math.sqrt(GAMMA * R * t0)
    return mach * a0


def _point_feasible(ctx: CruiseContext, mach: float, alt_m: float) -> bool:
    """该高度/马赫是否满足加力推阻平衡；推力模型无解视为不可行。"""
    try:
        return evaluate_cruise_forces(ctx, mach, alt_m).feasible
    except ValueError:
        return False


def _find_lowest_feasible_mach(
    ctx: CruiseContext,
    alt_m: float,
    mach_lo: float,
    mach_hi: float,
    step: float = 0.05,
) -> float | None:
    """从低马赫向上扫描，找到该高度首个可行马赫。"""
    mach = mach_lo
    while mach <= mach_hi + 1e-9:
        if _point_feasible(ctx, mach, alt_m):
            return mach
        mach += step
    return None


def search_max_mach_at_altitude(
    ctx: CruiseContext,
    alt_m: float,
    mach_lo: float = MACH_SEARCH_LO,
    mach_hi: float = MACH_SEARCH_HI,
    iters: int = MACH_SEARCH_ITERS,
) -> float | None:
    """在固定高度上二分搜索满足加力推阻平衡的最大马赫数。"""
    if mach_lo <= 0 or mach_hi <= mach_lo:
        raise ValueError('马赫搜索区间非法')
    if iters < 1:
        raise ValueError('马赫搜索迭代次数须为正')
    lo = _find_lowest_feasible_mach(ctx, alt_m, mach_lo, mach_hi)
    if lo is None:
        return None
    hi = mach_hi
    if _point_feasible(ctx, hi, alt_m):
        return hi
    for _ in range(iters):
        mid = (lo + hi) / 2.0
        if _point_feasible(ctx, mid, alt_m):
            lo = mid
        else:
            hi = mid
    return lo


def _pack_altitude_point(
    ctx: CruiseContext,
    alt_m: float,
    mach: float,
    forces: CruiseForces,
) -> dict[str, Any]:
    """单高度最大马赫点 → 可序列化字典。"""
    v_mps = true_airspeed_mps(mach, alt_m)
    return {
        'alt_m': alt_m,
        'mach': mach,
        'v_mps': v_mps,
        'v_kmh': v_mps * 3.6,
        'v_kts': v_mps * KTS_PER_MPS,
        'ld': forces.ld,
        'drag_N': forces.drag_N,
        'drag_kN': forces.drag_N / 1000.0,
        'thrust_avail_N': forces.thrust_avail_N,
        'thrust_avail_kN': forces.thrust_avail_N / 1000.0,
        'load_raw': forces.load_raw,
        'load': forces.load_raw,
        'feasible': forces.feasible,
    }


def _max_ld_row_at_mach(
    ctx: CruiseContext,
    mach: float,
    alt_min_m: float,
    alt_max_m: float,
    coarse_m: float,
    refine_m: float,
) -> dict[str, Any] | None:
    """给定马赫，在加力可飞高度上取最大升阻比，打包为极速剖面点。"""
    found = search_max_ld_altitude(
        ctx, mach, alt_min_m, alt_max_m, coarse_m, refine_m,
        primary_mode='afterburner',
    )
    if found is None:
        return None
    return _pack_altitude_point(ctx, found.forces.alt_m, mach, found.forces)


def search_global_max_speed(
    ctx: CruiseContext,
    alt_min_m: float = ALT_MIN_M,
    alt_max_m: float = ALT_MAX_M,
    coarse_m: float = ALT_COARSE_M,
    refine_m: float = ALT_REFINE_M,
    mach_lo: float = MACH_SEARCH_LO,
    mach_hi: float = MACH_SEARCH_HI,
    mach_iters: int = MACH_SEARCH_ITERS,
    mach_coarse: float = MACH_COARSE,
    mach_refine: float = MACH_REFINE,
) -> dict[str, Any] | None:
    """扫描马赫网格：各马赫取可飞高度上的最大升阻比，再取真速最大点。"""
    if mach_coarse <= 0 or mach_refine <= 0:
        raise ValueError('马赫步长须为正')
    if mach_lo <= 0 or mach_hi < mach_lo:
        raise ValueError('马赫搜索区间非法')
    # mach_iters 保留签名兼容；现按最大升阻比扫马赫，不再按高度二分
    _ = mach_iters
    best: dict[str, Any] | None = None
    profile: list[dict[str, Any]] = []

    for mach in altitude_grid(mach_lo, mach_hi, mach_coarse):
        row = _max_ld_row_at_mach(ctx, mach, alt_min_m, alt_max_m, coarse_m, refine_m)
        if row is None:
            continue
        profile.append(row)
        if best is None or row['v_mps'] > best['v_mps']:
            best = row

    if best is None:
        return None

    lo = max(mach_lo, best['mach'] - mach_coarse)
    hi = min(mach_hi, best['mach'] + mach_coarse)
    for mach in altitude_grid(lo, hi, mach_refine):
        if any(abs(p['mach'] - mach) < 1e-9 for p in profile):
            continue
        row = _max_ld_row_at_mach(ctx, mach, alt_min_m, alt_max_m, coarse_m, refine_m)
        if row is None:
            continue
        profile.append(row)
        if row['v_mps'] > best['v_mps']:
            best = row

    profile.sort(key=lambda r: r['mach'])
    return {
        'best': best,
        'profile': profile,
        'thrust_margin': ctx.thrust_margin,
    }
