"""给定马赫数搜索最佳巡航高度，并估算最大军推巡航马赫。

高度搜索范围限制在 11–20 km：与升阻比大气（11–20 km 等温层）
和效率模型 ISA 上限取交集。可行性约束为
阻力 ≤ 该点最大可用军推 × 推力裕度（默认 92%）。
目标函数为升阻比 × 总效率：低马赫时爬高会使负载过大、η_o 下降，
且大迎角附加阻力会压低 L/D，二者合起来把最佳高度压在标定巡航附近；
跨声速鼓包避免 Ma 1.2 爬得过高。Ma 1.5 以前最佳高度随速度升高。
「最大巡航」取高度仍接近峰值的上限（公开超巡数字）；
若允许掉到高度下限，军推还能再快一些。
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from utils.combat_radius.cruise_load import clamp_load, cruise_drag_n, engine_load_ratio
from utils.combat_radius.engine_efficiency import (
    ACC_FRAC_DEFAULT,
    EPS_DEFAULT,
    ETAN_DEFAULT,
    T4IDLE_DEFAULT,
    compute_engine_efficiency,
    tsfc_from_eta_o,
)
from utils.combat_radius.lift_drag import Aircraft, predict_ld
from utils.combat_radius.military_thrust import ETA_C_DEFAULT, estimate_military_thrust

THRUST_MARGIN_DEFAULT = 0.92
ALT_MIN_M = 11000.0
ALT_MAX_M = 20000.0
ALT_COARSE_M = 1000.0
ALT_REFINE_M = 200.0
FIXED_MACHS = (0.8, 1.5, 1.76, 2.0)
SUPERSONIC_MACH = 1.0
MACH_SEARCH_LO = 0.50
MACH_SEARCH_HI = 2.50
MACH_SEARCH_ITERS = 14
# 相对高度峰值允许回落这么多，仍算「峰值段」最大巡航
PEAK_ALT_DROP_M = 1200.0


@dataclass
class CruiseContext:
    """一次作战半径搜索所需的机型、标定与发动机参数。"""

    target: Aircraft
    cf0: float
    k_e: float
    mass_kg: float
    n_engines: int
    bpr: float
    opr: float
    t4_K: float
    tsl_N: float
    eta_c: float = ETA_C_DEFAULT
    fan_pr_override: float | None = None
    fpr: float | None = None
    eps: float = EPS_DEFAULT
    etan: float = ETAN_DEFAULT
    acc_frac: float = ACC_FRAC_DEFAULT
    t4idle: float = T4IDLE_DEFAULT
    thrust_margin: float = THRUST_MARGIN_DEFAULT


@dataclass
class CruiseForces:
    """单点升阻、阻力与可用军推（不含效率循环）。"""

    mach: float
    alt_m: float
    ld: float
    drag_N: float
    thrust_avail_N: float
    load_raw: float
    feasible: bool
    cd_breakdown: dict[str, float]


@dataclass
class CruiseScored(CruiseForces):
    """在可行点上补全效率、TSFC 与评分。"""

    load: float = 0.0
    eta_th: float = 0.0
    eta_p: float = 0.0
    eta_o: float = 0.0
    v0: float = 0.0
    tsfc_kg_n_s: float | None = None
    tsfc_mg_n_s: float | None = None
    tsfc_lb_lbf_h: float | None = None
    score: float = 0.0
    warning: str | None = None


@dataclass
class MaxLdPoint:
    """可飞高度上的最大升阻比点（军推优先，不足则加力）。"""

    forces: CruiseForces
    thrust_mode: str  # 'military' | 'afterburner'


def altitude_grid(lo_m: float, hi_m: float, step_m: float) -> list[float]:
    """闭区间 [lo, hi] 上按步长生成高度网格（整数步，避免浮点越过上界）。"""
    if step_m <= 0:
        raise ValueError('高度步长须为正')
    if hi_m < lo_m:
        raise ValueError('高度上界不能低于下界')
    n_steps = int(round((hi_m - lo_m) / step_m))
    return [lo_m + i * step_m for i in range(n_steps + 1)]


def evaluate_cruise_forces(ctx: CruiseContext, mach: float, alt_m: float) -> CruiseForces:
    """计算给定高度/马赫下的 L/D、阻力与可用军推，并判定 92% 推力裕度。"""
    if mach <= 0:
        raise ValueError('马赫数须为正')
    ac = replace(ctx.target, mach=mach, alt_m=alt_m)
    ld, breakdown = predict_ld(ac, ctx.cf0, ctx.k_e)
    drag_n = cruise_drag_n(ctx.mass_kg, ld)
    thrust_one = estimate_military_thrust(
        bpr=ctx.bpr,
        opr=ctx.opr,
        t4_K=ctx.t4_K,
        tsl_N=ctx.tsl_N,
        alt_m=alt_m,
        mach=mach,
        eta_c=ctx.eta_c,
        fan_pr_override=ctx.fan_pr_override,
    )
    thrust_avail = thrust_one.thrust_N * ctx.n_engines
    load_raw = engine_load_ratio(drag_n, thrust_avail)
    return CruiseForces(
        mach=mach,
        alt_m=alt_m,
        ld=ld,
        drag_N=drag_n,
        thrust_avail_N=thrust_avail,
        load_raw=load_raw,
        feasible=load_raw <= ctx.thrust_margin,
        cd_breakdown=breakdown,
    )


def score_cruise_point(ctx: CruiseContext, forces: CruiseForces) -> CruiseScored:
    """在已算好的力平衡点上跑效率循环，评分 = L/D × η_o。"""
    load = clamp_load(forces.load_raw)
    eff = compute_engine_efficiency(
        bpr=ctx.bpr,
        mach=forces.mach,
        altitude_m=forces.alt_m,
        load=load,
        OPR=ctx.opr,
        FPR=ctx.fpr if ctx.fpr is not None else ctx.fan_pr_override,
        T4max=ctx.t4_K,
        T4idle=ctx.t4idle,
        eps=ctx.eps,
        etan=ctx.etan,
        acc_frac=ctx.acc_frac,
    )
    tsfc: dict[str, float] | None = None
    if eff.valid and eff.eta_o > 0 and eff.V0 > 0:
        tsfc = tsfc_from_eta_o(eff.V0, eff.eta_o)
    score = forces.ld * eff.eta_o if (eff.valid and eff.eta_o > 0) else -1.0
    warning = None if eff.valid else (eff.warning or 'cycle_infeasible')
    return CruiseScored(
        mach=forces.mach,
        alt_m=forces.alt_m,
        ld=forces.ld,
        drag_N=forces.drag_N,
        thrust_avail_N=forces.thrust_avail_N,
        load_raw=forces.load_raw,
        feasible=forces.feasible,
        cd_breakdown=forces.cd_breakdown,
        load=load,
        eta_th=eff.eta_th if eff.valid else 0.0,
        eta_p=eff.eta_p if eff.valid else 0.0,
        eta_o=eff.eta_o if eff.valid else 0.0,
        v0=eff.V0 if eff.valid else 0.0,
        tsfc_kg_n_s=None if tsfc is None else tsfc['tsfc_kg_n_s'],
        tsfc_mg_n_s=None if tsfc is None else tsfc['tsfc_mg_n_s'],
        tsfc_lb_lbf_h=None if tsfc is None else tsfc['tsfc_lb_lbf_h'],
        score=score,
        warning=warning,
    )


def cruise_point_feasible(ctx: CruiseContext, mach: float, alt_m: float) -> bool:
    """该高度/马赫是否满足推力裕度（只算力，不算效率）。"""
    return evaluate_cruise_forces(ctx, mach, alt_m).feasible


def any_feasible_altitude(
    ctx: CruiseContext,
    mach: float,
    alt_min_m: float = ALT_MIN_M,
    alt_max_m: float = ALT_MAX_M,
    step_m: float = ALT_COARSE_M,
) -> bool:
    """粗网格上是否存在满足推力裕度的高度。"""
    for alt in altitude_grid(alt_min_m, alt_max_m, step_m):
        if cruise_point_feasible(ctx, mach, alt):
            return True
    return False


def search_best_altitude(
    ctx: CruiseContext,
    mach: float,
    alt_min_m: float = ALT_MIN_M,
    alt_max_m: float = ALT_MAX_M,
    coarse_m: float = ALT_COARSE_M,
    refine_m: float = ALT_REFINE_M,
) -> CruiseScored | None:
    """在给定马赫下搜索使 L/D×η_o 最大、且阻力不超过军推裕度的高度。"""
    if mach <= 0:
        raise ValueError('马赫数须为正')
    best: CruiseScored | None = None
    for alt in altitude_grid(alt_min_m, alt_max_m, coarse_m):
        forces = evaluate_cruise_forces(ctx, mach, alt)
        if not forces.feasible:
            continue
        scored = score_cruise_point(ctx, forces)
        if scored.score > (best.score if best is not None else -1.0):
            best = scored
    if best is None:
        return None
    lo = max(alt_min_m, best.alt_m - coarse_m)
    hi = min(alt_max_m, best.alt_m + coarse_m)
    for alt in altitude_grid(lo, hi, refine_m):
        forces = evaluate_cruise_forces(ctx, mach, alt)
        if not forces.feasible:
            continue
        scored = score_cruise_point(ctx, forces)
        if scored.score > best.score:
            best = scored
    return best


def _require_mach_search_bounds(mach_lo: float, mach_hi: float, iters: int) -> None:
    """校验马赫搜索区间与迭代次数。"""
    if mach_lo <= 0 or mach_hi <= mach_lo:
        raise ValueError('马赫搜索区间非法')
    if iters < 1:
        raise ValueError('马赫搜索迭代次数须为正')


def search_floor_max_cruise_mach(
    ctx: CruiseContext,
    mach_lo: float = MACH_SEARCH_LO,
    mach_hi: float = MACH_SEARCH_HI,
    iters: int = MACH_SEARCH_ITERS,
    alt_min_m: float = ALT_MIN_M,
    alt_max_m: float = ALT_MAX_M,
    step_m: float = ALT_COARSE_M,
) -> float | None:
    """允许掉到高度下限时，仍满足 92% 推力裕度的最大马赫。

    比峰值高度段的最大巡航更快；低马赫在 11 km 可能因大迎角不可飞，
    不作为失败条件。
    """
    _require_mach_search_bounds(mach_lo, mach_hi, iters)
    if any_feasible_altitude(ctx, mach_hi, alt_min_m, alt_max_m, step_m):
        return mach_hi
    lo = None
    n_probe = max(iters, 8)
    for i in range(n_probe):
        mach = mach_lo + (mach_hi - mach_lo) * i / n_probe
        if any_feasible_altitude(ctx, mach, alt_min_m, alt_max_m, step_m):
            lo = mach
            break
    if lo is None:
        return None
    hi = mach_hi
    for _ in range(iters):
        mid = (lo + hi) / 2.0
        if any_feasible_altitude(ctx, mid, alt_min_m, alt_max_m, step_m):
            lo = mid
        else:
            hi = mid
    return lo


def search_max_cruise_mach(
    ctx: CruiseContext,
    mach_lo: float = MACH_SEARCH_LO,
    mach_hi: float = MACH_SEARCH_HI,
    iters: int = MACH_SEARCH_ITERS,
    alt_min_m: float = ALT_MIN_M,
    alt_max_m: float = ALT_MAX_M,
    step_m: float = ALT_COARSE_M,
    peak_drop_m: float = PEAK_ALT_DROP_M,
) -> float | None:
    """高度仍接近峰值时的最大军推巡航马赫。

    公开超巡（如 F-22 Ma 1.76）按「高度单调上升到峰值附近」标定；
    掉到 11 km 后的绝对上限用 search_floor_max_cruise_mach。
    """
    _require_mach_search_bounds(mach_lo, mach_hi, iters)
    if peak_drop_m < 0:
        raise ValueError('峰值高度回落容差不能为负')
    refine_m = min(ALT_REFINE_M, step_m)
    n_scan = max(iters, 8) + 1
    profile: list[CruiseScored] = []
    for i in range(n_scan):
        mach = mach_lo + (mach_hi - mach_lo) * i / (n_scan - 1)
        scored = search_best_altitude(
            ctx, mach, alt_min_m, alt_max_m, step_m, refine_m,
        )
        if scored is not None:
            profile.append(scored)
    if not profile:
        return None
    peak_alt = max(point.alt_m for point in profile)
    near = [point for point in profile if point.alt_m >= peak_alt - peak_drop_m]
    lo = max(point.mach for point in near)
    above = [point.mach for point in profile if point.mach > lo]
    hi = min(above) if above else mach_hi
    if lo >= hi:
        return lo
    for _ in range(iters):
        mid = (lo + hi) / 2.0
        scored = search_best_altitude(
            ctx, mid, alt_min_m, alt_max_m, step_m, refine_m,
        )
        if scored is not None and scored.alt_m >= peak_alt - peak_drop_m:
            lo = mid
        else:
            hi = mid
    return lo


def try_cruise_forces(ctx: CruiseContext, mach: float, alt_m: float) -> CruiseForces | None:
    """计算力平衡；推力循环无解时返回 None。"""
    try:
        return evaluate_cruise_forces(ctx, mach, alt_m)
    except ValueError:
        return None


def flyable_forces(
    ctx: CruiseContext,
    mach: float,
    alt_m: float,
    ab_ctx: CruiseContext | None = None,
    primary_mode: str = 'military',
) -> MaxLdPoint | None:
    """该点能否平飞：先看主推力（默认军推），不足再用加力。"""
    if primary_mode not in ('military', 'afterburner'):
        raise ValueError('推力模式须为 military 或 afterburner')
    primary = try_cruise_forces(ctx, mach, alt_m)
    if primary is not None and primary.feasible:
        return MaxLdPoint(forces=primary, thrust_mode=primary_mode)
    if ab_ctx is not None:
        afterburner = try_cruise_forces(ab_ctx, mach, alt_m)
        if afterburner is not None and afterburner.feasible:
            return MaxLdPoint(forces=afterburner, thrust_mode='afterburner')
    return None


def search_max_ld_altitude(
    ctx: CruiseContext,
    mach: float,
    alt_min_m: float = ALT_MIN_M,
    alt_max_m: float = ALT_MAX_M,
    coarse_m: float = ALT_COARSE_M,
    refine_m: float = ALT_REFINE_M,
    ab_ctx: CruiseContext | None = None,
    primary_mode: str = 'military',
) -> MaxLdPoint | None:
    """在给定马赫下，于可飞高度中取升阻比最大点。

    可飞 = 阻力不超过该点可用推力 × 裕度。军推不够时可用加力。
    """
    if mach <= 0:
        raise ValueError('马赫数须为正')
    best: MaxLdPoint | None = None
    for alt in altitude_grid(alt_min_m, alt_max_m, coarse_m):
        point = flyable_forces(ctx, mach, alt, ab_ctx, primary_mode)
        if point is None:
            continue
        if best is None or point.forces.ld > best.forces.ld:
            best = point
    if best is None:
        return None
    lo = max(alt_min_m, best.forces.alt_m - coarse_m)
    hi = min(alt_max_m, best.forces.alt_m + coarse_m)
    for alt in altitude_grid(lo, hi, refine_m):
        point = flyable_forces(ctx, mach, alt, ab_ctx, primary_mode)
        if point is None:
            continue
        if point.forces.ld > best.forces.ld:
            best = point
    return best


def max_ld_fields(point: MaxLdPoint | None) -> dict[str, Any]:
    """最大升阻比点 → 仪表盘/搜索用的紧凑字段。"""
    if point is None:
        return {
            'max_ld': None,
            'max_ld_alt_m': None,
            'max_ld_thrust_mode': None,
            'max_ld_thrust_avail_kN': None,
            'max_ld_load': None,
        }
    forces = point.forces
    return {
        'max_ld': forces.ld,
        'max_ld_alt_m': forces.alt_m,
        'max_ld_thrust_mode': point.thrust_mode,
        'max_ld_thrust_avail_kN': forces.thrust_avail_N / 1000.0,
        'max_ld_load': forces.load_raw,
    }


def scored_to_dict(point: CruiseScored) -> dict[str, Any]:
    """巡航评分点 → JSON 字段（不含布雷盖半径，由上层补）。"""
    return {
        'mach': point.mach,
        'alt_m': point.alt_m,
        'ld': point.ld,
        'drag_N': point.drag_N,
        'drag_kN': point.drag_N / 1000.0,
        'thrust_avail_N': point.thrust_avail_N,
        'thrust_avail_kN': point.thrust_avail_N / 1000.0,
        'load_raw': point.load_raw,
        'load': point.load,
        'feasible': point.feasible,
        'eta_th': point.eta_th,
        'eta_p': point.eta_p,
        'eta_o': point.eta_o,
        'V0': point.v0,
        'tsfc_kg_n_s': point.tsfc_kg_n_s,
        'tsfc_mg_n_s': point.tsfc_mg_n_s,
        'tsfc_lb_lbf_h': point.tsfc_lb_lbf_h,
        'score': point.score,
        'warning': point.warning,
        'CL': point.cd_breakdown.get('CL'),
        'CD0': point.cd_breakdown.get('CD0'),
        'CDi': point.cd_breakdown.get('CDi'),
        'CDw': point.cd_breakdown.get('CDw'),
        'CDa': point.cd_breakdown.get('CDa'),
    }
