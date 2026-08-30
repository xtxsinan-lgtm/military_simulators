"""布雷盖航程公式，以及降落冗余 / 爬升额外 / 降落节省的任务油量账。

作战半径先按出发总重 → 返回总重（干重+冗余）做布雷盖，不含爬升/降落；
再按出发瞬时油耗扣爬升等价距离的一半，按返回瞬时油耗加降落节省距离的一半。
爬升、降落与返场余油一律按亚音速瞬时油耗计算，即使巡航段是超音速。
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


def breguet_range_factor(
    v_mps: float,
    tsfc_kg_n_s: float,
    ld: float,
    g0: float = G0,
) -> float:
    """布雷盖航程因子 k，使航程 = k·ln(Wi/Wf)，单位米。"""
    if v_mps <= 0:
        raise ValueError('巡航速度须为正')
    if tsfc_kg_n_s <= 0:
        raise ValueError('TSFC 须为正')
    if ld <= 0:
        raise ValueError('升阻比须为正')
    if g0 <= 0:
        raise ValueError('重力加速度须为正')
    return (v_mps / (g0 * tsfc_kg_n_s)) * ld


def mixed_combat_radius_m(
    v_out_mps: float,
    tsfc_out_kg_n_s: float,
    ld_out: float,
    v_back_mps: float,
    tsfc_back_kg_n_s: float,
    ld_back: float,
    mass_initial_kg: float,
    mass_final_kg: float,
    g0: float = G0,
) -> float:
    """混合作战半径（米）：去程用超音速点、返程用亚音速点，两边距离相等。

    由 k_out·ln(m0/m1) = k_back·ln(m1/m_final) 解中间质量 m1，半径即单程距离。
    当去程与返程的 k 相同时，结果与对称布雷盖作战半径一致。
    """
    k_out = breguet_range_factor(v_out_mps, tsfc_out_kg_n_s, ld_out, g0)
    k_back = breguet_range_factor(v_back_mps, tsfc_back_kg_n_s, ld_back, g0)
    if mass_final_kg <= 0:
        raise ValueError('终了质量须为正')
    if mass_initial_kg <= mass_final_kg:
        raise ValueError('起飞质量须大于终了质量（须有可消耗内油）')
    ratio = k_back / k_out
    mass_mid = (mass_initial_kg * (mass_final_kg ** ratio)) ** (1.0 / (1.0 + ratio))
    if not (mass_final_kg < mass_mid < mass_initial_kg):
        raise ValueError('混合剖面无法在质量区间内闭合')
    return k_out * math.log(mass_initial_kg / mass_mid)


def average_fuel_kg_per_km(fuel_kg: float, radius_m: float) -> float:
    """按往返航程（2×作战半径）均摊的平均油耗，kg/km。"""
    if fuel_kg < 0:
        raise ValueError('燃油质量不能为负')
    if radius_m <= 0:
        raise ValueError('作战半径须为正才能计算平均油耗')
    distance_km = 2.0 * radius_m / 1000.0
    return fuel_kg / distance_km


def instantaneous_fuel_kg_per_km(
    v_mps: float,
    tsfc_kg_n_s: float,
    ld: float,
    mass_kg: float,
    g0: float = G0,
) -> float:
    """布雷盖瞬时油耗 dm/ds = (g·c·m)/(V·L/D)，单位 kg/km。"""
    if v_mps <= 0:
        raise ValueError('巡航速度须为正')
    if tsfc_kg_n_s <= 0:
        raise ValueError('TSFC 须为正')
    if ld <= 0:
        raise ValueError('升阻比须为正')
    if mass_kg <= 0:
        raise ValueError('质量须为正')
    if g0 <= 0:
        raise ValueError('重力加速度须为正')
    kg_per_m = (g0 * tsfc_kg_n_s * mass_kg) / (v_mps * ld)
    return kg_per_m * 1000.0


def reserve_loiter_km(reserve_min: float, cruise_kph: float) -> float:
    """降落冗余对应的等价平飞距离（km）= 巡航速度 × 时间。"""
    if reserve_min < 0:
        raise ValueError('冗余时间不能为负')
    if cruise_kph <= 0:
        raise ValueError('冗余巡航速度须为正')
    return cruise_kph * (reserve_min / 60.0)


def landing_reserve_fuel_kg(
    dry_mass_kg: float,
    loiter_km: float,
    v_mps: float,
    tsfc_kg_n_s: float,
    ld: float,
    g0: float = G0,
) -> float:
    """降落时须保留的余油。

    瞬时油耗与质量成正比：R = α·(dry+R)·D → R = α·dry·D / (1-α·D)。
    """
    if dry_mass_kg <= 0:
        raise ValueError('干质量须为正')
    if loiter_km < 0:
        raise ValueError('冗余平飞距离不能为负')
    if loiter_km == 0:
        return 0.0
    alpha = instantaneous_fuel_kg_per_km(v_mps, tsfc_kg_n_s, ld, 1.0, g0)
    denom = 1.0 - alpha * loiter_km
    if denom <= 0:
        raise ValueError('冗余平飞距离过长，布雷盖瞬时油耗无法闭合')
    return (alpha * dry_mass_kg * loiter_km) / denom


def apply_mission_distance_offsets_m(
    radius_m: float,
    climb_extra_km: float,
    descent_save_km: float,
) -> float:
    """把无爬升/降落的布雷盖半径，按爬升额外与降落节省的等价距离修正。

    作战半径是往返航程的一半，因此半径变化 = (−爬升 + 降落节省) / 2。
    """
    if climb_extra_km < 0:
        raise ValueError('爬升等价距离不能为负')
    if descent_save_km < 0:
        raise ValueError('降落等价距离不能为负')
    return radius_m + (-climb_extra_km + descent_save_km) * 500.0


def mission_fuel_budget(
    *,
    internal_fuel_kg: float,
    takeoff_mass_kg: float,
    dry_mass_kg: float,
    reserve_min: float,
    cruise_kph: float,
    climb_extra_km: float,
    descent_save_km: float,
    v_mps: float,
    tsfc_kg_n_s: float,
    ld: float,
    carrier: bool = False,
    g0: float = G0,
) -> dict[str, float | bool]:
    """按出发/返回瞬时油耗结算冗余、爬升额外与降落节省。

    布雷盖质量：出发总重 → 返回总重（干重+冗余），不含爬升/降落。
    出发瞬时油耗 × 爬升等价距离 = 爬升额外油量；
    返回瞬时油耗 × 降落等价距离 = 降落节省油量；冗余按返回重量闭合。
    可用油 = 内油 − 冗余 − 爬升额外 + 降落节省，供油量校核与平均油耗。
    """
    if internal_fuel_kg < 0:
        raise ValueError('内油不能为负')
    if takeoff_mass_kg <= dry_mass_kg:
        raise ValueError('起飞质量须大于干质量')
    if climb_extra_km < 0:
        raise ValueError('爬升等价距离不能为负')
    if descent_save_km < 0:
        raise ValueError('降落等价距离不能为负')
    loiter_km = reserve_loiter_km(reserve_min, cruise_kph)
    reserve_kg = landing_reserve_fuel_kg(
        dry_mass_kg, loiter_km, v_mps, tsfc_kg_n_s, ld, g0,
    )
    land_mass_kg = dry_mass_kg + reserve_kg
    takeoff_kg_per_km = instantaneous_fuel_kg_per_km(
        v_mps, tsfc_kg_n_s, ld, takeoff_mass_kg, g0,
    )
    landing_kg_per_km = instantaneous_fuel_kg_per_km(
        v_mps, tsfc_kg_n_s, ld, land_mass_kg, g0,
    )
    climb_extra_kg = takeoff_kg_per_km * climb_extra_km
    descent_save_kg = landing_kg_per_km * descent_save_km
    cruise_fuel_kg = internal_fuel_kg - reserve_kg
    usable_fuel_kg = cruise_fuel_kg - climb_extra_kg + descent_save_kg
    mass_final_kg = land_mass_kg
    mass_initial_kg = takeoff_mass_kg
    radius_adjust_km = (-float(climb_extra_km) + float(descent_save_km)) / 2.0
    return {
        'carrier': bool(carrier),
        'reserve_min': float(reserve_min),
        'reserve_cruise_kph': float(cruise_kph),
        'reserve_loiter_km': loiter_km,
        'reserve_fuel_kg': reserve_kg,
        'climb_extra_km': float(climb_extra_km),
        'climb_extra_kg': climb_extra_kg,
        'descent_save_km': float(descent_save_km),
        'descent_save_kg': descent_save_kg,
        'cruise_fuel_kg': cruise_fuel_kg,
        'usable_fuel_kg': usable_fuel_kg,
        'takeoff_kg_per_km': takeoff_kg_per_km,
        'landing_kg_per_km': landing_kg_per_km,
        'mass_initial_kg': mass_initial_kg,
        'mass_final_kg': mass_final_kg,
        'radius_adjust_km': radius_adjust_km,
        'subsonic_v_mps': float(v_mps),
        'subsonic_tsfc_kg_n_s': float(tsfc_kg_n_s),
        'subsonic_ld': float(ld),
    }
