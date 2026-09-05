"""空战重量、平飞阻力与发动机负载比。

空战重量 = 空重 + 内油×1/2 + 飞行员数×0.1 吨 + 4 枚中距弹。
平飞阻力 D = W / (L/D)；负载比 = D / 该高度速度下飞机最大可用推力。
"""
from __future__ import annotations

from typing import Any

G0 = 9.80665
PILOT_MASS_KG = 100.0  # 0.1 吨 / 人
N_MISSILES_DEFAULT = 4
FUEL_FRACTION_DEFAULT = 0.5


def combat_mass_kg(
    empty_kg: float,
    internal_fuel_kg: float,
    n_pilots: float = 1.0,
    missile_mass_kg: float = 0.0,
    n_missiles: float = N_MISSILES_DEFAULT,
    fuel_fraction: float = FUEL_FRACTION_DEFAULT,
    pilot_mass_kg: float = PILOT_MASS_KG,
) -> float:
    """按空战构型估算质量（kg）。"""
    if empty_kg < 0 or internal_fuel_kg < 0 or missile_mass_kg < 0:
        raise ValueError('空重、内油、弹重不能为负')
    if n_pilots < 0 or n_missiles < 0:
        raise ValueError('飞行员数与挂弹数不能为负')
    if fuel_fraction < 0 or fuel_fraction > 1:
        raise ValueError('内油使用比例须在 [0, 1] 内')
    if pilot_mass_kg < 0:
        raise ValueError('单名飞行员质量不能为负')
    return (
        empty_kg
        + fuel_fraction * internal_fuel_kg
        + n_pilots * pilot_mass_kg
        + n_missiles * missile_mass_kg
    )


def wing_loading_t_m2(
    empty_kg: float,
    internal_fuel_kg: float,
    wing_area_m2: float,
    n_pilots: float = 1.0,
    missile_mass_kg: float = 0.0,
    n_missiles: float = N_MISSILES_DEFAULT,
    fuel_fraction: float = FUEL_FRACTION_DEFAULT,
    pilot_mass_kg: float = PILOT_MASS_KG,
) -> float:
    """空战翼载荷 (t/m²) = 空战重量 / 翼面积。

    默认半油 + 飞行员×0.1 t + 4 枚中距弹；起飞满油重量见 AircraftSpec.a2a_mass_kg。
    """
    if wing_area_m2 <= 0:
        raise ValueError('翼面积须为正才能计算翼载荷')
    mass_t = combat_mass_kg(
        empty_kg, internal_fuel_kg, n_pilots, missile_mass_kg, n_missiles,
        fuel_fraction, pilot_mass_kg,
    ) / 1000.0
    return mass_t / wing_area_m2


def aspect_ratio_from_geometry(wingspan_m: float, wing_area_m2: float) -> float:
    """展弦比 AR = 翼展² / 参考翼面积。"""
    if wingspan_m <= 0 or wing_area_m2 <= 0:
        raise ValueError('翼展与翼面积须为正才能计算展弦比')
    return (wingspan_m ** 2) / wing_area_m2


def _optional_finite(value: Any) -> float | None:
    """空值视为未提供；无法解析则返回 None。"""
    if value in (None, ''):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def apply_combat_wing_loading(
    target: dict[str, Any],
    empty_kg: float,
    internal_fuel_kg: float,
    n_pilots: float = 1.0,
    missile_mass_kg: float = 0.0,
    n_missiles: float = N_MISSILES_DEFAULT,
    fuel_fraction: float = FUEL_FRACTION_DEFAULT,
    pilot_mass_kg: float = PILOT_MASS_KG,
) -> dict[str, Any]:
    """有翼面积时用空战重量覆盖 wing_loading，使升阻比与布雷盖用同一重量。"""
    out = dict(target)
    area = out.get('wing_area_m2')
    if area in (None, ''):
        return out
    area_f = float(area)
    if area_f <= 0:
        return out
    out['wing_loading'] = wing_loading_t_m2(
        empty_kg, internal_fuel_kg, area_f, n_pilots, missile_mass_kg,
        n_missiles, fuel_fraction, pilot_mass_kg,
    )
    return out


