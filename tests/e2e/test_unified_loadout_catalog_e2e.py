"""统一挂载目录：碎片机型可按挂点选弹并进入作战半径计算。"""
from __future__ import annotations

import pytest

from apps.combat_radius_web import run_combat_radius_json
from utils.combat_radius.combat_radius_presets import get_preset_by_id, load_engine_presets, load_presets
from utils.combat_radius.combat_radius_results import dashboard_params_from_preset
from utils.combat_radius.loadout import build_loadout_catalog_payload, clear_loadout_caches


@pytest.mark.e2e
def test_fragment_aircraft_loadout_dashboard_runs():
    """台风默认挂载可走通仪表盘计算。"""
    clear_loadout_caches()
    cat = build_loadout_catalog_payload()
    aircraft = get_preset_by_id(load_presets(), 'Typhoon')
    engine = get_preset_by_id(load_engine_presets(), str(aircraft['engine_id']))
    params = dashboard_params_from_preset(aircraft, engine)
    params['loadout'] = {
        'aircraft_id': 'Typhoon',
        'selection': dict(cat['aircraft']['Typhoon']['default_selection']),
    }
    result = run_combat_radius_json({'action': 'aircraft_dashboard', 'params': params})
    assert result['success'] is True, result
    assert result.get('loadout_summary', {}).get('weapons_mass_kg') == pytest.approx(476)
    ma08 = next((p for p in result.get('points') or [] if p.get('mach') == 0.8), None)
    assert ma08 is not None
    assert float(ma08['radius_km']) > 0


@pytest.mark.e2e
def test_catalog_covers_image_aircraft_with_models():
    """有挂载模型的示意图机型均出现在 loadout_catalog。"""
    clear_loadout_caches()
    cat = build_loadout_catalog_payload()
    expected = {
        'F-14', 'F-15E', 'F-16', 'F-2', 'FA-18C', 'FA-18E', 'FA-50',
        'FC-1', 'Gripen-CD', 'Gripen-EF', 'MiG-29K', 'Rafale', 'Rafale-M',
        'Su-30', 'Tejas', 'Typhoon',
    }
    assert expected <= set(cat['aircraft'])
