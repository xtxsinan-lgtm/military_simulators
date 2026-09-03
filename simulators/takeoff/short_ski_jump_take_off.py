"""F-35B 短距滑跃起飞仿真（平直段 + 圆弧滑跃段，策略 A/B/C 喷口偏转对比）。

尾流波及：本模块为 VTOL/STOVL 专用；主喷管尾流模型见 utils.takeoff.exhaust_plume。
常规固定翼滑跃仿真（ski_jump_take_off）不计算尾流波及范围。

滑跃段建模为圆弧：入口切线与平直甲板相切（水平），出口切线角为资料给定滑跃角；
弧长与水平投影由圆弧半径导出（仅需滑跃角，可选唇口高度定半径）。见 ski_jump_geometry。

策略说明
--------
策略 A — 延迟偏转喷口
    平直段滑跑初期主喷口保持水平（0°）；当地速达到转换阈值 v_trans 后，
    以 NOZZLE_RATE_DEG_S 的速率偏转至目标角 nozzle_deg，随后经滑跃段离舰。
    搜索变量：平直段长度、目标喷口角、转换地速、俯仰角（及可选的离舰后喷口角）。

策略 B — 全程固定喷口
    自滑跑起点起主喷口即固定在某一角度，平直段与滑跃段均不变。
    搜索变量：平直段长度、固定喷口角、俯仰角（及可选的离舰后喷口角）。

策略 C — 尾流安全约束下的最优偏转
    给定 MIN_SAFE_DISTANCE_M（负值，如 −60），要求滑跑全程
    min(x − 安全距离) ≥ MIN_SAFE_DISTANCE_M，即尾流后缘不得侵入该 x 以左区域。
    利用 calc_exhaust_safe_distance_m 的反函数，在 x=0 处倒推起始喷口角；
    此后每个时间步根据当前 x 计算最小允许喷口角（滑跃段 θ 含滑跃角），
    并在「保持」与「减小 dt×NOZZLE_RATE_DEG_S」之间做动态规划，
    再经空中段判定，求最短起飞总距离（平直段 + 滑跃段水平投影）。
    搜索变量：MIN_SAFE_DISTANCE_M（用户设定）、平直段长度、俯仰角。

ALLOW_AIR_NOZZLE_VECTORING 为 True 时，策略 A/B 还可搜索离舰后主喷口继续偏转的角度。
"""
from __future__ import annotations

import numpy as np

from utils.takeoff.deck_config import assign_ski_jump_globals, total_takeoff_distance_m as _total_takeoff_distance_m
from utils.takeoff.exhaust_plume import (
    ExhaustPlumeParams,
    calc_exhaust_safe_distance_m as _calc_exhaust_safe_distance_m,
    calc_exhaust_theta_deg_for_safe_distance_m as _calc_exhaust_theta_deg_for_safe_distance_m,
    calc_min_nozzle_deg_for_plume as _calc_min_nozzle_deg_for_plume,
    default_exhaust_plume_params,
    update_min_plume_trailing_edge_m as _update_min_plume_trailing_edge_m,
)
from utils.takeoff.search_utils import fine_range_deck, fine_range_symmetric, grid_step
from utils.takeoff.sim_config import apply_wind_knots_globals
from utils.takeoff.ski_jump_geometry import SkiJumpArc, compute_ski_jump_arc, deck_angle_deg_at_s, deck_cos_sin_at_s, deck_height_at_s
from utils.takeoff.trajectory import TrajectoryRecorder
from utils.takeoff.takeoff_config import cfg_range, mode_config, shared_config
from utils.takeoff.takeoff_physics import (
    G,
    KT_TO_MPS,
    M_TO_FT,
    PITCH_MAX_DEG,
    T_THRUST_REF_C,
    calc_cl_alpha_with_canard,
    calc_cl_from_alpha_deg,
    calc_ground_effect_phi,
    calc_oswald_e,
    calc_sea_level_density_kg_m3,
    calc_thrust_temp_factor,
    check_pitch_deg,
    drag_coefficient as _drag_coefficient,
    dynamic_pressure as _dynamic_pressure,
    taxi_alpha_deg,
)

_SHARED = shared_config()
_MODE = mode_config('short_ski_jump')
_REF = _MODE['reference_aircraft']
_SEARCH = _MODE['search']

ALLOW_AIR_NOZZLE_VECTORING = bool(_SHARED['allow_air_nozzle_vectoring'])

AMBIENT_TEMP_C = float(_MODE['ambient_temp_c'])
RHO = calc_sea_level_density_kg_m3(AMBIENT_TEMP_C)
THRUST_TEMP_FACTOR = calc_thrust_temp_factor(AMBIENT_TEMP_C)

MASS_KG_MTOW = float(_REF['mass_kg_mtow'])
MASS_KG_A2A = float(_REF['mass_kg_a2a'])
MASS_KG = MASS_KG_A2A
WEIGHT_N = MASS_KG * G

S_REF_M2 = float(_REF['s_ref_m2'])
WINGSPAN_M = float(_REF['wingspan_m'])
WING_HEIGHT_M = float(_REF['wing_height_m'])
ASPECT_RATIO = WINGSPAN_M ** 2 / S_REF_M2

NOZZLE_RATE_DEG_S = float(_SHARED['nozzle_rate_deg_s'])
T_MAIN_STOVL_SL_N = float(_REF['t_main_stovl_sl_n'])
ROLLPOST_EFFICIENCY = float(_SHARED['rollpost_efficiency'])
T_LIFTFAN_SL_N = float(_REF['t_liftfan_sl_n'])
T_ROLLPOSTS_SL_N = float(_REF['t_rollposts_sl_n'])
T_MAIN_STOVL_N = T_MAIN_STOVL_SL_N * THRUST_TEMP_FACTOR
T_LIFTFAN_N = T_LIFTFAN_SL_N * THRUST_TEMP_FACTOR
T_ROLLPOSTS_N = T_ROLLPOSTS_SL_N * THRUST_TEMP_FACTOR
T_MAIN_GROUND_N = T_MAIN_STOVL_N + T_ROLLPOSTS_N / ROLLPOST_EFFICIENCY

CD0 = float(_REF['cd0'])
LAYOUT = 'conventional'
CANARD_HTAIL_AREA_M2 = 0.0
SWEEP_LE_DEG = float(_REF['sweep_le_deg'])

SKI_JUMP_ANGLE_DEG = float(_MODE['ski_jump_angle_deg'])
SKI_JUMP_ARC: SkiJumpArc = compute_ski_jump_arc(
    SKI_JUMP_ANGLE_DEG, lip_height_m=float(_MODE['ski_jump_lip_height_m']))
