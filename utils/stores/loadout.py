"""挂载方案解析、校验与质量/阻力汇总。"""
from __future__ import annotations

from dataclasses import dataclass

from utils.stores.store_catalog import (
    LoadoutPreset,
    StoreStation,
    StoreType,
    load_aircraft_store_layouts_csv,
    load_store_types_csv,
)


@dataclass(frozen=True)
class LoadoutItem:
    """单个挂点的挂载选择。"""
    station_id: str
    store_id: str


def parse_loadout_string(loadout: str) -> list[LoadoutItem]:
    """解析 `station:store;station:store` 格式的挂载字符串。"""
    text = (loadout or '').strip()
    if not text:
        return []
    items: list[LoadoutItem] = []
    seen: set[str] = set()
    for part in text.split(';'):
        part = part.strip()
        if not part:
            continue
        if ':' not in part:
            raise ValueError(f'挂载项格式错误 {part!r}，应为 station_id:store_id')
        station_id, store_id = part.split(':', 1)
        station_id = station_id.strip()
        store_id = store_id.strip()
        if not station_id or not store_id:
            raise ValueError(f'挂载项格式错误 {part!r}，station_id/store_id 不能为空')
        if station_id in seen:
            raise ValueError(f'挂点 {station_id!r} 重复挂载')
        seen.add(station_id)
        items.append(LoadoutItem(station_id=station_id, store_id=store_id))
    return items


def _station_map(stations: list[StoreStation]) -> dict[str, StoreStation]:
    return {s.station_id: s for s in stations}


def validate_loadout(
    aircraft_id: str,
    items: list[LoadoutItem],
    *,
    store_types: dict[str, StoreType] | None = None,
    layouts: dict[str, list[StoreStation]] | None = None,
) -> None:
    """校验挂载方案：挂点存在、弹种允许、无重复挂点。"""
    store_types = store_types or load_store_types_csv()
    layouts = layouts or load_aircraft_store_layouts_csv()
    if aircraft_id not in layouts:
        raise ValueError(f'机型 {aircraft_id!r} 无挂点布局定义')
    stations = _station_map(layouts[aircraft_id])
    seen: set[str] = set()
    for item in items:
        if item.station_id in seen:
            raise ValueError(f'挂点 {item.station_id!r} 重复挂载')
        seen.add(item.station_id)
        if item.station_id not in stations:
            raise ValueError(
                f'机型 {aircraft_id} 不存在挂点 {item.station_id!r}，'
                f'可选: {sorted(stations)}'
            )
        station = stations[item.station_id]
        if item.store_id not in store_types:
            raise ValueError(f'未知弹种 {item.store_id!r}')
        if item.store_id not in station.allowed_store_ids:
            raise ValueError(
                f'挂点 {item.station_id} 不允许挂载 {item.store_id!r}，'
                f'允许: {list(station.allowed_store_ids)}'
            )


def loadout_total_mass_kg(
    items: list[LoadoutItem],
    *,
    store_types: dict[str, StoreType] | None = None,
) -> float:
    """汇总挂载方案总质量（kg）。"""
    store_types = store_types or load_store_types_csv()
    total = 0.0
    for item in items:
        st = store_types[item.store_id]
        total += st.mass_kg
    return total


def loadout_drag_weight(
    items: list[LoadoutItem],
    *,
    store_types: dict[str, StoreType] | None = None,
) -> float:
    """汇总挂载方案气动阻力权重（相对 AIM-120 基准）。"""
    store_types = store_types or load_store_types_csv()
    total = 0.0
    for item in items:
        st = store_types[item.store_id]
        total += st.drag_weight
    return total


def effective_n_stores(
    items: list[LoadoutItem],
    *,
    store_types: dict[str, StoreType] | None = None,
) -> float:
    """将异构挂载折算为等效中距弹枚数（供作战半径阻力估算）。"""
    return loadout_drag_weight(items, store_types=store_types)
