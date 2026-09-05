"""作战半径仿真默认参数 — 从 data/combat_radius_config.json 加载。"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from utils.paths import COMBAT_RADIUS_CONFIG_JSON

_INJECTED: dict[str, Any] | None = None


def inject_combat_radius_config(cfg: dict[str, Any]) -> None:
    """注入配置（Pyodide / 测试用）；优先于磁盘文件。"""
    global _INJECTED
    _INJECTED = dict(cfg)
    load_combat_radius_config.cache_clear()


def load_combat_radius_config(path: str | Path | None = None) -> dict[str, Any]:
    """加载作战半径配置 JSON；路径缺省为 data/combat_radius_config.json。"""
    if _INJECTED is not None:
        return dict(_INJECTED)
    p = Path(path) if path is not None else COMBAT_RADIUS_CONFIG_JSON
    return json.loads(p.read_text(encoding='utf-8'))


# lru_cache 包一层，便于 inject 时 cache_clear
load_combat_radius_config = lru_cache(maxsize=1)(load_combat_radius_config)


def ui_config() -> dict[str, Any]:
    """界面默认锚点与目标 L/D。"""
    return dict(load_combat_radius_config()['ui'])


def planform_labels() -> dict[str, str]:
    """翼型 id → 中文显示名。"""
    return dict(load_combat_radius_config().get('planform_labels', {}))


def layout_labels() -> dict[str, str]:
    """布局 id → 中文显示名。"""
    return dict(load_combat_radius_config().get('layout_labels', {}))


def inlet_labels() -> dict[str, str]:
    """进气道 id → 中文显示名。"""
    return dict(load_combat_radius_config().get('inlet_labels', {}))


def store_mount_labels() -> dict[str, str]:
    """挂装方式 id → 中文显示名。"""
    return dict(load_combat_radius_config().get('store_mount_labels', {}))


def mission_fuel_config() -> dict[str, Any]:
    """降落冗余、爬升额外与降落节省的默认参数。"""
    return dict(load_combat_radius_config()['mission_fuel'])


def dry_to_max_thrust_ratio() -> float:
    """军推/加力默认比例：发动机只给了加力时，用此比例反推海平面军推。"""
    engine = load_combat_radius_config().get('engine') or {}
    raw = engine.get('dry_to_max_thrust_ratio', 0.7)
    try:
        ratio = float(raw)
    except (TypeError, ValueError):
        return 0.7
    if ratio <= 0.0 or ratio > 1.0:
        return 0.7
    return ratio


F135_TSFC_TOGGLE_AIRCRAFT_IDS = ('F-35A', 'F-35B', 'F-35C')
F135_TSFC_TOGGLE_PUBLISHED = 1.22
F135_TSFC_TOGGLE_LPC_ONLY = 1.04
F135_TSFC_TOGGLE_PUBLISHED_LABEL = '×1.22 公开军推'
F135_TSFC_TOGGLE_LPC_ONLY_LABEL = '×1.04 仅低压压气机'
F135_TSFC_TOGGLE_NOTE = (
    '1.22 按公开军推 TSFC 相对 F100 的差距；'
    '1.04 只计低压压气机为垂起榨功做的设计妥协（巡航不抽升力风扇）。'
)


def f135_tsfc_toggle_config() -> dict[str, Any]:
    """F-35 油耗惩罚切换：公开军推 1.22 与仅低压压气机 1.04。"""
    raw = load_combat_radius_config().get('f135_tsfc_toggle') or {}
    ids = raw.get('aircraft_ids') or list(F135_TSFC_TOGGLE_AIRCRAFT_IDS)
    return {
        'aircraft_ids': [str(x) for x in ids],
        'published': float(raw.get('published', F135_TSFC_TOGGLE_PUBLISHED)),
        'lpc_only': float(raw.get('lpc_only', F135_TSFC_TOGGLE_LPC_ONLY)),
        'published_label': str(raw.get('published_label') or F135_TSFC_TOGGLE_PUBLISHED_LABEL),
        'lpc_only_label': str(raw.get('lpc_only_label') or F135_TSFC_TOGGLE_LPC_ONLY_LABEL),
        'note': str(raw.get('note') or F135_TSFC_TOGGLE_NOTE),
    }


def shows_f135_tsfc_toggle(aircraft_id: str | None) -> bool:
    """仅 F-35A/B/C 显示油耗惩罚切换。"""
    return str(aircraft_id or '') in set(f135_tsfc_toggle_config()['aircraft_ids'])


def f135_tsfc_install_mult_for_mode(mode: str | None) -> float:
    """按切换档返回 TSFC 乘数；非法档回退公开军推 1.22。"""
    cfg = f135_tsfc_toggle_config()
    if str(mode or '') == 'lpc_only':
        return float(cfg['lpc_only'])
    return float(cfg['published'])


def resolve_ui_tsfc_install_mult(
    aircraft_id: str | None,
    mode: str | None = None,
    engine_mult: float | None = None,
) -> float:
    """界面选定的 TSFC 乘数：F-35 三型用切换档，其余用发动机预设。"""
    if shows_f135_tsfc_toggle(aircraft_id):
        return f135_tsfc_install_mult_for_mode(mode)
    if engine_mult is None:
        return 1.0
    val = float(engine_mult)
    if val <= 0:
        raise ValueError('TSFC 乘数须为正')
    return val


def build_combat_radius_config_payload() -> dict[str, Any]:
    """构建前端/小程序/iOS 共用的作战半径配置片段。"""
    cfg = load_combat_radius_config()
    return {
        'version': cfg.get('version', 1),
        'ui': dict(cfg['ui']),
        'planform_labels': dict(cfg.get('planform_labels', {})),
        'layout_labels': dict(cfg.get('layout_labels', {})),
        'inlet_labels': dict(cfg.get('inlet_labels', {})),
        'store_mount_labels': dict(cfg.get('store_mount_labels', {})),
        'mission_fuel': dict(cfg.get('mission_fuel', {})),
        'engine': dict(cfg.get('engine', {})),
        'f135_tsfc_toggle': f135_tsfc_toggle_config(),
    }


# 垂起 / 倾转不走舰载弹射那套 45 min 余油（虽挂在航母上，但按陆基 30 min）
LAND_RESERVE_TYPE_LABELS = frozenset({'v/stol', 'tiltrotor'})


def uses_land_fuel_reserve(type_label: str | None) -> bool:
    """垂起与倾转旋翼按陆基余油，不走舰载 45 min。"""
    return str(type_label or '').strip().lower() in LAND_RESERVE_TYPE_LABELS


def reserve_min_for_mission(carrier: bool, type_label: str | None = None) -> float:
    """弹射/滑跃舰载 45 min；陆基、垂起、倾转 30 min。"""
    mf = mission_fuel_config()
    if uses_land_fuel_reserve(type_label) or not carrier:
        return float(mf['land_reserve_min'])
    return float(mf['carrier_reserve_min'])


def reserve_kind_label(carrier: bool, type_label: str | None = None) -> str:
    """任务油量说明里的余油类别。"""
    if uses_land_fuel_reserve(type_label):
        return '垂起'
    return '舰载' if carrier else '陆基'