SKI_JUMP_ANGLE_RAD = SKI_JUMP_ARC.angle_rad
SKI_JUMP_RADIUS_M = SKI_JUMP_ARC.radius_m
SKI_JUMP_ARC_LENGTH_M = SKI_JUMP_ARC.arc_length_m
SKI_JUMP_HORIZONTAL_M = SKI_JUMP_ARC.horizontal_m
SKI_JUMP_LIP_HEIGHT_M = SKI_JUMP_ARC.lip_height_m
SKI_JUMP_COS = SKI_JUMP_ARC.cos_exit
SKI_JUMP_SIN = SKI_JUMP_ARC.sin_exit
SKI_JUMP_LENGTH_M = SKI_JUMP_ARC_LENGTH_M
MU = float(_MODE['mu'])
WIND_KT = float(_MODE['wind_kt'])
V_WIND_MPS = WIND_KT * KT_TO_MPS

MIN_SAFE_DISTANCE_M = float(_MODE['min_safe_distance_m'])

_SRCH_KEY = 'with_air_nozzle' if ALLOW_AIR_NOZZLE_VECTORING else 'without_air_nozzle'
_SRCH = _SEARCH[_SRCH_KEY]
_SC = _SEARCH['strategy_c']

FLAT_LENGTH_M_LIST_C = cfg_range(_SC['flat_length_m'])
PITCH_DEG_LIST_C = cfg_range(_SC['pitch_deg'])

NOZZLE_TAKEOFF_DEG_LIST_A = cfg_range(_SRCH['nozzle_takeoff_deg_a'])
FLAT_LENGTH_M_LIST_A = cfg_range(_SRCH['flat_length_m_a'])
V_TRANS_MPS_LIST_A = cfg_range(_SRCH['v_trans_mps_a'])
NOZZLE_TAKEOFF_DEG_LIST_B = cfg_range(_SRCH['nozzle_takeoff_deg_b'])
FLAT_LENGTH_M_LIST_B = cfg_range(_SRCH['flat_length_m_b'])
PITCH_DEG_LIST = cfg_range(_SRCH['pitch_deg'])
NOZZLE_AIR_DEG_LIST = cfg_range(_SRCH['nozzle_air_deg'])

FINE_SEARCH_STEP = int(_SHARED['fine_search_step'])

PLUME_PARAMS: ExhaustPlumeParams = default_exhaust_plume_params()


def apply_exhaust_plume_params(params: ExhaustPlumeParams) -> None:
    """设置本机尾流模型参数（按机型在仿真前调用）。"""
    global PLUME_PARAMS
    PLUME_PARAMS = params


def calc_exhaust_safe_distance_m(theta_deg, u_wind_mps):
    """尾流衰减至安全阈值所需的水平向后距离，m。"""
    return _calc_exhaust_safe_distance_m(theta_deg, u_wind_mps, RHO, PLUME_PARAMS)


def calc_exhaust_theta_deg_for_safe_distance_m(max_safe_m, u_wind_mps):
    """calc_exhaust_safe_distance_m 的反函数：求最小喷流角 θ（°）。"""
    return _calc_exhaust_theta_deg_for_safe_distance_m(max_safe_m, u_wind_mps, RHO, PLUME_PARAMS)


def calc_min_nozzle_deg_for_plume(x_m, min_safe_distance_m, u_wind_mps, deck_angle_deg=0.0):
    """位置 x 处满足尾流约束的最小喷口偏转角（°）；deck_angle_deg 为当前甲板切线角。"""
    return _calc_min_nozzle_deg_for_plume(
        x_m, min_safe_distance_m, u_wind_mps, deck_angle_deg, RHO, PLUME_PARAMS)


def update_min_plume_trailing_edge_m(x_m, theta_deg, u_wind_mps, current_min_m):
    """更新甲板上受影响最后缘位置，m：滑跑全程 min(x − 安全距离)。"""
    return _update_min_plume_trailing_edge_m(
        x_m, theta_deg, u_wind_mps, current_min_m, RHO, PLUME_PARAMS)


def _plume_edge_or_zero(value):
    return value if value is not None else 0.0


TAXI_ALPHA_DEG = taxi_alpha_deg()


def recompute_aero_parameters():
    global ASPECT_RATIO, WEIGHT_N, OSWALD_E, K_IND, CL_ALPHA, PHI_GROUND_FLAT, CL_TAXI
    ASPECT_RATIO = WINGSPAN_M ** 2 / S_REF_M2
    WEIGHT_N = MASS_KG * G
    OSWALD_E = calc_oswald_e(ASPECT_RATIO, SWEEP_LE_DEG)
    K_IND = 1 / (np.pi * ASPECT_RATIO * OSWALD_E)
    CL_ALPHA = calc_cl_alpha_with_canard(
        ASPECT_RATIO, OSWALD_E, SWEEP_LE_DEG,
        layout=LAYOUT, canard_area_m2=CANARD_HTAIL_AREA_M2, wing_area_m2=S_REF_M2,
    )
    PHI_GROUND_FLAT = calc_ground_effect_phi(WING_HEIGHT_M, WINGSPAN_M)
    CL_TAXI = calc_cl_from_alpha_deg(TAXI_ALPHA_DEG, CL_ALPHA)


def apply_thrust_temperature(ambient_temp_c):
    global AMBIENT_TEMP_C, RHO, THRUST_TEMP_FACTOR
    global T_MAIN_STOVL_N, T_LIFTFAN_N, T_ROLLPOSTS_N, T_MAIN_GROUND_N
    AMBIENT_TEMP_C = ambient_temp_c
    RHO = calc_sea_level_density_kg_m3(ambient_temp_c)
    THRUST_TEMP_FACTOR = calc_thrust_temp_factor(ambient_temp_c)
    T_MAIN_STOVL_N = T_MAIN_STOVL_SL_N * THRUST_TEMP_FACTOR
    T_LIFTFAN_N = T_LIFTFAN_SL_N * THRUST_TEMP_FACTOR
    T_ROLLPOSTS_N = T_ROLLPOSTS_SL_N * THRUST_TEMP_FACTOR
    T_MAIN_GROUND_N = T_MAIN_STOVL_N + T_ROLLPOSTS_N / ROLLPOST_EFFICIENCY


def apply_wind_knots(wind_kt):
    apply_wind_knots_globals(wind_kt, globals())


def apply_stovl_thrust_sl(t_main_sl_n, t_liftfan_sl_n, t_rollposts_sl_n):
    global T_MAIN_STOVL_SL_N, T_LIFTFAN_SL_N, T_ROLLPOSTS_SL_N
    T_MAIN_STOVL_SL_N = t_main_sl_n
    T_LIFTFAN_SL_N = t_liftfan_sl_n or 0.0
    T_ROLLPOSTS_SL_N = t_rollposts_sl_n or 0.0
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


def apply_ski_jump_deck(angle_deg, lip_height_m=None):
    """设置圆弧滑跃甲板；仅需出口切线角，可选唇口高度定半径。"""
    assign_ski_jump_globals(globals(), angle_deg, lip_height_m=lip_height_m)


recompute_aero_parameters()

