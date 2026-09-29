"""六类导弹的射程估算：超燃、亚燃、涡扇隐身、涡喷非隐身、亚超结合、弹道。

亚音速与冲压巡航用布雷盖航程；全高空与全掠海只改巡航高度、升阻比和耗油率。
冲压弹先用固体火箭助推到接力马赫数，再用剩余燃油巡航。
亚超结合在涡扇巡航之后加一段低空固体火箭冲刺。
普通弹道导弹沿用弹体装药估算，关机后取最大射程弹道。
"""
from __future__ import annotations

import math

from utils.missile_range.estimate import (
    DEFAULT_ISP_S,
    DEFAULT_PROPELLANT_DENSITY,
    G0,
    PROPELLANT_MASS_FRACTION,
    R_EARTH_M,
    gravity_drag_loss_m_s,
    head_and_booster_lengths_m,
    head_total_mass_kg,
    propellant_mass_kg,
)

LHV_J_KG = 43.0e6
BODY_PACK = 0.68
BOOST_FILL = 0.76
TERMINAL_FILL = 0.78
TERMINAL_PMF = 0.85
BOOST_CASE_FRAC = 0.12
BALLISTIC_TWO_STAGE_M = 6.0
TERMINAL_COAST_CAP_M = 150000.0
RHO_SEA_KG_M3 = 1.225
TERMINAL_CD = 0.40

MISSILE_CLASS_ORDER: list[dict[str, str]] = [
    {
        'id': 'hgv_biconic',
        'label': '双锥体助推滑翔',
        'blurb': '两级固体助推，双锥体升阻比，扣除重力阻力损失后积分滑翔航程。',
    },
    {
        'id': 'hgv_waverider',
        'label': '乘波体助推滑翔',
        'blurb': '两级固体助推，乘波体升阻比更高，扣除重力阻力损失后积分滑翔航程。',
    },
    {
        'id': 'scramjet',
        'label': '超燃冲压导弹',
        'blurb': '固体火箭助推到接力马赫数，超燃冲压在设计高度巡航。比冲与密度只作用于助推药。',
    },
    {
        'id': 'ramjet',
        'label': '亚燃冲压导弹',
        'blurb': '固体火箭助推到接力马赫数，亚燃冲压在设计高度巡航。比冲与密度只作用于助推药。',
    },
    {
        'id': 'turbofan_stealth',
        'label': '涡扇亚音速隐身巡航',
        'blurb': '涡扇耗油率较低，隐身进气道与涂层降低升阻比并占用容积。分别给出全高空与全掠海射程。',
    },
    {
        'id': 'turbojet_subsonic',
        'label': '涡喷亚音速非隐身巡航',
        'blurb': '涡喷耗油率较高，常规气动升阻比更好、油箱更满。分别给出全高空与全掠海射程。',
    },
    {
        'id': 'turbofan_rocket',
        'label': '亚超结合导弹',
        'blurb': '巡航段为涡扇，末端为固体火箭低空冲刺。全高空与全掠海都加上同一段末端航程。',
    },
    {
        'id': 'ballistic',
        'label': '普通弹道导弹',
        'blurb': '按弹体容积估算固体装药，地面或空射关机后取最优弹道弧，不含滑翔增程。',
    },
]

# 未写明双锥或乘波时，这些名字只表示「助推滑翔」，再由构型参数区分
_GENERIC_HGV = {'hgv', '滑翔', '助推滑翔', '助推滑翔弹'}

_CLASS_ALIASES = {
    'hgv_biconic': 'hgv_biconic',
    'biconic': 'hgv_biconic',
    '双锥': 'hgv_biconic',
    '双锥体': 'hgv_biconic',
    '双锥体助推滑翔': 'hgv_biconic',
    'hgv_waverider': 'hgv_waverider',
    'waverider': 'hgv_waverider',
    '乘波': 'hgv_waverider',
    '乘波体': 'hgv_waverider',
    '乘波体助推滑翔': 'hgv_waverider',
    'scramjet': 'scramjet',
    '超燃': 'scramjet',
    '超燃冲压': 'scramjet',
    '超燃冲压导弹': 'scramjet',
    'ramjet': 'ramjet',
    '亚燃': 'ramjet',
    '亚燃冲压': 'ramjet',
    '亚燃冲压导弹': 'ramjet',
    'turbofan_stealth': 'turbofan_stealth',
    '涡扇隐身': 'turbofan_stealth',
    '涡扇亚音速隐身巡航': 'turbofan_stealth',
    'turbojet_subsonic': 'turbojet_subsonic',
    '涡喷': 'turbojet_subsonic',
    '涡喷亚音速非隐身巡航': 'turbojet_subsonic',
    'turbofan_rocket': 'turbofan_rocket',
    '亚超': 'turbofan_rocket',
    '亚超结合': 'turbofan_rocket',
    '亚超结合导弹': 'turbofan_rocket',
    'ballistic': 'ballistic',
    '弹道': 'ballistic',
    '普通弹道': 'ballistic',
    '普通弹道导弹': 'ballistic',
}

