"""苏-30（Su-30）十二挂点弹药兼容目录。

依据挂载能力图：挂点从左至右编号 1–12（1/12 翼尖，2/11 翼外侧，
3/10 翼中侧，4/9 翼内侧，5/8 进气道下，6/7 机身中心线前后）。
前端经 build_all → data.json 的 weapon_loadout.su30 与 loadout_catalog 同步。
"""
from __future__ import annotations

from typing import Any

from utils.database_csv import (
    load_su30_store_compatibility_csv,
    load_su30_store_database_csv,
    load_su30_store_limits_csv,
    load_su30_store_stations_csv,
)

# 外挂挂点数量（不含内置航炮）
SU30_EXTERNAL_STATION_COUNT = 12
SU30_AIRCRAFT_ID = 'Su-30'
SU30_AIRCRAFT_NAME = '苏-30'

STORE_CATEGORY_LABELS: dict[str, str] = {
    'a2a': '空对空制导武器',
    'agm': '空对面制导武器',
    'pgm': '精确制导炸弹',
    'bomb': '空对面非制导炸弹',
    'rocket': '航空火箭弹/发射巢',
    'pod': '吊舱/设备',
    'training': '训练弹药',
}


def _weapon_index(weapons: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """weapon_id → 武器记录。"""
    return {str(item['id']): item for item in weapons}


def build_su30_stores_payload(
    weapons: list[dict[str, Any]] | None = None,
    stations: list[dict[str, Any]] | None = None,
    compatibility: list[dict[str, Any]] | None = None,
    limits: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """组装苏-30 挂点目录，供 Web / 小程序 / iOS 读取。"""
    weapon_rows = weapons if weapons is not None else load_su30_store_database_csv()
    station_rows = stations if stations is not None else load_su30_store_stations_csv()
    compat_rows = (
        compatibility if compatibility is not None
        else load_su30_store_compatibility_csv()
    )
    limit_rows = limits if limits is not None else load_su30_store_limits_csv()

    by_weapon = _weapon_index(weapon_rows)
    compat_by_station: dict[int, list[dict[str, Any]]] = {}
    for row in compat_rows:
        station_id = int(row['station_id'])
        weapon_id = str(row['weapon_id'])
        weapon = by_weapon.get(weapon_id)
        if weapon is None:
            raise ValueError(f'兼容表引用未知武器 {weapon_id!r}（挂点 {station_id}）')
        category = str(weapon['category'])
        entry = {
            'weapon_id': weapon_id,
            'name': str(weapon['name']),
            'category': category,
            'category_label': STORE_CATEGORY_LABELS.get(category, category),
            'max_qty': int(row['max_qty']),
            'mass_kg': float(weapon['mass_kg']),
        }
        notes = row.get('notes')
        if notes:
            entry['notes'] = str(notes)
        compat_by_station.setdefault(station_id, []).append(entry)

    stations_payload: list[dict[str, Any]] = []
    for station in sorted(station_rows, key=lambda item: int(item['station_id'])):
        station_id = int(station['station_id'])
        stores = compat_by_station.get(station_id)
        if not stores:
            raise ValueError(f'挂点 {station_id} 缺少兼容弹药记录')
        item: dict[str, Any] = {
            'id': station_id,
            'name': str(station['name']),
            'mount': str(station['mount']),
            'position_index': int(station['position_index']),
            'side': str(station.get('side') or ''),
            'stores': stores,
        }
        notes = station.get('notes')
        if notes:
            item['notes'] = str(notes)
        stations_payload.append(item)

    limits_payload = [
        {
            'store_id': str(row['store_id']),
            'max_count': int(row['max_count']),
            'notes': str(row.get('notes') or ''),
        }
        for row in limit_rows
    ]

    return {
        'aircraft_id': SU30_AIRCRAFT_ID,
        'aircraft_name': SU30_AIRCRAFT_NAME,
        'external_station_count': SU30_EXTERNAL_STATION_COUNT,
        'layout_note': (
            '挂点编号按图表从左至右 1–12：'
            '1/12 翼尖，2/11 翼外侧，3/10 翼中侧，4/9 翼内侧，'
            '5/8 进气道下方，6/7 机身中心线前后。'
        ),
        'category_labels': dict(STORE_CATEGORY_LABELS),
        'weapons': weapon_rows,
        'stations': stations_payload,
        'limits': limits_payload,
    }


def station_weapon_max_qty(
    payload: dict[str, Any],
    station_id: int,
    weapon_id: str,
) -> int:
    """返回指定挂点对某弹药的单点最大挂载数量；不允许则 0。"""
    for station in payload.get('stations') or []:
        if int(station['id']) != int(station_id):
            continue
        for item in station.get('stores') or []:
            if str(item['weapon_id']) == str(weapon_id):
                return int(item['max_qty'])
        return 0
    return 0


def aircraft_weapon_max_count(
    payload: dict[str, Any],
    weapon_id: str,
) -> int | None:
    """返回全机弹药上限；无记录则 None。"""
    for row in payload.get('limits') or []:
        if str(row['store_id']) == str(weapon_id):
            return int(row['max_count'])
    return None


def validate_su30_loadout(
    selection: dict[str | int, dict[str, Any]],
    payload: dict[str, Any] | None = None,
) -> list[str]:
    """校验挂点选择（station → {weapon_id, qty}），返回错误列表。"""
    model = payload if payload is not None else build_su30_stores_payload()
    errors: list[str] = []
    station_ids = {int(st['id']) for st in model['stations']}
    counts: dict[str, int] = {}

    for raw_sid, choice in selection.items():
        try:
            sid = int(raw_sid)
        except (TypeError, ValueError):
            errors.append(f'未知挂点: {raw_sid}')
            continue
        if sid not in station_ids:
            errors.append(f'未知挂点: {sid}')
            continue
        if not choice:
            continue
        weapon_id = str(choice.get('weapon_id') or choice.get('munition_id') or '')
        if not weapon_id:
            continue
        try:
            qty = int(choice.get('qty') or 1)
        except (TypeError, ValueError):
            errors.append(f'挂点 {sid} 数量非法')
            continue
        if qty <= 0:
            continue
        max_qty = station_weapon_max_qty(model, sid, weapon_id)
        if max_qty <= 0:
            errors.append(f'挂点 {sid} 不允许挂载 {weapon_id}')
            continue
        if qty > max_qty:
            errors.append(
                f'挂点 {sid} 的 {weapon_id} 最多 {max_qty}，当前 {qty}'
            )
            continue
        counts[weapon_id] = counts.get(weapon_id, 0) + qty

    for weapon_id, n in counts.items():
        limit = aircraft_weapon_max_count(model, weapon_id)
        if limit is not None and n > limit:
            errors.append(f'{weapon_id} 全机最多 {limit}，当前 {n}')
    return errors
