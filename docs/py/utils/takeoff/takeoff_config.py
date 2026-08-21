"""航母舰载机起飞仿真默认参数 — 从 data/takeoff_config.json 加载。"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from utils.paths import TAKEOFF_CONFIG_JSON

_INJECTED: dict[str, Any] | None = None


def inject_takeoff_config(cfg: dict[str, Any]) -> None:
    """注入配置（Pyodide / 测试用）；优先于磁盘文件。"""
    global _INJECTED
    _INJECTED = dict(cfg)
    load_takeoff_config.cache_clear()


@lru_cache(maxsize=1)
def load_takeoff_config(path: str | Path | None = None) -> dict[str, Any]:
    """加载起飞配置 JSON；路径缺省为 data/takeoff_config.json。"""
    if _INJECTED is not None:
        return dict(_INJECTED)
    p = Path(path) if path is not None else TAKEOFF_CONFIG_JSON
    return json.loads(p.read_text(encoding='utf-8'))


def shared_config() -> dict[str, Any]:
    return dict(load_takeoff_config()['shared'])


def physics_config() -> dict[str, Any]:
    return dict(load_takeoff_config()['physics'])


def ui_config() -> dict[str, Any]:
    return dict(load_takeoff_config()['ui'])


def mode_config(mode: str) -> dict[str, Any]:
    """返回指定模式的配置，并注入共享 mu 等字段。"""
    cfg = load_takeoff_config()
    data = dict(cfg['modes'][mode])
    data['mu'] = cfg['shared']['mu']
    return data


def cfg_range(spec: dict[str, int]) -> range:
    """将 {start,end,step} 转为 Python range。"""
    return range(spec['start'], spec['end'], spec['step'])


def build_takeoff_config_payload() -> dict[str, Any]:
    """构建前端/小程序/iOS 共用的起飞配置片段。"""
    cfg = load_takeoff_config()
    return {
        'version': cfg.get('version', 1),
        'shared': dict(cfg['shared']),
        'physics': dict(cfg['physics']),
        'ui': dict(cfg['ui']),
           'modes': {name: dict(mode) for name, mode in cfg['modes'].items()},
           'stovl_strategy_descriptions': dict(cfg.get('stovl_strategy_descriptions', {})),
           'tiltrotor_strategy_descriptions': dict(cfg.get('tiltrotor_strategy_descriptions', {})),
    }
