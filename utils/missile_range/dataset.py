"""导弹射程预设样本，以及前端共用的目录载荷。"""
from __future__ import annotations

from typing import Any

from utils.missile_range.classes import (
    MISSILE_CLASS_ORDER,
    class_blurb,
    class_label,
    estimate_by_class,
    glide_shape,
    resolve_missile_class,
)
from utils.missile_range.estimate import (
    DEFAULT_ISP_S,
    DEFAULT_PROPELLANT_DENSITY,
    HGV_TYPE_LABELS,
)

# 预设样本：几何、战斗部、构型与空射条件
MISSILE_DATASET: list[dict[str, Any]] = [
    {'id': 1, 'length': 10.50, 'diameter': 1.000, 'warhead': 200, 'type': 'biconic', 'v_mach': 0.85, 'h_km': 13.0},
    {'id': 2, 'length': 11.30, 'diameter': 0.860, 'warhead': 200, 'type': 'waverider', 'v_mach': 2.20, 'h_km': 19.0},
    {'id': 3, 'length': 11.30, 'diameter': 0.860, 'warhead': 800, 'type': 'waverider', 'v_mach': 2.20, 'h_km': 19.0},
    {'id': 4, 'length': 11.30, 'diameter': 0.860, 'warhead': 800, 'type': 'biconic', 'v_mach': 2.20, 'h_km': 19.0},
    {'id': 5, 'length': 11.30, 'diameter': 0.860, 'warhead': 200, 'type': 'waverider', 'v_mach': 0.85, 'h_km': 13.0},
    {'id': 6, 'length': 11.30, 'diameter': 0.860, 'warhead': 800, 'type': 'waverider', 'v_mach': 0.85, 'h_km': 13.0},
    {'id': 7, 'length': 11.30, 'diameter': 0.860, 'warhead': 800, 'type': 'biconic', 'v_mach': 0.85, 'h_km': 13.0},
    {'id': 8, 'length': 6.35, 'diameter': 0.840, 'warhead': 150, 'type': 'waverider', 'v_mach': 0.85, 'h_km': 15.0},
    {'id': 9, 'length': 6.35, 'diameter': 0.840, 'warhead': 500, 'type': 'waverider', 'v_mach': 0.85, 'h_km': 15.0},
    {'id': 10, 'length': 6.35, 'diameter': 0.840, 'warhead': 500, 'type': 'biconic', 'v_mach': 0.85, 'h_km': 15.0},
    {'id': 11, 'length': 6.50, 'diameter': 0.600, 'warhead': 300, 'type': 'waverider', 'v_mach': 2.20, 'h_km': 19.0},
    {'id': 12, 'length': 6.50, 'diameter': 0.600, 'warhead': 300, 'type': 'biconic', 'v_mach': 2.20, 'h_km': 19.0},
    {'id': 13, 'length': 6.35, 'diameter': 0.460, 'warhead': 300, 'type': 'waverider', 'v_mach': 2.20, 'h_km': 19.0},
    {'id': 14, 'length': 6.35, 'diameter': 0.460, 'warhead': 300, 'type': 'biconic', 'v_mach': 2.20, 'h_km': 19.0},
    {'id': 15, 'length': 4.90, 'diameter': 0.415, 'warhead': 160, 'type': 'waverider', 'v_mach': 2.20, 'h_km': 19.0},
    {'id': 16, 'length': 4.25, 'diameter': 0.345, 'warhead': 90, 'type': 'waverider', 'v_mach': 2.20, 'h_km': 19.0},
]

# 六类推进方式的代表尺寸。几何与战斗部只用于估算，不对应具体型号。
PROPULSION_DATASET: list[dict[str, Any]] = [
    {'id': 17, 'missile_class': 'scramjet', 'length': 9.20, 'diameter': 0.700, 'warhead': 180, 'type': 'biconic', 'v_mach': 0.85, 'h_km': 12.0},
    {'id': 18, 'missile_class': 'scramjet', 'length': 7.60, 'diameter': 0.550, 'warhead': 120, 'type': 'biconic', 'v_mach': 2.00, 'h_km': 18.0},
    {'id': 19, 'missile_class': 'ramjet', 'length': 8.90, 'diameter': 0.700, 'warhead': 250, 'type': 'biconic', 'v_mach': 0.85, 'h_km': 12.0},
    {'id': 20, 'missile_class': 'ramjet', 'length': 6.20, 'diameter': 0.450, 'warhead': 150, 'type': 'biconic', 'v_mach': 0.90, 'h_km': 10.0},
    {'id': 21, 'missile_class': 'turbofan_stealth', 'length': 6.20, 'diameter': 0.550, 'warhead': 450, 'type': 'biconic', 'v_mach': 0.70, 'h_km': 0.2},
    {'id': 22, 'missile_class': 'turbofan_stealth', 'length': 4.30, 'diameter': 0.450, 'warhead': 240, 'type': 'biconic', 'v_mach': 0.75, 'h_km': 8.0},
    {'id': 23, 'missile_class': 'turbojet_subsonic', 'length': 6.20, 'diameter': 0.550, 'warhead': 450, 'type': 'biconic', 'v_mach': 0.70, 'h_km': 0.2},
    {'id': 24, 'missile_class': 'turbojet_subsonic', 'length': 4.60, 'diameter': 0.340, 'warhead': 220, 'type': 'biconic', 'v_mach': 0.75, 'h_km': 0.2},
    {'id': 25, 'missile_class': 'turbofan_rocket', 'length': 8.20, 'diameter': 0.530, 'warhead': 300, 'type': 'biconic', 'v_mach': 0.70, 'h_km': 0.05},
    {'id': 26, 'missile_class': 'turbofan_rocket', 'length': 6.30, 'diameter': 0.500, 'warhead': 200, 'type': 'biconic', 'v_mach': 0.75, 'h_km': 8.0},
    {'id': 27, 'missile_class': 'ballistic', 'length': 11.20, 'diameter': 0.880, 'warhead': 980, 'type': 'biconic', 'v_mach': 0.0, 'h_km': 0.0},
    {'id': 28, 'missile_class': 'ballistic', 'length': 7.30, 'diameter': 0.920, 'warhead': 480, 'type': 'biconic', 'v_mach': 0.0, 'h_km': 0.0},
]