_SUBSONIC_SPECS: dict[str, dict[str, float]] = {
    'turbofan_stealth': {
        'areal': 24.0,
        'eng_coeff': 250.0,
        'eng_density': 520.0,
        'payload_density': 1500.0,
        'void_frac': 0.09,
        'fuel_density': 800.0,
        'tsfc': 1.75e-5,
        'mach': 0.75,
        'alt_km': 10.0,
        'ld_base': 4.4,
        'ld_slope': 0.16,
        'ld_min': 5.0,
        'ld_max': 6.8,
        'eta': 0.32,
        'sea_ld_factor': 0.60,
        'sea_tsfc_factor': 1.08,
        'reserve': 0.08,
        'sea_alt_km': 0.03,
    },
    'turbojet_subsonic': {
        'areal': 16.0,
        'eng_coeff': 190.0,
        'eng_density': 560.0,
        'payload_density': 1600.0,
        'void_frac': 0.05,
        'fuel_density': 800.0,
        'tsfc': 4.6e-5,
        'mach': 0.80,
        'alt_km': 8.0,
        'ld_base': 4.8,
        'ld_slope': 0.20,
        'ld_min': 5.2,
        'ld_max': 7.4,
        'eta': 0.24,
        'sea_ld_factor': 0.60,
        'sea_tsfc_factor': 1.08,
        'reserve': 0.08,
        'sea_alt_km': 0.03,
    },
}

_DUCT_SPECS: dict[str, dict[str, float]] = {
    'ramjet': {
        'areal': 28.0,
        'eng_coeff': 210.0,
        'eng_density': 380.0,
        'payload_density': 1450.0,
        'void_frac': 0.06,
        'fuel_density': 820.0,
        'tsfc': 8.2e-5,
        'mach_takeover': 2.05,
        'mach_cruise': 3.0,
        'alt_km': 18.0,
        'ld_base': 1.9,
        'ld_slope': 0.11,
        'ld_min': 2.3,
        'ld_max': 3.6,
        'eta': 0.20,
        'reserve': 0.08,
        'loss_frac': 0.18,
        'accel_excess': 0.32,
        'fuel_floor_frac': 0.30,
    },
    'scramjet': {
        'areal': 36.0,
        'eng_coeff': 240.0,
        'eng_density': 420.0,
        'payload_density': 1400.0,
        'void_frac': 0.05,
        'fuel_density': 840.0,
        'tsfc': 1.12e-4,
        'mach_takeover': 4.2,
        'mach_cruise': 5.5,
        'alt_km': 28.0,
        'ld_base': 1.7,
        'ld_slope': 0.09,
        'ld_min': 2.2,
        'ld_max': 3.4,
        'eta': 0.16,
        'reserve': 0.08,
        'loss_frac': 0.22,
        'accel_excess': 0.26,
        'fuel_floor_frac': 0.22,
    },
}

_ROCKET_CRUISE = {
    'areal': 22.0,
    'eng_coeff': 230.0,
    'eng_density': 520.0,
    'payload_density': 1500.0,
    'void_frac': 0.06,
    'fuel_density': 800.0,
    'tsfc': 1.85e-5,
    'mach': 0.75,
    'alt_km': 9.0,
    'ld_base': 4.3,
    'ld_slope': 0.15,
    'ld_min': 4.8,
    'ld_max': 6.5,
    'eta': 0.30,
    'sea_ld_factor': 0.60,
    'sea_tsfc_factor': 1.08,
    'reserve': 0.08,
    'sea_alt_km': 0.03,
    'terminal_dv_m_s': 860.0,
    'terminal_volume_cap_frac': 0.18,
}


def class_label(missile_class: str) -> str:
    """弹种中文名。"""
    canon = normalize_missile_class(missile_class)
    for item in MISSILE_CLASS_ORDER:
        if item['id'] == canon:
            return item['label']
    return canon


def class_blurb(missile_class: str) -> str:
    """弹种对应的估算说明。"""
    canon = normalize_missile_class(missile_class)
    for item in MISSILE_CLASS_ORDER:
        if item['id'] == canon:
            return item['blurb']
    return ''


def normalize_missile_class(missile_class: str) -> str:
    """把弹种名规范成内部 id。未写明双锥或乘波的滑翔弹不在这里解析。"""
    raw = str(missile_class).strip()
    canon = _CLASS_ALIASES.get(raw.lower()) or _CLASS_ALIASES.get(raw)
    if canon is None:
        raise ValueError(f'未知弹种: {missile_class}')
    return canon


def glide_shape(missile_class: str) -> str | None:
    """助推滑翔弹种对应的构型；其他弹种返回 None。"""
    canon = normalize_missile_class(missile_class)
    if canon == 'hgv_biconic':
        return 'biconic'
    if canon == 'hgv_waverider':
        return 'waverider'
    return None


def resolve_missile_class(missile_class: str, hgv_type: str = 'biconic') -> str:
    """把弹种和可选构型收成一个 id。旧的「助推滑翔」仍看 hgv_type。"""
    raw = str(missile_class).strip()
    if raw.lower() in _GENERIC_HGV or raw in _GENERIC_HGV:
        from utils.missile_range.estimate import normalize_hgv_type
        shape = normalize_hgv_type(hgv_type)
        return 'hgv_waverider' if shape == 'waverider' else 'hgv_biconic'
    return normalize_missile_class(missile_class)


def clamp(value: float, low: float, high: float) -> float:
    """把数值限制在闭区间内。"""
    return max(low, min(high, value))


def fineness_ratio(length_m: float, diameter_m: float) -> float:
    """长细比。弹长或弹径非正时拒绝估算。"""
    if length_m <= 0 or diameter_m <= 0:
        raise ValueError('弹长与弹径必须大于 0')
    return length_m / diameter_m


