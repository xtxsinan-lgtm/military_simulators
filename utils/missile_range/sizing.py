"""在弹长与起飞质量上限内，为给定弹种搜索射程最大的弹长和弹径。"""
from __future__ import annotations

from typing import Any

from utils.missile_range.classes import estimate_by_class, resolve_missile_class

# 隐身超音速轰炸机弹仓外形上限，按轰-6 发射条件寻优：弹长不超过 13 m，弹径不超过 1 m，起飞质量不超过 15 t。
H6_BELLY_MAX_BAY = '隐身超音速轰炸机弹仓'
H6_BELLY_MAX_LENGTH_M = 13.0
H6_BELLY_MAX_DIAMETER_M = 1.0
H6_BELLY_MAX_MASS_T = 15.0


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
    max_diameter_m: float = H6_BELLY_MAX_DIAMETER_M,
    length_step_m: float = 0.5,
    diameter_step_m: float = 0.1,
) -> dict[str, Any]:
    """在弹长、弹径、起飞质量都不超过上限时，搜索射程最大的弹长与弹径。

    超重或估不出来的点跳过。射程相同时优先用更长的弹，其次用更粗的弹。
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


def _envelope_candidate(
    missile_class: str,
    length_m: float,
    diameter_m: float,
    warhead_mass_kg: float,
    *,
    max_length_m: float,
    max_diameter_m: float,
    max_mass_t: float,
    min_length_m: float,
    min_diameter_m: float,
    v_launch_mach: float,
    h_launch_km: float,
) -> dict[str, Any] | None:
    """估一个外形。超出弹长、弹径或起飞质量上限，以及估不出来时返回空。"""
    if (
        length_m < min_length_m - 1e-9 or length_m > max_length_m + 1e-9
        or diameter_m < min_diameter_m - 1e-9 or diameter_m > max_diameter_m + 1e-9
    ):
        return None
    try:
        result = estimate_by_class(
            missile_class, length_m, diameter_m, warhead_mass_kg,
            v_launch_mach, h_launch_km,
        )
    except ValueError:
        return None
    if float(result['m_0_t']) > max_mass_t + 1e-9:
        return None
    return {
        'missile_class': resolve_missile_class(missile_class),
        'length_m': length_m,
        'diameter_m': diameter_m,
        'warhead_kg': float(warhead_mass_kg),
        'm_0_t': float(result['m_0_t']),
        'range_km': float(result['range_km']),
        'result': result,
    }


def polish_missile_envelope(
    seed: dict[str, Any],
    warhead_mass_kg: float,
    *,
    max_length_m: float = H6_BELLY_MAX_LENGTH_M,
    max_mass_t: float = H6_BELLY_MAX_MASS_T,
    v_launch_mach: float = 0.85,
    h_launch_km: float = 13.0,
    min_length_m: float = 4.0,
    min_diameter_m: float = 0.40,
    max_diameter_m: float = H6_BELLY_MAX_DIAMETER_M,
    steps_m: tuple[float, ...] = (0.2, 0.05, 0.01),
) -> dict[str, Any]:
    """从已有外形出发，按逐步缩小的步长在邻域里继续找更远的射程。

    步长同时用于弹长和弹径。每档步长沿八个方向贪心移动，直到该步长不再变远。
    """
    if not steps_m or any(step <= 0 for step in steps_m):
        raise ValueError('抛光步长必须大于 0')
    missile_class = str(seed['missile_class'])
    best = _envelope_candidate(
        missile_class, float(seed['length_m']), float(seed['diameter_m']), warhead_mass_kg,
        max_length_m=max_length_m, max_diameter_m=max_diameter_m, max_mass_t=max_mass_t,
        min_length_m=min_length_m, min_diameter_m=min_diameter_m,
        v_launch_mach=v_launch_mach, h_launch_km=h_launch_km,
    )
    if best is None:
        raise ValueError('抛光起点超出弹长、弹径或起飞质量上限')
    offsets = (
        (1, 0), (-1, 0), (0, 1), (0, -1),
        (1, 1), (1, -1), (-1, 1), (-1, -1),
    )
    for step in steps_m:
        for _ in range(48):
            moved = False
            for length_sign, diameter_sign in offsets:
                candidate = _envelope_candidate(
                    missile_class,
                    round(best['length_m'] + length_sign * step, 4),
                    round(best['diameter_m'] + diameter_sign * step, 4),
                    warhead_mass_kg,
                    max_length_m=max_length_m, max_diameter_m=max_diameter_m,
                    max_mass_t=max_mass_t, min_length_m=min_length_m,
                    min_diameter_m=min_diameter_m,
                    v_launch_mach=v_launch_mach, h_launch_km=h_launch_km,
                )
                if candidate is not None and _envelope_rank(candidate) > _envelope_rank(best):
                    best = candidate
                    moved = True
                    break
            if not moved:
                break
    return best


def diameter_for_liftoff_mass(
    missile_class: str,
    length_m: float,
    warhead_mass_kg: float,
    target_mass_t: float,
    *,
    max_diameter_m: float,
    v_launch_mach: float,
    h_launch_km: float,
    min_diameter_m: float = 0.20,
    structure_v_mach: float | None = None,
    structure_h_km: float | None = None,
) -> dict[str, Any]:
    """在弹径上限内把起飞质量收到目标值。

    到上限仍然偏轻时取上限。质量随弹径增加；估不出来的过细弹径跳过。
    弹径收到 0.0001 m，并取不超过目标质量、又尽量贴近目标的那一档。
    给出 structure_v_mach / structure_h_km 时，助推切分和滑翔体按该发射条件搜索后冻结，
    再按 v_launch_mach / h_launch_km 核算起飞质量。
    """
    if length_m <= 0 or max_diameter_m <= 0 or min_diameter_m <= 0:
        raise ValueError('弹长与弹径搜索范围必须大于 0')
    if max_diameter_m < min_diameter_m:
        raise ValueError('弹径上限不能小于下限')
    if target_mass_t <= 0 or warhead_mass_kg < 0:
        raise ValueError('目标质量必须大于 0，战斗部不能为负')
    if (structure_v_mach is None) != (structure_h_km is None):
        raise ValueError('结构发射条件须同时给出马赫数和高度')
    canon = resolve_missile_class(missile_class)

    def at(diameter_m: float) -> dict[str, Any] | None:
        try:
            if structure_v_mach is None:
                result = estimate_by_class(
                    canon, length_m, diameter_m, warhead_mass_kg,
                    v_launch_mach, h_launch_km,
                )
            else:
                # 助推切分按结构发射条件定，质量按交付发射条件核算。
                from utils.missile_range.dataset import fit_locked_head, structure_lock_kwargs
                template = estimate_by_class(
                    canon, length_m, diameter_m, warhead_mass_kg,
                    float(structure_v_mach), float(structure_h_km),
                )
                lock = fit_locked_head(
                    structure_lock_kwargs(template),
                    length_m, diameter_m, warhead_mass_kg, canon,
                )
                result = estimate_by_class(
                    canon, length_m, diameter_m, warhead_mass_kg,
                    v_launch_mach, h_launch_km,
                    **lock,
                )
        except ValueError:
            return None
        return {
            'missile_class': canon,
            'length_m': length_m,
            'diameter_m': diameter_m,
            'warhead_kg': float(warhead_mass_kg),
            'm_0_t': float(result['m_0_t']),
            'range_km': float(result['range_km']),
            'result': result,
        }

    capped = at(max_diameter_m)
    if capped is None:
        raise ValueError('弹径上限处无法估算')
    if capped['m_0_t'] <= target_mass_t:
        return capped
    low = min_diameter_m
    high = max_diameter_m
    best = capped
    for _ in range(28):
        mid = (low + high) / 2.0
        row = at(mid)
        if row is None or row['m_0_t'] > target_mass_t:
            high = mid
            continue
        low = mid
        best = row
    rounded = round(low, 4)
    candidates = []
    step = 0.0001
    start = max(min_diameter_m, rounded - 0.0002)
    stop = min(max_diameter_m, rounded + 0.0002)
    probe = start
    while probe <= stop + 1e-9:
        row = at(round(probe, 4))
        if row is not None and row['m_0_t'] <= target_mass_t + 1e-9:
            candidates.append(row)
        probe += step
    if not candidates:
        if best['m_0_t'] > target_mass_t:
            raise ValueError('在弹径下限处起飞质量仍高于目标')
        return best
    return max(candidates, key=lambda row: (row['m_0_t'], row['diameter_m']))
