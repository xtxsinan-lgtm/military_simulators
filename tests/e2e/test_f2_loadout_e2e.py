"""F-2 挂载模式作战半径端到端测试。"""
from __future__ import annotations

import pytest

from apps.combat_radius_web import run_combat_radius_json
from utils.combat_radius.combat_radius_presets import get_preset_by_id, load_engine_presets, load_presets
from utils.combat_radius.combat_radius_results import dashboard_params_from_preset
from utils.combat_radius.loadout import get_aircraft_station_def, resolve_loadout


@pytest.mark.e2e
def test_f2_loadout_dashboard_returns_radius():
    """F-2 默认挂载仪表盘成功并给出半径。"""
    aircraft = get_preset_by_id(load_presets(), 'F-2')
    assert aircraft is not None
    engine = get_preset_by_id(load_engine_presets(), str(aircraft['engine_id']))
    assert engine is not None
    params = dashboard_params_from_preset(aircraft, engine)
    ac_def = get_aircraft_station_def('F-2')
    selection = {
        sid: f"{v['munition_id']}@{int(v['qty'])}"
        for sid, v in (ac_def.get('default_selection') or {}).items()
    }
    params['loadout'] = {'aircraft_id': 'F-2', 'selection': selection}
    result = run_combat_radius_json({'action': 'aircraft_dashboard', 'params': params})
    assert result['success'] is True
    assert result.get('loadout_summary', {}).get('weapons_mass_kg') == pytest.approx(508)
    ma08 = next((p for p in result.get('points') or [] if p.get('mach') == 0.8), None)
    assert ma08 is not None
    assert ma08.get('feasible') is True
    assert float(ma08['radius_km']) > 300


@pytest.mark.e2e
def test_f2_cap_with_external_fuel():
    """F-2 巡逻挂载：中线 300 gal + 内侧 600 gal×2 外油计入总油。"""
    cap = resolve_loadout('F-2', {
        'sta1': 'aam3@1',
        'sta2': 'aim7@1',
        'sta3': 'aim7@1',
        'sta9': 'aim7@1',
        'sta10': 'aim7@1',
        'sta11': 'aam3@1',
        'sta6': 'drop_tank_300@1',
        'sta4': 'drop_tank_600@1',
        'sta8': 'drop_tank_600@1',
    })
    assert cap.external_fuel_kg == pytest.approx(1015 + 1810 * 2)

    aircraft = get_preset_by_id(load_presets(), 'F-2')
    engine = get_preset_by_id(load_engine_presets(), str(aircraft['engine_id']))
    params = dashboard_params_from_preset(aircraft, engine)
    params['loadout'] = {
        'aircraft_id': 'F-2',
        'selection': {
            'sta1': 'aam3@1',
            'sta11': 'aam3@1',
            'sta6': 'drop_tank_300@1',
        },
    }
    result = run_combat_radius_json({'action': 'aircraft_dashboard', 'params': params})
    assert result['success'] is True
    assert result['loadout_summary']['external_fuel_kg'] == pytest.approx(1015)
    assert float(result['fuel_kg']) > float(aircraft['internal_fuel_kg'])
