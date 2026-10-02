"""助推-滑翔弹射程估算（弹头容积、一至三级固体助推、滑翔航程）。"""
from __future__ import annotations

import copy
import math
from functools import lru_cache

G0 = 9.80665
R_EARTH_M = 6371000.0
SOUND_SPEED_M_S = 295.0
DEFAULT_ISP_S = 264.0
DEFAULT_PROPELLANT_DENSITY = 1760.0
PROPELLANT_MASS_FRACTION = 0.87
CHAMBER_FILL = 0.81
# 滑翔弹壳体加绝热大约占直径的 7%，药柱外径收到弹径的 93%。
HGV_MOTOR_DIAMETER_RATIO = 0.93
# 内孔装药的体积装填。0.84 比 0.81 少留一圈空腔，仍给中孔和余药留位置。
HGV_CHAMBER_FILL = 0.84
# 喷管、封头和级间段不装药。上限 1.30 m，或助推级长度的 22%，取更短的那个。
HGV_CHAMBER_DEDUCT_CAP_M = 1.30
HGV_CHAMBER_DEDUCT_FRAC = 0.22
# 复合材料壳体。结构占推进剂加壳体的 12%，金属壳体旧值是 13%。
HGV_PROPELLANT_MASS_FRACTION = 0.88
# 平衡滑翔到临近空间下沿后改末段俯冲。1500 m/s 约 Ma 5，不再把航程积到速度为 0。
GLIDE_EXIT_SPEED_M_S = 1500.0
# 13 km、约 9.05 t、弹径 1 m 的参考弹损失为 320 m/s，其中阻力约 80 m/s。
# 海平面同一发参考弹提到 1000 m/s；更轻、更细的弹再按弹道系数放大阻力。
HGV_LOSS_AT_13_M_S = 320.0
HGV_LOSS_PER_KM_ABOVE_13 = 15.0
HGV_LOSS_FLOOR_M_S = 180.0
HGV_LOSS_AT_SEA_M_S = 1000.0
HGV_DRAG_AT_13_M_S = 80.0
HGV_DRAG_SCALE_KM = 8.5
# 10.5 m × 1.0 m、战斗部 200 kg 的参考弹起飞质量，用来固定 13 km 损失仍为 320 m/s。
HGV_REF_MASS_KG = 9054.733123679523
HGV_REF_DIAMETER_M = 1.0
HGV_DRAG_SHARE_CAP = 0.72
HGV_BETA_SCALE_MIN = 0.50
HGV_BETA_SCALE_MAX = 2.60
# 每多一级的喷管、分离机构和级间段。按弹体截面积计，不随装药比例变。
# 1 m 弹径约 80 kg；更细的弹有 12 kg 下限，避免级间段轻于一圈螺栓。
STAGE_EVENT_AERAL_KG_M2 = 102.0
STAGE_EVENT_FLOOR_KG = 12.0
# 金属级间段比药柱密，同样质量占的容积更小，只挤掉这一密度对应的推进剂。
STAGE_HARDWARE_DENSITY_KG_M3 = 2700.0
# 固定死重里留到本级烧完的喷管份额，其余分离与级间段在下一级点火前抛掉。
STAGE_NOZZLE_SHARE = 0.50
# 每次分离的无动力滑行。重力损失按这段时间另计，不重复计算气动阻力。
STAGE_SEPARATION_COAST_S = 3.5
# 重力转弯平均仰角的正弦，与弹道弹燃烧损失同一档。
STAGING_GRAVITY_FACTOR = 0.64
# 推进剂分配搜索步长与单级最小份额。步长 2%，避免上面一级被收成没有喷管的空壳。
STAGE_FRACTION_STEP = 0.02
STAGE_FRACTION_MIN = 0.04
# 起飞推重比与弹道弹共用：轻弹燃烧更短，重弹趋近 2.3。
BOOST_TWR_HEAVY = 2.30
BOOST_TWR_LIGHT_EXTRA = 2.4
BOOST_TWR_SCALE_KG = 1400.0

HGV_TYPE_LABELS = {
    'biconic': '双锥体',
    'waverider': '乘波体',
}
# 长细比下限对齐升阻比公式触底的位置。再短升阻比也不再下降，只会被地板托住。
HGV_MIN_FINENESS: dict[str, float] = {
    'biconic': 1.8,
    'waverider': 2.2,
}
HGV_VOLUME_FACTOR: dict[str, float] = {
    'biconic': 0.2618,
    'waverider': 0.1745,
}
HGV_MAX_HEAD_LENGTH_RATIO = 0.45
HGV_DEFAULT_MIN_DIAMETER_RATIO = 0.35
HGV_ABSOLUTE_MIN_DIAMETER_M = 0.25

_TYPE_ALIASES = {
    'biconic': 'biconic',
    '双锥': 'biconic',
    '双锥体': 'biconic',
    'waverider': 'waverider',
    '乘波': 'waverider',
    '乘波体': 'waverider',
}


def normalize_hgv_type(hgv_type: str) -> str:
    """把构型名规范成 biconic 或 waverider。"""
    key = str(hgv_type).lower().strip()
    canon = _TYPE_ALIASES.get(key) or _TYPE_ALIASES.get(str(hgv_type).strip())
    if canon is None:
        raise ValueError(f'未知构型: {hgv_type}（可选 biconic / waverider）')
    return canon


def head_aux_ratio(warhead_mass_kg: float) -> float:
    """弹头辅助结构占战斗部质量的比例：轻弹头 0.35，重弹头 0.28。"""
    return 0.35 if warhead_mass_kg <= 250.0 else 0.28


