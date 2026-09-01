"""布雷盖航程与平均油耗单元测试。"""
from __future__ import annotations

import math

import pytest

from utils.combat_radius.breguet import (
    G0,
    average_fuel_kg_per_km,
    breguet_range_factor,
    breguet_range_m,
    combat_radius_m,
    instantaneous_fuel_kg_per_km,
    landing_reserve_fuel_kg,
    mission_fuel_budget,
    mixed_combat_radius_m,
    reserve_loiter_km,
)


def test_breguet_range_m_known_identity():
    """R = V/(g·c)·(L/D)·ln(Wi/Wf)。"""
    v, tsfc, ld, wi, wf = 240.0, 2.5e-5, 8.0, 28000.0, 20000.0
    expected = (v / (G0 * tsfc)) * ld * math.log(wi / wf)
    assert breguet_range_m(v, tsfc, ld, wi, wf) == pytest.approx(expected)


def test_combat_radius_m_is_half_range():
    r = breguet_range_m(240.0, 2.5e-5, 8.0, 28000.0, 20000.0)
    assert combat_radius_m(240.0, 2.5e-5, 8.0, 28000.0, 20000.0) == pytest.approx(r / 2.0)


def test_breguet_range_m_rejects_bad_inputs():
    with pytest.raises(ValueError, match='巡航速度'):
        breguet_range_m(0, 1e-5, 8, 2, 1)
    with pytest.raises(ValueError, match='TSFC'):
        breguet_range_m(100, 0, 8, 2, 1)
    with pytest.raises(ValueError, match='升阻比'):
        breguet_range_m(100, 1e-5, 0, 2, 1)
    with pytest.raises(ValueError, match='终了质量'):
        breguet_range_m(100, 1e-5, 8, 2, 0)
    with pytest.raises(ValueError, match='起飞质量'):
        breguet_range_m(100, 1e-5, 8, 1, 1)
    with pytest.raises(ValueError, match='重力'):
        breguet_range_m(100, 1e-5, 8, 2, 1, g0=0)


def test_average_fuel_kg_per_km():
    # 8000 kg 燃油、半径 1000 km → 往返 2000 km → 4 kg/km
    assert average_fuel_kg_per_km(8000.0, 1_000_000.0) == pytest.approx(4.0)
    with pytest.raises(ValueError, match='燃油'):
        average_fuel_kg_per_km(-1, 1000)
    with pytest.raises(ValueError, match='作战半径'):
        average_fuel_kg_per_km(100, 0)


def test_instantaneous_fuel_kg_per_km_matches_breguet_derivative():
    """dm/ds = (g·c·m)/(V·L/D)，单位 kg/km。"""
    v, tsfc, ld, mass = 240.0, 2.5e-5, 8.0, 28000.0
    expected = (G0 * tsfc * mass) / (v * ld) * 1000.0
    assert instantaneous_fuel_kg_per_km(v, tsfc, ld, mass) == pytest.approx(expected)
    with pytest.raises(ValueError, match='巡航速度'):
        instantaneous_fuel_kg_per_km(0, tsfc, ld, mass)
    with pytest.raises(ValueError, match='TSFC'):
        instantaneous_fuel_kg_per_km(v, 0, ld, mass)
    with pytest.raises(ValueError, match='升阻比'):
        instantaneous_fuel_kg_per_km(v, tsfc, 0, mass)
    with pytest.raises(ValueError, match='质量'):
        instantaneous_fuel_kg_per_km(v, tsfc, ld, 0)
    with pytest.raises(ValueError, match='重力'):
        instantaneous_fuel_kg_per_km(v, tsfc, ld, mass, g0=0)


def test_reserve_loiter_km_carrier_and_land():
    """舰载 45 min、陆基 30 min，均按 850 km/h。"""
    assert reserve_loiter_km(40, 850) == pytest.approx(850 * 40 / 60)
    assert reserve_loiter_km(30, 850) == pytest.approx(425.0)
    with pytest.raises(ValueError, match='冗余时间'):
        reserve_loiter_km(-1, 850)
    with pytest.raises(ValueError, match='冗余巡航速度'):
        reserve_loiter_km(30, 0)


