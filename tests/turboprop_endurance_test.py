"""涡桨待战续航（留航余油 + 舰载/陆基双口径）单元测试。"""
from __future__ import annotations

from utils.combat_radius.combat_radius_presets import get_preset_by_id, load_engine_presets, load_presets
from utils.combat_radius.combat_radius_results import dashboard_params_from_preset
from utils.combat_radius.cruise_search import build_cruise_context_from_params, search_best_altitude
from utils.combat_radius.turboprop_endurance import (
    build_turboprop_endurance_pack,
    compute_turboprop_endurance_scenario,
    endurance_internal_fuel_kg,
    fuel_flow_kg_s_from_scored,
    loiter_landing_reserve_fuel_kg,
    search_min_fuel_flow_cruise,
)
from simulators.combat_radius.combat_radius import run_aircraft_dashboard_from_params, _calibrate_from_params
from utils.combat_radius.cruise_load import combat_mass_breakdown
from utils.combat_radius.propulsion import cruise_envelope_defaults


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


def test_land_internal_fuel_same_as_carrier_tanks():
    _, params = _e2_ctx_and_params()
    internal = params['internal_fuel_kg']
    assert endurance_internal_fuel_kg(params, land_scenario=False) == internal
    assert endurance_internal_fuel_kg(params, land_scenario=True) == internal


def test_loiter_reserve_less_than_mission_850kph_reserve():
    ctx, params = _e2_ctx_and_params()
    scored, _ = search_min_fuel_flow_cruise(ctx)
    assert scored is not None
    from utils.combat_radius.breguet import landing_reserve_fuel_kg, reserve_loiter_km
    dry = combat_mass_breakdown(
        empty_kg=params['empty_kg'],
        internal_fuel_kg=params['internal_fuel_kg'],
        n_pilots=params['n_pilots'],
        missile_mass_kg=0,
        n_missiles=0,
        fuel_fraction=0.0,
    )['total_kg']
    loiter_res = loiter_landing_reserve_fuel_kg(dry, 45.0, scored)
    fast_km = reserve_loiter_km(45.0, 850.0)
    fast_res = landing_reserve_fuel_kg(dry, fast_km, scored.v0, scored.tsfc_kg_n_s, scored.ld)
    assert loiter_res < fast_res


def test_e2_endurance_carrier_near_6h_land_slightly_longer():
    ctx, params = _e2_ctx_and_params()
    env = cruise_envelope_defaults(params)
    pack = build_turboprop_endurance_pack(params, ctx, env)
    carrier = pack['variants']['carrier']
    land = pack['variants']['land']
    assert carrier['feasible'] is True
    assert land['feasible'] is True
    assert carrier['internal_fuel_kg'] == land['internal_fuel_kg'] == params['internal_fuel_kg']
    assert 5.5 <= float(carrier['endurance_h']) <= 6.5
    assert float(land['endurance_h']) > float(carrier['endurance_h'])
    assert float(land['endurance_h']) <= 6.8


def test_kj600_endurance_same_rules_as_e2():
    presets = load_presets()
    engines = {e['id']: e for e in load_engine_presets()}
    params = dashboard_params_from_preset(get_preset_by_id(presets, 'KJ-600'), engines['aep500'])
    target, cf0, k_e = _calibrate_from_params(params)
    mass = combat_mass_breakdown(
        empty_kg=params['empty_kg'], internal_fuel_kg=params['internal_fuel_kg'],
        n_pilots=5, missile_mass_kg=0, n_missiles=0, fuel_fraction=0.5,
    )
    ctx = build_cruise_context_from_params(
        target=target, cf0=cf0, k_e=k_e, mass_kg=mass['total_kg'], params=params,
    )
    pack = build_turboprop_endurance_pack(params, ctx, cruise_envelope_defaults(params))
    c, land = pack['variants']['carrier'], pack['variants']['land']
    assert c['internal_fuel_kg'] == land['internal_fuel_kg'] == 5995.0
    assert float(c['endurance_h']) >= 6.0
    assert float(land['endurance_h']) > float(c['endurance_h'])
    assert float(land['endurance_h']) <= 7.5


def test_dashboard_includes_dual_endurance_for_e2():
    presets = load_presets()
    engines = {e['id']: e for e in load_engine_presets()}
    params = dashboard_params_from_preset(
        get_preset_by_id(presets, 'E-2'),
        engines['t56-a425'],
    )
    dash = run_aircraft_dashboard_from_params(params)
    en = dash.get('endurance') or {}
    assert en.get('feasible') is True
    assert en.get('scenario') == 'carrier'
    variants = en.get('variants') or {}
    assert variants['carrier']['endurance_h'] >= 5.5
    assert variants['land']['endurance_h'] > variants['carrier']['endurance_h']
    ids = [p.get('id') for p in dash.get('points') or []]
    assert 'min_fuel_flow_endurance' in ids


def test_compute_scenario_reserve_uses_loiter_fuel():
    ctx, params = _e2_ctx_and_params()
    env = cruise_envelope_defaults(params)
    result = compute_turboprop_endurance_scenario(
        ctx,
        params,
        land_scenario=False,
        reserve_min=45.0,
        alt_min_m=env['alt_min_m'],
        alt_max_m=env['alt_max_m'],
        mach_lo=env['mach_search_lo'],
        mach_hi=env['mach_search_hi'],
    )
    assert result is not None
    assert result.loiter_fuel_kg == params['internal_fuel_kg'] - result.reserve_fuel_kg
    assert result.endurance_h > 0