DT_DEFAULT = float(_MODE['dt_default'])
MAX_GROUND_TIME_S = float(_MODE['max_ground_time_s'])
MAX_AIR_TIME_S = float(_MODE['max_air_time_s'])
ALPHA_LIMIT_RAD = np.radians(float(_MODE['alpha_limit_deg']))
CL_MIN, CL_MAX = 0.2, 1.8


def print_config_summary():
    mode = "离甲板后可偏转" if ALLOW_AIR_NOZZLE_VECTORING else "离甲板后固定"
    print(f"仿真模式:     {mode}")
    print(f"环境温度:     {AMBIENT_TEMP_C:.0f} °C (推力标定 {T_THRUST_REF_C:.0f} °C)")
    print(f"空气密度 ρ:   {RHO:.4f} kg/m³ | 推力温度系数 {THRUST_TEMP_FACTOR:.4f}")
    print(f"实际推力({AMBIENT_TEMP_C:.0f}°C SL): 主喷管 {T_MAIN_STOVL_N/1000:.1f} kN，"
          f"升力风扇 {T_LIFTFAN_N/1000:.1f} kN，滚转 {T_ROLLPOSTS_N/1000:.1f} kN"
          f"（{T_THRUST_REF_C:.0f}°C 标定 {T_MAIN_STOVL_SL_N/1000:.1f}/"
          f"{T_LIFTFAN_SL_N/1000:.1f}/{T_ROLLPOSTS_SL_N/1000:.1f} kN）")
    print(f"起飞重量:     {MASS_KG:,} kg")
    print(f"展弦比 AR:    {ASPECT_RATIO:.3f}")
    print(f"甲板风:       {WIND_KT} kt ({V_WIND_MPS:.2f} m/s)")
    print(f"地面效应 φ:   {PHI_GROUND_FLAT:.3f}")
    print(f"Oswald η:     {OSWALD_E:.4f}")
    print(f"诱导因子 k:   {K_IND:.3f}")
    print(f"C_Lα:         {CL_ALPHA:.4f} /rad  (Λ={SWEEP_LE_DEG}°)")
    print(f"Cl_taxi:      {CL_TAXI:.4f}")
    print(f"滑跃圆弧:     {SKI_JUMP_ANGLE_DEG:.1f}° 出口 | R={SKI_JUMP_RADIUS_M:.0f} m | "
          f"弧长 {SKI_JUMP_ARC_LENGTH_M:.1f} m | 水平 {SKI_JUMP_HORIZONTAL_M:.1f} m | "
          f"唇高 {SKI_JUMP_LIP_HEIGHT_M:.1f} m")


def total_takeoff_distance_m(flat_length_m):
    return _total_takeoff_distance_m(flat_length_m, SKI_JUMP_HORIZONTAL_M)


def dynamic_pressure(airspeed_mps):
    """动压 q = ½·ρ·V²，Pa"""
    return _dynamic_pressure(RHO, airspeed_mps)


def drag_coefficient(cl, phi_ground):
    """阻力系数 Cd = Cd0 + k·Cl²·φ（含地面效应修正）"""
    return _drag_coefficient(CD0, K_IND, cl, phi_ground)


def simulate(flat_length_m, v_trans_mps, nozzle_takeoff_deg, strategy, pitch_deg,
             nozzle_air_deg=0, dt=DT_DEFAULT, trajectory: list | None = None):
    """
    滑跃短距起飞全过程仿真。

    返回: (success, x_deck, v_deck, t_deck, min_vy, min_plume_trailing_edge_m)
    若传入 trajectory 列表，则按间隔写入 {'x','y','t','phase'} 轨迹点。
    """
    check_pitch_deg(pitch_deg)
    nozzle_final_rad = np.radians(nozzle_takeoff_deg)
    trans_duration_s = nozzle_takeoff_deg / NOZZLE_RATE_DEG_S if nozzle_takeoff_deg > 0 else 0.0
    pitch_rad = np.radians(pitch_deg)
    nozzle_start_rad = 0.0
    min_plume_trailing_edge_m = None

    v_gs, x, t = 0.0, 0.0, 0.0
    y = 0.0
    rec = TrajectoryRecorder(trajectory)
    rec.record(x, y, t, 'flat', force=True)
    transitioned, in_trans, trans_start_t = False, False, 0.0
    nozzle_rad = nozzle_start_rad

    def track_plume(deck_deg):
        """θ = 喷口偏转角 + 当前甲板切线角；更新甲板受影响最后缘。"""
        nonlocal min_plume_trailing_edge_m
        theta_deg = np.degrees(nozzle_rad) + deck_deg
        min_plume_trailing_edge_m = update_min_plume_trailing_edge_m(
            x, theta_deg, V_WIND_MPS, min_plume_trailing_edge_m)

    def step_nozzle():
        nonlocal transitioned, in_trans, trans_start_t, nozzle_rad
        if (strategy == 'A' and not transitioned and not in_trans
                and v_gs >= v_trans_mps):
            in_trans, trans_start_t = True, t
        if in_trans:
            ratio = (t - trans_start_t) / trans_duration_s if trans_duration_s > 0 else 1.0
            if ratio >= 1.0:
                ratio, in_trans, transitioned = 1.0, False, True
            nozzle_rad = nozzle_start_rad + (nozzle_final_rad - nozzle_start_rad) * ratio
        elif strategy == 'B' or transitioned:
            nozzle_rad = nozzle_final_rad

    # ==================== 阶段 1：平直甲板滑跑 ====================
    while x < flat_length_m and t < MAX_GROUND_TIME_S:
        step_nozzle()
        v_air = v_gs + V_WIND_MPS
        q = dynamic_pressure(v_air)
        t_h = T_MAIN_GROUND_N * np.cos(nozzle_rad)
        t_v = T_MAIN_GROUND_N * np.sin(nozzle_rad) + T_LIFTFAN_N
        lift = q * S_REF_M2 * CL_TAXI
        drag = q * S_REF_M2 * drag_coefficient(CL_TAXI, PHI_GROUND_FLAT)
        normal = max(WEIGHT_N - lift - t_v, 0.0)
        v_gs = max(v_gs + (t_h - drag - MU * normal) / MASS_KG * dt, 0.0)
        x += v_gs * dt
        t += dt
        track_plume(0.0)
        rec.record(x, y, t, 'flat')

    rec.record(x, y, t, 'flat', force=True)

    # ==================== 阶段 2：滑跃圆弧段 ====================
    s = 0.0
    while s < SKI_JUMP_ARC_LENGTH_M and t < MAX_GROUND_TIME_S:
        step_nozzle()
        deck_deg = deck_angle_deg_at_s(s, SKI_JUMP_ARC)
        cos_p, sin_p = deck_cos_sin_at_s(s, SKI_JUMP_ARC)
        v_air = v_gs + V_WIND_MPS * cos_p
        q = dynamic_pressure(v_air)
        phi_s = PHI_GROUND_FLAT * (1 - s / SKI_JUMP_ARC_LENGTH_M) + s / SKI_JUMP_ARC_LENGTH_M
        t_s = T_MAIN_GROUND_N * np.cos(nozzle_rad)
        t_n = T_MAIN_GROUND_N * np.sin(nozzle_rad) + T_LIFTFAN_N
        lift = q * S_REF_M2 * CL_TAXI
        drag = q * S_REF_M2 * drag_coefficient(CL_TAXI, phi_s)
        normal = max(WEIGHT_N * cos_p - lift - t_n, 0.0)
        v_gs = max(v_gs + (t_s - drag - WEIGHT_N * sin_p - MU * normal) / MASS_KG * dt, 0.0)
        s += v_gs * dt
        x += v_gs * cos_p * dt
        y = deck_height_at_s(s, SKI_JUMP_ARC)
        t += dt
        track_plume(deck_deg)
        rec.record(x, y, t, 'arc')

    if s < SKI_JUMP_ARC_LENGTH_M * 0.99:
        return False, x, v_gs, t, 0.0, _plume_edge_or_zero(min_plume_trailing_edge_m)

    v_deck = v_gs
    vx = v_gs * SKI_JUMP_COS
    vy = v_gs * SKI_JUMP_SIN
    x_deck, t_deck = x, t
    y_deck = y
    min_vy = vy
    rec.record(x_deck, y_deck, t_deck, 'deck_exit', force=True)

    if vy < 0:
        return False, x_deck, v_deck, t_deck, min_vy, _plume_edge_or_zero(min_plume_trailing_edge_m)

    plume_trailing_edge_m = _plume_edge_or_zero(min_plume_trailing_edge_m)
    if ALLOW_AIR_NOZZLE_VECTORING:
        return _simulate_air_vectoring(
            vx, vy, pitch_rad, nozzle_final_rad, nozzle_takeoff_deg, nozzle_air_deg,
            x_deck, v_deck, t_deck, min_vy, plume_trailing_edge_m, dt,
            trajectory=trajectory, y_deck=y_deck)
    return _simulate_air_fixed(
        vx, vy, pitch_rad, nozzle_final_rad,
        x_deck, v_deck, t_deck, min_vy, plume_trailing_edge_m, dt,
        trajectory=trajectory, y_deck=y_deck)


