"""作战半径任务剖面：高-高-高、高-低-高、低-低-低。

剖面影响任务油量开销（爬升额外 / 降落节省）以及布雷盖半径的巡航段组合。
"""
from __future__ import annotations

from typing import Any

from utils.combat_radius.breguet import combat_radius_m, hi_lo_hi_combat_radius_m
from utils.combat_radius.combat_radius_config import load_combat_radius_config
from utils.combat_radius.cruise_search import (
    ALT_COARSE_M,
    ALT_MAX_M,
    ALT_MIN_M,
    ALT_REFINE_M,
    CruiseContext,
    search_best_altitude,
)

# 低-低-低 / 高-低-高 的低空段搜索带（m）
LOW_ALT_MIN_M = 300.0
LOW_ALT_MAX_M = 3000.0
LOW_ALT_COARSE_M = 500.0
LOW_ALT_REFINE_M = 100.0

# 高-低-高 低空段默认用 Ma 0.8（超音速低空通常不可飞）
HI_LO_HI_LOW_MACH = 0.8
# 高-低-高 目标区低空突防段单程距离（km）；进、出各一段
HI_LO_HI_LOW_LEG_KM = 150.0

DEFAULT_PROFILE_ID = 'hi_hi_hi'
PROFILE_IDS = ('hi_hi_hi', 'hi_lo_hi', 'lo_lo_lo')

_BUILTIN_PROFILES: dict[str, dict[str, Any]] = {
    'hi_hi_hi': {
        'label': '高-高-高',
        'mode': 'symmetric_high',
        'climb_extra_km': 120.0,
        'descent_save_km': 87.5,
        'note': '进出与巡航均在高空；爬升/降落开销按标准 120 / 87.5 km 等价油耗入账。',
    },
    'hi_lo_hi': {
        'label': '高-低-高',
        'mode': 'mixed_high_low',
        'climb_extra_km': 180.0,
        'descent_save_km': 50.0,
        'low_leg_km': HI_LO_HI_LOW_LEG_KM,
        'note': '高空进出，目标区前后各 150 km 低空突防/撤出；额外爬升/下降按 180 / 50 km 等价油耗入账。',
    },
    'lo_lo_lo': {
        'label': '低-低-低',
        'mode': 'symmetric_low',
        'climb_extra_km': 30.0,
        'descent_save_km': 25.0,
        'note': '全程低空贴地/掠海；爬升/降落开销按 30 / 25 km 等价油耗入账；半径在 0.3–3 km 带搜索最佳巡航。',
    },
}


def _profiles_from_config() -> dict[str, dict[str, Any]]:
    """合并 JSON 配置与内置默认值。"""
    cfg = load_combat_radius_config().get('flight_profiles') or {}
    raw = cfg.get('profiles') or {}
    merged: dict[str, dict[str, Any]] = {}
    for pid in PROFILE_IDS:
        base = dict(_BUILTIN_PROFILES[pid])
        override = raw.get(pid) or {}
        base.update({k: v for k, v in override.items() if v is not None})
        base['id'] = pid
        merged[pid] = base
    return merged


def default_flight_profile_id() -> str:
    """默认剖面 id（缺省高-高-高）。"""
    cfg = load_combat_radius_config().get('flight_profiles') or {}
    raw = str(cfg.get('default') or DEFAULT_PROFILE_ID).strip()
    return raw if raw in PROFILE_IDS else DEFAULT_PROFILE_ID


def resolve_flight_profile(profile_id: str | None) -> dict[str, Any]:
    """解析剖面 id，非法值回退默认。"""
    pid = str(profile_id or '').strip() or default_flight_profile_id()
    profiles = _profiles_from_config()
    if pid not in profiles:
        pid = default_flight_profile_id()
    return dict(profiles[pid])


def flight_profile_options() -> list[dict[str, Any]]:
    """前端/小程序/iOS 共用的剖面列表（固定顺序）。"""
    profiles = _profiles_from_config()
    return [
        {
            'id': pid,
            'label': profiles[pid]['label'],
            'note': profiles[pid].get('note'),
        }
        for pid in PROFILE_IDS
    ]


def profile_mission_fuel_km(profile_id: str | None) -> tuple[float, float]:
    """返回 (climb_extra_km, descent_save_km)。"""
    prof = resolve_flight_profile(profile_id)
    return float(prof['climb_extra_km']), float(prof['descent_save_km'])


def search_low_altitude_point(
    ctx: CruiseContext,
    mach: float,
    alt_min_m: float = LOW_ALT_MIN_M,
    alt_max_m: float = LOW_ALT_MAX_M,
    coarse_m: float = LOW_ALT_COARSE_M,
    refine_m: float = LOW_ALT_REFINE_M,
) -> Any | None:
    """在低空带搜索最佳巡航点（L/D×η_o 最大且满足推力裕度）。"""
    if mach <= 0:
        raise ValueError('马赫数须为正')
    return search_best_altitude(ctx, mach, alt_min_m, alt_max_m, coarse_m, refine_m)


def _scored_usable(scored: Any) -> bool:
    """评分点是否可用于布雷盖。"""
    return (
        scored is not None
        and scored.tsfc_kg_n_s is not None
        and scored.v0 > 0
        and scored.ld > 0
        and scored.eta_o > 0
    )


def profile_combat_radius_m(
    profile: dict[str, Any],
    high_scored: Any,
    *,
    mach: float,
    mass_initial_kg: float,
    mass_final_kg: float,
    ctx: CruiseContext | None = None,
    low_scored: Any | None = None,
    alt_min_m: float = ALT_MIN_M,
    alt_max_m: float = ALT_MAX_M,
    coarse_m: float = ALT_COARSE_M,
    refine_m: float = ALT_REFINE_M,
) -> float:
    """按剖面模式由评分点估算作战半径（米）。"""
    mode = str(profile.get('mode') or 'symmetric_high')
    if mode == 'symmetric_high':
        if not _scored_usable(high_scored):
            raise ValueError('高空巡航点不可用')
        return combat_radius_m(
            high_scored.v0,
            high_scored.tsfc_kg_n_s,
            high_scored.ld,
            mass_initial_kg,
            mass_final_kg,
        )
    if ctx is None:
        raise ValueError('该剖面需要巡航搜索上下文')
    if mode == 'symmetric_low':
        low = low_scored
        if low is None:
            low = search_low_altitude_point(ctx, mach)
        if not _scored_usable(low):
            raise ValueError('低空巡航点不可用')
        return combat_radius_m(
            low.v0,
            low.tsfc_kg_n_s,
            low.ld,
            mass_initial_kg,
            mass_final_kg,
        )
    if mode == 'mixed_high_low':
        if not _scored_usable(high_scored):
            raise ValueError('高空巡航点不可用')
        low = low_scored
        if low is None:
            low_mach = mach if mach <= 1.0 else HI_LO_HI_LOW_MACH
            low = search_low_altitude_point(ctx, low_mach)
        if not _scored_usable(low):
            raise ValueError('低空突防点不可用')
        return hi_lo_hi_combat_radius_m(
            high_scored.v0,
            high_scored.tsfc_kg_n_s,
            high_scored.ld,
            low.v0,
            low.tsfc_kg_n_s,
            low.ld,
            mass_initial_kg,
            mass_final_kg,
            float(profile.get('low_leg_km', HI_LO_HI_LOW_LEG_KM)) * 1000.0,
        )
    raise ValueError(f'未知剖面模式: {mode}')