def speed_of_sound_m_s(altitude_km: float) -> float:
    """国际标准大气近似下的声速。"""
    if altitude_km < 0:
        raise ValueError('高度不能为负')
    height_m = altitude_km * 1000.0
    if height_m <= 11000.0:
        temperature = 288.15 - 0.0065 * height_m
    elif height_m <= 20000.0:
        temperature = 216.65
    elif height_m <= 32000.0:
        temperature = 216.65 + 0.001 * (height_m - 20000.0)
    else:
        temperature = 228.65 + 0.0028 * (min(height_m, 47000.0) - 32000.0)
    return math.sqrt(1.4 * 287.05287 * temperature)


def body_volume_m3(length_m: float, diameter_m: float) -> float:
    """弹体外形对应的可用内部容积。"""
    fineness_ratio(length_m, diameter_m)
    return BODY_PACK * math.pi * (diameter_m / 2.0) ** 2 * length_m


def payload_mass_kg(warhead_mass_kg: float) -> float:
    """战斗部加上舱段结构，舱段至少 18 kg。"""
    if warhead_mass_kg < 0:
        raise ValueError('战斗部质量不能为负')
    return warhead_mass_kg + max(18.0, 0.12 * warhead_mass_kg)


def structural_mass_kg(length_m: float, diameter_m: float, areal_kg_m2: float) -> float:
    """蒙皮、舵面与加强框，按侧面积乘面密度。"""
    if areal_kg_m2 <= 0:
        raise ValueError('结构面密度必须大于 0')
    fineness_ratio(length_m, diameter_m)
    return areal_kg_m2 * math.pi * diameter_m * length_m * 1.15


def engine_mass_kg(length_m: float, diameter_m: float, eng_coeff: float) -> float:
    """吸气发动机干质量，随弹径平方与弹长弱相关。"""
    if eng_coeff <= 0:
        raise ValueError('发动机质量系数必须大于 0')
    fineness_ratio(length_m, diameter_m)
    return eng_coeff * (diameter_m ** 2) * (length_m ** 0.15)


def energy_volume_m3(
    body_volume: float,
    payload_mass: float,
    payload_density: float,
    engine_mass: float,
    engine_density: float,
    void_frac: float,
) -> float:
    """扣掉战斗部、发动机和空腔后，留给燃油或助推药的容积。"""
    if payload_density <= 0 or engine_density <= 0:
        raise ValueError('密度必须大于 0')
    if not 0.0 <= void_frac < 0.5:
        raise ValueError('空腔比例须在 0 到 0.5 之间')
    leftover = (
        body_volume
        - payload_mass / payload_density
        - engine_mass / engine_density
        - void_frac * body_volume
    )
    if leftover <= 0.02:
        raise ValueError('弹体容积放不下战斗部与发动机')
    return leftover


def subsonic_ld(length_m: float, diameter_m: float, spec: dict[str, float]) -> float:
    """按长细比插值亚音速升阻比，并夹在弹种允许区间。"""
    fineness = fineness_ratio(length_m, diameter_m)
    raw = spec['ld_base'] + spec['ld_slope'] * fineness
    return clamp(raw, spec['ld_min'], spec['ld_max'])


def breguet_cruise_range_m(
    speed_m_s: float,
    tsfc_kg_n_s: float,
    ld: float,
    mass_initial_kg: float,
    mass_final_kg: float,
) -> float:
    """布雷盖巡航航程（米）。耗油率为 kg/(N·s)。"""
    if speed_m_s <= 0:
        raise ValueError('巡航速度必须大于 0')
    if tsfc_kg_n_s <= 0:
        raise ValueError('耗油率必须大于 0')
    if ld <= 0:
        raise ValueError('升阻比必须大于 0')
    if mass_final_kg <= 0 or mass_initial_kg <= mass_final_kg:
        raise ValueError('巡航必须消耗燃油，且终了质量为正')
    return (speed_m_s / (G0 * tsfc_kg_n_s)) * ld * math.log(mass_initial_kg / mass_final_kg)


def climb_fuel_kg(
    mass_kg: float,
    delta_height_m: float,
    delta_speed_sq: float,
    eta: float,
) -> float:
    """把高度差和加速折成爬升耗油，推进效率越低越费油。"""
    if mass_kg <= 0:
        raise ValueError('质量必须大于 0')
    if eta <= 0:
        raise ValueError('推进效率必须大于 0')
    energy = mass_kg * (G0 * max(0.0, delta_height_m) + 0.5 * max(0.0, delta_speed_sq))
    return energy / (LHV_J_KG * eta)


