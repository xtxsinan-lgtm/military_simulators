"""涡桨待战续航（最小流量速度）单元测试。"""
from __future__ import annotations

from utils.combat_radius.combat_radius_presets import get_preset_by_id, load_engine_presets, load_presets
from utils.combat_radius.combat_radius_results import dashboard_params_from_preset
from utils.combat_radius.cruise_search import build_cruise_context_from_params, search_best_altitude
from utils.combat_radius.lift_drag import model_coefficients
from utils.combat_radius.turboprop_endurance import (
    compute_turboprop_endurance,
    fuel_flow_kg_s_from_scored,
    search_min_fuel_flow_cruise,
)
from simulators.combat_radius.combat_radius import run_aircraft_dashboard_from_params, _calibrate_from_params
from utils.combat_radius.cruise_load import combat_mass_breakdown


def _e2_ctx_and_params():
    presets = load_presets()
    engines = {e['id']: e for e in load_engine_presets()}
    ac = get_preset_by_id(presets, 'E-2')
    params = dashboard_params_from_preset(ac, engines['t56-a425'])
    target, cf0, k_e = _calibrate_from_params(params)
    mass = combat_mass_breakdown(
        empty_kg=params['empty_kg'],
        internal_fuel_kg=params['internal_fuel_kg'],
        n_pilots=params['n_pilots'],
        missile_mass_kg=0,
        n_missiles=0,
        fuel_fraction=0.5,
    )
    ctx = build_cruise_context_from_params(
        target=target, cf0=cf0, k_e=k_e, mass_kg=mass['total_kg'], params=params,
    )
    return ctx, params


def test_fuel_flow_from_scored_positive():
    ctx, _ = _e2_ctx_and_params()
    found = search_min_fuel_flow_cruise(ctx)
    assert found is not None
    scored, flow = found
    assert flow == fuel_flow_kg_s_from_scored(scored)


def test_min_flow_speed_differs_from_max_range_score():
    ctx, _ = _e2_ctx_and_params()
    found = search_min_fuel_flow_cruise(ctx)
    assert found is not None
    min_flow_scored, _ = found
    best_range = search_best_altitude(ctx, 0.45, 3000, 12000, 500, 200)
    assert best_range is not None
    assert min_flow_scored.score != best_range.score or min_flow_scored.mach != best_range.mach


def test_dashboard_includes_endurance_for_e2():
    presets = load_presets()
    engines = {e['id']: e for e in load_engine_presets()}
    params = dashboard_params_from_preset(
        get_preset_by_id(presets, 'E-2'),
        engines['t56-a425'],
    )
    dash = run_aircraft_dashboard_from_params(params)
    en = dash.get('endurance') or {}
    assert en.get('feasible') is True
    assert float(en['endurance_h']) > 3.5
    assert float(en['mach']) < 0.55
    ids = [p.get('id') for p in dash.get('points') or []]
    assert 'min_fuel_flow_endurance' in ids


def test_compute_endurance_uses_loiter_fuel():
    ctx, params = _e2_ctx_and_params()
    result = compute_turboprop_endurance(
        ctx,
        float(params['internal_fuel_kg']),
        reserve_fuel_kg=800.0,
    )
    assert result is not None
    assert result.loiter_fuel_kg == params['internal_fuel_kg'] - 800.0
    assert result.endurance_h > 0
