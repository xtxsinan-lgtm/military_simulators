"""非隐身机挂点挂载：弹药库、挂点表、质量/外油/外挂几何汇总。

挂载阻力按各站 mount_style 与弹药长径估算浸润与迎风，供 lift_drag.CDs 使用。
副油箱燃油并入任务总油量；油箱干重计入挂载质量。
"""
from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from utils.paths import AIRCRAFT_STATIONS_JSON, MUNITIONS_CSV

# 挂点气动：相对 AIM-120 全外挂架的挂架浸润/迎风与干扰
MOUNT_STYLE_AERO: dict[str, dict[str, float]] = {
    'wing_pylon': {
        'pylon_wetted_m2': 0.35,
        'pylon_front_m2': 0.008,
        'interf': 1.40,
        'exposed_frac': 1.0,
        'front_frac': 1.0,
    },
    'centerline': {
        'pylon_wetted_m2': 0.40,
        'pylon_front_m2': 0.010,
        'interf': 1.45,
        'exposed_frac': 1.0,
        'front_frac': 1.0,
    },
    'side_rail': {
        'pylon_wetted_m2': 0.06,
        'pylon_front_m2': 0.002,
        'interf': 1.15,
        'exposed_frac': 1.0,
        'front_frac': 1.0,
    },
    'cft': {
        'pylon_wetted_m2': 0.10,
        'pylon_front_m2': 0.003,
        'interf': 1.30,
        'exposed_frac': 0.85,
        'front_frac': 0.90,
    },
    'chin_pod': {
        'pylon_wetted_m2': 0.15,
        'pylon_front_m2': 0.004,
        'interf': 1.35,
        'exposed_frac': 1.0,
        'front_frac': 1.0,
    },
}

# 同站多枚（三联架/CFT 串挂）额外干扰
MULTI_STORE_INTERF_PER_EXTRA = 0.08

_MUNITIONS_CACHE: dict[str, dict[str, Any]] | None = None
_STATIONS_CACHE: dict[str, Any] | None = None


@dataclass
class StoreSpec:
    """单站同型外挂几何，供升阻比外挂项使用。"""

    length_m: float
    diameter_m: float
    count: float = 1.0
    mount: str = 'pylon'
    pylon_wetted_m2: float = 0.35
    pylon_front_m2: float = 0.008
    exposed_frac: float = 1.0
    interf: float = 1.40
    front_frac: float = 1.0
    station_id: str = ''
    munition_id: str = ''


@dataclass
class LoadoutSummary:
    """挂载汇总：质量、外油与外挂几何。"""

    aircraft_id: str
    weapons_mass_kg: float = 0.0
    tank_dry_mass_kg: float = 0.0
    external_fuel_kg: float = 0.0
    store_specs: list[StoreSpec] = field(default_factory=list)
    stations: list[dict[str, Any]] = field(default_factory=list)

    @property
    def payload_mass_kg(self) -> float:
        """计入空战重量的挂载干重（弹药+油箱壳体，不含燃油）。"""
        return self.weapons_mass_kg + self.tank_dry_mass_kg

    @property
    def n_store_units(self) -> float:
        """外挂件数合计（用于兼容 n_stores 显示）。"""
        return float(sum(max(s.count, 0.0) for s in self.store_specs))

    def to_dict(self) -> dict[str, Any]:
        """JSON 友好汇总。"""
        return {
            'aircraft_id': self.aircraft_id,
            'weapons_mass_kg': self.weapons_mass_kg,
            'tank_dry_mass_kg': self.tank_dry_mass_kg,
            'external_fuel_kg': self.external_fuel_kg,
            'payload_mass_kg': self.payload_mass_kg,
            'n_store_units': self.n_store_units,
            'store_specs': [asdict(s) for s in self.store_specs],
            'stations': list(self.stations),
        }


def _opt_float(value: Any, default: float = 0.0) -> float:
    """解析浮点；空值用默认。"""
    if value is None or value == '':
        return default
    return float(value)


