"""滑翔弹预设尺寸样本，以及前端共用的目录载荷。"""
from __future__ import annotations

from typing import Any

from utils.missile_range.estimate import (
    DEFAULT_ISP_S,
    DEFAULT_PROPELLANT_DENSITY,
    HGV_TYPE_LABELS,
    estimate_hgv,
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


def format_size_m(length_m: float, diameter_m: float) -> str:
    """尺寸栏：长 x 径，保留与样本表相同的小数位。"""
    return f'{length_m:.2f} x {diameter_m:.3f}'


def format_launch(v_mach: float, h_km: float) -> str:
    """发射条件文案。"""
    return f'Ma {v_mach:g} @ {h_km:g}km'


def missile_case_label(case: dict[str, Any]) -> str:
    """选择器显示名。"""
    type_label = HGV_TYPE_LABELS.get(str(case['type']), str(case['type']))
    return (
        f"#{int(case['id'])}  {format_size_m(float(case['length']), float(case['diameter']))}"
        f" · {int(case['warhead'])}kg · {type_label}"
        f" · {format_launch(float(case['v_mach']), float(case['h_km']))}"
    )


def evaluate_case(
    case: dict[str, Any],
    isp_s: float = DEFAULT_ISP_S,
    propellant_density: float = DEFAULT_PROPELLANT_DENSITY,
) -> dict[str, Any]:
    """计算单条预设，并附上界面用的尺寸与构型字段。"""
    result = estimate_hgv(
        length_m=float(case['length']),
        diameter_m=float(case['diameter']),
        warhead_mass_kg=float(case['warhead']),
        hgv_type=str(case['type']),
        v_launch_mach=float(case['v_mach']),
        h_launch_km=float(case['h_km']),
        isp_s=isp_s,
        propellant_density=propellant_density,
    )
    hgv_type = str(case['type'])
    return {
        'id': int(case['id']),
        'name': missile_case_label(case),
        'length_m': float(case['length']),
        'diameter_m': float(case['diameter']),
        'warhead_kg': float(case['warhead']),
        'hgv_type': hgv_type,
        'type_label': HGV_TYPE_LABELS.get(hgv_type, hgv_type),
        'v_mach': float(case['v_mach']),
        'h_km': float(case['h_km']),
        'size_m': format_size_m(float(case['length']), float(case['diameter'])),
        'launch': format_launch(float(case['v_mach']), float(case['h_km'])),
        **result,
    }


def evaluate_dataset(
    dataset: list[dict[str, Any]] | None = None,
    isp_s: float = DEFAULT_ISP_S,
    propellant_density: float = DEFAULT_PROPELLANT_DENSITY,
) -> list[dict[str, Any]]:
    """按当前比冲与密度重算整张样本表。"""
    rows = dataset if dataset is not None else MISSILE_DATASET
    return [
        evaluate_case(case, isp_s=isp_s, propellant_density=propellant_density)
        for case in rows
    ]


def build_missile_range_catalog_payload() -> dict[str, Any]:
    """构建 Web / 小程序 / iOS 共用的预设与默认估算表。"""
    return {
        'type_labels': dict(HGV_TYPE_LABELS),
        'defaults': {
            'isp_s': DEFAULT_ISP_S,
            'propellant_density': DEFAULT_PROPELLANT_DENSITY,
            'length_m': 10.50,
            'diameter_m': 1.000,
            'warhead_kg': 200,
            'hgv_type': 'biconic',
            'v_launch_mach': 0.85,
            'h_launch_km': 13.0,
        },
        'cases': evaluate_dataset(),
    }
