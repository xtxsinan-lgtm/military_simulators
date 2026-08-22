"""倾转旋翼机翼–旋翼干涉：悬停下洗与滑流增升。"""
from __future__ import annotations

import math

from utils.takeoff.propeller_thrust import calc_rotor_induced_velocity_mps

# 默认：使海平面 15°C 净悬停推力对齐 MV-22 官方垂起重量 52,600 lb
DEFAULT_HOVER_DOWNLOAD_FRAC = 0.117
# 远尾迹动量理论：尾流速度增量 = 2 v_i；机翼靠近桨盘，取远尾迹系数
DEFAULT_SLIPSTREAM_WAKE_FACTOR = 2.0
# V-22 机翼几乎全在双旋翼滑流内
DEFAULT_SLIPSTREAM_WET_FRAC = 0.9
# 官方短距构型短舱 60° 时下洗视为 0，90° 悬停达最大
DEFAULT_DOWNLOAD_ZERO_DEG = 60.0
DEFAULT_DOWNLOAD_FULL_DEG = 90.0


def calc_hover_download_schedule(
    nacelle_deg: float,
    zero_deg: float = DEFAULT_DOWNLOAD_ZERO_DEG,
    full_deg: float = DEFAULT_DOWNLOAD_FULL_DEG,
) -> float:
    """
    下洗日程：短舱 ≤ zero_deg 为 0，≥ full_deg 为 1，中间 smoothstep。

    官方 STO 短舱 60° 时机翼已转为正升力，不再按悬停阻挡折减。
    """
    ang = float(nacelle_deg)
    lo = float(zero_deg)
    hi = float(full_deg)
    if hi <= lo:
        return 1.0 if ang >= hi else 0.0
    if ang <= lo:
        return 0.0
    if ang >= hi:
        return 1.0
    x = (ang - lo) / (hi - lo)
    return x * x * (3.0 - 2.0 * x)


def calc_tiltrotor_download_n(
    thrust_n: float,
    nacelle_deg: float,
    hover_download_frac: float = DEFAULT_HOVER_DOWNLOAD_FRAC,
    zero_deg: float = DEFAULT_DOWNLOAD_ZERO_DEG,
    full_deg: float = DEFAULT_DOWNLOAD_FULL_DEG,
) -> float:
    """机翼阻挡旋翼尾流的下洗力，N。悬停最大，短距构型（≤60°）为 0。"""
    if thrust_n <= 0:
        return 0.0
    frac = min(max(float(hover_download_frac), 0.0), 0.4)
    return float(thrust_n) * frac * calc_hover_download_schedule(nacelle_deg, zero_deg, full_deg)


def calc_slipstream_wing_speed_mps(
    v_air_mps: float,
    induced_vel_mps: float,
    nacelle_deg: float,
    wake_factor: float = DEFAULT_SLIPSTREAM_WAKE_FACTOR,
) -> float:
    """
    机翼当地水平速度：来流 + 滑流轴向分量。

    短舱垂直时 cosθ=0，退化为来流；短舱前倾时旋翼把气流吹过机翼。
    """
    axial = max(float(induced_vel_mps), 0.0) * math.cos(math.radians(nacelle_deg))
    wf = min(max(float(wake_factor), 0.0), 3.0)
    return max(float(v_air_mps), 0.0) + wf * max(axial, 0.0)


def calc_slipstream_dynamic_pressure(
    rho: float,
    v_air_mps: float,
    v_slip_mps: float,
    wet_frac: float = DEFAULT_SLIPSTREAM_WET_FRAC,
) -> float:
    """浸湿区用滑流速度、其余用自由来流的加权动压，Pa。"""
    wet = min(max(float(wet_frac), 0.0), 1.0)
    v_fs = max(float(v_air_mps), 0.0)
    v_sl = max(float(v_slip_mps), 0.0)
    return 0.5 * float(rho) * (wet * v_sl * v_sl + (1.0 - wet) * v_fs * v_fs)


def calc_tiltrotor_wing_lift_n(
    rho: float,
    disk_area_m2: float,
    thrust_n: float,
    v_air_mps: float,
    nacelle_deg: float,
    cl: float,
    s_ref_m2: float,
    v_edgewise_mps: float = 0.0,
    wake_factor: float = DEFAULT_SLIPSTREAM_WAKE_FACTOR,
    wet_frac: float = DEFAULT_SLIPSTREAM_WET_FRAC,
) -> float:
    """滑流增升后的机翼升力（不含旋翼垂直分量与下洗），N。"""
    if s_ref_m2 <= 0 or rho <= 0:
        return 0.0
    v_ax = max(float(v_air_mps), 0.0) * math.cos(math.radians(nacelle_deg))
    v_i = calc_rotor_induced_velocity_mps(
        thrust_n, rho, disk_area_m2, v_ax, v_edgewise_mps,
    )
    v_slip = calc_slipstream_wing_speed_mps(v_air_mps, v_i, nacelle_deg, wake_factor)
    q = calc_slipstream_dynamic_pressure(rho, v_air_mps, v_slip, wet_frac)
    return q * float(s_ref_m2) * float(cl)


def calc_tiltrotor_vertical_force_n(
    thrust_n: float,
    rho: float,
    disk_area_m2: float,
    v_air_mps: float,
    nacelle_deg: float,
    cl: float,
    s_ref_m2: float,
    hover_download_frac: float = DEFAULT_HOVER_DOWNLOAD_FRAC,
    wake_factor: float = DEFAULT_SLIPSTREAM_WAKE_FACTOR,
    wet_frac: float = DEFAULT_SLIPSTREAM_WET_FRAC,
    zero_deg: float = DEFAULT_DOWNLOAD_ZERO_DEG,
    full_deg: float = DEFAULT_DOWNLOAD_FULL_DEG,
    figure_of_merit: float = 0.78,
) -> float:
    """净垂直力：旋翼垂直分量 + 滑流机翼升力 − 下洗，N。

    滑流诱导速度按动量理想推力（实际推力 / 品质因数）计算。
    """
    rad = math.radians(nacelle_deg)
    t_v = float(thrust_n) * math.sin(rad)
    v_ed = abs(float(v_air_mps) * math.sin(rad))
    fm = min(max(float(figure_of_merit), 0.1), 1.0)
    t_wake = float(thrust_n) / fm
    wing = calc_tiltrotor_wing_lift_n(
        rho, disk_area_m2, t_wake, v_air_mps, nacelle_deg, cl, s_ref_m2,
        v_edgewise_mps=v_ed, wake_factor=wake_factor, wet_frac=wet_frac,
    )
    download = calc_tiltrotor_download_n(
        thrust_n, nacelle_deg, hover_download_frac, zero_deg, full_deg,
    )
    return t_v + wing - download