def cruise_range_pair_km(
    *,
    length_m: float,
    diameter_m: float,
    warhead_mass_kg: float,
    v_launch_mach: float,
    h_launch_km: float,
    spec: dict[str, float],
    reserved_volume_m3: float = 0.0,
    inert_mass_kg: float = 0.0,
) -> dict[str, float]:
    """全高空与全掠海巡航航程。预留容积和惰性质量给末端火箭。"""
    if v_launch_mach < 0 or h_launch_km < 0:
        raise ValueError('发射马赫数与高度不能为负')
    if reserved_volume_m3 < 0 or inert_mass_kg < 0:
        raise ValueError('预留容积与附加质量不能为负')
    volume = body_volume_m3(length_m, diameter_m)
    payload = payload_mass_kg(warhead_mass_kg)
    structure = structural_mass_kg(length_m, diameter_m, spec['areal'])
    engine = engine_mass_kg(length_m, diameter_m, spec['eng_coeff'])
    tank = energy_volume_m3(
        volume, payload, spec['payload_density'], engine, spec['eng_density'], spec['void_frac'],
    )
    if reserved_volume_m3 >= tank:
        raise ValueError('末端火箭占用的容积超过燃油舱')
    fuel_kg = (tank - reserved_volume_m3) * spec['fuel_density']
    if fuel_kg <= 1.0:
        raise ValueError('燃油过少，无法巡航')
    launch_mass = payload + structure + engine + fuel_kg + inert_mass_kg
    ld = subsonic_ld(length_m, diameter_m, spec)
    sound_hi = speed_of_sound_m_s(spec['alt_km'])
    sound_sea = speed_of_sound_m_s(spec['sea_alt_km'])
    speed_hi = spec['mach'] * sound_hi
    speed_sea = spec['mach'] * sound_sea
    launch_speed = v_launch_mach * speed_of_sound_m_s(h_launch_km)
    climb = climb_fuel_kg(
        launch_mass,
        (spec['alt_km'] - h_launch_km) * 1000.0,
        speed_hi ** 2 - launch_speed ** 2,
        spec['eta'],
    )
    climb = min(climb, fuel_kg * 0.40)
    usable_hi = max(0.0, fuel_kg - climb) * (1.0 - spec['reserve'])
    usable_sea = fuel_kg * (1.0 - spec['reserve'])
    range_high = breguet_cruise_range_m(
        speed_hi, spec['tsfc'], ld, launch_mass, launch_mass - usable_hi,
    )
    range_sea = breguet_cruise_range_m(
        speed_sea,
        spec['tsfc'] * spec['sea_tsfc_factor'],
        ld * spec['sea_ld_factor'],
        launch_mass,
        launch_mass - usable_sea,
    )
    bay = payload / spec['payload_density']
    section = math.pi * (diameter_m / 2.0) ** 2
    head_len = min(length_m * 0.45, bay / max(section, 1e-6))
    return {
        'm_0': launch_mass,
        'fuel_kg': fuel_kg,
        'ld': ld,
        'range_high_m': range_high,
        'range_sea_m': range_sea,
        'l_head_m': head_len,
        'cruise_mach': spec['mach'],
        'cruise_alt_km': spec['alt_km'],
        'm_engine': engine,
        'usable_high_kg': usable_hi,
        'usable_sea_kg': usable_sea,
    }


def split_boost_and_fuel(
    energy_volume_m3_value: float,
    fixed_mass_kg: float,
    dv_boost_m_s: float,
    isp_s: float,
    propellant_density: float,
    fuel_density: float,
    fuel_floor_frac: float,
) -> tuple[float, float, float]:
    """在能源容积里分配助推药和冲压燃油，助推药不超过扣除保底燃油后的上限。"""
    if energy_volume_m3_value <= 0 or fixed_mass_kg <= 0:
        raise ValueError('能源容积与固定质量必须大于 0')
    if isp_s <= 0 or propellant_density <= 0 or fuel_density <= 0:
        raise ValueError('比冲与密度必须大于 0')
    if dv_boost_m_s < 0:
        raise ValueError('助推速度增量不能为负')
    ve = isp_s * G0
    floor = clamp(fuel_floor_frac, 0.05, 0.8)
    boost_cap_volume = energy_volume_m3_value * (1.0 - floor)
    propellant_cap = boost_cap_volume * propellant_density * BOOST_FILL
    propellant = 0.0
    if dv_boost_m_s <= 1.0:
        fuel = energy_volume_m3_value * fuel_density
        return 0.0, fuel, fixed_mass_kg + fuel
    for _ in range(24):
        prop_volume = propellant / (propellant_density * BOOST_FILL)
        fuel = max(0.0, energy_volume_m3_value - prop_volume) * fuel_density
        launch_mass = fixed_mass_kg + propellant * (1.0 + BOOST_CASE_FRAC) + fuel
        needed = launch_mass * (1.0 - math.exp(-dv_boost_m_s / ve))
        propellant = min(propellant_cap, 0.45 * propellant + 0.55 * needed)
    prop_volume = propellant / (propellant_density * BOOST_FILL)
    fuel = max(0.0, energy_volume_m3_value - prop_volume) * fuel_density
    launch_mass = fixed_mass_kg + propellant * (1.0 + BOOST_CASE_FRAC) + fuel
    return propellant, fuel, launch_mass


def achieved_boost_dv_m_s(
    propellant_kg: float,
    launch_mass_kg: float,
    isp_s: float,
) -> float:
    """当前装药实际能给出的理想速度增量。"""
    if launch_mass_kg <= propellant_kg or propellant_kg < 0 or isp_s <= 0:
        raise ValueError('助推装药与起飞质量组合无效')
    if propellant_kg == 0:
        return 0.0
    return isp_s * G0 * math.log(launch_mass_kg / (launch_mass_kg - propellant_kg))


def duct_ld(length_m: float, diameter_m: float, spec: dict[str, float]) -> float:
    """冲压弹巡航升阻比。"""
    return subsonic_ld(length_m, diameter_m, spec)


