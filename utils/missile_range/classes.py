"""六类导弹的射程估算：超燃、亚燃、涡扇隐身、涡喷非隐身、亚超结合、弹道。

亚音速与冲压巡航用布雷盖航程；全高空与全掠海只改巡航高度、升阻比和耗油率。
低速发射的亚音速弹先扣一截可抛弃固体助推器，助推器占燃油舱、不带进巡航质量。
冲压弹先用固体火箭助推到接力马赫数，再用剩余燃油巡航。亚燃在 10 km 以下按稠密大气加大助推损失。
亚超结合在涡扇巡航之后加一段低空固体火箭冲刺。
普通弹道导弹沿用弹体装药估算，关机后取最大射程弹道。
助推段不足 8.5 m 按单级。燃烧明显长于地面标定弹时，海平面再加一段大气阻力。
轻型战术弹推重比更高，地面 4 m 级用 PrSM 的 499 km 标定。
"""
from __future__ import annotations

import math

from utils.missile_range.estimate import (
    DEFAULT_ISP_S,
    DEFAULT_PROPELLANT_DENSITY,
    G0,
    PROPELLANT_MASS_FRACTION,
    R_EARTH_M,
    head_and_booster_lengths_m,
    head_total_mass_kg,
    propellant_mass_kg,
)

LHV_J_KG = 43.0e6
ISA_R = 287.05287
# 折叠弹翼：高空巡航设计升力系数、展弦比、相对厚度，面密度含折叠铰链
FOLDED_WING_CL = 0.65
FOLDED_WING_AR = 5.0
FOLDED_WING_TC = 0.08
FOLDED_WING_AREAL_KG_M2 = 42.0
# 折进弹体后，翼盒厚度不得超过弹径的这一比例
FOLDED_WING_THICKNESS_FRAC = 0.45
BODY_PACK = 0.68
BOOST_FILL = 0.76
TERMINAL_FILL = 0.78
TERMINAL_PMF = 0.85
BOOST_CASE_FRAC = 0.12
# 助推段达到这一长度才按两级。8.5 m 以下仍是单级，东风-15、850 垂发这一档不会被加成。
BALLISTIC_TWO_STAGE_M = 8.5
# 重型弹道弹起飞推重比。轻弹按质量再加上一截：战术固体火箭燃烧更短。
# 4.0 m × 0.43 m、战斗部 91 kg、地面静止发射，标定到 PrSM 公开射程 499 km。
BALLISTIC_TWR_HEAVY = 2.30
BALLISTIC_TWR_LIGHT_EXTRA = 2.4
BALLISTIC_TWR_SCALE_KG = 1400.0
# 燃烧段平均仰角的正弦。最大射程的重力转弯大约在 0.5 到 0.7。
BALLISTIC_GRAVITY_FACTOR = 0.64
# 海平面阻力。高度按大气标高衰减；空射不再改用滑翔弹那一档 180–320 m/s。
BALLISTIC_DRAG_FRACTION = 0.078
BALLISTIC_DRAG_BIAS_M_S = 44.0
BALLISTIC_DRAG_SCALE_KM = 8.5
# PrSM 地面发射燃烧约 42 s，这段阻力已经含在上面的份额里。
# 更久的燃烧还留在稠密大气中，海平面每多 1 秒再损失 16 m/s。
# 略高于 PrSM 的 42.2 s，标定弹本身不再多扣。
BALLISTIC_LONG_BURN_S = 43.0
BALLISTIC_LONG_BURN_DRAG_M_S = 16.0
# 亚音速发动机接力马赫数。更慢的发射要带可抛弃固体助推器。
SUBSONIC_TAKEOVER_MACH = 0.62
SUBSONIC_BOOSTER_ISP_S = 235.0
# 海平面从静止推到接力速度时，重力与阻力约占理想速度增量的 45%，随高度衰减。
SUBSONIC_BOOSTER_LOSS = 0.45
# 药柱只有一部分挤占燃油舱，喷管和尾裙落在油箱以外。
BOOSTER_TANK_SHARE = 0.50
# 亚燃助推损失在 10 km 标定高度以上不变；海平面提高到约 1.8 倍。超燃地面发射是另一条标定，不加。
RAMJET_LOSS_REF_KM = 10.0
RAMJET_SURFACE_LOSS_GAIN = 0.80
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
        'blurb': '固体火箭助推到接力马赫数，超燃冲压在高空巡航。进气道与燃烧室占去大量容积，比冲与密度只作用于助推药。',
    },
    {
        'id': 'ramjet',
        'label': '亚燃冲压导弹',
        'blurb': '固体火箭助推后亚燃冲压巡航。分别给出高空巡航与掠海巡航；进气道占容积，比冲与密度只作用于助推药。',
    },
    {
        'id': 'turbofan_stealth',
        'label': '涡扇亚音速隐身巡航',
        'blurb': '涡扇耗油率较低，隐身进气道与涂层降低升阻比并占用容积。弹体按扁五边形而不是圆。分别给出全高空与全掠海射程。弹翼折叠在弹体内，质量计入死重，占用容积不再装油。',
    },
    {
        'id': 'turbojet_subsonic',
        'label': '涡喷亚音速非隐身巡航',
        'blurb': '涡喷耗油率较高，常规气动升阻比更好、油箱更满。分别给出全高空与全掠海射程。弹翼折叠在弹体内，质量计入死重，占用容积不再装油。',
    },
    {
        'id': 'turbofan_rocket',
        'label': '亚超结合导弹',
        'blurb': '巡航段为涡扇，末端为固体火箭低空冲刺。全高空与全掠海都加上同一段末端航程。弹翼折叠在弹体内，质量计入死重，占用容积不再装油。',
    },
    {
        'id': 'ballistic',
        'label': '普通弹道导弹',
        'blurb': '按弹体容积估算固体装药。空射仍扣除燃烧段重力损失，关机后取最优弹道弧，不含滑翔增程。',
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
        # 截面是扁五边形，不是圆。只给弹径时，弹径是最大外廓，短边按 LRASM 的高/宽。
        # LRASM：长 4.26 m、宽 0.635 m、高 0.450 m、战斗部 450 kg，公开质量约 1.20–1.25 t。
        # JSM：长 4.00 m、宽 0.480 m、高 0.520 m、战斗部 120 kg，公开质量 416 kg。
        # 两发外廓体积接近，但 JSM 公开质量只有 416 kg，同样装填会到约 0.84 t。
        # 装填和面密度按装得满的 LRASM 标定到约 1.21 t、全高空约 970 km；
        # 五边形去掉“用最大边长当圆直径”多出来的容积。
        # 耗油率在 F107 基础上计入进气损失，燃油按 JP-10。
        'body_pack': 0.66,
        'pentagon_shoulder': 0.66,
        'minor_over_major': 0.450 / 0.635,
        'areal': 38.0,
        'eng_coeff': 180.0,
        'eng_density': 900.0,
        'payload_density': 2800.0,
        'void_frac': 0.16,
        'fuel_density': 940.0,
        'tsfc': 2.15e-5,
        'mach': 0.74,
        'alt_km': 10.0,
        'ld_base': 4.2,
        'ld_slope': 0.16,
        'ld_min': 4.6,
        'ld_max': 6.6,
        'eta': 0.32,
        'sea_ld_factor': 0.58,
        'sea_tsfc_factor': 1.08,
        'reserve': 0.08,
        'sea_alt_km': 0.03,
        'folded_wing': 1.0,
    },
    'turbojet_subsonic': {
        # 对照 Harpoon / Exocet 公开航程：小涡喷耗油率更高、升阻比更低
        'body_pack': 0.64,
        'areal': 18.0,
        'eng_coeff': 210.0,
        'eng_density': 580.0,
        'payload_density': 2100.0,
        'void_frac': 0.10,
        'fuel_density': 800.0,
        'tsfc': 6.8e-5,
        'mach': 0.80,
        'alt_km': 6.0,
        'ld_base': 3.6,
        'ld_slope': 0.12,
        'ld_min': 4.0,
        'ld_max': 5.8,
        'eta': 0.22,
        'sea_ld_factor': 0.58,
        'sea_tsfc_factor': 1.15,
        'reserve': 0.08,
        'sea_alt_km': 0.03,
        'folded_wing': 1.0,
    },
}

