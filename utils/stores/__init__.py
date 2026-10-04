"""飞机外挂/挂点模型：多数据源 catalog 与挂载校验。"""

from utils.stores.loadout import (
    LoadoutItem,
    LoadoutPreset,
    effective_n_stores,
    loadout_drag_weight,
    loadout_total_mass_kg,
    parse_loadout_string,
)
from utils.stores.store_catalog import (
    StoreStation,
    StoreType,
    build_store_catalog_payload,
    load_aircraft_loadout_presets_csv,
    load_aircraft_store_layouts_csv,
    load_store_types_csv,
)
from utils.stores.stores_config import (
    build_aircraft_stores_payload as build_mrca_stores_payload,
    load_aircraft_stations,
    load_aircraft_store_limits,
    load_stores_database,
    loadout_mass_kg as mrca_loadout_mass_kg,
    station_allowed,
    store_count_ok,
    validate_loadout as validate_mrca_loadout,
)
from utils.stores.hardpoints import (
    build_stores_catalog_payload,
    load_aircraft_hardpoint_stores_csv,
    load_aircraft_hardpoints_csv as load_fa50_hardpoints_csv,
    load_loadout_presets_csv,
    load_stores_csv,
    loadout_mass_kg,
    validate_loadout as validate_fa50_loadout,
)


def build_combined_aircraft_stores_payload() -> dict:
    """合并 F-14 store_catalog 与 MiG-29 MRCA stores 目录（键空间不重叠）。"""
    payload = build_store_catalog_payload()
    payload.update(build_mrca_stores_payload())
    return payload


__all__ = [
    'StoreStation',
    'StoreType',
    'LoadoutItem',
    'LoadoutPreset',
    'build_combined_aircraft_stores_payload',
    'build_mrca_stores_payload',
    'build_store_catalog_payload',
    'build_stores_catalog_payload',
    'load_aircraft_loadout_presets_csv',
    'load_aircraft_store_layouts_csv',
    'load_aircraft_stations',
    'load_aircraft_store_limits',
    'load_store_types_csv',
    'load_stores_database',
    'load_fa50_hardpoints_csv',
    'load_aircraft_hardpoint_stores_csv',
    'load_loadout_presets_csv',
    'load_stores_csv',
    'mrca_loadout_mass_kg',
    'loadout_mass_kg',
    'parse_loadout_string',
    'station_allowed',
    'store_count_ok',
    'validate_mrca_loadout',
    'validate_fa50_loadout',
    'loadout_total_mass_kg',
    'loadout_drag_weight',
    'effective_n_stores',
]
