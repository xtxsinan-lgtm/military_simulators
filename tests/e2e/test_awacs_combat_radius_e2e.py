"""预警机（涡桨）作战半径端到端。"""
from __future__ import annotations

import pytest

from simulators.combat_radius.combat_radius import run_aircraft_dashboard_from_params
from utils.combat_radius.combat_radius_presets import get_preset_by_id, load_engine_presets, load_presets
from utils.combat_radius.combat_radius_results import dashboard_params_from_preset


@pytest.mark.e2e
def test_e2e_e2_hawkeye_combat_radius_dashboard():
    presets = load_presets()
    engines = {e['id']: e for e in load_engine_presets()}
    ac = get_preset_by_id(presets, 'E-2')
    eng = engines[ac['engine_id']]
    params = dashboard_params_from_preset(ac, eng)
    dash = run_aircraft_dashboard_from_params(params)
    assert dash['success'] is True
    feasible = [p for p in dash['points'] if p.get('feasible') and p.get('radius_km')]
    assert feasible, 'E-2 应至少有一个可行作战半径点'
    best = max(feasible, key=lambda p: float(p['radius_km']))
    assert 800 <= float(best['radius_km']) <= 3500
    assert float(best['mach']) <= 0.65


@pytest.mark.e2e
def test_e2e_kj600_combat_radius_dashboard():
    presets = load_presets()
    engines = {e['id']: e for e in load_engine_presets()}
    ac = get_preset_by_id(presets, 'KJ-600')
    eng = engines[ac['engine_id']]
    params = dashboard_params_from_preset(ac, eng)
    dash = run_aircraft_dashboard_from_params(params)
    assert dash['success'] is True
    feasible = [p for p in dash['points'] if p.get('feasible') and p.get('radius_km')]
    assert feasible
    e2 = run_aircraft_dashboard_from_params(
        dashboard_params_from_preset(
            get_preset_by_id(presets, 'E-2'),
            engines['t56-a425'],
        ),
    )
    e2_best = max(
        (p for p in e2['points'] if p.get('feasible') and p.get('radius_km')),
        key=lambda p: float(p['radius_km']),
    )
    kj_best = max(feasible, key=lambda p: float(p['radius_km']))
    assert float(kj_best['radius_km']) >= float(e2_best['radius_km']) * 0.85
