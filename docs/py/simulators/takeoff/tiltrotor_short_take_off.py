"""倾转旋翼短距起飞仿真（平直甲板，策略 A/B 短舱倾转）。

机型以 MV-22 为参考：涡桨额定轴功率 + 桨盘直径 → 推力（含短舱遮挡与侧向入流），
机翼计入悬停下洗与滑流增升。无升力风扇与滚转喷管。暂不计尾流波及，故不提供策略 C。

策略说明
--------
策略 A — 延迟倾转短舱
    滑跑初期短舱保持水平（0°，推力向前）；当地速达转换阈值后，
    以 NACELLE_RATE_DEG_S 倾转至目标角 nacelle_deg（类比 STOVL 主喷口）。
    搜索变量：目标短舱角、转换地速。

策略 B — 全程固定短舱角
    自滑跑起点起短舱固定在某一倾转角。
    搜索变量：固定短舱角。

短舱倾转速率取自公开资料：V-22 短舱可在约 12 s 内前倾 90° → 7.5 °/s。
"""
from __future__ import annotations

import numpy as np

from utils.takeoff.propeller_thrust import (
    calc_effective_disk_area_m2,
    calc_prop_disk_area_m2,
    calc_propeller_thrust_n,
    calc_rotor_induced_velocity_mps,
)
from utils.takeoff.search_utils import fine_range_symmetric
from utils.takeoff.sim_config import apply_wind_knots_globals
from utils.takeoff.takeoff_config import mode_config, shared_config
from utils.takeoff.tiltrotor_aero import (
    aero_params_from_mode,
    calc_slipstream_dynamic_pressure,
    calc_slipstream_wing_speed_mps,
    calc_tiltrotor_vertical_force_n,
)
from utils.takeoff.takeoff_physics import (
    G,
    KT_TO_MPS,
    MPS_TO_KT,
    M_TO_FT,
    T_THRUST_REF_C,
    calc_cl_alpha_with_canard,
    calc_cl_from_alpha_deg,
    calc_ground_effect_phi,
    calc_oswald_e,
    calc_sea_level_density_kg_m3,
    calc_thrust_temp_factor,
    dynamic_pressure as _dynamic_pressure,
    taxi_alpha_deg,
)

_SHARED = shared_config()
_MODE = mode_config('tiltrotor_short_takeoff')
_REF = _MODE['reference_aircraft']
_SEARCH = _MODE['search']

AMBIENT_TEMP_C = float(_MODE['ambient_temp_c'])
RHO = calc_sea_level_density_kg_m3(AMBIENT_TEMP_C)
THRUST_TEMP_FACTOR = calc_thrust_temp_factor(AMBIENT_TEMP_C)

MASS_KG = float(_REF['mass_kg'])
WEIGHT_N = MASS_KG * G
S_REF_M2 = float(_REF['s_ref_m2'])
WINGSPAN_M = float(_REF['wingspan_m'])
WING_HEIGHT_M = float(_REF['wing_height_m'])
ASPECT_RATIO = WINGSPAN_M ** 2 / S_REF_M2
SWEEP_LE_DEG = float(_REF['sweep_le_deg'])
CD0 = float(_REF['cd0'])
LAYOUT = 'conventional'
CANARD_HTAIL_AREA_M2 = 0.0
MU = float(_MODE['mu'])
ROTATION_AOA_DEG = float(_MODE['rotation_aoa_deg'])

SHAFT_POWER_SL_W = float(_REF['shaft_power_sl_w'])
PROP_DIAMETER_M = float(_REF['prop_diameter_m'])
N_ROTORS = int(_REF['n_rotors'])
NACELLE_BLOCKAGE_FRAC = float(_MODE['nacelle_blockage_frac'])
FIGURE_OF_MERIT = float(_MODE['figure_of_merit'])
_AERO = aero_params_from_mode(_MODE)
HOVER_DOWNLOAD_FRAC = _AERO['hover_download_frac']
SLIPSTREAM_WAKE_FACTOR = _AERO['slipstream_wake_factor']
SLIPSTREAM_WET_FRAC = _AERO['slipstream_wet_frac']
DOWNLOAD_ZERO_DEG = _AERO['download_zero_nacelle_deg']
DOWNLOAD_FULL_DEG = _AERO['download_full_nacelle_deg']
PROP_DISK_AREA_M2 = calc_prop_disk_area_m2(PROP_DIAMETER_M, N_ROTORS)
PROP_DISK_AREA_EFF_M2 = calc_effective_disk_area_m2(PROP_DISK_AREA_M2, NACELLE_BLOCKAGE_FRAC)