_DUCT_SPECS: dict[str, dict[str, float]] = {
    'ramjet': {
        # 整体式火箭冲压：进气道按 void 留空，发动机按金属密度占容积，避免空腔扣两次。
        # 质量锚点为鹰击-91：4.7 m × 0.36 m、战斗部 90 kg、Ma 0.9 @ 10 km，公开起飞质量约 600 kg。
        # 只按蒙皮外推时这一发只有约 460 kg。壳体与进气道改按 1.46 倍计
        # （面密度、发动机系数、发动机密度同比例，发动机容积不变），
        # 空腔从 0.28 降到 0.14，让出的容积改装煤油和助推药，燃油质量比基本不动。
        # 超燃不共用这组系数：气道里没有固体药柱，体密度应更低。
        # 苏俄标定用同尺寸的最新型，不用出口型的 MTCR 上限。
        # 缟玛瑙-M：与 P-800 同为约 8.9 m×0.70 m、约 3 t、战斗部 300 kg、舰面，
        # 塔斯社称重量尺寸和最大速度不变，最大射程 800 km（高弹道）。低弹道仍约 120 km。
        # Kh-31PD：5.34 m×0.36 m、715 kg、战斗部 110 kg，Ma 1.5 @ 15 km 时最大 180–250 km。
        # 小口径进气道在 Ma 2.8、14 km 更费油，耗油率相对 0.70 m 按弹径放大，大弹不再额外省油。
        'body_pack': 0.64,
        'areal': 40.9,
        'eng_coeff': 263.0,
        'eng_density': 1168.0,
        'payload_density': 2800.0,
        'void_frac': 0.14,
        'fuel_density': 820.0,
        'tsfc': 7.2e-5,
        'tsfc_ref_diameter_m': 0.70,
        'tsfc_diameter_exponent': 0.90,
        'tsfc_scale_min': 1.0,
        'tsfc_scale_max': 2.5,
        'mach_takeover': 1.95,
        'mach_cruise': 2.8,
        'alt_km': 14.0,
        'ld_base': 1.7,
        'ld_slope': 0.08,
        'ld_min': 2.1,
        'ld_max': 2.85,
        'eta': 0.18,
        'reserve': 0.08,
        'loss_frac': 0.16,
        'accel_excess': 0.30,
        'fuel_floor_frac': 0.28,
        'sea_alt_km': 0.015,
        'sea_mach': 2.0,
        'sea_ld_factor': 0.38,
        # 高弹道 800 km、低弹道约 120 km，掠海耗油按这个落差加重。
        'sea_tsfc_factor': 2.45,
    },
    'scramjet': {
        # 对照长剑-1000：地面发射、约 10 m × 1 m、巡航 Ma 6、30–50 km、射程约 5000–6000 km。
        # 固定进气道容积让较小弹油箱更小。
        'body_pack': 0.74,
        'areal': 22.0,
        'eng_coeff': 120.0,
        'eng_density': 300.0,
        'payload_density': 1800.0,
        'void_frac': 0.04,
        'fixed_void_m3': 0.85,
        'fuel_density': 840.0,
        'tsfc': 5.2e-5,
        'mach_takeover': 3.6,
        'mach_cruise': 6.2,
        'alt_km': 36.0,
        'ld_base': 2.4,
        'ld_slope': 0.05,
        'ld_min': 2.8,
        'ld_max': 3.8,
        'eta': 0.35,
        'reserve': 0.08,
        'loss_frac': 0.08,
        'accel_excess': 0.45,
        'fuel_floor_frac': 0.42,
    },
}