def drag_coast_range_m(
    speed_start_m_s: float,
    speed_end_m_s: float,
    mass_kg: float,
    diameter_m: float,
    rho_kg_m3: float = RHO_SEA_KG_M3,
    cd: float = TERMINAL_CD,
) -> float:
    """二次阻力下从起始速度减速到终止速度的航程，并设上限。"""
    if mass_kg <= 0 or diameter_m <= 0 or rho_kg_m3 <= 0 or cd <= 0:
        raise ValueError('阻力滑行的质量、弹径、密度与阻力系数必须大于 0')
    if speed_end_m_s <= 0 or speed_start_m_s <= speed_end_m_s:
        return 0.0
    area = math.pi * (diameter_m / 2.0) ** 2
    drag_k = 0.5 * rho_kg_m3 * cd * area / mass_kg
    return min(TERMINAL_COAST_CAP_M, math.log(speed_start_m_s / speed_end_m_s) / drag_k)


def terminal_dash_range_m(
    mass_ignition_kg: float,
    propellant_kg: float,
    diameter_m: float,
    isp_s: float,
    speed_entry_m_s: float,
) -> float:
    """低空固体火箭冲刺：燃烧段平均速度加上减速到马赫 1.05 的滑行。"""
    if propellant_kg <= 0 or propellant_kg >= mass_ignition_kg:
        return 0.0
    if isp_s <= 0 or speed_entry_m_s <= 0 or diameter_m <= 0:
        raise ValueError('末端冲刺参数无效')
    dv = isp_s * G0 * math.log(mass_ignition_kg / (mass_ignition_kg - propellant_kg)) - 160.0
    speed_exit = speed_entry_m_s + max(0.0, dv)
    burn_time = propellant_kg * isp_s / (6.0 * mass_ignition_kg)
    burn_range = 0.5 * (speed_entry_m_s + speed_exit) * burn_time
    speed_floor = 1.05 * speed_of_sound_m_s(0.0)
    coast = drag_coast_range_m(
        speed_exit, min(speed_exit, max(speed_floor, speed_entry_m_s)),
        mass_ignition_kg - propellant_kg, diameter_m,
    )
    return burn_range + coast


def ballistic_range_km(speed_m_s: float, altitude_km: float) -> float:
    """真空中关机速度对应的最大地面射程，对弹道倾角取最大值。"""
    if speed_m_s <= 0:
        raise ValueError('关机速度必须大于 0')
    if altitude_km < 0:
        raise ValueError('关机高度不能为负')
    radius0 = R_EARTH_M + altitude_km * 1000.0
    mu = G0 * R_EARTH_M * R_EARTH_M
    if speed_m_s ** 2 / 2.0 - mu / radius0 >= 0:
        return 20000.0
    best = 0.0
    for gamma_deg in range(5, 80):
        gamma = math.radians(gamma_deg)
        angular = radius0 * speed_m_s * math.cos(gamma)
        energy = speed_m_s ** 2 / 2.0 - mu / radius0
        ecc_sq = 1.0 + 2.0 * energy * angular ** 2 / (mu ** 2)
        if ecc_sq <= 1e-8:
            continue
        ecc = math.sqrt(ecc_sq)
        semi_latus = angular ** 2 / mu
        cos_burnout = (semi_latus / radius0 - 1.0) / ecc
        cos_impact = (semi_latus / R_EARTH_M - 1.0) / ecc
        if abs(cos_burnout) > 1.0 or abs(cos_impact) > 1.0:
            continue
        true_burnout = math.acos(clamp(cos_burnout, -1.0, 1.0))
        true_impact = 2.0 * math.pi - math.acos(clamp(cos_impact, -1.0, 1.0))
        arc = true_impact - true_burnout
        ground_km = arc * R_EARTH_M / 1000.0
        if 0.0 < ground_km < 20000.0 and ground_km > best:
            best = ground_km
    if best <= 0.0:
        raise ValueError('该关机状态没有落到地面的弹道')
    return best


def burnout_altitude_km(speed_m_s: float, launch_altitude_km: float) -> float:
    """关机高度：发射高度加上与关机速度相关的爬升。"""
    if speed_m_s < 0 or launch_altitude_km < 0:
        raise ValueError('速度与发射高度不能为负')
    climb = 7.5 * (speed_m_s / 1000.0) ** 1.45
    return min(280.0, launch_altitude_km + climb)


def ballistic_loss_m_s(dv_ideal_m_s: float, burn_time_s: float, launch_altitude_km: float) -> float:
    """地面发射按燃烧时间估重力损失；高空发射沿用滑翔弹的损失模型。"""
    if dv_ideal_m_s < 0 or burn_time_s < 0 or launch_altitude_km < 0:
        raise ValueError('速度增量、燃烧时间与高度不能为负')
    if launch_altitude_km >= 8.0:
        return gravity_drag_loss_m_s(launch_altitude_km)
    return G0 * burn_time_s * 0.58 + 0.06 * dv_ideal_m_s + 50.0


def ballistic_burn_time_s(propellant_kg: float, launch_mass_kg: float, isp_s: float) -> float:
    """起飞推重比约 2.3 时的燃烧时间。"""
    if launch_mass_kg <= 0 or propellant_kg < 0 or isp_s <= 0:
        raise ValueError('弹道弹燃烧时间参数无效')
    return propellant_kg * isp_s / (2.3 * launch_mass_kg)


