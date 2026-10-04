"""作战半径界面：机型外挂挂载示意图映射。"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from utils.paths import COMBAT_RADIUS_LOADOUT_DIR, COMBAT_RADIUS_LOADOUT_IMAGES_JSON

_INJECTED: dict[str, Any] | None = None


def inject_combat_radius_loadout_images(payload: dict[str, Any]) -> None:
    """注入挂载图映射（测试用）；优先于磁盘文件。"""
    global _INJECTED
    _INJECTED = dict(payload)
    load_combat_radius_loadout_images.cache_clear()


def load_combat_radius_loadout_images(path: str | Path | None = None) -> dict[str, Any]:
    """加载机型 id → 图片文件名映射。"""
    if _INJECTED is not None:
        return dict(_INJECTED)
    p = Path(path) if path is not None else COMBAT_RADIUS_LOADOUT_IMAGES_JSON
    return json.loads(p.read_text(encoding='utf-8'))


load_combat_radius_loadout_images = lru_cache(maxsize=1)(load_combat_radius_loadout_images)


def loadout_image_filename(aircraft_id: str | None) -> str | None:
    """按机型 id 返回挂载图文件名；无图则 None。"""
    aid = str(aircraft_id or '').strip()
    if not aid:
        return None
    aircraft = load_combat_radius_loadout_images().get('aircraft') or {}
    raw = aircraft.get(aid)
    if raw is None:
        return None
    name = str(raw).strip()
    return name or None


def build_combat_radius_loadout_images_payload() -> dict[str, Any]:
    """构建前端/小程序/iOS 共用的挂载图映射片段。"""
    raw = load_combat_radius_loadout_images()
    return {
        'version': int(raw.get('version', 1)),
        'aircraft': {str(k): str(v) for k, v in (raw.get('aircraft') or {}).items()},
    }


def list_loadout_image_files() -> list[Path]:
    """列出 data/combat_radius_loadout/ 下全部挂载图源文件。"""
    if not COMBAT_RADIUS_LOADOUT_DIR.is_dir():
        return []
    return sorted(COMBAT_RADIUS_LOADOUT_DIR.glob('*.jpg'))
