"""外挂弹种与飞机挂点布局 CSV 加载。"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from utils.combat_radius.lift_drag import parse_store_mount
from utils.paths import (
    AIRCRAFT_LOADOUT_PRESETS_CSV,
    AIRCRAFT_STORE_LAYOUTS_CSV,
    STORE_TYPES_CSV,
)

STORE_TYPES_CSV_COLUMNS = (
    'id', 'name', 'mass_kg', 'length_m', 'diameter_m', 'store_mount', 'drag_weight', 'notes',
)
AIRCRAFT_STORE_LAYOUTS_CSV_COLUMNS = (
    'aircraft_id', 'station_id', 'label', 'zone', 'allowed_store_ids', 'notes',
)
AIRCRAFT_LOADOUT_PRESETS_CSV_COLUMNS = (
    'aircraft_id', 'preset_id', 'name', 'loadout', 'notes',
)


@dataclass(frozen=True)
class StoreType:
    """外挂弹种/装备规格。"""
    id: str
    name: str
    mass_kg: float
    length_m: float
    diameter_m: float
    store_mount: str
    drag_weight: float
    notes: str = ''


@dataclass(frozen=True)
class StoreStation:
    """单架飞机的一个挂点。"""
    aircraft_id: str
    station_id: str
    label: str
    zone: str
    allowed_store_ids: tuple[str, ...]
    notes: str = ''


@dataclass(frozen=True)
class LoadoutPreset:
    """命名挂载方案。"""
    aircraft_id: str
    preset_id: str
    name: str
    loadout: str
    notes: str = ''


def _parse_float(raw: str, field: str) -> float:
    text = raw.strip()
    if not text:
        raise ValueError(f'缺少必填数值字段 {field}')
    return float(text)


def _parse_allowed_store_ids(raw: str) -> tuple[str, ...]:
    """解析分号分隔的允许弹种 id 列表。"""
    text = (raw or '').strip()
    if not text:
        return ()
    return tuple(part.strip() for part in text.split(';') if part.strip())


def load_store_types_csv(path: str | Path | None = None) -> dict[str, StoreType]:
    """从 store_types.csv 加载弹种目录。"""
    csv_path = Path(path) if path is not None else STORE_TYPES_CSV
    if not csv_path.is_file():
        raise ValueError(f'{csv_path} 不存在')
    out: dict[str, StoreType] = {}
    with csv_path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f'{csv_path} 缺少表头')
        missing = [c for c in STORE_TYPES_CSV_COLUMNS if c not in reader.fieldnames]
        if missing:
            raise ValueError(f'{csv_path} 缺少列: {missing}')
        for row in reader:
            item_id = (row.get('id') or '').strip()
            name = (row.get('name') or '').strip()
            if not item_id or not name:
                continue
            if item_id in out:
                raise ValueError(f'{csv_path} 重复 id={item_id!r}')
            out[item_id] = StoreType(
                id=item_id,
                name=name,
                mass_kg=_parse_float(row.get('mass_kg') or '', 'mass_kg'),
                length_m=_parse_float(row.get('length_m') or '', 'length_m'),
                diameter_m=_parse_float(row.get('diameter_m') or '', 'diameter_m'),
                store_mount=parse_store_mount(row.get('store_mount')),
                drag_weight=_parse_float(row.get('drag_weight') or '', 'drag_weight'),
                notes=(row.get('notes') or '').strip(),
            )
    if not out:
        raise ValueError(f'{csv_path} 无有效记录')
    return out


def load_aircraft_store_layouts_csv(path: str | Path | None = None) -> dict[str, list[StoreStation]]:
    """按 aircraft_id 分组加载挂点布局。"""
    csv_path = Path(path) if path is not None else AIRCRAFT_STORE_LAYOUTS_CSV
    if not csv_path.is_file():
        raise ValueError(f'{csv_path} 不存在')
    grouped: dict[str, list[StoreStation]] = {}
    seen: dict[str, set[str]] = {}
    with csv_path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f'{csv_path} 缺少表头')
        missing = [c for c in AIRCRAFT_STORE_LAYOUTS_CSV_COLUMNS if c not in reader.fieldnames]
        if missing:
            raise ValueError(f'{csv_path} 缺少列: {missing}')
        for row in reader:
            aircraft_id = (row.get('aircraft_id') or '').strip()
            station_id = (row.get('station_id') or '').strip()
            label = (row.get('label') or '').strip()
            zone = (row.get('zone') or '').strip()
            if not aircraft_id or not station_id or not label:
                continue
            seen.setdefault(aircraft_id, set())
            if station_id in seen[aircraft_id]:
                raise ValueError(f'{csv_path} {aircraft_id} 重复 station_id={station_id!r}')
            seen[aircraft_id].add(station_id)
            allowed = _parse_allowed_store_ids(row.get('allowed_store_ids') or '')
            if not allowed:
                raise ValueError(f'{csv_path} {aircraft_id}/{station_id} 缺少 allowed_store_ids')
            grouped.setdefault(aircraft_id, []).append(StoreStation(
                aircraft_id=aircraft_id,
                station_id=station_id,
                label=label,
                zone=zone,
                allowed_store_ids=allowed,
                notes=(row.get('notes') or '').strip(),
            ))
    if not grouped:
        raise ValueError(f'{csv_path} 无有效记录')
    return grouped


def load_aircraft_loadout_presets_csv(path: str | Path | None = None) -> dict[str, list[LoadoutPreset]]:
    """按 aircraft_id 分组加载命名挂载方案。"""
    csv_path = Path(path) if path is not None else AIRCRAFT_LOADOUT_PRESETS_CSV
    if not csv_path.is_file():
        raise ValueError(f'{csv_path} 不存在')
    grouped: dict[str, list[LoadoutPreset]] = {}
    seen: dict[str, set[str]] = {}
    with csv_path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f'{csv_path} 缺少表头')
        missing = [c for c in AIRCRAFT_LOADOUT_PRESETS_CSV_COLUMNS if c not in reader.fieldnames]
        if missing:
            raise ValueError(f'{csv_path} 缺少列: {missing}')
        for row in reader:
            aircraft_id = (row.get('aircraft_id') or '').strip()
            preset_id = (row.get('preset_id') or '').strip()
            name = (row.get('name') or '').strip()
            loadout = (row.get('loadout') or '').strip()
            if not aircraft_id or not preset_id or not name or not loadout:
                continue
            seen.setdefault(aircraft_id, set())
            if preset_id in seen[aircraft_id]:
                raise ValueError(f'{csv_path} {aircraft_id} 重复 preset_id={preset_id!r}')
            seen[aircraft_id].add(preset_id)
            grouped.setdefault(aircraft_id, []).append(LoadoutPreset(
                aircraft_id=aircraft_id,
                preset_id=preset_id,
                name=name,
                loadout=loadout,
                notes=(row.get('notes') or '').strip(),
            ))
    return grouped


def _store_type_to_dict(st: StoreType) -> dict[str, Any]:
    return {
        'id': st.id,
        'name': st.name,
        'mass_kg': st.mass_kg,
        'length_m': st.length_m,
        'diameter_m': st.diameter_m,
        'store_mount': st.store_mount,
        'drag_weight': st.drag_weight,
        'notes': st.notes,
    }


def _station_to_dict(st: StoreStation) -> dict[str, Any]:
    return {
        'station_id': st.station_id,
        'label': st.label,
        'zone': st.zone,
        'allowed_store_ids': list(st.allowed_store_ids),
        'notes': st.notes,
    }


def _preset_to_dict(p: LoadoutPreset) -> dict[str, Any]:
    return {
        'preset_id': p.preset_id,
        'name': p.name,
        'loadout': p.loadout,
        'notes': p.notes,
    }


def build_store_catalog_payload() -> dict[str, Any]:
    """构建前端 catalog 用的外挂/挂点数据。"""
    store_types = load_store_types_csv()
    layouts = load_aircraft_store_layouts_csv()
    presets = load_aircraft_loadout_presets_csv()
    return {
        'store_types': [_store_type_to_dict(v) for v in store_types.values()],
        'aircraft_store_layouts': {
            aid: [_station_to_dict(s) for s in stations]
            for aid, stations in layouts.items()
        },
        'aircraft_loadout_presets': {
            aid: [_preset_to_dict(p) for p in plist]
            for aid, plist in presets.items()
        },
    }
