"""F-35B 短距起飞仿真（平直甲板，策略 A/B/C 喷口偏转对比）。

尾流波及：本模块为 VTOL/STOVL 专用；主喷管尾流模型见 utils.takeoff.exhaust_plume。
常规固定翼滑跃仿真（ski_jump_take_off）不计算尾流波及范围。

策略说明
--------
策略 A — 延迟偏转喷口
    滑跑初期主喷口保持水平（0°），仅升力风扇提供垂直推力；当地速达到
    转换阈值 v_trans 后，以 NOZZLE_RATE_DEG_S 的速率偏转至目标角 nozzle_deg。
    搜索变量：目标喷口角、转换地速。

策略 B — 全程固定喷口
    自滑跑起点起主喷口即固定在某一角度，不再变化。
    搜索变量：固定喷口角。

策略 C — 尾流安全约束下的最优偏转
    给定 MIN_SAFE_DISTANCE_M（负值，如 −60），要求滑跑全程
    min(x − 安全距离) ≥ MIN_SAFE_DISTANCE_M，即尾流后缘不得侵入该 x 以左区域。
    利用 calc_exhaust_safe_distance_m 的反函数，在 x=0 处倒推起始喷口角；
    此后每个时间步根据当前 x 计算最小允许喷口角，并在「保持」与
    「减小 dt×NOZZLE_RATE_DEG_S」之间做动态规划，求最短离地距离。
    搜索变量：MIN_SAFE_DISTANCE_M（用户设定）。
"""
import numpy as np

from utils.takeoff.exhaust_plume import (
    ExhaustPlumeParams,
    calc_exhaust_safe_distance_m as _calc_exhaust_safe_distance_m,
    calc_exhaust_theta_deg_for_safe_distance_m as _calc_exhaust_theta_deg_for_safe_distance_m,
    calc_min_nozzle_deg_for_plume as _calc_min_nozzle_deg_for_plume,
    default_exhaust_plume_params,
    update_min_plume_trailing_edge_m as _update_min_plume_trailing_edge_m,
)
from utils.takeoff.search_utils import fine_range_symmetric
from utils.takeoff.sim_config import apply_wind_knots_globals
from utils.takeoff.takeoff_config import cfg_range, mode_config, shared_config
from utils.takeoff.takeoff_physics import (
    G,
    KT_TO_MPS,
    MPS_TO_KT,
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
    dynamic_pressure as _dynamic_pressure,
    taxi_alpha_deg,
)

_SHARED = shared_config()
_MODE = mode_config('short_takeoff')
_REF = _MODE['reference_aircraft']
_SEARCH = _MODE['search']

# ---------------------------------------------------------------------------
# 大气与温度（推力在 T_THRUST_REF_C 海平面标定）
# ---------------------------------------------------------------------------
AMBIENT_TEMP_C = float(_MODE['ambient_temp_c'])

RHO = calc_sea_level_density_kg_m3(AMBIENT_TEMP_C)
THRUST_TEMP_FACTOR = calc_thrust_temp_factor(AMBIENT_TEMP_C)

# ---------------------------------------------------------------------------
# 飞机与推力参数（F-35B 参考默认值，Web 仿真前由 apply_aircraft_geometry 覆盖）
# ---------------------------------------------------------------------------
MASS_KG = float(_REF['mass_kg'])
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
MU = float(_MODE['mu'])

SWEEP_LE_DEG = float(_REF['sweep_le_deg'])
ROTATION_AOA_DEG = float(_MODE['rotation_aoa_deg'])

WIND_KT = float(_MODE['wind_kt'])
V_WIND_MPS = WIND_KT * KT_TO_MPS

MIN_SAFE_DISTANCE_M = float(_MODE['min_safe_distance_m'])

