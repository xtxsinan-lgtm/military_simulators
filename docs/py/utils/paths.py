"""项目根目录与数据文件路径。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / 'data'
OUTPUT_DIR = ROOT / 'output'

AIRCRAFT_CSV = DATA_DIR / 'aircraft_database.csv'
CARRIERS_CSV = DATA_DIR / 'carriers_database.csv'
# 饱和打击：导弹库（反舰弹 / 防空弹）与雷达库（预警机 / 舰载雷达）分表
MISSILE_INTERCEPTION_MISSILE_CSV = DATA_DIR / 'missile_interception_missile_database.csv'
MISSILE_INTERCEPTION_RADAR_CSV = DATA_DIR / 'missile_interception_radar_database.csv'
MISSILE_RANGE_PRESET_CSV = DATA_DIR / 'missile_range_preset_database.csv'
BASELINE_JSON = DATA_DIR / 'baseline_before.json'
TAKEOFF_CONFIG_JSON = DATA_DIR / 'takeoff_config.json'
MISSILE_INTERCEPTION_CONFIG_JSON = DATA_DIR / 'missile_interception_config.json'
# 作战半径与起飞共用同一机型库；起飞加载器只取填写了 mtow_kg 的机型
COMBAT_RADIUS_AIRCRAFT_CSV = AIRCRAFT_CSV
COMBAT_RADIUS_ENGINE_CSV = DATA_DIR / 'aircraft_engine_database.csv'
COMBAT_RADIUS_CONFIG_JSON = DATA_DIR / 'combat_radius_config.json'
COMBAT_RADIUS_RESULTS_JSON = DATA_DIR / 'combat_radius_results.json'
# 作战半径挂点挂载（munitions + stations JSON）
MUNITIONS_CSV = DATA_DIR / 'munitions_database.csv'
AIRCRAFT_STATIONS_JSON = DATA_DIR / 'aircraft_stations_database.json'
# F-14 外挂 catalog（store_types / layouts / 紧凑预设）
STORE_TYPES_CSV = DATA_DIR / 'store_types.csv'
AIRCRAFT_STORE_LAYOUTS_CSV = DATA_DIR / 'aircraft_store_layouts.csv'
AIRCRAFT_STORE_PRESETS_CSV = DATA_DIR / 'aircraft_store_presets.csv'
# F-16 外挂 catalog（store_catalog / station / 逐站预设行）
AIRCRAFT_STORE_CATALOG_CSV = DATA_DIR / 'aircraft_store_catalog.csv'
AIRCRAFT_STATION_CSV = DATA_DIR / 'aircraft_station_database.csv'
AIRCRAFT_LOADOUT_PRESETS_CSV = DATA_DIR / 'aircraft_loadout_presets.csv'
# MiG-29 MRCA 外挂挂点
STORES_DATABASE_CSV = DATA_DIR / 'stores_database.csv'
AIRCRAFT_STATIONS_CSV = DATA_DIR / 'aircraft_stations.csv'
AIRCRAFT_STORE_LIMITS_CSV = DATA_DIR / 'aircraft_store_limits.csv'
AIRCRAFT_PYLON_CSV = DATA_DIR / 'aircraft_pylon_database.csv'
RAFALE_MOUNT_STATIONS_CSV = DATA_DIR / 'rafale_mount_stations.csv'
RAFALE_MOUNT_STORES_CSV = DATA_DIR / 'rafale_mount_stores.csv'
AIRCRAFT_WEAPON_STATIONS_CSV = DATA_DIR / 'aircraft_weapon_stations.csv'
AIRCRAFT_WEAPON_CONFIG_JSON = DATA_DIR / 'aircraft_weapon_config.json'
# JF-17/FC-1 外挂兼容库（store_id 列，与 F-16 catalog 分列）
FC1_STORE_CATALOG_CSV = DATA_DIR / 'fc1_store_catalog.csv'
FC1_STORE_MOUNTS_CSV = DATA_DIR / 'aircraft_store_mounts.csv'
AIRCRAFT_STORES_CSV = DATA_DIR / 'aircraft_stores_database.csv'
AIRCRAFT_HARDPOINTS_CSV = DATA_DIR / 'aircraft_hardpoints_database.csv'
AIRCRAFT_FIXED_EQUIPMENT_CSV = DATA_DIR / 'aircraft_fixed_equipment_database.csv'
SURVEY_RESULTS_TXT = OUTPUT_DIR / 'carrier_takeoff_survey_results.txt'
