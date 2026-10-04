"""台风挂点目录端到端：CSV → catalog → 前端 data.json 契约。"""
from __future__ import annotations

import json

import pytest

from scripts.frontend_catalog import build_catalog_payload
from utils.database_csv import load_aircraft_csv, load_carriers_csv
from utils.paths import AIRCRAFT_CSV, CARRIERS_CSV, ROOT


@pytest.mark.e2e
def test_typhoon_stores_in_catalog_payload():
    """weapon_loadout.typhoon 应出现在 catalog 且挂点编号连续。"""
    payload = build_catalog_payload(
        load_aircraft_csv(AIRCRAFT_CSV),
        load_carriers_csv(CARRIERS_CSV),
    )
    typhoon = payload['weapon_loadout']['typhoon']
    assert typhoon['external_station_count'] == 13
    station_ids = [s['id'] for s in typhoon['stations']]
    assert station_ids == list(range(1, 11))
    semi = [s for s in typhoon['stations'] if s['mount'] == 'semi_recessed']
    assert len(semi) == 2
    assert {s['id'] for s in semi} == {4, 6}


@pytest.mark.e2e
def test_docs_data_json_includes_weapon_loadout():
    """docs/data.json 须含 weapon_loadout（build_all 后同步）。"""
    path = ROOT / 'docs' / 'data.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    assert 'weapon_loadout' in data
    assert data['weapon_loadout']['typhoon']['aircraft_id'] == 'Typhoon'
