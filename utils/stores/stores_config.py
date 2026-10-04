"""战斗机外挂挂点与弹药能力模型（CSV 数据源）。

依据 MiG-29 MRCA STORES CAPABILITY 挂载示意图：
  9 个外部挂点（左翼 4 + 右翼 4 + 机腹中央 1），内置航炮不计外挂质量。
前端经 build_all → data.json 的 aircraft_stores 自动同步。
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from utils.paths import (
    AIRCRAFT_STATIONS_CSV,
    AIRCRAFT_STORE_LIMITS_CSV,
    STORES_DATABASE_CSV,
)

STORES_DATABASE_COLUMNS = (
    'id', 'name', 'category', 'mass_kg', 'length_m', 'diameter_m', 'notes',
)
AIRCRAFT_STATIONS_COLUMNS = (
    'aircraft_id', 'station_id', 'name', 'side', 'position_rank', 'allowed_stores', 'notes',
)
AIRCRAFT_STORE_LIMITS_COLUMNS = (
    'aircraft_id', 'store_id', 'max_count', 'scope', 'notes',
)

# 挂点侧别
STATION_SIDES = ('center', 'left', 'right')

# 弹药类别
STORE_CATEGORIES = (
    'gun', 'aam_bvr', 'aam_wvr', 'aam_mrm', 'agm',
    'bomb_guided', 'bomb_unguided', 'rocket', 'tank', 'pod_optronic', 'ecm',
)


def _parse_float_or_none(raw: str) -> float | None:
    """解析可选浮点；空白返回 None。"""
    text = (raw or '').strip()
    if not text:
        return None
    return float(text)


def _split_semicolon_list(raw: str) -> list[str]:
    """分号分隔列表；去空白、去空项。"""
    return [x.strip() for x in (raw or '').split(';') if x.strip()]


def load_stores_database(path: str | Path | None = None) -> dict[str, dict[str, Any]]:
    """加载弹药/外挂物目录。"""
    csv_path = Path(path) if path is not None else STORES_DATABASE_CSV
    if not csv_path.is_file():
        return {}
    stores: dict[str, dict[str, Any]] = {}
    with csv_path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            store_id = (row.get('id') or '').strip()
            if not store_id:
                continue
            category = (row.get('category') or '').strip()
            if category not in STORE_CATEGORIES:
                raise ValueError(f'{csv_path} 记录 {store_id} 未知类别 {category!r}')
            stores[store_id] = {
                'id': store_id,
                'name': (row.get('name') or '').strip(),
                'category': category,
                'mass_kg': float((row.get('mass_kg') or '0').strip()),
                'length_m': _parse_float_or_none(row.get('length_m') or ''),
                'diameter_m': _parse_float_or_none(row.get('diameter_m') or ''),
                'notes': (row.get('notes') or '').strip(),
            }
    return stores


def load_aircraft_stations(path: str | Path | None = None) -> dict[str, list[dict[str, Any]]]:
    """按机型加载挂点能力表。"""
    csv_path = Path(path) if path is not None else AIRCRAFT_STATIONS_CSV
    if not csv_path.is_file():
        return {}
    by_aircraft: dict[str, list[dict[str, Any]]] = {}
    with csv_path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            ac_id = (row.get('aircraft_id') or '').strip()
            station_id = (row.get('station_id') or '').strip()
            if not ac_id or not station_id:
                continue
            side = (row.get('side') or '').strip()
            if side not in STATION_SIDES:
                raise ValueError(f'{csv_path} 挂点 {station_id} 未知侧别 {side!r}')
            allowed = _split_semicolon_list(row.get('allowed_stores') or '')
            item = {
                'station_id': station_id,
                'name': (row.get('name') or '').strip(),
                'side': side,
                'position_rank': int((row.get('position_rank') or '0').strip()),
                'allowed_stores': allowed,
                'notes': (row.get('notes') or '').strip(),
            }
            by_aircraft.setdefault(ac_id, []).append(item)
    for stations in by_aircraft.values():
        stations.sort(key=lambda s: (s['position_rank'], s['side'], s['station_id']))
    return by_aircraft


def load_aircraft_store_limits(path: str | Path | None = None) -> dict[str, list[dict[str, Any]]]:
    """按机型加载全机弹药数量上限。"""
    csv_path = Path(path) if path is not None else AIRCRAFT_STORE_LIMITS_CSV
    if not csv_path.is_file():
        return {}
    by_aircraft: dict[str, list[dict[str, Any]]] = {}
    with csv_path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            ac_id = (row.get('aircraft_id') or '').strip()
            store_id = (row.get('store_id') or '').strip()
            if not ac_id or not store_id:
                continue
            item = {
                'store_id': store_id,
                'max_count': int((row.get('max_count') or '0').strip()),
                'scope': (row.get('scope') or 'aircraft').strip(),
                'notes': (row.get('notes') or '').strip(),
            }
            by_aircraft.setdefault(ac_id, []).append(item)
    return by_aircraft


def _stations_for_aircraft(aircraft_id: str, stations_map: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """取指定机型的挂点列表；不存在则返回空列表。"""
    return list(stations_map.get(aircraft_id, []))


def station_allowed(
    aircraft_id: str,
    station_id: str,
    store_id: str,
    *,
    stations_map: dict[str, list[dict[str, Any]]] | None = None,
) -> bool:
    """判断某挂点是否允许挂载指定弹药。"""
    stations = stations_map if stations_map is not None else load_aircraft_stations()
    for st in _stations_for_aircraft(aircraft_id, stations):
        if st['station_id'] == station_id:
            return store_id in st['allowed_stores']
    return False


def store_count_ok(
    aircraft_id: str,
    loadout: dict[str, str],
    *,
    limits_map: dict[str, list[dict[str, Any]]] | None = None,
) -> bool:
    """检查挂载方案是否满足全机弹药数量上限。"""
    limits = limits_map if limits_map is not None else load_aircraft_store_limits()
    ac_limits = limits.get(aircraft_id, [])
    if not ac_limits:
        return True
    counts: dict[str, int] = {}
    for store_id in loadout.values():
        if store_id:
            counts[store_id] = counts.get(store_id, 0) + 1
    for rule in ac_limits:
        sid = rule['store_id']
        if counts.get(sid, 0) > rule['max_count']:
            return False
    return True


def validate_loadout(
    aircraft_id: str,
    loadout: dict[str, str],
    *,
    stores: dict[str, dict[str, Any]] | None = None,
    stations_map: dict[str, list[dict[str, Any]]] | None = None,
    limits_map: dict[str, list[dict[str, Any]]] | None = None,
) -> list[str]:
    """校验挂载方案，返回错误信息列表（空列表表示合法）。"""
    errors: list[str] = []
    store_db = stores if stores is not None else load_stores_database()
    stations = stations_map if stations_map is not None else load_aircraft_stations()
    ac_stations = _stations_for_aircraft(aircraft_id, stations)
    if not ac_stations:
        errors.append(f'未知或未配置挂点模型的机型: {aircraft_id}')
        return errors

    valid_station_ids = {st['station_id'] for st in ac_stations}
    for station_id, store_id in loadout.items():
        if station_id not in valid_station_ids:
            errors.append(f'未知挂点: {station_id}')
            continue
        if not store_id:
            continue
        if store_id not in store_db:
            errors.append(f'未知弹药/外挂: {store_id}')
            continue
        if not station_allowed(aircraft_id, station_id, store_id, stations_map=stations):
            errors.append(f'挂点 {station_id} 不允许挂载 {store_id}')

    if not store_count_ok(aircraft_id, loadout, limits_map=limits_map):
        limits = limits_map if limits_map is not None else load_aircraft_store_limits()
        counts: dict[str, int] = {}
        for store_id in loadout.values():
            if store_id:
                counts[store_id] = counts.get(store_id, 0) + 1
        for rule in limits.get(aircraft_id, []):
            sid = rule['store_id']
            n = counts.get(sid, 0)
            if n > rule['max_count']:
                errors.append(
                    f'{sid} 全机最多 {rule["max_count"]} 个，当前 {n} 个'
                )
    return errors


def loadout_mass_kg(
    loadout: dict[str, str],
    *,
    stores: dict[str, dict[str, Any]] | None = None,
) -> float:
    """计算外挂总质量（kg）；空挂点或内置航炮不计入。"""
    store_db = stores if stores is not None else load_stores_database()
    total = 0.0
    for store_id in loadout.values():
        if not store_id:
            continue
        item = store_db.get(store_id)
        if item is None:
            continue
        total += float(item['mass_kg'])
    return total


def _collect_store_ids(stations_map: dict[str, list[dict[str, Any]]]) -> set[str]:
    """从所有挂点能力表收集涉及的弹药 id。"""
    ids: set[str] = set()
    for stations in stations_map.values():
        for st in stations:
            ids.update(st['allowed_stores'])
    return ids


def build_aircraft_stores_payload(
    stores_path: str | Path | None = None,
    stations_path: str | Path | None = None,
    limits_path: str | Path | None = None,
) -> dict[str, Any]:
    """构建前端/小程序/iOS 共用的外挂挂点目录。"""
    store_db = load_stores_database(stores_path)
    stations_map = load_aircraft_stations(stations_path)
    limits_map = load_aircraft_store_limits(limits_path)
    if not store_db or not stations_map:
        return {'stores': [], 'aircraft': {}}

    used_ids = _collect_store_ids(stations_map)
    stores_list = [store_db[sid] for sid in sorted(used_ids) if sid in store_db]

    aircraft: dict[str, Any] = {}
    for ac_id, stations in sorted(stations_map.items()):
        limits = limits_map.get(ac_id, [])
        aircraft[ac_id] = {
            'aircraft_id': ac_id,
            'station_count': len(stations),
            'builtin_gun': 'built_in_gun',
            'stations': stations,
            'limits': limits,
            'notes': 'MiG-29 MRCA STORES CAPABILITY 挂载示意图；9 外部挂点 + 内置航炮',
        }

    return {
        'stores': stores_list,
        'aircraft': aircraft,
        'categories': {c: c for c in STORE_CATEGORIES},
    }
