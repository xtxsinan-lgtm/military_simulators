"""由公开航程/作战半径与 TSFC 倒推浸润面积，并分解为分段机身尺寸。

布雷盖作战半径：
    R = (V / (2 g c)) · (L/D) · ln(Wi / Wf)
故在已知 R、V、c、质量比时可反解 L/D。

浸润侧：有完整分段几何时
    S_wet = 圆锥侧面积 + 圆台侧面积 + 长方体表面积 + 2×升力面平面面积
在固定机长分段与升力面后，只缩放机身盒段宽高（保持宽高比）使 S_wet 对齐目标。
"""
from __future__ import annotations

import math
from typing import Any

from utils.combat_radius.breguet import G0
from utils.combat_radius.lift_drag import (
    LIFTING_WETTED_SIDES,
    box_surface_area_m2,
    cone_lateral_area_m2,
    frustum_lateral_area_m2,
)

# F-35A 分段长度占机长比例（锥+圆台+盒段合计约 0.89·L）
F35_CONE_FRAC = 1.06 / 15.7
F35_NOSE_FRAC = 3.26 / 15.7
F35_BODY_FRAC = 9.66 / 15.7


def ld_from_combat_radius_m(
    radius_m: float,
    v_mps: float,
    tsfc_kg_n_s: float,
    mass_initial_kg: float,
    mass_final_kg: float,
    g0: float = G0,
) -> float:
    """由作战半径反推所需升阻比（对称去/返、单一巡航点）。"""
    if radius_m <= 0:
        raise ValueError('作战半径须为正')
    if v_mps <= 0:
        raise ValueError('巡航速度须为正')
    if tsfc_kg_n_s <= 0:
        raise ValueError('TSFC 须为正')
    if mass_final_kg <= 0:
        raise ValueError('终了质量须为正')
    if mass_initial_kg <= mass_final_kg:
        raise ValueError('起飞质量须大于终了质量')
    if g0 <= 0:
        raise ValueError('重力加速度须为正')
    ln_ratio = math.log(mass_initial_kg / mass_final_kg)
    return (2.0 * radius_m * g0 * tsfc_kg_n_s) / (v_mps * ln_ratio)


def ld_from_ferry_range_m(
    range_m: float,
    v_mps: float,
    tsfc_kg_n_s: float,
    mass_initial_kg: float,
    mass_final_kg: float,
    g0: float = G0,
) -> float:
    """由航程（单程布雷盖）反推所需升阻比。"""
    if range_m <= 0:
        raise ValueError('航程须为正')
    # 作战半径是航程一半，故航程对应的 L/D = 半径公式的一半系数
    return ld_from_combat_radius_m(
        range_m / 2.0, v_mps, tsfc_kg_n_s, mass_initial_kg, mass_final_kg, g0,
    )


def tsfc_lb_lbf_h_to_kg_n_s(tsfc_lb_lbf_h: float, g0: float = G0) -> float:
    """公开军推 TSFC（lb/lbf·h）转为 SI kg/(N·s)。"""
    if tsfc_lb_lbf_h <= 0:
        raise ValueError('TSFC 须为正')
    if g0 <= 0:
        raise ValueError('重力加速度须为正')
    return tsfc_lb_lbf_h / (g0 * 3600.0)


def length_segments_from_aircraft_length(
    length_m: float,
    cone_frac: float = F35_CONE_FRAC,
    nose_frac: float = F35_NOSE_FRAC,
    body_frac: float = F35_BODY_FRAC,
) -> dict[str, float]:
    """按 F-35A 比例（或自定义比例）把机长切成锥/圆台/盒段。"""
    if length_m <= 0:
        raise ValueError('机长须为正')
    if min(cone_frac, nose_frac, body_frac) <= 0:
        raise ValueError('长度比例须为正')
    total = cone_frac + nose_frac + body_frac
    if total >= 1.0:
        raise ValueError('三段长度比例之和须小于 1')
    return {
        'nose_cone_length_m': round(length_m * cone_frac, 3),
        'nose_length_m': round(length_m * nose_frac, 3),
        'fuse_body_length_m': round(length_m * body_frac, 3),
    }


