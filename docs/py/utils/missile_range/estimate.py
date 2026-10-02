"""助推-滑翔弹射程估算（弹头容积、两级推进剂、滑翔航程）。"""
from __future__ import annotations

import math

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
HGV_MIN_FINENESS: dict[str, float] = {
    'biconic': 2.0,
    'waverider': 3.0,
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


def uncapped_head_length_m(volume_m3: float, diameter_m: float, hgv_type: str) -> float:
    """由体积与弹径反推弹头长度（未按全弹比例截断）。"""
    if diameter_m <= 0:
        raise ValueError('弹径必须大于 0')
    factor = 0.2618 if normalize_hgv_type(hgv_type) == 'biconic' else 0.1745
    return volume_m3 / (factor * (diameter_m ** 2))


def hgv_min_fineness(hgv_type: str) -> float:
    """滑翔体合理气动长细比下限：双锥体 2.0，乘波体 3.0。"""
    return HGV_MIN_FINENESS[normalize_hgv_type(hgv_type)]


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
    enforce_min_fineness: bool = False,
) -> tuple[float, float]:
    """弹头长度不超过全长 45%，其余视为助推级。可按长细比下限修正。"""
    if length_m <= 0:
        raise ValueError('弹长必须大于 0')
    raw = uncapped_head_length_m(
        head_volume_m3(warhead_mass_kg, hgv_type), diameter_m, hgv_type,
    )
    if enforce_min_fineness:
        raw = max(raw, hgv_min_fineness(hgv_type) * diameter_m)
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
    """按抛掉助推级之后的滑翔体长细比，夹在构型允许的升阻比区间内。"""
    if glide_length_m <= 0 or diameter_m <= 0:
        raise ValueError('滑翔体长度与弹径必须大于 0')
    fineness = glide_length_m / diameter_m
    if normalize_hgv_type(hgv_type) == 'biconic':
        return max(1.8, min(3.5, 1.5 + 0.18 * fineness))
    return max(2.8, min(5.0, 2.2 + 0.28 * fineness))


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

    支持指定滑翔体独立长径 (l_head_m, d_head_m)，或开启 optimize_geometry 寻优最大射程。
    乘波体当量密度更低、容积系数更小，同样战斗部的弹头更长，助推级装药更少。
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

    if l_head_m is not None:
        l_head = float(l_head_m)
        if l_head <= 0 or l_head >= length_m:
            raise ValueError('滑翔体长度必须大于 0 且小于全弹长')
        l_booster = length_m - l_head
    else:
        l_head, l_booster = head_and_booster_lengths_m(
            length_m, d_head, warhead_mass_kg, hgv_type,
        )

    v_launch_ms = v_launch_mach * SOUND_SPEED_M_S
    m_head_total = head_total_mass_kg(warhead_mass_kg)
    m_propellant = propellant_mass_kg(diameter_m, l_booster, propellant_density)
    pmf = PROPELLANT_MASS_FRACTION
    m_booster_dry = m_propellant * (1.0 - pmf) / pmf
    m_0 = m_head_total + m_booster_dry + m_propellant

    v_e = isp_s * G0
    m_p1 = m_propellant * 0.58
    m_p2 = m_propellant * 0.42
    m_s1 = m_booster_dry * 0.60

    m_stg1_in = m_0
    m_stg1_out = m_stg1_in - m_p1
    m_stg2_in = m_stg1_out - m_s1
    m_stg2_out = m_stg2_in - m_p2
    if min(m_stg1_out, m_stg2_in, m_stg2_out) <= 0:
        raise ValueError('推进剂或结构质量组合无效，无法计算速度增量')

    dv1 = v_e * math.log(m_stg1_in / m_stg1_out)
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

    res = {
        'm_0_t': round(m_0 / 1000.0, 2),
        'l_head_m': round(l_head, 2),
        'l_booster_m': round(l_booster, 2),
        'm_p_total_kg': round(m_propellant, 1),
        'v_burnout_mach': round(v_burnout / SOUND_SPEED_M_S, 2),
        'ld_ratio': round(ld_ratio, 2),
        'range_km': round(total_range_km, 1),
    }
    if d_head_m is not None:
        res['d_head_m'] = round(d_head, 3)
        res['fineness'] = round(l_head / d_head, 2)
    return res


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
    grid_points_d: int = 40,
    grid_points_l: int = 40,
) -> dict:
    """搜索包含战斗部与制控组件的滑翔体最优长度与直径（使总射程最大）。

    在保证战斗部与制导控制组件所需容积的前提下，综合权衡：
    1. 滑翔体做长做细提升长细比与升阻比（增程）；
    2. 助推器剩余长度与装药量（提供关机初速）；
    3. 直径不超过全弹弹体直径，且满足气动长细比下限约束。
    """
    hgv_type = normalize_hgv_type(hgv_type)
    if length_m <= 0 or diameter_m <= 0:
        raise ValueError('弹长与弹径必须大于 0')
    if isp_s <= 0 or propellant_density <= 0:
        raise ValueError('比冲与推进剂密度必须大于 0')
    _require_non_negative('战斗部质量', warhead_mass_kg)
    _require_non_negative('发射马赫数', v_launch_mach)
    _require_non_negative('发射高度', h_launch_km)

    floor_fineness = hgv_min_fineness(hgv_type) if min_fineness is None else float(min_fineness)
    if floor_fineness <= 0:
        raise ValueError('长细比下限必须大于 0')

    d_max = diameter_m if max_d_head_m is None else min(diameter_m, float(max_d_head_m))
    d_min = max(HGV_ABSOLUTE_MIN_DIAMETER_M, diameter_m * HGV_DEFAULT_MIN_DIAMETER_RATIO) if min_d_head_m is None else float(min_d_head_m)
    d_min = min(d_min, d_max)
    if d_min <= 0 or d_max <= 0:
        raise ValueError('直径范围必须大于 0')

    l_max = length_m * max_head_length_ratio
    vol_req = head_volume_m3(warhead_mass_kg, hgv_type)

    base = estimate_hgv(
        length_m=length_m,
        diameter_m=diameter_m,
        warhead_mass_kg=warhead_mass_kg,
        hgv_type=hgv_type,
        v_launch_mach=v_launch_mach,
        h_launch_km=h_launch_km,
        isp_s=isp_s,
        propellant_density=propellant_density,
        optimize_geometry=False,
    )
    best_range = float(base['range_km'])
    best_lh = float(base['l_head_m'])
    best_dh = float(diameter_m)
    best_res = dict(base)
    best_res['d_head_m'] = round(best_dh, 3)
    best_res['fineness'] = round(best_lh / best_dh, 2)

    for i in range(grid_points_d + 1):
        dh = d_min + (d_max - d_min) * (i / max(1, grid_points_d))
        vol_len = uncapped_head_length_m(vol_req, dh, hgv_type)
        lh_min = max(vol_len, floor_fineness * dh)
        if lh_min > l_max:
            continue
        for j in range(grid_points_l + 1):
            lh = lh_min + (l_max - lh_min) * (j / max(1, grid_points_l))
            try:
                candidate = estimate_hgv(
                    length_m=length_m,
                    diameter_m=diameter_m,
                    warhead_mass_kg=warhead_mass_kg,
                    hgv_type=hgv_type,
                    v_launch_mach=v_launch_mach,
                    h_launch_km=h_launch_km,
                    isp_s=isp_s,
                    propellant_density=propellant_density,
                    l_head_m=lh,
                    d_head_m=dh,
                    optimize_geometry=False,
                )
            except ValueError:
                continue
            cand_range = float(candidate['range_km'])
            if cand_range > best_range:
                best_range = cand_range
                best_lh = lh
                best_dh = dh
                best_res = dict(candidate)

    gain_km = round(best_range - float(base['range_km']), 1)
    base_range = float(base['range_km'])
    gain_pct = round(gain_km / base_range * 100.0, 2) if base_range > 0 else 0.0

    best_res['d_head_m'] = round(best_dh, 3)
    best_res['fineness'] = round(best_lh / best_dh, 2)
    best_res['optimal_geometry'] = True
    best_res['range_gain_km'] = gain_km
    best_res['range_gain_pct'] = gain_pct
    best_res['baseline_range_km'] = base_range
    best_res['baseline_l_head_m'] = float(base['l_head_m'])
    best_res['baseline_d_head_m'] = round(diameter_m, 3)
    best_res['baseline_ld_ratio'] = float(base['ld_ratio'])

    return {
        'best_l_head_m': round(best_lh, 2),
        'best_d_head_m': round(best_dh, 3),
        'best_l_booster_m': round(length_m - best_lh, 2),
        'best_fineness': round(best_lh / best_dh, 2),
        'best_ld_ratio': float(best_res['ld_ratio']),
        'max_range_km': round(best_range, 1),
        'baseline_range_km': base_range,
        'baseline_l_head_m': float(base['l_head_m']),
        'baseline_d_head_m': round(diameter_m, 3),
        'baseline_ld_ratio': float(base['ld_ratio']),
        'range_gain_km': gain_km,
        'range_gain_pct': gain_pct,
        'result': best_res,
        'baseline_result': base,
    }
