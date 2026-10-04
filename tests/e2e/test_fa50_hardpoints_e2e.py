"""FA-50 七挂点挂载数据端到端校验。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.frontend_catalog import build_catalog_payload
from utils.database_csv import load_aircraft_csv, load_carriers_csv
from utils.paths import AIRCRAFT_CSV, CARRIERS_CSV, ROOT
from utils.stores.hardpoints import (
    load_loadout_presets_csv,
    preset_to_loadout,
    validate_loadout,
)


@pytest.mark.e2e
def test_fa50_hardpoints_in_catalog_payload():
    """build_catalog_payload 含 FA-50 七挂点与弹药库。"""
    payload = build_catalog_payload(
        load_aircraft_csv(AIRCRAFT_CSV),
        load_carriers_csv(CARRIERS_CSV),
    )
    catalog = payload['stores_catalog']
    assert 'stores' in catalog and 'aircraft' in catalog
    fa50 = next(a for a in catalog['aircraft'] if a['aircraft_id'] == 'FA-50')
    assert len(fa50['stations']) == 7
    station_names = [s['name'] for s in fa50['stations']]
    assert any('翼尖' in n for n in station_names)
    assert any('BL 120' in n for n in station_names)
    assert any('BL 80' in n for n in station_names)
    assert any('机腹' in n for n in station_names)


@pytest.mark.e2e
def test_fa50_all_loadout_presets_validate():
    """全部 FA-50 预设挂载方案通过挂点校验。"""
    presets = load_loadout_presets_csv()['FA-50']
    assert len(presets) >= 4
    for preset in presets:
        loadout = preset_to_loadout(preset)
        errors = validate_loadout('FA-50', loadout)
        assert errors == [], f"预设 {preset['id']} 校验失败: {errors}"


@pytest.mark.e2e
def test_built_data_json_contains_stores_catalog():
    """构建产物 data.json 含 stores_catalog（若已 build）。"""
    data_path = ROOT / 'docs' / 'data.json'
    if not data_path.is_file():
        pytest.skip('docs/data.json 尚未构建')
    data = json.loads(data_path.read_text(encoding='utf-8'))
    assert 'stores_catalog' in data
    fa50 = next(
        a for a in data['stores_catalog']['aircraft'] if a['aircraft_id'] == 'FA-50'
    )
    assert len(fa50['stations']) == 7