def test_landing_reserve_fuel_kg_closed_form():
    """R = α·dry·D / (1-α·D)。"""
    v, tsfc, ld, dry = 236.11, 2.5e-5, 8.0, 20000.0
    loiter = 850 * 30 / 60
    alpha = instantaneous_fuel_kg_per_km(v, tsfc, ld, 1.0)
    expected = (alpha * dry * loiter) / (1.0 - alpha * loiter)
    assert landing_reserve_fuel_kg(dry, loiter, v, tsfc, ld) == pytest.approx(expected)
    assert landing_reserve_fuel_kg(dry, 0, v, tsfc, ld) == pytest.approx(0.0)
    with pytest.raises(ValueError, match='干质量'):
        landing_reserve_fuel_kg(0, loiter, v, tsfc, ld)
    with pytest.raises(ValueError, match='冗余平飞距离'):
        landing_reserve_fuel_kg(dry, -1, v, tsfc, ld)
    with pytest.raises(ValueError, match='无法闭合'):
        landing_reserve_fuel_kg(dry, 1e9, v, tsfc, ld)


def test_mission_fuel_budget_usable_and_masses():
    """终点 = 空重 +（冗余−降落节省）；可用油 = 内油 − 该值 − 爬升额外。"""
    v, tsfc, ld = 236.11, 2.5e-5, 8.0
    dry, fuel = 20000.0, 8000.0
    takeoff = dry + fuel
    budget = mission_fuel_budget(
        internal_fuel_kg=fuel,
        takeoff_mass_kg=takeoff,
        dry_mass_kg=dry,
        reserve_min=30,
        cruise_kph=850,
        climb_extra_km=120,
        descent_save_km=87.5,
        v_mps=v,
        tsfc_kg_n_s=tsfc,
        ld=ld,
        carrier=False,
    )
    assert budget['carrier'] is False
    assert budget['reserve_loiter_km'] == pytest.approx(425.0)
    return_mass = dry + budget['reserve_fuel_kg']
    assert budget['return_mass_kg'] == pytest.approx(return_mass)
    assert budget['takeoff_kg_per_km'] == pytest.approx(
        instantaneous_fuel_kg_per_km(v, tsfc, ld, takeoff),
    )
    assert budget['landing_kg_per_km'] == pytest.approx(
        instantaneous_fuel_kg_per_km(v, tsfc, ld, return_mass),
    )
    assert budget['climb_extra_kg'] == pytest.approx(budget['takeoff_kg_per_km'] * 120)
    assert budget['descent_save_kg'] == pytest.approx(budget['landing_kg_per_km'] * 87.5)
    held = budget['reserve_fuel_kg'] - budget['descent_save_kg']
    assert budget['held_fuel_kg'] == pytest.approx(held)
    assert budget['mass_final_kg'] == pytest.approx(dry + held)
    assert budget['usable_fuel_kg'] == pytest.approx(fuel - held - budget['climb_extra_kg'])
    assert budget['mass_initial_kg'] == pytest.approx(
        budget['mass_final_kg'] + budget['usable_fuel_kg'],
    )
    assert budget['mass_initial_kg'] == pytest.approx(takeoff - budget['climb_extra_kg'])
    r = combat_radius_m(v, tsfc, ld, budget['mass_initial_kg'], budget['mass_final_kg'])
    assert r > 0
    sea = mission_fuel_budget(
        internal_fuel_kg=fuel,
        takeoff_mass_kg=takeoff,
        dry_mass_kg=dry,
        reserve_min=40,
        cruise_kph=850,
        climb_extra_km=120,
        descent_save_km=87.5,
        v_mps=v,
        tsfc_kg_n_s=tsfc,
        ld=ld,
        carrier=True,
    )
    assert sea['carrier'] is True
    assert sea['reserve_fuel_kg'] > budget['reserve_fuel_kg']
    assert sea['usable_fuel_kg'] < budget['usable_fuel_kg']
    r_sub = combat_radius_m(v, tsfc, ld, budget['mass_initial_kg'], budget['mass_final_kg'])
    r_sup = combat_radius_m(400.0, 4e-5, 6.0, budget['mass_initial_kg'], budget['mass_final_kg'])
    assert r_sub > 0 and r_sup > 0
    with pytest.raises(ValueError, match='内油'):
        mission_fuel_budget(
            internal_fuel_kg=-1, takeoff_mass_kg=takeoff, dry_mass_kg=dry,
            reserve_min=30, cruise_kph=850, climb_extra_km=120, descent_save_km=87.5,
            v_mps=v, tsfc_kg_n_s=tsfc, ld=ld,
        )
    with pytest.raises(ValueError, match='起飞质量'):
        mission_fuel_budget(
            internal_fuel_kg=fuel, takeoff_mass_kg=dry, dry_mass_kg=dry,
            reserve_min=30, cruise_kph=850, climb_extra_km=120, descent_save_km=87.5,
            v_mps=v, tsfc_kg_n_s=tsfc, ld=ld,
        )
    with pytest.raises(ValueError, match='爬升等价'):
        mission_fuel_budget(
            internal_fuel_kg=fuel, takeoff_mass_kg=takeoff, dry_mass_kg=dry,
            reserve_min=30, cruise_kph=850, climb_extra_km=-1, descent_save_km=87.5,
            v_mps=v, tsfc_kg_n_s=tsfc, ld=ld,
        )
    with pytest.raises(ValueError, match='降落等价'):
        mission_fuel_budget(
            internal_fuel_kg=fuel, takeoff_mass_kg=takeoff, dry_mass_kg=dry,
            reserve_min=30, cruise_kph=850, climb_extra_km=120, descent_save_km=-1,
            v_mps=v, tsfc_kg_n_s=tsfc, ld=ld,
        )


