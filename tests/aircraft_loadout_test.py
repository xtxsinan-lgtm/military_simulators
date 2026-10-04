"""飞机外挂挂点与挂载方案单元测试。"""
import pytest

from utils.aircraft_loadout.catalog import (
    build_aircraft_loadout_catalog_payload,
    loadout_drag_store_count,
    loadout_total_mass_kg,
    validate_loadout,
)
from utils.database_csv import (
    AIRCRAFT_LOADOUT_PRESET_CSV_COLUMNS,
    AIRCRAFT_STATION_CSV_COLUMNS,
    AIRCRAFT_STORE_CATALOG_CSV_COLUMNS,
    load_aircraft_loadout_presets_csv,
    load_aircraft_station_csv,
    load_aircraft_store_catalog_csv,
)
from utils.paths import (
    AIRCRAFT_LOADOUT_PRESETS_CSV,
    AIRCRAFT_STATION_CSV,
    AIRCRAFT_STORE_CATALOG_CSV,
)


def test_store_catalog_loads_f16_weapons():
    """外挂目录应含 F-16 Block 50 挂载表中的典型弹药。"""
    stores = load_aircraft_store_catalog_csv()
    ids = {s['id'] for s in stores}
    for required in (
        'AIM-120C-5', 'AIM-9X', 'AGM-88C', 'GBU-31V1B',
        'FUEL-TANK-370', 'AN-AAQ-28', 'AN-ASQ-213',
    ):
        assert required in ids
    aim120 = next(s for s in stores if s['id'] == 'AIM-120C-5')
    assert aim120['category'] == 'aam'
    assert aim120['store_mount'] == 'pylon'


def test_f16_has_eleven_stations_block_50():
    """F-16C Block 50 应有 11 个挂点（含 5/5L/5R）。"""
    rows = load_aircraft_station_csv()
    f16 = [r for r in rows if r['aircraft_id'] == 'F-16' and r['block'] == 'Block 50']
    assert len(f16) == 11
    station_ids = {r['station_id'] for r in f16}
    assert station_ids == {'1', '2', '3', '4', '5', '5L', '5R', '6', '7', '8', '9'}


def test_f16_wingtip_only_aam():
    """翼尖挂点 1/9 仅允许空对空导弹。"""
    rows = load_aircraft_station_csv()
    tip1 = next(r for r in rows if r['station_id'] == '1')
    allowed = set(tip1['allowed_stores'])
    assert allowed <= {'AIM-120B', 'AIM-120C-5', 'AIM-9L', 'AIM-9M', 'AIM-9X'}
    assert 'AGM-88C' not in allowed


def test_f16_station_6_litening_or_cluster():
    """挂点 6 支持 Litening 或三联集束弹。"""
    rows = load_aircraft_station_csv()
    st6 = next(r for r in rows if r['aircraft_id'] == 'F-16' and r['station_id'] == '6')
    assert 'AN-AAQ-28' in st6['allowed_stores']
    assert 'CBU-87-3x' in st6['allowed_stores']


def test_validate_loadout_accepts_a2a_cap():
    """空战巡逻预设各挂点分配应通过校验。"""
    presets = load_aircraft_loadout_presets_csv()
    cap_rows = [r for r in presets if r['preset_id'] == 'a2a_cap']
    assignments = {r['station_id']: r['store_id'] for r in cap_rows}
    validate_loadout('F-16', assignments, block='Block 50')


def test_validate_loadout_rejects_disallowed_store():
    """翼尖挂 HARM 应被拒绝。"""
    with pytest.raises(ValueError, match='不支持'):
        validate_loadout('F-16', {'1': 'AGM-88C'}, block='Block 50')


def test_loadout_total_mass_a2a_cap():
    """空战巡逻（2×120 + 2×9）总外挂质量。"""
    presets = load_aircraft_loadout_presets_csv()
    cap_rows = [r for r in presets if r['preset_id'] == 'a2a_cap']
    assignments = {r['station_id']: r['store_id'] for r in cap_rows}
    mass = loadout_total_mass_kg(assignments)
    # 2×152 + 2×86 = 476
    assert mass == pytest.approx(476.0)


def test_loadout_drag_store_count_a2a_cap():
    """空战巡逻计入 4 个阻力外挂体。"""
    assignments = {'1': 'AIM-9M', '2': 'AIM-120C-5', '8': 'AIM-120C-5', '9': 'AIM-9M'}
    assert loadout_drag_store_count(assignments) == pytest.approx(4.0)


def test_build_catalog_payload_structure():
    """catalog 载荷应含 stores / aircraft_stations / presets。"""
    payload = build_aircraft_loadout_catalog_payload()
    assert 'stores' in payload
    assert 'store_categories' in payload
    assert 'aircraft_stations' in payload
    assert 'presets' in payload
    assert 'F-16' in payload['aircraft_stations']
    assert len(payload['aircraft_stations']['F-16']) == 11
    cap = next(p for p in payload['presets'] if p['id'] == 'a2a_cap')
    assert cap['total_mass_kg'] == pytest.approx(476.0)
    assert cap['drag_store_count'] == pytest.approx(4.0)


def test_csv_columns_exported():
    """列名常量可供 Excel 模板使用。"""
    assert 'mass_kg' in AIRCRAFT_STORE_CATALOG_CSV_COLUMNS
    assert 'allowed_stores' in AIRCRAFT_STATION_CSV_COLUMNS
    assert 'preset_id' in AIRCRAFT_LOADOUT_PRESET_CSV_COLUMNS
    assert AIRCRAFT_STORE_CATALOG_CSV.is_file()
    assert AIRCRAFT_STATION_CSV.is_file()
    assert AIRCRAFT_LOADOUT_PRESETS_CSV.is_file()
