"""台风（Eurofighter Typhoon）挂点与弹药兼容目录。"""
from __future__ import annotations

from typing import Any

from utils.database_csv import (
    load_typhoon_store_compatibility_csv,
    load_typhoon_store_stations_csv,
    load_weapon_store_csv,
)

# 图表从左至右共 13 个外挂站位：9 个翼下/机腹挂架 + 4 个半埋中距弹位 + 内置航炮。
# 半埋弹位在目录中合并为 4 号与 6 号逻辑挂点（各含两个物理站位）。
TYPHOON_EXTERNAL_STATION_COUNT = 13
TYPHOON_SEMI_RECESSED_PHYSICAL = 4

STORE_CATEGORY_LABELS: dict[str, str] = {
    'a2a': '空对空导弹',
    'pgm': '精确制导/巡航/反辐射弹药',
    'battlefield': '战场/反装甲弹药',
    'asm': '反舰导弹',
    'aux': '辅助设备',
    'fixed': '内置固定武器',
}


def _weapon_index(weapons: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """weapon_id → 武器记录。"""
    return {str(item['id']): item for item in weapons}


def build_typhoon_stores_payload(
    weapons: list[dict[str, Any]] | None = None,
    stations: list[dict[str, Any]] | None = None,
    compatibility: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """组装台风挂点目录，供 Web / 小程序 / iOS 读取。"""
    weapon_rows = weapons if weapons is not None else load_weapon_store_csv()
    station_rows = stations if stations is not None else load_typhoon_store_stations_csv()
    compat_rows = compatibility if compatibility is not None else load_typhoon_store_compatibility_csv()

    by_weapon = _weapon_index(weapon_rows)
    compat_by_station: dict[int, list[dict[str, Any]]] = {}
    for row in compat_rows:
        station_id = int(row['station_id'])
        weapon_id = str(row['weapon_id'])
        weapon = by_weapon.get(weapon_id)
        if weapon is None:
            raise ValueError(f'兼容表引用未知武器 {weapon_id!r}（挂点 {station_id}）')
        entry = {
            'weapon_id': weapon_id,
            'name': str(weapon['name']),
            'category': str(weapon['category']),
            'category_label': STORE_CATEGORY_LABELS[str(weapon['category'])],
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
            'stores': stores,
        }
        notes = station.get('notes')
        if notes:
            item['notes'] = str(notes)
        stations_payload.append(item)

    return {
        'aircraft_id': 'Typhoon',
        'aircraft_name': '台风',
        'external_station_count': TYPHOON_EXTERNAL_STATION_COUNT,
        'semi_recessed_physical_count': TYPHOON_SEMI_RECESSED_PHYSICAL,
        'layout_note': (
            '挂点编号按图表从左至右；最左侧为左翼最外侧。'
            '4 号与 6 号半埋挂点各含两个物理站位，合计 13 个外挂位加内置航炮。'
        ),
        'category_labels': dict(STORE_CATEGORY_LABELS),
        'weapons': weapon_rows,
        'stations': stations_payload,
    }


def build_weapon_loadout_catalog_payload() -> dict[str, Any]:
    """前端 weapon_loadout 目录根节点。"""
    from utils.weapon_loadout.su30_stores import build_su30_stores_payload

    return {
        'typhoon': build_typhoon_stores_payload(),
        'su30': build_su30_stores_payload(),
    }
