"""战斗机外挂挂点兼容库单元测试。"""
from __future__ import annotations

import pytest

from scripts.frontend_catalog import build_catalog_payload
from utils.aircraft_stores import build_fc1_stores_payload, stores_for_aircraft
from utils.database_csv import (
    load_aircraft_store_catalog_csv,
    load_aircraft_store_mounts_csv,
    load_aircraft_csv,
    load_carriers_csv,
)
from utils.paths import (
    AIRCRAFT_CSV,
    AIRCRAFT_STORE_CATALOG_CSV,
    AIRCRAFT_STORE_MOUNTS_CSV,
    CARRIERS_CSV,
)


def test_store_catalog_loads_fc1_weapons():
    """弹药目录应包含 FC-1 图示中的主要外挂。"""
    rows = load_aircraft_store_catalog_csv()
    ids = {row['store_id'] for row in rows}
    for store_id in (
        'pl5e2', 'pl12', 'mar1', 'c802a', 'ls6_500', 'bomb_1000', 'bomb_500',
        'bomb_250', 'practice_bomb', 'rocket', 'ft_800', 'ft_1100', 'hatf8',
        'wmd7', 'kg300g',
    ):
        assert store_id in ids


def test_fc1_mounts_cover_seven_stations():
    """FC-1 挂点 1–7 应完整覆盖，且对称挂点能力一致。"""
    payload = build_fc1_stores_payload()
    groups = payload['aircraft']['FC-1']
    assert len(groups) == 4

    station_map: dict[int, str] = {}
    for group in groups:
        for sid in group['station_ids']:
            station_map[sid] = group['group']

    assert station_map == {
        1: 'wingtip', 2: 'outer_wing', 3: 'inner_wing', 4: 'centerline',
        5: 'inner_wing', 6: 'outer_wing', 7: 'wingtip',
    }


def test_fc1_wingtip_only_pl5e2():
    """翼尖挂点仅允许 PL-5E-II。"""
    groups = stores_for_aircraft('FC-1')
    assert groups is not None
    wingtip = next(g for g in groups if g['group'] == 'wingtip')
    assert wingtip['station_ids'] == [1, 7]
    assert [item['store_id'] for item in wingtip['stores']] == ['pl5e2']
    assert wingtip['stores'][0]['max_qty'] == 1


def test_fc1_outer_wing_dual_racks():
    """外翼挂点应支持双联挂架弹药。"""
    groups = stores_for_aircraft('FC-1')
    assert groups is not None
    outer = next(g for g in groups if g['group'] == 'outer_wing')
    dual = {item['store_id']: item['max_qty'] for item in outer['stores']}
    assert dual['pl5e2'] == 2
    assert dual['pl12'] == 2
    assert dual['bomb_250'] == 2
    assert dual['practice_bomb'] == 2
    assert dual['mar1'] == 1
    assert 'c802a' not in dual


def test_fc1_inner_wing_heavy_stores():
    """内翼挂点应含反舰弹、副油箱与巡航导弹。"""
    groups = stores_for_aircraft('FC-1')
    assert groups is not None
    inner = next(g for g in groups if g['group'] == 'inner_wing')
    store_ids = {item['store_id'] for item in inner['stores']}
    assert {'c802a', 'bomb_1000', 'ft_800', 'ft_1100', 'hatf8', 'wmd7', 'kg300g'} <= store_ids


def test_fc1_centerline_no_wing_only_stores():
    """机腹中线不含仅翼下可选的常规炸弹与火箭巢。"""
    groups = stores_for_aircraft('FC-1')
    assert groups is not None
    belly = next(g for g in groups if g['group'] == 'centerline')
    store_ids = {item['store_id'] for item in belly['stores']}
    assert store_ids == {
        'c802a', 'ls6_500', 'bomb_1000', 'ft_800', 'hatf8', 'wmd7', 'kg300g',
    }


def test_mount_rows_reference_valid_stores():
    """挂点表中的 store_id 必须在弹药目录中存在。"""
    catalog_ids = {row['store_id'] for row in load_aircraft_store_catalog_csv()}
    for row in load_aircraft_store_mounts_csv():
        assert row['store_id'] in catalog_ids


def test_build_payload_rejects_unknown_store():
    """挂点表引用未知弹药时应报错。"""
    mounts = load_aircraft_store_mounts_csv()
    bad = dict(mounts[0])
    bad['store_id'] = 'missing_store'
    with pytest.raises(ValueError, match='未知 store_id'):
        build_fc1_stores_payload(mounts=[bad])


def test_catalog_payload_includes_fc1_stores():
    """前端 catalog 应携带 fc1_stores 字段。"""
    payload = build_catalog_payload(
        load_aircraft_csv(AIRCRAFT_CSV),
        load_carriers_csv(CARRIERS_CSV),
    )
    assert 'fc1_stores' in payload
    assert 'FC-1' in payload['fc1_stores']['aircraft']
    assert payload['fc1_stores']['stores']['pl12']['name'].startswith('PL-12')


def test_csv_files_exist():
    """外挂 CSV 源文件应存在。"""
    from utils.paths import FC1_STORE_CATALOG_CSV, FC1_STORE_MOUNTS_CSV

    assert FC1_STORE_CATALOG_CSV.is_file()
    assert FC1_STORE_MOUNTS_CSV.is_file()