def head_total_mass_kg(warhead_mass_kg: float) -> float:
    """战斗部加上壳体等辅助质量，辅助质量至少 40 kg。"""
    return warhead_mass_kg + max(40.0, warhead_mass_kg * head_aux_ratio(warhead_mass_kg))


def head_density_kg_m3(hgv_type: str) -> float:
    """滑翔体当量密度：双锥 1800，乘波 1650 kg/m³。"""
    return 1800.0 if normalize_hgv_type(hgv_type) == 'biconic' else 1650.0


def head_volume_m3(warhead_mass_kg: float, hgv_type: str) -> float:
    """按密度把弹头总质量折成所需体积。"""
    return head_total_mass_kg(warhead_mass_kg) / head_density_kg_m3(hgv_type)


def head_volume_factor(hgv_type: str) -> float:
    """滑翔体容积系数：双锥 0.2618，乘波 0.1745。"""
    return HGV_VOLUME_FACTOR[normalize_hgv_type(hgv_type)]


def uncapped_head_length_m(volume_m3: float, diameter_m: float, hgv_type: str) -> float:
    """由体积与弹径反推弹头长度（未按全弹比例截断）。"""
    if diameter_m <= 0:
        raise ValueError('弹径必须大于 0')
    return volume_m3 / (head_volume_factor(hgv_type) * (diameter_m ** 2))


def head_packaging_volume_m3(length_m: float, diameter_m: float, hgv_type: str) -> float:
    """按构型容积系数把滑翔体外形折成可用容积。"""
    if length_m <= 0 or diameter_m <= 0:
        raise ValueError('滑翔体长度与直径必须大于 0')
    return head_volume_factor(hgv_type) * length_m * (diameter_m ** 2)


def hgv_min_fineness(hgv_type: str) -> float:
    """滑翔体长细比下限：双锥体 1.8，乘波体 2.2，与升阻比地板对齐。"""
    return HGV_MIN_FINENESS[normalize_hgv_type(hgv_type)]


def hgv_head_diameter_bounds(
    diameter_m: float,
    min_d_head_m: float | None = None,
    max_d_head_m: float | None = None,
) -> tuple[float, float]:
    """滑翔体等效直径搜索区间：不超过弹体直径，且不低于装填/导引头口径。"""
    if diameter_m <= 0:
        raise ValueError('弹径必须大于 0')
    d_max = diameter_m if max_d_head_m is None else min(diameter_m, float(max_d_head_m))
    if min_d_head_m is None:
        d_min = max(HGV_ABSOLUTE_MIN_DIAMETER_M, diameter_m * HGV_DEFAULT_MIN_DIAMETER_RATIO)
    else:
        d_min = float(min_d_head_m)
    d_min = min(d_min, d_max)
    if d_min <= 0 or d_max <= 0:
        raise ValueError('直径范围必须大于 0')
    return d_min, d_max


def min_head_length_m(
    warhead_mass_kg: float,
    d_head_m: float,
    hgv_type: str,
    enforce_min_fineness: bool = True,
) -> float:
    """满足容积及长细比底线的滑翔体最小长度。"""
    if d_head_m <= 0:
        raise ValueError('滑翔体直径必须大于 0')
    vol = head_volume_m3(warhead_mass_kg, hgv_type)
    vol_len = uncapped_head_length_m(vol, d_head_m, hgv_type)
    if not enforce_min_fineness:
        return vol_len
    fineness_floor = hgv_min_fineness(hgv_type) * d_head_m
    return max(vol_len, fineness_floor)


def head_and_booster_lengths_m(
    length_m: float,
    diameter_m: float,
    warhead_mass_kg: float,
    hgv_type: str,
    enforce_min_fineness: bool = True,
) -> tuple[float, float]:
    """弹头长度取容积与长细比底线的较大值，且不超过全长 45%，其余视为助推级。"""
    if length_m <= 0:
        raise ValueError('弹长必须大于 0')
    raw = min_head_length_m(
        warhead_mass_kg, diameter_m, hgv_type, enforce_min_fineness=enforce_min_fineness,
    )
    l_head = min(raw, length_m * HGV_MAX_HEAD_LENGTH_RATIO)
    return l_head, length_m - l_head


def motor_cross_section_m2(diameter_m: float, diameter_ratio: float = 0.90) -> float:
    """发动机截面积。默认直径取弹径的 90%，滑翔弹可传入更薄的壳体比例。"""
    if diameter_ratio <= 0 or diameter_ratio > 1.0:
        raise ValueError('发动机直径比例必须在 (0, 1] 内')
    d_motor = diameter_m * diameter_ratio
    return math.pi * (d_motor / 2.0) ** 2


def chamber_length_m(
    l_booster_m: float,
    deduct_cap_m: float = 1.50,
    deduct_frac: float = 0.25,
) -> float:
    """有效药柱长度：扣掉接头和喷管，且不少于 0.2 m。"""
    if deduct_cap_m < 0 or deduct_frac < 0:
        raise ValueError('药柱扣除长度不能为负')
    l_deduct = min(deduct_cap_m, l_booster_m * deduct_frac)
    return max(0.2, l_booster_m - l_deduct)


def propellant_mass_kg(
    diameter_m: float,
    l_booster_m: float,
    propellant_density: float,
    diameter_ratio: float = 0.90,
    chamber_fill: float = CHAMBER_FILL,
    deduct_cap_m: float = 1.50,
    deduct_frac: float = 0.25,
) -> float:
    """药柱体积乘装填系数与推进剂密度。"""
    if chamber_fill <= 0 or chamber_fill > 1.0:
        raise ValueError('装填系数必须在 (0, 1] 内')
    volume = (
        motor_cross_section_m2(diameter_m, diameter_ratio)
        * chamber_length_m(l_booster_m, deduct_cap_m, deduct_frac)
        * chamber_fill
    )
    return volume * propellant_density