def _ideal_two_stage_dv(launch_mass: float, propellant: float, booster_dry: float, ve: float) -> float:
    """与滑翔弹相同的 58/42 两级速度增量。"""
    first = propellant * 0.58
    second = propellant * 0.42
    stage1_dry_drop = booster_dry * 0.60
    stage1_out = launch_mass - first
    stage2_in = stage1_out - stage1_dry_drop
    stage2_out = stage2_in - second
    if min(stage1_out, stage2_in, stage2_out) <= 0:
        raise ValueError('两级质量组合无效')
    return ve * math.log(launch_mass / stage1_out) + ve * math.log(stage2_in / stage2_out)


def _base_fields(
    missile_class: str,
    launch_mass: float,
    head_m: float,
    booster_m: float,
    propellant_kg: float,
    speed_mach: float,
    ld: float | None,
    range_km: float,
    note: str,
    range_high_km: float | None = None,
    range_sea_km: float | None = None,
    range_cruise_km: float | None = None,
    range_terminal_km: float | None = None,
    cruise_mach: float | None = None,
    cruise_alt_km: float | None = None,
) -> dict:
    return {
        'missile_class': missile_class,
        'class_label': class_label(missile_class),
        'm_0_t': round(launch_mass / 1000.0, 2),
        'l_head_m': round(head_m, 2),
        'l_booster_m': round(booster_m, 2),
        'm_p_total_kg': round(propellant_kg, 1),
        'v_burnout_mach': round(speed_mach, 2),
        'ld_ratio': None if ld is None else round(ld, 2),
        'range_km': round(range_km, 1),
        'range_high_km': None if range_high_km is None else round(range_high_km, 1),
        'range_sea_km': None if range_sea_km is None else round(range_sea_km, 1),
        'range_cruise_km': None if range_cruise_km is None else round(range_cruise_km, 1),
        'range_terminal_km': None if range_terminal_km is None else round(range_terminal_km, 1),
        'cruise_mach': None if cruise_mach is None else round(cruise_mach, 2),
        'cruise_alt_km': None if cruise_alt_km is None else round(cruise_alt_km, 1),
        'note': note,
    }


def estimate_subsonic_class(
    missile_class: str,
    length_m: float,
    diameter_m: float,
    warhead_mass_kg: float,
    v_launch_mach: float,
    h_launch_km: float,
) -> dict:
    """涡扇隐身或涡喷非隐身的全高空、全掠海射程。"""
    canon = normalize_missile_class(missile_class)
    if canon not in _SUBSONIC_SPECS:
        raise ValueError('该函数只用于亚音速巡航弹')
    spec = _SUBSONIC_SPECS[canon]
    sized = cruise_range_pair_km(
        length_m=length_m,
        diameter_m=diameter_m,
        warhead_mass_kg=warhead_mass_kg,
        v_launch_mach=v_launch_mach,
        h_launch_km=h_launch_km,
        spec=spec,
    )
    high_km = sized['range_high_m'] / 1000.0
    sea_km = sized['range_sea_m'] / 1000.0
    note = (
        f"{class_label(canon)}：主射程为全高空 {spec['alt_km']:.0f} km、"
        f"Ma {spec['mach']:.2f}；全掠海为 {spec['sea_alt_km'] * 1000:.0f} m。"
        f"升阻比 {sized['ld']:.2f}，耗油率按弹种固定。"
    )
    return _base_fields(
        canon, sized['m_0'], sized['l_head_m'], length_m - sized['l_head_m'],
        sized['fuel_kg'], spec['mach'], sized['ld'], high_km, note,
        range_high_km=high_km, range_sea_km=sea_km,
        range_cruise_km=high_km, cruise_mach=spec['mach'], cruise_alt_km=spec['alt_km'],
    )