_ROCKET_CRUISE = {
    # 对照 3M54K：8.22 m×0.533 m、战斗部 200 kg、舰面/潜射，出口型 3M54E 全重 1951 kg。
    # 国内型公开估计 550–660 km，全程掠海，末端固体级约 20 km、Ma 2.9。
    # 出口型 220 km 是 MTCR 上限，不拿来标定。末端级最多占弹体两成容积，冲刺才落在 20 km 附近。
    'body_pack': 0.62,
    'areal': 36.0,
    'eng_coeff': 200.0,
    'eng_density': 650.0,
    'payload_density': 2600.0,
    'void_frac': 0.10,
    'fuel_density': 800.0,
    'tsfc': 3.95e-5,
    'mach': 0.80,
    'alt_km': 6.0,
    'ld_base': 3.4,
    'ld_slope': 0.08,
    'ld_min': 3.8,
    'ld_max': 5.0,
    'eta': 0.28,
    'sea_ld_factor': 0.90,
    'sea_tsfc_factor': 1.08,
    'reserve': 0.08,
    'sea_alt_km': 0.02,
    'folded_wing': 1.0,
    'terminal_dv_m_s': 1900.0,
    'terminal_volume_cap_frac': 0.21,
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


def resolve_missile_class(missile_class: str) -> str:
    """把弹种名收成内部 id。旧的「助推滑翔」视为双锥体助推滑翔。"""
    raw = str(missile_class).strip()
    if raw.lower() in _GENERIC_HGV or raw in _GENERIC_HGV:
        return 'hgv_biconic'
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
    return math.sqrt(1.4 * ISA_R * temperature)



def isa_density_kg_m3(altitude_km: float) -> float:
    """国际标准大气密度。11 km 以下按对流层，其上按平流层等温层。"""
    if altitude_km < 0:
        raise ValueError('高度不能为负')
    height_m = altitude_km * 1000.0
    lapse = 0.0065
    if height_m <= 11000.0:
        temperature = 288.15 - lapse * height_m
        pressure = 101325.0 * (temperature / 288.15) ** (G0 / (ISA_R * lapse))
    else:
        temperature = 216.65
        pressure_11 = 101325.0 * (216.65 / 288.15) ** (G0 / (ISA_R * lapse))
        pressure = pressure_11 * math.exp(-G0 * (min(height_m, 47000.0) - 11000.0) / (ISA_R * temperature))
    return pressure / (ISA_R * temperature)


def folded_wing_package(
    mass_kg: float,
    mach: float,
    altitude_km: float,
    diameter_m: float,
) -> tuple[float, float, float]:
    """按巡航重量定折叠弹翼，返回面积、质量和弹内占用容积。

    翼面收在给定弹径以内，所以厚度受弹径限制；质量和容积都算死重，不算出外露翼。
    """
    if mass_kg <= 0 or mach <= 0 or diameter_m <= 0:
        raise ValueError('折叠弹翼的质量、马赫数与弹径必须大于 0')
    if altitude_km < 0:
        raise ValueError('高度不能为负')
    speed = mach * speed_of_sound_m_s(altitude_km)
    dynamic = 0.5 * isa_density_kg_m3(altitude_km) * speed * speed
    if dynamic <= 1.0:
        raise ValueError('巡航动压过低，无法确定弹翼面积')
    area = mass_kg * G0 / (dynamic * FOLDED_WING_CL)
    chord = math.sqrt(area / FOLDED_WING_AR)
    thickness = FOLDED_WING_TC * chord
    limit = FOLDED_WING_THICKNESS_FRAC * diameter_m
    if thickness > limit:
        raise ValueError('弹翼厚度超过弹径，无法折进弹体')
    volume = area * thickness
    mass = FOLDED_WING_AREAL_KG_M2 * area
    return area, mass, volume


def stow_folded_wing(
    mass_kg: float,
    mach: float,
    altitude_km: float,
    diameter_m: float,
    volume_budget_m3: float,
) -> tuple[float, float, float, float]:
    """把设计弹翼收进剩余燃油舱。

    舱内容不下整翼时，按容积把面积缩小（容积约随面积的 1.5 次方），
    质量和占用容积仍计入死重。返回面积、质量、容积，以及相对设计面积的比例。
    """
    if volume_budget_m3 <= 0:
        raise ValueError('折叠弹翼占用的容积超过燃油舱')
    area, mass, volume = folded_wing_package(mass_kg, mach, altitude_km, diameter_m)
    if volume <= volume_budget_m3:
        return area, mass, volume, 1.0
    factor = (volume_budget_m3 / volume) ** (2.0 / 3.0)
    area *= factor
    mass *= factor
    chord = math.sqrt(area / FOLDED_WING_AR)
    volume = area * FOLDED_WING_TC * chord
    if volume > volume_budget_m3:
        volume = volume_budget_m3
    return area, mass, volume, factor


def deadweight_kg(
    launch_mass_kg: float,
    fuel_kg: float,
    warhead_mass_kg: float,
    propellant_kg: float = 0.0,
) -> float:
    """死重：起飞质量去掉燃油、战斗部和仍要燃烧的固体装药。折叠弹翼留在死重里。"""
    if launch_mass_kg <= 0:
        raise ValueError('起飞质量必须大于 0')
    if fuel_kg < 0 or warhead_mass_kg < 0 or propellant_kg < 0:
        raise ValueError('质量不能为负')
    dead = launch_mass_kg - fuel_kg - warhead_mass_kg - propellant_kg
    if dead <= 0:
        raise ValueError('死重必须大于 0')
    return dead


def pentagon_cross_section(
    width_m: float,
    height_m: float,
    shoulder: float,
) -> tuple[float, float]:
    """扁五边形截面的面积和周长。

    底边等于全宽，两侧升到肩部，肩以上收到顶部中点的棱。
    肩高比是肩部高度占全高的比例。LRASM、JSM 都是这种宽高不同的五边形，不是圆。
    """
    if width_m <= 0 or height_m <= 0:
        raise ValueError('截面宽和高必须大于 0')
    if not 0.05 <= shoulder <= 0.95:
        raise ValueError('五边形肩高比须在 0.05 到 0.95 之间')
    area = width_m * height_m * (0.5 + 0.5 * shoulder)
    roof = (1.0 - shoulder) * height_m
    slope = math.hypot(width_m / 2.0, roof)
    perimeter = width_m + 2.0 * shoulder * height_m + 2.0 * slope
    return area, perimeter


def outer_cross_section(
    diameter_m: float,
    spec: dict[str, float],
    width_m: float | None = None,
    height_m: float | None = None,
) -> dict[str, float]:
    """弹体外廓截面。隐身涡扇用扁五边形，其余弹种仍用圆。

    只给弹径时，弹径是最大外廓，短边按弹种的高宽比缩进去，所以装不满同一个圆。
    同时给出宽和高时，用真实外廓，不再把较长的一边当成圆直径。
    """
    shoulder = spec.get('pentagon_shoulder')
    if shoulder:
        if width_m is None and height_m is None:
            if diameter_m <= 0:
                raise ValueError('弹长与弹径必须大于 0')
            width_m = diameter_m
            height_m = diameter_m * spec['minor_over_major']
        elif width_m is None or height_m is None:
            raise ValueError('五边形截面的宽和高必须同时给出')
        area, perimeter = pentagon_cross_section(width_m, height_m, shoulder)
        minor = min(width_m, height_m)
    else:
        if diameter_m <= 0:
            raise ValueError('弹长与弹径必须大于 0')
        area = math.pi * (diameter_m / 2.0) ** 2
        perimeter = math.pi * diameter_m
        minor = diameter_m
    equivalent = 2.0 * math.sqrt(area / math.pi)
    return {
        'area': area,
        'perimeter': perimeter,
        'minor': minor,
        'd_eq': equivalent,
    }


def packed_section_volume_m3(area_m2: float, length_m: float, pack: float = BODY_PACK) -> float:
    """按外廓截面积乘弹长，再乘装填系数，得到可用内部容积。"""
    if area_m2 <= 0 or length_m <= 0:
        raise ValueError('截面积与弹长必须大于 0')
    if not 0.3 <= pack <= 0.9:
        raise ValueError('弹体装填系数须在 0.3 到 0.9 之间')
    return pack * area_m2 * length_m


def skin_mass_kg(perimeter_m: float, length_m: float, areal_kg_m2: float) -> float:
    """蒙皮、舵面与加强框。侧面积用截面周长，1.15 计入头尾封头。"""
    if perimeter_m <= 0 or length_m <= 0:
        raise ValueError('截面周长与弹长必须大于 0')
    if areal_kg_m2 <= 0:
        raise ValueError('结构面密度必须大于 0')
    return areal_kg_m2 * perimeter_m * length_m * 1.15


def body_volume_m3(length_m: float, diameter_m: float, pack: float = BODY_PACK) -> float:
    """圆截面弹体外形对应的可用内部容积。冲压弹进气道更大时 pack 更小。"""
    if not 0.3 <= pack <= 0.9:
        raise ValueError('弹体装填系数须在 0.3 到 0.9 之间')
    fineness_ratio(length_m, diameter_m)
    return pack * math.pi * (diameter_m / 2.0) ** 2 * length_m


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
    fixed_void_m3: float = 0.0,
) -> float:
    """扣掉战斗部、发动机和空腔后，留给燃油或助推药的容积。

    fixed_void_m3 是不随弹体放大的进气道/隔离段，小弹会因此少装油。
    """
    if payload_density <= 0 or engine_density <= 0:
        raise ValueError('密度必须大于 0')
    if not 0.0 <= void_frac < 0.55:
        raise ValueError('空腔比例须在 0 到 0.55 之间')
    if fixed_void_m3 < 0:
        raise ValueError('固定空腔容积不能为负')
    # 进气道再长也不能超过弹体四成，否则小口径弹会没有油箱
    fixed_void_m3 = min(fixed_void_m3, 0.40 * body_volume)
    leftover = (
        body_volume
        - payload_mass / payload_density
        - engine_mass / engine_density
        - void_frac * body_volume
        - fixed_void_m3
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


def jettisoned_booster_propellant_kg(
    cruise_mass_kg: float,
    launch_speed_m_s: float,
    h_launch_km: float,
) -> float:
    """低速发射所需的可抛弃固体助推药。

    发射速度已经达到接力马赫数时返回 0。助推器随后抛弃，不进入巡航质量。
    """
    if cruise_mass_kg <= 0:
        raise ValueError('巡航质量必须大于 0')
    if launch_speed_m_s < 0 or h_launch_km < 0:
        raise ValueError('发射速度与高度不能为负')
    takeover = SUBSONIC_TAKEOVER_MACH * speed_of_sound_m_s(h_launch_km)
    if launch_speed_m_s >= takeover:
        return 0.0
    loss = SUBSONIC_BOOSTER_LOSS * math.exp(-h_launch_km / BALLISTIC_DRAG_SCALE_KM)
    dv = (takeover - launch_speed_m_s) * (1.0 + loss)
    ve = SUBSONIC_BOOSTER_ISP_S * G0
    return cruise_mass_kg * (math.exp(dv / ve) - 1.0)


def booster_grain_volume_m3(propellant_kg: float) -> float:
    """助推药挤占的燃油舱容积。喷管在油箱外，只计入药柱容积的一部分。"""
    if propellant_kg < 0:
        raise ValueError('助推药质量不能为负')
    if propellant_kg == 0:
        return 0.0
    grain = propellant_kg / (DEFAULT_PROPELLANT_DENSITY * BOOST_FILL)
    return grain * BOOSTER_TANK_SHARE


def dense_air_loss_frac(loss_frac: float, h_launch_km: float) -> float:
    """亚燃助推损失份额：10 km 及以上不变，海平面约为该值的 1.8 倍。"""
    if loss_frac < 0 or h_launch_km < 0:
        raise ValueError('损失份额与高度不能为负')
    at_ref = math.exp(-RAMJET_LOSS_REF_KM / BALLISTIC_DRAG_SCALE_KM)
    extra = max(0.0, math.exp(-h_launch_km / BALLISTIC_DRAG_SCALE_KM) - at_ref)
    span = 1.0 - at_ref
    return loss_frac * (1.0 + RAMJET_SURFACE_LOSS_GAIN * extra / span)


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
    width_m: float | None = None,
    height_m: float | None = None,
) -> dict[str, float]:
    """全高空与全掠海巡航航程。预留容积和惰性质量给末端火箭。

    亚音速弹种带折叠弹翼时，翼面质量和占用容积从燃油舱里扣出，计入死重。
    发射速度低于接力马赫数时，可抛弃助推器再占一截燃油舱，巡航质量不含助推器。
    隐身涡扇可另给宽和高，按扁五边形算容积，不再把较长的一边当成圆直径。
    """
    if v_launch_mach < 0 or h_launch_km < 0:
        raise ValueError('发射马赫数与高度不能为负')
    if reserved_volume_m3 < 0 or inert_mass_kg < 0:
        raise ValueError('预留容积与附加质量不能为负')
    if length_m <= 0:
        raise ValueError('弹长与弹径必须大于 0')
    section = outer_cross_section(diameter_m, spec, width_m, height_m)
    volume = packed_section_volume_m3(
        section['area'], length_m, spec.get('body_pack', BODY_PACK),
    )
    payload = payload_mass_kg(warhead_mass_kg)
    structure = skin_mass_kg(section['perimeter'], length_m, spec['areal'])
    engine = engine_mass_kg(length_m, section['d_eq'], spec['eng_coeff'])
    tank = energy_volume_m3(
        volume, payload, spec['payload_density'], engine, spec['eng_density'], spec['void_frac'],
        spec.get('fixed_void_m3', 0.0),
    )
    launch_speed = v_launch_mach * speed_of_sound_m_s(h_launch_km)
    wing_area = 0.0
    wing_mass = 0.0
    wing_volume = 0.0
    wing_fill = 1.0
    fuel_slot_m3 = 0.006
    booster_prop = 0.0
    if spec.get('folded_wing', 0.0) > 0.0:
        guess = payload + structure + engine + tank * spec['fuel_density'] + inert_mass_kg
        fuel_kg = 0.0
        for _ in range(12):
            booster_volume = booster_grain_volume_m3(booster_prop)
            budget = tank - reserved_volume_m3 - fuel_slot_m3 - booster_volume
            if budget <= 0.02:
                raise ValueError('助推器占用的容积超过燃油舱')
            wing_area, wing_mass, wing_volume, wing_fill = stow_folded_wing(
                guess, spec['mach'], spec['alt_km'], section['minor'], budget,
            )
            free = tank - wing_volume - booster_volume
            if reserved_volume_m3 >= free:
                raise ValueError('末端火箭占用的容积超过燃油舱')
            fuel_kg = (free - reserved_volume_m3) * spec['fuel_density']
            cruise_mass = payload + structure + engine + fuel_kg + inert_mass_kg + wing_mass
            booster_prop = jettisoned_booster_propellant_kg(
                cruise_mass, launch_speed, h_launch_km,
            )
            guess = 0.35 * guess + 0.65 * cruise_mass
        booster_volume = booster_grain_volume_m3(booster_prop)
        free = tank - wing_volume - booster_volume
        if reserved_volume_m3 >= free:
            raise ValueError('末端火箭占用的容积超过燃油舱')
        fuel_kg = (free - reserved_volume_m3) * spec['fuel_density']
        launch_mass = payload + structure + engine + fuel_kg + inert_mass_kg + wing_mass
        booster_prop = jettisoned_booster_propellant_kg(launch_mass, launch_speed, h_launch_km)
    else:
        launch_mass = payload + structure + engine + inert_mass_kg
        fuel_kg = 0.0
        for _ in range(8):
            booster_volume = booster_grain_volume_m3(booster_prop)
            free = tank - booster_volume
            if reserved_volume_m3 >= free:
                raise ValueError('末端火箭占用的容积超过燃油舱')
            fuel_kg = (free - reserved_volume_m3) * spec['fuel_density']
            launch_mass = payload + structure + engine + fuel_kg + inert_mass_kg
            booster_prop = jettisoned_booster_propellant_kg(
                launch_mass, launch_speed, h_launch_km,
            )
        booster_volume = booster_grain_volume_m3(booster_prop)
        free = tank - booster_volume
        if reserved_volume_m3 >= free:
            raise ValueError('末端火箭占用的容积超过燃油舱')
        fuel_kg = (free - reserved_volume_m3) * spec['fuel_density']
        launch_mass = payload + structure + engine + fuel_kg + inert_mass_kg
        booster_prop = jettisoned_booster_propellant_kg(launch_mass, launch_speed, h_launch_km)
    if fuel_kg <= 1.0:
        raise ValueError('燃油过少，无法巡航')
    booster_mass = booster_prop * (1.0 + BOOST_CASE_FRAC)
    ld = subsonic_ld(length_m, section['d_eq'], spec)
    if wing_fill < 1.0:
        ld *= 0.55 + 0.45 * wing_fill
    sound_hi = speed_of_sound_m_s(spec['alt_km'])
    sound_sea = speed_of_sound_m_s(spec['sea_alt_km'])
    speed_hi = spec['mach'] * sound_hi
    speed_sea = spec['mach'] * sound_sea
    # 助推器把弹推到接力速度后抛弃，涡扇只补剩余的加速和爬升。
    speed_after_boost = launch_speed
    if booster_prop > 0.0:
        speed_after_boost = max(
            launch_speed, SUBSONIC_TAKEOVER_MACH * speed_of_sound_m_s(h_launch_km),
        )
    climb = climb_fuel_kg(
        launch_mass,
        (spec['alt_km'] - h_launch_km) * 1000.0,
        speed_hi ** 2 - speed_after_boost ** 2,
        spec['eta'],
    )
    climb = min(climb, fuel_kg * 0.40)
    climb_sea = climb_fuel_kg(
        launch_mass,
        (spec['sea_alt_km'] - h_launch_km) * 1000.0,
        speed_sea ** 2 - speed_after_boost ** 2,
        spec['eta'],
    )
    climb_sea = min(climb_sea, fuel_kg * 0.40)
    usable_hi = max(0.0, fuel_kg - climb) * (1.0 - spec['reserve'])
    usable_sea = max(0.0, fuel_kg - climb_sea) * (1.0 - spec['reserve'])
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
    head_len = min(length_m * 0.45, bay / max(section['area'], 1e-6))
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
        'm_structure': structure,
        'm_payload': payload,
        'm_wing_kg': wing_mass,
        'wing_area_m2': wing_area,
        'wing_volume_m3': wing_volume,
        'wing_fill': wing_fill,
        'usable_high_kg': usable_hi,
        'usable_sea_kg': usable_sea,
        'm_booster_kg': booster_mass,
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