def hgv_propellant_mass_kg(
    diameter_m: float,
    l_booster_m: float,
    propellant_density: float,
) -> float:
    """滑翔弹助推药柱：壳体更薄、装填更高，喷管和级间段占的长度更短。"""
    return propellant_mass_kg(
        diameter_m,
        l_booster_m,
        propellant_density,
        diameter_ratio=HGV_MOTOR_DIAMETER_RATIO,
        chamber_fill=HGV_CHAMBER_FILL,
        deduct_cap_m=HGV_CHAMBER_DEDUCT_CAP_M,
        deduct_frac=HGV_CHAMBER_DEDUCT_FRAC,
    )


def booster_liftoff_twr(launch_mass_kg: float) -> float:
    """起飞推重比：轻型战术弹更高，重弹趋近 2.3。"""
    if launch_mass_kg <= 0:
        raise ValueError('起飞质量必须大于 0')
    extra = BOOST_TWR_LIGHT_EXTRA * math.exp(-launch_mass_kg / BOOST_TWR_SCALE_KG)
    return BOOST_TWR_HEAVY + extra


def stage_event_dead_kg(diameter_m: float) -> float:
    """多一级时新增的喷管、分离机构与级间段质量。"""
    if diameter_m <= 0:
        raise ValueError('弹径必须大于 0')
    area = math.pi * (diameter_m / 2.0) ** 2
    return max(STAGE_EVENT_FLOOR_KG, STAGE_EVENT_AERAL_KG_M2 * area)


def displaced_propellant_kg(hardware_kg: float, propellant_density: float) -> float:
    """级间死重占掉的推进剂。结构更密，挤掉的药比死重本身轻。"""
    if hardware_kg < 0 or propellant_density <= 0:
        raise ValueError('死重与推进剂密度无效')
    return hardware_kg * propellant_density / STAGE_HARDWARE_DENSITY_KG_M3


def format_stage_split(fractions: tuple[float, ...] | list[float]) -> str:
    """把推进剂份额收成和为 100 的整数百分比，例如 64/26/10。"""
    if not fractions:
        raise ValueError('推进剂分配不能为空')
    if any(part < 0 for part in fractions):
        raise ValueError('推进剂份额不能为负')
    if abs(sum(fractions) - 1.0) > 1e-6:
        raise ValueError('推进剂份额之和必须为 1')
    if len(fractions) == 1:
        return '100'
    pcts = [int(round(part * 100.0)) for part in fractions]
    pcts[-1] += 100 - sum(pcts)
    if any(part <= 0 for part in pcts):
        raise ValueError('推进剂分配圆整后出现空级')
    return '/'.join(str(part) for part in pcts)


@lru_cache(maxsize=4)
def _fraction_candidates(n_stages: int) -> tuple[tuple[float, ...], ...]:
    """一至三级的推进剂份额格点。单级只有 100%。"""
    if n_stages < 1 or n_stages > 3:
        raise ValueError('助推级数只能是 1、2 或 3')
    if n_stages == 1:
        return ((1.0,),)
    units = int(round(1.0 / STAGE_FRACTION_STEP))
    min_units = int(round(STAGE_FRACTION_MIN / STAGE_FRACTION_STEP))
    found: list[tuple[float, ...]] = []

    def walk(slots: int, remaining: int, prefix: tuple[int, ...]) -> None:
        if slots == 1:
            if remaining >= min_units:
                parts = prefix + (remaining,)
                found.append(tuple(part / units for part in parts))
            return
        upper = remaining - min_units * (slots - 1)
        for used in range(min_units, upper + 1):
            walk(slots - 1, remaining - used, prefix + (used,))

    walk(n_stages, units, ())
    return tuple(found)


def _staged_dv_and_burn(
    payload_kg: float,
    propellant_kg: float,
    hardware_kg: float,
    event_dead_kg: float,
    fractions: tuple[float, ...],
    isp_s: float,
    propellant_mass_fraction: float = PROPELLANT_MASS_FRACTION,
) -> tuple[float, float, float, float] | None:
    """给定分配，返回理想速度增量、燃烧时间、关机质量和起飞质量。

    质量组合烧穿或结构比药还重时返回 None。
    """
    if propellant_mass_fraction <= 0 or propellant_mass_fraction >= 1.0:
        raise ValueError('推进剂质量分数必须在 (0, 1) 内')
    n_stages = len(fractions)
    dry_prop = propellant_kg * (1.0 - propellant_mass_fraction) / propellant_mass_fraction
    launch_mass = payload_kg + dry_prop + hardware_kg + propellant_kg
    if launch_mass <= propellant_kg:
        return None
    ve = isp_s * G0
    mass = launch_mass
    dv = 0.0
    burn_time = 0.0
    burnout = launch_mass
    for index, share in enumerate(fractions):
        prop = share * propellant_kg
        dry = share * dry_prop
        if n_stages > 1 and index > 0:
            dry += event_dead_kg * STAGE_NOZZLE_SHARE
        if n_stages > 1 and index < n_stages - 1:
            dry += event_dead_kg * (1.0 - STAGE_NOZZLE_SHARE)
        mass_out = mass - prop
        if mass_out <= 0.0 or mass <= 0.0:
            return None
        dv += ve * math.log(mass / mass_out)
        twr = booster_liftoff_twr(mass)
        burn_time += prop * isp_s / (twr * mass)
        burnout = mass_out
        if index < n_stages - 1:
            mass = mass_out - dry
            if mass <= 0.0:
                return None
    burn_time += STAGE_SEPARATION_COAST_S * (n_stages - 1)
    return dv, burn_time, burnout, launch_mass


