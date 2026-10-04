"""F-15E 挂载模式作战半径端到端测试。"""
from __future__ import annotations

import pytest

from apps.combat_radius_web import run_combat_radius_json
from utils.combat_radius.combat_radius_presets import get_preset_by_id, load_engine_presets, load_presets
from utils.combat_radius.combat_radius_results import dashboard_params_from_preset
from utils.combat_radius.loadout import get_aircraft_station_def, resolve_loadout


@pytest.mark.e2e
def test_f15e_loadout_dashboard_returns_radius():
    """F-15E 默认挂载（四枚 AIM-120）仪表盘成功并给出半径。"""
    aircraft = get_preset_by_id(load_presets(), 'F-15E')
    assert aircraft is not None
    engine = get_preset_by_id(load_engine_presets(), str(aircraft['engine_id']))
    assert engine is not None
    params = dashboard_params_from_preset(aircraft, engine)
    ac_def = get_aircraft_station_def('F-15E')
    selection = {
        sid: f"{v['munition_id']}@{int(v['qty'])}"
        for sid, v in (ac_def.get('default_selection') or {}).items()
    }
    params['loadout'] = {'aircraft_id': 'F-15E', 'selection': selection}
    result = run_combat_radius_json({'action': 'aircraft_dashboard', 'params': params})
    assert result['success'] is True
    assert result.get('loadout_summary', {}).get('weapons_mass_kg') == pytest.approx(608)
    ma08 = next((p for p in result.get('points') or [] if p.get('mach') == 0.8), None)
    assert ma08 is not None
    assert ma08.get('feasible') is True
    assert float(ma08['radius_km']) > 500


@pytest.mark.e2e
def test_f15e_strike_loadout_heavier_than_clean_aam():
    """对地挂载（副油箱+炸弹）比空优四弹更重，外油更大。"""
    aam = resolve_loadout('F-15E', {
        'sta2a': 'aim120@1',
        'sta2b': 'aim120@1',
        'sta8a': 'aim120@1',
        'sta8b': 'aim120@1',
    })
    strike = resolve_loadout('F-15E', {
        'sta2': 'drop_tank_610@1',
        'sta5': 'drop_tank_610@1',
        'sta8': 'gbu31@1',
        'lcft_inbd': 'gbu38@3',
        'rcft_inbd': 'gbu38@3',
        'ltp': 'sniper@1',
        'sta2a': 'aim120@1',
        'sta8b': 'aim9@1',
    })
    assert strike.payload_mass_kg > aam.payload_mass_kg
    assert strike.external_fuel_kg > aam.external_fuel_kg

    aircraft = get_preset_by_id(load_presets(), 'F-15E')
    engine = get_preset_by_id(load_engine_presets(), str(aircraft['engine_id']))
    params = dashboard_params_from_preset(aircraft, engine)
    params['loadout'] = {
        'aircraft_id': 'F-15E',
        'selection': {
            'sta2': 'drop_tank_610@1',
            'sta8': 'gbu31@1',
            'sta2a': 'aim120@1',
            'sta8b': 'aim9@1',
        },
    }
    result = run_combat_radius_json({'action': 'aircraft_dashboard', 'params': params})
    assert result['success'] is True
    assert result['loadout_summary']['external_fuel_kg'] == pytest.approx(1855)
    assert float(result['fuel_kg']) > float(aircraft['internal_fuel_kg'])