NOZZLE_FINAL_DEG_START = _SEARCH['nozzle_final_deg']['start']
NOZZLE_FINAL_DEG_END = _SEARCH['nozzle_final_deg']['end']
NOZZLE_FINAL_DEG_STEP = _SEARCH['nozzle_final_deg']['step']
V_TRANS_START_MPS = _SEARCH['v_trans_mps']['start']
V_TRANS_END_MPS = _SEARCH['v_trans_mps']['end']
V_TRANS_STEP_MPS = _SEARCH['v_trans_mps']['step']
NOZZLE_B_DEG_START = _SEARCH['nozzle_b_deg']['start']
NOZZLE_B_DEG_END = _SEARCH['nozzle_b_deg']['end']
NOZZLE_B_DEG_STEP = _SEARCH['nozzle_b_deg']['step']
FINE_SEARCH_STEP = int(_SHARED['fine_search_step'])

DT_DEFAULT = float(_MODE['dt_default'])
MAX_SIM_TIME_S = float(_MODE['max_sim_time_s'])
MAX_RUNWAY_M = float(_MODE['max_runway_m'])

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


def calc_min_nozzle_deg_for_plume(x_m, min_safe_distance_m, u_wind_mps, ski_jump_offset_deg=0.0):
    """位置 x 处满足尾流约束的最小喷口偏转角（°）。"""
    return _calc_min_nozzle_deg_for_plume(
        x_m, min_safe_distance_m, u_wind_mps, ski_jump_offset_deg, RHO, PLUME_PARAMS)


def update_min_plume_trailing_edge_m(x_m, theta_deg, u_wind_mps, current_min_m):
    """更新甲板上受影响最后缘位置，m：滑跑全程 min(x − 安全距离)。"""
    return _update_min_plume_trailing_edge_m(
        x_m, theta_deg, u_wind_mps, current_min_m, RHO, PLUME_PARAMS)


TAXI_ALPHA_DEG = taxi_alpha_deg()  # 滑行等效迎角，°


def recompute_aero_parameters():
    """根据当前 MASS_KG / 几何参数刷新气动派生量。"""
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


recompute_aero_parameters()


def print_config_summary():
    print(f"环境温度:     {AMBIENT_TEMP_C:.0f} °C (推力标定 {T_THRUST_REF_C:.0f} °C)")
    print(f"空气密度 ρ:   {RHO:.4f} kg/m³ | 推力温度系数 {THRUST_TEMP_FACTOR:.4f}")
    print(f"实际推力({AMBIENT_TEMP_C:.0f}°C SL): 主喷管 {T_MAIN_STOVL_N/1000:.1f} kN，"
          f"升力风扇 {T_LIFTFAN_N/1000:.1f} kN，滚转 {T_ROLLPOSTS_N/1000:.1f} kN"
          f"（{T_THRUST_REF_C:.0f}°C 标定 {T_MAIN_STOVL_SL_N/1000:.1f}/"
          f"{T_LIFTFAN_SL_N/1000:.1f}/{T_ROLLPOSTS_SL_N/1000:.1f} kN）")
    print(f"起飞重量:     {MASS_KG:,} kg")
    print(f"展弦比 AR:    {ASPECT_RATIO:.3f}")
    print(f"甲板风:       {WIND_KT} kt ({V_WIND_MPS:.2f} m/s)")
    print(f"地面效应 φ:   {PHI_GROUND:.3f}")
    print(f"Oswald η:     {OSWALD_E:.4f}")
    print(f"诱导因子 k:   {K_IND:.3f}")
    print(f"C_Lα:         {CL_ALPHA:.4f} /rad  (Λ={SWEEP_LE_DEG}°)")
    print(f"Cl_taxi:      {CL_TAXI:.4f}")
    print(f"Cl_rotation:  {CL_ROTATION:.4f}")


def dynamic_pressure(airspeed_mps):
    """动压 q = ½·ρ·V²，Pa"""
    return _dynamic_pressure(RHO, airspeed_mps)


def find_liftoff_index(normal_force):
    """正压力由正变负时的索引（离地瞬间）。"""
    idx = np.where(np.diff(np.sign(normal_force)) < 0)[0]
    return int(idx[0]) if len(idx) else None