def load_munitions(path: str | Path | None = None) -> dict[str, dict[str, Any]]:
    """读取弹药库，返回 id → 记录。"""
    global _MUNITIONS_CACHE
    src = Path(path) if path is not None else MUNITIONS_CSV
    if path is None and _MUNITIONS_CACHE is not None:
        return _MUNITIONS_CACHE
    out: dict[str, dict[str, Any]] = {}
    with src.open(encoding='utf-8-sig', newline='') as fh:
        for row in csv.DictReader(fh):
            mid = (row.get('id') or '').strip()
            if not mid:
                continue
            dry = _opt_float(row.get('dry_mass_kg'), _opt_float(row.get('mass_kg')))
            fuel = _opt_float(row.get('fuel_kg'))
            mass = _opt_float(row.get('mass_kg'), dry + fuel)
            out[mid] = {
                'id': mid,
                'name': (row.get('name') or mid).strip(),
                'category': (row.get('category') or '').strip(),
                'mass_kg': mass,
                'dry_mass_kg': dry,
                'fuel_kg': fuel,
                'length_m': _opt_float(row.get('length_m')),
                'diameter_m': _opt_float(row.get('diameter_m')),
                'notes': (row.get('notes') or '').strip(),
            }
    if path is None:
        _MUNITIONS_CACHE = out
    return out


def load_aircraft_stations(path: str | Path | None = None) -> dict[str, Any]:
    """读取机型挂点库（含 version 与 aircraft 映射）。"""
    global _STATIONS_CACHE
    src = Path(path) if path is not None else AIRCRAFT_STATIONS_JSON
    if path is None and _STATIONS_CACHE is not None:
        return _STATIONS_CACHE
    data = json.loads(src.read_text(encoding='utf-8'))
    if path is None:
        _STATIONS_CACHE = data
    return data


def inject_loadout_catalog(
    munitions: dict[str, dict[str, Any]] | None = None,
    stations: dict[str, Any] | None = None,
) -> None:
    """供 Pyodide/测试注入挂载目录，避免读盘。"""
    global _MUNITIONS_CACHE, _STATIONS_CACHE
    if munitions is not None:
        _MUNITIONS_CACHE = munitions
    if stations is not None:
        _STATIONS_CACHE = stations


def clear_loadout_caches() -> None:
    """清空挂载缓存。"""
    global _MUNITIONS_CACHE, _STATIONS_CACHE
    _MUNITIONS_CACHE = None
    _STATIONS_CACHE = None


def get_aircraft_station_def(aircraft_id: str) -> dict[str, Any] | None:
    """按机型 id 取挂点定义；无挂点表时返回 None。"""
    if not aircraft_id:
        return None
    root = load_aircraft_stations()
    aircraft = root.get('aircraft') or {}
    item = aircraft.get(aircraft_id)
    return dict(item) if isinstance(item, dict) else None


def option_key(munition_id: str, qty: float) -> str:
    """挂载选项稳定键：munition_id@qty。"""
    q = int(qty) if float(qty) == int(float(qty)) else float(qty)
    return f'{munition_id}@{q}'


def option_label(munition: dict[str, Any], qty: float, custom: str | None = None) -> str:
    """生成选项显示名。"""
    if custom:
        return custom
    name = munition.get('name') or munition.get('id') or '?'
    q = float(qty)
    if q <= 1:
        return str(name)
    if q == int(q):
        return f'{name} ×{int(q)}'
    return f'{name} ×{q}'


