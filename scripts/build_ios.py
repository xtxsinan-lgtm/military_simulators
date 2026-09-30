#!/usr/bin/env python3
"""构建 iOS App 静态数据：catalog + 嵌入式 Python 源码（供本地 Pyodide）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IOS_RESOURCES = ROOT / 'ios' / 'CarrierTakeOff' / 'Resources'

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def build_ios_data() -> dict:
    """从 CSV 生成目录，并嵌入与 Web 相同的 py_sources 供本地仿真。"""
    from scripts.build_docs import PY_DATA_FILES, PY_IMPORT_ORDER, PY_LOAD_ORDER, collect_py_sources
    from scripts.frontend_catalog import build_catalog_payload
    from utils.database_csv import load_aircraft_csv, load_carriers_csv
    from utils.paths import AIRCRAFT_CSV, CARRIERS_CSV

    aircraft = load_aircraft_csv(AIRCRAFT_CSV)
    carriers = load_carriers_csv(CARRIERS_CSV)
    data = build_catalog_payload(aircraft, carriers)

    py_sources = collect_py_sources()
    data['py_load_order'] = list(PY_LOAD_ORDER)
    data['py_import_order'] = list(PY_IMPORT_ORDER)
    data['py_data_files'] = list(PY_DATA_FILES)
    data['py_sources'] = py_sources
    return data


def _ensure_engine_assets() -> None:
    """确认本地 Pyodide 桥接页存在于 Resources。"""
    for name in ('engine.html', 'engine.js'):
        path = IOS_RESOURCES / name
        if not path.is_file():
            raise FileNotFoundError(f'缺少 {path}，请保留 ios/.../Resources/{name}')


def main() -> None:
    """写入 iOS Bundle 用 data.json（含 py_sources）。"""
    IOS_RESOURCES.mkdir(parents=True, exist_ok=True)
    _ensure_engine_assets()
    data = build_ios_data()
    path = IOS_RESOURCES / 'data.json'
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Wrote {path} (py_sources={len(data["py_sources"])})')


if __name__ == '__main__':
    main()