NACELLE_RATE_DEG_S = float(_SHARED['nacelle_rate_deg_s'])

SHAFT_POWER_W = SHAFT_POWER_SL_W * THRUST_TEMP_FACTOR

WIND_KT = float(_MODE['wind_kt'])
V_WIND_MPS = WIND_KT * KT_TO_MPS

NACELLE_FINAL_DEG_START = _SEARCH['nacelle_final_deg']['start']
NACELLE_FINAL_DEG_END = _SEARCH['nacelle_final_deg']['end']
NACELLE_FINAL_DEG_STEP = _SEARCH['nacelle_final_deg']['step']
V_TRANS_START_MPS = _SEARCH['v_trans_mps']['start']
V_TRANS_END_MPS = _SEARCH['v_trans_mps']['end']
V_TRANS_STEP_MPS = _SEARCH['v_trans_mps']['step']
NACELLE_B_DEG_START = _SEARCH['nacelle_b_deg']['start']
NACELLE_B_DEG_END = _SEARCH['nacelle_b_deg']['end']
NACELLE_B_DEG_STEP = _SEARCH['nacelle_b_deg']['step']
FINE_SEARCH_STEP = int(_SHARED['fine_search_step'])

DT_DEFAULT = float(_MODE['dt_default'])
MAX_SIM_TIME_S = float(_MODE['max_sim_time_s'])
MAX_RUNWAY_M = float(_MODE['max_runway_m'])

TAXI_ALPHA_DEG = taxi_alpha_deg()


def recompute_aero_parameters():
    """根据当前质量 / 几何刷新气动派生量。"""
    global ASPECT_RATIO, WEIGHT_N, OSWALD_E, K_IND, CL_ALPHA, PHI_GROUND, CL_TAXI, CL_ROTATION
    ASPECT_RATIO = WINGSPAN_M ** 2 / S_REF_M2
    WEIGHT_N = MASS_KG * G
    OSWALD_E = calc_oswald_e(ASPECT_RATIO, SWEEP_LE_DEG)
    K_IND = 1 / (np.pi * ASPECT_RATIO * OSWALD_E)
    CL_ALPHA = calc_cl_alpha_with_canard(
        ASPECT_RATIO, OSWALD_E, SWEEP_LE_DEG,
        layout=LAYOUT, canard_area_m2=CANARD_HTAIL_AREA_M2, wing_area_m2=S_REF_M2,
    )
    PHI_GROUND = calc_ground_effect_phi(WING_HEIGHT_M, WINGSPAN_M)
    CL_TAXI = calc_cl_from_alpha_deg(TAXI_ALPHA_DEG, CL_ALPHA)
    CL_ROTATION = calc_cl_from_alpha_deg(TAXI_ALPHA_DEG + ROTATION_AOA_DEG, CL_ALPHA)


def apply_thrust_temperature(ambient_temp_c):
    """按环境温度更新密度与可用轴功率。"""
    global AMBIENT_TEMP_C, RHO, THRUST_TEMP_FACTOR, SHAFT_POWER_W
    AMBIENT_TEMP_C = ambient_temp_c
    RHO = calc_sea_level_density_kg_m3(ambient_temp_c)
    THRUST_TEMP_FACTOR = calc_thrust_temp_factor(ambient_temp_c)
    SHAFT_POWER_W = SHAFT_POWER_SL_W * THRUST_TEMP_FACTOR


