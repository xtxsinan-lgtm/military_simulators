"""固定翼舰载机滑跃起飞仿真（以歼-15 为气动参考）。

滑跃段为圆弧：入口切线水平，出口切线角 = 资料滑跃角；见 ski_jump_geometry。
不计算主喷管尾流波及（该模型仅用于 VTOL/STOVL，见 utils.takeoff.exhaust_plume）。
"""
from __future__ import annotations

import numpy as np

from utils.takeoff.deck_config import assign_ski_jump_globals, total_takeoff_distance_m as _total_takeoff_distance_m
from utils.takeoff.propeller_thrust import (
    DEFAULT_FIGURE_OF_MERIT,
    DEFAULT_NACELLE_BLOCKAGE_FRAC,
    calc_prop_disk_area_m2,
    calc_propeller_thrust_n,
)
from utils.takeoff.search_utils import fine_range_deck, fine_range_symmetric
from utils.takeoff.sim_config import apply_wind_knots_globals
from utils.takeoff.ski_jump_geometry import SkiJumpArc, compute_ski_jump_arc, deck_angle_deg_at_s, deck_cos_sin_at_s, deck_height_at_s
from utils.takeoff.trajectory import TrajectoryRecorder
from utils.takeoff.takeoff_config import cfg_range, mode_config, shared_config
from utils.takeoff.takeoff_physics import (
    FLAP_DEFLECTION_DEG,
    FLAP_EFFICIENCY,
    G,
    KT_TO_MPS,
    MPS_TO_KT,
    M_TO_FT,
    PITCH_MAX_DEG,
    T_THRUST_REF_C,
    WING_INCIDENCE_DEG,
    calc_cl_alpha,
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
_MODE = mode_config('ski_jump')
_REF = _MODE['reference_aircraft']
_SEARCH = _MODE['search']

# ---------------------------------------------------------------------------
# 大气与温度（推力在 T_THRUST_REF_C 海平面标定）
# ---------------------------------------------------------------------------
AMBIENT_TEMP_C = float(_MODE['ambient_temp_c'])

RHO = calc_sea_level_density_kg_m3(AMBIENT_TEMP_C)
THRUST_TEMP_FACTOR = calc_thrust_temp_factor(AMBIENT_TEMP_C)

# ---------------------------------------------------------------------------
# 飞机参数（参考默认值，Web 仿真前由 apply_aircraft_geometry 覆盖）
# ---------------------------------------------------------------------------
MASS_KG = float(_REF['mass_kg'])
WEIGHT_N = MASS_KG * G
S_REF_M2 = float(_REF['s_ref_m2'])
WINGSPAN_M = float(_REF['wingspan_m'])
WING_HEIGHT_M = float(_REF['wing_height_m'])
ASPECT_RATIO = WINGSPAN_M ** 2 / S_REF_M2
T_MAX_SL_N = float(_REF['t_max_sl_n'])
T_MAX_N = T_MAX_SL_N * THRUST_TEMP_FACTOR
CD0 = float(_REF['cd0'])

# 涡桨恒定功率：有轴功率与桨盘时，推力随空速由动量理论给出；否则用上面的恒定推力
SHAFT_POWER_SL_W = 0.0
PROP_DIAMETER_M = 0.0
N_ROTORS = 2
NACELLE_BLOCKAGE_FRAC = DEFAULT_NACELLE_BLOCKAGE_FRAC
FIGURE_OF_MERIT = DEFAULT_FIGURE_OF_MERIT
PROP_DISK_AREA_M2 = 0.0
SHAFT_POWER_W = 0.0

SWEEP_LE_DEG = float(_REF['sweep_le_deg'])

SKI_JUMP_ANGLE_DEG = float(_MODE['ski_jump_angle_deg'])
SKI_JUMP_ARC: SkiJumpArc = compute_ski_jump_arc(SKI_JUMP_ANGLE_DEG)
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

_PITCH = _SEARCH['pitch_deg']
PITCH_SEARCH_MIN = _PITCH['start']
PITCH_SEARCH_MAX = _PITCH['end'] - 1
PITCH_SEARCH_STEP = _PITCH['step']
_FLAT = _SEARCH['flat_length_m']
FLAT_SEARCH_MAX_M = _FLAT['end'] - 1
FLAT_SEARCH_STEP_M = _FLAT['step']
FINE_SEARCH_STEP = int(_SHARED['fine_search_step'])
# ---------------------------------------------------------------------------
# 气动参数（计算值）
# ---------------------------------------------------------------------------
TAXI_ALPHA_DEG = taxi_alpha_deg()


def recompute_aero_parameters():
    global ASPECT_RATIO, WEIGHT_N, OSWALD_E, K_IND, CL_ALPHA, PHI_GROUND_FLAT, CL_TAXI
    ASPECT_RATIO = WINGSPAN_M ** 2 / S_REF_M2
    WEIGHT_N = MASS_KG * G
    OSWALD_E = calc_oswald_e(ASPECT_RATIO, SWEEP_LE_DEG)
    K_IND = 1 / (np.pi * ASPECT_RATIO * OSWALD_E)
    CL_ALPHA = calc_cl_alpha(ASPECT_RATIO, OSWALD_E, SWEEP_LE_DEG)
    PHI_GROUND_FLAT = calc_ground_effect_phi(WING_HEIGHT_M, WINGSPAN_M)
    CL_TAXI = calc_cl_from_alpha_deg(TAXI_ALPHA_DEG, CL_ALPHA)


def apply_thrust_temperature(ambient_temp_c):
    global AMBIENT_TEMP_C, RHO, THRUST_TEMP_FACTOR, T_MAX_N, SHAFT_POWER_W
    AMBIENT_TEMP_C = ambient_temp_c
    RHO = calc_sea_level_density_kg_m3(ambient_temp_c)
    THRUST_TEMP_FACTOR = calc_thrust_temp_factor(ambient_temp_c)
    T_MAX_N = T_MAX_SL_N * THRUST_TEMP_FACTOR
    SHAFT_POWER_W = SHAFT_POWER_SL_W * THRUST_TEMP_FACTOR


def apply_wind_knots(wind_kt):
    apply_wind_knots_globals(wind_kt, globals())


def uses_propeller_power_model() -> bool:
    """当前模块是否按恒定轴功率计算滑跃推力。"""
    return SHAFT_POWER_SL_W > 0 and PROP_DIAMETER_M > 0 and PROP_DISK_AREA_M2 > 0


def apply_propulsion_sl(
    shaft_power_sl_w: float | None = None,
    prop_diameter_m: float | None = None,
    nacelle_blockage_frac: float | None = None,
    figure_of_merit: float | None = None,
    n_rotors: int = 2,
):
    """设置涡桨海平面轴功率与桨盘；功率或直径为空则退回恒定喷气推力。"""
    global SHAFT_POWER_SL_W, PROP_DIAMETER_M, N_ROTORS, PROP_DISK_AREA_M2
    global NACELLE_BLOCKAGE_FRAC, FIGURE_OF_MERIT
    power = float(shaft_power_sl_w or 0.0)
    diam = float(prop_diameter_m or 0.0)
    SHAFT_POWER_SL_W = power
    PROP_DIAMETER_M = diam
    N_ROTORS = int(n_rotors)
    if nacelle_blockage_frac is not None:
        NACELLE_BLOCKAGE_FRAC = float(nacelle_blockage_frac)
    else:
        NACELLE_BLOCKAGE_FRAC = DEFAULT_NACELLE_BLOCKAGE_FRAC
    if figure_of_merit is not None:
        FIGURE_OF_MERIT = float(figure_of_merit)
    else:
        FIGURE_OF_MERIT = DEFAULT_FIGURE_OF_MERIT
    if power > 0 and diam > 0:
        PROP_DISK_AREA_M2 = calc_prop_disk_area_m2(PROP_DIAMETER_M, N_ROTORS)
    else:
        SHAFT_POWER_SL_W = 0.0
        PROP_DIAMETER_M = 0.0
        PROP_DISK_AREA_M2 = 0.0
    apply_thrust_temperature(AMBIENT_TEMP_C)


def apply_aircraft_geometry(mass_kg, s_ref_m2, wingspan_m, wing_height_m, sweep_le_deg, cd0, t_max_sl_n):
    global MASS_KG, S_REF_M2, WINGSPAN_M, WING_HEIGHT_M, SWEEP_LE_DEG, CD0, T_MAX_SL_N
    MASS_KG = mass_kg
    S_REF_M2 = s_ref_m2
    WINGSPAN_M = wingspan_m
    WING_HEIGHT_M = wing_height_m
    SWEEP_LE_DEG = sweep_le_deg
    CD0 = cd0
    T_MAX_SL_N = t_max_sl_n
    # 喷气机默认；涡桨须在此后再调用 apply_propulsion_sl，避免上一机残留功率模型
    apply_propulsion_sl(0.0, 0.0)
    apply_thrust_temperature(AMBIENT_TEMP_C)
    recompute_aero_parameters()


def current_thrust_n(v_air_mps: float) -> float:
    """当前空速下的可用推力：涡桨为恒定功率动量理论，喷气为恒定推力。"""
    if uses_propeller_power_model():
        return calc_propeller_thrust_n(
            SHAFT_POWER_W,
            RHO,
            PROP_DISK_AREA_M2,
            v_axial_mps=max(float(v_air_mps), 0.0),
            figure_of_merit=FIGURE_OF_MERIT,
            nacelle_blockage_frac=NACELLE_BLOCKAGE_FRAC,
        )
    return T_MAX_N


def apply_ski_jump_deck(angle_deg, lip_height_m=None):
    """设置圆弧滑跃甲板；仅需出口切线角，可选唇口高度定半径。"""
    assign_ski_jump_globals(globals(), angle_deg, lip_height_m=lip_height_m)


recompute_aero_parameters()

DT_DEFAULT = float(_MODE['dt_default'])
MAX_GROUND_TIME_S = float(_MODE['max_ground_time_s'])
MAX_AIR_TIME_S = float(_MODE['max_air_time_s'])
CL_MAX = float(_MODE['cl_max'])


def print_config_summary():
    print(f"环境温度:     {AMBIENT_TEMP_C:.0f} °C (推力标定 {T_THRUST_REF_C:.0f} °C)")
    print(f"空气密度 ρ:   {RHO:.4f} kg/m³ | 推力温度系数 {THRUST_TEMP_FACTOR:.4f}")
    if uses_propeller_power_model():
        t0 = current_thrust_n(0.0)
        print(f"轴功率:       {SHAFT_POWER_W/1e6:.2f} MW（{T_THRUST_REF_C:.0f}°C 标定 {SHAFT_POWER_SL_W/1e6:.2f} MW）")
        print(f"桨盘:         {N_ROTORS}×⌀{PROP_DIAMETER_M:.2f} m，总面积 {PROP_DISK_AREA_M2:.1f} m²")
        print(f"静推力估计:   {t0/1000:.1f} kN（恒定功率，推力随空速下降）")
    else:
        print(f"实际加力推力({AMBIENT_TEMP_C:.0f}°C SL): {T_MAX_N/1000:.1f} kN"
              f"（{T_THRUST_REF_C:.0f}°C 标定 {T_MAX_SL_N/1000:.1f} kN）")
    print(f"起飞重量:     {MASS_KG:,} kg")
    print(f"展弦比 AR:    {ASPECT_RATIO:.3f}")
    print(f"甲板风:       {WIND_KT} kt ({V_WIND_MPS:.2f} m/s)")
    print(f"地面效应 φ:   {PHI_GROUND_FLAT:.3f}")
    print(f"Oswald η:     {OSWALD_E:.4f}")
    print(f"诱导因子 k:   {K_IND:.3f}")
    print(f"C_Lα:         {CL_ALPHA:.4f} /rad  (Λ={SWEEP_LE_DEG}°)")
    print(f"Cl_taxi:      {CL_TAXI:.4f}")
    print(f"滑跃圆弧:     {SKI_JUMP_ANGLE_DEG:.1f}° 出口 | R={SKI_JUMP_RADIUS_M:.0f} m | "
          f"弧长 {SKI_JUMP_ARC_LENGTH_M:.1f} m | 水平 {SKI_JUMP_HORIZONTAL_M:.1f} m")


def total_takeoff_distance_m(flat_length_m):
    return _total_takeoff_distance_m(flat_length_m, SKI_JUMP_HORIZONTAL_M)


def dynamic_pressure(airspeed_mps):
    """动压 q = ½·ρ·V²，Pa"""
    return _dynamic_pressure(RHO, airspeed_mps)


def drag_coefficient(cl, phi_ground):
    """阻力系数 Cd = Cd0 + k·Cl²·φ（含地面效应修正）"""
    return _drag_coefficient(CD0, K_IND, cl, phi_ground)


def simulate(flat_length_m, pitch_deg, dt=DT_DEFAULT, max_time_s=MAX_GROUND_TIME_S,
             trajectory: list | None = None):
    """
    固定翼滑跃起飞全过程仿真。

    返回: (success, x_deck, v_deck, vy_final, min_vy, t_deck, final_lift_n)
    若传入 trajectory 列表，则按间隔写入 {'x','y','t','phase'} 轨迹点。
    """
    check_pitch_deg(pitch_deg)
    v_gs, x, t = 0.0, 0.0, 0.0
    y = 0.0
    rec = TrajectoryRecorder(trajectory)
    rec.record(x, y, t, 'flat', force=True)

    # ==================== 阶段 1：平直甲板滑跑 ====================
    while x < flat_length_m and t < max_time_s:
        v_air = v_gs + V_WIND_MPS
        q = dynamic_pressure(v_air)
        lift = q * S_REF_M2 * CL_TAXI
        drag = q * S_REF_M2 * drag_coefficient(CL_TAXI, PHI_GROUND_FLAT)
        normal = max(WEIGHT_N - lift, 0.0)
        thrust = current_thrust_n(v_air)
        v_gs = max(v_gs + (thrust - drag - MU * normal) / MASS_KG * dt, 0.0)
        x += v_gs * dt
        t += dt
        rec.record(x, y, t, 'flat')

    rec.record(x, y, t, 'flat', force=True)

    # ==================== 阶段 2：滑跃圆弧段 ====================
    s = 0.0
    while s < SKI_JUMP_ARC_LENGTH_M and t < max_time_s:
        cos_p, sin_p = deck_cos_sin_at_s(s, SKI_JUMP_ARC)
        v_air = v_gs + V_WIND_MPS * cos_p
        q = dynamic_pressure(v_air)
        phi_s = PHI_GROUND_FLAT * (1 - s / SKI_JUMP_ARC_LENGTH_M) + s / SKI_JUMP_ARC_LENGTH_M
        lift = q * S_REF_M2 * CL_TAXI
        drag = q * S_REF_M2 * drag_coefficient(CL_TAXI, phi_s)
        normal = max(WEIGHT_N * cos_p - lift, 0.0)
        thrust = current_thrust_n(v_air)
        v_gs = max(v_gs + (thrust - drag - WEIGHT_N * sin_p - MU * normal) / MASS_KG * dt, 0.0)
        s += v_gs * dt
        x += v_gs * cos_p * dt
        y = deck_height_at_s(s, SKI_JUMP_ARC)
        t += dt
        rec.record(x, y, t, 'arc')

    if s < SKI_JUMP_ARC_LENGTH_M * 0.99:
        return False, x, v_gs, 0.0, 0.0, t, 0.0

    v_deck = v_gs
    vx = v_gs * SKI_JUMP_COS
    vy = v_gs * SKI_JUMP_SIN
    x_deck, t_deck = x, t
    y_deck = y
    min_vy = vy
    rec.record(x_deck, y_deck, t_deck, 'deck_exit', force=True)
    if vy <= 0:
        return False, x_deck, v_deck, vy, min_vy, t_deck, 0.0

    # ==================== 阶段 3：离甲板后自由飞行 ====================
    pitch_rad = np.radians(pitch_deg)
    t_air = 0.0
    final_lift_n = 0.0
    x_air, y_air = x_deck, y_deck

    while t_air < MAX_AIR_TIME_S and t < max_time_s:
        rec.record(x_air, y_air, t, 'air')
        v_spd = np.hypot(vx, vy)
        gamma = np.arctan2(vy, vx) if v_spd > 0.1 else 0.0
        v_air = np.hypot(vx + V_WIND_MPS, vy)
        q = dynamic_pressure(v_air)
        alpha_eff = pitch_rad - gamma
        cl = np.clip(CL_TAXI + CL_ALPHA * alpha_eff, 0.0, CL_MAX)
        lift = q * S_REF_M2 * cl
        drag = q * S_REF_M2 * (CD0 + K_IND * cl * cl)
        final_lift_n = lift

        sin_g, cos_g = np.sin(gamma), np.cos(gamma)
        thrust = current_thrust_n(v_air)
        dvx = (thrust - lift * sin_g - drag * cos_g) / MASS_KG
        dvy = (lift * cos_g - drag * sin_g - WEIGHT_N) / MASS_KG
        vx += dvx * dt
        vy += dvy * dt
        x_air += vx * dt
        y_air += vy * dt
        t_air += dt
        t += dt
        min_vy = min(min_vy, vy)

        if vy <= 0:
            rec.record(x_air, y_air, t, 'air', force=True)
            return False, x_deck, v_deck, vy, min_vy, t_deck, final_lift_n
        if lift >= WEIGHT_N * 0.95 and vy > 1.0 and t_air > 0.5:
            rec.record(x_air, y_air, t, 'air', force=True)
            break

    return True, x_deck, v_deck, vy, min_vy, t_deck, final_lift_n


def best_pitch_for_flat(flat_m, pitch_values):
    """给定平直段长度，返回 (pitch_deg, min_vy, sim_result) 或 None。"""
    best = None
    for pitch_deg in pitch_values:
        if pitch_deg > PITCH_MAX_DEG:
            continue
        ok, x_deck, v_deck, vy_final, min_vy, t_deck, final_lift = simulate(flat_m, pitch_deg)
        if ok and (best is None or min_vy > best[1]):
            best = (pitch_deg, min_vy, (ok, x_deck, v_deck, vy_final, min_vy, t_deck, final_lift))
    return best


def _coarse_flat_pitch_search():
    """粗搜平直段 + 俯仰角，返回最优 dict 或 None。"""
    best_overall = None
    pitch_values = range(PITCH_SEARCH_MIN, PITCH_SEARCH_MAX + 1, PITCH_SEARCH_STEP)
    for flat_m in range(0, FLAT_SEARCH_MAX_M + 1, FLAT_SEARCH_STEP_M):
        result = best_pitch_for_flat(flat_m, pitch_values)
        if not result:
            continue
        pitch_deg, min_vy, sim = result
        _, x_deck, v_deck, _, _, t_deck, _ = sim
        total_m = total_takeoff_distance_m(flat_m)
        if best_overall is None or total_m < best_overall['total_m']:
            best_overall = dict(total_m=total_m, flat_m=flat_m, pitch_deg=pitch_deg,
                                min_vy_mps=min_vy, t_deck_s=t_deck, v_deck_mps=v_deck,
                                x_deck_m=x_deck, sim=sim)
    return best_overall


def _fine_flat_pitch_search(best_overall):
    """精搜：平直段仅向更短方向；俯仰角 ± 粗搜步长。"""
    refined = best_overall
    pitch_range = fine_range_symmetric(
        best_overall['pitch_deg'], PITCH_SEARCH_STEP, FINE_SEARCH_STEP,
        min_val=PITCH_SEARCH_MIN, max_val=PITCH_SEARCH_MAX)
    for flat_m in fine_range_deck(best_overall['flat_m'], FLAT_SEARCH_STEP_M, FINE_SEARCH_STEP):
        result = best_pitch_for_flat(flat_m, pitch_range)
        if not result:
            continue
        pitch_deg, min_vy, sim = result
        _, x_deck, v_deck, _, _, t_deck, _ = sim
        total_m = total_takeoff_distance_m(flat_m)
        if total_m < refined['total_m']:
            refined = dict(total_m=total_m, flat_m=flat_m, pitch_deg=pitch_deg,
                           min_vy_mps=min_vy, t_deck_s=t_deck, v_deck_mps=v_deck,
                           x_deck_m=x_deck, sim=sim)
    return refined


def search_flat_length():
    best_overall = None
    print("=" * 70)
    print("扫描最小平直段（同步搜索最优俯仰角）")
    print("=" * 70)

    pitch_values = range(PITCH_SEARCH_MIN, PITCH_SEARCH_MAX + 1, PITCH_SEARCH_STEP)
    for flat_m in range(0, FLAT_SEARCH_MAX_M + 1, FLAT_SEARCH_STEP_M):
        result = best_pitch_for_flat(flat_m, pitch_values)
        total_m = total_takeoff_distance_m(flat_m)
        if result:
            pitch_deg, min_vy, sim = result
            _, x_deck, v_deck, _, _, t_deck, _ = sim
            status = f"✓ 成功 | 俯仰角 {pitch_deg}° | 最小 Vy {min_vy:.2f} m/s"
            if best_overall is None or total_m < best_overall['total_m']:
                best_overall = dict(total_m=total_m, flat_m=flat_m, pitch_deg=pitch_deg,
                                    min_vy_mps=min_vy, t_deck_s=t_deck, v_deck_mps=v_deck,
                                    x_deck_m=x_deck, sim=sim)
        else:
            status = "✗ 失败"
        print(f"  平直段 {flat_m:3d} m | 总距 {total_m:6.1f} m | {status}")

    if best_overall:
        print(f"\n  粗搜索最优: 平直段 {best_overall['flat_m']} m，"
              f"总距 {best_overall['total_m']:.1f} m，俯仰角 {best_overall['pitch_deg']}°")
        print("  细化搜索 …")
        refined = _fine_flat_pitch_search(best_overall)
        if refined['total_m'] < best_overall['total_m']:
            best_overall = refined
    return best_overall


def run_min_takeoff_search():
    """最小起飞总距离搜索（粗搜 + 细化），无控制台输出。"""
    best_overall = _coarse_flat_pitch_search()
    if not best_overall:
        return None
    return _fine_flat_pitch_search(best_overall)


def print_best_result(best):
    if not best:
        print("  未找到可行解。")
        return
    sim = best.get('sim')
    if sim:
        _, x_deck, v_deck, _, min_vy, t_deck, final_lift = sim
    else:
        ok, x_deck, v_deck, _, min_vy, t_deck, final_lift = simulate(best['flat_m'], best['pitch_deg'])
        if not ok:
            print("  未找到可行解。")
            return

    print("\n" + "=" * 70)
    print("最优结果")
    print("=" * 70)
    print(f"  最小平直段:     {best['flat_m']:.0f} m")
    print(f"  总起飞距离:     {best['total_m']:.1f} m ({best['total_m'] * M_TO_FT:.0f} ft)")
    print(f"  最优俯仰角:     {best['pitch_deg']}°")
    print(f"  离甲板速度:     {v_deck:.1f} m/s ({v_deck * MPS_TO_KT:.0f} kt)")
    print(f"  离甲板 Vy:      {v_deck * SKI_JUMP_SIN:.1f} m/s")
    print(f"  最小 Vy:        {min_vy:.2f} m/s")
    print(f"  离甲板总时间:   {t_deck:.2f} s")
    print(f"  最终升力:       {final_lift / 1000:.1f} kN  (W = {WEIGHT_N / 1000:.1f} kN, L/W = {final_lift / WEIGHT_N:.2f})")
    v_stall = np.sqrt(2 * WEIGHT_N / (RHO * S_REF_M2 * 1.4))  # 失速速度 V_s = √(2W/(ρ·S·Cl_max))
    print(f"\n  参考失速速度:   {v_stall:.1f} m/s ({v_stall * MPS_TO_KT:.0f} kt, Cl=1.4)")
    print(f"  V_deck / V_stall: {v_deck / v_stall:.2f}")


def print_pitch_sensitivity(flat_m):
    print("\n" + "=" * 70)
    print(f"俯仰角敏感性（平直段 {flat_m} m）")
    print("=" * 70)
    print(f"  {'俯仰角':>6} | {'结果':>4} | {'V_deck':>10} | {'最小Vy':>8} | {'L/W':>8}")
    print("  " + "-" * 52)
    for pitch_deg in range(5, PITCH_MAX_DEG + 1, 2):
        ok, _, v_deck, _, min_vy, _, final_lift = simulate(flat_m, pitch_deg)
        result = "成功" if ok else "失败"
        lw = final_lift / WEIGHT_N if final_lift > 0 else 0.0
        print(f"  {pitch_deg:>5}° | {result:>4} | {v_deck:>8.1f} m/s | {min_vy:>8.2f} | {lw:>8.2f}")


def _main():
    print_config_summary()
    best = search_flat_length()
    print_best_result(best)
    if best:
        print_pitch_sensitivity(best['flat_m'])


if __name__ == "__main__":
    _main()