def build_stage_plan(
    payload_kg: float,
    propellant_kg: float,
    diameter_m: float,
    isp_s: float,
    propellant_density: float,
    fractions: tuple[float, ...],
    locked: bool = False,
    propellant_mass_fraction: float = PROPELLANT_MASS_FRACTION,
) -> dict | None:
    """把一份推进剂分配收成质量、速度增量和燃烧时间。装不下死重时返回 None。"""
    if payload_kg <= 0 or propellant_kg <= 0 or diameter_m <= 0:
        raise ValueError('载荷、推进剂与弹径必须大于 0')
    if isp_s <= 0 or propellant_density <= 0:
        raise ValueError('比冲与推进剂密度必须大于 0')
    n_stages = len(fractions)
    if n_stages < 1 or n_stages > 3:
        raise ValueError('助推级数只能是 1、2 或 3')
    event = 0.0 if n_stages == 1 else stage_event_dead_kg(diameter_m)
    hardware = event * (n_stages - 1)
    displaced = displaced_propellant_kg(hardware, propellant_density)
    if displaced >= propellant_kg:
        return None
    burned = propellant_kg - displaced
    staged = _staged_dv_and_burn(
        payload_kg, burned, hardware, event, fractions, isp_s, propellant_mass_fraction,
    )
    if staged is None:
        return None
    dv, burn_time, burnout, launch_mass = staged
    single_time = burned * isp_s / (booster_liftoff_twr(launch_mass) * launch_mass)
    extra_gravity = G0 * STAGING_GRAVITY_FACTOR * max(0.0, burn_time - single_time)
    return {
        'n_stages': n_stages,
        'fractions': fractions,
        'stage_split': format_stage_split(fractions),
        'propellant_kg': burned,
        'hardware_kg': hardware,
        'launch_mass_kg': launch_mass,
        'dv_m_s': dv,
        'burn_time_s': burn_time,
        'burnout_mass_kg': burnout,
        'extra_gravity_m_s': extra_gravity,
        'stage_locked': locked,
    }


def _best_fraction_by_impulse(
    payload_kg: float,
    propellant_kg: float,
    diameter_m: float,
    isp_s: float,
    propellant_density: float,
    n_stages: int,
    propellant_mass_fraction: float = PROPELLANT_MASS_FRACTION,
) -> tuple[float, ...] | None:
    """固定级数时，按理想速度增量减去额外重力损失选择分配。

    同一级数的起飞质量不变，滑翔弹的气动损失也不变，所以这一指标就是关机速度。
    """
    if propellant_mass_fraction <= 0 or propellant_mass_fraction >= 1.0:
        raise ValueError('推进剂质量分数必须在 (0, 1) 内')
    event = 0.0 if n_stages == 1 else stage_event_dead_kg(diameter_m)
    hardware = event * (n_stages - 1)
    displaced = displaced_propellant_kg(hardware, propellant_density)
    if displaced >= propellant_kg:
        return None
    burned = propellant_kg - displaced
    dry_frac = (1.0 - propellant_mass_fraction) / propellant_mass_fraction
    single_twr = booster_liftoff_twr(
        payload_kg + burned * dry_frac + hardware + burned,
    )
    single_time = burned * isp_s / (
        single_twr * (payload_kg + burned * dry_frac + hardware + burned)
    )
    best: tuple[float, ...] | None = None
    best_metric: float | None = None
    for fractions in _fraction_candidates(n_stages):
        staged = _staged_dv_and_burn(
            payload_kg, burned, hardware, event, fractions, isp_s, propellant_mass_fraction,
        )
        if staged is None:
            continue
        dv, burn_time, _burnout, _launch_mass = staged
        extra_gravity = G0 * STAGING_GRAVITY_FACTOR * max(0.0, burn_time - single_time)
        metric = dv - extra_gravity
        if best_metric is None or metric > best_metric + 1e-6:
            best = fractions
            best_metric = metric
    return best


def search_booster_stages(
    payload_kg: float,
    propellant_kg: float,
    diameter_m: float,
    isp_s: float,
    propellant_density: float,
    score_fn,
    stages: int | None = None,
    tie_tol: float = 0.5,
    prescreen: bool = False,
    propellant_mass_fraction: float = PROPELLANT_MASS_FRACTION,
) -> dict:
    """在给定级数里搜索推进剂分配，取得分最高的方案。

    stages 为空时比较单级、两级和三级。得分相同则保留级数更少的方案。
    prescreen 为真时，每一级只把关机速度最高的分配送去评分，供滑翔弹使用。
    """
    if stages is None:
        stage_counts = (1, 2, 3)
        locked = False
    else:
        if stages not in (1, 2, 3):
            raise ValueError('助推级数只能是 1、2 或 3')
        stage_counts = (stages,)
        locked = True
    best: dict | None = None
    best_score: float | None = None
    for n_stages in stage_counts:
        if prescreen:
            chosen = _best_fraction_by_impulse(
                payload_kg, propellant_kg, diameter_m, isp_s, propellant_density, n_stages,
                propellant_mass_fraction,
            )
            fraction_list = () if chosen is None else (chosen,)
        else:
            fraction_list = _fraction_candidates(n_stages)
        for fractions in fraction_list:
            plan = build_stage_plan(
                payload_kg, propellant_kg, diameter_m, isp_s, propellant_density,
                fractions, locked=locked, propellant_mass_fraction=propellant_mass_fraction,
            )
            if plan is None:
                continue
            score = float(score_fn(plan))
            if best_score is None or score > best_score + tie_tol:
                best = plan
                best_score = score
    if best is None or best_score is None:
        raise ValueError('没有可用的助推分级')
    best['score'] = best_score
    return best