def apply_wind_knots(wind_kt):
    apply_wind_knots_globals(wind_kt, globals())


def apply_propulsion_sl(
    shaft_power_sl_w: float,
    prop_diameter_m: float,
    nacelle_blockage_frac: float | None = None,
    figure_of_merit: float | None = None,
    n_rotors: int = 2,
):
    """设置海平面轴功率与桨盘几何，并刷新当前温度下功率。"""
    global SHAFT_POWER_SL_W, PROP_DIAMETER_M, N_ROTORS, PROP_DISK_AREA_M2
    global PROP_DISK_AREA_EFF_M2, NACELLE_BLOCKAGE_FRAC, FIGURE_OF_MERIT
    SHAFT_POWER_SL_W = float(shaft_power_sl_w)
    PROP_DIAMETER_M = float(prop_diameter_m)
    N_ROTORS = int(n_rotors)
    PROP_DISK_AREA_M2 = calc_prop_disk_area_m2(PROP_DIAMETER_M, N_ROTORS)
    if nacelle_blockage_frac is not None:
        NACELLE_BLOCKAGE_FRAC = float(nacelle_blockage_frac)
    if figure_of_merit is not None:
        FIGURE_OF_MERIT = float(figure_of_merit)
    PROP_DISK_AREA_EFF_M2 = calc_effective_disk_area_m2(
        PROP_DISK_AREA_M2, NACELLE_BLOCKAGE_FRAC)
    apply_thrust_temperature(AMBIENT_TEMP_C)


def apply_aircraft_geometry(mass_kg, s_ref_m2, wingspan_m, wing_height_m, sweep_le_deg, cd0=None,
                            layout='conventional', canard_htail_area_m2=None):
    global MASS_KG, S_REF_M2, WINGSPAN_M, WING_HEIGHT_M, SWEEP_LE_DEG, CD0
    global LAYOUT, CANARD_HTAIL_AREA_M2
    MASS_KG = mass_kg
    S_REF_M2 = s_ref_m2
    WINGSPAN_M = wingspan_m
    WING_HEIGHT_M = wing_height_m
    SWEEP_LE_DEG = sweep_le_deg
    if cd0 is not None:
        CD0 = cd0
    LAYOUT = layout or 'conventional'
    CANARD_HTAIL_AREA_M2 = float(canard_htail_area_m2 or 0.0)
    recompute_aero_parameters()


recompute_aero_parameters()


def print_config_summary():
    t0 = current_prop_thrust_n(0.0, 0.0)
    print(f"环境温度:     {AMBIENT_TEMP_C:.0f} °C (功率标定 {T_THRUST_REF_C:.0f} °C)")
    print(f"空气密度 ρ:   {RHO:.4f} kg/m³ | 功率温度系数 {THRUST_TEMP_FACTOR:.4f}")
    print(f"轴功率:       {SHAFT_POWER_W/1e6:.2f} MW（{T_THRUST_REF_C:.0f}°C 标定 {SHAFT_POWER_SL_W/1e6:.2f} MW）")
    print(f"桨盘:         {N_ROTORS}×⌀{PROP_DIAMETER_M:.2f} m，总面积 {PROP_DISK_AREA_M2:.1f} m²")
    print(f"短舱遮挡比:   {NACELLE_BLOCKAGE_FRAC:.0%} | 品质因数 {FIGURE_OF_MERIT:.2f}")
    print(f"悬停下洗比:   {HOVER_DOWNLOAD_FRAC:.1%} | 滑流尾迹系数 {SLIPSTREAM_WAKE_FACTOR:.1f}")
    print(f"静推力估计:   {t0/1000:.1f} kN（含遮挡与品质因数）")
    print(f"净悬停推力:   {(t0 * (1.0 - HOVER_DOWNLOAD_FRAC))/1000:.1f} kN（扣机翼下洗）")
    print(f"起飞重量:     {MASS_KG:,.0f} kg")
    print(f"展弦比 AR:    {ASPECT_RATIO:.3f}")
    print(f"甲板风:       {WIND_KT} kt ({V_WIND_MPS:.2f} m/s)")
    print(f"短舱倾转速率: {NACELLE_RATE_DEG_S:.2f} °/s")
    print(f"Cl_taxi:      {CL_TAXI:.4f} | Cl_rotation: {CL_ROTATION:.4f}")


