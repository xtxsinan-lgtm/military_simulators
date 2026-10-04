"""F-14 挂载模型端到端：catalog 同步与预设校验。"""
from __future__ import annotations

import pytest

from scripts.frontend_catalog import build_catalog_payload
from utils.database_csv import load_aircraft_csv, load_carriers_csv
from utils.paths import AIRCRAFT_CSV, CARRIERS_CSV
from utils.stores.loadout import loadout_total_mass_kg, parse_loadout_string, validate_loadout


@pytest.mark.e2e
def test_e2e_f14_store_model_in_catalog():
    """F-14 挂点布局与预设已进入前端 catalog。"""
    payload = build_catalog_payload(
        load_aircraft_csv(AIRCRAFT_CSV),
        load_carriers_csv(CARRIERS_CSV),
    )
    stores = payload['aircraft_stores']
    f14_layout = stores['aircraft_store_layouts']['F-14']
    station_ids = [s['station_id'] for s in f14_layout]
    assert station_ids == ['1', '1b', '2', '3', '4', '5', '6', '7', '8', '8b']

    f14_presets = {p['preset_id']: p for p in stores['aircraft_loadout_presets']['F-14']}
    assert set(f14_presets) == {'cap', 'tarps', 'tank'}

    # 三种预设均可校验通过
    for preset in f14_presets.values():
        items = parse_loadout_string(preset['loadout'])
        validate_loadout('F-14', items)

    # 转场预设含 2 副油箱
    tank_items = parse_loadout_string(f14_presets['tank']['loadout'])
    assert loadout_total_mass_kg(tank_items) == pytest.approx(2 * 85 + 2 * 231 + 2 * 1043)

    # F-14 机型 BVR 标签已更新
    f14_ac = next(a for a in payload['aircraft'] if a['id'] == 'F-14')
    assert f14_ac['bvr_missile'] == 'AIM-54 Phoenix'
