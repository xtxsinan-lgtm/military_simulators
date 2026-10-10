"""饱和打击用简化雷达方程与末段运动学估算（探测距离 / 火控锁定 / 单发 Pk）。

单发 Pk 由比例导引末段脱靶（双方速度与过载）再乘传感器系数得到。
过载多为公开量级或估计，不对应型号实测鉴定值。
"""
from __future__ import annotations

import math
from typing import Any

from utils.missile_interception.missile_interception_config import physics_config
from utils.radar_horizon import radar_horizon_km

_PHYS = physics_config()

# 雷达体制灵敏度倍率（相对机械扫描）
TECH_MULT: dict[str, float] = dict(_PHYS['tech_mult'])

# 假设高度（米）
H_AWACS = float(_PHYS['h_awacs_m'])
H_SHIP_RADAR = float(_PHYS['h_ship_radar_m'])
H_TARGET: dict[str, float] = dict(_PHYS['h_target_m'])
DIVE_ANGLE: dict[str, float] = dict(_PHYS.get('dive_angle_deg', {}))
MANEUVER_PK: dict[str, float] = dict(_PHYS.get('maneuver_pk_factor', {'cruise': 1.0}))
DEFAULT_SAM_MAX_ALT_KM = float(_PHYS.get('default_sam_max_alt_km', 33.0))
PK_TRAJ_FACTOR: dict[str, float] = dict(_PHYS.get('pk_traj_factor', {'sea': 0.85, 'high': 1.0}))

# 火控锁定距离占搜索探测距离的比例
LOCK_FRACTION = float(_PHYS['lock_fraction'])

# 冲压 / 超燃冲压等型号 id（CSV 未填 maneuver_class 时回退）
_SCRAMJET_ASM_IDS = frozenset({
    'yj12', 'yj19', 'zircon', 'brahmos', 'p500', 'p700', 'hf3', 'kh31', 'p270',
})


def clamp(x: float, lo: float, hi: float) -> float:
    """将数值限制在 [lo, hi]。"""
    return max(lo, min(hi, x))


def power_range_km(
    ref_range_km: float,
    area: float,
    ref_area: float,
    radar_type: str,
    rcs: float,
    ref_rcs: float,
) -> float:
    """功率受限探测距离（公里），按雷达方程比例关系缩放。"""
    mult = TECH_MULT.get(radar_type, 1.0)
    return ref_range_km * math.sqrt(area / ref_area) * (rcs / ref_rcs) ** 0.25 * mult


def target_altitude_m(traj: str) -> float:
    """按弹道类型返回巡航/典型飞行高度估计（米）；未知弹道类型按高空弹道回退。"""
    return H_TARGET.get(traj, H_TARGET['high'])


def dive_angle_deg(traj: str) -> float:
    """俯冲角（与水平面夹角，度）；用于计算进入拦截射高包线时的水平距离。"""
    return float(DIVE_ANGLE.get(traj, DIVE_ANGLE.get('high', 30.0)))


def default_maneuver_class(traj: str, asm_id: str = '') -> str:
    """由弹道 / 型号推断机动性类别（CSV 未填 maneuver_class 时使用）。"""
    if traj == 'glide':
        return 'glide'
    if traj == 'ballistic':
        return 'dual_cone'
    aid = (asm_id or '').strip().lower()
    if aid in _SCRAMJET_ASM_IDS:
        return 'scramjet'
    return 'cruise'


def maneuver_pk_factor(maneuver_class: str) -> float:
    """旧版机动性类别乘数。Pk 已改用过载；此函数仅保留类别表供对照。"""
    return float(MANEUVER_PK.get(maneuver_class, MANEUVER_PK.get('cruise', 1.0)))