def duct_cruise_tsfc(missile_class: str, diameter_m: float, spec: dict[str, float]) -> float:
    """巡航耗油率。亚燃相对参考弹径放大细弹的进气道损失。

    弹径大于参考值时耗油率不再下降，大弹只靠燃油比变远。
    """
    tsfc = spec['tsfc']
    exponent = spec.get('tsfc_diameter_exponent', 0.0)
    if exponent <= 0:
        return tsfc
    if diameter_m <= 0:
        raise ValueError('弹径必须大于 0')
    ref = spec.get('tsfc_ref_diameter_m', diameter_m)
    if ref <= 0:
        raise ValueError('耗油率参考弹径必须大于 0')
    scale = (ref / diameter_m) ** exponent
    return tsfc * clamp(
        scale,
        spec.get('tsfc_scale_min', 1.0),
        spec.get('tsfc_scale_max', 2.5),
    )


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


def ballistic_liftoff_twr(launch_mass_kg: float) -> float:
    """起飞推重比：轻型战术弹更高，重弹趋近 2.3。"""
    if launch_mass_kg <= 0:
        raise ValueError('起飞质量必须大于 0')
    extra = BALLISTIC_TWR_LIGHT_EXTRA * math.exp(-launch_mass_kg / BALLISTIC_TWR_SCALE_KG)
    return BALLISTIC_TWR_HEAVY + extra


