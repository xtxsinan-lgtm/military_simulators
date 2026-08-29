"""加力最大速度搜索单元测试。"""
from __future__ import annotations

import pytest

from utils.combat_radius.combat_radius_presets import get_preset_by_id, load_engine_presets, load_presets
from utils.combat_radius.cruise_search import CruiseContext, THRUST_MARGIN_DEFAULT
from utils.combat_radius.lift_drag import calibrate, aircraft_from_dict
from utils.combat_radius.max_speed_search import (
    MACH_SEARCH_HI,
    MACH_SEARCH_LO,
    search_global_max_speed,
    search_max_mach_at_altitude,
    true_airspeed_mps,
)
from utils.combat_radius.military_thrust import ETA_C_DEFAULT
from simulators.combat_radius.combat_radius import run_estimate_max_speed_from_params


def _f22_ctx(max_tsl_kn: float) -> CruiseContext:
    presets = load_presets()
    a1 = aircraft_from_dict(get_preset_by_id(presets, 'F-35C'))
    a2 = aircraft_from_dict(get_preset_by_id(presets, 'F-22'))
    tgt = aircraft_from_dict(get_preset_by_id(presets, 'F-22'))
    cf0, k_e = calibrate(a1, 8.8, a2, 8.0)
    return CruiseContext(
        target=tgt,
        cf0=cf0,
        k_e=k_e,
        mass_kg=22000.0,
        n_engines=2,
        bpr=0.30,
        opr=26.0,
        t4_K=1922.0,
        tsl_N=max_tsl_kn * 1000.0,
        eta_c=ETA_C_DEFAULT,
        thrust_margin=THRUST_MARGIN_DEFAULT,
    )


def test_true_airspeed_mps_sea_level():
    v = true_airspeed_mps(1.0, 0.0)
    assert 330 < v < 350


def test_true_airspeed_invalid_mach():
    with pytest.raises(ValueError, match='马赫'):
        true_airspeed_mps(0.0, 0.0)


def test_search_max_mach_at_altitude_returns_none_when_infeasible_low():
    ctx = _f22_ctx(50.0)
    assert search_max_mach_at_altitude(ctx, 15000.0) is None


def test_search_max_mach_at_altitude_f22_ab():
    ctx = _f22_ctx(156.0)
    mach = search_max_mach_at_altitude(ctx, 10000.0)
    assert mach is not None
    assert MACH_SEARCH_LO <= mach <= MACH_SEARCH_HI


def test_search_global_max_speed_f22_f119():
    ctx = _f22_ctx(156.0)
    result = search_global_max_speed(ctx)
    assert result is not None
    best = result['best']
    assert best['mach'] > 1.0
    assert best['v_kmh'] > 1500
    assert len(result['profile']) >= 1


def test_run_estimate_max_speed_from_params():
    presets = load_presets()
    engines = load_engine_presets()
    tgt = get_preset_by_id(presets, 'J-20')
    a1 = get_preset_by_id(presets, 'F-35C')
    a2 = get_preset_by_id(presets, 'F-22')
    eng = get_preset_by_id(engines, 'ws15')
    r = run_estimate_max_speed_from_params({
        'anchor1': a1,
        'ld1_target': a1['ld_known'],
        'anchor2': a2,
        'ld2_target': a2['ld_known'],
        'target': tgt,
        'empty_kg': tgt['empty_kg'],
        'internal_fuel_kg': tgt['internal_fuel_kg'],
        'n_pilots': tgt['n_pilots'],
        'missile_mass_kg': tgt['missile_mass_kg'],
        'n_engines': tgt['n_engines'],
        'bpr': eng['bpr'],
        'opr': eng['opr'],
        't4_K': eng['t4_K'],
        'max_tsl_kN': eng['max_tsl_kN'],
    })
    assert r['success'] is True
    assert r['feasible'] is True
    assert r['max_speed_mach'] > 1.0
    assert r['max_tsl_kN'] == 156.0


def test_run_estimate_max_speed_missing_max_thrust_raises():
    presets = load_presets()
    engines = load_engine_presets()
    tgt = get_preset_by_id(presets, 'F-22')
    a1 = get_preset_by_id(presets, 'F-35C')
    a2 = get_preset_by_id(presets, 'F-22')
    eng = get_preset_by_id(engines, 'f414')
    with pytest.raises(ValueError, match='加力'):
        run_estimate_max_speed_from_params({
            'anchor1': a1,
            'ld1_target': 8.8,
            'anchor2': a2,
            'ld2_target': 8.0,
            'target': tgt,
            'empty_kg': tgt['empty_kg'],
            'internal_fuel_kg': tgt['internal_fuel_kg'],
            'n_engines': 2,
            'bpr': eng['bpr'],
            'opr': eng['opr'],
            't4_K': eng['t4_K'],
        })