def stage_result_sentence(plan: dict) -> str:
    """结果说明里的分级、分配、死重和额外重力损失。"""
    n_stages = int(plan['n_stages'])
    names = {1: '单级', 2: '两级', 3: '三级'}
    name = names.get(n_stages, f'{n_stages}级')
    hardware = float(plan.get('hardware_kg', plan.get('stage_hardware_kg', 0.0)))
    burn_time = float(plan['burn_time_s'])
    extra_gravity = float(plan.get('extra_gravity_m_s', 0.0))
    if plan.get('stage_locked') and n_stages == 1:
        return f"已锁定{name}，推进剂一次烧完，燃烧时间 {burn_time:.0f} s。"
    if n_stages == 1:
        return f"助推按射程取{name}，推进剂一次烧完，燃烧时间 {burn_time:.0f} s。"
    return (
        f"助推按射程取{name}，推进剂分配 {plan['stage_split']}。"
        f"喷管、分离与级间段死重 {hardware:.0f} kg，"
        f"燃烧时间 {burn_time:.0f} s，"
        f"比按单级烧完多损失 {extra_gravity:.0f} m/s。"
    )


def hgv_altitude_loss_m_s(h_launch_km: float) -> float:
    """参考弹的重力加阻力：13 km 及以上沿用原曲线，更低处抬到海平面约 1000 m/s。"""
    if h_launch_km < 0:
        raise ValueError('发射高度不能为负')
    if h_launch_km >= 13.0:
        return max(
            HGV_LOSS_FLOOR_M_S,
            HGV_LOSS_AT_13_M_S - (h_launch_km - 13.0) * HGV_LOSS_PER_KM_ABOVE_13,
        )
    span = HGV_LOSS_AT_SEA_M_S - HGV_LOSS_AT_13_M_S
    return HGV_LOSS_AT_13_M_S + (13.0 - h_launch_km) * span / 13.0


def boost_drag_height_factor(h_launch_km: float, h_burnout_km: float) -> float:
    """助推阻力相对「全程停在发射高度」的比例。

    指数大气从发射高度积到关机高度。动压峰值在爬升前段，
    所以保留七成发射高度阻力，只把三成换成这段爬升的平均值。
    """
    if h_launch_km < 0 or h_burnout_km < 0:
        raise ValueError('发射高度与关机高度不能为负')
    if h_burnout_km + 1e-9 < h_launch_km:
        raise ValueError('关机高度不能低于发射高度')
    span = h_burnout_km - h_launch_km
    if span < 1.0:
        return 1.0
    mean = (HGV_DRAG_SCALE_KM / span) * (1.0 - math.exp(-span / HGV_DRAG_SCALE_KM))
    return 0.70 + 0.30 * mean


def gravity_drag_loss_m_s(
    h_launch_km: float,
    mass_kg: float | None = None,
    diameter_m: float | None = None,
    h_burnout_km: float | None = None,
) -> float:
    """重力与阻力速度损失。

    不给质量时按参考弹。给出质量后，阻力按弹道系数相对参考弹缩放，
    轻而细的弹在海平面多损失一截，13 km 的参考弹仍是 320 m/s。
    给出关机高度后，阻力只按爬升穿过稠密大气的那一段计，不再按全程海平面。
    """
    baseline = hgv_altitude_loss_m_s(h_launch_km)
    if mass_kg is None and diameter_m is None:
        if h_burnout_km is not None:
            raise ValueError('给出关机高度时必须同时给出质量与弹径')
        return baseline
    if mass_kg is None or diameter_m is None:
        raise ValueError('质量与弹径必须同时给出')
    if mass_kg <= 0 or diameter_m <= 0:
        raise ValueError('质量与弹径必须大于 0')
    drag_ref = HGV_DRAG_AT_13_M_S * math.exp(-(h_launch_km - 13.0) / HGV_DRAG_SCALE_KM)
    drag_ref = min(drag_ref, baseline * HGV_DRAG_SHARE_CAP)
    if h_burnout_km is not None:
        drag_ref *= boost_drag_height_factor(h_launch_km, h_burnout_km)
    beta_ref = HGV_REF_MASS_KG / (math.pi * (HGV_REF_DIAMETER_M / 2.0) ** 2)
    beta = mass_kg / (math.pi * (diameter_m / 2.0) ** 2)
    scale = min(HGV_BETA_SCALE_MAX, max(HGV_BETA_SCALE_MIN, beta_ref / beta))
    return baseline - drag_ref + drag_ref * scale


def lift_drag_ratio(glide_length_m: float, diameter_m: float, hgv_type: str) -> float:
    """按抛掉助推级之后的滑翔体长细比，夹在构型允许的升阻比区间内。"""
    if glide_length_m <= 0 or diameter_m <= 0:
        raise ValueError('滑翔体长度与弹径必须大于 0')
    fineness = glide_length_m / diameter_m
    if normalize_hgv_type(hgv_type) == 'biconic':
        return max(1.8, min(3.5, 1.5 + 0.18 * fineness))
    # 短乘波体在高超声速的升阻比大约 3.5–4，不再从 2.2 起算。
    return max(2.8, min(5.0, 2.4 + 0.32 * fineness))


