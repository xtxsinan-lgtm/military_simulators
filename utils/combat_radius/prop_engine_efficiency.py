"""涡桨发动机巡航效率与可用推力估算。

与涡扇布雷顿循环不同：轴功率经减速器驱动桨盘，推进效率由动量理论 + 品质因数给出，
燃气发生器效率随负载变化，总效率 η_o = η_thermal × η_prop × η_gearbox。
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

from utils.combat_radius.engine_efficiency import FUEL_LHV_J_KG, isa
from utils.takeoff.propeller_thrust import (
    DEFAULT_FIGURE_OF_MERIT,
    DEFAULT_NACELLE_BLOCKAGE_FRAC,
    calc_prop_disk_area_m2,
    calc_propeller_thrust_n,
)

G0 = 9.80665
GEARBOX_ETA_DEFAULT = 0.98
ETA_THERMAL_SL_DEFAULT = 0.36
CRITICAL_ALT_M_DEFAULT = 7620.0
POWER_LAPSE_EXPONENT = 0.70
LOAD_FLOOR = 0.05


@dataclass
class PropEngineResult:
    """涡桨单点效率与推力结果。"""

    valid: bool
    warning: str | None = None
    T0: float = 0.0
    V0: float = 0.0
    thrust_N: float = 0.0
    max_thrust_N: float = 0.0
    shaft_power_used_w: float = 0.0
    shaft_power_max_w: float = 0.0
    load: float = 0.0
    eta_th: float = 0.0
    eta_p: float = 0.0
    eta_o: float = 0.0


def available_shaft_power_w(
    power_sl_w: float,
    alt_m: float,
    critical_alt_m: float = CRITICAL_ALT_M_DEFAULT,
) -> float:
    """可用轴功率：临界高度以下取海平面额定，以上按静压比幂次衰减。"""
    if power_sl_w <= 0:
        raise ValueError('海平面轴功率须为正')
    if alt_m < 0:
        raise ValueError('高度不能为负')
    if critical_alt_m <= 0:
        raise ValueError('临界高度须为正')
    if alt_m <= critical_alt_m:
        return power_sl_w
    _, p0 = isa(alt_m)
    _, p_sl = isa(0.0)
    if p_sl <= 0:
        return power_sl_w
    return power_sl_w * (p0 / p_sl) ** POWER_LAPSE_EXPONENT


def thermal_efficiency_for_load(load: float, eta_sl: float = ETA_THERMAL_SL_DEFAULT) -> float:
    """燃气发生器热效率：巡航中高负载略优于极低负载。"""
    if eta_sl <= 0:
        raise ValueError('海平面热效率须为正')
    load_clamped = min(max(float(load), LOAD_FLOOR), 1.0)
    return eta_sl * (0.88 + 0.12 * load_clamped)


def prop_thrust_from_power_n(
    power_w: float,
    alt_m: float,
    mach: float,
    prop_diameter_m: float,
    n_rotors: int,
    figure_of_merit: float = DEFAULT_FIGURE_OF_MERIT,
    nacelle_blockage_frac: float = DEFAULT_NACELLE_BLOCKAGE_FRAC,
) -> float:
    """给定轴功率下的桨盘可用推力（牛顿）。"""
    if power_w <= 0 or prop_diameter_m <= 0 or n_rotors < 1:
        return 0.0
    t0, _ = isa(alt_m)
    a0 = math.sqrt(1.4 * 287.0 * t0)
    v0 = max(mach, 0.0) * a0
    rho = 1.225 * (t0 / 288.15) ** 4.256 if alt_m <= 11000 else None
    if rho is None:
        # 11 km 以上仍用 ISA 密度公式（与 military_thrust 分段一致）
        if alt_m <= 20000:
            rho = 0.36391 * math.exp(-G0 * (alt_m - 11000.0) / (287.0 * 216.65))
        else:
            t_iso = 216.65 + 0.001 * (alt_m - 20000.0)
            p_iso = 5474.9 * (216.65 / t_iso) ** 34.163
            rho = p_iso / (287.0 * t_iso)
    disk = calc_prop_disk_area_m2(prop_diameter_m, n_rotors)
    return calc_propeller_thrust_n(
        power_w,
        rho,
        disk,
        v0,
        figure_of_merit=figure_of_merit,
        nacelle_blockage_frac=nacelle_blockage_frac,
    )


def solve_equilibrium_load(
    drag_n: float,
    power_max_w: float,
    alt_m: float,
    mach: float,
    prop_diameter_m: float,
    n_rotors: int,
    figure_of_merit: float,
    nacelle_blockage_frac: float,
) -> tuple[float, float, float] | None:
    """二分法求负载使 T(P_max·load) ≈ drag；返回 (load, thrust_N, power_used_w)。"""
    if drag_n <= 0 or power_max_w <= 0:
        return None
    t_max = prop_thrust_from_power_n(
        power_max_w, alt_m, mach, prop_diameter_m, n_rotors,
        figure_of_merit, nacelle_blockage_frac,
    )
    if t_max <= 0 or drag_n > t_max * (1.0 + 1e-6):
        return None
    lo, hi = LOAD_FLOOR, 1.0
    for _ in range(48):
        mid = (lo + hi) / 2.0
        p_mid = power_max_w * mid
        t_mid = prop_thrust_from_power_n(
            p_mid, alt_m, mach, prop_diameter_m, n_rotors,
            figure_of_merit, nacelle_blockage_frac,
        )
        if t_mid < drag_n:
            lo = mid
        else:
            hi = mid
    load = (lo + hi) / 2.0
    power_used = power_max_w * load
    thrust = prop_thrust_from_power_n(
        power_used, alt_m, mach, prop_diameter_m, n_rotors,
        figure_of_merit, nacelle_blockage_frac,
    )
    return load, thrust, power_used


def compute_prop_engine_efficiency(
    drag_n: float,
    mach: float,
    altitude_m: float,
    shaft_power_sl_w: float,
    prop_diameter_m: float,
    n_rotors: int = 2,
    figure_of_merit: float = DEFAULT_FIGURE_OF_MERIT,
    nacelle_blockage_frac: float = DEFAULT_NACELLE_BLOCKAGE_FRAC,
    eta_thermal_sl: float = ETA_THERMAL_SL_DEFAULT,
    critical_alt_m: float = CRITICAL_ALT_M_DEFAULT,
    gearbox_eta: float = GEARBOX_ETA_DEFAULT,
) -> PropEngineResult:
    """涡桨主入口：由平飞阻力反解轴功率负载，并给出 η_th、η_p、η_o。"""
    if mach < 0 or altitude_m < 0:
        raise ValueError('马赫与高度须非负')
    t0, _ = isa(altitude_m)
    v0 = mach * math.sqrt(1.4 * 287.0 * t0)
    power_max = available_shaft_power_w(shaft_power_sl_w, altitude_m, critical_alt_m)
    t_max = prop_thrust_from_power_n(
        power_max, altitude_m, mach, prop_diameter_m, n_rotors,
        figure_of_merit, nacelle_blockage_frac,
    )
    eq = solve_equilibrium_load(
        drag_n, power_max, altitude_m, mach, prop_diameter_m, n_rotors,
        figure_of_merit, nacelle_blockage_frac,
    )
    if eq is None:
        return PropEngineResult(
            valid=False,
            warning='thrust_insufficient',
            T0=t0,
            V0=v0,
            max_thrust_N=t_max,
            shaft_power_max_w=power_max,
        )
    load, thrust, power_used = eq
    eta_th = thermal_efficiency_for_load(load, eta_thermal_sl)
    eta_p = (thrust * v0) / power_used if power_used > 0 and v0 > 0 else 0.0
    eta_o = eta_th * eta_p * gearbox_eta
    warning = None
    if mach < 0.02:
        warning = 'static'
    return PropEngineResult(
        valid=True,
        warning=warning,
        T0=t0,
        V0=v0,
        thrust_N=thrust,
        max_thrust_N=t_max,
        shaft_power_used_w=power_used,
        shaft_power_max_w=power_max,
        load=load,
        eta_th=eta_th,
        eta_p=eta_p,
        eta_o=eta_o,
    )


def prop_engine_result_to_dict(result: PropEngineResult) -> dict[str, Any]:
    """PropEngineResult → 可 JSON 序列化的字典。"""
    return asdict(result)


def static_prop_thrust_sl_n(
    shaft_power_sl_w: float,
    prop_diameter_m: float,
    n_rotors: int = 2,
    figure_of_merit: float = DEFAULT_FIGURE_OF_MERIT,
    nacelle_blockage_frac: float = DEFAULT_NACELLE_BLOCKAGE_FRAC,
) -> float:
    """海平面静止桨盘推力，供界面「海平面军推」对照显示。"""
    return prop_thrust_from_power_n(
        shaft_power_sl_w,
        0.0,
        0.0,
        prop_diameter_m,
        n_rotors,
        figure_of_merit,
        nacelle_blockage_frac,
    )
