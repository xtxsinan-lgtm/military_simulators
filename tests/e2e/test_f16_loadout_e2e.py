"""F-16C Block 50 挂载模型端到端：CSV → catalog → 校验与质量汇总。"""
import json

import pytest

from scripts.frontend_catalog import build_catalog_payload
from utils.aircraft_loadout.catalog import validate_loadout
from utils.database_csv import load_aircraft_csv, load_carriers_csv
from utils.paths import AIRCRAFT_CSV, CARRIERS_CSV, ROOT


@pytest.mark.e2e
def test_e2e_f16_loadout_in_catalog_and_presets_valid():
    """F-16 挂点表与预设应进入 data.json 且全部通过挂点能力校验。"""
    payload = build_catalog_payload(
        load_aircraft_csv(AIRCRAFT_CSV),
        load_carriers_csv(CARRIERS_CSV),
    )
    loadout = payload['aircraft_loadout']
    assert loadout['aircraft_stations']['F-16']
    f16_stations = {s['station_id'] for s in loadout['aircraft_stations']['F-16']}
    assert '5L' in f16_stations and '5R' in f16_stations

    f16_presets = [p for p in loadout['presets'] if p['aircraft_id'] == 'F-16']
    assert len(f16_presets) >= 4
    for preset in f16_presets:
        validate_loadout(
            preset['aircraft_id'],
            preset['stations'],
            block=preset['block'],
        )
        assert preset['total_mass_kg'] > 0

    docs_path = ROOT / 'docs' / 'data.json'
    docs = json.loads(docs_path.read_text(encoding='utf-8'))
    assert docs['aircraft_loadout'] == loadout