def glide_exit_ratio() -> float:
    """临近空间下沿对应的速度能量比，滑翔积分到这里为止。"""
    return (GLIDE_EXIT_SPEED_M_S ** 2) / (G0 * R_EARTH_M)


def glide_range_m(ratio_v2: float, ld_ratio: float) -> float:
    """平衡滑翔航程，积到临近空间下沿；接近轨道能量时封顶 16000 km。

    对数项是从入口速度积到出口速度。1 + 0.35 v²/vc² 把下滑过程换回的高度势能补上一点。
    """
    if ratio_v2 >= 0.95:
        return 16000000.0
    if ratio_v2 < 0.0:
        raise ValueError('滑翔能量参数超出估算范围')
    exit_ratio = glide_exit_ratio()
    if ratio_v2 <= exit_ratio:
        return 0.0
    return (
        0.5 * R_EARTH_M * ld_ratio
        * math.log((1.0 - exit_ratio) / (1.0 - ratio_v2))
        * (1.0 + 0.35 * ratio_v2)
    )


def _require_non_negative(name: str, value: float) -> float:
    if value < 0:
        raise ValueError(f'{name}不能为负')
    return value


def hgv_burnout_altitude_km(speed_m_s: float, h_launch_km: float) -> float:
    """关机高度沿用弹道弹的爬升关系。函数内导入，避免和 classes 顶层循环引用。"""
    from utils.missile_range.classes import burnout_altitude_km
    return burnout_altitude_km(speed_m_s, h_launch_km)


def _round_hgv_result(
    m_0: float,
    l_head: float,
    l_booster: float,
    m_propellant: float,
    v_burnout: float,
    ld_ratio: float,
    total_range_km: float,
    d_head: float,
    h_burnout_km: float,
    stage: dict | None = None,
) -> dict:
    """把内部未舍入的助推滑翔结果收成对外字段。"""
    result = {
        'm_0_t': round(m_0 / 1000.0, 2),
        'l_head_m': round(l_head, 2),
        'l_booster_m': round(l_booster, 2),
        'm_p_total_kg': round(m_propellant, 1),
        'v_burnout_mach': round(v_burnout / SOUND_SPEED_M_S, 2),
        'ld_ratio': round(ld_ratio, 2),
        'range_km': round(total_range_km, 1),
        'd_head_m': round(d_head, 3),
        'fineness': round(l_head / d_head, 2),
        'h_burnout_km': round(h_burnout_km, 1),
    }
    if stage is not None:
        result['n_stages'] = int(stage['n_stages'])
        result['stage_split'] = stage['stage_split']
        result['stage_hardware_kg'] = round(float(stage['hardware_kg']), 1)
        result['burn_time_s'] = round(float(stage['burn_time_s']), 1)
        result['extra_gravity_m_s'] = round(float(stage['extra_gravity_m_s']), 1)
        result['stage_locked'] = bool(stage.get('stage_locked'))
    return result


def estimate_hgv_unrounded(
    length_m: float,
    diameter_m: float,
    warhead_mass_kg: float,
    hgv_type: str = 'biconic',
    v_launch_mach: float = 0.85,
    h_launch_km: float = 13.0,
    isp_s: float = DEFAULT_ISP_S,
    propellant_density: float = DEFAULT_PROPELLANT_DENSITY,
    l_head_m: float | None = None,
    d_head_m: float | None = None,
    enforce_min_fineness: bool = True,
) -> dict:
    """估算助推滑翔弹，返回未舍入的质量、速度与射程，供几何搜索比较。"""
    hgv_type = normalize_hgv_type(hgv_type)
    if length_m <= 0 or diameter_m <= 0:
        raise ValueError('弹长与弹径必须大于 0')
    if isp_s <= 0 or propellant_density <= 0:
        raise ValueError('比冲与推进剂密度必须大于 0')
    _require_non_negative('战斗部质量', warhead_mass_kg)
    _require_non_negative('发射马赫数', v_launch_mach)
    _require_non_negative('发射高度', h_launch_km)

    d_head = diameter_m if d_head_m is None else float(d_head_m)
    if d_head <= 0 or d_head > diameter_m:
        raise ValueError('滑翔体直径必须大于 0 且不超过弹体直径')

    vol_req = head_volume_m3(warhead_mass_kg, hgv_type)
    specified = l_head_m is not None
    if specified:
        l_head = float(l_head_m)
        if l_head <= 0 or l_head >= length_m:
            raise ValueError('滑翔体长度必须大于 0 且小于全弹长')
        l_booster = length_m - l_head
    else:
        l_head, l_booster = head_and_booster_lengths_m(
            length_m, d_head, warhead_mass_kg, hgv_type,
            enforce_min_fineness=enforce_min_fineness,
        )
    if specified and head_packaging_volume_m3(l_head, d_head, hgv_type) + 1e-9 < vol_req:
        raise ValueError('滑翔体容积不足以容纳战斗部与制控组件')

    v_launch_ms = v_launch_mach * SOUND_SPEED_M_S
    m_head_total = head_total_mass_kg(warhead_mass_kg)
    m_propellant_geom = hgv_propellant_mass_kg(diameter_m, l_booster, propellant_density)

    def lofted_speed_m_s(plan: dict) -> tuple[float, float]:
        """按爬升后的阻力重算关机速度，并返回对应关机高度。"""
        speed = v_launch_ms + plan['dv_m_s'] - plan['extra_gravity_m_s']
        h_burn = h_launch_km
        for _ in range(2):
            h_burn = hgv_burnout_altitude_km(max(speed, 0.0), h_launch_km)
            loss = gravity_drag_loss_m_s(
                h_launch_km, plan['launch_mass_kg'], diameter_m, h_burn,
            )
            speed = v_launch_ms + plan['dv_m_s'] - loss - plan['extra_gravity_m_s']
        return speed, h_burn

    def score_plan(plan: dict) -> float:
        # 关机速度已经含分级死重、更长燃烧的重力损失，以及高抛后少掉的稠密大气阻力。
        speed, _h_burn = lofted_speed_m_s(plan)
        return speed

    stage = search_booster_stages(
        m_head_total, m_propellant_geom, diameter_m, isp_s, propellant_density, score_plan,
        prescreen=True,
        propellant_mass_fraction=HGV_PROPELLANT_MASS_FRACTION,
    )
    m_0 = stage['launch_mass_kg']
    m_propellant = stage['propellant_kg']
    v_burnout, h_burnout_km = lofted_speed_m_s(stage)
    v_burnout = max(0.0, v_burnout)
    ld_ratio = lift_drag_ratio(l_head, d_head, hgv_type)
    # 平衡滑翔公式用的是飞行速度。关机高度已经体现在助推阻力里，再加 2gh 会和走廊积分重复。
    v_eff2 = v_burnout ** 2 + 2.0 * G0 * (h_launch_km * 1000.0)
    ratio_v2 = max(0.0, v_eff2 / (G0 * R_EARTH_M))
    glide_m = glide_range_m(ratio_v2, ld_ratio)
    boost_m = (v_launch_ms + max(v_burnout, 0.0)) / 2.0 * 60.0 + h_launch_km * 1000.0 * 2.0
    total_range_km = (boost_m + glide_m) / 1000.0
    return {
        'm_0': m_0,
        'l_head_m': l_head,
        'l_booster_m': l_booster,
        'm_propellant': m_propellant,
        'v_burnout': v_burnout,
        'ld_ratio': ld_ratio,
        'range_km': total_range_km,
        'd_head_m': d_head,
        'fineness': l_head / d_head,
        'h_burnout_km': h_burnout_km,
        'stage': stage,
    }


