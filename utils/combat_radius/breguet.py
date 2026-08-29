"""布雷盖航程公式：全程平飞、不预留爬升/降落/返场余油。

作战半径取航程的一半（去程+返程对称，挂弹不抛）。
"""
from __future__ import annotations

import math

G0 = 9.80665


def breguet_range_m(
    v_mps: float,
    tsfc_kg_n_s: float,
    ld: float,
    mass_initial_kg: float,
    mass_final_kg: float,
    g0: float = G0,
) -> float:
    """布雷盖航程（米）。TSFC 为 kg/(N·s)。"""
    if v_mps <= 0:
        raise ValueError('巡航速度须为正')
    if tsfc_kg_n_s <= 0:
        raise ValueError('TSFC 须为正')
    if ld <= 0:
        raise ValueError('升阻比须为正')
    if mass_final_kg <= 0:
        raise ValueError('终了质量须为正')
    if mass_initial_kg <= mass_final_kg:
        raise ValueError('起飞质量须大于终了质量（须有可消耗内油）')
    if g0 <= 0:
        raise ValueError('重力加速度须为正')
    return (v_mps / (g0 * tsfc_kg_n_s)) * ld * math.log(mass_initial_kg / mass_final_kg)


def combat_radius_m(
    v_mps: float,
    tsfc_kg_n_s: float,
    ld: float,
    mass_initial_kg: float,
    mass_final_kg: float,
    g0: float = G0,
) -> float:
    """作战半径（米）= 布雷盖航程 / 2。"""
    return breguet_range_m(
        v_mps, tsfc_kg_n_s, ld, mass_initial_kg, mass_final_kg, g0,
    ) / 2.0


def average_fuel_kg_per_km(fuel_kg: float, radius_m: float) -> float:
    """按往返航程（2×作战半径）均摊的平均油耗，kg/km。"""
    if fuel_kg < 0:
        raise ValueError('燃油质量不能为负')
    if radius_m <= 0:
        raise ValueError('作战半径须为正才能计算平均油耗')
    distance_km = 2.0 * radius_m / 1000.0
    return fuel_kg / distance_km
