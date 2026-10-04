"""战斗机外挂挂点与弹药兼容库。"""
from __future__ import annotations

from typing import Any

from utils.database_csv import load_aircraft_store_catalog_csv, load_aircraft_store_mounts_csv


def _station_ids(raw: str) -> list[int]:
    """解析分号分隔的挂点编号。"""
    parts = [part.strip() for part in str(raw).split(';') if part.strip()]
    if not parts:
        raise ValueError(f'挂点编号不能为空: {raw!r}')
    return [int(part) for part in parts]


def build_aircraft_stores_payload(
    catalog: list[dict[str, Any]] | None = None,
    mounts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """构建前端 catalog 用的外挂兼容表。

    返回结构：
    - stores: 弹药/装备目录（store_id -> 字段）
    - aircraft: 各机型挂点组与可选弹药列表
    """
    catalog_rows = catalog if catalog is not None else load_aircraft_store_catalog_csv()
    mount_rows = mounts if mounts is not None else load_aircraft_store_mounts_csv()

    stores: dict[str, dict[str, Any]] = {}
    for row in catalog_rows:
        store_id = str(row['store_id'])
        if store_id in stores:
            raise ValueError(f'重复 store_id: {store_id}')
        stores[store_id] = {
            'id': store_id,
            'name': str(row['name']),
            'category': str(row['category']),
            'mass_kg': float(row['mass_kg']),
            'length_m': float(row['length_m']),
            'diameter_m': float(row['diameter_m']),
            'notes': str(row.get('notes') or ''),
        }

    # 按机型、挂点组聚合
    grouped: dict[str, dict[str, dict[str, Any]]] = {}
    for row in mount_rows:
        aircraft_id = str(row['aircraft_id'])
        group_key = str(row['station_group'])
        store_id = str(row['store_id'])
        if store_id not in stores:
            raise ValueError(f'未知 store_id {store_id!r}（机型 {aircraft_id}）')
        aircraft_groups = grouped.setdefault(aircraft_id, {})
        group = aircraft_groups.get(group_key)
        if group is None:
            group = {
                'group': group_key,
                'label': str(row['group_label']),
                'station_ids': _station_ids(str(row['station_ids'])),
                'stores': [],
            }
            aircraft_groups[group_key] = group
        else:
            if group['label'] != str(row['group_label']):
                raise ValueError(
                    f'{aircraft_id}/{group_key} 挂点组标签不一致: '
                    f'{group["label"]!r} vs {row["group_label"]!r}',
                )
            if group['station_ids'] != _station_ids(str(row['station_ids'])):
                raise ValueError(f'{aircraft_id}/{group_key} 挂点编号不一致')
        group['stores'].append({
            'store_id': store_id,
            'max_qty': int(row['max_qty']),
            'notes': str(row.get('notes') or ''),
        })

    aircraft_payload: dict[str, list[dict[str, Any]]] = {}
    for aircraft_id, groups in grouped.items():
        # 挂点编号从左到右（1=左翼尖 … 7=右翼尖）
        aircraft_payload[aircraft_id] = sorted(
            groups.values(),
            key=lambda item: min(item['station_ids']),
        )

    return {
        'stores': stores,
        'aircraft': aircraft_payload,
    }


def stores_for_aircraft(aircraft_id: str) -> list[dict[str, Any]] | None:
    """查询指定机型的挂点组列表；无数据时返回 None。"""
    payload = build_aircraft_stores_payload()
    return payload['aircraft'].get(aircraft_id)
