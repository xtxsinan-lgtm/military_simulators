"""战斗机外挂挂点目录：CSV 加载与前端 catalog 载荷。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from utils.database_csv import load_aircraft_weapon_stations_csv
from utils.paths import AIRCRAFT_WEAPON_CONFIG_JSON, AIRCRAFT_WEAPON_STATIONS_CSV


def load_weapon_config(path: str | Path | None = None) -> dict[str, Any]:
    """读取挂点类别与排序配置。"""
    cfg_path = Path(path) if path is not None else AIRCRAFT_WEAPON_CONFIG_JSON
    if not cfg_path.is_file():
        return {'version': 1, 'category_labels': {}, 'station_order': []}
    with cfg_path.open('r', encoding='utf-8') as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f'{cfg_path} 根节点必须是对象')
    return data


def build_aircraft_weapons_payload(
    csv_path: str | Path | None = None,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    """把挂点 CSV 收成 aircraft_id -> stations 结构，供 Web/小程序/iOS 共用。"""
    config = load_weapon_config(config_path)
    category_labels: dict[str, str] = dict(config.get('category_labels') or {})
    station_order: list[str] = [str(x) for x in (config.get('station_order') or [])]
    rows = load_aircraft_weapon_stations_csv(csv_path)

    by_aircraft: dict[str, dict[str, Any]] = {}
    for row in rows:
        aid = str(row['aircraft_id'])
        station_id = str(row['station_id'])
        station_name = str(row['station_name'])
        category = str(row['category'])
        weapon = {
            'id': str(row['weapon_id']),
            'name': str(row['weapon_name']),
        }
        notes = (row.get('notes') or '').strip()
        if notes:
            weapon['notes'] = notes

        ac = by_aircraft.setdefault(aid, {'id': aid, 'stations': {}})
        stations: dict[str, dict[str, Any]] = ac['stations']
        station = stations.setdefault(
            station_id,
            {'id': station_id, 'name': station_name, 'categories': {}},
        )
        categories: dict[str, dict[str, Any]] = station['categories']
        cat = categories.setdefault(
            category,
            {
                'id': category,
                'label': category_labels.get(category, category),
                'weapons': [],
            },
        )
        cat['weapons'].append(weapon)

    aircraft_out: dict[str, Any] = {}
    for aid, ac in by_aircraft.items():
        stations_map: dict[str, dict[str, Any]] = ac['stations']
        order = station_order or sorted(stations_map.keys(), key=_station_sort_key)
        stations_list: list[dict[str, Any]] = []
        for sid in order:
            if sid not in stations_map:
                continue
            station = stations_map[sid]
            categories = list(station['categories'].values())
            categories.sort(key=lambda c: c['id'])
            stations_list.append({
                'id': station['id'],
                'name': station['name'],
                'categories': categories,
            })
        aircraft_out[aid] = {'id': aid, 'stations': stations_list}

    return {
        'version': int(config.get('version') or 1),
        'category_labels': category_labels,
        'station_order': station_order,
        'aircraft': aircraft_out,
    }


def get_aircraft_weapon_stations(
    payload: dict[str, Any],
    aircraft_id: str,
) -> list[dict[str, Any]] | None:
    """按机型 id 取挂点列表；无数据时返回 None。"""
    ac = (payload.get('aircraft') or {}).get(aircraft_id)
    if not ac:
        return None
    return list(ac.get('stations') or [])


def _station_sort_key(station_id: str) -> tuple[int, str]:
    """G 固定机炮排在数字挂点之后。"""
    if station_id == 'G':
        return (1, station_id)
    try:
        return (0, f'{int(station_id):04d}')
    except ValueError:
        return (0, station_id)
