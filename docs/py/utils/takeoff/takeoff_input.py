"""起飞仿真输入校验与结果高亮卡片（三端共用结构化字段）。"""
from __future__ import annotations

from typing import Any

# 舰载起飞允许超过最大起飞重量的上限（仍仿真，但前端须提示）
MTOW_OVERLOAD_ALLOWANCE_KG = 3000.0


def _parse_mass(value: float | None) -> float | None:
    """解析重量；无法得到有限正负值时返回 None。"""
    if value is None:
        return None
    try:
        mass = float(value)
    except (TypeError, ValueError):
        return None
    if mass != mass:  # NaN
        return None
    return mass


def validate_takeoff_mass(
    mass_kg: float,
    mtow_kg: float,
    empty_kg: float | None = None,
) -> str | None:
    """校验起飞重量。合法（含超 MTOW 不超过 3 t）返回 None，否则返回中文错误。"""
    try:
        mass = float(mass_kg)
    except (TypeError, ValueError):
        return '请填写有效的起飞重量'
    if mass != mass:  # NaN
        return '请填写有效的起飞重量'
    if mass <= 0:
        return '起飞重量必须为正数'
    mtow = _parse_mass(mtow_kg)
    if mtow is not None and mass > mtow + MTOW_OVERLOAD_ALLOWANCE_KG + 1e-6:
        return (
            f'起飞重量 {mass:.0f} kg 超出最大起飞重量 {mtow:.0f} kg'
            f'（最多允许超重 {MTOW_OVERLOAD_ALLOWANCE_KG:.0f} kg）'
        )
    if empty_kg is not None:
        empty = _parse_mass(empty_kg)
        if empty is not None and mass + 1e-6 < empty:
            return f'起飞重量 {mass:.0f} kg 低于空重 {empty:.0f} kg'
    return None


def takeoff_mass_over_mtow_warning(
    mass_kg: float,
    mtow_kg: float,
) -> str | None:
    """超过 MTOW 但仍在 3 t 裕度内时返回提示；否则 None。"""
    mass = _parse_mass(mass_kg)
    mtow = _parse_mass(mtow_kg)
    if mass is None or mtow is None:
        return None
    if mass <= 0:
        return None
    if mass <= mtow + 1e-6:
        return None
    if mass > mtow + MTOW_OVERLOAD_ALLOWANCE_KG + 1e-6:
        return None
    over_kg = mass - mtow
    return (
        f'起飞重量已超过最大起飞重量 {mtow:.0f} kg'
        f'（超重 {over_kg:.0f} kg，仿真仍可进行）'
    )


def mass_range_hint(empty_kg: float | None, mtow_kg: float | None) -> str:
    """重量输入旁的合理范围文案，例如「范围：空重 14651 – MTOW 27200 kg（最多可超 3000 kg）」。"""
    parts: list[str] = []
    if empty_kg is not None:
        try:
            parts.append(f'空重 {float(empty_kg):.0f}')
        except (TypeError, ValueError):
            pass
    if mtow_kg is not None:
        try:
            parts.append(f'MTOW {float(mtow_kg):.0f}')
        except (TypeError, ValueError):
            pass
    if not parts:
        return ''
    hint = '范围：' + ' – '.join(parts) + ' kg'
    if mtow_kg is not None and _parse_mass(mtow_kg) is not None:
        hint += f'（最多可超 {MTOW_OVERLOAD_ALLOWANCE_KG:.0f} kg）'
    return hint


def _fmt_num(value: float, digits: int = 1) -> str:
    """格式化高亮卡片数值。"""
    return f'{float(value):.{digits}f}'


def build_takeoff_highlights(
    distance_m: float | None,
    deck_margin_m: float | None,
    exit_speed_mps: float | None,
    exit_time_s: float | None,
    deck_launch_ok: bool | None = None,
) -> list[dict[str, Any]]:
    """核心结果卡片：起飞距离、甲板余量、离舰速度、离舰用时。"""
    cards: list[dict[str, Any]] = []
    if distance_m is not None:
        cards.append({
            'key': 'distance',
            'label': '起飞距离',
            'value': f'{_fmt_num(distance_m, 1)} m',
            'tone': 'accent',
        })
    if deck_margin_m is not None:
        margin = float(deck_margin_m)
        if margin >= 0:
            cards.append({
                'key': 'margin',
                'label': '甲板余量',
                'value': f'{_fmt_num(margin, 1)} m',
                'tone': 'ok',
            })
        else:
            cards.append({
                'key': 'margin',
                'label': '超出甲板',
                'value': f'{_fmt_num(-margin, 1)} m',
                'tone': 'danger',
            })
    elif deck_launch_ok is False:
        cards.append({
            'key': 'margin',
            'label': '甲板起飞',
            'value': '不足',
            'tone': 'danger',
        })
    if exit_speed_mps is not None:
        cards.append({
            'key': 'speed',
            'label': '离舰速度',
            'value': f'{_fmt_num(exit_speed_mps, 1)} m/s',
            'tone': 'accent',
        })
    if exit_time_s is not None:
        cards.append({
            'key': 'time',
            'label': '离舰用时',
            'value': f'{_fmt_num(exit_time_s, 2)} s',
            'tone': 'accent',
        })
    return cards


def extract_exit_kinematics(result: dict[str, Any] | None) -> tuple[float | None, float | None]:
    """从仿真内层 result 读取离舰速度与用时。"""
    if not result:
        return None, None
    speed = result.get('v_deck_mps')
    if speed is None:
        speed = result.get('v_gs_mps')
    time_s = result.get('t_deck_s')
    if time_s is None:
        time_s = result.get('t_s')
    try:
        speed_f = float(speed) if speed is not None else None
    except (TypeError, ValueError):
        speed_f = None
    try:
        time_f = float(time_s) if time_s is not None else None
    except (TypeError, ValueError):
        time_f = None
    return speed_f, time_f