def _kin() -> dict[str, float]:
    """读取末段运动学常数；缺省键用内置默认，避免旧配置注入后缺字段。"""
    raw = dict(physics_config().get('pk_kinematics') or {})
    defaults = {
        'g0': 9.80665,
        'nav_ratio': 4.0,
        'tau_aero_s': 0.32,
        'tau_tvc_s': 0.15,
        'tvc_g': 45.0,
        'tau_track_s': 0.4,
        'semi_active_extra_s': 0.08,
        'homing_range_m': 8000.0,
        'homing_mach_knee': 2.5,
        'homing_mach_slope': 0.08,
        'homing_floor': 0.35,
        'lag_coeff': 1.0,
        'settle_taus': 3.0,
        'heading_error_deg': 0.5,
        'heading_mach_k': 0.15,
        'heading_mach_ref': 1.5,
        'heading_exp': 1.4,
        'lethal_radius_m': 20.0,
        'lethal_ref_dia_m': 0.34,
        'lethal_exp': 0.6,
        'lethal_floor_m': 8.0,
        'lethal_cap_m': 22.0,
        'sensor_ref': 1.25,
        'sensor_lo': 0.4,
        'sensor_hi': 1.15,
        'pk_lo': 0.03,
        'pk_hi': 0.95,
    }
    defaults.update({k: float(v) for k, v in raw.items()})
    return defaults


def default_target_g(maneuver_class: str, vm_ma: float) -> float:
    """未给出过载时，按机动类别与速度估计来袭弹末端可用过载（g）。

    亚音速巡航按数 g 的拉起/蛇形；超音速巡航更高。
    冲压在中低马赫按末端机动（约 12g），马赫 5 以上按热/结构限制降到约 5g。
    滑翔体约 8g，双锥末制导约 15g。
    """
    vm = float(vm_ma)
    kind = (maneuver_class or 'cruise').strip() or 'cruise'
    if kind == 'glide':
        return 8.0
    if kind == 'dual_cone':
        return 15.0
    if kind == 'scramjet':
        return 5.0 if vm >= 5.0 else 12.0
    return 8.0 if vm >= 2.0 else 5.0


def default_interceptor_g(interceptor_dia_m: float) -> float:
    """未给出过载时，按弹径粗分拦截弹可用过载（g）。小弹按点防御高机动，大弹按中程弹体。"""
    dia = float(interceptor_dia_m)
    if dia <= 0.20:
        return 50.0
    if dia <= 0.28:
        return 40.0
    return 25.0


def homing_range_factor(vm_ma: float) -> float:
    """高速目标缩短可用末制导距离（跟踪噪声、气动加热、等离子体）。低速保持 1。"""
    k = _kin()
    vm = float(vm_ma)
    if vm <= k['homing_mach_knee']:
        return 1.0
    return clamp(
        1.0 - k['homing_mach_slope'] * (vm - k['homing_mach_knee']),
        k['homing_floor'],
        1.0,
    )


def guidance_time_constant_s(interceptor_g: float, seeker_type: str) -> float:
    """自动驾驶仪时间常数（秒）。高过载按直接力/推力矢量更快；半主动照射回路更慢。"""
    k = _kin()
    tau = k['tau_tvc_s'] if float(interceptor_g) >= k['tvc_g'] else k['tau_aero_s']
    if seeker_type == 'semi_active':
        tau += k['semi_active_extra_s']
    return tau


def angle_track_time_constant_s(autopilot_tau_s: float) -> float:
    """航向误差通道的时间常数：跟踪滤波与舵回路各占一半，高速目标不会因舵快而误差消失。"""
    k = _kin()
    track = k['tau_track_s']
    auto = float(autopilot_tau_s)
    slower = max(track, auto)
    return 0.5 * slower + 0.5 * auto


def lethal_radius_m(interceptor_dia_m: float) -> float:
    """按弹径估计破片杀伤半径（米）。参考 0.34 m 弹径约 20 m。"""
    k = _kin()
    dia = max(0.05, float(interceptor_dia_m))
    radius = k['lethal_radius_m'] * (dia / k['lethal_ref_dia_m']) ** k['lethal_exp']
    return clamp(radius, k['lethal_floor_m'], k['lethal_cap_m'])


