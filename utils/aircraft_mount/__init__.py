"""战机挂载模型（挂点与武器兼容表）。"""

from utils.aircraft_mount.rafale_mount import (
    RAFALE_MOUNT_AIRCRAFT_IDS,
    RAFALE_MOUNT_CATEGORIES,
    build_rafale_mount_catalog_payload,
    build_rafale_mount_model,
    load_rafale_mount_stations,
    load_rafale_mount_stores,
    station_store_allowed,
    stores_for_station,
)

__all__ = [
    'RAFALE_MOUNT_AIRCRAFT_IDS',
    'RAFALE_MOUNT_CATEGORIES',
    'build_rafale_mount_catalog_payload',
    'build_rafale_mount_model',
    'load_rafale_mount_stations',
    'load_rafale_mount_stores',
    'station_store_allowed',
    'stores_for_station',
]
