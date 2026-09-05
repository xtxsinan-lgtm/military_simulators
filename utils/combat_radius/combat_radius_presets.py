"""作战半径机型几何预设（源自统一机型库 data/aircraft_database.csv）。

前端经 build_all → data.json 的 combat_radius_presets 自动同步。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from utils.combat_radius.lift_drag import Aircraft, aircraft_from_dict, aircraft_to_dict
from utils.database_csv import load_combat_radius_aircraft_csv, load_combat_radius_engine_csv
from utils.paths import COMBAT_RADIUS_AIRCRAFT_CSV, COMBAT_RADIUS_ENGINE_CSV

_INJECTED_AIRCRAFT: list[dict[str, Any]] | None = None
_INJECTED_ENGINES: list[dict[str, Any]] | None = None


def inject_combat_radius_presets(
    aircraft: list[dict[str, Any]] | None = None,
    engines: list[dict[str, Any]] | None = None,
) -> None:
    """注入机型/发动机预设（Pyodide / 测试用）；优先于 CSV。"""
    global _INJECTED_AIRCRAFT, _INJECTED_ENGINES
    if aircraft is not None:
        _INJECTED_AIRCRAFT = [dict(item) for item in aircraft]
    if engines is not None:
        _INJECTED_ENGINES = [dict(item) for item in engines]


def clear_injected_combat_radius_presets() -> None:
    """清除注入的预设，恢复从 CSV 加载。"""
    global _INJECTED_AIRCRAFT, _INJECTED_ENGINES
    _INJECTED_AIRCRAFT = None
    _INJECTED_ENGINES = None


def load_presets(path: str | Path | None = None) -> list[dict[str, Any]]:
    """加载机型几何预设；注入优先于默认 CSV；显式路径仍读文件。"""
    if path is None and _INJECTED_AIRCRAFT is not None:
        return [dict(item) for item in _INJECTED_AIRCRAFT]
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


def _preset_sort_key(item: dict[str, Any]) -> tuple[str, str, str]:
    """选择器排序键：国别 → 名称 → id（大小写不敏感）。"""
    return (
        (item.get('nation') or '').strip().casefold(),
        (item.get('name') or '').strip().casefold(),
        (item.get('id') or '').strip().casefold(),
    )


def sort_presets_by_nation_then_name(
    presets: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """按国别再按名称字母序排列机型预设（不修改入参）。"""
    return sorted(presets, key=_preset_sort_key)


def preset_select_label(preset: dict[str, Any]) -> str:
    """选择器显示名：有国别时为「国别 · 名称」。"""
    nation = (preset.get('nation') or '').strip()
    name = (preset.get('name') or '').strip()
    if nation:
        return f'{nation} · {name}'
    return name


def selected_aircraft_name(
    preset: dict[str, Any] | None,
    fallback: str = '未命名',
) -> str:
    """机型显示名取自预设；选择器已展示机型，表单不再另开名称栏。"""
    if not preset:
        return fallback
    name = str(preset.get('name') or '').strip()
    return name or fallback


def preset_to_aircraft_dict(preset: dict[str, Any]) -> dict[str, Any]:
    """预设记录 → Aircraft 字段字典（去掉 id/nation/ld_known/notes）。"""
    ac = aircraft_from_dict(preset)
    return aircraft_to_dict(ac)


def preset_to_aircraft(preset: dict[str, Any]) -> Aircraft:
    """预设记录 → Aircraft。"""
    return aircraft_from_dict(preset)


def build_combat_radius_presets_payload(path: str | Path | None = None) -> list[dict[str, Any]]:
    """构建前端/小程序/iOS 共用的作战半径机型预设列表（按国别再按名称排序）。"""
    return sort_presets_by_nation_then_name(load_presets(path))


def load_engine_presets(path: str | Path | None = None) -> list[dict[str, Any]]:
    """加载发动机预设；注入优先于默认 CSV；显式路径仍读文件。"""
    if path is None and _INJECTED_ENGINES is not None:
        return [dict(item) for item in _INJECTED_ENGINES]
    csv_path = Path(path) if path is not None else COMBAT_RADIUS_ENGINE_CSV
    if not csv_path.is_file():
        return []
    return load_combat_radius_engine_csv(csv_path)


def build_combat_radius_engine_presets_payload(path: str | Path | None = None) -> list[dict[str, Any]]:
    """构建前端/小程序/iOS 共用的发动机预设列表。"""
    return list(load_engine_presets(path))
