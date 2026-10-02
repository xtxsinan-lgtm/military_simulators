"""助推-滑翔弹射程估算（弹头容积、两级推进剂、滑翔航程）。"""
from __future__ import annotations

import copy
import math
from functools import lru_cache

G0 = 9.80665
R_EARTH_M = 6371000.0
SOUND_SPEED_M_S = 295.0
DEFAULT_ISP_S = 264.0
DEFAULT_PROPELLANT_DENSITY = 1760.0
GLIDE_EFF = 0.513
PROPELLANT_MASS_FRACTION = 0.87
CHAMBER_FILL = 0.81
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

HGV_TYPE_LABELS = {
    'biconic': '双锥体',
    'waverider': '乘波体',
}
# 气动合理的滑翔体长细比下限：过短会变成钝头扁锥，升阻比被模型下限兜住但不真实。
HGV_MIN_FINENESS: dict[str, float] = {
    'biconic': 2.5,
    'waverider': 3.5,
}
HGV_VOLUME_FACTOR: dict[str, float] = {
    'biconic': 0.2618,
    'waverider': 0.1745,
}
HGV_MAX_HEAD_LENGTH_RATIO = 0.45
# 后缘/底径默认等于弹径，不再把滑翔体缩成细杆去抬升阻比。
HGV_DEFAULT_MIN_DIAMETER_RATIO = 1.0
HGV_ABSOLUTE_MIN_DIAMETER_M = 0.25
# 牛顿平板最优升阻比用的零升阻力。扁平三角摩擦小，旋成双锥湿面积更大。
WAVERIDER_FRICTION_CD0 = 0.0020
BICONIC_FRICTION_CD0 = 0.0045
# 零升波阻系数：乘以半厚度角或半锥角（弧度）的平方。
HGV_WAVE_DRAG_K = 0.55

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
    """滑翔体合理气动长细比下限：双锥体 2.5，乘波体 3.5。"""
    return HGV_MIN_FINENESS[normalize_hgv_type(hgv_type)]


def waverider_thickness_to_span() -> float:
    """扁平三角后缘厚度与后缘宽度之比。

    双锥容积系数就是同底径圆锥。乘波体容积更小，相当于把这个圆锥
    沿铅垂方向压扁，后缘仍等于弹径。
    """
    return HGV_VOLUME_FACTOR['waverider'] / HGV_VOLUME_FACTOR['biconic']


def waverider_thickness_m(trailing_edge_m: float) -> float:
    """乘波体后缘厚度。后缘宽度应等于弹径。"""
    if trailing_edge_m <= 0:
        raise ValueError('后缘宽度必须大于 0')
    return trailing_edge_m * waverider_thickness_to_span()


def glide_body_mass_kg(
    length_m: float,
    diameter_m: float,
    warhead_mass_kg: float,
    hgv_type: str,
) -> float:
    """滑翔体质量按实际外形容积计，且不低于战斗部加制控。

    长细比把外形撑得比战斗部所需更大时，多出来的壳体和防热要算进起飞质量。
    """
    if length_m <= 0 or diameter_m <= 0:
        raise ValueError('滑翔体长度与直径必须大于 0')
    payload = head_total_mass_kg(warhead_mass_kg)
    shell = head_packaging_volume_m3(length_m, diameter_m, hgv_type) * head_density_kg_m3(hgv_type)
    return max(payload, shell)


def hypersonic_flatplate_ld(cd0: float) -> float:
    """小迎角牛顿平板的最优升阻比：2 / (3 · CD0^(1/3))。"""
    if cd0 <= 0:
        raise ValueError('零升阻力系数必须大于 0')
    return 2.0 / (3.0 * cd0 ** (1.0 / 3.0))


def hgv_head_diameter_bounds(
    diameter_m: float,
    min_d_head_m: float | None = None,
    max_d_head_m: float | None = None,
) -> tuple[float, float]:
    """后缘或底径的搜索区间。默认锁在弹径上，调用方仍可收窄。"""
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


def motor_cross_section_m2(diameter_m: float) -> float:
    """发动机直径取弹径的 90%。"""
    d_motor = diameter_m * 0.90
    return math.pi * (d_motor / 2.0) ** 2


def chamber_length_m(l_booster_m: float) -> float:
    """有效药柱长度：扣掉接头/喷管，且不少于 0.2 m。"""
    l_deduct = min(1.50, l_booster_m * 0.25)
    return max(0.2, l_booster_m - l_deduct)


def propellant_mass_kg(
    diameter_m: float,
    l_booster_m: float,
    propellant_density: float,
) -> float:
    """药柱体积乘装填系数与推进剂密度。"""
    volume = motor_cross_section_m2(diameter_m) * chamber_length_m(l_booster_m) * CHAMBER_FILL
    return volume * propellant_density


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


def gravity_drag_loss_m_s(
    h_launch_km: float,
    mass_kg: float | None = None,
    diameter_m: float | None = None,
) -> float:
    """重力与阻力速度损失。

    不给质量时按参考弹。给出质量后，阻力按弹道系数相对参考弹缩放，
    轻而细的弹在海平面多损失一截，13 km 的参考弹仍是 320 m/s。
    """
    baseline = hgv_altitude_loss_m_s(h_launch_km)
    if mass_kg is None and diameter_m is None:
        return baseline
    if mass_kg is None or diameter_m is None:
        raise ValueError('质量与弹径必须同时给出')
    if mass_kg <= 0 or diameter_m <= 0:
        raise ValueError('质量与弹径必须大于 0')
    drag_ref = HGV_DRAG_AT_13_M_S * math.exp(-(h_launch_km - 13.0) / HGV_DRAG_SCALE_KM)
    drag_ref = min(drag_ref, baseline * HGV_DRAG_SHARE_CAP)
    beta_ref = HGV_REF_MASS_KG / (math.pi * (HGV_REF_DIAMETER_M / 2.0) ** 2)
    beta = mass_kg / (math.pi * (diameter_m / 2.0) ** 2)
    scale = min(HGV_BETA_SCALE_MAX, max(HGV_BETA_SCALE_MIN, beta_ref / beta))
    return baseline - drag_ref + drag_ref * scale


