"""外挂弹药目录与挂载方案校验、质量/阻力汇总。"""
from __future__ import annotations

from typing import Any

from utils.database_csv import (
    load_aircraft_loadout_presets_csv,
    load_aircraft_station_csv,
    load_aircraft_store_catalog_csv,
)

# 计入气动阻力的外挂类别（吊舱/油箱也产生阻力，但量级不同于导弹）
_DRAG_CATEGORIES = frozenset({
    'aam', 'arm', 'agm', 'bomb', 'cluster', 'guided_bomb', 'jdam', 'rocket', 'fuel_tank',
})


def _store_index() -> dict[str, dict[str, Any]]:
    """store_id → 弹药/设备记录。"""
    return {row['id']: row for row in load_aircraft_store_catalog_csv()}


def _station_rows() -> list[dict[str, Any]]:
    return load_aircraft_station_csv()


def _stations_by_aircraft() -> dict[str, list[dict[str, Any]]]:
    """aircraft_id → 挂点列表（含 allowed_stores 已解析为 list）。"""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in _station_rows():
        aid = row['aircraft_id']
        grouped.setdefault(aid, []).append(row)
    for stations in grouped.values():
        stations.sort(key=lambda s: _station_sort_key(s['station_id']))
    return grouped


def _station_sort_key(station_id: str) -> tuple[int, str]:
    """挂点排序：数字优先，再字母后缀（5 < 5L < 5R < 6）。"""
    digits = ''
    suffix = ''
    for ch in station_id:
        if ch.isdigit():
            digits += ch
        else:
            suffix += ch
    return (int(digits) if digits else 0, suffix)


def validate_loadout(
    aircraft_id: str,
    assignments: dict[str, str],
    *,
    block: str | None = None,
) -> None:
    """校验 station_id → store_id 挂载是否在挂点能力表内。

    若 block 给定则只匹配该批次；否则取该机首个 block。
    """
    stations = _stations_for_aircraft(aircraft_id, block)
    station_map = {s['station_id']: s for s in stations}
    unknown_station = set(assignments) - set(station_map)
    if unknown_station:
        raise ValueError(f'{aircraft_id} 未知挂点: {sorted(unknown_station)}')
    store_ids = set(_store_index())
    for sid, store_id in assignments.items():
        if store_id not in store_ids:
            raise ValueError(f'未知外挂 {store_id!r}（挂点 {sid}）')
        allowed = station_map[sid]['allowed_stores']
        if store_id not in allowed:
            raise ValueError(
                f'{aircraft_id} 挂点 {sid} 不支持 {store_id!r}；'
                f'允许: {", ".join(allowed)}'
            )


def _stations_for_aircraft(aircraft_id: str, block: str | None) -> list[dict[str, Any]]:
    rows = [r for r in _station_rows() if r['aircraft_id'] == aircraft_id]
    if not rows:
        raise ValueError(f'未找到机型 {aircraft_id!r} 的挂点表')
    if block is not None:
        rows = [r for r in rows if r['block'] == block]
        if not rows:
            raise ValueError(f'{aircraft_id} 无 block={block!r} 挂点记录')
    else:
        first_block = rows[0]['block']
        rows = [r for r in rows if r['block'] == first_block]
    return sorted(rows, key=lambda s: _station_sort_key(s['station_id']))


def loadout_total_mass_kg(assignments: dict[str, str]) -> float:
    """按 station→store 汇总外挂总质量（kg）。"""
    stores = _store_index()
    total = 0.0
    for store_id in assignments.values():
        total += float(stores[store_id]['mass_kg'])
    return total


def loadout_drag_store_count(assignments: dict[str, str]) -> float:
    """估算计入 cd_store 的外挂体数量（油箱/炸弹/导弹各计 1，三联挂仍计 1）。"""
    stores = _store_index()
    count = 0.0
    for store_id in assignments.values():
        cat = stores[store_id]['category']
        if cat in _DRAG_CATEGORIES:
            count += 1.0
    return count


def _build_presets_payload() -> list[dict[str, Any]]:
    """把 CSV 预设行收成 preset 对象列表。"""
    rows = load_aircraft_loadout_presets_csv()
    presets: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (row['aircraft_id'], row['block'], row['preset_id'])
        if key not in presets:
            presets[key] = {
                'aircraft_id': row['aircraft_id'],
                'block': row['block'],
                'id': row['preset_id'],
                'name': row['preset_name'],
                'stations': {},
            }
        presets[key]['stations'][row['station_id']] = row['store_id']
    result: list[dict[str, Any]] = []
    for preset in presets.values():
        assignments = preset['stations']
        preset['total_mass_kg'] = loadout_total_mass_kg(assignments)
        preset['drag_store_count'] = loadout_drag_store_count(assignments)
        result.append(preset)
    result.sort(key=lambda p: (p['aircraft_id'], p['id']))
    return result


def build_aircraft_loadout_catalog_payload() -> dict[str, Any]:
    """构建前端 catalog 用的外挂/挂点/预设载荷。"""
    stores = load_aircraft_store_catalog_csv()
    store_categories = sorted({s['category'] for s in stores})
    aircraft_stations: dict[str, list[dict[str, Any]]] = {}
    for aid, stations in _stations_by_aircraft().items():
        aircraft_stations[aid] = [
            {
                'station_id': s['station_id'],
                'block': s['block'],
                'position': s['position'],
                'position_label': s['position_label'],
                'allowed_stores': list(s['allowed_stores']),
                'notes': s.get('notes'),
            }
            for s in stations
        ]
    return {
        'stores': stores,
        'store_categories': store_categories,
        'aircraft_stations': aircraft_stations,
        'presets': _build_presets_payload(),
    }