def dynamic_pressure(airspeed_mps):
    return _dynamic_pressure(RHO, airspeed_mps)


def current_prop_thrust_n(v_air_mps: float, nacelle_deg: float) -> float:
    """当前空速与短舱角下的总旋翼推力，N。"""
    nacelle_rad = np.radians(nacelle_deg)
    v_air = max(float(v_air_mps), 0.0)
    # 水平来流分解为轴向 + 侧向；短舱垂直时侧向即前飞来流
    v_axial = max(v_air * float(np.cos(nacelle_rad)), 0.0)
    v_edge = abs(v_air * float(np.sin(nacelle_rad)))
    return calc_propeller_thrust_n(
        SHAFT_POWER_W,
        RHO,
        PROP_DISK_AREA_M2,
        v_axial_mps=v_axial,
        figure_of_merit=FIGURE_OF_MERIT,
        nacelle_blockage_frac=NACELLE_BLOCKAGE_FRAC,
        v_edgewise_mps=v_edge,
    )


def find_liftoff_index(normal_force):
    """正压力由正变负时的索引（离地瞬间）。"""
    idx = np.where(np.diff(np.sign(normal_force)) < 0)[0]
    return int(idx[0]) if len(idx) else None


def _thrust_components(v_air_mps: float, nacelle_deg: float) -> tuple[float, float]:
    """返回水平 / 垂直推力分量 (T_h, T_v)。"""
    t = current_prop_thrust_n(v_air_mps, nacelle_deg)
    rad = np.radians(nacelle_deg)
    return float(t * np.cos(rad)), float(t * np.sin(rad))


def _slipstream_q(v_air_mps: float, nacelle_deg: float, thrust_n: float) -> float:
    """滑流加权动压，仅用于机翼升力。

    诱导速度按动量理想推力（实际推力 / 品质因数）计算：品质因数折的是
    型阻功率，尾迹速度仍由动量理论给出。
    """
    rad = np.radians(nacelle_deg)
    v_ax = max(float(v_air_mps), 0.0) * float(np.cos(rad))
    v_ed = abs(float(v_air_mps) * float(np.sin(rad)))
    t_ideal = float(thrust_n) / max(FIGURE_OF_MERIT, 0.1)
    v_i = calc_rotor_induced_velocity_mps(
        t_ideal, RHO, PROP_DISK_AREA_EFF_M2, v_ax, v_ed)
    v_slip = calc_slipstream_wing_speed_mps(
        v_air_mps, v_i, nacelle_deg, SLIPSTREAM_WAKE_FACTOR)
    return calc_slipstream_dynamic_pressure(
        RHO, v_air_mps, v_slip, SLIPSTREAM_WET_FRAC)


def net_vertical_force_n(
    v_air_mps: float,
    nacelle_deg: float,
    cl: float,
    thrust_n: float | None = None,
) -> float:
    """净垂直力：旋翼垂直分量 + 滑流机翼升力 − 下洗，N。"""
    t = current_prop_thrust_n(v_air_mps, nacelle_deg) if thrust_n is None else float(thrust_n)
    return calc_tiltrotor_vertical_force_n(
        t, RHO, PROP_DISK_AREA_EFF_M2, v_air_mps, nacelle_deg, cl, S_REF_M2,
        hover_download_frac=HOVER_DOWNLOAD_FRAC,
        wake_factor=SLIPSTREAM_WAKE_FACTOR,
        wet_frac=SLIPSTREAM_WET_FRAC,
        zero_deg=DOWNLOAD_ZERO_DEG,
        full_deg=DOWNLOAD_FULL_DEG,
        figure_of_merit=FIGURE_OF_MERIT,
    )