def _simulate_air_fixed(vx, vy, pitch_rad, nozzle_final_rad,
                        x_deck, v_deck, t_deck, min_vy, min_plume_trailing_edge_m, dt,
                        trajectory=None, y_deck=None):
    rec = TrajectoryRecorder(trajectory)
    t = t_deck
    x_air = x_deck
    y_air = y_deck if y_deck is not None else SKI_JUMP_LIP_HEIGHT_M
    t_air = 0.0
    while t_air < MAX_AIR_TIME_S:
        rec.record(x_air, y_air, t, 'air')
        v_spd = np.hypot(vx, vy)
        gamma = np.arctan2(vy, vx) if v_spd > 0.1 else 0.0
        v_air = np.hypot(vx + V_WIND_MPS, vy)
        q = dynamic_pressure(v_air)
        alpha_eff = pitch_rad - gamma
        if abs(alpha_eff) > ALPHA_LIMIT_RAD:
            return False, x_deck, v_deck, t_deck, min_vy, min_plume_trailing_edge_m

        cl = np.clip(CL_TAXI + CL_ALPHA * alpha_eff, CL_MIN, CL_MAX)
        lift = q * S_REF_M2 * cl
        drag = q * S_REF_M2 * (CD0 + K_IND * cl * cl)

        thrust_ang = pitch_rad + nozzle_final_rad
        t_mx = T_MAIN_STOVL_N * np.cos(thrust_ang)
        t_my = T_MAIN_STOVL_N * np.sin(thrust_ang)
        t_vx = -(T_LIFTFAN_N + T_ROLLPOSTS_N) * np.sin(pitch_rad)
        t_vy = (T_LIFTFAN_N + T_ROLLPOSTS_N) * np.cos(pitch_rad)

        sin_g, cos_g = np.sin(gamma), np.cos(gamma)
        lx, ly = -lift * sin_g, lift * cos_g
        dx, dy = -drag * cos_g, -drag * sin_g
        dvx = (t_mx + t_vx + lx + dx) / MASS_KG
        dvy = (t_my + t_vy + ly + dy - WEIGHT_N) / MASS_KG

        if dvy < -15:
            return False, x_deck, v_deck, t_deck, min_vy, min_plume_trailing_edge_m

        vx += dvx * dt
        vy += dvy * dt
        x_air += vx * dt
        y_air += vy * dt
        t_air += dt
        t += dt
        min_vy = min(min_vy, vy)

        if vy <= 0:
            rec.record(x_air, y_air, t, 'air', force=True)
            return False, x_deck, v_deck, t_deck, min_vy, min_plume_trailing_edge_m
        if lift + t_vy >= WEIGHT_N and vy > 2 and t_air > 0.3:
            rec.record(x_air, y_air, t, 'air', force=True)
            break

    return True, x_deck, v_deck, t_deck, min_vy, min_plume_trailing_edge_m


