"""战斗机外挂/挂点载荷目录。"""

from utils.weapon_loadout.su30_stores import (
    SU30_AIRCRAFT_ID,
    SU30_EXTERNAL_STATION_COUNT,
    aircraft_weapon_max_count,
    build_su30_stores_payload,
    station_weapon_max_qty,
    validate_su30_loadout,
)
from utils.weapon_loadout.typhoon_stores import (
    build_typhoon_stores_payload,
    build_weapon_loadout_catalog_payload,
)

__all__ = [
    'SU30_AIRCRAFT_ID',
    'SU30_EXTERNAL_STATION_COUNT',
    'aircraft_weapon_max_count',
    'build_su30_stores_payload',
    'build_typhoon_stores_payload',
    'build_weapon_loadout_catalog_payload',
    'station_weapon_max_qty',
    'validate_su30_loadout',
]