def estimate_hgv(
    length_m: float,
    diameter_m: float,
    warhead_mass_kg: float,
    hgv_type: str = 'biconic',
    v_launch_mach: float = 0.85,
    h_launch_km: float = 13.0,
    isp_s: float = DEFAULT_ISP_S,
    propellant_density: float = DEFAULT_PROPELLANT_DENSITY,
    l_head_m: float | None = None,
    d_head_m: float | None = None,
    optimize_geometry: bool = False,
    min_fineness: float | None = None,
    min_d_head_m: float | None = None,
    max_d_head_m: float | None = None,
    max_head_length_ratio: float = HGV_MAX_HEAD_LENGTH_RATIO,
) -> dict:
    """估算起飞质量、关机马赫数、升阻比与总射程（千米）。

    未指定滑翔体尺寸时按容积与长细比底线划分弹头；开启 optimize_geometry
    则在弹径以内搜索使总射程最大的滑翔体长度与等效直径。
    """
    if optimize_geometry:
        return optimize_hgv_geometry(
            length_m=length_m,
            diameter_m=diameter_m,
            warhead_mass_kg=warhead_mass_kg,
            hgv_type=hgv_type,
            v_launch_mach=v_launch_mach,
            h_launch_km=h_launch_km,
            isp_s=isp_s,
            propellant_density=propellant_density,
            min_fineness=min_fineness,
            min_d_head_m=min_d_head_m,
            max_d_head_m=max_d_head_m,
            max_head_length_ratio=max_head_length_ratio,
        )['result']
    raw = estimate_hgv_unrounded(
        length_m=length_m,
        diameter_m=diameter_m,
        warhead_mass_kg=warhead_mass_kg,
        hgv_type=hgv_type,
        v_launch_mach=v_launch_mach,
        h_launch_km=h_launch_km,
        isp_s=isp_s,
        propellant_density=propellant_density,
        l_head_m=l_head_m,
        d_head_m=d_head_m,
    )
    return _round_hgv_result(
        raw['m_0'], raw['l_head_m'], raw['l_booster_m'], raw['m_propellant'],
        raw['v_burnout'], raw['ld_ratio'], raw['range_km'], raw['d_head_m'],
        raw['h_burnout_km'], stage=raw['stage'],
    )


def _optimize_geometry_cache_key(
    length_m: float,
    diameter_m: float,
    warhead_mass_kg: float,
    hgv_type: str,
    v_launch_mach: float,
    h_launch_km: float,
    isp_s: float,
    propellant_density: float,
    min_fineness: float | None,
    min_d_head_m: float | None,
    max_d_head_m: float | None,
    max_head_length_ratio: float,
    grid_points_d: int,
    grid_points_l: int,
) -> tuple:
    """把寻优参数收成可哈希键，避免预设表反复扫同一发弹。"""
    return (
        round(length_m, 6), round(diameter_m, 6), round(warhead_mass_kg, 4),
        normalize_hgv_type(hgv_type), round(v_launch_mach, 6), round(h_launch_km, 6),
        round(isp_s, 4), round(propellant_density, 4),
        None if min_fineness is None else round(float(min_fineness), 6),
        None if min_d_head_m is None else round(float(min_d_head_m), 6),
        None if max_d_head_m is None else round(float(max_d_head_m), 6),
        round(max_head_length_ratio, 6), int(grid_points_d), int(grid_points_l),
    )


@lru_cache(maxsize=512)
def _optimize_hgv_geometry_cached(key: tuple) -> dict:
    """按缓存键搜索滑翔体几何。"""
    return _optimize_hgv_geometry_compute(*key)


