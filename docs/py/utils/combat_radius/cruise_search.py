"""给定马赫数搜索最佳巡航高度，并估算最大军推巡航马赫。

高度搜索范围限制在 11–25 km：与升阻比大气（11–20 km 等温层 + 20–25 km 平流层递增层）
和效率模型 ISA 相容。可行性约束为
阻力 ≤ 该点最大可用军推 × 推力裕度（默认 92%）。
目标函数为升阻比 × 总效率：低马赫时爬高会使负载过大、η_o 下降，
且大迎角附加阻力会压低 L/D，二者合起来把最佳高度压在标定巡航附近；
跨声速鼓包在 Ma 1.0–1.2 加大阻力，最佳高度可能先掉再恢复。
「实用最大巡航」只在 Ma 1.2 以上取最佳巡航高度达到最大值时的速度
（同一峰值平台取最大马赫，已经掉高的点不算）。「最大可能巡航」是
11–25 km 内仍能军推平飞的最大马赫（从高往低搜最高可行窗口）；
跨声速鼓包会使可行性对马赫不单调，不能停在空洞前沿。
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from utils.combat_radius.cruise_load import clamp_load, cruise_drag_n, engine_load_ratio
from utils.combat_radius.engine_efficiency import (
    ACC_FRAC_DEFAULT,
    EPS_DEFAULT,
    ETAN_DEFAULT,
    FUEL_LHV_J_KG,
    T4IDLE_DEFAULT,
    TSFC_INSTALL_MULT_DEFAULT,
    compute_engine_efficiency,
    eta_o_after_install,
    tsfc_from_eta_o,
)
from utils.combat_radius.lift_drag import SUPERCRUISE_BAND_HI, Aircraft, predict_ld
from utils.combat_radius.military_thrust import ETA_C_DEFAULT, estimate_military_thrust
from utils.combat_radius.prop_engine_efficiency import (
    CRITICAL_ALT_M_DEFAULT,
    ETA_THERMAL_SL_DEFAULT,
    compute_prop_engine_efficiency,
    prop_thrust_from_power_n,
    available_shaft_power_w,
)
from utils.combat_radius.propulsion import (
    PROPULSION_TURBOFAN,
    is_turboprop_context,
    normalize_propulsion,
)
from utils.takeoff.propeller_thrust import DEFAULT_FIGURE_OF_MERIT, DEFAULT_NACELLE_BLOCKAGE_FRAC

THRUST_MARGIN_DEFAULT = 0.92
# 全加力 TSFC / 军推最大点 TSFC。公开涡扇海平面静止大约 2.5–2.8
# （如 F100 军推 0.73、加力约 2.0），有来流后推进效率更好，巡航取 2.2。
# 只用于阻力已经超过军推的点；未超过军推时仍按军推节流，不开加力。
AB_TSFC_OVER_MIL = 2.2
ALT_MIN_M = 11000.0
ALT_MAX_M = 25000.0
ALT_COARSE_M = 1000.0
ALT_REFINE_M = 200.0
FIXED_MACHS = (0.8, 1.0, 1.2, 1.35, 1.5, 1.75, 2.0, 2.15, 2.3)
SUPERSONIC_MACH = 1.0
MACH_SEARCH_LO = 0.50
# 实用最大巡航按高度极值搜索时，只看 Ma 1.2 以上（跳过跨声速鼓包前的峰值）
PRACTICAL_MAX_CRUISE_MACH_LO = 1.2
MACH_SEARCH_HI = 2.50
MACH_SEARCH_ITERS = 14
# 马赫剖面步长：实用最大巡航按 0.01 均匀网格扫高度峰值，不靠 1.76 钉子补点
MACH_PROFILE_STEP = 0.01
# 高度细化一格：用于判定「已经从峰值掉高」，不作为实用最大巡航的搜索容差
PEAK_ALT_DROP_M = ALT_REFINE_M


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
    tsfc_install_mult: float = TSFC_INSTALL_MULT_DEFAULT
    propulsion: str = PROPULSION_TURBOFAN
    shaft_power_sl_w: float = 0.0
    prop_diameter_m: float = 0.0
    prop_figure_of_merit: float = DEFAULT_FIGURE_OF_MERIT
    nacelle_blockage_frac: float = DEFAULT_NACELLE_BLOCKAGE_FRAC
    eta_thermal_sl: float = ETA_THERMAL_SL_DEFAULT
    critical_alt_m: float = CRITICAL_ALT_M_DEFAULT


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
    # 阻力超过该高度军推、必须打开加力时为 True。仅加力最佳高度使用。
    reheat: bool = False


@dataclass
class MaxLdPoint:
    """可飞高度上的最大升阻比点（军推优先，不足则加力）。"""

    forces: CruiseForces
    thrust_mode: str  # 'military' | 'afterburner'


def altitude_grid(lo_m: float, hi_m: float, step_m: float) -> list[float]:
    """闭区间 [lo, hi] 上按步长生成高度网格；上界不能被步长整除时仍补上界点。"""
    if step_m <= 0:
        raise ValueError('高度步长须为正')
    if hi_m < lo_m:
        raise ValueError('高度上界不能低于下界')
    n_steps = int(round((hi_m - lo_m) / step_m))
    grid = [lo_m + i * step_m for i in range(n_steps + 1)]
    # 步长不能整除区间时，网格不得越过上界，也不得漏掉上界本身
    while len(grid) > 1 and grid[-1] > hi_m + 1e-9:
        grid.pop()
    if grid[-1] < hi_m - 1e-9:
        grid.append(float(hi_m))
    return grid


def evaluate_cruise_forces(ctx: CruiseContext, mach: float, alt_m: float) -> CruiseForces:
    """计算给定高度/马赫下的 L/D、阻力与可用军推，并判定 92% 推力裕度。"""
    if mach <= 0:
        raise ValueError('马赫数须为正')
    ac = replace(ctx.target, mach=mach, alt_m=alt_m)
    ld, breakdown = predict_ld(ac, ctx.cf0, ctx.k_e)
    drag_n = cruise_drag_n(ctx.mass_kg, ld)
    if is_turboprop_context(ctx):
        if ctx.shaft_power_sl_w <= 0 or ctx.prop_diameter_m <= 0:
            raise ValueError('涡桨须填写海平面轴功率与桨盘直径')
        power_max = available_shaft_power_w(
            ctx.shaft_power_sl_w, alt_m, ctx.critical_alt_m,
        )
        thrust_avail = prop_thrust_from_power_n(
            power_max,
            alt_m,
            mach,
            ctx.prop_diameter_m,
            ctx.n_engines,
            ctx.prop_figure_of_merit,
            ctx.nacelle_blockage_frac,
        )
    else:
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
    tsfc: dict[str, float] | None = None
    eta_o = 0.0
    eta_th = 0.0
    eta_p = 0.0
    v0 = 0.0
    warning: str | None = None
    if is_turboprop_context(ctx):
        prop_eff = compute_prop_engine_efficiency(
            drag_n=forces.drag_N,
            mach=forces.mach,
            altitude_m=forces.alt_m,
            shaft_power_sl_w=ctx.shaft_power_sl_w,
            prop_diameter_m=ctx.prop_diameter_m,
            n_rotors=ctx.n_engines,
            figure_of_merit=ctx.prop_figure_of_merit,
            nacelle_blockage_frac=ctx.nacelle_blockage_frac,
            eta_thermal_sl=ctx.eta_thermal_sl,
            critical_alt_m=ctx.critical_alt_m,
        )
        if prop_eff.valid and prop_eff.eta_o > 0:
            eta_th = prop_eff.eta_th
            eta_p = prop_eff.eta_p
            eta_o = eta_o_after_install(prop_eff.eta_o, ctx.tsfc_install_mult)
            v0 = prop_eff.V0
            load = clamp_load(prop_eff.load)
            tsfc = tsfc_from_eta_o(
                v0, prop_eff.eta_o, install_mult=ctx.tsfc_install_mult,
            )
        else:
            warning = prop_eff.warning or 'prop_infeasible'
    else:
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
        if eff.valid and eff.eta_o > 0:
            eta_o = eta_o_after_install(eff.eta_o, ctx.tsfc_install_mult)
            v0 = eff.V0
            eta_th = eff.eta_th
            eta_p = eff.eta_p
            if v0 > 0:
                tsfc = tsfc_from_eta_o(
                    v0, eff.eta_o, install_mult=ctx.tsfc_install_mult,
                )
        warning = None if eff.valid else (eff.warning or 'cycle_infeasible')
    score = forces.ld * eta_o if eta_o > 0 else -1.0
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
        eta_th=eta_th,
        eta_p=eta_p,
        eta_o=eta_o,
        v0=v0,
        tsfc_kg_n_s=None if tsfc is None else tsfc['tsfc_kg_n_s'],
        tsfc_mg_n_s=None if tsfc is None else tsfc['tsfc_mg_n_s'],
        tsfc_lb_lbf_h=None if tsfc is None else tsfc['tsfc_lb_lbf_h'],
        score=score,
        warning=warning,
    )


def afterburner_tsfc_kg_n_s(
    tsfc_mil_max: float,
    thrust_mil_n: float,
    thrust_ab_n: float,
    drag_n: float,
) -> float:
    """阻力超过军推时的有效 TSFC（kg/(N·s)）。

    核心停在军推最大点，燃油流量随推力从军推最大线性增到全加力。
    全加力 TSFC = AB_TSFC_OVER_MIL × 军推最大 TSFC。未超过军推不能调用。
    """
    if tsfc_mil_max <= 0 or thrust_mil_n <= 0 or drag_n <= 0:
        raise ValueError('加力油耗参数须为正')
    if thrust_ab_n <= thrust_mil_n:
        raise ValueError('加力推力须大于军推')
    if drag_n <= thrust_mil_n:
        raise ValueError('阻力未超过军推，不应使用加力油耗')
    if drag_n > thrust_ab_n * (1.0 + 1e-9):
        raise ValueError('阻力超过加力推力')
    fuel_mil = tsfc_mil_max * thrust_mil_n
    fuel_full = AB_TSFC_OVER_MIL * tsfc_mil_max * thrust_ab_n
    frac = (drag_n - thrust_mil_n) / (thrust_ab_n - thrust_mil_n)
    return (fuel_mil + (fuel_full - fuel_mil) * frac) / drag_n


def _eta_o_from_tsfc(v0: float, tsfc_kg_n_s: float) -> float:
    """由已含安装乘数的 TSFC 反推对外总效率：η_o = V / (TSFC·Q)。"""
    if v0 <= 0 or tsfc_kg_n_s <= 0:
        raise ValueError('速度与 TSFC 须为正才能反推总效率')
    return v0 / (tsfc_kg_n_s * FUEL_LHV_J_KG)


def score_afterburner_point(mil_ctx: CruiseContext, ab_forces: CruiseForces) -> CruiseScored:
    """给加力可飞点评分。

    可用推力按加力上下文。阻力不超过军推时按军推节流，reheat=False，
    油耗与军推循环相同。超过军推才把差额算作加力燃油，总效率随之下跌。
    负载按阻力/加力推力，与表上的「加力 kN」一致。
    """
    if ab_forces.drag_N <= 0 or ab_forces.thrust_avail_N <= 0:
        raise ValueError('加力点的阻力与可用推力须为正')
    mil_full = replace(mil_ctx, thrust_margin=1.0)
    mil_forces = evaluate_cruise_forces(mil_full, ab_forces.mach, ab_forces.alt_m)
    t_mil = mil_forces.thrust_avail_N
    t_ab = ab_forces.thrust_avail_N
    drag = ab_forces.drag_N
    ab_load = drag / t_ab
    if drag <= t_mil:
        scored = score_cruise_point(mil_full, mil_forces)
        return replace(
            scored,
            thrust_avail_N=t_ab,
            load_raw=ab_load,
            load=clamp_load(ab_load),
            feasible=ab_forces.feasible,
            reheat=False,
        )
    core = score_cruise_point(mil_full, replace(mil_forces, load_raw=1.0, feasible=True))
    if (
        core.tsfc_kg_n_s is None
        or core.v0 <= 0
        or t_ab <= t_mil
        or not ab_forces.feasible
    ):
        return replace(
            core,
            thrust_avail_N=t_ab,
            load_raw=ab_load,
            load=clamp_load(ab_load),
            feasible=ab_forces.feasible,
            ld=ab_forces.ld,
            drag_N=drag,
            reheat=True,
            score=-1.0,
        )
    tsfc = afterburner_tsfc_kg_n_s(core.tsfc_kg_n_s, t_mil, t_ab, drag)
    eta_o = _eta_o_from_tsfc(core.v0, tsfc)
    pack = tsfc_from_eta_o(core.v0, eta_o, install_mult=1.0)
    return replace(
        core,
        thrust_avail_N=t_ab,
        load_raw=ab_load,
        load=clamp_load(ab_load),
        feasible=True,
        ld=ab_forces.ld,
        drag_N=drag,
        cd_breakdown=ab_forces.cd_breakdown,
        eta_o=eta_o,
        tsfc_kg_n_s=pack['tsfc_kg_n_s'],
        tsfc_mg_n_s=pack['tsfc_mg_n_s'],
        tsfc_lb_lbf_h=pack['tsfc_lb_lbf_h'],
        score=ab_forces.ld * eta_o,
        reheat=True,
        warning=None,
    )


def search_best_afterburner_altitude(
    mil_ctx: CruiseContext,
    ab_ctx: CruiseContext,
    mach: float,
    alt_min_m: float = 0.0,
    alt_max_m: float = 25000.0,
    coarse_m: float = ALT_COARSE_M,
    refine_m: float = ALT_REFINE_M,
) -> CruiseScored | None:
    """在加力包线内搜索使 L/D×含加力油耗的总效率最大的高度。

    默认可到海平面，与极速同一高度带，不能停在 11 km 军推巡航地板。
    只接受阻力不超过全部加力推力的点。
    """
    if mach <= 0:
        raise ValueError('马赫数须为正')
    best: CruiseScored | None = None
    for alt in altitude_grid(alt_min_m, alt_max_m, coarse_m):
        forces = try_cruise_forces(ab_ctx, mach, alt)
        if forces is None or not forces.feasible:
            continue
        try:
            scored = score_afterburner_point(mil_ctx, forces)
        except ValueError:
            continue
        if scored.score > (best.score if best is not None else -1.0):
            best = scored
    if best is None:
        return None
    lo = max(alt_min_m, best.alt_m - coarse_m)
    hi = min(alt_max_m, best.alt_m + coarse_m)
    for alt in altitude_grid(lo, hi, refine_m):
        forces = try_cruise_forces(ab_ctx, mach, alt)
        if forces is None or not forces.feasible:
            continue
        try:
            scored = score_afterburner_point(mil_ctx, forces)
        except ValueError:
            continue
        if scored.score > best.score:
            best = scored
    return best


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


def search_max_possible_cruise_mach(
    ctx: CruiseContext,
    mach_lo: float = MACH_SEARCH_LO,
    mach_hi: float = MACH_SEARCH_HI,
    iters: int = MACH_SEARCH_ITERS,
    alt_min_m: float = ALT_MIN_M,
    alt_max_m: float = ALT_MAX_M,
    step_m: float = ALT_COARSE_M,
) -> float | None:
    """11–25 km 内仍满足 92% 军推裕度的最大马赫（最大可能巡航）。

    比峰值高度段的实用最大巡航更快。跨声速鼓包会使可行性对马赫不单调
    （Ma 1.2 附近可能有空洞、更高马赫又能飞），不能从低马赫往上二分，
    否则会停在空洞前沿。改为从高往低找最高可行点，再在该点与上一格
    不可行点之间细化。低马赫在 11 km 可能因大迎角不可飞，不作为失败条件。
    """
    _require_mach_search_bounds(mach_lo, mach_hi, iters)
    if any_feasible_altitude(ctx, mach_hi, alt_min_m, alt_max_m, step_m):
        return mach_hi
    lo = None
    hi = mach_hi
    n_probe = max(iters, 8)
    for i in range(1, n_probe + 1):
        mach = mach_hi - (mach_hi - mach_lo) * i / n_probe
        if any_feasible_altitude(ctx, mach, alt_min_m, alt_max_m, step_m):
            lo = mach
            break
        hi = mach
    if lo is None:
        return None
    for _ in range(iters):
        mid = (lo + hi) / 2.0
        if any_feasible_altitude(ctx, mid, alt_min_m, alt_max_m, step_m):
            lo = mid
        else:
            hi = mid
    return lo


def snap_mach(mach: float, step: float) -> float:
    """把马赫收到步长网格，去掉 1.609999 这类二进制残渣。"""
    if step <= 0:
        raise ValueError('马赫步长须为正')
    return round(round(mach / step) * step, 10)


def profile_machs(
    mach_lo: float,
    mach_hi: float,
    step: float = MACH_PROFILE_STEP,
    extra: tuple[float, ...] | None = None,
) -> list[float]:
    """闭区间 [lo, hi] 上按固定步长生成马赫网格，再并入额外钉子。

    步长用整数格点（与高度网格相同），保证 0.01 时 1.21、1.76、1.77
    都会扫到，而不是靠插值点数碰巧落到 1.76。
    """
    if step <= 0:
        raise ValueError('马赫步长须为正')
    if mach_lo <= 0 or mach_hi <= mach_lo:
        raise ValueError('马赫搜索区间非法')
    n_steps = int(round((mach_hi - mach_lo) / step))
    raw = [mach_lo]
    for i in range(1, n_steps):
        raw.append(snap_mach(mach_lo + i * step, step))
    raw.append(mach_hi)
    pins = extra if extra is not None else (*FIXED_MACHS, SUPERCRUISE_BAND_HI)
    for mach in pins:
        if mach_lo < mach < mach_hi:
            raw.append(mach)
    unique: list[float] = []
    for mach in sorted(raw):
        if not unique or abs(mach - unique[-1]) > 1e-9:
            unique.append(mach)
    return unique


def scan_best_altitude_profile(
    ctx: CruiseContext,
    mach_lo: float = MACH_SEARCH_LO,
    mach_hi: float = MACH_SEARCH_HI,
    step: float = MACH_PROFILE_STEP,
    alt_min_m: float = ALT_MIN_M,
    alt_max_m: float = ALT_MAX_M,
    coarse_m: float = ALT_COARSE_M,
    refine_m: float = ALT_REFINE_M,
) -> list[CruiseScored]:
    """按马赫步长扫描各点最佳巡航高度，用于找峰值与回落点。"""
    profile: list[CruiseScored] = []
    for mach in profile_machs(mach_lo, mach_hi, step):
        scored = search_best_altitude(
            ctx, mach, alt_min_m, alt_max_m, coarse_m, refine_m,
        )
        if scored is not None:
            profile.append(scored)
    return profile


def contiguous_peak_max_mach(
    machs_alts: list[tuple[float, float]],
    peak_drop_m: float = 0.0,
    mach_hi: float | None = None,
) -> float | None:
    """最佳巡航高度达到全局最大值时的最大马赫。

    默认不容差：已经掉高（即使只掉一格）的点不算进实用最大巡航。
    不把跨声速掉高后再爬回的第二段算进去。machs_alts 须按马赫升序。
    """
    if peak_drop_m < 0:
        raise ValueError('峰值高度回落容差不能为负')
    if not machs_alts:
        return None
    peak_alt = max(alt for _mach, alt in machs_alts)
    idx = max(range(len(machs_alts)), key=lambda i: machs_alts[i][1])
    thresh = peak_alt - peak_drop_m
    lo = hi = idx
    while lo > 0 and machs_alts[lo - 1][1] >= thresh:
        lo -= 1
    while hi + 1 < len(machs_alts) and machs_alts[hi + 1][1] >= thresh:
        hi += 1
    mach = machs_alts[hi][0]
    if mach_hi is not None:
        mach = min(mach, mach_hi)
    return mach


def search_max_cruise_mach(
    ctx: CruiseContext,
    mach_lo: float = PRACTICAL_MAX_CRUISE_MACH_LO,
    mach_hi: float = MACH_SEARCH_HI,
    iters: int = MACH_SEARCH_ITERS,
    alt_min_m: float = ALT_MIN_M,
    alt_max_m: float = ALT_MAX_M,
    step_m: float = ALT_COARSE_M,
    peak_drop_m: float = 0.0,
    profile_step: float = MACH_PROFILE_STEP,
) -> float | None:
    """最佳巡航高度达到最大值时的军推巡航马赫（同一峰值平台取最大马赫）。

    默认只在 Ma 1.2 以上按 0.01 马赫扫剖面，避免把跨声速鼓包前的高度峰值
    当成实用最大巡航。取高度仍等于全局最大值的连续平台上沿，不容差掉高。
    11–20 km 内的绝对上限用 search_max_possible_cruise_mach。
    """
    _require_mach_search_bounds(mach_lo, mach_hi, iters)
    if peak_drop_m < 0:
        raise ValueError('峰值高度回落容差不能为负')
    refine_m = min(ALT_REFINE_M, step_m)
    profile = scan_best_altitude_profile(
        ctx, mach_lo, mach_hi, profile_step, alt_min_m, alt_max_m, step_m, refine_m,
    )
    found = contiguous_peak_max_mach(
        [(point.mach, point.alt_m) for point in profile],
        peak_drop_m,
        mach_hi,
    )
    if found is None:
        return None
    return snap_mach(found, profile_step)


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


def _search_max_ld_on_band(
    ctx: CruiseContext,
    mach: float,
    alt_min_m: float,
    alt_max_m: float,
    coarse_m: float,
    refine_m: float,
    ab_ctx: CruiseContext | None,
    primary_mode: str,
) -> MaxLdPoint | None:
    """在单一高度带上粗搜再细化，取可飞点中升阻比最大者。"""
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


def search_max_ld_altitude(
    ctx: CruiseContext,
    mach: float,
    alt_min_m: float = ALT_MIN_M,
    alt_max_m: float = ALT_MAX_M,
    coarse_m: float = ALT_COARSE_M,
    refine_m: float = ALT_REFINE_M,
    ab_ctx: CruiseContext | None = None,
    primary_mode: str = 'military',
    ab_alt_min_m: float | None = None,
    ab_alt_max_m: float | None = None,
) -> MaxLdPoint | None:
    """在给定马赫下，于可飞高度中取升阻比最大点。

    可飞 = 阻力不超过该点可用推力 × 裕度。军推不够时可用加力。
    巡航高度带找不到时，再在加力极速高度带（可到海平面）上搜。
    """
    if mach <= 0:
        raise ValueError('马赫数须为正')
    best = _search_max_ld_on_band(
        ctx, mach, alt_min_m, alt_max_m, coarse_m, refine_m, ab_ctx, primary_mode,
    )
    if best is not None:
        return best
    if ab_ctx is None:
        return None
    ab_lo = alt_min_m if ab_alt_min_m is None else ab_alt_min_m
    ab_hi = alt_max_m if ab_alt_max_m is None else ab_alt_max_m
    if ab_lo >= alt_min_m - 1e-9 and ab_hi <= alt_max_m + 1e-9:
        return None
    return _search_max_ld_on_band(
        ab_ctx, mach, ab_lo, ab_hi, coarse_m, refine_m, None, 'afterburner',
    )


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


def scan_altitudes_at_mach(
    ctx: CruiseContext,
    mach: float,
    alt_min_m: float = ALT_MIN_M,
    alt_max_m: float = ALT_MAX_M,
    step_m: float = ALT_COARSE_M,
) -> list[CruiseScored]:
    """给定马赫，按高度网格逐点计算升阻比、推力、负载与效率。

    不可行高度也保留：便于对照为何未被选为最佳巡航点。
    推力循环无解的高度跳过。
    """
    if mach <= 0:
        raise ValueError('马赫数须为正')
    rows: list[CruiseScored] = []
    for alt in altitude_grid(alt_min_m, alt_max_m, step_m):
        forces = try_cruise_forces(ctx, mach, alt)
        if forces is None:
            continue
        rows.append(score_cruise_point(ctx, forces))
    return rows


def altitude_scan_fields(point: CruiseScored, selected: bool = False) -> dict[str, Any]:
    """单个高度扫描点的展示字段。"""
    return {
        'alt_m': point.alt_m,
        'ld': point.ld,
        'thrust_avail_kN': point.thrust_avail_N / 1000.0,
        'load': point.load,
        'load_raw': point.load_raw,
        'feasible': point.feasible,
        'eta_th': point.eta_th,
        'eta_p': point.eta_p,
        'eta_o': point.eta_o,
        'score': point.score,
        'selected': selected,
    }


def build_altitude_scan(
    ctx: CruiseContext,
    mach: float,
    alt_min_m: float = ALT_MIN_M,
    alt_max_m: float = ALT_MAX_M,
    step_m: float = ALT_COARSE_M,
    selected: CruiseScored | None = None,
) -> list[dict[str, Any]]:
    """给定马赫扫描各高度，并标出已选最佳点。

    细化后的最佳高度若不在粗网格上，插入该点再按高度排序。
    """
    points = scan_altitudes_at_mach(ctx, mach, alt_min_m, alt_max_m, step_m)
    if selected is not None and all(abs(p.alt_m - selected.alt_m) > 1e-6 for p in points):
        points = sorted([*points, selected], key=lambda p: p.alt_m)
    best_alt = selected.alt_m if selected is not None else None
    return [
        altitude_scan_fields(
            point,
            selected=best_alt is not None and abs(point.alt_m - best_alt) < 1e-6,
        )
        for point in points
    ]


def search_afterburner_ceiling(
    ab_ctx: CruiseContext,
    mach: float,
    alt_min_m: float = 0.0,
    alt_max_m: float = 20000.0,
    coarse_m: float = ALT_COARSE_M,
    refine_m: float = ALT_REFINE_M,
    ceiling_margin: float = THRUST_MARGIN_DEFAULT,
) -> float | None:
    """加力升限：该马赫下阻力不超过 ceiling_margin × 加力推力的最大飞行高度。"""
    ceiling_ctx = replace(ab_ctx, thrust_margin=ceiling_margin)
    best_alt: float | None = None
    for alt in altitude_grid(alt_min_m, alt_max_m, coarse_m):
        forces = try_cruise_forces(ceiling_ctx, mach, alt)
        if forces is not None and forces.feasible:
            best_alt = alt  # 升序网格，最后一个可行点即最高高度
    if best_alt is None:
        return None
    lo = best_alt
    hi = min(alt_max_m, best_alt + coarse_m)
    for alt in altitude_grid(lo, hi, refine_m):
        forces = try_cruise_forces(ceiling_ctx, mach, alt)
        if forces is not None and forces.feasible:
            best_alt = alt
    return best_alt


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
        'reheat': point.reheat,
        'CL': point.cd_breakdown.get('CL'),
        'CD0': point.cd_breakdown.get('CD0'),
        'CDi': point.cd_breakdown.get('CDi'),
        'CDw': point.cd_breakdown.get('CDw'),
        'CDa': point.cd_breakdown.get('CDa'),
        'CDs': point.cd_breakdown.get('CDs'),
    }


def build_cruise_context_from_params(
    *,
    target: Aircraft,
    cf0: float,
    k_e: float,
    mass_kg: float,
    params: dict[str, Any],
) -> CruiseContext:
    """由 API 参数字典构造巡航上下文（涡扇 / 涡桨共用）。"""
    n_engines = int(params.get('n_engines') or 1)
    if n_engines < 1:
        raise ValueError('发动机台数须至少为 1')
    propulsion = normalize_propulsion(params.get('propulsion'))
    t4max = float(params.get('t4_K', params.get('t4', params.get('T4max', 0.0)) or 0.0))
    tsl_n = float(params.get('tsl_N') or 0.0)
    if tsl_n <= 0 and params.get('tsl_kN') not in (None, ''):
        tsl_n = float(params['tsl_kN']) * 1000.0
    shaft_power = float(params.get('shaft_power_sl_w') or 0.0)
    prop_diameter = float(params.get('prop_diameter_m') or 0.0)
    if propulsion == PROPULSION_TURBOFAN and tsl_n <= 0:
        raise ValueError('缺少海平面军推 tsl_N 或 tsl_kN')
    if propulsion != PROPULSION_TURBOFAN:
        if shaft_power <= 0:
            raise ValueError('涡桨须填写海平面轴功率 shaft_power_sl_w')
        if prop_diameter <= 0:
            raise ValueError('涡桨须填写桨盘直径 prop_diameter_m')
    return CruiseContext(
        target=target,
        cf0=cf0,
        k_e=k_e,
        mass_kg=mass_kg,
        n_engines=n_engines,
        bpr=float(params.get('bpr') or 0.0),
        opr=float(params.get('opr') or 1.0),
        t4_K=t4max,
        tsl_N=tsl_n,
        eta_c=float(params['eta_c']) if params.get('eta_c') not in (None, '') else ETA_C_DEFAULT,
        fan_pr_override=_optional_float_param(params.get('fan_pr_override', params.get('fan_pr'))),
        fpr=_optional_float_param(params.get('FPR', params.get('fan_pr_override'))),
        eps=float(params['eps']) if params.get('eps') not in (None, '') else EPS_DEFAULT,
        etan=float(params['etan']) if params.get('etan') not in (None, '') else ETAN_DEFAULT,
        acc_frac=float(params['acc_frac']) if params.get('acc_frac') not in (None, '') else ACC_FRAC_DEFAULT,
        t4idle=float(params['T4idle']) if params.get('T4idle') not in (None, '') else T4IDLE_DEFAULT,
        thrust_margin=float(params['thrust_margin']) if params.get('thrust_margin') not in (None, '') else THRUST_MARGIN_DEFAULT,
        tsfc_install_mult=float(params.get('tsfc_install_mult') or TSFC_INSTALL_MULT_DEFAULT),
        propulsion=propulsion,
        shaft_power_sl_w=shaft_power,
        prop_diameter_m=prop_diameter,
        prop_figure_of_merit=float(params.get('prop_figure_of_merit') or DEFAULT_FIGURE_OF_MERIT),
        nacelle_blockage_frac=float(params.get('nacelle_blockage_frac') or DEFAULT_NACELLE_BLOCKAGE_FRAC),
        eta_thermal_sl=float(params.get('eta_thermal_sl') or ETA_THERMAL_SL_DEFAULT),
        critical_alt_m=float(params.get('critical_alt_m') or CRITICAL_ALT_M_DEFAULT),
    )


def _optional_float_param(value: Any) -> float | None:
    if value in (None, ''):
        return None
    return float(value)
