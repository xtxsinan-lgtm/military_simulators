"""作战半径推进类型判定与默认搜索包线。"""
from __future__ import annotations

from typing import Any

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from utils.combat_radius.cruise_search import CruiseContext

PROPULSION_TURBOPROP = 'turboprop'
PROPULSION_TURBOFAN = 'turbofan'

TURBOPROP_FIXED_MACHS = (0.35, 0.4, 0.45, 0.5, 0.55, 0.6)
TURBOPROP_ALT_MIN_M = 3000.0
TURBOPROP_ALT_MAX_M = 12000.0
TURBOPROP_MACH_SEARCH_LO = 0.35
TURBOPROP_MACH_SEARCH_HI = 0.62
TURBOPROP_PRACTICAL_MAX_CRUISE_MACH_LO = 0.45


def normalize_propulsion(raw: Any) -> str:
    """解析推进类型字符串。"""
    text = str(raw or PROPULSION_TURBOFAN).strip().lower()
    if text in ('turboprop', 'prop', '涡桨'):
        return PROPULSION_TURBOPROP
    return PROPULSION_TURBOFAN


def propulsion_from_params(params: dict[str, Any]) -> str:
    """从请求参数或嵌套发动机字段读取推进类型。"""
    if params.get('propulsion') not in (None, ''):
        return normalize_propulsion(params['propulsion'])
    engine = params.get('engine')
    if isinstance(engine, dict) and engine.get('propulsion') not in (None, ''):
        return normalize_propulsion(engine['propulsion'])
    return PROPULSION_TURBOFAN


def is_turboprop_params(params: dict[str, Any]) -> bool:
    """是否为涡桨推进配置。"""
    return propulsion_from_params(params) == PROPULSION_TURBOPROP


def is_turboprop_context(ctx: 'CruiseContext') -> bool:
    """巡航上下文是否为涡桨。"""
    return normalize_propulsion(getattr(ctx, 'propulsion', PROPULSION_TURBOFAN)) == PROPULSION_TURBOPROP


def cruise_envelope_defaults(params: dict[str, Any]) -> dict[str, Any]:
    """按推进类型返回马赫/高度搜索缺省值。"""
    if is_turboprop_params(params):
        return {
            'fixed_machs': TURBOPROP_FIXED_MACHS,
            'alt_min_m': TURBOPROP_ALT_MIN_M,
            'alt_max_m': TURBOPROP_ALT_MAX_M,
            'mach_search_lo': TURBOPROP_MACH_SEARCH_LO,
            'mach_search_hi': TURBOPROP_MACH_SEARCH_HI,
            'mach_search_iters': 14,
            'practical_max_cruise_mach_lo': TURBOPROP_PRACTICAL_MAX_CRUISE_MACH_LO,
            'alt_coarse_m': 500.0,
            'alt_refine_m': 200.0,
        }
    from utils.combat_radius.cruise_search import (
        ALT_COARSE_M,
        ALT_MAX_M,
        ALT_MIN_M,
        ALT_REFINE_M,
        FIXED_MACHS,
        MACH_SEARCH_HI,
        MACH_SEARCH_ITERS,
        MACH_SEARCH_LO,
        PRACTICAL_MAX_CRUISE_MACH_LO,
    )

    return {
        'fixed_machs': FIXED_MACHS,
        'alt_min_m': ALT_MIN_M,
        'alt_max_m': ALT_MAX_M,
        'mach_search_lo': MACH_SEARCH_LO,
        'mach_search_hi': MACH_SEARCH_HI,
        'mach_search_iters': MACH_SEARCH_ITERS,
        'practical_max_cruise_mach_lo': PRACTICAL_MAX_CRUISE_MACH_LO,
        'alt_coarse_m': ALT_COARSE_M,
        'alt_refine_m': ALT_REFINE_M,
    }