def _aero_step(v_air_mps: float, nacelle_deg: float):
    """单步气动力：水平推力、垂直推力、滑行升力、抬头升力、阻力。"""
    thrust = current_prop_thrust_n(v_air_mps, nacelle_deg)
    rad = np.radians(nacelle_deg)
    t_h = float(thrust * np.cos(rad))
    t_v = float(thrust * np.sin(rad))
    lift_taxi = net_vertical_force_n(v_air_mps, nacelle_deg, CL_TAXI, thrust)
    lift_rot = net_vertical_force_n(v_air_mps, nacelle_deg, CL_ROTATION, thrust)
    # 阻力按自由来流：机身不在滑流核心，避免用滑流 q 放大整机阻力
    q_fs = dynamic_pressure(v_air_mps)
    drag = q_fs * S_REF_M2 * (CD0 + K_IND * CL_TAXI ** 2 * PHI_GROUND)
    return t_h, t_v, lift_taxi, lift_rot, drag


def simulate_strategy_a(v_trans_mps, nacelle_final_deg, dt=DT_DEFAULT):
    """策略 A：先水平加速，达阈值后再倾转短舱。"""
    trans_duration_s = nacelle_final_deg / NACELLE_RATE_DEG_S
    v_gs, x, t = 0.0, 0.0, 0.0
    airborne = False
    transitioned = in_trans = False
    trans_start_t = 0.0
    history = {k: [] for k in ('t', 'x', 'v_gs', 'v_air', 'normal', 'a', 't_h', 't_v')}

    while t < MAX_SIM_TIME_S and x < MAX_RUNWAY_M:
        v_air = v_gs + V_WIND_MPS

        if not airborne and not transitioned and v_gs >= v_trans_mps and not in_trans:
            in_trans, trans_start_t = True, t

        if in_trans:
            elapsed = t - trans_start_t
            ratio = min(elapsed / trans_duration_s, 1.0) if trans_duration_s > 0 else 1.0
            if ratio >= 1.0:
                in_trans, transitioned = False, True
            nacelle_deg = nacelle_final_deg * ratio
        elif transitioned:
            nacelle_deg = nacelle_final_deg
        else:
            nacelle_deg = 0.0

        t_h, t_v, lift, lift_potential, drag = _aero_step(v_air, nacelle_deg)
        normal = WEIGHT_N - lift
        if WEIGHT_N - lift_potential < 0:
            normal = 0.0
            airborne = True

        friction = MU * normal if not airborne else 0.0
        accel = (t_h - drag - friction) / MASS_KG

        history['t'].append(t)
        history['x'].append(x)
        history['v_gs'].append(v_gs)
        history['v_air'].append(v_air)
        history['normal'].append(normal)
        history['a'].append(accel)
        history['t_h'].append(t_h)
        history['t_v'].append(t_v)

        if airborne:
            break
        v_gs = max(v_gs + accel * dt, 0.0)
        x += v_gs * dt
        t += dt

    for key in history:
        history[key] = np.array(history[key])
    return history, airborne


def simulate_strategy_b(nacelle_fixed_deg, dt=DT_DEFAULT):
    """策略 B：全程固定短舱倾转角。"""
    v_gs, x, t = 0.0, 0.0, 0.0
    airborne = False
    history = {k: [] for k in ('t', 'x', 'v_gs', 'v_air', 'normal', 'a', 't_h', 't_v')}

    while t < MAX_SIM_TIME_S and x < MAX_RUNWAY_M:
        v_air = v_gs + V_WIND_MPS
        t_h, t_v, lift, lift_potential, drag = _aero_step(v_air, nacelle_fixed_deg)
        normal = WEIGHT_N - lift
        if WEIGHT_N - lift_potential < 0:
            normal = 0.0
            airborne = True

        friction = MU * normal if not airborne else 0.0
        accel = (t_h - drag - friction) / MASS_KG

        history['t'].append(t)
        history['x'].append(x)
        history['v_gs'].append(v_gs)
        history['v_air'].append(v_air)
        history['normal'].append(normal)
        history['a'].append(accel)
        history['t_h'].append(t_h)
        history['t_v'].append(t_v)

        if airborne:
            break
        v_gs = max(v_gs + accel * dt, 0.0)
        x += v_gs * dt
        t += dt

    for key in history:
        history[key] = np.array(history[key])
    return history, airborne