def nose_wetted_m2(
    nose_cone_length_m: float,
    nose_cone_diameter_m: float,
    nose_length_m: float,
    nose_root_diameter_m: float,
) -> float:
    """机头锥+圆台浸润。"""
    return (
        cone_lateral_area_m2(nose_cone_length_m, nose_cone_diameter_m)
        + frustum_lateral_area_m2(
            nose_length_m, nose_cone_diameter_m, nose_root_diameter_m,
        )
    )


def lifting_wetted_from_planforms(
    main_wing_area_m2: float,
    canard_htail_area_m2: float = 0.0,
    ventral_fin_area_m2: float = 0.0,
    vtail_area_m2: float = 0.0,
) -> float:
    """升力面浸润 = 平面面积之和 × 2。"""
    planform = (
        main_wing_area_m2 + canard_htail_area_m2
        + ventral_fin_area_m2 + vtail_area_m2
    )
    if planform < 0:
        raise ValueError('升力面面积不能为负')
    return LIFTING_WETTED_SIDES * planform


def solve_box_width_height(
    body_length_m: float,
    target_box_area_m2: float,
    width_height_ratio: float,
) -> tuple[float, float]:
    """在固定盒段长度与宽高比下，解长方体表面积对应的宽、高。"""
    if body_length_m <= 0:
        raise ValueError('盒段长度须为正')
    if target_box_area_m2 <= 0:
        raise ValueError('目标盒段表面积须为正')
    if width_height_ratio <= 0:
        raise ValueError('宽高比须为正')
    # 2(L·r·h + L·h + r·h²) = A  →  2r h² + 2L(r+1) h - A = 0
    r = width_height_ratio
    a = 2.0 * r
    b = 2.0 * body_length_m * (r + 1.0)
    c = -target_box_area_m2
    disc = b * b - 4.0 * a * c
    if disc < 0:
        raise ValueError('目标盒段表面积相对长度过大，无法解出正宽高')
    height = (-b + math.sqrt(disc)) / (2.0 * a)
    if height <= 0:
        raise ValueError('解出的机身高度非正')
    width = r * height
    return width, height


def fuse_dims_for_target_swet(
    target_swet_m2: float,
    *,
    nose_cone_length_m: float,
    nose_cone_diameter_m: float,
    nose_length_m: float,
    nose_root_diameter_m: float,
    fuse_body_length_m: float,
    main_wing_area_m2: float,
    canard_htail_area_m2: float = 0.0,
    ventral_fin_area_m2: float = 0.0,
    vtail_area_m2: float = 0.0,
    width_height_ratio: float,
) -> dict[str, float]:
    """固定机头与升力面，倒推机身宽高使全机 S_wet 对齐目标。"""
    if target_swet_m2 <= 0:
        raise ValueError('目标浸润面积须为正')
    nose = nose_wetted_m2(
        nose_cone_length_m, nose_cone_diameter_m, nose_length_m, nose_root_diameter_m,
    )
    lift = lifting_wetted_from_planforms(
        main_wing_area_m2, canard_htail_area_m2, ventral_fin_area_m2, vtail_area_m2,
    )
    need_box = target_swet_m2 - nose - lift
    if need_box <= 0:
        raise ValueError(
            f'目标浸润 {target_swet_m2:.1f} m² 小于机头+升力面 '
            f'{nose + lift:.1f} m²，无法只靠机身盒段对齐'
        )
    width, height = solve_box_width_height(
        fuse_body_length_m, need_box, width_height_ratio,
    )
    box = box_surface_area_m2(fuse_body_length_m, width, height)
    return {
        'fuse_width_m': round(width, 3),
        'fuse_height_m': round(height, 3),
        'nose_wetted_m2': nose,
        'lifting_wetted_m2': lift,
        'box_wetted_m2': box,
        'total_swet_m2': nose + lift + box,
    }