def ballistic_loss_m_s(dv_ideal_m_s: float, burn_time_s: float, launch_altitude_km: float) -> float:
    """重力损失按燃烧时间计，阻力随发射高度按大气标高衰减。

    燃烧明显长于地面标定弹时，海平面再加一段与超时成正比的阻力。
    高度够高时这一项随大气变薄，空射不再改用滑翔弹的固定损失。
    """
    if dv_ideal_m_s < 0 or burn_time_s < 0 or launch_altitude_km < 0:
        raise ValueError('速度增量、燃烧时间与高度不能为负')
    drag_scale = math.exp(-launch_altitude_km / BALLISTIC_DRAG_SCALE_KM)
    gravity = G0 * burn_time_s * BALLISTIC_GRAVITY_FACTOR
    drag = (BALLISTIC_DRAG_FRACTION * dv_ideal_m_s + BALLISTIC_DRAG_BIAS_M_S) * drag_scale
    extra_burn = max(0.0, burn_time_s - BALLISTIC_LONG_BURN_S)
    drag += extra_burn * BALLISTIC_LONG_BURN_DRAG_M_S * drag_scale
    return gravity + drag


def ballistic_burn_time_s(
    propellant_kg: float,
    launch_mass_kg: float,
    isp_s: float,
    twr: float = BALLISTIC_TWR_HEAVY,
) -> float:
    """按起飞推重比估算燃烧时间。弹道弹传入轻弹更高的推重比；冲压助推沿用 2.3。"""
    if launch_mass_kg <= 0 or propellant_kg < 0 or isp_s <= 0 or twr <= 0:
        raise ValueError('弹道弹燃烧时间参数无效')
    return propellant_kg * isp_s / (twr * launch_mass_kg)


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
    m_dead_kg: float | None = None,
    m_wing_kg: float | None = None,
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
        'm_dead_kg': None if m_dead_kg is None else round(m_dead_kg, 1),
        'm_wing_kg': None if m_wing_kg is None else round(m_wing_kg, 1),
        'note': note,
    }


