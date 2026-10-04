"""阵风挂载模型端到端：CSV → catalog → 前端 data.json 同步。"""
import json

import pytest

from scripts.frontend_catalog import build_catalog_payload
from utils.aircraft_mount.rafale_mount import build_rafale_mount_catalog_payload
from utils.database_csv import load_aircraft_csv, load_carriers_csv
from utils.paths import AIRCRAFT_CSV, CARRIERS_CSV, DATA_DIR


@pytest.mark.e2e
def test_rafale_mount_catalog_matches_csv_and_data_json():
    """catalog 中 rafale_mount 与 CSV 一致，且 docs/data.json 已同步。"""
    direct = build_rafale_mount_catalog_payload()
    payload = build_catalog_payload(
        load_aircraft_csv(AIRCRAFT_CSV),
        load_carriers_csv(CARRIERS_CSV),
    )
    assert 'rafale_mount' in payload
    mount = payload['rafale_mount']
    assert mount['aircraft_ids'] == direct['aircraft_ids']
    assert len(mount['stations']) == len(direct['stations'])
    assert mount['stores_by_station']['FUS_CENT'] == direct['stores_by_station']['FUS_CENT']

    data_json = DATA_DIR.parent / 'docs' / 'data.json'
    if not data_json.is_file():
        pytest.skip('docs/data.json 尚未构建，请先运行 build_all.py')
    built = json.loads(data_json.read_text(encoding='utf-8'))
    assert built['rafale_mount']['stations'][0]['station_id'] == direct['stations'][0]['station_id']
    assert 'TGP_STN' in built['rafale_mount']['stores_by_station']
    assert built['version'] >= 37