def evaluate_liftoff(history):
    """从仿真历史提取离地指标，无法离地则返回 None。起步即离地（垂起）记为 0 m。"""
    if history['normal'].size == 0:
        return None
    if float(history['normal'][0]) <= 0.0:
        return dict(
            x_m=0.0,
            v_gs_mps=float(history['v_gs'][0]),
            v_air_mps=float(history['v_air'][0]),
            t_s=float(history['t'][0]),
            idx=0,
            history=history,
        )
    idx = find_liftoff_index(history['normal'])
    if idx is None:
        return None
    return dict(
        x_m=history['x'][idx],
        v_gs_mps=history['v_gs'][idx],
        v_air_mps=history['v_air'][idx],
        t_s=history['t'][idx],
        idx=idx,
        history=history,
    )


def search_strategy_a():
    """策略 A 粗搜索。"""
    best = None
    for nacelle_deg in range(NACELLE_FINAL_DEG_START, NACELLE_FINAL_DEG_END + 1, NACELLE_FINAL_DEG_STEP):
        for v_trans in range(V_TRANS_START_MPS, V_TRANS_END_MPS + 1, V_TRANS_STEP_MPS):
            hist, _ = simulate_strategy_a(float(v_trans), float(nacelle_deg))
            lo = evaluate_liftoff(hist)
            if lo and (best is None or lo['x_m'] < best['x_m']):
                best = dict(nozzle_deg=nacelle_deg, v_trans_mps=v_trans, **{
                    k: lo[k] for k in ('x_m', 'v_gs_mps', 'v_air_mps', 't_s', 'idx')
                })
    return best


def fine_tune_strategy_a(coarse):
    """策略 A 细化搜索。"""
    best = dict(coarse)
    for nacelle_deg in fine_range_symmetric(
            coarse['nozzle_deg'], NACELLE_FINAL_DEG_STEP, FINE_SEARCH_STEP,
            NACELLE_FINAL_DEG_START, NACELLE_FINAL_DEG_END):
        for v_trans in fine_range_symmetric(
                coarse['v_trans_mps'], V_TRANS_STEP_MPS, FINE_SEARCH_STEP,
                V_TRANS_START_MPS, V_TRANS_END_MPS):
            hist, _ = simulate_strategy_a(float(v_trans), float(nacelle_deg))
            lo = evaluate_liftoff(hist)
            if lo and lo['x_m'] < best['x_m']:
                best = dict(nozzle_deg=nacelle_deg, v_trans_mps=v_trans, **{
                    k: lo[k] for k in ('x_m', 'v_gs_mps', 'v_air_mps', 't_s', 'idx')
                })
    return best


def search_strategy_b():
    """策略 B 搜索。"""
    best = None
    for nacelle_deg in range(NACELLE_B_DEG_START, NACELLE_B_DEG_END + 1, NACELLE_B_DEG_STEP):
        hist, _ = simulate_strategy_b(float(nacelle_deg))
        lo = evaluate_liftoff(hist)
        if lo and (best is None or lo['x_m'] < best['x_m']):
            best = dict(nozzle_deg=nacelle_deg, **{
                k: lo[k] for k in ('x_m', 'v_gs_mps', 'v_air_mps', 't_s', 'idx')
            })
    return best


def run_strategy_a_search():
    """策略 A 粗搜索 + 细化，返回最优结果 dict 或 None。"""
    best = search_strategy_a()
    if best:
        best = fine_tune_strategy_a(best)
    return best


def run_strategy_b_search():
    """策略 B 搜索，返回最优结果 dict 或 None。"""
    return search_strategy_b()


def run_strategy_c_search():
    """倾转旋翼暂不提供策略 C。"""
    raise ValueError('倾转短距起飞暂不支持策略 C（未计入尾流波及）')
