"""在弹长与起飞质量上限内，为给定弹种搜索射程最大的弹长和弹径。"""
from __future__ import annotations

from typing import Any

from utils.missile_range.classes import estimate_by_class, resolve_missile_class

# 轰-6 机腹放开后的外形上限：弹长不超过 12 m，起飞质量不超过 10 t。
H6_BELLY_MAX_BAY = '轰-6机腹最大'
H6_BELLY_MAX_LENGTH_M = 12.0
H6_BELLY_MAX_MASS_T = 10.0


def _inclusive_grid_m(low_m: float, high_m: float, step_m: float) -> list[float]:
    """生成含两端的长度或直径网格，单位米。"""
    if step_m <= 0:
        raise ValueError('搜索步长必须大于 0')
    if high_m < low_m:
        raise ValueError('搜索上限不能小于下限')
    low = round(low_m * 10000)
    high = round(high_m * 10000)
    step = round(step_m * 10000)
    if step < 1:
        raise ValueError('搜索步长过小')
    values = list(range(low, high + 1, step))
    if values[-1] != high:
        values.append(high)
    return [value / 10000 for value in values]


def optimize_missile_envelope(
    missile_class: str,
    warhead_mass_kg: float,
    *,
    max_length_m: float = H6_BELLY_MAX_LENGTH_M,
    max_mass_t: float = H6_BELLY_MAX_MASS_T,
    v_launch_mach: float = 0.85,
    h_launch_km: float = 13.0,
    min_length_m: float = 4.0,
    min_diameter_m: float = 0.40,
    max_diameter_m: float = 2.0,
    length_step_m: float = 0.5,
    diameter_step_m: float = 0.1,
) -> dict[str, Any]:
    """在弹长不超过上限、起飞质量不超过上限时，搜索射程最大的弹长与弹径。

    弹径没有单独的硬上限，由调用方给出搜索范围；超重或估不出来的点跳过。
    射程相同时优先用更长的弹，其次用更粗的弹。
    """
    if max_length_m <= 0 or max_mass_t <= 0:
        raise ValueError('弹长上限与起飞质量上限必须大于 0')
    if warhead_mass_kg < 0:
        raise ValueError('战斗部质量不能为负')
    if min_diameter_m <= 0 or max_diameter_m <= 0:
        raise ValueError('弹径搜索范围必须大于 0')
    canon = resolve_missile_class(missile_class)
    lengths = _inclusive_grid_m(min_length_m, max_length_m, length_step_m)
    diameters = _inclusive_grid_m(min_diameter_m, max_diameter_m, diameter_step_m)
    best: dict[str, Any] | None = None
    for length_m in lengths:
        for diameter_m in diameters:
            try:
                result = estimate_by_class(
                    canon, length_m, diameter_m, warhead_mass_kg,
                    v_launch_mach, h_launch_km,
                )
            except ValueError:
                continue
            if float(result['m_0_t']) > max_mass_t:
                continue
            candidate = {
                'missile_class': canon,
                'length_m': length_m,
                'diameter_m': diameter_m,
                'warhead_kg': float(warhead_mass_kg),
                'm_0_t': float(result['m_0_t']),
                'range_km': float(result['range_km']),
                'result': result,
            }
            if best is None or _envelope_rank(candidate) > _envelope_rank(best):
                best = candidate
    if best is None:
        raise ValueError('在弹长和起飞质量上限内没有可用尺寸')
    return best


def _envelope_rank(row: dict[str, Any]) -> tuple[float, float, float]:
    """射程优先，其次弹长，再次弹径。"""
    return (float(row['range_km']), float(row['length_m']), float(row['diameter_m']))