def endgame_miss_m(
    vm_ma: float,
    vi_ma: float,
    target_g: float,
    interceptor_g: float,
    seeker_type: str,
) -> dict[str, float]:
    """迎头比例导引末段脱靶（米）。

    需用过载约为导航比 N'/(N'-2) 倍目标过载（N'=4 时为 2 倍）。
    拦截弹达不到时，亏欠加速度在末段饱和时间内积累成脱靶。
    舵回路滞后带来与目标加速度成正比的残余脱靶；
    截获时的航向误差在剩余飞行时间短于跟踪时间常数时留不下来。
    """
    k = _kin()
    vm = max(0.1, float(vm_ma))
    vi = max(0.1, float(vi_ma))
    tg = max(0.5, float(target_g))
    ig = max(1.0, float(interceptor_g))
    g0 = k['g0']
    nav = k['nav_ratio']
    closing = (vm + vi) * float(physics_config()['mach_mps'])
    homing_m = k['homing_range_m'] * homing_range_factor(vm)
    t_go = max(homing_m / closing, 0.05)
    a_t = tg * g0
    a_i = ig * g0
    a_req = (nav / (nav - 2.0)) * a_t
    if a_i >= a_req:
        t_sat = 0.0
    else:
        t_sat = t_go * (1.0 - a_i / a_req)
    miss_sat = 0.5 * a_t * t_sat * t_sat
    tau = guidance_time_constant_s(ig, seeker_type)
    settle = max(1.0, (k['settle_taus'] * tau / t_go) ** 2)
    miss_lag = k['lag_coeff'] * a_t * tau * tau * settle
    heading = math.radians(k['heading_error_deg']) * (
        1.0 + k['heading_mach_k'] * max(0.0, vm - k['heading_mach_ref'])
    )
    tau_ang = angle_track_time_constant_s(tau)
    frac = min(1.0, (tau_ang / t_go) ** k['heading_exp'])
    miss_heading = homing_m * heading * frac
    miss = math.sqrt(miss_sat ** 2 + miss_lag ** 2 + miss_heading ** 2)
    return {
        'miss_m': miss,
        'miss_saturation_m': miss_sat,
        'miss_lag_m': miss_lag,
        'miss_heading_m': miss_heading,
        't_go_s': t_go,
        'homing_range_m': homing_m,
        'g_required': a_req / g0,
        'closing_mps': closing,
    }


def dive_entry_horizontal_km(
    h_cruise_m: float,
    sam_max_alt_km: float,
    dive_angle_deg_val: float,
) -> float | None:
    """目标以给定俯冲角自巡航高度下降，进入拦截弹最大射高包线时的水平距离（km）。

    几何关系：Δh = h_cruise - h_sam_max，水平距离 ≈ Δh / tan(俯冲角)。
    若巡航高度已在射高包线内则返回 None（不额外几何限制）。
    """
    sam_alt_m = max(0.0, float(sam_max_alt_km)) * 1000.0
    if h_cruise_m <= sam_alt_m + 1.0:
        return None
    delta_h_km = (h_cruise_m - sam_alt_m) / 1000.0
    angle_rad = math.radians(clamp(float(dive_angle_deg_val), 5.0, 85.0))
    return delta_h_km / math.tan(angle_rad)


def radar_gain_factor(area: float, radar_type: str, ref_area: float) -> float:
    """天线面积 + 体制的增益系数，归一到参考面积附近约 1.0。"""
    mult = TECH_MULT.get(radar_type, 1.0)
    g = math.sqrt(area / ref_area) * mult
    return clamp(0.55 + 0.45 * min(g, 1.6), 0.55, 1.25)