def simulate_strategy_a(v_trans_mps, nozzle_final_deg, dt=DT_DEFAULT):
    """策略 A：先水平加速，达阈值后再偏转喷口。"""
    trans_duration_s = nozzle_final_deg / NOZZLE_RATE_DEG_S
    nozzle_final_rad = np.radians(nozzle_final_deg)
    v_gs, x, t = 0.0, 0.0, 0.0
    airborne = False
    transitioned = in_trans = False
    trans_start_t = 0.0
    min_plume_trailing_edge_m = None
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
            nozzle_rad = nozzle_final_rad * ratio
            t_h = T_MAIN_GROUND_N * np.cos(nozzle_rad)
            t_v = T_MAIN_GROUND_N * np.sin(nozzle_rad) + T_LIFTFAN_N
        elif transitioned:
            nozzle_rad = nozzle_final_rad
            t_h = T_MAIN_GROUND_N * np.cos(nozzle_final_rad)
            t_v = T_MAIN_STOVL_N * np.sin(nozzle_final_rad) + T_LIFTFAN_N
        else:
            nozzle_rad = 0.0
            t_h = T_MAIN_GROUND_N
            t_v = T_LIFTFAN_N

        if airborne:
            nozzle_rad = nozzle_final_rad if transitioned else 0.0
            t_h, t_v = T_MAIN_STOVL_N, T_LIFTFAN_N + T_ROLLPOSTS_N

        q = dynamic_pressure(v_air)
        lift = q * S_REF_M2 * CL_TAXI + t_v        # 总升力 = 机翼升力 + 垂直推力
        drag = q * S_REF_M2 * (CD0 + K_IND * CL_TAXI ** 2 * PHI_GROUND)  # 含地面效应的阻力
        normal = WEIGHT_N - lift                   # 地面正压力 N = W - L_total
        # 拉杆后潜在升力（含滚转喷管）足以克服重力 → 判定离地
        lift_potential = q * S_REF_M2 * CL_ROTATION + t_v + T_ROLLPOSTS_N
        if WEIGHT_N - lift_potential < 0:
            normal = 0.0
            airborne = True

        friction = MU * normal if not airborne else 0.0  # 地面摩擦力 μ·N
        accel = (t_h - drag - friction) / MASS_KG   # 水平加速度 a = (T_h - D - F) / m

        history['t'].append(t)
        history['x'].append(x)
        history['v_gs'].append(v_gs)
        history['v_air'].append(v_air)
        history['normal'].append(normal)
        history['a'].append(accel)
        history['t_h'].append(t_h)
        history['t_v'].append(t_v)

        v_gs = max(v_gs + accel * dt, 0.0)
        x += v_gs * dt
        t += dt

        if not airborne:
            min_plume_trailing_edge_m = update_min_plume_trailing_edge_m(
                x, np.degrees(nozzle_rad), V_WIND_MPS, min_plume_trailing_edge_m)

    for key in history:
        history[key] = np.array(history[key])
    return history, airborne, min_plume_trailing_edge_m if min_plume_trailing_edge_m is not None else 0.0


def simulate_strategy_b(nozzle_fixed_deg, dt=DT_DEFAULT):
    """策略 B：全程固定喷口偏转角。"""
    nozzle_rad = np.radians(nozzle_fixed_deg)
    v_gs, x, t = 0.0, 0.0, 0.0
    airborne = False
    min_plume_trailing_edge_m = None
    history = {k: [] for k in ('t', 'x', 'v_gs', 'v_air', 'normal', 'a', 't_h', 't_v')}

    while t < MAX_SIM_TIME_S and x < MAX_RUNWAY_M:
        v_air = v_gs + V_WIND_MPS
        t_h = T_MAIN_GROUND_N * np.cos(nozzle_rad)
        t_v = T_MAIN_GROUND_N * np.sin(nozzle_rad) + T_LIFTFAN_N
        q = dynamic_pressure(v_air)
        lift = q * S_REF_M2 * CL_TAXI + t_v
        drag = q * S_REF_M2 * (CD0 + K_IND * CL_TAXI ** 2 * PHI_GROUND)
        normal = WEIGHT_N - lift
        lift_potential = q * S_REF_M2 * CL_ROTATION + t_v + T_ROLLPOSTS_N
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

        v_gs = max(v_gs + accel * dt, 0.0)
        x += v_gs * dt
        t += dt

        if not airborne:
            min_plume_trailing_edge_m = update_min_plume_trailing_edge_m(
                x, nozzle_fixed_deg, V_WIND_MPS, min_plume_trailing_edge_m)

    for key in history:
        history[key] = np.array(history[key])
    return history, airborne, min_plume_trailing_edge_m if min_plume_trailing_edge_m is not None else 0.0