def optimize_hgv_geometry(
    length_m: float,
    diameter_m: float,
    warhead_mass_kg: float,
    hgv_type: str = 'biconic',
    v_launch_mach: float = 0.85,
    h_launch_km: float = 13.0,
    isp_s: float = DEFAULT_ISP_S,
    propellant_density: float = DEFAULT_PROPELLANT_DENSITY,
    min_fineness: float | None = None,
    min_d_head_m: float | None = None,
    max_d_head_m: float | None = None,
    max_head_length_ratio: float = HGV_MAX_HEAD_LENGTH_RATIO,
    grid_points_d: int = 24,
    grid_points_l: int = 24,
) -> dict:
    """搜索包含战斗部与制控组件的滑翔体最优长度与直径（使总射程最大）。"""
    key = _optimize_geometry_cache_key(
        length_m, diameter_m, warhead_mass_kg, hgv_type, v_launch_mach,
        h_launch_km, isp_s, propellant_density, min_fineness, min_d_head_m,
        max_d_head_m, max_head_length_ratio, grid_points_d, grid_points_l,
    )
    return copy.deepcopy(_optimize_hgv_geometry_cached(key))


def _optimize_hgv_geometry_compute(
    length_m: float,
    diameter_m: float,
    warhead_mass_kg: float,
    hgv_type: str,
    v_launch_mach: float,
    h_launch_km: float,
    isp_s: float,
    propellant_density: float,
    min_fineness: float | None,
    min_d_head_m: float | None,
    max_d_head_m: float | None,
    max_head_length_ratio: float,
    grid_points_d: int,
    grid_points_l: int,
) -> dict:
    """真正扫网格的滑翔体寻优。网格比较用未舍入射程。"""
    hgv_type = normalize_hgv_type(hgv_type)
    if grid_points_d < 1 or grid_points_l < 1:
        raise ValueError('搜索网格点数必须大于 0')
    floor_fineness = hgv_min_fineness(hgv_type) if min_fineness is None else float(min_fineness)
    if floor_fineness <= 0:
        raise ValueError('长细比下限必须大于 0')
    d_min, d_max = hgv_head_diameter_bounds(diameter_m, min_d_head_m, max_d_head_m)
    l_max = length_m * max_head_length_ratio
    vol_req = head_volume_m3(warhead_mass_kg, hgv_type)
    common = dict(
        length_m=length_m, diameter_m=diameter_m, warhead_mass_kg=warhead_mass_kg,
        hgv_type=hgv_type, v_launch_mach=v_launch_mach, h_launch_km=h_launch_km,
        isp_s=isp_s, propellant_density=propellant_density,
    )
    base_raw = estimate_hgv_unrounded(**common)
    best_raw = dict(base_raw)
    for i in range(grid_points_d + 1):
        dh = d_min + (d_max - d_min) * (i / grid_points_d)
        vol_len = uncapped_head_length_m(vol_req, dh, hgv_type)
        lh_min = max(vol_len, floor_fineness * dh)
        if lh_min > l_max:
            continue
        for j in range(grid_points_l + 1):
            lh = lh_min + (l_max - lh_min) * (j / grid_points_l)
            try:
                candidate = estimate_hgv_unrounded(**common, l_head_m=lh, d_head_m=dh)
            except ValueError:
                continue
            if candidate['range_km'] > best_raw['range_km']:
                best_raw = candidate
    base = _round_hgv_result(
        base_raw['m_0'], base_raw['l_head_m'], base_raw['l_booster_m'],
        base_raw['m_propellant'], base_raw['v_burnout'], base_raw['ld_ratio'],
        base_raw['range_km'], base_raw['d_head_m'], base_raw['h_burnout_km'],
        stage=base_raw['stage'],
    )
    best_res = _round_hgv_result(
        best_raw['m_0'], best_raw['l_head_m'], best_raw['l_booster_m'],
        best_raw['m_propellant'], best_raw['v_burnout'], best_raw['ld_ratio'],
        best_raw['range_km'], best_raw['d_head_m'], best_raw['h_burnout_km'],
        stage=best_raw['stage'],
    )
    best_lh = best_raw['l_head_m']
    best_dh = best_raw['d_head_m']
    best_range = float(best_res['range_km'])
    base_range = float(base['range_km'])
    gain_km = round(best_range - base_range, 1)
    gain_pct = round(gain_km / base_range * 100.0, 2) if base_range > 0 else 0.0
    best_res['optimal_geometry'] = True
    best_res['range_gain_km'] = gain_km
    best_res['range_gain_pct'] = gain_pct
    best_res['baseline_range_km'] = base_range
    best_res['baseline_l_head_m'] = float(base['l_head_m'])
    best_res['baseline_d_head_m'] = float(base['d_head_m'])
    best_res['baseline_ld_ratio'] = float(base['ld_ratio'])
    return {
        'best_l_head_m': round(best_lh, 2),
        'best_d_head_m': round(best_dh, 3),
        'best_l_booster_m': round(length_m - best_lh, 2),
        'best_fineness': round(best_lh / best_dh, 2),
        'best_ld_ratio': float(best_res['ld_ratio']),
        'max_range_km': best_range,
        'baseline_range_km': base_range,
        'baseline_l_head_m': float(base['l_head_m']),
        'baseline_d_head_m': float(base['d_head_m']),
        'baseline_ld_ratio': float(base['ld_ratio']),
        'range_gain_km': gain_km,
        'range_gain_pct': gain_pct,
        'result': best_res,
        'baseline_result': base,
    }