def scale_nose_diameters_to_fuse_width(
    fuse_width_m: float,
    *,
    cone_to_width: float = 0.36,
    root_to_width: float = 0.60,
) -> dict[str, float]:
    """按机身宽度比例估计雷达罩底径与机头根径（战斗机典型比例）。"""
    if fuse_width_m <= 0:
        raise ValueError('机身宽度须为正')
    if cone_to_width <= 0 or root_to_width <= 0:
        raise ValueError('直径比例须为正')
    if cone_to_width >= root_to_width:
        raise ValueError('锥底径比例应小于机头根径比例')
    return {
        'nose_cone_diameter_m': round(fuse_width_m * cone_to_width, 3),
        'nose_root_diameter_m': round(fuse_width_m * root_to_width, 3),
    }


def iterate_fuse_dims_with_nose_scale(
    target_swet_m2: float,
    *,
    nose_cone_length_m: float,
    nose_length_m: float,
    fuse_body_length_m: float,
    main_wing_area_m2: float,
    canard_htail_area_m2: float = 0.0,
    ventral_fin_area_m2: float = 0.0,
    vtail_area_m2: float = 0.0,
    width_height_ratio: float,
    cone_to_width: float = 0.36,
    root_to_width: float = 0.60,
    seed_width_m: float = 2.0,
    iters: int = 8,
) -> dict[str, float]:
    """机头直径随机身宽缩放时，迭代使总浸润对齐目标。"""
    if iters < 1:
        raise ValueError('迭代次数须为正')
    width = seed_width_m
    last: dict[str, float] | None = None
    for _ in range(iters):
        nose_d = scale_nose_diameters_to_fuse_width(
            width, cone_to_width=cone_to_width, root_to_width=root_to_width,
        )
        last = fuse_dims_for_target_swet(
            target_swet_m2,
            nose_cone_length_m=nose_cone_length_m,
            nose_cone_diameter_m=nose_d['nose_cone_diameter_m'],
            nose_length_m=nose_length_m,
            nose_root_diameter_m=nose_d['nose_root_diameter_m'],
            fuse_body_length_m=fuse_body_length_m,
            main_wing_area_m2=main_wing_area_m2,
            canard_htail_area_m2=canard_htail_area_m2,
            ventral_fin_area_m2=ventral_fin_area_m2,
            vtail_area_m2=vtail_area_m2,
            width_height_ratio=width_height_ratio,
        )
        width = last['fuse_width_m']
    assert last is not None
    nose_d = scale_nose_diameters_to_fuse_width(
        width, cone_to_width=cone_to_width, root_to_width=root_to_width,
    )
    out = dict(last)
    out.update(nose_d)
    out['nose_cone_length_m'] = nose_cone_length_m
    out['nose_length_m'] = nose_length_m
    out['fuse_body_length_m'] = fuse_body_length_m
    return out


def geometry_dict_for_csv(calc: dict[str, float], lifting: dict[str, float]) -> dict[str, Any]:
    """把倒推结果整理成可写入机型 CSV 的字段。"""
    return {
        'nose_cone_length_m': calc['nose_cone_length_m'],
        'nose_cone_diameter_m': calc['nose_cone_diameter_m'],
        'nose_length_m': calc['nose_length_m'],
        'nose_root_diameter_m': calc['nose_root_diameter_m'],
        'fuse_body_length_m': calc['fuse_body_length_m'],
        'fuse_width_m': calc['fuse_width_m'],
        'fuse_height_m': calc['fuse_height_m'],
        'main_wing_area_m2': lifting.get('main_wing_area_m2', 0.0),
        'canard_htail_area_m2': lifting.get('canard_htail_area_m2', 0.0) or '',
        'ventral_fin_area_m2': lifting.get('ventral_fin_area_m2', 0.0) or '',
        'vtail_area_m2': lifting.get('vtail_area_m2', 0.0) or '',
    }
