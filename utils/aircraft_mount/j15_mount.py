"""歼-15 / 歼-15T 12 挂点与武器兼容模型。"""
from __future__ import annotations

from typing import Any

from utils.aircraft_mount.categories import J15_MOUNT_CATEGORIES
from utils.database_csv import (
    load_j15_mount_stations_csv,
    load_j15_mount_stores_csv,
)
from utils.paths import J15_MOUNT_STATIONS_CSV, J15_MOUNT_STORES_CSV

# 适用机型（歼-15 无 PL-10/PL-15/鹰击-15，其余参照歼-15T）
J15_MOUNT_AIRCRAFT_IDS = ('J-15', 'J-15T')


def load_j15_mount_stations(path: str | None = None) -> list[dict[str, Any]]:
    """加载歼-15 系列挂点定义。"""
    return load_j15_mount_stations_csv(path)


def load_j15_mount_stores(path: str | None = None) -> list[dict[str, Any]]:
    """加载歼-15 系列挂点-武器兼容表。"""
    return load_j15_mount_stores_csv(path)


def build_j15_mount_model(
    aircraft_id: str,
    stations_path: str | None = None,
    stores_path: str | None = None,
) -> dict[str, Any]:
    """合并指定机型的挂点与兼容表，生成按挂点索引的挂载模型。"""
    if aircraft_id not in J15_MOUNT_AIRCRAFT_IDS:
        raise KeyError(f'未知机型 {aircraft_id!r}')
    stations = [
        s for s in load_j15_mount_stations(stations_path)
        if s['aircraft_id'] == aircraft_id
    ]
    stores = [
        s for s in load_j15_mount_stores(stores_path)
        if s['aircraft_id'] == aircraft_id
    ]
    station_order = [item['station_id'] for item in stations]
    station_ids = set(station_order)
    if len(station_order) != len(station_ids):
        raise ValueError('挂点 station_id 重复')
    stores_by_station: dict[str, list[dict[str, str]]] = {
        sid: [] for sid in station_order
    }
    for row in stores:
        sid = row['station_id']
        if sid not in station_ids:
            raise ValueError(f'兼容表引用未知挂点 {sid!r}')
        stores_by_station[sid].append({
            'id': row['store_id'],
            'name': row['store_name'],
            'category': row['category'],
        })
    for sid, items in stores_by_station.items():
        if not items:
            raise ValueError(f'挂点 {sid} 无可用武器/设备')
    return {
        'aircraft_ids': [aircraft_id],
        'stations': stations,
        'stores_by_station': stores_by_station,
    }


def stores_for_station(
    model: dict[str, Any],
    station_id: str,
) -> list[dict[str, str]]:
    """返回指定挂点可挂载的武器/设备列表。"""
    stores = model.get('stores_by_station', {})
    if station_id not in stores:
        raise KeyError(f'未知挂点 {station_id!r}')
    return list(stores[station_id])


def station_store_allowed(
    model: dict[str, Any],
    station_id: str,
    store_id: str,
) -> bool:
    """判断某挂点是否允许挂载指定武器/设备。"""
    return any(item['id'] == store_id for item in stores_for_station(model, station_id))


def build_j15_mount_catalog_payload(
    stations_path: str | None = None,
    stores_path: str | None = None,
) -> dict[str, Any]:
    """构建前端 catalog 用的歼-15 系列挂载模型 JSON。"""
    models = {
        aid: build_j15_mount_model(aid, stations_path, stores_path)
        for aid in J15_MOUNT_AIRCRAFT_IDS
    }
    return {
        'aircraft_ids': list(J15_MOUNT_AIRCRAFT_IDS),
        'categories': {
            key: dict(value) for key, value in J15_MOUNT_CATEGORIES.items()
        },
        'models': {
            aid: {
                'stations': m['stations'],
                'stores_by_station': m['stores_by_station'],
            }
            for aid, m in models.items()
        },
        'stations_csv': str(
            J15_MOUNT_STATIONS_CSV.relative_to(J15_MOUNT_STATIONS_CSV.parent.parent)
        ),
        'stores_csv': str(
            J15_MOUNT_STORES_CSV.relative_to(J15_MOUNT_STORES_CSV.parent.parent)
        ),
    }
