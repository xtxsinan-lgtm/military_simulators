"""中型六代机三型端到端：机库、作战半径与起飞。"""
from __future__ import annotations

import pytest

from apps.combat_radius_web import run_combat_radius_json
from apps.web_simulator import filter_aircraft_for_mode, run_simulation
from scripts.frontend_catalog import build_catalog_payload
from utils.combat_radius.combat_radius_presets import get_preset_by_id, load_presets
from utils.database_csv import load_aircraft_csv, load_carriers_csv
from utils.paths import AIRCRAFT_CSV, CARRIERS_CSV


@pytest.mark.e2e
def test_e2e_ng6_catalog_and_combat_radius():
    """三型进入作战半径库；弹射/垂起进起飞目录，陆基不进。"""
    presets = load_presets()
    aircraft = load_aircraft_csv(AIRCRAFT_CSV)
    carriers = load_carriers_csv(CARRIERS_CSV)
    catalog = build_catalog_payload(aircraft, carriers)
    takeoff_ids = {a['id'] for a in catalog['aircraft']}
    cr_ids = {p['id'] for p in catalog['combat_radius_presets']}

    for aid in ('NG6C', 'NG6B', 'NG6A'):
        tgt = get_preset_by_id(presets, aid)
        assert tgt is not None, aid
        assert tgt['planform'] == 'lambda'
        assert tgt['layout'] == 'conventional', aid
        assert tgt['fuse_width_m'] == pytest.approx(3.40)
        assert tgt['fuse_height_m'] == pytest.approx(1.97)
        assert tgt['canard_htail_area_m2'] == pytest.approx(
            15.4 if aid == 'NG6C' else 12.1
        ), aid
        assert tgt['mach_angle_deg'] == pytest.approx(
            29.3 if aid == 'NG6C' else 27.3
        ), aid
        assert aid in cr_ids
        r = run_combat_radius_json({'action': 'predict_ld', 'params': {'target': tgt}})
        assert r['success'] is True, aid
        assert 6.0 < r['target']['ld'] < 18.0, aid
        from utils.combat_radius.cruise_load import wing_loading_t_m2
        assert tgt['wing_loading'] == pytest.approx(wing_loading_t_m2(
            tgt['empty_kg'], tgt['internal_fuel_kg'], tgt['wing_area_m2'],
            tgt['n_pilots'], tgt['missile_mass_kg'],
        ), abs=1e-6), aid

    assert aircraft['NG6C'].a2a_mass_kg == pytest.approx(13700 + 10820 + 100 + 840)
    assert aircraft['NG6B'].a2a_mass_kg == pytest.approx(13300 + 7890 + 100 + 840)
    assert get_preset_by_id(presets, 'NG6B')['internal_fuel_kg'] == pytest.approx(7890)
    assert get_preset_by_id(presets, 'NG6A')['internal_fuel_kg'] == pytest.approx(10120)
    assert get_preset_by_id(presets, 'NG6B')['empty_kg'] == pytest.approx(13300)
    assert get_preset_by_id(presets, 'NG6A')['empty_kg'] == pytest.approx(11900)

    assert get_preset_by_id(presets, 'NG6C')['wing_area_m2'] == pytest.approx(65.3)
    assert get_preset_by_id(presets, 'NG6B')['wing_area_m2'] == pytest.approx(51.3)
    assert get_preset_by_id(presets, 'NG6A')['wing_area_m2'] == pytest.approx(51.3)
    assert get_preset_by_id(presets, 'NG6C')['main_wing_area_m2'] == pytest.approx(36.0)
    assert get_preset_by_id(presets, 'NG6B')['main_wing_area_m2'] == pytest.approx(28.7)
    assert get_preset_by_id(presets, 'NG6A')['main_wing_area_m2'] == pytest.approx(28.7)

    assert 'NG6C' in takeoff_ids and 'NG6B' in takeoff_ids
    assert 'NG6A' not in takeoff_ids
    assert aircraft['NG6C'].t_max_sl_n == pytest.approx(185000)
    assert aircraft['NG6B'].is_vtol is True
    assert aircraft['NG6B'].mtow_kg == pytest.approx(28340)
    assert aircraft['NG6B'].max_payload_kg == 8000
    assert get_preset_by_id(presets, 'NG6B')['engine_id'] == 'f135b'
    from utils.combat_radius.combat_radius_config import layout_labels
    assert set(layout_labels()) == {'conventional', 'canard', 'tailless'}
    ng6c_tgt = get_preset_by_id(presets, 'NG6C')
    ng6a_tgt = get_preset_by_id(presets, 'NG6A')
    ng6c_ld = run_combat_radius_json({'action': 'predict_ld', 'params': {'target': ng6c_tgt}})
    ng6a_ld = run_combat_radius_json({'action': 'predict_ld', 'params': {'target': ng6a_tgt}})
    assert ng6c_ld['success'] is True and ng6a_ld['success'] is True
    assert 6.0 < ng6c_ld['target']['ld'] < 18.0
    assert 6.0 < ng6a_ld['target']['ld'] < 18.0
    from utils.combat_radius.combat_radius_results import run_preset_dashboard
    ng6c = run_preset_dashboard('NG6C')
    ng6b = run_preset_dashboard('NG6B')
    ng6a = run_preset_dashboard('NG6A')
    assert ng6c['mission_fuel']['reserve_min'] == 45
    assert ng6b['mission_fuel']['reserve_min'] == 30
    assert ng6a['mission_fuel']['reserve_min'] == 30
    stovl_ids = {a.id for a in filter_aircraft_for_mode('short_takeoff', list(aircraft.values()))}
    assert 'NG6B' in stovl_ids
    ski_ids = {a.id for a in filter_aircraft_for_mode('ski_jump', list(aircraft.values()))}
    assert 'NG6C' in ski_ids and 'NG6B' not in ski_ids


@pytest.mark.e2e
def test_e2e_ng6c_ski_jump_and_ng6b_short_takeoff():
    """弹射型可滑跃起飞；垂起型可平直甲板短距起飞。"""
    aircraft = load_aircraft_csv(AIRCRAFT_CSV)
    carriers = load_carriers_csv(CARRIERS_CSV)
    shandong = next(c for c in carriers if c.id == 'SHANDONG')
    wasp = next(c for c in carriers if c.id == 'WASP')
    ng6c = aircraft['NG6C']
    ski = run_simulation(
        'ski_jump', ng6c, shandong, ng6c.a2a_mass_kg, 30.0, shandong.max_speed_kt,
    )
    assert ski['success'] is True
    assert ski['distance_m'] is not None and ski['distance_m'] > 0

    ng6b = aircraft['NG6B']
    sto = run_simulation(
        'short_takeoff', ng6b, wasp, ng6b.a2a_mass_kg, 30.0, wasp.max_speed_kt,
    )
    assert sto['success'] is True
    assert sto['distance_m'] is not None
    assert sto['plume_applicable'] is True
