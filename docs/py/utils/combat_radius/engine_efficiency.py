"""涡扇/涡喷发动机总效率估算。

ISA 标准大气 + 完整压力追踪的实际布雷顿循环：
冲压增压 → 压气机 → 燃烧室 → 涡轮（驱动压气机+风扇+固定附件功率）
→ 核心喷管膨胀到环境压力；涵道流经风扇后单独喷管膨胀。
逐站跟踪总温、总压，核心流与涵道流分开计算比推力和动能增量，按流量加权
合成总推进效率。涡轮前温度 Tt4 不是预设值，而是由目标推力（负载 = 实际推力
与该工况最大可用推力之比，线性定义）反解得到。

这是面向工程估算的简化模型，不是认证级发动机性能预测工具。
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

GAMMA = 1.4
R = 287.0  # J/(kg·K)
CP = 1004.5  # J/(kg·K)
EXP = GAMMA / (GAMMA - 1)  # = 3.5
EXPI = (GAMMA - 1) / GAMMA  # = 1/3.5
G0 = 9.80665
# Jet A-1 低热值，用于 η_o = T·V / (ṁ_f·Q) ⇒ TSFC = V / (η_o·Q)
FUEL_LHV_J_KG = 43.15e6
# 安装 TSFC 乘数：布雷顿循环看不到进气道/宽风扇巡航损失。
# F135 为 STOVL 加宽风扇、加大核心，公开军推 TSFC（约 0.89）比 F100（0.73）还高约 22%，
# 而循环却把 F135 排成最省油。机身已留 FAT×BUMP≈1.10 残余后，1.15 把 F-35C Ma0.8 压到约 1400 km。
TSFC_INSTALL_MULT_DEFAULT = 1.0
F135_TSFC_INSTALL_MULT = 1.15
T4MAX_DEFAULT = 1850.0
T4IDLE_DEFAULT = 900.0
EPS_DEFAULT = 0.83
ETAN_DEFAULT = 0.95
ACC_FRAC_DEFAULT = 0.16


def isa(h_m: float) -> tuple[float, float]:
    """给定几何高度（米），返回 (T0 静温 K, P0 静压 Pa)。适用约 0–20 km。"""
    if h_m <= 11000:
        t0 = 288.15 - 0.0065 * h_m
        p0 = 101325.0 * (t0 / 288.15) ** 5.2559
    else:
        t0 = 216.65
        p0 = 22632.0 * math.exp(-9.80665 * (h_m - 11000.0) / (R * 216.65))
    return t0, p0


def opr_default(bpr: float) -> float:
    """由涵道比估计缺省总压比。"""
    return min(50.0, max(8.0, 12.0 + 1.6 * bpr))


def fpr_default(bpr: float) -> float:
    """由涵道比估计缺省风扇压比。"""
    return min(1.8, max(1.15, 1.8 - 0.35 * math.log(1.0 + bpr)))


@dataclass
class CycleResult:
    """单点实际布雷顿循环结果。"""

    valid: bool
    reason: str | None = None
    Tt5: float = 0.0
    Vj: float = 0.0
    Vfan: float = 0.0
    thrust_spec: float = 0.0  # 比推力（相对核心质量流量），m/s ≡ N/(kg/s)
    qin: float = 0.0  # 单位核心质量流量燃烧放热，J/kg
    eta_th: float = 0.0
    eta_p: float = 0.0
    eta_o: float = 0.0
    dTturb_actual: float = 0.0
    dTc: float = 0.0  # 核心压气机实际温升（附件功率定标用）


def cycle_for_t4(
    T4: float,
    bpr: float,
    T0: float,
    P0: float,
    V0: float,
    tau_r: float,
    OPR: float,
    FPR: float,
    ec: float,
    et: float,
    etan: float,
    bleed_work: float,
) -> CycleResult:
    """给定涡轮前总温 T4，算出该工作点的比推力与各项效率。

    ec/et：压气机/涡轮等熵效率；etan：喷管等熵效率；
    bleed_work：固定附件功率提取（J/kg 核心质量流量）。
    """
    pi_r = tau_r ** EXP
    tau_c = OPR ** EXPI
    tau_fan = FPR ** EXPI
    pt0 = P0 * pi_r

    d_tc = T0 * tau_r * (tau_c - 1.0) / ec
    tt3 = T0 * tau_r + d_tc

    d_tfan = T0 * tau_r * (tau_fan - 1.0) / ec

    qin = CP * (T4 - tt3)
    if qin <= 0:
        return CycleResult(valid=False, reason='qin')

    d_tturb_actual = d_tc + bpr * d_tfan + bleed_work / CP
    tt5 = T4 - d_tturb_actual
    d_tturb_ideal = d_tturb_actual / et
    tt5_ideal = T4 - d_tturb_ideal
    if tt5 <= 0 or tt5_ideal <= 0:
        return CycleResult(valid=False, reason='turbine')
    pt5 = (P0 * pi_r * OPR) * (tt5_ideal / T4) ** EXP

    t9_ideal = tt5 * (P0 / pt5) ** EXPI
    d_tnoz = tt5 - t9_ideal
    if d_tnoz < 0:
        return CycleResult(valid=False, reason='nozzle')
    vj = math.sqrt(2.0 * CP * etan * d_tnoz)

    vfan = V0
    if bpr > 0:
        tt13 = T0 * tau_r + d_tfan
        pt13 = pt0 * FPR
        t19_ideal = tt13 * (P0 / pt13) ** EXPI
        d_tnoz_fan = tt13 - t19_ideal
        if d_tnoz_fan > 0:
            vfan = math.sqrt(2.0 * CP * etan * d_tnoz_fan)

    thrust_spec = (vj - V0) + bpr * (vfan - V0)
    ke_rate = 0.5 * (vj ** 2 - V0 ** 2) + bpr * 0.5 * (vfan ** 2 - V0 ** 2)
    eta_th = ke_rate / qin
    eta_p = (V0 * thrust_spec) / ke_rate if (V0 > 0 and ke_rate > 0) else 0.0
    eta_o = eta_th * eta_p

    return CycleResult(
        valid=True,
        Tt5=tt5,
        Vj=vj,
        Vfan=vfan,
        thrust_spec=thrust_spec,
        qin=qin,
        eta_th=eta_th,
        eta_p=eta_p,
        eta_o=eta_o,
        dTturb_actual=d_tturb_actual,
        dTc=d_tc,
    )


def _find_valid_floor(
    bpr: float,
    T0: float,
    P0: float,
    V0: float,
    tau_r: float,
    OPR: float,
    FPR: float,
    ec: float,
    et: float,
    etan: float,
    bleed_work: float,
    lo: float,
    hi: float,
    iters: int = 60,
) -> float:
    """在 [lo, hi] 内找到循环刚好可行的最低 T4，避免二分落入无解区间。"""
    if cycle_for_t4(lo, bpr, T0, P0, V0, tau_r, OPR, FPR, ec, et, etan, bleed_work).valid:
        return lo
    for _ in range(iters):
        mid = (lo + hi) / 2.0
        if cycle_for_t4(mid, bpr, T0, P0, V0, tau_r, OPR, FPR, ec, et, etan, bleed_work).valid:
            hi = mid
        else:
            lo = mid
    return hi


def solve_t4_for_thrust(
    target: float,
    bpr: float,
    T0: float,
    P0: float,
    V0: float,
    tau_r: float,
    OPR: float,
    FPR: float,
    ec: float,
    et: float,
    etan: float,
    bleed_work: float,
    lo_raw: float,
    hi: float,
    iters: int = 60,
) -> float:
    """比推力关于 T4 单调递增，二分法求解维持目标比推力所需的 T4。"""
    lo = _find_valid_floor(
        bpr, T0, P0, V0, tau_r, OPR, FPR, ec, et, etan, bleed_work, lo_raw, hi,
    )
    a, b = lo, hi
    for _ in range(iters):
        mid = (a + b) / 2.0
        r = cycle_for_t4(mid, bpr, T0, P0, V0, tau_r, OPR, FPR, ec, et, etan, bleed_work)
        t = r.thrust_spec if r.valid else -1e9
        if t < target:
            a = mid
        else:
            b = mid
    return (a + b) / 2.0


@dataclass
class EngineResult:
    """给定负载下的效率与反解 T4。"""

    valid: bool
    warning: str | None = None  # core_limit | static | thrust_lapse | cycle_infeasible | …
    T4_solved: float = 0.0
    T0: float = 0.0
    V0: float = 0.0
    Vj: float = 0.0
    eta_th: float = 0.0
    eta_p: float = 0.0
    eta_o: float = 0.0
    thrust_spec: float = 0.0
    max_thrust_spec: float = 0.0


def compute_engine_efficiency(
    bpr: float,
    mach: float,
    altitude_m: float,
    load: float,
    OPR: float | None = None,
    FPR: float | None = None,
    T4max: float = T4MAX_DEFAULT,
    T4idle: float = T4IDLE_DEFAULT,
    eps: float = EPS_DEFAULT,
    etan: float = ETAN_DEFAULT,
    acc_frac: float = ACC_FRAC_DEFAULT,
) -> EngineResult:
    """主入口：由负载比反解 T4，并给出热效率、推进效率与总效率。"""
    if bpr < 0 or mach < 0 or altitude_m < 0 or T4max <= 0:
        raise ValueError('效率模型参数超出有效范围')
    if load < 0 or load > 1:
        raise ValueError('负载比例须在 [0, 1] 内')

    if OPR is None:
        OPR = opr_default(bpr)
    if FPR is None:
        FPR = fpr_default(bpr)

    t0, p0 = isa(altitude_m)
    a0 = math.sqrt(GAMMA * R * t0)
    v0 = mach * a0
    tau_r = 1.0 + (GAMMA - 1.0) / 2.0 * mach ** 2

    ref = cycle_for_t4(T4max, bpr, t0, p0, v0, tau_r, OPR, FPR, eps, eps, etan, bleed_work=0.0)
    if not ref.valid:
        return EngineResult(valid=False, warning='cycle_infeasible')
    bleed_work = acc_frac * ref.dTc * CP

    max_point = cycle_for_t4(T4max, bpr, t0, p0, v0, tau_r, OPR, FPR, eps, eps, etan, bleed_work)
    if not max_point.valid:
        return EngineResult(valid=False, warning='cycle_infeasible_with_bleed')

    idle_point = cycle_for_t4(T4idle, bpr, t0, p0, v0, tau_r, OPR, FPR, eps, eps, etan, bleed_work)
    idle_thrust = idle_point.thrust_spec if idle_point.valid else 0.0
    if idle_thrust < 0:
        idle_thrust = 0.0
    if idle_thrust >= max_point.thrust_spec:
        idle_thrust = 0.0

    thrust_target = idle_thrust + load * (max_point.thrust_spec - idle_thrust)
    t4_solved = solve_t4_for_thrust(
        thrust_target, bpr, t0, p0, v0, tau_r, OPR, FPR, eps, eps, etan, bleed_work,
        lo_raw=min(T4idle, 500.0), hi=T4max,
    )
    r = cycle_for_t4(t4_solved, bpr, t0, p0, v0, tau_r, OPR, FPR, eps, eps, etan, bleed_work)

    warning = None
    if (not r.valid) or (r.thrust_spec < thrust_target - 1.0):
        warning = 'core_limit'
    elif mach < 0.02:
        warning = 'static'
    elif max_point.thrust_spec < 40:
        warning = 'thrust_lapse'

    return EngineResult(
        valid=True,
        warning=warning,
        T4_solved=t4_solved,
        T0=t0,
        V0=v0,
        Vj=r.Vj,
        eta_th=r.eta_th,
        eta_p=r.eta_p,
        eta_o=r.eta_o,
        thrust_spec=r.thrust_spec,
        max_thrust_spec=max_point.thrust_spec,
    )


def find_optimal_load(
    bpr: float,
    mach: float,
    altitude_m: float,
    OPR: float | None = None,
    FPR: float | None = None,
    T4max: float = T4MAX_DEFAULT,
    T4idle: float = T4IDLE_DEFAULT,
    eps: float = EPS_DEFAULT,
    etan: float = ETAN_DEFAULT,
    acc_frac: float = ACC_FRAC_DEFAULT,
    coarse_step: float = 0.005,
) -> tuple[float, float]:
    """在 0–100% 负载范围内扫描，返回 (最优负载比例, 对应总效率)。"""
    best_load, best_eta = 0.0, -1.0
    n_steps = max(1, int(round(1.0 / coarse_step)))
    for i in range(1, n_steps + 1):
        load = min(i * coarse_step, 1.0)
        r = compute_engine_efficiency(
            bpr, mach, altitude_m, load, OPR, FPR, T4max, T4idle, eps, etan, acc_frac,
        )
        if r.valid and r.eta_o > best_eta:
            best_load, best_eta = load, r.eta_o
    return best_load, best_eta


def parse_tsfc_install_mult(raw: Any) -> float:
    """解析安装 TSFC 乘数；空/缺省为 1.0。"""
    if raw in (None, ''):
        return TSFC_INSTALL_MULT_DEFAULT
    val = float(raw)
    if val <= 0:
        raise ValueError('安装 TSFC 惩罚须为正')
    return val


def eta_o_after_install(
    eta_o: float,
    install_mult: float = TSFC_INSTALL_MULT_DEFAULT,
) -> float:
    """把循环总效率换成含安装损失的对外效率（η_o / 乘数）。"""
    if install_mult <= 0:
        raise ValueError('安装 TSFC 惩罚须为正')
    if eta_o < 0:
        raise ValueError('总效率不能为负')
    return eta_o / install_mult


def tsfc_from_eta_o(
    v0: float,
    eta_o: float,
    fuel_lhv_j_kg: float = FUEL_LHV_J_KG,
    install_mult: float = TSFC_INSTALL_MULT_DEFAULT,
) -> dict[str, float]:
    """由巡航速度与总效率求推力燃油消耗率。

    η_o = T·V / (ṁ_f·Q) ⇒ TSFC = ṁ_f / T = V / (η_o·Q)。
    install_mult 再乘到 TSFC 上，表示循环外的进气道/宽风扇巡航损失。
    返回 SI 值 kg/(N·s)、mg/(N·s) 以及常用的 lb/(lbf·h)。
    """
    if eta_o <= 0:
        raise ValueError('总效率须为正才能计算 TSFC（静飞或循环无解时不可用）')
    if v0 < 0:
        raise ValueError('飞行速度不能为负')
    if fuel_lhv_j_kg <= 0:
        raise ValueError('燃油热值须为正')
    if install_mult <= 0:
        raise ValueError('安装 TSFC 惩罚须为正')
    tsfc_si = v0 / (eta_o * fuel_lhv_j_kg) * install_mult
    return {
        'tsfc_kg_n_s': tsfc_si,
        'tsfc_mg_n_s': tsfc_si * 1e6,
        'tsfc_lb_lbf_h': tsfc_si * G0 * 3600.0,
        'fuel_lhv_j_kg': fuel_lhv_j_kg,
        'tsfc_install_mult': install_mult,
    }


def engine_result_to_dict(result: EngineResult) -> dict[str, Any]:
    """EngineResult → 可 JSON 序列化的字典。"""
    return asdict(result)