def _ground_forces_flat(v_gs, nozzle_deg):
    """平直甲板单步前力与离地判定（策略 C 共用）。"""
    v_air = v_gs + V_WIND_MPS
    nozzle_rad = np.radians(nozzle_deg)
    t_h = T_MAIN_GROUND_N * np.cos(nozzle_rad)
    t_v = T_MAIN_GROUND_N * np.sin(nozzle_rad) + T_LIFTFAN_N
    q = dynamic_pressure(v_air)
    lift = q * S_REF_M2 * CL_TAXI + t_v
    drag = q * S_REF_M2 * (CD0 + K_IND * CL_TAXI ** 2 * PHI_GROUND)
    normal = WEIGHT_N - lift
    lift_potential = q * S_REF_M2 * CL_ROTATION + t_v + T_ROLLPOSTS_N
    airborne = WEIGHT_N - lift_potential < 0
    if airborne:
        normal = 0.0
    friction = MU * normal if not airborne else 0.0
    accel = (t_h - drag - friction) / MASS_KG
    return accel, airborne


def simulate_strategy_c(min_safe_distance_m, dt=DT_DEFAULT):
    """
    策略 C：全程满足 min(x − 安全距离) ≥ min_safe_distance_m；
    每步可选减小喷口或保持，DP 求最短离地距离。
    """
    if min_safe_distance_m >= 0:
        raise ValueError("min_safe_distance_m 必须为负值")

    rate_step = NOZZLE_RATE_DEG_S * dt
    init_nozzle = calc_min_nozzle_deg_for_plume(0.0, min_safe_distance_m, V_WIND_MPS)
    states = {round(init_nozzle, 2): (0.0, 0.0, 0.0)}
    best = None
    min_plume_trailing_edge_m = None

    for _ in range(int(MAX_SIM_TIME_S / dt)):
        if not states:
            break
        new_states = {}
        for nozzle_deg, (v_gs, x, t) in states.items():
            if x >= MAX_RUNWAY_M:
                continue

            nozzle_min = calc_min_nozzle_deg_for_plume(x, min_safe_distance_m, V_WIND_MPS)
            nozzle_deg = max(nozzle_deg, nozzle_min)

            _, airborne_now = _ground_forces_flat(v_gs, nozzle_deg)
            if airborne_now:
                candidate = dict(
                    x_m=x, v_gs_mps=v_gs, v_air_mps=v_gs + V_WIND_MPS, t_s=t,
                    nozzle_deg=nozzle_deg,
                    min_plume_trailing_edge_m=min_plume_trailing_edge_m if min_plume_trailing_edge_m is not None else 0.0,
                )
                if best is None or x < best['x_m']:
                    best = candidate
                continue

            for decrease in (False, True):
                n2 = nozzle_deg - rate_step if decrease else nozzle_deg
                if decrease and n2 < nozzle_min - 1e-9:
                    continue
                n2 = max(n2, nozzle_min)

                accel, airborne = _ground_forces_flat(v_gs, n2)
                v2 = max(v_gs + accel * dt, 0.0)
                x2 = x + v2 * dt
                t2 = t + dt

                if not airborne:
                    min_plume_trailing_edge_m = update_min_plume_trailing_edge_m(
                        x2, n2, V_WIND_MPS, min_plume_trailing_edge_m)

                if airborne:
                    candidate = dict(
                        x_m=x2, v_gs_mps=v2, v_air_mps=v2 + V_WIND_MPS, t_s=t2,
                        nozzle_deg=n2,
                        min_plume_trailing_edge_m=min_plume_trailing_edge_m if min_plume_trailing_edge_m is not None else 0.0,
                    )
                    if best is None or x2 < best['x_m']:
                        best = candidate
                else:
                    key = round(n2, 2)
                    if key not in new_states or v2 > new_states[key][0]:
                        new_states[key] = (v2, x2, t2)
        states = new_states

    return best