def estimate_engagement_distance(
    rcs: float,
    traj: str,
    awacs_area: float,
    awacs_type: str,
    standoff_km: float,
    ship_area: float,
    ship_type: str,
    sam_range_km: float,
    has_awacs: bool = True,
    sam_max_alt_km: float | None = None,
    dive_angle_deg_val: float | None = None,
) -> dict[str, Any]:
    """分别估算舰载/预警机雷达探测距离，并据此推算最终交战距离（公里）。

    雷达视距按拦截弹最大射高 ``sam_max_alt_km`` 处目标高度计算（进入包线后的交战高度）。

    仅当巡航高度 **高于** 拦截弹最大射高时，才用俯冲角几何限制有效交战距离
    （滑翔体 / 弹道等须先下降进入射高包线才可拦截）。
    常规高空 / 掠海导弹若巡航高度已在射高包线内，则不计算俯冲进入距离。

    ``engage_dist = min(max(awacs_detect_km, ship_detect_km), sam_range_km[, dive_entry_km])``
    """
    rcs = max(0.001, float(rcs))
    h_cruise = target_altitude_m(traj)
    sam_max = float(sam_max_alt_km if sam_max_alt_km is not None else DEFAULT_SAM_MAX_ALT_KM)
    sam_max = max(0.1, sam_max)
    sam_alt_m = sam_max * 1000.0
    h_engage = min(h_cruise, sam_alt_m)

    entry_km: float | None = None
    dive: float | None = None
    if h_cruise > sam_alt_m + 1.0:
        dive = float(dive_angle_deg_val if dive_angle_deg_val is not None else dive_angle_deg(traj))
        entry_km = dive_entry_horizontal_km(h_cruise, sam_max, dive)

    awacs_area = max(0.1, float(awacs_area))
    standoff_km = max(0.0, float(standoff_km))
    ship_area = max(0.1, float(ship_area))
    sam_range_km = max(0.1, float(sam_range_km))
    has_awacs = bool(has_awacs)

    ship_power = power_range_km(200.0, ship_area, 10.0, ship_type, rcs, 5.0)
    ship_horizon = radar_horizon_km(H_SHIP_RADAR, h_engage)
    ship_search = min(ship_power, ship_horizon)
    ship_detect_km = ship_search
    ship_lock = ship_search * LOCK_FRACTION

    if has_awacs:
        awacs_power = power_range_km(400.0, awacs_area, 8.0, awacs_type, rcs, 5.0)
        awacs_horizon = radar_horizon_km(H_AWACS, h_engage)
        awacs_detect = min(awacs_power, awacs_horizon)
        awacs_total = standoff_km + awacs_detect
        awacs_detect_km = awacs_total
    else:
        awacs_power = 0.0
        awacs_horizon = 0.0
        awacs_detect = 0.0
        awacs_total = 0.0
        awacs_detect_km = 0.0
        standoff_km = 0.0

    detect_max_km = max(awacs_detect_km, ship_detect_km)
    engage_before_dive = min(detect_max_km, sam_range_km)
    if entry_km is not None:
        engage_dist = min(engage_before_dive, entry_km)
    else:
        engage_dist = engage_before_dive

    return {
        'awacs_power': awacs_power,
        'awacs_horizon': awacs_horizon,
        'awacs_detect': awacs_detect,
        'awacs_total': awacs_total,
        'awacs_detect_km': awacs_detect_km,
        'ship_power': ship_power,
        'ship_horizon': ship_horizon,
        'ship_search': ship_search,
        'ship_detect_km': ship_detect_km,
        'ship_lock': ship_lock,
        'detect_max_km': detect_max_km,
        'engage_before_dive_km': engage_before_dive,
        'dive_entry_km': entry_km,
        'dive_angle_deg': dive,
        'sam_max_alt_km': sam_max,
        'sam_range': sam_range_km,
        'engage_dist': engage_dist,
        'standoff': standoff_km,
        'has_awacs': has_awacs,
        'h_target_m': h_cruise,
        'h_engage_m': h_engage,
    }


