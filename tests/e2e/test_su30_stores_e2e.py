"""苏-30 挂点目录端到端：CSV → catalog → data.json / loadout_catalog。"""
from __future__ import annotations

import json

import pytest

from apps.combat_radius_web import run_combat_radius_json
from scripts.frontend_catalog import build_catalog_payload
from utils.combat_radius.combat_radius_presets import get_preset_by_id, load_engine_presets, load_presets
from utils.combat_radius.combat_radius_results import dashboard_params_from_preset
from utils.combat_radius.loadout import build_loadout_catalog_payload, clear_loadout_caches
from utils.database_csv import load_aircraft_csv, load_carriers_csv
from utils.paths import AIRCRAFT_CSV, CARRIERS_CSV, ROOT
from utils.weapon_loadout.su30_stores import validate_su30_loadout


@pytest.mark.e2e
def test_su30_stores_in_catalog_payload():
    """weapon_loadout.su30 应出现在 catalog 且挂点 1–12 连续。"""
    payload = build_catalog_payload(
        load_aircraft_csv(AIRCRAFT_CSV),
        load_carriers_csv(CARRIERS_CSV),
    )
    su30 = payload['weapon_loadout']['su30']
    assert su30['external_station_count'] == 12
    station_ids = [s['id'] for s in su30['stations']]
    assert station_ids == list(range(1, 13))
    tip = next(s for s in su30['stations'] if s['id'] == 1)
    assert {x['weapon_id'] for x in tip['stores']} == {'r73e'}
    mid = next(s for s in su30['stations'] if s['id'] == 3)
    fab250 = next(x for x in mid['stores'] if x['weapon_id'] == 'fab250')
    assert fab250['max_qty'] == 6


@pytest.mark.e2e
def test_docs_data_json_includes_su30_weapon_loadout():
    """docs/data.json 须含 weapon_loadout.su30（build_all 后同步）。"""
    path = ROOT / 'docs' / 'data.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    assert 'weapon_loadout' in data
    assert data['weapon_loadout']['su30']['aircraft_id'] == 'Su-30'
    assert len(data['weapon_loadout']['su30']['stations']) == 12


@pytest.mark.e2e
def test_loadout_catalog_includes_su30_with_qty_options():
    """统一 loadout_catalog 含 Su-30，且多联挂架展开为多档 qty。"""
    clear_loadout_caches()
    cat = build_loadout_catalog_payload()
    assert 'Su-30' in cat['aircraft']
    ac = cat['aircraft']['Su-30']
    assert len(ac['stations']) == 12
    st3 = next(s for s in ac['stations'] if s['id'] == '3')
    fab_opts = [
        o for o in st3['options']
        if o.get('munition_id') == 'fab250'
    ]
    assert {int(o['qty']) for o in fab_opts} == {1, 2, 3, 4, 5, 6}
    # 默认空战挂载可通过校验（catalog 键形如 munition_id@qty）
    sel = {}
    for sid, key in ac['default_selection'].items():
        munition_id, qty_s = str(key).split('@', 1)
        sel[int(sid)] = {'weapon_id': munition_id, 'qty': int(float(qty_s))}
    assert validate_su30_loadout(sel) == []


@pytest.mark.e2e
def test_su30_in_combat_radius_presets_and_default_loadout_dashboard():
    """苏-30 出现在作战半径机型列表，默认挂载可走通仪表盘。"""
    clear_loadout_caches()
    presets = load_presets()
    aircraft = get_preset_by_id(presets, 'Su-30')
    assert aircraft is not None
    assert aircraft['nation'] == '俄罗斯'
    assert aircraft['engine_id'] == 'al31fp'
    assert aircraft['n_pilots'] == 2
    assert aircraft['store_mount'] == 'pylon'
    assert aircraft['n_engines'] == 2

    cat = build_loadout_catalog_payload()
    ac = cat['aircraft']['Su-30']
    assert len(ac['stations']) == 12
    engine = get_preset_by_id(load_engine_presets(), 'al31fp')
    params = dashboard_params_from_preset(aircraft, engine)
    params['loadout'] = {
        'aircraft_id': 'Su-30',
        'selection': dict(ac['default_selection']),
    }
    result = run_combat_radius_json({'action': 'aircraft_dashboard', 'params': params})
    assert result['success'] is True, result
    # 默认：6×R-73E + 6×RVV-AE = 6×105 + 6×175 = 1680
    assert result.get('loadout_summary', {}).get('weapons_mass_kg') == pytest.approx(1680.0)
    ma08 = next((p for p in result.get('points') or [] if p.get('mach') == 0.8), None)
    assert ma08 is not None
    assert float(ma08['radius_km']) > 200