def test_breguet_range_factor_matches_range_over_ln():
    v, tsfc, ld, wi, wf = 240.0, 2.5e-5, 8.0, 28000.0, 20000.0
    k = breguet_range_factor(v, tsfc, ld)
    assert k * math.log(wi / wf) == pytest.approx(breguet_range_m(v, tsfc, ld, wi, wf))
    with pytest.raises(ValueError, match='巡航速度'):
        breguet_range_factor(0, tsfc, ld)
    with pytest.raises(ValueError, match='TSFC'):
        breguet_range_factor(v, 0, ld)
    with pytest.raises(ValueError, match='升阻比'):
        breguet_range_factor(v, tsfc, 0)
    with pytest.raises(ValueError, match='重力'):
        breguet_range_factor(v, tsfc, ld, g0=0)


def test_mixed_combat_radius_equals_symmetric_when_k_equal():
    """去程返程 k 相同时，混合作战半径等于对称布雷盖半径。"""
    v, tsfc, ld, wi, wf = 240.0, 2.5e-5, 8.0, 28000.0, 20000.0
    mixed = mixed_combat_radius_m(v, tsfc, ld, v, tsfc, ld, wi, wf)
    assert mixed == pytest.approx(combat_radius_m(v, tsfc, ld, wi, wf))


def test_mixed_combat_radius_between_two_legs():
    """超音速去程油耗更高时，混合半径应介于两段对称半径之间。"""
    wi, wf = 28000.0, 20000.0
    r_sub = combat_radius_m(240.0, 2.5e-5, 8.0, wi, wf)
    r_sup = combat_radius_m(500.0, 5.0e-5, 5.0, wi, wf)
    mixed = mixed_combat_radius_m(500.0, 5.0e-5, 5.0, 240.0, 2.5e-5, 8.0, wi, wf)
    lo, hi = sorted((r_sub, r_sup))
    assert lo < mixed < hi


def test_mixed_combat_radius_rejects_bad_mass():
    with pytest.raises(ValueError, match='起飞质量'):
        mixed_combat_radius_m(240, 2.5e-5, 8, 240, 2.5e-5, 8, 1000, 1000)
    with pytest.raises(ValueError, match='终了质量'):
        mixed_combat_radius_m(240, 2.5e-5, 8, 240, 2.5e-5, 8, 2000, 0)