def lift_drag_ratio(glide_length_m: float, diameter_m: float, hgv_type: str) -> float:
    """按后缘或底径等于给定宽度来估算升阻比。

    乘波体前段是较扁的等腰三角，后缘宽度就是这个直径，厚度由容积系数
    相对圆锥压扁得到。波阻用铅垂半厚度角。
    双锥体是旋成体，底圆直径同样取这个值，波阻用半锥角；湿面积更大，摩擦更高。
    两者都把零升阻力放进牛顿平板的最优迎角，不再靠缩小直径抬升阻比。
    """
    if glide_length_m <= 0 or diameter_m <= 0:
        raise ValueError('滑翔体长度与弹径必须大于 0')
    if normalize_hgv_type(hgv_type) == 'waverider':
        half_angle = math.atan((waverider_thickness_m(diameter_m) / 2.0) / glide_length_m)
        cd0 = WAVERIDER_FRICTION_CD0 + HGV_WAVE_DRAG_K * half_angle * half_angle
    else:
        half_angle = math.atan((diameter_m / 2.0) / glide_length_m)
        cd0 = BICONIC_FRICTION_CD0 + HGV_WAVE_DRAG_K * half_angle * half_angle
    return hypersonic_flatplate_ld(cd0)


def glide_range_m(ratio_v2: float, ld_ratio: float) -> float:
    """能量参数对应的滑翔航程；接近轨道能量时封顶 16000 km。"""
    if ratio_v2 >= 0.95:
        return 16000000.0
    if ratio_v2 < 0.0:
        raise ValueError('滑翔能量参数超出估算范围')
    return (
        0.5 * R_EARTH_M * ld_ratio
        * math.log(1.0 / (1.0 - ratio_v2))
        * (1.0 + 0.35 * ratio_v2)
        * GLIDE_EFF
    )


def _require_non_negative(name: str, value: float) -> float:
    if value < 0:
        raise ValueError(f'{name}不能为负')
    return value


def _round_hgv_result(
    m_0: float,
    l_head: float,
    l_booster: float,
    m_propellant: float,
    v_burnout: float,
    ld_ratio: float,
    total_range_km: float,
    d_head: float,
) -> dict:
    """把内部未舍入的助推滑翔结果收成对外字段。"""
    return {
        'm_0_t': round(m_0 / 1000.0, 2),
        'l_head_m': round(l_head, 2),
        'l_booster_m': round(l_booster, 2),
        'm_p_total_kg': round(m_propellant, 1),
        'v_burnout_mach': round(v_burnout / SOUND_SPEED_M_S, 2),
        'ld_ratio': round(ld_ratio, 2),
        'range_km': round(total_range_km, 1),
        'd_head_m': round(d_head, 3),
        'fineness': round(l_head / d_head, 2),
    }


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
    m_head_total = glide_body_mass_kg(l_head, d_head, warhead_mass_kg, hgv_type)
    m_propellant = propellant_mass_kg(diameter_m, l_booster, propellant_density)
    pmf = PROPELLANT_MASS_FRACTION
    m_booster_dry = m_propellant * (1.0 - pmf) / pmf
    m_0 = m_head_total + m_booster_dry + m_propellant

    v_e = isp_s * G0
    m_p1 = m_propellant * 0.58
    m_p2 = m_propellant * 0.42
    m_s1 = m_booster_dry * 0.60
    m_stg1_out = m_0 - m_p1
    m_stg2_in = m_stg1_out - m_s1
    m_stg2_out = m_stg2_in - m_p2
    if min(m_stg1_out, m_stg2_in, m_stg2_out) <= 0:
        raise ValueError('推进剂或结构质量组合无效，无法计算速度增量')

    dv1 = v_e * math.log(m_0 / m_stg1_out)
    dv2 = v_e * math.log(m_stg2_in / m_stg2_out)
    v_burnout = v_launch_ms + (dv1 + dv2) - gravity_drag_loss_m_s(
        h_launch_km, m_0, diameter_m,
    )
    ld_ratio = lift_drag_ratio(l_head, d_head, hgv_type)
    v_eff2 = v_burnout ** 2 + 2.0 * G0 * (h_launch_km * 1000.0)
    ratio_v2 = v_eff2 / (G0 * R_EARTH_M)
    glide_m = glide_range_m(ratio_v2, ld_ratio)
    boost_m = (v_launch_ms + v_burnout) / 2.0 * 60.0 + h_launch_km * 1000.0 * 2.0
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
    则在后缘或底径锁定为弹径的前提下搜索使总射程最大的滑翔体长度。
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
        base_raw['range_km'], base_raw['d_head_m'],
    )
    best_res = _round_hgv_result(
        best_raw['m_0'], best_raw['l_head_m'], best_raw['l_booster_m'],
        best_raw['m_propellant'], best_raw['v_burnout'], best_raw['ld_ratio'],
        best_raw['range_km'], best_raw['d_head_m'],
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
