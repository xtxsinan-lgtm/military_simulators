"""战斗机挂点与外挂弹药目录 — 从 CSV 加载并序列化为前端 catalog。"""
from __future__ import annotations

from typing import Any

from utils.database_csv import (
    load_aircraft_fixed_equipment_csv,
    load_aircraft_hardpoints_csv,
    load_aircraft_stores_csv,
)


def _stores_for_aircraft(
    aircraft_id: str,
    all_stores: dict[str, dict[str, Any]],
    hardpoint_rows: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """收集某机型挂点表中出现的外挂 id 及其规格。"""
    store_ids: set[str] = set()
    for row in hardpoint_rows:
        if row['aircraft_id'] != aircraft_id:
            continue
        store_ids.update(row['allowed_stores'])
    return {sid: dict(all_stores[sid]) for sid in sorted(store_ids) if sid in all_stores}


def hardpoints_for_aircraft(aircraft_id: str) -> dict[str, Any] | None:
    """返回单机型挂点目录；无记录时返回 None。"""
    stores = load_aircraft_stores_csv()
    hardpoints = load_aircraft_hardpoints_csv()
    fixed = load_aircraft_fixed_equipment_csv()
    rows = [r for r in hardpoints if r['aircraft_id'] == aircraft_id]
    if not rows:
        return None
    equipment = [dict(e) for e in fixed if e['aircraft_id'] == aircraft_id]
    station_payload = []
    for row in rows:
        station_payload.append({
            'id': row['station_id'],
            'name_zh': row['name_zh'],
            'position': row['position'],
            'side': row['side'],
            'max_mass_kg': row['max_mass_kg'],
            'allowed_stores': list(row['allowed_stores']),
            **({'notes': row['notes']} if row.get('notes') else {}),
        })
    return {
        'stores': _stores_for_aircraft(aircraft_id, stores, hardpoints),
        'stations': station_payload,
        'fixed_equipment': equipment,
    }


def build_aircraft_hardpoints_catalog_payload() -> dict[str, Any]:
    """构建 catalog 中的 aircraft_hardpoints 字段（按机型 id 索引）。"""
    hardpoints = load_aircraft_hardpoints_csv()
    aircraft_ids = sorted({row['aircraft_id'] for row in hardpoints})
    payload: dict[str, Any] = {}
    for aid in aircraft_ids:
        entry = hardpoints_for_aircraft(aid)
        if entry is not None:
            payload[aid] = entry
    position_labels = {
        'outboard': '外侧挂点',
        'midboard': '中侧挂点',
        'inboard': '内侧挂点',
        'centreline': '机腹中心线',
    }
    category_labels = {
        'wvr': '近距空空导弹',
        'bvr': '中距空空导弹',
        'pgb': '精确制导炸弹',
        'lgb': '激光制导炸弹',
        'unguided_bomb': '航空炸弹',
        'training': '训练弹',
        'fuel_tank': '副油箱',
        'ecm': '电子战吊舱',
        'targeting_pod': '瞄准吊舱',
    }
    return {
        'by_aircraft': payload,
        'position_labels': position_labels,
        'category_labels': category_labels,
    }
