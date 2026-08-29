"""作战半径机型几何预设（源自统一机型库 data/aircraft_database.csv）。

前端经 build_all → data.json 的 combat_radius_presets 自动同步。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from utils.combat_radius.lift_drag import Aircraft, aircraft_from_dict, aircraft_to_dict
from utils.database_csv import load_combat_radius_aircraft_csv, load_combat_radius_engine_csv
from utils.paths import COMBAT_RADIUS_AIRCRAFT_CSV, COMBAT_RADIUS_ENGINE_CSV


def load_presets(path: str | Path | None = None) -> list[dict[str, Any]]:
    """加载机型几何预设；文件不存在时返回空列表（如 Pyodide 环境）。"""
    csv_path = Path(path) if path is not None else COMBAT_RADIUS_AIRCRAFT_CSV
    if not csv_path.is_file():
        return []
    return load_combat_radius_aircraft_csv(csv_path)


def get_preset_by_id(presets: list[dict[str, Any]], preset_id: str) -> dict[str, Any] | None:
    """按 id 查找预设；找不到返回 None。"""
    for item in presets:
        if item['id'] == preset_id:
            return item
    return None


def preset_to_aircraft_dict(preset: dict[str, Any]) -> dict[str, Any]:
    """预设记录 → Aircraft 字段字典（去掉 id/nation/ld_known/notes）。"""
    ac = aircraft_from_dict(preset)
    return aircraft_to_dict(ac)


def preset_to_aircraft(preset: dict[str, Any]) -> Aircraft:
    """预设记录 → Aircraft。"""
    return aircraft_from_dict(preset)


def build_combat_radius_presets_payload(path: str | Path | None = None) -> list[dict[str, Any]]:
    """构建前端/小程序/iOS 共用的作战半径机型预设列表。"""
    return list(load_presets(path))


def load_engine_presets(path: str | Path | None = None) -> list[dict[str, Any]]:
    """加载发动机预设；文件不存在时返回空列表（如 Pyodide 环境）。"""
    csv_path = Path(path) if path is not None else COMBAT_RADIUS_ENGINE_CSV
    if not csv_path.is_file():
        return []
    return load_combat_radius_engine_csv(csv_path)


def build_combat_radius_engine_presets_payload(path: str | Path | None = None) -> list[dict[str, Any]]:
    """构建前端/小程序/iOS 共用的发动机预设列表。"""
    return list(load_engine_presets(path))
