"""导弹射程预设样本，以及前端共用的目录载荷。"""
from __future__ import annotations

import copy
from functools import lru_cache
from typing import Any

from utils.database_csv import load_missile_range_preset_csv
from utils.missile_range.classes import (
    BOOST_CASE_FRAC,
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
    min_head_length_m,
    parse_stage_fractions,
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
# 翼下按歼-15 发射条件定外形。机腹的助推切分按轰-6 搜索后再冻结。
J15_STRUCTURE_BAYS = ('歼-15翼下', '歼-15机腹')
# 这几组在本行发射条件之外，用同一结构另算轰-6、轰-20、歼-36，单独一栏显示。
ALT_RANGE_BAYS = J15_STRUCTURE_BAYS + ('隐身超音速轰炸机弹仓',)
# 歼-15 机腹：助推分级、滑翔体和助推药按轰-6 的发射条件搜索。
H6_STRUCTURE_BAY = '歼-15机腹'
H6_STRUCTURE_LAUNCH = (0.85, 13.0)
# 轰-20 与隐身亚音速轰炸机弹仓同一发射包线：Ma 0.85 @ 15 km。
J15_ALT_LAUNCHES = (
    ('轰-6', 0.85, 13.0),
    ('轰-20', 0.85, 15.0),
    ('歼-36', 2.15, 20.0),
)
# 普通战斗机自己在 Ma 1.50 @ 14 km 发射。同一构型再算另外三架：
# 轰-6 仍是 Ma 0.85 @ 13 km；轰-20 改用 Ma 1.75 @ 18 km；歼-36 为 Ma 2.15 @ 20 km。
FIGHTER_BAY = '普通战斗机弹仓'
FIGHTER_ALT_LAUNCHES = (
    ('轰-6', 0.85, 13.0),
    ('轰-20', 1.75, 18.0),
    ('歼-36', 2.15, 20.0),
)
# 翼下超音速弹统一外形；亚音速另按质量和弹径上限收。
J15_WING_SUPERSONIC_SIZE = (6.5, 0.5)
J15_WING_LENGTH_M = 6.5
J15_WING_SUBSONIC_MAX_DIAMETER_M = 0.6
J15_WING_MASS_T = 1.5
J15_BELLY_LENGTH_M = 8.5
J15_BELLY_MAX_DIAMETER_M = 0.70
J15_BELLY_MASS_T = 2.5
# 三种高超：双锥体、乘波体、超燃。冲压单独一档战斗部。
J15_HYPERSONIC_CLASSES = ('hgv_biconic', 'hgv_waverider', 'scramjet')


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


def format_cruise_profile(result: dict[str, Any]) -> str | None:
    """巡航弹的高空、混合、掠海射程，用斜线收成一栏。没有掠海档时返回空。"""
    high = result.get('range_high_km')
    sea = result.get('range_sea_km')
    if high is None or sea is None:
        return None
    mixed = result.get('range_mixed_km')
    mixed_text = '—' if mixed is None else f'{float(mixed):.1f}'
    return f'{float(high):.1f}/{mixed_text}/{float(sea):.1f}'


def format_alt_launch_text(parts: list[str]) -> str:
    """三个平台的预计算射程。巡航档内部已用斜线，平台之间用间隔号分开。"""
    if len(parts) != 3 or any(not part for part in parts):
        raise ValueError('需要轰-6、轰-20、歼-36 三档射程')
    return ' · '.join(parts)


def fit_locked_head(
    lock: dict[str, Any],
    length_m: float,
    diameter_m: float,
    warhead_kg: float,
    missile_class: str,
) -> dict[str, Any]:
    """圆整后的滑翔体若装不下战斗部，把长度拉回装填底线，直径不超过弹径。"""
    if 'd_head_m' not in lock:
        return lock
    fitted = dict(lock)
    fitted['d_head_m'] = min(float(fitted['d_head_m']), float(diameter_m))
    shape = 'waverider' if str(missile_class).endswith('waverider') else 'biconic'
    floor = min_head_length_m(float(warhead_kg), fitted['d_head_m'], shape)
    fitted['l_head_m'] = min(max(float(fitted['l_head_m']), floor), float(length_m) - 0.05)
    return fitted


def structure_lock_kwargs(result: dict[str, Any]) -> dict[str, Any]:
    """从参考发射条件的估算里取出要冻结的滑翔体、助推分级和助推药。"""
    canon = resolve_missile_class(str(result.get('missile_class') or ''))
    locked: dict[str, Any] = {}
    if canon.startswith('hgv'):
        if result.get('l_head_m') is None or result.get('d_head_m') is None:
            raise ValueError('助推滑翔缺少可冻结的滑翔体尺寸')
        locked['l_head_m'] = float(result['l_head_m'])
        locked['d_head_m'] = float(result['d_head_m'])
        locked['optimize_geometry'] = False
    if result.get('stage_split') and canon in ('hgv_biconic', 'hgv_waverider', 'ballistic'):
        locked['stage_fractions'] = parse_stage_fractions(str(result['stage_split']))
    if canon not in ('hgv_biconic', 'hgv_waverider', 'ballistic') and result.get('m_booster_kg') is not None:
        locked['booster_propellant_kg'] = float(result['m_booster_kg']) / (1.0 + BOOST_CASE_FRAC)
    return locked


def alt_launch_ranges(
    case: dict[str, Any],
    template: dict[str, Any],
    launches: tuple[tuple[str, float, float], ...] = J15_ALT_LAUNCHES,
) -> dict[str, Any]:
    """同一结构下，按轰-6、轰-20、歼-36 的发射条件重算射程。"""
    lock = fit_locked_head(
        structure_lock_kwargs(template),
        float(case['length']), float(case['diameter']), float(case['warhead']),
        str(case['missile_class']),
    )
    pieces: list[str] = []
    detail: list[dict[str, Any]] = []
    for label, mach, height in launches:
        result = estimate_by_class(
            missile_class=str(case['missile_class']),
            length_m=float(case['length']),
            diameter_m=float(case['diameter']),
            warhead_mass_kg=float(case['warhead']),
            v_launch_mach=mach,
            h_launch_km=height,
            **lock,
        )
        profile = format_cruise_profile(result)
        text = profile if profile is not None else f"{float(result['range_km']):.1f}"
        pieces.append(text)
        detail.append({
            'label': label,
            'v_mach': mach,
            'h_km': height,
            'range_km': float(result['range_km']),
            'range_high_km': result.get('range_high_km'),
            'range_mixed_km': result.get('range_mixed_km'),
            'range_sea_km': result.get('range_sea_km'),
            'text': text,
        })
    return {
        'alt_range_text': format_alt_launch_text(pieces),
        'alt_launches': detail,
    }


def format_launch(v_mach: float, h_km: float) -> str:
    """发射条件文案。"""
    return f'Ma {v_mach:g} @ {h_km:g}km'


def _row_liftoff_t(row: dict[str, Any]) -> float:
    """起飞质量（吨）。预设表用 m_0_t；缺省时按 0。"""
    return float(row.get('m_0_t') or 0.0)


def sort_missile_range_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按载机分组显示。

    载机之间按该载机里起飞质量最大的一发降序；起飞质量相同再按载机名称。
    同一载机内按战斗部重量升序，同一战斗部再按射程降序。
    """
    copied = [dict(row) for row in rows]
    bay_mass: dict[str, float] = {}
    for row in copied:
        bay = str(row.get('bay') or '')
        mass = _row_liftoff_t(row)
        current = bay_mass.get(bay)
        if current is None or mass > current:
            bay_mass[bay] = mass
    bay_order = {
        bay: index
        for index, (bay, _) in enumerate(
            sorted(bay_mass.items(), key=lambda item: (-item[1], item[0]))
        )
    }
    ordered = sorted(
        copied,
        key=lambda row: (
            bay_order.get(str(row.get('bay') or ''), len(bay_order)),
            float(row.get('warhead_kg') or 0.0),
            -float(row.get('range_km') or 0.0),
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
    bay = str(case.get('bay') or '')
    # 机腹先按轰-6 把助推切分和滑翔体定死，本行再按歼-15 发射条件算射程。
    # 普通战斗机按自己的发射条件定构型，不套用轰-6 的助推切分。
    template = None
    lock: dict[str, Any] = {}
    if bay == H6_STRUCTURE_BAY:
        template = estimate_by_class(
            missile_class=canon,
            length_m=float(case['length']),
            diameter_m=float(case['diameter']),
            warhead_mass_kg=float(case['warhead']),
            v_launch_mach=H6_STRUCTURE_LAUNCH[0],
            h_launch_km=H6_STRUCTURE_LAUNCH[1],
            isp_s=isp_s,
            propellant_density=propellant_density,
        )
        lock = fit_locked_head(
            structure_lock_kwargs(template),
            float(case['length']), float(case['diameter']), float(case['warhead']),
            canon,
        )
    result = estimate_by_class(
        missile_class=canon,
        length_m=float(case['length']),
        diameter_m=float(case['diameter']),
        warhead_mass_kg=float(case['warhead']),
        v_launch_mach=float(case['v_mach']),
        h_launch_km=float(case['h_km']),
        isp_s=isp_s,
        propellant_density=propellant_density,
        **lock,
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
        'bay': bay,
        'size_m': format_size_m(float(case['length']), float(case['diameter'])),
        'launch': format_launch(float(case['v_mach']), float(case['h_km'])),
        'range_high_km': None,
        'range_sea_km': None,
        'range_mixed_km': None,
        'range_terminal_km': None,
        'profile_text': None,
        'alt_range_text': None,
        'alt_launches': None,
        'note': class_blurb(canon),
    }
    row.update(result)
    row['profile_text'] = format_cruise_profile(row)
    if bay == FIGHTER_BAY:
        # 构型已按战斗机发射条件寻优，轰-6 / 轰-20 / 歼-36 只改发射条件。
        alt = alt_launch_ranges(case, row, launches=FIGHTER_ALT_LAUNCHES)
        row.update(alt)
    elif bay in ALT_RANGE_BAYS:
        # 机腹的冻结结构来自轰-6；翼下和隐身超音速轰炸机弹仓沿用本行已经搜好的结构。
        alt = alt_launch_ranges(case, template if template is not None else row)
        row.update(alt)
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


def dataset_propellant_key(isp_s: float, propellant_density: float) -> tuple[float, float]:
    """把固体比冲和推进剂密度收成样本表缓存键。"""
    return (round(float(isp_s), 6), round(float(propellant_density), 6))


@lru_cache(maxsize=4)
def _cached_default_dataset(isp_key: float, density_key: float) -> list[dict[str, Any]]:
    """按推进剂假设缓存默认样本表，避免网页每次估算都重扫一百多发。"""
    evaluated = [
        evaluate_case(case, isp_s=isp_key, propellant_density=density_key)
        for case in all_missile_cases()
    ]
    return sort_missile_range_rows(evaluated)


def evaluate_dataset(
    dataset: list[dict[str, Any]] | None = None,
    isp_s: float = DEFAULT_ISP_S,
    propellant_density: float = DEFAULT_PROPELLANT_DENSITY,
) -> list[dict[str, Any]]:
    """按当前比冲与密度重算整张样本表，并生成展示顺序。

    默认样本表按推进剂假设缓存。返回的是副本，改一行不会影响下次结果。
    传入自定义 dataset 时不走缓存。
    """
    if dataset is not None:
        evaluated = [
            evaluate_case(case, isp_s=isp_s, propellant_density=propellant_density)
            for case in dataset
        ]
        return sort_missile_range_rows(evaluated)
    key = dataset_propellant_key(isp_s, propellant_density)
    return copy.deepcopy(_cached_default_dataset(*key))


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
            'ballistic_single_stage': False,
            'v_launch_mach': 0.85,
            'h_launch_km': 13.0,
        },
        'cases': evaluate_dataset(),
    }