def _simulate_air_vectoring(vx, vy, pitch_rad, nozzle_final_rad, nozzle_takeoff_deg, nozzle_air_deg,
                            x_deck, v_deck, t_deck, min_vy, min_plume_trailing_edge_m, dt,
                            trajectory=None, y_deck=None):
    rec = TrajectoryRecorder(trajectory)
    t = t_deck
    x_air = x_deck
    y_air = y_deck if y_deck is not None else SKI_JUMP_LIP_HEIGHT_M
    nozzle_air_final_rad = np.radians(nozzle_air_deg)
    trans_air_duration_s = abs(nozzle_air_deg - nozzle_takeoff_deg) / NOZZLE_RATE_DEG_S
    in_trans_air, transitioned_air, trans_air_start_t = False, False, 0.0
    nozzle_air_rad = nozzle_final_rad
    t_air = 0.0

    while t_air < MAX_AIR_TIME_S:
        rec.record(x_air, y_air, t, 'air')
        if nozzle_air_deg != nozzle_takeoff_deg:
            if not transitioned_air and not in_trans_air:
                in_trans_air, trans_air_start_t = True, t_air
            if in_trans_air:
                ratio = ((t_air - trans_air_start_t) / trans_air_duration_s
                         if trans_air_duration_s > 0 else 1.0)
                if ratio >= 1.0:
                    ratio, in_trans_air, transitioned_air = 1.0, False, True
                nozzle_air_rad = nozzle_final_rad + (nozzle_air_final_rad - nozzle_final_rad) * ratio
            elif transitioned_air:
                nozzle_air_rad = nozzle_air_final_rad

        v_spd = np.hypot(vx, vy)
        gamma = np.arctan2(vy, vx) if v_spd > 0.1 else 0.0
        v_air = np.hypot(vx + V_WIND_MPS, vy)
        q = dynamic_pressure(v_air)
        alpha_eff = pitch_rad - gamma
        if abs(alpha_eff) > ALPHA_LIMIT_RAD:
            return False, x_deck, v_deck, t_deck, min_vy, min_plume_trailing_edge_m

        cl = np.clip(CL_TAXI + CL_ALPHA * alpha_eff, CL_MIN, CL_MAX)
        lift = q * S_REF_M2 * cl
        drag = q * S_REF_M2 * (CD0 + K_IND * cl * cl)

        thrust_ang = pitch_rad + nozzle_air_rad
        t_mx = T_MAIN_STOVL_N * np.cos(thrust_ang)
        t_my = T_MAIN_STOVL_N * np.sin(thrust_ang)
        t_vx = -(T_LIFTFAN_N + T_ROLLPOSTS_N) * np.sin(pitch_rad)
        t_vy = (T_LIFTFAN_N + T_ROLLPOSTS_N) * np.cos(pitch_rad)

        sin_g, cos_g = np.sin(gamma), np.cos(gamma)
        dvx = (t_mx + t_vx - lift * sin_g - drag * cos_g) / MASS_KG
        dvy = (t_my + t_vy + lift * cos_g - drag * sin_g - WEIGHT_N) / MASS_KG
        if dvy < -15:
            return False, x_deck, v_deck, t_deck, min_vy, min_plume_trailing_edge_m

        vx += dvx * dt
        vy += dvy * dt
        x_air += vx * dt
        y_air += vy * dt
        t_air += dt
        t += dt
        min_vy = min(min_vy, vy)
        if vy <= 0:
            rec.record(x_air, y_air, t, 'air', force=True)
            return False, x_deck, v_deck, t_deck, min_vy, min_plume_trailing_edge_m
        if lift + t_vy >= WEIGHT_N and vy > 2 and t_air > 0.3:
            rec.record(x_air, y_air, t, 'air', force=True)
            break

    return True, x_deck, v_deck, t_deck, min_vy, min_plume_trailing_edge_m


def _ground_step_flat_c(v_gs, x, nozzle_deg, dt):
    nozzle_rad = np.radians(nozzle_deg)
    v_air = v_gs + V_WIND_MPS
    q = dynamic_pressure(v_air)
    t_h = T_MAIN_GROUND_N * np.cos(nozzle_rad)
    t_v = T_MAIN_GROUND_N * np.sin(nozzle_rad) + T_LIFTFAN_N
    lift = q * S_REF_M2 * CL_TAXI
    drag = q * S_REF_M2 * drag_coefficient(CL_TAXI, PHI_GROUND_FLAT)
    normal = max(WEIGHT_N - lift - t_v, 0.0)
    v2 = max(v_gs + (t_h - drag - MU * normal) / MASS_KG * dt, 0.0)
    return v2, x + v2 * dt


def _ground_step_ski_c(v_gs, x, s, nozzle_deg, dt):
    nozzle_rad = np.radians(nozzle_deg)
    cos_p, sin_p = deck_cos_sin_at_s(s, SKI_JUMP_ARC)
    v_air = v_gs + V_WIND_MPS * cos_p
    q = dynamic_pressure(v_air)
    phi_s = PHI_GROUND_FLAT * (1 - s / SKI_JUMP_ARC_LENGTH_M) + s / SKI_JUMP_ARC_LENGTH_M
    t_s = T_MAIN_GROUND_N * np.cos(nozzle_rad)
    t_n = T_MAIN_GROUND_N * np.sin(nozzle_rad) + T_LIFTFAN_N
    lift = q * S_REF_M2 * CL_TAXI
    drag = q * S_REF_M2 * drag_coefficient(CL_TAXI, phi_s)
    normal = max(WEIGHT_N * cos_p - lift - t_n, 0.0)
    v2 = max(v_gs + (t_s - drag - WEIGHT_N * sin_p - MU * normal) / MASS_KG * dt, 0.0)
    s2 = s + v2 * dt
    return v2, x + v2 * cos_p * dt, s2


def simulate_strategy_c(flat_length_m, pitch_deg, min_safe_distance_m, dt=DT_DEFAULT):
    """
    策略 C：尾流约束下 DP 优化喷口减小 schedule，再经空中段判定能否成功离舰。
    """
    check_pitch_deg(pitch_deg)
    if min_safe_distance_m >= 0:
        raise ValueError("min_safe_distance_m 必须为负值")

    rate_step = NOZZLE_RATE_DEG_S * dt
    init_nozzle = calc_min_nozzle_deg_for_plume(0.0, min_safe_distance_m, V_WIND_MPS, deck_angle_deg=0.0)
    states = {round(init_nozzle, 2): (0.0, 0.0, 0.0, 0.0, False)}
    min_plume_trailing_edge_m = None
    completed = []

    for _ in range(int(MAX_GROUND_TIME_S / dt) * 3):
        if not states:
            break
        new_states = {}
        for nozzle_deg, (v_gs, x, t, s, on_ski) in states.items():
            if on_ski and s >= SKI_JUMP_ARC_LENGTH_M:
                completed.append((nozzle_deg, v_gs, x, t, s))
                continue

            deck_deg = deck_angle_deg_at_s(s, SKI_JUMP_ARC) if on_ski else 0.0
            nozzle_min = calc_min_nozzle_deg_for_plume(
                x, min_safe_distance_m, V_WIND_MPS, deck_angle_deg=deck_deg)
            nozzle_deg = max(nozzle_deg, nozzle_min)

            for decrease in (False, True):
                n2 = nozzle_deg - rate_step if decrease else nozzle_deg
                if decrease and n2 < nozzle_min - 1e-9:
                    continue
                n2 = max(n2, nozzle_min)

                if on_ski:
                    v2, x2, s2 = _ground_step_ski_c(v_gs, x, s, n2, dt)
                    on_ski2 = True
                    theta_deg = n2 + deck_angle_deg_at_s(s, SKI_JUMP_ARC)
                else:
                    v2, x2 = _ground_step_flat_c(v_gs, x, n2, dt)
                    on_ski2 = x2 >= flat_length_m
                    s2 = 0.0
                    theta_deg = n2

                t2 = t + dt
                min_plume_trailing_edge_m = update_min_plume_trailing_edge_m(
                    x2, theta_deg, V_WIND_MPS, min_plume_trailing_edge_m)

                if on_ski2 and s2 >= SKI_JUMP_ARC_LENGTH_M:
                    completed.append((n2, v2, x2, t2, s2))
                    continue

                key = round(n2, 2)
                val = (v2, x2, t2, s2, on_ski2)
                if key not in new_states or v2 > new_states[key][0]:
                    new_states[key] = val
        states = new_states

    pitch_rad = np.radians(pitch_deg)
    plume_val = _plume_edge_or_zero(min_plume_trailing_edge_m)
    best = None
    total_m = total_takeoff_distance_m(flat_length_m)

    for nozzle_deg, v_deck, x_deck, t_deck, s in completed:
        if s < SKI_JUMP_ARC_LENGTH_M * 0.99:
            continue
        vy = v_deck * SKI_JUMP_SIN
        if vy < 0:
            continue
        vx = v_deck * SKI_JUMP_COS
        nozzle_rad = np.radians(nozzle_deg)
        ok, _, _, _, min_vy, _ = _simulate_air_fixed(
            vx, vy, pitch_rad, nozzle_rad, x_deck, v_deck, t_deck, vy, plume_val, dt)
        if not ok:
            continue
        candidate = dict(
            total_m=total_m, flat_m=flat_length_m, pitch_deg=pitch_deg,
            nozzle_deg=nozzle_deg, v_deck_mps=v_deck, t_deck_s=t_deck,
            min_vy_mps=min_vy, min_plume_trailing_edge_m=plume_val,
        )
        if best is None or v_deck > best['v_deck_mps']:
            best = candidate

    return best