def apply_derived_planform_loads(
    target: dict[str, Any],
    empty_kg: float | None = None,
    internal_fuel_kg: float | None = None,
    n_pilots: float | None = None,
    missile_mass_kg: float | None = None,
    n_missiles: float = N_MISSILES_DEFAULT,
    fuel_fraction: float = FUEL_FRACTION_DEFAULT,
    pilot_mass_kg: float = PILOT_MASS_KG,
) -> dict[str, Any]:
    """有几何时覆盖展弦比，有空战重量时覆盖翼载荷；缺数则保留原值。"""
    out = dict(target)
    span = _optional_finite(out.get('wingspan_m'))
    area = _optional_finite(out.get('wing_area_m2'))
    if span is not None and area is not None and span > 0 and area > 0:
        out['AR'] = aspect_ratio_from_geometry(span, area)
    empty = _optional_finite(empty_kg)
    if empty is None:
        empty = _optional_finite(out.get('empty_kg'))
    fuel = _optional_finite(internal_fuel_kg)
    if fuel is None:
        fuel = _optional_finite(out.get('internal_fuel_kg'))
    pilots = _optional_finite(n_pilots)
    if pilots is None:
        pilots = _optional_finite(out.get('n_pilots'))
        if pilots is None:
            pilots = 1.0
    missile = _optional_finite(missile_mass_kg)
    if missile is None:
        missile = _optional_finite(out.get('missile_mass_kg'))
        if missile is None:
            missile = 0.0
    if empty is not None and fuel is not None and empty >= 0 and fuel >= 0:
        out = apply_combat_wing_loading(
            out, empty, fuel, pilots, missile, n_missiles,
            fuel_fraction, pilot_mass_kg,
        )
    return out


def combat_mass_breakdown(
    empty_kg: float,
    internal_fuel_kg: float,
    n_pilots: float = 1.0,
    missile_mass_kg: float = 0.0,
    n_missiles: float = N_MISSILES_DEFAULT,
    fuel_fraction: float = FUEL_FRACTION_DEFAULT,
    pilot_mass_kg: float = PILOT_MASS_KG,
) -> dict[str, float]:
    """空战质量分项，便于前端展示。"""
    fuel_kg = fuel_fraction * internal_fuel_kg
    pilots_kg = n_pilots * pilot_mass_kg
    missiles_kg = n_missiles * missile_mass_kg
    total = combat_mass_kg(
        empty_kg, internal_fuel_kg, n_pilots, missile_mass_kg, n_missiles,
        fuel_fraction, pilot_mass_kg,
    )
    return {
        'empty_kg': float(empty_kg),
        'fuel_kg': fuel_kg,
        'pilots_kg': pilots_kg,
        'missiles_kg': missiles_kg,
        'total_kg': total,
    }


def cruise_drag_n(mass_kg: float, ld: float, g0: float = G0) -> float:
    """平飞阻力（N）：升力等于重力，D = W / (L/D)。"""
    if mass_kg <= 0:
        raise ValueError('空战质量须为正')
    if ld <= 0:
        raise ValueError('升阻比须为正')
    return mass_kg * g0 / ld


def engine_load_ratio(drag_n: float, thrust_avail_n: float) -> float:
    """负载比 = 平飞阻力 / 该工况最大可用推力（可大于 1）。"""
    if drag_n < 0:
        raise ValueError('阻力不能为负')
    if thrust_avail_n <= 0:
        raise ValueError('可用推力须为正')
    return drag_n / thrust_avail_n


def clamp_load(load: float) -> float:
    """将负载比截断到效率模型允许的 [0, 1]。"""
    if load < 0.0:
        return 0.0
    if load > 1.0:
        return 1.0
    return load
