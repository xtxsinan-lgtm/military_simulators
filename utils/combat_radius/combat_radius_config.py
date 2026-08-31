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


def build_combat_radius_config_payload() -> dict[str, Any]:
    """构建前端/小程序/iOS 共用的作战半径配置片段。"""
    cfg = load_combat_radius_config()
    return {
        'version': cfg.get('version', 1),
        'ui': dict(cfg['ui']),
        'planform_labels': dict(cfg.get('planform_labels', {})),
        'layout_labels': dict(cfg.get('layout_labels', {})),
        'inlet_labels': dict(cfg.get('inlet_labels', {})),
        'mission_fuel': dict(cfg.get('mission_fuel', {})),
        'engine': dict(cfg.get('engine', {})),
    }