def estimate_ducted(
    missile_class: str,
    length_m: float,
    diameter_m: float,
    warhead_mass_kg: float,
    v_launch_mach: float,
    h_launch_km: float,
    isp_s: float,
    propellant_density: float,
) -> dict:
    """超燃或亚燃：助推到实际能达到的马赫数，再用剩余燃油巡航。"""
    canon = normalize_missile_class(missile_class)
    spec = _DUCT_SPECS.get(canon)
    if spec is None:
        raise ValueError('该函数只用于冲压弹')
    if isp_s <= 0 or propellant_density <= 0:
        raise ValueError('比冲与推进剂密度必须大于 0')
    if v_launch_mach < 0 or h_launch_km < 0:
        raise ValueError('发射马赫数与高度不能为负')
    volume = body_volume_m3(length_m, diameter_m)
    payload = payload_mass_kg(warhead_mass_kg)
    structure = structural_mass_kg(length_m, diameter_m, spec['areal'])
    engine = engine_mass_kg(length_m, diameter_m, spec['eng_coeff'])
    tank = energy_volume_m3(
        volume, payload, spec['payload_density'], engine, spec['eng_density'], spec['void_frac'],
    )
    sound = speed_of_sound_m_s(spec['alt_km'])
    launch_speed = v_launch_mach * speed_of_sound_m_s(h_launch_km)
    takeover_speed = spec['mach_takeover'] * sound
    gap = max(0.0, takeover_speed - launch_speed)
    dv_need = gap * (1.0 + spec['loss_frac']) + (0.0 if gap == 0 else 80.0)
    fixed = payload + structure + engine
    propellant, fuel, launch_mass = split_boost_and_fuel(
        tank, fixed, dv_need, isp_s, propellant_density, spec['fuel_density'], spec['fuel_floor_frac'],
    )
    ideal = achieved_boost_dv_m_s(propellant, launch_mass, isp_s)
    if dv_need <= 1.0:
        speed_after = launch_speed
    else:
        speed_after = launch_speed + gap * min(1.0, ideal / dv_need)
    reached = speed_after >= takeover_speed * 0.98
    if reached:
        cruise_speed = spec['mach_cruise'] * sound
    else:
        cruise_speed = max(speed_after, sound * 1.3)
    cruise_mach = cruise_speed / sound
    accel = max(0.0, cruise_speed - speed_after) if reached else 0.0
    isp_air = 1.0 / (spec['tsfc'] * G0)
    mass_after_boost = launch_mass - propellant
    accel_frac = 0.0 if accel <= 1.0 else 1.0 - math.exp(-accel / (isp_air * G0 * spec['accel_excess']))
    accel_fuel = min(fuel * 0.65, accel_frac * mass_after_boost)
    cruise_fuel = max(0.0, fuel - accel_fuel) * (1.0 - spec['reserve'])
    if cruise_fuel <= 1.0:
        raise ValueError('冲压燃油不足以完成巡航')
    ld = duct_ld(length_m, diameter_m, spec)
    cruise_m = breguet_cruise_range_m(
        cruise_speed, spec['tsfc'], ld, mass_after_boost, mass_after_boost - cruise_fuel,
    )
    burn_time = ballistic_burn_time_s(propellant, launch_mass, isp_s) if propellant > 0 else 0.0
    boost_range = 0.5 * (launch_speed + min(speed_after, cruise_speed)) * burn_time
    total_km = (cruise_m + boost_range) / 1000.0
    bay = payload / spec['payload_density']
    section = math.pi * (diameter_m / 2.0) ** 2
    head_len = min(length_m * 0.45, bay / section)
    trimmed = '' if reached else '接力装药不足，巡航马赫已下调。'
    note = (
        f"{class_label(canon)}：设计巡航 Ma {spec['mach_cruise']:.1f} @ {spec['alt_km']:.0f} km，"
        f"本次巡航 Ma {cruise_mach:.2f}。{trimmed}"
    )
    return _base_fields(
        canon, launch_mass, head_len, length_m - head_len, fuel + propellant,
        cruise_mach, ld, total_km, note,
        range_cruise_km=cruise_m / 1000.0,
        cruise_mach=cruise_mach, cruise_alt_km=spec['alt_km'],
    )


def terminal_propellant_for_dash(
    length_m: float,
    diameter_m: float,
    warhead_mass_kg: float,
    v_launch_mach: float,
    h_launch_km: float,
    isp_s: float,
    propellant_density: float,
    spec: dict[str, float],
) -> tuple[float, dict[str, float]]:
    """按较重的巡航终点质量迭代末端装药，容积不超过弹体上限。"""
    volume = body_volume_m3(length_m, diameter_m)
    propellant_cap = volume * spec['terminal_volume_cap_frac'] * TERMINAL_FILL * propellant_density
    ve = isp_s * G0
    propellant = 0.0
    sized: dict[str, float] = {}
    for _ in range(10):
        reserved = propellant / (TERMINAL_FILL * propellant_density) if propellant > 0 else 0.0
        case_mass = propellant * (1.0 - TERMINAL_PMF) / TERMINAL_PMF
        sized = cruise_range_pair_km(
            length_m=length_m,
            diameter_m=diameter_m,
            warhead_mass_kg=warhead_mass_kg,
            v_launch_mach=v_launch_mach,
            h_launch_km=h_launch_km,
            spec=spec,
            reserved_volume_m3=reserved,
            inert_mass_kg=propellant + case_mass,
        )
        mass_ign = sized['m_0'] - sized['usable_high_kg']
        needed = mass_ign * (1.0 - math.exp(-spec['terminal_dv_m_s'] / ve))
        propellant = min(propellant_cap, 0.5 * propellant + 0.5 * needed)
    reserved = propellant / (TERMINAL_FILL * propellant_density)
    case_mass = propellant * (1.0 - TERMINAL_PMF) / TERMINAL_PMF
    sized = cruise_range_pair_km(
        length_m=length_m,
        diameter_m=diameter_m,
        warhead_mass_kg=warhead_mass_kg,
        v_launch_mach=v_launch_mach,
        h_launch_km=h_launch_km,
        spec=spec,
        reserved_volume_m3=reserved,
        inert_mass_kg=propellant + case_mass,
    )
    return propellant, sized


