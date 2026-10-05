"""幻影 2000 挂载模型端到端：CSV → catalog → 前端 data.json 同步。"""
import json

import pytest

from apps.combat_radius_web import run_combat_radius_json
from scripts.frontend_catalog import build_catalog_payload
from utils.aircraft_mount.mirage2000_mount import build_mirage2000_mount_catalog_payload
from utils.combat_radius.combat_radius_presets import get_preset_by_id, load_engine_presets, load_presets
from utils.combat_radius.combat_radius_results import dashboard_params_from_preset
from utils.combat_radius.loadout import build_loadout_catalog_payload, clear_loadout_caches
from utils.database_csv import load_aircraft_csv, load_carriers_csv
from utils.paths import AIRCRAFT_CSV, CARRIERS_CSV, DATA_DIR


@pytest.mark.e2e
def test_mirage2000_mount_catalog_matches_csv_and_data_json():
    """catalog 中 mirage2000_mount 与 CSV 一致，且 docs/data.json 已同步。"""
    direct = build_mirage2000_mount_catalog_payload()
    payload = build_catalog_payload(
        load_aircraft_csv(AIRCRAFT_CSV),
        load_carriers_csv(CARRIERS_CSV),
    )
    assert 'mirage2000_mount' in payload
    mount = payload['mirage2000_mount']
    assert mount['aircraft_ids'] == direct['aircraft_ids']
    assert len(mount['stations']) == len(direct['stations'])
    assert mount['stores_by_station']['6'] == direct['stores_by_station']['6']

    data_json = DATA_DIR.parent / 'docs' / 'data.json'
    if not data_json.is_file():
        pytest.skip('docs/data.json 尚未构建，请先运行 build_all.py')
    built = json.loads(data_json.read_text(encoding='utf-8'))
    assert built['mirage2000_mount']['stations'][0]['station_id'] == direct['stations'][0]['station_id']
    assert 'atlis_ii' in {s['id'] for s in built['mirage2000_mount']['stores_by_station']['6']}
    assert built['version'] >= 38


@pytest.mark.e2e
def test_mirage2000_default_loadout_dashboard_runs():
    """幻影 2000 默认挂载可走通作战半径仪表盘。"""
    clear_loadout_caches()
    cat = build_loadout_catalog_payload()
    assert 'Mirage-2000' in cat['aircraft']
    ac = cat['aircraft']['Mirage-2000']
    assert len(ac['stations']) == 9
    assert ac['default_selection']['1'] == 'magic_ii@1'
    assert ac['default_selection']['9'] == 'magic_ii@1'

    aircraft = get_preset_by_id(load_presets(), 'Mirage-2000')
    engine = get_preset_by_id(load_engine_presets(), str(aircraft['engine_id']))
    params = dashboard_params_from_preset(aircraft, engine)
    params['loadout'] = {
        'aircraft_id': 'Mirage-2000',
        'selection': dict(ac['default_selection']),
    }
    result = run_combat_radius_json({'action': 'aircraft_dashboard', 'params': params})
    assert result['success'] is True, result
    # 2×Magic II + 2×MICA EM = 2×89 + 2×112 = 402
    assert result.get('loadout_summary', {}).get('weapons_mass_kg') == pytest.approx(402.0)
    ma08 = next((p for p in result.get('points') or [] if p.get('mach') == 0.8), None)
    assert ma08 is not None
    assert float(ma08['radius_km']) > 0
