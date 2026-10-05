"""战机挂载模型（挂点与武器兼容表）。"""

from utils.aircraft_mount.categories import (
    MIRAGE2000_MOUNT_CATEGORIES,
    RAFALE_MOUNT_CATEGORIES,
)
from utils.aircraft_mount.mirage2000_mount import (
    MIRAGE2000_MOUNT_AIRCRAFT_IDS,
    build_mirage2000_mount_catalog_payload,
    build_mirage2000_mount_model,
    load_mirage2000_mount_stations,
    load_mirage2000_mount_stores,
    station_store_allowed as mirage2000_station_store_allowed,
    stores_for_station as mirage2000_stores_for_station,
)
from utils.aircraft_mount.rafale_mount import (
    RAFALE_MOUNT_AIRCRAFT_IDS,
    build_rafale_mount_catalog_payload,
    build_rafale_mount_model,
    load_rafale_mount_stations,
    load_rafale_mount_stores,
    station_store_allowed,
    stores_for_station,
)

__all__ = [
    'MIRAGE2000_MOUNT_AIRCRAFT_IDS',
    'MIRAGE2000_MOUNT_CATEGORIES',
    'RAFALE_MOUNT_AIRCRAFT_IDS',
    'RAFALE_MOUNT_CATEGORIES',
    'build_mirage2000_mount_catalog_payload',
    'build_mirage2000_mount_model',
    'build_rafale_mount_catalog_payload',
    'build_rafale_mount_model',
    'load_mirage2000_mount_stations',
    'load_mirage2000_mount_stores',
    'load_rafale_mount_stations',
    'load_rafale_mount_stores',
    'mirage2000_station_store_allowed',
    'mirage2000_stores_for_station',
    'station_store_allowed',
    'stores_for_station',
]