def evaluate_liftoff(history, min_plume_trailing_edge_m):
    """从仿真历史提取离地指标，无法离地则返回 None。"""
    idx = find_liftoff_index(history['normal'])
    if idx is None:
        return None
    return dict(
        x_m=history['x'][idx],
        v_gs_mps=history['v_gs'][idx],
        v_air_mps=history['v_air'][idx],
        t_s=history['t'][idx],
        min_plume_trailing_edge_m=min_plume_trailing_edge_m,
        idx=idx,
        history=history,
    )


def search_strategy_a():
    best = None
    for nozzle_deg in range(NOZZLE_FINAL_DEG_START, NOZZLE_FINAL_DEG_END + 1, NOZZLE_FINAL_DEG_STEP):
        for v_trans in range(V_TRANS_START_MPS, V_TRANS_END_MPS + 1, V_TRANS_STEP_MPS):
            hist, _, max_plume_m = simulate_strategy_a(v_trans, nozzle_deg)
            lo = evaluate_liftoff(hist, max_plume_m)
            if lo and (best is None or lo['x_m'] < best['x_m']):
                best = dict(nozzle_deg=nozzle_deg, v_trans_mps=v_trans, **lo)
    return best


def fine_tune_strategy_a(coarse_best):
    best = coarse_best.copy()
    for nozzle_deg in fine_range_symmetric(
            coarse_best['nozzle_deg'], NOZZLE_FINAL_DEG_STEP, FINE_SEARCH_STEP):
        for v_trans in fine_range_symmetric(
                coarse_best['v_trans_mps'], V_TRANS_STEP_MPS, FINE_SEARCH_STEP,
                min_val=0):
            hist, _, max_plume_m = simulate_strategy_a(v_trans, nozzle_deg)
            lo = evaluate_liftoff(hist, max_plume_m)
            if lo and lo['x_m'] < best['x_m']:
                best = dict(nozzle_deg=nozzle_deg, v_trans_mps=v_trans, **lo)
    return best


def search_strategy_b():
    best = None
    for nozzle_deg in range(NOZZLE_B_DEG_START, NOZZLE_B_DEG_END + 1, NOZZLE_B_DEG_STEP):
        hist, _, max_plume_m = simulate_strategy_b(nozzle_deg)
        lo = evaluate_liftoff(hist, max_plume_m)
        if lo and (best is None or lo['x_m'] < best['x_m']):
            best = dict(nozzle_deg=nozzle_deg, **lo)
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
    """策略 C（尾流约束 DP），返回最优结果 dict 或 None。"""
    return simulate_strategy_c(MIN_SAFE_DISTANCE_M)