def search_strategy_c(min_safe_distance_m):
    best = None
    for flat_m in FLAT_LENGTH_M_LIST_C:
        for pitch_deg in PITCH_DEG_LIST_C:
            result = simulate_strategy_c(flat_m, pitch_deg, min_safe_distance_m)
            if result and (best is None or result['total_m'] < best['total_m']):
                best = result
    if best:
        refined = fine_tune_strategy_c(best, min_safe_distance_m)
        if refined:
            best = refined
    return best


def fine_tune_strategy_c(initial, min_safe_distance_m):
    best = initial
    flat_step = grid_step(FLAT_LENGTH_M_LIST_C)
    pitch_step = grid_step(PITCH_DEG_LIST_C)
    pitch_min = PITCH_DEG_LIST_C.start
    for flat_m in fine_range_deck(initial['flat_m'], flat_step, FINE_SEARCH_STEP):
        for pitch_deg in fine_range_symmetric(
                initial['pitch_deg'], pitch_step, FINE_SEARCH_STEP,
                min_val=pitch_min, max_val=PITCH_MAX_DEG):
            result = simulate_strategy_c(flat_m, pitch_deg, min_safe_distance_m)
            if result and result['total_m'] < best['total_m']:
                best = result
    return best if best['total_m'] < initial['total_m'] else None


def print_strategy_c_result(title, r):
    print(f"★ {title}: 总距 {r['total_m']:.1f} m ({r['total_m'] * M_TO_FT:.0f} ft)")
    print(f"    平直段 {r['flat_m']:.0f} m | 俯仰角 {r['pitch_deg']}°")
    print(f"    离甲板喷管角 {r['nozzle_deg']:.1f}° | 离甲板 {r['v_deck_mps']:.1f} m/s @ {r['t_deck_s']:.1f} s")
    print(f"    最小 Vy {r['min_vy_mps']:.2f} m/s")
    print(f"    离甲板总时间 {r['t_deck_s']:.2f} s | 甲板受影响最后缘 {r['min_plume_trailing_edge_m']:.1f} m")


def _pack_result_a_fixed(total_m, flat_m, v_trans, nozzle_deg, pitch_deg, v_deck, t_deck, min_vy,
                         plume_trailing_edge_m):
    return dict(total_m=total_m, flat_m=flat_m, v_trans_mps=v_trans, nozzle_deg=nozzle_deg,
                pitch_deg=pitch_deg, v_deck_mps=v_deck, t_deck_s=t_deck, min_vy_mps=min_vy,
                min_plume_trailing_edge_m=plume_trailing_edge_m)


def _pack_result_a_vectoring(total_m, flat_m, v_trans, nozzle_deg, nozzle_air_deg, pitch_deg,
                             v_deck, t_deck, min_vy, plume_trailing_edge_m):
    return dict(total_m=total_m, flat_m=flat_m, v_trans_mps=v_trans, nozzle_deg=nozzle_deg,
                nozzle_air_deg=nozzle_air_deg, pitch_deg=pitch_deg, v_deck_mps=v_deck,
                t_deck_s=t_deck, min_vy_mps=min_vy, min_plume_trailing_edge_m=plume_trailing_edge_m)


def _pack_result_b_fixed(total_m, flat_m, nozzle_deg, pitch_deg, v_deck, t_deck, min_vy, plume_trailing_edge_m):
    return dict(total_m=total_m, flat_m=flat_m, nozzle_deg=nozzle_deg, pitch_deg=pitch_deg,
                v_deck_mps=v_deck, t_deck_s=t_deck, min_vy_mps=min_vy, min_plume_trailing_edge_m=plume_trailing_edge_m)


def _pack_result_b_vectoring(total_m, flat_m, nozzle_deg, nozzle_air_deg, pitch_deg, v_deck,
                             t_deck, plume_trailing_edge_m):
    return dict(total_m=total_m, flat_m=flat_m, nozzle_deg=nozzle_deg,
                nozzle_air_deg=nozzle_air_deg, pitch_deg=pitch_deg, v_deck_mps=v_deck,
                t_deck_s=t_deck, min_plume_trailing_edge_m=plume_trailing_edge_m)


def print_strategy_a_result(title, r):
    print(f"★ {title}: 总距 {r['total_m']:.1f} m ({r['total_m'] * M_TO_FT:.0f} ft)")
    if ALLOW_AIR_NOZZLE_VECTORING:
        print(f"    平直段 {r['flat_m']:.0f} m | 转换地速 {r['v_trans_mps']} m/s | 滑跑喷管角 {r['nozzle_deg']}°")
        print(f"    离甲板喷管角 {r['nozzle_air_deg']}° | 俯仰角 {r['pitch_deg']}° | 离甲板速度 {r['v_deck_mps']:.1f} m/s")
    else:
        print(f"    平直段 {r['flat_m']:.0f} m | 转换地速 {r['v_trans_mps']} m/s | 喷管角 {r['nozzle_deg']}°")
        print(f"    俯仰角 {r['pitch_deg']}° | 离甲板 {r['v_deck_mps']:.1f} m/s @ {r['t_deck_s']:.1f} s")
    print(f"    最小 Vy {r['min_vy_mps']:.2f} m/s")
    print(f"    离甲板总时间 {r['t_deck_s']:.2f} s | 甲板受影响最后缘 {r['min_plume_trailing_edge_m']:.1f} m")


def print_strategy_b_result(title, r):
    print(f"★ {title}: 总距 {r['total_m']:.1f} m ({r['total_m'] * M_TO_FT:.0f} ft)")
    if ALLOW_AIR_NOZZLE_VECTORING:
        print(f"    平直段 {r['flat_m']:.0f} m | 固定喷管角 {r['nozzle_deg']}°")
        print(f"    离甲板喷管角 {r['nozzle_air_deg']}° | 俯仰角 {r['pitch_deg']}° | 离甲板速度 {r['v_deck_mps']:.1f} m/s")
    else:
        print(f"    平直段 {r['flat_m']:.0f} m | 固定喷管角 {r['nozzle_deg']}° | 俯仰角 {r['pitch_deg']}°")
        print(f"    离甲板 {r['v_deck_mps']:.1f} m/s @ {r['t_deck_s']:.1f} s")
    print(f"    离甲板总时间 {r['t_deck_s']:.2f} s | 甲板受影响最后缘 {r['min_plume_trailing_edge_m']:.1f} m")


