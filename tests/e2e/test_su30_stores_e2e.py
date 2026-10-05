"""苏-30 挂点目录端到端：CSV → catalog → data.json / loadout_catalog。"""
from __future__ import annotations

import json

import pytest

from scripts.frontend_catalog import build_catalog_payload
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