def estimate_turbofan_rocket(
    length_m: float,
    diameter_m: float,
    warhead_mass_kg: float,
    v_launch_mach: float,
    h_launch_km: float,
    isp_s: float,
    propellant_density: float,
) -> dict:
    """涡扇巡航加上末端固体火箭。全高空、全掠海都包含同一段冲刺。"""
    if isp_s <= 0 or propellant_density <= 0:
        raise ValueError('比冲与推进剂密度必须大于 0')
    spec = _ROCKET_CRUISE
    propellant, sized = terminal_propellant_for_dash(
        length_m, diameter_m, warhead_mass_kg, v_launch_mach, h_launch_km,
        isp_s, propellant_density, spec,
    )
    entry = spec['mach'] * speed_of_sound_m_s(spec['sea_alt_km'])
    mass_ign = sized['m_0'] - sized['usable_high_kg']
    dash = terminal_dash_range_m(mass_ign, propellant, diameter_m, isp_s, entry)
    high_km = sized['range_high_m'] / 1000.0 + dash / 1000.0
    sea_km = sized['range_sea_m'] / 1000.0 + dash / 1000.0
    note = (
        f"亚超结合：涡扇巡航 Ma {spec['mach']:.2f}，"
        f"全高空 {spec['alt_km']:.0f} km / 全掠海 {spec['sea_alt_km'] * 1000:.0f} m，"
        f"末端火箭冲刺 {dash / 1000.0:.1f} km。"
    )
    return _base_fields(
        'turbofan_rocket', sized['m_0'], sized['l_head_m'], length_m - sized['l_head_m'],
        sized['fuel_kg'] + propellant, spec['mach'], sized['ld'], high_km, note,
        range_high_km=high_km, range_sea_km=sea_km,
        range_cruise_km=sized['range_high_m'] / 1000.0,
        range_terminal_km=dash / 1000.0,
        cruise_mach=spec['mach'], cruise_alt_km=spec['alt_km'],
    )


def estimate_ballistic(
    length_m: float,
    diameter_m: float,
    warhead_mass_kg: float,
    v_launch_mach: float,
    h_launch_km: float,
    isp_s: float,
    propellant_density: float,
) -> dict:
    """普通弹道导弹：装药估算、重力阻力损失、最优弹道射程。"""
    if length_m <= 0 or diameter_m <= 0:
        raise ValueError('弹长与弹径必须大于 0')
    if warhead_mass_kg < 0 or v_launch_mach < 0 or h_launch_km < 0:
        raise ValueError('战斗部、发射马赫数与高度不能为负')
    if isp_s <= 0 or propellant_density <= 0:
        raise ValueError('比冲与推进剂密度必须大于 0')
    head_len, booster_len = head_and_booster_lengths_m(
        length_m, diameter_m, warhead_mass_kg, 'biconic',
    )
    propellant = propellant_mass_kg(diameter_m, booster_len, propellant_density)
    dry = propellant * (1.0 - PROPELLANT_MASS_FRACTION) / PROPELLANT_MASS_FRACTION
    head = head_total_mass_kg(warhead_mass_kg)
    launch_mass = head + dry + propellant
    ve = isp_s * G0
    if booster_len >= BALLISTIC_TWO_STAGE_M:
        dv_ideal = _ideal_two_stage_dv(launch_mass, propellant, dry, ve)
        stages = '两级'
    else:
        if propellant >= launch_mass:
            raise ValueError('推进剂质量超过起飞质量')
        dv_ideal = ve * math.log(launch_mass / (launch_mass - propellant))
        stages = '单级'
    burn_time = ballistic_burn_time_s(propellant, launch_mass, isp_s)
    loss = ballistic_loss_m_s(dv_ideal, burn_time, h_launch_km)
    launch_speed = v_launch_mach * speed_of_sound_m_s(h_launch_km)
    speed = max(50.0, launch_speed + dv_ideal - loss)
    altitude = burnout_altitude_km(speed, h_launch_km)
    ground_km = ballistic_range_km(speed, altitude)
    note = (
        f"普通弹道导弹：{stages}固体，关机速度 {speed / 1000.0:.2f} km/s，"
        f"关机高度 {altitude:.0f} km，按最优倾角取射程，不含滑翔。"
    )
    return _base_fields(
        'ballistic', launch_mass, head_len, booster_len, propellant,
        speed / speed_of_sound_m_s(0.0), None, ground_km, note,
        cruise_alt_km=altitude,
    )


def estimate_by_class(
    missile_class: str,
    length_m: float,
    diameter_m: float,
    warhead_mass_kg: float,
    hgv_type: str = 'biconic',
    v_launch_mach: float = 0.85,
    h_launch_km: float = 13.0,
    isp_s: float = DEFAULT_ISP_S,
    propellant_density: float = DEFAULT_PROPELLANT_DENSITY,
) -> dict:
    """按弹种估算。双锥体和乘波体助推滑翔仍走原有模型。"""
    canon = resolve_missile_class(missile_class, hgv_type)
    shape = glide_shape(canon)
    if shape is not None:
        from utils.missile_range.estimate import estimate_hgv
        result = estimate_hgv(
            length_m, diameter_m, warhead_mass_kg, shape,
            v_launch_mach, h_launch_km, isp_s, propellant_density,
        )
        result = dict(result)
        result['missile_class'] = canon
        result['class_label'] = class_label(canon)
        result['note'] = class_blurb(canon)
        return result
    if canon in _SUBSONIC_SPECS:
        return estimate_subsonic_class(
            canon, length_m, diameter_m, warhead_mass_kg, v_launch_mach, h_launch_km,
        )
    if canon in _DUCT_SPECS:
        return estimate_ducted(
            canon, length_m, diameter_m, warhead_mass_kg,
            v_launch_mach, h_launch_km, isp_s, propellant_density,
        )
    if canon == 'turbofan_rocket':
        return estimate_turbofan_rocket(
            length_m, diameter_m, warhead_mass_kg,
            v_launch_mach, h_launch_km, isp_s, propellant_density,
        )
    if canon == 'ballistic':
        return estimate_ballistic(
            length_m, diameter_m, warhead_mass_kg,
            v_launch_mach, h_launch_km, isp_s, propellant_density,
        )
    raise ValueError(f'未知弹种: {missile_class}')