def search_strategy_a():
    best = None
    if ALLOW_AIR_NOZZLE_VECTORING:
        for flat_m in FLAT_LENGTH_M_LIST_A:
            for nozzle_deg in NOZZLE_TAKEOFF_DEG_LIST_A:
                for v_trans in V_TRANS_MPS_LIST_A:
                    for nozzle_air_deg in NOZZLE_AIR_DEG_LIST:
                        for pitch_deg in PITCH_DEG_LIST:
                            ok, _, v_deck, t_deck, min_vy, plume_trailing_edge_m = simulate(
                                flat_m, v_trans, nozzle_deg, 'A', pitch_deg, nozzle_air_deg)
                            if not ok:
                                continue
                            total_m = total_takeoff_distance_m(flat_m)
                            candidate = _pack_result_a_vectoring(
                                total_m, flat_m, v_trans, nozzle_deg, nozzle_air_deg, pitch_deg,
                                v_deck, t_deck, min_vy, plume_trailing_edge_m)
                            if best is None or candidate['total_m'] < best['total_m']:
                                best = candidate
    else:
        for flat_m in FLAT_LENGTH_M_LIST_A:
            for nozzle_deg in NOZZLE_TAKEOFF_DEG_LIST_A:
                for v_trans in V_TRANS_MPS_LIST_A:
                    for pitch_deg in PITCH_DEG_LIST:
                        ok, _, v_deck, t_deck, min_vy, plume_trailing_edge_m = simulate(
                            flat_m, v_trans, nozzle_deg, 'A', pitch_deg)
                        if not ok:
                            continue
                        total_m = total_takeoff_distance_m(flat_m)
                        candidate = _pack_result_a_fixed(
                            total_m, flat_m, v_trans, nozzle_deg, pitch_deg,
                            v_deck, t_deck, min_vy, plume_trailing_edge_m)
                        if best is None or candidate['total_m'] < best['total_m']:
                            best = candidate
    return best


def fine_tune_strategy_a(initial):
    best = initial
    flat_step = grid_step(FLAT_LENGTH_M_LIST_A)
    nozzle_step = grid_step(NOZZLE_TAKEOFF_DEG_LIST_A)
    vtrans_step = grid_step(V_TRANS_MPS_LIST_A)
    pitch_step = grid_step(PITCH_DEG_LIST)
    if ALLOW_AIR_NOZZLE_VECTORING:
        air_step = grid_step(NOZZLE_AIR_DEG_LIST)
        for flat_m in fine_range_deck(initial['flat_m'], flat_step, FINE_SEARCH_STEP):
            for v_trans in fine_range_symmetric(
                    initial['v_trans_mps'], vtrans_step, FINE_SEARCH_STEP, min_val=0):
                for nozzle_deg in fine_range_symmetric(
                        initial['nozzle_deg'], nozzle_step, FINE_SEARCH_STEP,
                        min_val=1, max_val=90):
                    for nozzle_air_deg in fine_range_symmetric(
                            initial['nozzle_air_deg'], air_step, FINE_SEARCH_STEP,
                            min_val=0, max_val=90):
                        for pitch_deg in fine_range_symmetric(
                                initial['pitch_deg'], pitch_step, FINE_SEARCH_STEP,
                                min_val=PITCH_DEG_LIST.start, max_val=PITCH_MAX_DEG):
                            ok, _, v_deck, t_deck, min_vy, plume_trailing_edge_m = simulate(
                                flat_m, v_trans, nozzle_deg, 'A', pitch_deg, nozzle_air_deg)
                            if not ok:
                                continue
                            total_m = total_takeoff_distance_m(flat_m)
                            if total_m < best['total_m']:
                                best = _pack_result_a_vectoring(
                                    total_m, flat_m, v_trans, nozzle_deg, nozzle_air_deg, pitch_deg,
                                    v_deck, t_deck, min_vy, plume_trailing_edge_m)
    else:
        for flat_m in fine_range_deck(initial['flat_m'], flat_step, FINE_SEARCH_STEP):
            for v_trans in fine_range_symmetric(
                    initial['v_trans_mps'], vtrans_step, FINE_SEARCH_STEP, min_val=0):
                for nozzle_deg in fine_range_symmetric(
                        initial['nozzle_deg'], nozzle_step, FINE_SEARCH_STEP,
                        min_val=1, max_val=90):
                    for pitch_deg in fine_range_symmetric(
                            initial['pitch_deg'], pitch_step, FINE_SEARCH_STEP,
                            min_val=PITCH_DEG_LIST.start, max_val=PITCH_MAX_DEG):
                        ok, _, v_deck, t_deck, min_vy, plume_trailing_edge_m = simulate(
                            flat_m, v_trans, nozzle_deg, 'A', pitch_deg)
                        if not ok:
                            continue
                        total_m = total_takeoff_distance_m(flat_m)
                        if total_m < best['total_m']:
                            best = _pack_result_a_fixed(
                                total_m, flat_m, v_trans, nozzle_deg, pitch_deg,
                                v_deck, t_deck, min_vy, plume_trailing_edge_m)
    return best if best['total_m'] < initial['total_m'] else None


def search_strategy_b():
    best = None
    if ALLOW_AIR_NOZZLE_VECTORING:
        for nozzle_deg in NOZZLE_TAKEOFF_DEG_LIST_B:
            for flat_m in FLAT_LENGTH_M_LIST_B:
                for nozzle_air_deg in NOZZLE_AIR_DEG_LIST:
                    for pitch_deg in PITCH_DEG_LIST:
                        ok, _, v_deck, t_deck, _, plume_trailing_edge_m = simulate(
                            flat_m, 0, nozzle_deg, 'B', pitch_deg, nozzle_air_deg)
                        if not ok:
                            continue
                        total_m = total_takeoff_distance_m(flat_m)
                        candidate = _pack_result_b_vectoring(
                            total_m, flat_m, nozzle_deg, nozzle_air_deg, pitch_deg, v_deck,
                            t_deck, plume_trailing_edge_m)
                        if best is None or candidate['total_m'] < best['total_m']:
                            best = candidate
    else:
        for flat_m in FLAT_LENGTH_M_LIST_B:
            for nozzle_deg in NOZZLE_TAKEOFF_DEG_LIST_B:
                for pitch_deg in PITCH_DEG_LIST:
                    ok, _, v_deck, t_deck, min_vy, plume_trailing_edge_m = simulate(
                        flat_m, 0, nozzle_deg, 'B', pitch_deg)
                    if not ok:
                        continue
                    total_m = total_takeoff_distance_m(flat_m)
                    candidate = _pack_result_b_fixed(
                        total_m, flat_m, nozzle_deg, pitch_deg, v_deck, t_deck, min_vy, plume_trailing_edge_m)
                    if best is None or candidate['total_m'] < best['total_m']:
                        best = candidate
    return best


