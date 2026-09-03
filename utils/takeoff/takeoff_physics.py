"""Shared atmosphere, aero, units, and flight-limit helpers for carrier takeoff simulators."""
import numpy as np

from utils.takeoff.takeoff_config import physics_config

_PHYS = physics_config()

# ---------------------------------------------------------------------------
# Atmosphere / thrust temperature reference
# ---------------------------------------------------------------------------
T_THRUST_REF_C = float(_PHYS['t_thrust_ref_c'])
RHO_ISA_KG_M3 = float(_PHYS['rho_isa_kg_m3'])
THRUST_TEMP_EXPONENT = float(_PHYS['thrust_temp_exponent'])

# ---------------------------------------------------------------------------
# Physical units
# ---------------------------------------------------------------------------
G = float(_PHYS['g'])
KT_TO_MPS = float(_PHYS['kt_to_mps'])
M_TO_FT = float(_PHYS['m_to_ft'])
MPS_TO_KT = float(_PHYS['mps_to_kt'])

# ---------------------------------------------------------------------------
# Flap / incidence defaults (STOVL & conventional)
# ---------------------------------------------------------------------------
FLAP_DEFLECTION_DEG = float(_PHYS['flap_deflection_deg'])
FLAP_EFFICIENCY = float(_PHYS['flap_efficiency'])
WING_INCIDENCE_DEG = float(_PHYS['wing_incidence_deg'])

# ---------------------------------------------------------------------------
# Flight limits
# ---------------------------------------------------------------------------
PITCH_MAX_DEG = int(_PHYS['pitch_max_deg'])

# 近距耦合鸭翼：起飞滑跑约 10–20°，净增升取孤立鸭翼升力的一半。
# Gloss / Hummel：小迎角下洗减主翼升力；中迎角翼上洗把鸭翼增量补回。
# DTIC ADA067122：低迎角增量升力 ≈ ½ 孤立鸭翼 CL。
# Stoll、Howard 的 20–34% 是失速 CLmax，不用于线性起飞段。
CANARD_LAYOUT = 'canard'
CANARD_LIFT_INTERFERENCE = float(_PHYS.get('canard_lift_interference', 0.5))


def calc_sea_level_density_kg_m3(ambient_temp_c, reference_temp_c=T_THRUST_REF_C):
    """海平面空气密度，kg/m³；同压强下 ρ ∝ 1/T。"""
    t_ref_k = reference_temp_c + 273.15
    t_amb_k = ambient_temp_c + 273.15
    return RHO_ISA_KG_M3 * t_ref_k / t_amb_k


def calc_thrust_temp_factor(ambient_temp_c, reference_temp_c=T_THRUST_REF_C,
                            exponent=THRUST_TEMP_EXPONENT):
    """相对 reference_temp_c 标定推力的温度衰减系数。"""
    t_ref_k = reference_temp_c + 273.15
    t_amb_k = ambient_temp_c + 273.15
    return (t_ref_k / t_amb_k) ** exponent


def calc_oswald_e(aspect_ratio, sweep_le_deg):
    """η = 4.61(1 - 0.045·AR^0.68)(cos Λ)^0.15 - 3.1"""
    sweep_rad = np.radians(sweep_le_deg)
    return 4.61 * (1 - 0.045 * aspect_ratio ** 0.68) * (np.cos(sweep_rad) ** 0.15) - 3.1


def calc_cl_alpha(aspect_ratio, oswald_e, sweep_le_deg):
    """C_Lα = 2π·AR / (2 + √(4 + (AR²/η²)(1 + tan²Λ)))，单位 /rad"""
    sweep_rad = np.radians(sweep_le_deg)
    denom = 2 + np.sqrt(4 + (aspect_ratio ** 2 / oswald_e ** 2) * (1 + np.tan(sweep_rad) ** 2))
    return 2 * np.pi * aspect_ratio / denom


def calc_cl_from_alpha_deg(alpha_deg, cl_alpha):
    return np.radians(alpha_deg) * cl_alpha


def calc_canard_lift_factor(layout, canard_area_m2, wing_area_m2,
                            interference=CANARD_LIFT_INTERFERENCE):
    """近距耦合鸭翼相对参考翼面积的净增升乘数（1 表示无鸭翼）。

    ΔCL/CL = k · (Sc / S_ref)，k 默认 0.5。
    非鸭式布局、缺面积时返回 1。
    """
    if (layout or '') != CANARD_LAYOUT:
        return 1.0
    s_c = float(canard_area_m2 or 0.0)
    s_w = float(wing_area_m2 or 0.0)
    if s_c <= 0.0 or s_w <= 0.0:
        return 1.0
    k = min(max(float(interference), 0.0), 1.0)
    return 1.0 + k * (s_c / s_w)


def calc_cl_alpha_with_canard(aspect_ratio, oswald_e, sweep_le_deg,
                              layout='conventional', canard_area_m2=0.0, wing_area_m2=0.0):
    """Helmbold C_Lα 再乘鸭翼净增升。"""
    cl_a = calc_cl_alpha(aspect_ratio, oswald_e, sweep_le_deg)
    return cl_a * calc_canard_lift_factor(layout, canard_area_m2, wing_area_m2)


def calc_ground_effect_phi(wing_height_m, wingspan_m):
    """Torenbeek 地面效应修正因子 φ。"""
    x = 16 * wing_height_m / wingspan_m
    return x * x / (1 + x * x)


def taxi_alpha_deg(fldef_deg=FLAP_DEFLECTION_DEG, flap_efficiency=FLAP_EFFICIENCY,
                   wing_incidence_deg=WING_INCIDENCE_DEG):
    """滑行等效迎角，°。"""
    return fldef_deg * flap_efficiency + wing_incidence_deg


def dynamic_pressure(rho, airspeed_mps):
    """动压 q = ½·ρ·V²，Pa"""
    return 0.5 * rho * airspeed_mps * airspeed_mps


def drag_coefficient(cd0, k_ind, cl, phi_ground):
    """阻力系数 Cd = Cd0 + k·Cl²·φ（含地面效应修正）"""
    return cd0 + k_ind * cl * cl * phi_ground


def check_pitch_deg(pitch_deg, pitch_max_deg=PITCH_MAX_DEG):
    """校验俯仰角不超过硬上限；超限则抛出 ValueError。"""
    if pitch_deg > pitch_max_deg:
        raise ValueError(f"俯仰角 {pitch_deg}° 超过硬上限 {pitch_max_deg}°")
    return pitch_deg


def wind_knots_to_mps(wind_kt, kt_to_mps=KT_TO_MPS):
    return wind_kt * kt_to_mps