def all_missile_cases() -> list[dict[str, Any]]:
    """滑翔弹样本在前，其后为六类推进方式样本。"""
    rows: list[dict[str, Any]] = []
    for case in MISSILE_DATASET:
        item = dict(case)
        item['missile_class'] = resolve_missile_class(
            str(item.get('missile_class') or 'hgv'),
            str(item.get('type') or 'biconic'),
        )
        rows.append(item)
    rows.extend(dict(case) for case in PROPULSION_DATASET)
    return rows


def format_size_m(length_m: float, diameter_m: float) -> str:
    """尺寸栏：长 x 径，保留与样本表相同的小数位。"""
    return f'{length_m:.2f} x {diameter_m:.3f}'


def format_launch(v_mach: float, h_km: float) -> str:
    """发射条件文案。"""
    return f'Ma {v_mach:g} @ {h_km:g}km'


def missile_case_label(case: dict[str, Any]) -> str:
    """选择器显示名，弹种名里已经包含双锥或乘波。"""
    canon = resolve_missile_class(
        str(case.get('missile_class') or 'hgv'),
        str(case.get('type') or 'biconic'),
    )
    kind = class_label(canon)
    return (
        f"#{int(case['id'])}  {format_size_m(float(case['length']), float(case['diameter']))}"
        f" · {int(case['warhead'])}kg · {kind}"
        f" · {format_launch(float(case['v_mach']), float(case['h_km']))}"
    )


def evaluate_case(
    case: dict[str, Any],
    isp_s: float = DEFAULT_ISP_S,
    propellant_density: float = DEFAULT_PROPELLANT_DENSITY,
) -> dict[str, Any]:
    """计算单条预设，并附上界面用的尺寸、弹种与构型字段。"""
    canon = resolve_missile_class(
        str(case.get('missile_class') or 'hgv'),
        str(case.get('type') or 'biconic'),
    )
    hgv_type = glide_shape(canon) or str(case.get('type') or 'biconic')
    result = estimate_by_class(
        missile_class=canon,
        length_m=float(case['length']),
        diameter_m=float(case['diameter']),
        warhead_mass_kg=float(case['warhead']),
        hgv_type=hgv_type,
        v_launch_mach=float(case['v_mach']),
        h_launch_km=float(case['h_km']),
        isp_s=isp_s,
        propellant_density=propellant_density,
    )
    row: dict[str, Any] = {
        'id': int(case['id']),
        'name': missile_case_label(case),
        'missile_class': canon,
        'class_label': class_label(canon),
        'length_m': float(case['length']),
        'diameter_m': float(case['diameter']),
        'warhead_kg': float(case['warhead']),
        'hgv_type': hgv_type,
        'type_label': HGV_TYPE_LABELS.get(hgv_type, hgv_type),
        'v_mach': float(case['v_mach']),
        'h_km': float(case['h_km']),
        'size_m': format_size_m(float(case['length']), float(case['diameter'])),
        'launch': format_launch(float(case['v_mach']), float(case['h_km'])),
        'range_high_km': None,
        'range_sea_km': None,
        'range_terminal_km': None,
        'note': class_blurb(canon),
    }
    row.update(result)
    return row


def evaluate_dataset(
    dataset: list[dict[str, Any]] | None = None,
    isp_s: float = DEFAULT_ISP_S,
    propellant_density: float = DEFAULT_PROPELLANT_DENSITY,
) -> list[dict[str, Any]]:
    """按当前比冲与密度重算整张样本表。"""
    rows = dataset if dataset is not None else all_missile_cases()
    return [
        evaluate_case(case, isp_s=isp_s, propellant_density=propellant_density)
        for case in rows
    ]


def build_missile_range_catalog_payload() -> dict[str, Any]:
    """构建 Web / 小程序 / iOS 共用的预设与默认估算表。"""
    return {
        'type_labels': dict(HGV_TYPE_LABELS),
        'classes': [dict(item) for item in MISSILE_CLASS_ORDER],
        'defaults': {
            'isp_s': DEFAULT_ISP_S,
            'propellant_density': DEFAULT_PROPELLANT_DENSITY,
            'length_m': 10.50,
            'diameter_m': 1.000,
            'warhead_kg': 200,
            'hgv_type': 'biconic',
            'missile_class': 'hgv_biconic',
            'v_launch_mach': 0.85,
            'h_launch_km': 13.0,
        },
        'cases': evaluate_dataset(),
    }