def _main():
    print_config_summary()

    print("\n" + "=" * 60)
    print(f"策略 A：起飞前偏转喷口（{WIND_KT} kt 甲板风）")
    print("=" * 60)

    best_a = search_strategy_a()
    if best_a:
        print(f"\n粗搜索最优:")
        print(f"  喷管最终角:   {best_a['nozzle_deg']}°")
        print(f"  开始偏转地速: {best_a['v_trans_mps']} m/s ({best_a['v_trans_mps'] * MPS_TO_KT:.0f} kt)")
        print(f"  离地距离:     {best_a['x_m']:.1f} m ({best_a['x_m'] * M_TO_FT:.0f} ft)")
        print(f"  离地地速:     {best_a['v_gs_mps']:.1f} m/s ({best_a['v_gs_mps'] * MPS_TO_KT:.0f} kt)")
        print(f"  离地空速:     {best_a['v_air_mps']:.1f} m/s ({best_a['v_air_mps'] * MPS_TO_KT:.0f} kt)")
        print(f"  离地时间:     {best_a['t_s']:.2f} s")
        print(f"  甲板受影响最后缘: {best_a['min_plume_trailing_edge_m']:.1f} m")

        print("\n细化搜索 …")
        best_a = fine_tune_strategy_a(best_a)
        print(f"\n★ 细化最优: 喷管角 {best_a['nozzle_deg']}°，转换地速 {best_a['v_trans_mps']} m/s "
              f"({best_a['v_trans_mps'] * MPS_TO_KT:.0f} kt)")
        print(f"  离地距离: {best_a['x_m']:.1f} m ({best_a['x_m'] * M_TO_FT:.0f} ft)")
        print(f"  离地总时间: {best_a['t_s']:.2f} s | 甲板受影响最后缘 {best_a['min_plume_trailing_edge_m']:.1f} m")

    print("\n" + "=" * 60)
    print(f"策略 B：全程固定喷口（{WIND_KT} kt 甲板风）")
    print("=" * 60)

    best_b = search_strategy_b()
    if best_a and best_b:
        diff_m = best_b['x_m'] - best_a['x_m']
        print(f"\n策略 B 最优: 固定 {best_b['nozzle_deg']}°，离地 {best_b['x_m']:.1f} m")
        print(f"  离地总时间 {best_b['t_s']:.2f} s | 甲板受影响最后缘 {best_b['min_plume_trailing_edge_m']:.1f} m")
        print(f"策略 A 最优: 转换地速 {best_a['v_trans_mps']} m/s，离地 {best_a['x_m']:.1f} m")
        print(f"  离地总时间 {best_a['t_s']:.2f} s | 甲板受影响最后缘 {best_a['min_plume_trailing_edge_m']:.1f} m")
        print(f"策略 A 比 B 短: {diff_m:.1f} m ({diff_m / best_b['x_m'] * 100:.1f}%)")

    print("\n" + "=" * 60)
    print(f"策略 C：尾流约束 min(x−安全距离) ≥ {MIN_SAFE_DISTANCE_M:.0f} m（{WIND_KT} kt 甲板风）")
    print("=" * 60)

    init_nozzle_c = calc_min_nozzle_deg_for_plume(0.0, MIN_SAFE_DISTANCE_M, V_WIND_MPS)
    print(f"起始喷管角（x=0 反推）: {init_nozzle_c:.1f}°")

    best_c = simulate_strategy_c(MIN_SAFE_DISTANCE_M)
    if best_c:
        print(f"\n★ 策略 C 最优: 离地 {best_c['x_m']:.1f} m ({best_c['x_m'] * M_TO_FT:.0f} ft)")
        print(f"  离地喷管角:   {best_c['nozzle_deg']:.1f}°")
        print(f"  离地地速:     {best_c['v_gs_mps']:.1f} m/s ({best_c['v_gs_mps'] * MPS_TO_KT:.0f} kt)")
        print(f"  离地空速:     {best_c['v_air_mps']:.1f} m/s ({best_c['v_air_mps'] * MPS_TO_KT:.0f} kt)")
        print(f"  离地总时间:   {best_c['t_s']:.2f} s")
        print(f"  甲板受影响最后缘: {best_c['min_plume_trailing_edge_m']:.1f} m")
        if best_a and best_b:
            print(f"  比策略 A 长: {best_c['x_m'] - best_a['x_m']:.1f} m | 比策略 B 长: {best_c['x_m'] - best_b['x_m']:.1f} m")
    else:
        print("\n策略 C 未能离地")


if __name__ == "__main__":
    _main()
