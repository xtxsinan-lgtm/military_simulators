"""幻影 2000（Mirage-2000）挂点与武器兼容模型。"""
from __future__ import annotations

from typing import Any

from utils.aircraft_mount.categories import MIRAGE2000_MOUNT_CATEGORIES
from utils.database_csv import (
    load_mirage2000_mount_stations_csv,
    load_mirage2000_mount_stores_csv,
)
from utils.paths import MIRAGE2000_MOUNT_STATIONS_CSV, MIRAGE2000_MOUNT_STORES_CSV

# 适用机型
MIRAGE2000_MOUNT_AIRCRAFT_IDS = ('Mirage-2000',)


def load_mirage2000_mount_stations(
    path: str | None = None,
) -> list[dict[str, Any]]:
    """加载幻影 2000 挂点定义。"""
    return load_mirage2000_mount_stations_csv(path)


def load_mirage2000_mount_stores(
    path: str | None = None,
) -> list[dict[str, Any]]:
    """加载幻影 2000 挂点-武器兼容表。"""
    return load_mirage2000_mount_stores_csv(path)


def build_mirage2000_mount_model(
    stations_path: str | None = None,
    stores_path: str | None = None,
) -> dict[str, Any]:
    """合并挂点与兼容表，生成按挂点索引的挂载模型。"""
    stations = load_mirage2000_mount_stations(stations_path)
    stores = load_mirage2000_mount_stores(stores_path)
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
        'aircraft_ids': list(MIRAGE2000_MOUNT_AIRCRAFT_IDS),
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


def build_mirage2000_mount_catalog_payload(
    stations_path: str | None = None,
    stores_path: str | None = None,
) -> dict[str, Any]:
    """构建前端 catalog 用的幻影 2000 挂载模型 JSON。"""
    model = build_mirage2000_mount_model(stations_path, stores_path)
    return {
        'aircraft_ids': model['aircraft_ids'],
        'categories': {
            key: dict(value) for key, value in MIRAGE2000_MOUNT_CATEGORIES.items()
        },
        'stations': model['stations'],
        'stores_by_station': model['stores_by_station'],
        'stations_csv': str(
            MIRAGE2000_MOUNT_STATIONS_CSV.relative_to(
                MIRAGE2000_MOUNT_STATIONS_CSV.parent.parent
            )
        ),
        'stores_csv': str(
            MIRAGE2000_MOUNT_STORES_CSV.relative_to(
                MIRAGE2000_MOUNT_STORES_CSV.parent.parent
            )
        ),
    }