def estimate_subsonic_class(
    missile_class: str,
    length_m: float,
    diameter_m: float,
    warhead_mass_kg: float,
    v_launch_mach: float,
    h_launch_km: float,
    width_m: float | None = None,
    height_m: float | None = None,
) -> dict:
    """涡扇隐身或涡喷非隐身的全高空、全掠海射程。

    隐身涡扇可另给宽和高。不给时，弹径是最大外廓，短边按弹种高宽比收成扁五边形。
    """
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
        width_m=width_m,
        height_m=height_m,
    )
    high_km = sized['range_high_m'] / 1000.0
    sea_km = sized['range_sea_m'] / 1000.0
    ignition = sized['m_0'] + sized['m_booster_kg']
    dead = deadweight_kg(ignition, sized['fuel_kg'], warhead_mass_kg, sized['m_booster_kg'])
    fit = '' if sized['wing_fill'] >= 0.995 else f"弹舱只能放下设计翼面积的 {sized['wing_fill'] * 100:.0f}%。"
    boost_txt = ''
    if sized['m_booster_kg'] > 1.0:
        boost_txt = f"可抛弃助推器 {sized['m_booster_kg']:.0f} kg。"
    note = (
        f"{class_label(canon)}：主射程为全高空 {spec['alt_km']:.0f} km、"
        f"Ma {spec['mach']:.2f}；全掠海为 {spec['sea_alt_km'] * 1000:.0f} m。"
        f"升阻比 {sized['ld']:.2f}，耗油率按弹种固定。"
        f"{boost_txt}折叠弹翼 {sized['m_wing_kg']:.0f} kg，死重 {dead:.0f} kg。{fit}"
    )
    return _base_fields(
        canon, ignition, sized['l_head_m'], length_m - sized['l_head_m'],
        sized['fuel_kg'], spec['mach'], sized['ld'], high_km, note,
        range_high_km=high_km, range_sea_km=sea_km,
        range_cruise_km=high_km, cruise_mach=spec['mach'], cruise_alt_km=spec['alt_km'],
        m_dead_kg=dead, m_wing_kg=sized['m_wing_kg'],
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
    volume = body_volume_m3(length_m, diameter_m, spec.get('body_pack', BODY_PACK))
    payload = payload_mass_kg(warhead_mass_kg)
    structure = structural_mass_kg(length_m, diameter_m, spec['areal'])
    engine = engine_mass_kg(length_m, diameter_m, spec['eng_coeff'])
    tank = energy_volume_m3(
        volume, payload, spec['payload_density'], engine, spec['eng_density'], spec['void_frac'],
        spec.get('fixed_void_m3', 0.0),
    )
    sound = speed_of_sound_m_s(spec['alt_km'])
    launch_speed = v_launch_mach * speed_of_sound_m_s(h_launch_km)
    takeover_speed = spec['mach_takeover'] * sound
    gap = max(0.0, takeover_speed - launch_speed)
    loss_frac = spec['loss_frac']
    if canon == 'ramjet':
        loss_frac = dense_air_loss_frac(loss_frac, h_launch_km)
    dv_need = gap * (1.0 + loss_frac) + (0.0 if gap == 0 else 80.0)
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
    tsfc = duct_cruise_tsfc(canon, diameter_m, spec)
    isp_air = 1.0 / (tsfc * G0)
    mass_after_boost = launch_mass - propellant
    accel_frac = 0.0 if accel <= 1.0 else 1.0 - math.exp(-accel / (isp_air * G0 * spec['accel_excess']))
    accel_fuel = min(fuel * 0.65, accel_frac * mass_after_boost)
    climb = climb_fuel_kg(
        mass_after_boost,
        (spec['alt_km'] - h_launch_km) * 1000.0,
        cruise_speed ** 2 - speed_after ** 2,
        spec['eta'],
    )
    climb = min(climb, max(0.0, fuel - accel_fuel) * 0.40)
    cruise_fuel = max(0.0, fuel - accel_fuel - climb) * (1.0 - spec['reserve'])
    if cruise_fuel <= 1.0:
        raise ValueError('冲压燃油不足以完成巡航')
    ld = duct_ld(length_m, diameter_m, spec)
    cruise_m = breguet_cruise_range_m(
        cruise_speed, tsfc, ld, mass_after_boost, mass_after_boost - cruise_fuel,
    )
    burn_time = ballistic_burn_time_s(propellant, launch_mass, isp_s) if propellant > 0 else 0.0
    boost_range = 0.5 * (launch_speed + min(speed_after, cruise_speed)) * burn_time
    high_km = (cruise_m + boost_range) / 1000.0
    sea_km = None
    if spec.get('sea_alt_km') is not None:
        sea_sound = speed_of_sound_m_s(spec['sea_alt_km'])
        sea_speed = spec.get('sea_mach', 2.0) * sea_sound
        sea_ld = ld * spec.get('sea_ld_factor', 0.42)
        sea_tsfc = tsfc * spec.get('sea_tsfc_factor', 1.3)
        sea_fuel = max(0.0, fuel - accel_fuel) * (1.0 - spec['reserve'])
        if sea_fuel > 1.0 and sea_ld > 0:
            sea_m = breguet_cruise_range_m(
                sea_speed, sea_tsfc, sea_ld, mass_after_boost, mass_after_boost - sea_fuel,
            )
            sea_km = (sea_m + boost_range) / 1000.0
    dead = deadweight_kg(launch_mass, fuel, warhead_mass_kg, propellant)
    bay = payload / spec['payload_density']
    section = math.pi * (diameter_m / 2.0) ** 2
    head_len = min(length_m * 0.45, bay / section)
    trimmed = '' if reached else '接力装药不足，巡航马赫已下调。'
    sea_txt = '' if sea_km is None else f'全掠海 {sea_km:.0f} km。'
    note = (
        f"{class_label(canon)}：高空巡航 Ma {cruise_mach:.2f} @ {spec['alt_km']:.0f} km，"
        f"设计 Ma {spec['mach_cruise']:.1f}。{trimmed}{sea_txt}"
        f"死重 {dead:.0f} kg。"
    )
    return _base_fields(
        canon, launch_mass, head_len, length_m - head_len, fuel + propellant,
        cruise_mach, ld, high_km, note,
        range_high_km=high_km if sea_km is not None else None,
        range_sea_km=sea_km,
        range_cruise_km=cruise_m / 1000.0,
        cruise_mach=cruise_mach, cruise_alt_km=spec['alt_km'],
        m_dead_kg=dead,
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
    """按较重的巡航终点质量迭代末端装药。折叠弹翼先占燃油舱，装药不得挤掉弹翼。"""
    volume = body_volume_m3(length_m, diameter_m, spec.get('body_pack', BODY_PACK))
    propellant_cap = volume * spec['terminal_volume_cap_frac'] * TERMINAL_FILL * propellant_density
    ve = isp_s * G0
    propellant = 0.0
    sized: dict[str, float] = {}
    for _ in range(16):
        reserved = propellant / (TERMINAL_FILL * propellant_density) if propellant > 0 else 0.0
        case_mass = propellant * (1.0 - TERMINAL_PMF) / TERMINAL_PMF
        try:
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
        except ValueError as exc:
            if '容积' not in str(exc):
                raise
            propellant_cap *= 0.55
            propellant = min(propellant, propellant_cap) * 0.55
            continue
        mass_ign = sized['m_0'] - sized['usable_high_kg']
        needed = mass_ign * (1.0 - math.exp(-spec['terminal_dv_m_s'] / ve))
        propellant = min(propellant_cap, 0.5 * propellant + 0.5 * needed)
    for _ in range(8):
        reserved = propellant / (TERMINAL_FILL * propellant_density) if propellant > 0 else 0.0
        case_mass = propellant * (1.0 - TERMINAL_PMF) / TERMINAL_PMF
        try:
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
            break
        except ValueError as exc:
            if '容积' not in str(exc) or propellant <= 0.5:
                raise
            propellant *= 0.5
    else:
        raise ValueError('折叠弹翼占用的容积超过燃油舱')
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
    ignition = sized['m_0'] + sized['m_booster_kg']
    dead = deadweight_kg(
        ignition, sized['fuel_kg'], warhead_mass_kg, propellant + sized['m_booster_kg'],
    )
    fit = '' if sized['wing_fill'] >= 0.995 else f"弹舱只能放下设计翼面积的 {sized['wing_fill'] * 100:.0f}%。"
    boost_txt = ''
    if sized['m_booster_kg'] > 1.0:
        boost_txt = f"可抛弃助推器 {sized['m_booster_kg']:.0f} kg。"
    note = (
        f"亚超结合：涡扇巡航 Ma {spec['mach']:.2f}，"
        f"全高空 {spec['alt_km']:.0f} km / 全掠海 {spec['sea_alt_km'] * 1000:.0f} m，"
        f"末端火箭冲刺 {dash / 1000.0:.1f} km。"
        f"{boost_txt}折叠弹翼 {sized['m_wing_kg']:.0f} kg，死重 {dead:.0f} kg。{fit}"
    )
    return _base_fields(
        'turbofan_rocket', ignition, sized['l_head_m'], length_m - sized['l_head_m'],
        sized['fuel_kg'] + propellant, spec['mach'], sized['ld'], high_km, note,
        range_high_km=high_km, range_sea_km=sea_km,
        range_cruise_km=sized['range_high_m'] / 1000.0,
        range_terminal_km=dash / 1000.0,
        cruise_mach=spec['mach'], cruise_alt_km=spec['alt_km'],
        m_dead_kg=dead, m_wing_kg=sized['m_wing_kg'],
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
    burn_time = ballistic_burn_time_s(
        propellant, launch_mass, isp_s, ballistic_liftoff_twr(launch_mass),
    )
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
    v_launch_mach: float = 0.85,
    h_launch_km: float = 13.0,
    isp_s: float = DEFAULT_ISP_S,
    propellant_density: float = DEFAULT_PROPELLANT_DENSITY,
    width_m: float | None = None,
    height_m: float | None = None,
) -> dict:
    """按弹种估算。双锥体和乘波体助推滑翔由 missile_class 区分。

    隐身涡扇的宽和高可选。给出后按扁五边形外廓算质量，不再把弹径当成圆。
    """
    canon = resolve_missile_class(missile_class)
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
            width_m, height_m,
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