def fine_tune_strategy_b(initial):
    best = initial
    flat_step = grid_step(FLAT_LENGTH_M_LIST_B)
    nozzle_step = grid_step(NOZZLE_TAKEOFF_DEG_LIST_B)
    pitch_step = grid_step(PITCH_DEG_LIST)
    if ALLOW_AIR_NOZZLE_VECTORING:
        air_step = grid_step(NOZZLE_AIR_DEG_LIST)
        for flat_m in fine_range_deck(initial['flat_m'], flat_step, FINE_SEARCH_STEP):
            for nozzle_deg in fine_range_symmetric(
                    initial['nozzle_deg'], nozzle_step, FINE_SEARCH_STEP,
                    min_val=0, max_val=90):
                for nozzle_air_deg in fine_range_symmetric(
                        initial['nozzle_air_deg'], air_step, FINE_SEARCH_STEP,
                        min_val=0, max_val=90):
                    for pitch_deg in fine_range_symmetric(
                            initial['pitch_deg'], pitch_step, FINE_SEARCH_STEP,
                            min_val=PITCH_DEG_LIST.start, max_val=PITCH_MAX_DEG):
                        ok, _, v_deck, t_deck, _, plume_trailing_edge_m = simulate(
                            flat_m, 0, nozzle_deg, 'B', pitch_deg, nozzle_air_deg)
                        if not ok:
                            continue
                        total_m = total_takeoff_distance_m(flat_m)
                        if total_m < best['total_m']:
                            best = _pack_result_b_vectoring(
                                total_m, flat_m, nozzle_deg, nozzle_air_deg, pitch_deg, v_deck,
                                t_deck, plume_trailing_edge_m)
    else:
        for flat_m in fine_range_deck(initial['flat_m'], flat_step, FINE_SEARCH_STEP):
            for nozzle_deg in fine_range_symmetric(
                    initial['nozzle_deg'], nozzle_step, FINE_SEARCH_STEP,
                    min_val=0, max_val=90):
                for pitch_deg in fine_range_symmetric(
                        initial['pitch_deg'], pitch_step, FINE_SEARCH_STEP,
                        min_val=PITCH_DEG_LIST.start, max_val=PITCH_MAX_DEG):
                    ok, _, v_deck, t_deck, min_vy, plume_trailing_edge_m = simulate(
                        flat_m, 0, nozzle_deg, 'B', pitch_deg)
                    if not ok:
                        continue
                    total_m = total_takeoff_distance_m(flat_m)
                    if total_m < best['total_m']:
                        best = _pack_result_b_fixed(
                            total_m, flat_m, nozzle_deg, pitch_deg, v_deck, t_deck, min_vy, plume_trailing_edge_m)
    return best if best['total_m'] < initial['total_m'] else None


def run_strategy_a_search():
    """策略 A 粗搜索 + 细化，返回最优结果 dict 或 None。"""
    best = search_strategy_a()
    if not best:
        return None
    refined = fine_tune_strategy_a(best)
    return refined if refined else best


def run_strategy_b_search():
    """策略 B 粗搜索 + 细化，返回最优结果 dict 或 None。"""
    best = search_strategy_b()
    if not best:
        return None
    refined = fine_tune_strategy_b(best)
    return refined if refined else best


def run_strategy_c_search():
    """策略 C（尾流约束）搜索，返回最优结果 dict 或 None。"""
    return search_strategy_c(MIN_SAFE_DISTANCE_M)


def _main():
    print_config_summary()

    print("\n" + "=" * 60)
    print("策略 A：滑跑中延迟偏转喷口（自 0° 转换）")
    print("=" * 60)

    best_a = search_strategy_a()
    if best_a:
        print_strategy_a_result("粗搜索最优", best_a)
        print("细化搜索 …")
        refined_a = fine_tune_strategy_a(best_a)
        if refined_a:
            best_a = refined_a
        print_strategy_a_result("细化最优", best_a)

    print("\n" + "=" * 60)
    print("策略 B：滑跑全程固定喷口")
    print("=" * 60)

    best_b = search_strategy_b()
    if best_b:
        print_strategy_b_result("粗搜索最优", best_b)
        print("细化搜索 …")
        refined_b = fine_tune_strategy_b(best_b)
        if refined_b:
            best_b = refined_b
        print_strategy_b_result("细化最优", best_b)

    print("\n" + "=" * 60)
    print(f"策略 C：尾流约束 min(x−安全距离) ≥ {MIN_SAFE_DISTANCE_M:.0f} m")
    print("=" * 60)

    init_nozzle_c = calc_min_nozzle_deg_for_plume(0.0, MIN_SAFE_DISTANCE_M, V_WIND_MPS, deck_angle_deg=0.0)
    print(f"起始喷管角（x=0 反推）: {init_nozzle_c:.1f}°")

    best_c = search_strategy_c(MIN_SAFE_DISTANCE_M)
    if best_c:
        print_strategy_c_result("最优", best_c)

    print("\n" + "=" * 60)
    print("对比总结")
    print("=" * 60)
    if best_a and best_b:
        diff_m = best_b['total_m'] - best_a['total_m']
        print(f"策略 A: {best_a['total_m']:.1f} m ({best_a['total_m'] * M_TO_FT:.0f} ft)")
        if ALLOW_AIR_NOZZLE_VECTORING:
            print(f"        平直段 {best_a['flat_m']:.0f} m，转换地速 {best_a['v_trans_mps']} m/s")
            print(f"        滑跑喷管角 {best_a['nozzle_deg']}°，离甲板喷管角 {best_a['nozzle_air_deg']}°")
        else:
            print(f"        平直段 {best_a['flat_m']:.0f} m，转换地速 {best_a['v_trans_mps']} m/s，喷管角 {best_a['nozzle_deg']}°")
        print(f"策略 B: {best_b['total_m']:.1f} m ({best_b['total_m'] * M_TO_FT:.0f} ft)")
        print(f"        平直段 {best_b['flat_m']:.0f} m，固定喷管角 {best_b['nozzle_deg']}°")
        print(f"策略 A 比 B 短 {diff_m:.1f} m ({diff_m / best_b['total_m'] * 100:.1f}%)")
        if best_c:
            print(f"策略 C: {best_c['total_m']:.1f} m ({best_c['total_m'] * M_TO_FT:.0f} ft)")
            print(f"        平直段 {best_c['flat_m']:.0f} m，离甲板喷管角 {best_c['nozzle_deg']:.1f}°")
            print(f"        比策略 A {'短' if best_c['total_m'] < best_a['total_m'] else '长'} "
                  f"{abs(best_c['total_m'] - best_a['total_m']):.1f} m")


if __name__ == "__main__":
    _main()
