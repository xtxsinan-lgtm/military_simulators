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
BASELINE_JSON = DATA_DIR / 'baseline_before.json'
TAKEOFF_CONFIG_JSON = DATA_DIR / 'takeoff_config.json'
MISSILE_INTERCEPTION_CONFIG_JSON = DATA_DIR / 'missile_interception_config.json'
# 作战半径与起飞共用同一机型库；起飞加载器只取 carrier=1
COMBAT_RADIUS_AIRCRAFT_CSV = AIRCRAFT_CSV
COMBAT_RADIUS_ENGINE_CSV = DATA_DIR / 'aircraft_engine_database.csv'
COMBAT_RADIUS_CONFIG_JSON = DATA_DIR / 'combat_radius_config.json'
COMBAT_RADIUS_RESULTS_JSON = DATA_DIR / 'combat_radius_results.json'
SURVEY_RESULTS_TXT = OUTPUT_DIR / 'carrier_takeoff_survey_results.txt'
