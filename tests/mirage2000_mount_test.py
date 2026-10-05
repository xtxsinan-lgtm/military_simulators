"""幻影 2000 挂载模型单元测试。"""
import pytest

from utils.aircraft_mount.mirage2000_mount import (
    MIRAGE2000_MOUNT_AIRCRAFT_IDS,
    build_mirage2000_mount_catalog_payload,
    build_mirage2000_mount_model,
    load_mirage2000_mount_stations,
    load_mirage2000_mount_stores,
    station_store_allowed,
    stores_for_station,
)
from utils.database_csv import (
    load_mirage2000_mount_stations_csv,
    load_mirage2000_mount_stores_csv,
)
from utils.paths import MIRAGE2000_MOUNT_STATIONS_CSV, MIRAGE2000_MOUNT_STORES_CSV


def test_load_mirage2000_mount_stations_csv_count():
    """幻影 2000 应有 Pylon 1–9 共 9 个挂点。"""
    stations = load_mirage2000_mount_stations_csv()
    assert len(stations) == 9
    ids = {item['station_id'] for item in stations}
    assert ids == {str(i) for i in range(1, 10)}
    tip9 = next(s for s in stations if s['station_id'] == '9')
    tip1 = next(s for s in stations if s['station_id'] == '1')
    assert tip9['side'] == 'left'
    assert tip1['side'] == 'right'
    assert tip9['position'] == 'wing_tip'
    center = next(s for s in stations if s['station_id'] == '5')
    assert center['position'] == 'fuselage_center'


def test_load_mirage2000_mount_stores_wingtip_magic_only():
    """翼尖挂点仅允许 Magic II。"""
    stores = load_mirage2000_mount_stores_csv()
    for sid in ('1', '9'):
        tip = [row for row in stores if row['station_id'] == sid]
        assert len(tip) == 1
        assert tip[0]['store_id'] == 'magic_ii'
        assert tip[0]['category'] == 'air_to_air'


def test_load_mirage2000_mount_stations_wrapper():
    """load_mirage2000_mount_stations 与 CSV 加载器结果一致。"""
    assert load_mirage2000_mount_stations() == load_mirage2000_mount_stations_csv()


def test_load_mirage2000_mount_stores_wrapper():
    """load_mirage2000_mount_stores 与 CSV 加载器结果一致。"""
    assert load_mirage2000_mount_stores() == load_mirage2000_mount_stores_csv()


def test_build_mirage2000_mount_model_indexes_stores():
    """合并模型应按挂点索引武器列表。"""
    model = build_mirage2000_mount_model()
    assert model['aircraft_ids'] == list(MIRAGE2000_MOUNT_AIRCRAFT_IDS)
    assert len(model['stations']) == 9
    assert set(model['stores_by_station']) == {s['station_id'] for s in model['stations']}
    fus = model['stores_by_station']['5']
    assert any(item['id'] == 'asmp' and item['category'] == 'nuclear' for item in fus)
    assert any(item['id'] == 'apache' for item in fus)
    assert any(item['id'] == 'am39_exocet' for item in fus)


def test_stores_for_station_outer_wing():
    """机翼外侧挂点含 Super 530D、飞鱼与副油箱。"""
    model = build_mirage2000_mount_model()
    for sid in ('2', '8'):
        ids = {item['id'] for item in stores_for_station(model, sid)}
        assert 'super_530d' in ids
        assert 'am39_exocet' in ids
        assert 'ft_1700l' in ids
        assert 'ft_2000l' in ids
        assert 'mk82_4x' in ids


def test_stores_for_station_unknown_raises():
    """未知挂点应抛出 KeyError。"""
    model = build_mirage2000_mount_model()
    with pytest.raises(KeyError):
        stores_for_station(model, 'NO_SUCH_STATION')


def test_station_store_allowed_targeting_pod_only_pylon_6():
    """光电瞄准吊舱仅允许挂在 Pylon 6。"""
    model = build_mirage2000_mount_model()
    pods = {'atlis_ii', 'pdlct', 'damocles'}
    p6 = {item['id'] for item in stores_for_station(model, '6')}
    assert pods <= p6
    for pod_id in pods:
        assert station_store_allowed(model, '6', pod_id)
        assert not station_store_allowed(model, '4', pod_id)
        assert not station_store_allowed(model, '5', pod_id)


def test_inner_wing_mica_and_surface_strike():
    """机翼内侧挂点含 MICA 与 Brimstone / BLG 66 / Mk 82。"""
    model = build_mirage2000_mount_model()
    for sid in ('3', '7'):
        ids = {item['id'] for item in stores_for_station(model, sid)}
        assert {'mica_em', 'mica_ir', 'brimstone', 'blg66', 'mk82'} <= ids
        assert 'magic_ii' not in ids
        assert 'atlis_ii' not in ids


def test_build_mirage2000_mount_catalog_payload_structure():
    """catalog 载荷应含类别、挂点与按挂点分组的武器表。"""
    payload = build_mirage2000_mount_catalog_payload()
    assert payload['aircraft_ids'] == ['Mirage-2000']
    assert 'air_to_air' in payload['categories']
    assert payload['categories']['laser_designation']['label_zh'] == '激光制导/瞄准吊舱'
    assert len(payload['stations']) == 9
    assert '5' in payload['stores_by_station']
    assert payload['stations_csv'] == 'data/mirage2000_mount_stations.csv'
    assert payload['stores_csv'] == 'data/mirage2000_mount_stores.csv'


def test_mirage2000_mount_csv_files_exist():
    """数据文件路径有效。"""
    assert MIRAGE2000_MOUNT_STATIONS_CSV.is_file()
    assert MIRAGE2000_MOUNT_STORES_CSV.is_file()
