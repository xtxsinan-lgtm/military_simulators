#!/usr/bin/env python3
"""构建 GitHub Pages 静态资源：data.json + 打包 Python 仿真模块。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / 'docs'
PY_DEST = DOCS / 'py'

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Pyodide 按依赖顺序加载（路径相对项目根）
# missile_interception_presets 依赖 paths + database_csv（CSV 在浏览器中不存在时返回空分组）
# 导弹射程预设 CSV 写入 py_sources，供 Pyodide 在 /py/data/ 下读取
PY_LOAD_ORDER = [
    'utils/__init__.py',
    'utils/radar_horizon.py',
    'utils/paths.py',
    'utils/takeoff/__init__.py',
    'utils/takeoff/takeoff_config.py',
    'utils/takeoff/takeoff_input.py',
    'utils/missile_interception/__init__.py',
    'utils/missile_interception/missile_interception_config.py',
    'utils/database_csv.py',
    'utils/takeoff/takeoff_physics.py',
    'utils/takeoff/ski_jump_geometry.py',
    'utils/takeoff/trajectory.py',
    'utils/takeoff/sim_config.py',
    'utils/takeoff/search_utils.py',
    'utils/takeoff/deck_config.py',
    'utils/takeoff/exhaust_plume.py',
    'utils/takeoff/propeller_thrust.py',
    'utils/takeoff/tiltrotor_aero.py',
    'utils/specs.py',
    'utils/missile_interception/missile_interception_presets.py',
    'utils/missile_interception/missile_interception_radar.py',
    'utils/missile_interception/missile_interception_windows.py',
    'utils/missile_interception/missile_interception_monte_carlo.py',
    'utils/missile_interception/missile_interception_display.py',
    'utils/combat_radius/__init__.py',
    'utils/combat_radius/combat_radius_config.py',
    'utils/combat_radius/lift_drag.py',
    'utils/combat_radius/military_thrust.py',
    'utils/combat_radius/engine_efficiency.py',
    'utils/combat_radius/prop_engine_efficiency.py',
    'utils/combat_radius/propulsion.py',
    'utils/combat_radius/cruise_load.py',
    'utils/combat_radius/loadout.py',
    'utils/combat_radius/breguet.py',
    'utils/combat_radius/flight_profile.py',
    'utils/combat_radius/cruise_search.py',
    'utils/combat_radius/max_speed_search.py',
    'utils/combat_radius/combat_radius_presets.py',
    'simulators/__init__.py',
    'simulators/takeoff/__init__.py',
    'simulators/takeoff/short_take_off.py',
    'simulators/takeoff/short_ski_jump_take_off.py',
    'simulators/takeoff/ski_jump_take_off.py',
    'simulators/takeoff/tiltrotor_short_take_off.py',
    'simulators/missile_interception/__init__.py',
    'simulators/missile_interception/missile_interception_strike.py',
    'simulators/combat_radius/__init__.py',
    'simulators/combat_radius/combat_radius.py',
    'utils/missile_range/__init__.py',
    'utils/missile_range/estimate.py',
    'utils/missile_range/classes.py',
    'utils/missile_range/dataset.py',
    'simulators/missile_range/__init__.py',
    'simulators/missile_range/missile_range.py',
    'apps/__init__.py',
    'apps/web_simulator.py',
    'apps/missile_interception_strike_web.py',
    'apps/combat_radius_web.py',
    'apps/missile_range_web.py',
]

PY_IMPORT_ORDER = [
    'utils.radar_horizon',
    'utils.paths',
    'utils.takeoff.takeoff_config',
    'utils.takeoff.takeoff_input',
    'utils.missile_interception.missile_interception_config',
    'utils.database_csv',
    'utils.takeoff.takeoff_physics',
    'utils.takeoff.ski_jump_geometry',
    'utils.takeoff.trajectory',
    'utils.takeoff.sim_config',
    'utils.takeoff.search_utils',
    'utils.takeoff.deck_config',
    'utils.takeoff.exhaust_plume',
    'utils.takeoff.propeller_thrust',
    'utils.takeoff.tiltrotor_aero',
    'utils.specs',
    'utils.missile_interception.missile_interception_presets',
    'utils.missile_interception.missile_interception_radar',
    'utils.missile_interception.missile_interception_windows',
    'utils.missile_interception.missile_interception_monte_carlo',
    'utils.missile_interception.missile_interception_display',
    'utils.combat_radius.combat_radius_config',
    'utils.combat_radius.lift_drag',
    'utils.combat_radius.military_thrust',
    'utils.combat_radius.engine_efficiency',
    'utils.combat_radius.prop_engine_efficiency',
    'utils.combat_radius.propulsion',
    'utils.combat_radius.cruise_load',
    'utils.combat_radius.loadout',
    'utils.combat_radius.breguet',
    'utils.combat_radius.flight_profile',
    'utils.combat_radius.cruise_search',
    'utils.combat_radius.max_speed_search',
    'utils.combat_radius.combat_radius_presets',
    'simulators.takeoff.short_take_off',
    'simulators.takeoff.short_ski_jump_take_off',
    'simulators.takeoff.ski_jump_take_off',
    'simulators.takeoff.tiltrotor_short_take_off',
    'simulators.missile_interception.missile_interception_strike',
    'simulators.combat_radius.combat_radius',
    'utils.missile_range.estimate',
    'utils.missile_range.classes',
    'utils.missile_range.dataset',
    'simulators.missile_range.missile_range',
    'apps.web_simulator',
    'apps.missile_interception_strike_web',
    'apps.combat_radius_web',
    'apps.missile_range_web',
]

# 起飞页 / iOS 本地引擎初始化时不应 import 其它仿真（各自有独立页或按需加载）
_TAKEOFF_IMPORT_SKIP = ('missile_interception', 'missile_range', 'combat_radius', 'database_csv')


def build_py_takeoff_import_order() -> list[str]:
    """从全量 import 表剔除其它仿真依赖，避免 Pyodide 读不到对应 JSON。"""
    return [name for name in PY_IMPORT_ORDER if not any(skip in name for skip in _TAKEOFF_IMPORT_SKIP)]


PY_TAKEOFF_IMPORT_ORDER = build_py_takeoff_import_order()

# 非 Python 数据文件：写入虚拟文件系统，不参与 import
PY_DATA_FILES = (
    'data/missile_range_preset_database.csv',
    'data/munitions_database.csv',
    'data/aircraft_stations_database.json',
    'data/aircraft_pylon_database.csv',
    'data/rafale_mount_stations.csv',
    'data/rafale_mount_stores.csv',
    'data/mirage2000_mount_stations.csv',
    'data/mirage2000_mount_stores.csv',
    'data/j10c_mount_stations.csv',
    'data/j10c_mount_stores.csv',
    'data/j15_mount_stations.csv',
    'data/j15_mount_stores.csv',
)


def collect_py_sources() -> dict[str, str]:
    """打包仿真 Python 与射程预设 CSV。"""
    sources: dict[str, str] = {}
    for rel in list(PY_LOAD_ORDER) + list(PY_DATA_FILES):
        src = ROOT / rel
        if not src.is_file():
            raise FileNotFoundError(src)
        sources[rel] = src.read_text(encoding='utf-8')
    return sources


def main() -> None:
    from scripts.frontend_catalog import build_catalog_payload
    from utils.database_csv import load_aircraft_csv, load_carriers_csv
    from utils.paths import AIRCRAFT_CSV, CARRIERS_CSV

    DOCS.mkdir(exist_ok=True)
    PY_DEST.mkdir(parents=True, exist_ok=True)

    aircraft = load_aircraft_csv(AIRCRAFT_CSV)
    carriers = load_carriers_csv(CARRIERS_CSV)

    py_sources = collect_py_sources()
    for rel, text in py_sources.items():
        dest = PY_DEST / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding='utf-8')

    data = build_catalog_payload(aircraft, carriers)
    data['py_load_order'] = PY_LOAD_ORDER
    data['py_import_order'] = PY_IMPORT_ORDER
    data['py_takeoff_import_order'] = list(PY_TAKEOFF_IMPORT_ORDER)
    data['py_data_files'] = list(PY_DATA_FILES)
    data['py_sources'] = py_sources

    (DOCS / 'data.json').write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

    print(f'Wrote {DOCS / "data.json"}')
    print(f'Copied {len(PY_LOAD_ORDER)} Python modules under {PY_DEST}/')


if __name__ == '__main__':
    main()
