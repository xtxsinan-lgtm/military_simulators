"""导弹射程预设样本，以及前端共用的目录载荷。"""
from __future__ import annotations

from typing import Any

from utils.database_csv import load_missile_range_preset_csv
from utils.missile_range.classes import (
    MISSILE_CLASS_ORDER,
    class_blurb,
    class_isp_defaults,
    class_label,
    estimate_by_class,
    resolve_missile_class,
)
from utils.missile_range.estimate import (
    DEFAULT_ISP_S,
    DEFAULT_PROPELLANT_DENSITY,
)

# 超音速弹种（不含亚超结合，含普通弹道）共用 CSV 中 speed_group=supersonic 的弹仓。
SUPERSONIC_CLASSES = (
    'hgv_biconic',
    'hgv_waverider',
    'scramjet',
    'ramjet',
    'ballistic',
)
# 亚音速弹种（含亚超结合）。弹翼按折叠在弹体内估算。
SUBSONIC_CLASSES = (
    'turbofan_stealth',
    'turbojet_subsonic',
    'turbofan_rocket',
)
SPEED_GROUP_CLASSES = {
    'supersonic': SUPERSONIC_CLASSES,
    'subsonic': SUBSONIC_CLASSES,
}


def grouped_preset_bays(
    preset_rows: list[dict[str, Any]] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """把 CSV 行收成速度组 -> 弹仓列表（同一弹仓连续多行视为多发战斗部）。

    若行带 missile_class，则该弹仓只对该弹种生效；留空则对该速度组全部弹种生效。
    """
    rows = preset_rows if preset_rows is not None else load_missile_range_preset_csv()
    grouped: dict[str, list[dict[str, Any]]] = {name: [] for name in SPEED_GROUP_CLASSES}
    last_key: dict[str, tuple[Any, ...] | None] = {name: None for name in grouped}
    for row in rows:
        group = str(row['speed_group'])
        if group not in grouped:
            raise ValueError(f'未知速度组 {group}')
        missile_class = row.get('missile_class') or None
        if missile_class is not None:
            missile_class = str(missile_class)
        key = (missile_class, str(row['bay']), float(row['v_launch_mach']), float(row['h_launch_km']))
        if last_key[group] != key:
            grouped[group].append({
                'missile_class': missile_class,
                'bay': str(row['bay']),
                'v_mach': float(row['v_launch_mach']),
                'h_km': float(row['h_launch_km']),
                'rounds': [],
            })
            last_key[group] = key
        grouped[group][-1]['rounds'].append((
            float(row['length_m']),
            float(row['diameter_m']),
            int(row['warhead_kg']),
        ))
    for group, bays in grouped.items():
        if not bays:
            raise ValueError(f'弹种速度组 {group} 没有预设弹仓')
        for bay in bays:
            bay['rounds'] = tuple(bay['rounds'])
    return grouped


def build_preset_cases(
    preset_rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """按弹种目录顺序展开载机弹仓样本，编号从 1 连续增加。

    同一弹仓若存在弹种专属行（missile_class 非空），则该弹种不再使用同弹仓的共用行，
    专属行按 CSV 顺序覆盖共用行。
    """
    grouped = grouped_preset_bays(preset_rows)
    rows: list[dict[str, Any]] = []
    number = 1
    for item in MISSILE_CLASS_ORDER:
        missile_class = item['id']
        try:
            group = next(g for g, names in SPEED_GROUP_CLASSES.items() if missile_class in names)
        except StopIteration as exc:
            raise ValueError(f'弹种 {missile_class} 没有预设弹仓') from exc
        # 哪些 (弹种, 弹仓, 发射条件) 在该速度组存在专属覆盖
        specific_keys = {
            (bay['missile_class'], bay['bay'], bay['v_mach'], bay['h_km'])
            for bay in grouped[group]
            if bay.get('missile_class') is not None
        }
        for bay in grouped[group]:
            bay_class = bay.get('missile_class')
            if bay_class is not None:
                if bay_class != missile_class:
                    continue
            else:
                if (missile_class, bay['bay'], bay['v_mach'], bay['h_km']) in specific_keys:
                    continue
            for length, diameter, warhead in bay['rounds']:
                rows.append({
                    'id': number,
                    'missile_class': missile_class,
                    'bay': bay['bay'],
                    'length': float(length),
                    'diameter': float(diameter),
                    'warhead': int(warhead),
                    'v_mach': float(bay['v_mach']),
                    'h_km': float(bay['h_km']),
                })
                number += 1
    return rows


_PRESET_CASES = build_preset_cases()
# 助推滑翔样本仍单独列出，便于对照原有滑翔公式
MISSILE_DATASET: list[dict[str, Any]] = [
    case for case in _PRESET_CASES if str(case['missile_class']).startswith('hgv')
]
# 冲压、亚音速、亚超结合与弹道
PROPULSION_DATASET: list[dict[str, Any]] = [
    case for case in _PRESET_CASES if not str(case['missile_class']).startswith('hgv')
]


def all_missile_cases() -> list[dict[str, Any]]:
    """滑翔弹样本在前，其后为六类推进方式样本。"""
    rows: list[dict[str, Any]] = []
    for case in MISSILE_DATASET:
        item = dict(case)
        item['missile_class'] = resolve_missile_class(str(item.get('missile_class') or 'hgv_biconic'))
        rows.append(item)
    rows.extend(dict(case) for case in PROPULSION_DATASET)
    return rows


def format_size_m(length_m: float, diameter_m: float) -> str:
    """尺寸栏：长 x 径，保留与样本表相同的小数位。"""
    return f'{length_m:.2f} x {diameter_m:.3f}'


def format_launch(v_mach: float, h_km: float) -> str:
    """发射条件文案。"""
    return f'Ma {v_mach:g} @ {h_km:g}km'


def sort_missile_range_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按载机平台分组；同一平台内先按尺寸从大到小，同尺寸再按射程从高到低。

    尺寸比较先看弹长，再看弹径。轰-6 机腹这类同一挂架有多套尺寸时，
    同一尺寸的各弹种会排在一起，而不是按射程把不同尺寸穿插开。
    """
    copied = [dict(row) for row in rows]
    bay_sizes: dict[str, tuple[float, float]] = {}
    for row in copied:
        bay = str(row.get('bay') or '')
        size = (float(row.get('length_m') or 0.0), float(row.get('diameter_m') or 0.0))
        current = bay_sizes.get(bay)
        if current is None or size > current:
            bay_sizes[bay] = size
    bay_order = {
        bay: index
        for index, (bay, _) in enumerate(
            sorted(
                bay_sizes.items(),
                key=lambda item: (-item[1][0], -item[1][1], item[0]),
            )
        )
    }
    ordered = sorted(
        copied,
        key=lambda row: (
            bay_order.get(str(row.get('bay') or ''), len(bay_order)),
            -float(row.get('length_m') or 0.0),
            -float(row.get('diameter_m') or 0.0),
            -float(row.get('range_km') or 0.0),
            -float(row.get('warhead_kg') or 0.0),
            int(row.get('id') or 0),
        ),
    )
    for index, row in enumerate(ordered, 1):
        row['id'] = index
        name = str(row.get('name') or '')
        suffix = name.split('  ', 1)[1] if '  ' in name else name
        row['name'] = f'#{index}  {suffix}'.rstrip()
    return ordered


def missile_case_label(case: dict[str, Any]) -> str:
    """选择器显示名：载机弹仓、尺寸、弹种与发射条件。"""
    canon = resolve_missile_class(str(case.get('missile_class') or 'hgv_biconic'))
    kind = class_label(canon)
    bay = str(case.get('bay') or '').strip()
    place = f'{bay} · ' if bay else ''
    return (
        f"#{int(case['id'])}  {place}"
        f"{format_size_m(float(case['length']), float(case['diameter']))}"
        f" · {int(case['warhead'])}kg · {kind}"
        f" · {format_launch(float(case['v_mach']), float(case['h_km']))}"
    )


def evaluate_case(
    case: dict[str, Any],
    isp_s: float = DEFAULT_ISP_S,
    propellant_density: float = DEFAULT_PROPELLANT_DENSITY,
) -> dict[str, Any]:
    """计算单条预设，并附上界面用的尺寸与弹种字段。"""
    canon = resolve_missile_class(str(case.get('missile_class') or 'hgv_biconic'))
    result = estimate_by_class(
        missile_class=canon,
        length_m=float(case['length']),
        diameter_m=float(case['diameter']),
        warhead_mass_kg=float(case['warhead']),
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
        'v_mach': float(case['v_mach']),
        'h_km': float(case['h_km']),
        'bay': str(case.get('bay') or ''),
        'size_m': format_size_m(float(case['length']), float(case['diameter'])),
        'launch': format_launch(float(case['v_mach']), float(case['h_km'])),
        'range_high_km': None,
        'range_sea_km': None,
        'range_mixed_km': None,
        'range_terminal_km': None,
        'note': class_blurb(canon),
    }
    row.update(result)
    if result.get('reached_takeover') is False:
        row['name'] = f"{row['name']} · 未达工作速度"
    return row


def filter_takeover_failed(
    rows: list[dict[str, Any]],
    failed_only: bool,
) -> list[dict[str, Any]]:
    """界面筛选：只保留冲压未达接力速度的样本。"""
    copied = [dict(row) for row in rows]
    if not failed_only:
        return copied
    return [row for row in copied if row.get('reached_takeover') is False]


def evaluate_dataset(
    dataset: list[dict[str, Any]] | None = None,
    isp_s: float = DEFAULT_ISP_S,
    propellant_density: float = DEFAULT_PROPELLANT_DENSITY,
) -> list[dict[str, Any]]:
    """按当前比冲与密度重算整张样本表，并生成展示顺序。"""
    rows = dataset if dataset is not None else all_missile_cases()
    evaluated = [
        evaluate_case(case, isp_s=isp_s, propellant_density=propellant_density)
        for case in rows
    ]
    return sort_missile_range_rows(evaluated)


def build_missile_range_catalog_payload() -> dict[str, Any]:
    """构建 Web / 小程序 / iOS 共用的预设与默认估算表。"""
    classes = []
    for item in MISSILE_CLASS_ORDER:
        row = dict(item)
        row.update(class_isp_defaults(item['id']))
        classes.append(row)
    return {
        'classes': classes,
        'defaults': {
            'isp_s': DEFAULT_ISP_S,
            'propellant_density': DEFAULT_PROPELLANT_DENSITY,
            'length_m': 10.50,
            'diameter_m': 1.100,
            'warhead_kg': 150,
            'missile_class': 'hgv_biconic',
            'ballistic_two_stage': True,
            'v_launch_mach': 0.85,
            'h_launch_km': 13.0,
        },
        'cases': evaluate_dataset(),
    }
