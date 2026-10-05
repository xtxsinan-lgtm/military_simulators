"""外挂弹药库、挂点与挂载方案加载与校验。"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from utils.paths import (
    AIRCRAFT_HARDPOINT_STORES_CSV,
    AIRCRAFT_HARDPOINTS_CSV,
    LOADOUT_PRESETS_CSV,
    STORES_CSV,
)

STORES_CSV_COLUMNS = ('id', 'name', 'category', 'mass_kg', 'notes')
HARDPOINTS_CSV_COLUMNS = (
    'aircraft_id', 'station_id', 'name', 'position_order',
    'max_mass_lb', 'max_mass_kg', 'load_factor_g', 'notes',
)
HARDPOINT_STORES_CSV_COLUMNS = ('aircraft_id', 'station_id', 'store_id', 'max_count')
LOADOUT_PRESETS_CSV_COLUMNS = (
    'aircraft_id', 'preset_id', 'name', 'station_id', 'store_id', 'count', 'notes',
)

STORE_CATEGORIES = ('aam', 'agm', 'bomb', 'dispenser', 'rocket', 'fuel_tank', 'target', 'pod')


def lb_to_kg(lb: float) -> float:
    """磅 → 千克（精确换算）。"""
    return lb * 0.45359237


def _read_csv_rows(path: Path, required_columns: tuple[str, ...]) -> list[dict[str, str]]:
    """读取 CSV 并校验表头。"""
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f'{path} 缺少表头')
        missing = [c for c in required_columns if c not in reader.fieldnames]
        if missing:
            raise ValueError(f'{path} 缺少列: {missing}')
        return list(reader)


def load_stores_csv(path: str | Path | None = None) -> dict[str, dict[str, Any]]:
    """加载外挂弹药/装备库；返回 store_id → 记录。"""
    csv_path = Path(path) if path is not None else STORES_CSV
    stores: dict[str, dict[str, Any]] = {}
    for row in _read_csv_rows(csv_path, STORES_CSV_COLUMNS):
        store_id = (row.get('id') or '').strip()
        if not store_id:
            continue
        category = (row.get('category') or '').strip()
        if category not in STORE_CATEGORIES:
            raise ValueError(f'{csv_path} 记录 {store_id} 未知 category={category!r}')
        mass = float((row.get('mass_kg') or '').strip())
        if mass <= 0:
            raise ValueError(f'{csv_path} 记录 {store_id} mass_kg 须 > 0')
        stores[store_id] = {
            'id': store_id,
            'name': (row.get('name') or '').strip(),
            'category': category,
            'mass_kg': mass,
            'notes': (row.get('notes') or '').strip(),
        }
    return stores


def load_aircraft_hardpoints_csv(path: str | Path | None = None) -> dict[str, list[dict[str, Any]]]:
    """加载机型挂点表；返回 aircraft_id → 挂点列表（按 position_order 排序）。"""
    csv_path = Path(path) if path is not None else AIRCRAFT_HARDPOINTS_CSV
    by_aircraft: dict[str, list[dict[str, Any]]] = {}
    for row in _read_csv_rows(csv_path, HARDPOINTS_CSV_COLUMNS):
        aircraft_id = (row.get('aircraft_id') or '').strip()
        station_id = (row.get('station_id') or '').strip()
        if not aircraft_id or not station_id:
            continue
        max_lb = float((row.get('max_mass_lb') or '').strip())
        max_kg = float((row.get('max_mass_kg') or '').strip())
        if abs(max_kg - lb_to_kg(max_lb)) > 0.15:
            raise ValueError(
                f'{csv_path} 记录 {aircraft_id}/{station_id} '
                f'max_mass_kg={max_kg} 与 max_mass_lb={max_lb} 不一致'
            )
        item = {
            'aircraft_id': aircraft_id,
            'station_id': station_id,
            'name': (row.get('name') or '').strip(),
            'position_order': int((row.get('position_order') or '').strip()),
            'max_mass_lb': max_lb,
            'max_mass_kg': max_kg,
            'load_factor_g': float((row.get('load_factor_g') or '').strip()),
            'notes': (row.get('notes') or '').strip(),
        }
        by_aircraft.setdefault(aircraft_id, []).append(item)
    for stations in by_aircraft.values():
        stations.sort(key=lambda x: x['position_order'])
    return by_aircraft


def load_aircraft_hardpoint_stores_csv(
    path: str | Path | None = None,
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """加载挂点可用弹药表；返回 aircraft_id → station_id → 允许列表。"""
    csv_path = Path(path) if path is not None else AIRCRAFT_HARDPOINT_STORES_CSV
    result: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for row in _read_csv_rows(csv_path, HARDPOINT_STORES_CSV_COLUMNS):
        aircraft_id = (row.get('aircraft_id') or '').strip()
        station_id = (row.get('station_id') or '').strip()
        store_id = (row.get('store_id') or '').strip()
        if not aircraft_id or not station_id or not store_id:
            continue
        max_count = int((row.get('max_count') or '').strip())
        if max_count <= 0:
            raise ValueError(
                f'{csv_path} 记录 {aircraft_id}/{station_id}/{store_id} max_count 须 > 0'
            )
        entry = {'store_id': store_id, 'max_count': max_count}
        result.setdefault(aircraft_id, {}).setdefault(station_id, []).append(entry)
    return result


def load_loadout_presets_csv(path: str | Path | None = None) -> dict[str, list[dict[str, Any]]]:
    """加载挂载方案预设；返回 aircraft_id → 预设列表。"""
    csv_path = Path(path) if path is not None else LOADOUT_PRESETS_CSV
    grouped: dict[str, dict[str, dict[str, Any]]] = {}
    for row in _read_csv_rows(csv_path, LOADOUT_PRESETS_CSV_COLUMNS):
        aircraft_id = (row.get('aircraft_id') or '').strip()
        preset_id = (row.get('preset_id') or '').strip()
        station_id = (row.get('station_id') or '').strip()
        store_id = (row.get('store_id') or '').strip()
        if not aircraft_id or not preset_id or not station_id or not store_id:
            continue
        count = int((row.get('count') or '').strip())
        if count <= 0:
            raise ValueError(f'{csv_path} 预设 {preset_id} 的 count 须 > 0')
        key = (aircraft_id, preset_id)
        if key not in grouped:
            grouped[key] = {
                'id': preset_id,
                'name': (row.get('name') or '').strip(),
                'aircraft_id': aircraft_id,
                'notes': (row.get('notes') or '').strip(),
                'stations': [],
            }
        preset = grouped[key]
        if preset['name'] != (row.get('name') or '').strip():
            raise ValueError(f'{csv_path} 预设 {preset_id} 名称不一致')
        preset['stations'].append({
            'station_id': station_id,
            'store_id': store_id,
            'count': count,
        })
    by_aircraft: dict[str, list[dict[str, Any]]] = {}
    for (aircraft_id, _), preset in grouped.items():
        by_aircraft.setdefault(aircraft_id, []).append(preset)
    for presets in by_aircraft.values():
        presets.sort(key=lambda x: x['id'])
    return by_aircraft


def _station_lookup(aircraft_id: str, hardpoints: dict[str, list[dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    """机型挂点 id → 记录。"""
    stations = hardpoints.get(aircraft_id, [])
    return {s['station_id']: s for s in stations}


def _allowed_store_map(
    aircraft_id: str,
    hardpoint_stores: dict[str, dict[str, list[dict[str, Any]]]],
) -> dict[str, dict[str, int]]:
    """station_id → store_id → max_count。"""
    station_map = hardpoint_stores.get(aircraft_id, {})
    return {
        station_id: {item['store_id']: item['max_count'] for item in items}
        for station_id, items in station_map.items()
    }


def loadout_mass_kg(
    loadout: dict[str, list[tuple[str, int]]],
    stores: dict[str, dict[str, Any]],
) -> float:
    """计算挂载总重：loadout 为 station_id → [(store_id, count), ...]。"""
    total = 0.0
    for items in loadout.values():
        for store_id, count in items:
            if store_id not in stores:
                raise ValueError(f'未知弹药 {store_id!r}')
            if count <= 0:
                raise ValueError(f'弹药 {store_id!r} count 须 > 0')
            total += stores[store_id]['mass_kg'] * count
    return total


def validate_loadout(
    aircraft_id: str,
    loadout: dict[str, list[tuple[str, int]]],
    *,
    stores: dict[str, dict[str, Any]] | None = None,
    hardpoints: dict[str, list[dict[str, Any]]] | None = None,
    hardpoint_stores: dict[str, dict[str, list[dict[str, Any]]]] | None = None,
) -> list[str]:
    """校验挂载方案；返回错误信息列表（空表示通过）。"""
    stores = stores if stores is not None else load_stores_csv()
    hardpoints = hardpoints if hardpoints is not None else load_aircraft_hardpoints_csv()
    hardpoint_stores = (
        hardpoint_stores if hardpoint_stores is not None else load_aircraft_hardpoint_stores_csv()
    )
    station_by_id = _station_lookup(aircraft_id, hardpoints)
    allowed = _allowed_store_map(aircraft_id, hardpoint_stores)
    errors: list[str] = []

    if aircraft_id not in hardpoints:
        return [f'机型 {aircraft_id!r} 无挂点定义']

    for station_id, items in loadout.items():
        if station_id not in station_by_id:
            errors.append(f'未知挂点 {station_id!r}')
            continue
        station = station_by_id[station_id]
        station_allowed = allowed.get(station_id, {})
        station_mass = 0.0
        for store_id, count in items:
            if store_id not in stores:
                errors.append(f'挂点 {station_id}：未知弹药 {store_id!r}')
                continue
            if store_id not in station_allowed:
                errors.append(f'挂点 {station_id}：不允许挂载 {store_id!r}')
                continue
            if count > station_allowed[store_id]:
                errors.append(
                    f'挂点 {station_id}：{store_id} 数量 {count} 超过上限 {station_allowed[store_id]}'
                )
            station_mass += stores[store_id]['mass_kg'] * count
        if station_mass > station['max_mass_kg'] + 1e-6:
            errors.append(
                f'挂点 {station_id}：总重 {station_mass:.1f} kg 超过上限 {station["max_mass_kg"]:.1f} kg'
            )

    return errors


def preset_to_loadout(preset: dict[str, Any]) -> dict[str, list[tuple[str, int]]]:
    """预设 stations 列表 → loadout 字典。"""
    loadout: dict[str, list[tuple[str, int]]] = {}
    for item in preset.get('stations', []):
        sid = item['station_id']
        loadout.setdefault(sid, []).append((item['store_id'], item['count']))
    return loadout


def build_stores_catalog_payload(
    stores_path: str | Path | None = None,
    hardpoints_path: str | Path | None = None,
    hardpoint_stores_path: str | Path | None = None,
    presets_path: str | Path | None = None,
) -> dict[str, Any]:
    """构建前端/小程序/iOS 共用的外挂与挂点目录。"""
    stores = load_stores_csv(stores_path)
    hardpoints = load_aircraft_hardpoints_csv(hardpoints_path)
    hardpoint_stores = load_aircraft_hardpoint_stores_csv(hardpoint_stores_path)
    presets = load_loadout_presets_csv(presets_path)

    aircraft_ids = sorted(set(hardpoints) | set(presets))
    aircraft_payload: list[dict[str, Any]] = []
    for aid in aircraft_ids:
        station_map = hardpoint_stores.get(aid, {})
        stations: list[dict[str, Any]] = []
        for hp in hardpoints.get(aid, []):
            sid = hp['station_id']
            allowed = station_map.get(sid, [])
            stations.append({
                **hp,
                'allowed_stores': [
                    {
                        'store_id': a['store_id'],
                        'max_count': a['max_count'],
                        'name': stores[a['store_id']]['name'],
                        'category': stores[a['store_id']]['category'],
                        'mass_kg': stores[a['store_id']]['mass_kg'],
                    }
                    for a in allowed
                    if a['store_id'] in stores
                ],
            })
        aircraft_payload.append({
            'aircraft_id': aid,
            'stations': stations,
            'loadout_presets': presets.get(aid, []),
        })

    return {
        'stores': list(stores.values()),
        'aircraft': aircraft_payload,
    }
