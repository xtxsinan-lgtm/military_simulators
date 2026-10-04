"""阵风挂载模型单元测试。"""
import pytest

from utils.aircraft_mount.rafale_mount import (
    RAFALE_MOUNT_AIRCRAFT_IDS,
    build_rafale_mount_catalog_payload,
    build_rafale_mount_model,
    load_rafale_mount_stations,
    load_rafale_mount_stores,
    station_store_allowed,
    stores_for_station,
)
from utils.database_csv import (
    load_rafale_mount_stations_csv,
    load_rafale_mount_stores_csv,
)
from utils.paths import RAFALE_MOUNT_STATIONS_CSV, RAFALE_MOUNT_STORES_CSV


def test_load_rafale_mount_stations_csv_count():
    """阵风挂点 CSV 应含 16 个挂点（含 TGP 专用与保形挂点）。"""
    stations = load_rafale_mount_stations_csv()
    assert len(stations) == 16
    ids = {item['station_id'] for item in stations}
    assert 'WING_TIP_R' in ids
    assert 'FUS_CENT' in ids
    assert 'TGP_STN' in ids
    assert 'TOP_LAT_L' in ids


def test_load_rafale_mount_stores_csv_wing_tip_mica_only():
    """翼尖挂点仅允许 MICA IR/EM (NG)。"""
    stores = load_rafale_mount_stores_csv()
    tip_r = [row for row in stores if row['station_id'] == 'WING_TIP_R']
    assert len(tip_r) == 2
    assert {row['store_id'] for row in tip_r} == {'mica_ir_ng', 'mica_em_ng'}
    assert all(row['category'] == 'air_to_air' for row in tip_r)


def test_load_rafale_mount_stations_wrapper():
    """load_rafale_mount_stations 与 CSV 加载器结果一致。"""
    assert load_rafale_mount_stations() == load_rafale_mount_stations_csv()


def test_load_rafale_mount_stores_wrapper():
    """load_rafale_mount_stores 与 CSV 加载器结果一致。"""
    assert load_rafale_mount_stores() == load_rafale_mount_stores_csv()


def test_build_rafale_mount_model_indexes_stores():
    """合并模型应按挂点索引武器列表。"""
    model = build_rafale_mount_model()
    assert model['aircraft_ids'] == list(RAFALE_MOUNT_AIRCRAFT_IDS)
    assert len(model['stations']) == 16
    assert set(model['stores_by_station']) == {s['station_id'] for s in model['stations']}
    fus = model['stores_by_station']['FUS_CENT']
    assert any(item['id'] == 'asmp_a' and item['category'] == 'nuclear' for item in fus)
    assert any(item['id'] == 'narang_buddy' for item in fus)


def test_stores_for_station_wing_3():
    """外侧翼下挂点含 LR68 与 X-GUARD 拖曳诱饵。"""
    model = build_rafale_mount_model()
    wing3 = stores_for_station(model, 'WING_3_R')
    ids = {item['id'] for item in wing3}
    assert 'lr68' in ids
    assert 'x_guard_towed_decoy' in ids
    assert 'mica_ir_ng' in ids


def test_stores_for_station_unknown_raises():
    """未知挂点应抛出 KeyError。"""
    model = build_rafale_mount_model()
    with pytest.raises(KeyError):
        stores_for_station(model, 'NO_SUCH_STATION')


def test_station_store_allowed_tgp_pods():
    """TGP 专用挂点仅允许四类瞄准吊舱。"""
    model = build_rafale_mount_model()
    allowed = {'pod_tr', 'damocles_mp', 'talios', 'sniper'}
    tgp_ids = {item['id'] for item in stores_for_station(model, 'TGP_STN')}
    assert tgp_ids == allowed
    for pod_id in allowed:
        assert station_store_allowed(model, 'TGP_STN', pod_id)
    assert not station_store_allowed(model, 'TGP_STN', 'meteor')


def test_station_store_allowed_conformal_cft():
    """保形挂点仅允许 CFT 1150L。"""
    model = build_rafale_mount_model()
    for sid in ('TOP_LAT_R', 'TOP_LAT_L'):
        items = stores_for_station(model, sid)
        assert len(items) == 1
        assert items[0]['id'] == 'cft_1150l'
        assert station_store_allowed(model, sid, 'cft_1150l')
        assert not station_store_allowed(model, sid, 'mica_ir_ng')


def test_build_rafale_mount_catalog_payload_structure():
    """catalog 载荷应含类别、挂点与按挂点分组的武器表。"""
    payload = build_rafale_mount_catalog_payload()
    assert payload['aircraft_ids'] == ['Rafale', 'Rafale-M']
    assert 'air_to_air' in payload['categories']
    assert payload['categories']['nuclear']['label_en'] == 'NUCLEAR'
    assert len(payload['stations']) == 16
    assert 'WING_2_L' in payload['stores_by_station']
    assert payload['stations_csv'] == 'data/rafale_mount_stations.csv'
    assert payload['stores_csv'] == 'data/rafale_mount_stores.csv'


def test_rafale_mount_csv_files_exist():
    """数据文件路径有效。"""
    assert RAFALE_MOUNT_STATIONS_CSV.is_file()
    assert RAFALE_MOUNT_STORES_CSV.is_file()
