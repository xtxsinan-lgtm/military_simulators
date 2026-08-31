"""作战半径机型仪表盘预计算结果。

按 CSV 默认机型+发动机跑完整仪表盘，写入 data/combat_radius_results.json，
经 build_all 进入 data.json，网页选取战机后直接加载，无需现场计算。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from simulators.combat_radius.combat_radius import resolve_tsl_kN, run_aircraft_dashboard_from_params
from utils.combat_radius.combat_radius_config import ui_config
from utils.combat_radius.combat_radius_presets import get_preset_by_id, load_engine_presets, load_presets
from utils.combat_radius.cruise_load import N_MISSILES_DEFAULT
from utils.paths import COMBAT_RADIUS_RESULTS_JSON

RESULTS_VERSION = 1


def dashboard_params_from_preset(
    aircraft: dict[str, Any],
    engine: dict[str, Any],
) -> dict[str, Any]:
    """由机型/发动机预设组装仪表盘请求（不含锚点，由核心默认填入）。"""
    params: dict[str, Any] = {
        'name': f'{aircraft["name"]} / {engine["name"]}',
        'target': aircraft,
        'empty_kg': aircraft['empty_kg'],
        'internal_fuel_kg': aircraft['internal_fuel_kg'],
        'n_pilots': aircraft.get('n_pilots', 1),
        'missile_mass_kg': aircraft.get('missile_mass_kg', 0),
        'n_missiles': N_MISSILES_DEFAULT,
        'n_engines': aircraft.get('n_engines', 1),
        'carrier': bool(aircraft.get('carrier', False)),
        'bpr': engine['bpr'],
        'opr': engine['opr'],
        't4_K': engine['t4_K'],
        'tsl_kN': resolve_tsl_kN(engine),
        'max_tsl_kN': engine.get('max_tsl_kN'),
        'tsfc_install_mult': engine.get('tsfc_install_mult', 1.0),
    }
    return params


def _round(value: Any, digits: int) -> float | None:
    """可空浮点四舍五入，供稳定 JSON 快照。"""
    if value is None:
        return None
    return round(float(value), digits)


def sanitize_cruise_point(point: dict[str, Any]) -> dict[str, Any]:
    """仪表盘巡航点：只保留界面需要的字段并四舍五入。"""
    return {
        'id': point.get('id'),
        'label': point.get('label'),
        'mach': _round(point.get('mach'), 4),
        'feasible': bool(point.get('feasible')),
        'fail_reason': point.get('fail_reason'),
        'alt_m': _round(point.get('alt_m'), 1),
        'ld': _round(point.get('ld'), 4),
        'thrust_avail_kN': _round(point.get('thrust_avail_kN'), 3),
        'load': _round(point.get('load'), 4),
        'eta_th': _round(point.get('eta_th'), 6),
        'eta_p': _round(point.get('eta_p'), 6),
        'eta_o': _round(point.get('eta_o'), 6),
        'score': _round(point.get('score'), 6),
        'radius_km': _round(point.get('radius_km'), 2),
        'fuel_kg_per_km': _round(point.get('fuel_kg_per_km'), 3),
        'mixed_radius_km': _round(point.get('mixed_radius_km'), 2),
        'mixed_fuel_kg_per_km': _round(point.get('mixed_fuel_kg_per_km'), 3),
        'tsfc_mg_n_s': _round(point.get('tsfc_mg_n_s'), 3),
        'max_ld': _round(point.get('max_ld'), 4),
        'max_ld_alt_m': _round(point.get('max_ld_alt_m'), 1),
        'max_ld_thrust_mode': point.get('max_ld_thrust_mode'),
    }


def sanitize_max_speed(block: dict[str, Any] | None) -> dict[str, Any]:
    """极速摘要四舍五入。"""
    block = block or {}
    return {
        'success': bool(block.get('success', True)),
        'feasible': block.get('feasible'),
        'fail_reason': block.get('fail_reason'),
        'max_speed_mach': _round(block.get('max_speed_mach'), 4),
        'max_speed_kmh': _round(block.get('max_speed_kmh'), 1),
        'max_speed_kts': _round(block.get('max_speed_kts'), 1),
        'alt_m': _round(block.get('alt_m'), 1),
        'ld': _round(block.get('ld'), 4),
        'load': _round(block.get('load'), 4),
        'thrust_avail_kN': _round(block.get('thrust_avail_kN'), 3),
    }


def sanitize_dashboard(result: dict[str, Any]) -> dict[str, Any]:
    """压缩仪表盘结果，去掉 Cf0/k_e 等黑箱标定数字。"""
    if not result.get('success'):
        return {
            'success': False,
            'error': result.get('error') or '仪表盘计算失败',
        }
    return {
        'success': True,
        'name': result.get('name'),
        'carrier': bool(result.get('carrier')),
        'max_cruise_mach': _round(result.get('max_cruise_mach'), 4),
        'max_cruise_floor_mach': _round(result.get('max_cruise_floor_mach'), 4),
        'max_radius_mach': _round(result.get('max_radius_mach'), 4),
        'max_radius_km': _round(result.get('max_radius_km'), 2),
        'fuel_kg': _round(result.get('fuel_kg'), 1),
        'fuel_usable_kg': _round(result.get('fuel_usable_kg'), 1),
        'n_engines': result.get('n_engines'),
        'points': [sanitize_cruise_point(p) for p in (result.get('points') or [])],
        'max_speed': sanitize_max_speed(result.get('max_speed')),
    }


def run_preset_dashboard(aircraft_id: str) -> dict[str, Any]:
    """按机型 id 跑默认仪表盘；缺发动机或军推时返回失败结构。"""
    aircraft = get_preset_by_id(load_presets(), aircraft_id)
    if aircraft is None:
        return {'success': False, 'error': f'找不到机型 {aircraft_id}'}
    engine_id = aircraft.get('engine_id')
    if not engine_id:
        return {'success': False, 'error': '未绑定发动机'}
    engine = get_preset_by_id(load_engine_presets(), str(engine_id))
    if engine is None:
        return {'success': False, 'error': f'找不到发动机 {engine_id}'}
    if engine.get('tsl_kN') in (None, '') and engine.get('max_tsl_kN') in (None, ''):
        return {'success': False, 'error': '缺少海平面军推 tsl_kN'}
    try:
        raw = run_aircraft_dashboard_from_params(dashboard_params_from_preset(aircraft, engine))
    except Exception as exc:
        return {'success': False, 'error': str(exc)}
    return sanitize_dashboard(raw)


def build_combat_radius_results_payload() -> dict[str, Any]:
    """为全部机型生成预计算仪表盘。"""
    ui = ui_config()
    aircraft_map: dict[str, Any] = {}
    for item in load_presets():
        aircraft_map[item['id']] = run_preset_dashboard(item['id'])
    return {
        'version': RESULTS_VERSION,
        'aircraft': aircraft_map,
    }


def write_combat_radius_results(path: str | Path | None = None) -> Path:
    """写入预计算 JSON，返回路径。"""
    out = Path(path) if path is not None else COMBAT_RADIUS_RESULTS_JSON
    payload = build_combat_radius_results_payload()
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return out


def load_combat_radius_results(path: str | Path | None = None) -> dict[str, Any]:
    """读取已生成的预计算 JSON；文件不存在时返回空表。"""
    src = Path(path) if path is not None else COMBAT_RADIUS_RESULTS_JSON
    if not src.is_file():
        return {'version': 0, 'aircraft': {}}
    return json.loads(src.read_text(encoding='utf-8'))


def build_combat_radius_results_catalog_payload() -> dict[str, Any]:
    """前端 catalog 用预计算片段。"""
    return load_combat_radius_results()