def expand_station_options(station: dict[str, Any], munitions: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """展开挂点选项（含空挂），供前端下拉。"""
    rows: list[dict[str, Any]] = [{
        'key': '',
        'munition_id': '',
        'qty': 0,
        'label': '空挂',
    }]
    for opt in station.get('options') or []:
        mid = str(opt.get('munition_id') or '').strip()
        if not mid:
            continue
        mun = munitions.get(mid)
        if mun is None:
            raise ValueError(f'挂点 {station.get("id")} 引用未知弹药 {mid}')
        qty = _opt_float(opt.get('qty'), 1.0)
        if qty <= 0:
            continue
        custom = opt.get('label')
        rows.append({
            'key': option_key(mid, qty),
            'munition_id': mid,
            'qty': qty,
            'label': option_label(mun, qty, str(custom) if custom else None),
            'mass_kg': mun['dry_mass_kg'] * qty + mun['fuel_kg'] * qty,
            'dry_mass_kg': mun['dry_mass_kg'] * qty,
            'fuel_kg': mun['fuel_kg'] * qty,
        })
    return rows


def build_loadout_catalog_payload() -> dict[str, Any]:
    """前端 catalog：弹药表 + 各机挂点与展开选项。"""
    munitions = load_munitions()
    root = load_aircraft_stations()
    aircraft_out: dict[str, Any] = {}
    for aid, raw in (root.get('aircraft') or {}).items():
        stations = []
        for st in raw.get('stations') or []:
            stations.append({
                'id': st['id'],
                'label': st.get('label') or st['id'],
                'mount_style': st.get('mount_style') or 'wing_pylon',
                'options': expand_station_options(st, munitions),
            })
        default_sel = {}
        for sid, sel in (raw.get('default_selection') or {}).items():
            mid = str(sel.get('munition_id') or '').strip()
            qty = _opt_float(sel.get('qty'), 1.0)
            if mid:
                default_sel[sid] = option_key(mid, qty)
        aircraft_out[aid] = {
            'id': aid,
            'name': raw.get('name') or aid,
            'stations': stations,
            'default_selection': default_sel,
        }
    return {
        'version': int(root.get('version') or 1),
        'munitions': list(munitions.values()),
        'aircraft': aircraft_out,
    }


def _aero_for_mount_style(mount_style: str, qty: float) -> dict[str, float]:
    """按挂点类型与枚数给出外挂气动参数。"""
    style = mount_style if mount_style in MOUNT_STYLE_AERO else 'wing_pylon'
    base = dict(MOUNT_STYLE_AERO[style])
    extra = max(float(qty) - 1.0, 0.0)
    base['interf'] = float(base['interf']) * (1.0 + MULTI_STORE_INTERF_PER_EXTRA * extra)
    return base


def resolve_loadout(
    aircraft_id: str,
    selection: dict[str, Any] | None,
) -> LoadoutSummary:
    """将各站选择解析为质量、外油与 StoreSpec 列表。

    selection: station_id → 选项键（munition@qty）或 {munition_id, qty}；空/缺省=空挂。
    """
    ac_def = get_aircraft_station_def(aircraft_id)
    if ac_def is None:
        raise ValueError(f'机型 {aircraft_id} 无挂点挂载表')
    munitions = load_munitions()
    sel = selection or {}
    summary = LoadoutSummary(aircraft_id=aircraft_id)
    station_by_id = {st['id']: st for st in (ac_def.get('stations') or [])}

    for st in ac_def.get('stations') or []:
        sid = st['id']
        raw = sel.get(sid)
        mid, qty = _parse_selection_value(raw)
        if not mid or qty <= 0:
            summary.stations.append({
                'station_id': sid,
                'label': st.get('label') or sid,
                'munition_id': '',
                'qty': 0,
                'label_option': '空挂',
            })
            continue
        allowed = {
            option_key(str(o.get('munition_id')), _opt_float(o.get('qty'), 1.0))
            for o in (st.get('options') or [])
        }
        key = option_key(mid, qty)
        if key not in allowed:
            raise ValueError(f'挂点 {sid} 不允许挂载 {key}')
        mun = munitions.get(mid)
        if mun is None:
            raise ValueError(f'未知弹药 {mid}')
        dry = float(mun['dry_mass_kg']) * qty
        fuel = float(mun['fuel_kg']) * qty
        if float(mun['fuel_kg']) > 0:
            summary.tank_dry_mass_kg += dry
            summary.external_fuel_kg += fuel
        else:
            summary.weapons_mass_kg += dry
        aero = _aero_for_mount_style(str(st.get('mount_style') or 'wing_pylon'), qty)
        summary.store_specs.append(StoreSpec(
            length_m=float(mun['length_m']),
            diameter_m=float(mun['diameter_m']),
            count=float(qty),
            mount='pylon',
            pylon_wetted_m2=float(aero['pylon_wetted_m2']),
            pylon_front_m2=float(aero['pylon_front_m2']),
            exposed_frac=float(aero['exposed_frac']),
            interf=float(aero['interf']),
            front_frac=float(aero['front_frac']),
            station_id=sid,
            munition_id=mid,
        ))
        custom = None
        for o in st.get('options') or []:
            if (
                str(o.get('munition_id')) == mid
                and abs(_opt_float(o.get('qty'), 1.0) - qty) < 1e-9
            ):
                custom = o.get('label')
                break
        summary.stations.append({
            'station_id': sid,
            'label': st.get('label') or sid,
            'munition_id': mid,
            'qty': qty,
            'label_option': option_label(mun, qty, str(custom) if custom else None),
            'dry_mass_kg': dry,
            'fuel_kg': fuel,
        })
    # 校验 selection 里没有未知站
    for sid in sel:
        if sid not in station_by_id and sel[sid] not in (None, '', {}):
            raise ValueError(f'未知挂点 {sid}')
    return summary


def _parse_selection_value(raw: Any) -> tuple[str, float]:
    """解析单站选择：空 / 键 / 字典。"""
    if raw is None or raw == '' or raw == {}:
        return '', 0.0
    if isinstance(raw, dict):
        mid = str(raw.get('munition_id') or '').strip()
        qty = _opt_float(raw.get('qty'), 1.0 if mid else 0.0)
        return mid, qty
    text = str(raw).strip()
    if not text or text == 'empty':
        return '', 0.0
    if '@' in text:
        mid, _, q = text.partition('@')
        return mid.strip(), _opt_float(q, 1.0)
    return text, 1.0


def apply_loadout_to_params(params: dict[str, Any]) -> dict[str, Any]:
    """若请求含 loadout，则覆盖挂载质量、总油量与 target.store_specs。"""
    loadout = params.get('loadout')
    if not loadout:
        return params
    if isinstance(loadout, str):
        loadout = json.loads(loadout)
    if not isinstance(loadout, dict):
        raise ValueError('loadout 必须为对象')
    aircraft_id = str(
        loadout.get('aircraft_id')
        or params.get('aircraft_id')
        or ''
    ).strip()
    if not aircraft_id:
        raise ValueError('loadout 缺少 aircraft_id')
    selection = loadout.get('selection')
    if selection is None:
        # 允许 loadout 直接是 station→选项 映射
        selection = {
            k: v for k, v in loadout.items()
            if k not in ('aircraft_id', 'selection')
        }
    summary = resolve_loadout(aircraft_id, selection)
    out = dict(params)
    out['aircraft_id'] = aircraft_id
    base_fuel = _opt_float(out.get('internal_fuel_kg'))
    out['internal_fuel_kg'] = base_fuel + summary.external_fuel_kg
    # 空战重量：挂载干重按「一件」计入，兼容 n_missiles×missile_mass
    out['missile_mass_kg'] = summary.payload_mass_kg
    out['n_missiles'] = 1.0 if summary.payload_mass_kg > 0 else 0.0
    target = dict(out.get('target') or {})
    target['store_specs'] = [asdict(s) for s in summary.store_specs]
    target['n_stores'] = summary.n_store_units
    target['store_mount'] = 'pylon' if summary.store_specs else target.get('store_mount', 'pylon')
    out['target'] = target
    out['loadout_summary'] = summary.to_dict()
    return out
