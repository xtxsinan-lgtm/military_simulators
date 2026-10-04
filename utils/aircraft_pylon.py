"""飞机挂点挂载模型：按挂点定义可挂载的弹药与设备类型。"""
from __future__ import annotations

from typing import Any

from utils.database_csv import (
    PYLON_POSITION_LABELS,
    STORE_TYPE_LABELS,
    load_aircraft_pylon_csv,
)

# 前端与文档沿用简短别名
POSITION_LABELS = PYLON_POSITION_LABELS


def _station_to_dict(row: dict[str, Any]) -> dict[str, Any]:
    """CSV 行 → 前端可用的挂点字典。"""
    position = str(row['position'])
    item: dict[str, Any] = {
        'station_id': str(row['station_id']),
        'label': str(row['label']),
        'position': position,
        'position_label': POSITION_LABELS.get(position, position),
        'symmetric': bool(row['symmetric']),
        'allowed_stores': list(row['allowed_stores']),
    }
    notes = row.get('notes')
    if notes:
        item['notes'] = str(notes)
    return item


def load_pylon_models() -> dict[str, list[dict[str, Any]]]:
    """按机型 id 分组挂点配置。"""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in load_aircraft_pylon_csv():
        aircraft_id = str(row['aircraft_id'])
        grouped.setdefault(aircraft_id, []).append(_station_to_dict(row))
    return grouped


def get_pylon_model(aircraft_id: str) -> list[dict[str, Any]] | None:
    """返回指定机型的挂点列表；未配置则 None。"""
    stations = load_pylon_models().get(aircraft_id)
    if stations is None:
        return None
    return list(stations)


def station_allows_store(station: dict[str, Any], store_type: str) -> bool:
    """挂点是否允许挂载给定类型。"""
    return store_type in station.get('allowed_stores', [])


def physical_station_count(stations: list[dict[str, Any]]) -> int:
    """统计物理挂点数量（对称挂点计为 2）。"""
    total = 0
    for station in stations:
        total += 2 if station.get('symmetric') else 1
    return total


def build_aircraft_pylon_payload() -> dict[str, Any]:
    """构建写入 data.json 的挂点挂载目录。"""
    models: dict[str, Any] = {}
    for aircraft_id, stations in load_pylon_models().items():
        models[aircraft_id] = {
            'aircraft_id': aircraft_id,
            'station_count': len(stations),
            'physical_station_count': physical_station_count(stations),
            'stations': stations,
        }
    return {
        'store_types': dict(STORE_TYPE_LABELS),
        'position_labels': dict(POSITION_LABELS),
        'models': models,
    }