def estimate_pk(
    vm_ma: float,
    vi_ma: float,
    rcs: float,
    traj: str,
    ship_area: float,
    ship_type: str,
    interceptor_dia_m: float,
    seeker_type: str,
    maneuver_class: str | None = None,
    asm_id: str = '',
    target_g: float | None = None,
    interceptor_g: float | None = None,
) -> dict[str, Any]:
    """估算单发拦截成功概率 Pk。

    运动学项是脱靶相对杀伤半径的指数：Pk_kin = exp(-(miss/R)^2)。
    弹径已体现在杀伤半径和导引时间常数里，传感器项只乘舰载雷达、RCS 与弹道。
    未传入过载时按机动类别 / 弹径估计。
    """
    vm_ma = max(0.1, float(vm_ma))
    vi_ma = max(0.1, float(vi_ma))
    rcs = max(0.001, float(rcs))
    ship_area = max(0.1, float(ship_area))
    dia = max(0.05, float(interceptor_dia_m))
    mclass = (maneuver_class or '').strip() or default_maneuver_class(traj, asm_id)
    tg = float(target_g) if target_g not in (None, '') else default_target_g(mclass, vm_ma)
    ig = float(interceptor_g) if interceptor_g not in (None, '') else default_interceptor_g(dia)
    tg = max(0.5, tg)
    ig = max(1.0, ig)

    ship_radar_factor = radar_gain_factor(ship_area, ship_type, 10.0)
    if seeker_type == 'semi_active':
        seeker_factor = ship_radar_factor * 0.9
    else:
        seeker_area = math.pi * (dia / 2.0) ** 2
        seeker_tech = 'aesa' if seeker_type == 'active_aesa' else 'mechanical'
        seeker_factor = radar_gain_factor(seeker_area, seeker_tech, 0.03)

    rcs_factor = clamp(1.0 + 0.15 * math.log10(rcs / 0.5), 0.55, 1.15)
    traj_factor = float(PK_TRAJ_FACTOR.get(traj, PK_TRAJ_FACTOR.get('high', 1.0)))
    kin_cfg = _kin()
    # 导引头口径已进入杀伤半径与时间常数，不再重复乘进传感器项
    sensor_ratio = clamp(
        ship_radar_factor * rcs_factor * traj_factor / kin_cfg['sensor_ref'],
        kin_cfg['sensor_lo'],
        kin_cfg['sensor_hi'],
    )
    miss = endgame_miss_m(vm_ma, vi_ma, tg, ig, seeker_type)
    r_kill = lethal_radius_m(dia)
    pk_kin = math.exp(-((miss['miss_m'] / r_kill) ** 2))
    pk = clamp(pk_kin * sensor_ratio, kin_cfg['pk_lo'], kin_cfg['pk_hi'])
    return {
        'pk': pk,
        'pk_kinematic': pk_kin,
        'sensor_factor': sensor_ratio,
        'ship_radar_factor': ship_radar_factor,
        'seeker_factor': seeker_factor,
        'rcs_factor': rcs_factor,
        'traj_factor': traj_factor,
        'target_g': tg,
        'interceptor_g': ig,
        'g_required': miss['g_required'],
        'miss_m': miss['miss_m'],
        'miss_saturation_m': miss['miss_saturation_m'],
        'miss_lag_m': miss['miss_lag_m'],
        'miss_heading_m': miss['miss_heading_m'],
        'lethal_radius_m': r_kill,
        't_go_s': miss['t_go_s'],
        'homing_range_km': miss['homing_range_m'] / 1000.0,
        'maneuver_class': mclass,
    }


def binding_limit_label(result: dict[str, Any]) -> str:
    """返回交战距离受限于哪一项（中文标签）。"""
    engage = result['engage_dist']
    sam_range = result['sam_range']
    has_awacs = bool(result.get('has_awacs', True))
    awacs_detect_km = result.get('awacs_detect_km', result.get('awacs_total', 0.0))
    ship_detect_km = result.get('ship_detect_km', result.get('ship_search', 0.0))
    entry_km = result.get('dive_entry_km')
    before_dive = float(result.get('engage_before_dive_km', engage))

    if math.isclose(engage, sam_range, rel_tol=0, abs_tol=1e-9):
        return '拦截弹射程'
    if (
        entry_km is not None
        and entry_km > 0
        and math.isclose(engage, min(before_dive, entry_km), rel_tol=0, abs_tol=1e-9)
        and engage <= float(entry_km) + 1e-9
        and (before_dive > entry_km + 1e-9 or engage < before_dive - 1e-9)
    ):
        return '俯冲进入射高包线'
    awacs_is_farther = has_awacs and awacs_detect_km >= ship_detect_km
    if awacs_is_farther and math.isclose(engage, awacs_detect_km, rel_tol=0, abs_tol=1e-9):
        return '预警机雷达探测距离'
    if math.isclose(engage, ship_detect_km, rel_tol=0, abs_tol=1e-9):
        return '舰载雷达探测距离'
    return '拦截弹射程'
