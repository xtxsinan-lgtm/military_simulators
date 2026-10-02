"""六类导弹的射程估算：超燃、亚燃、涡扇隐身、涡喷非隐身、亚超结合、弹道。

亚音速与冲压巡航用布雷盖航程，比冲由吸气耗油率换算，明显高于固体火箭。
带助推器的吸气弹把比冲拆成两段：助推用固体比冲，巡航用吸气比冲。
全高空统一 10 km，全掠海统一 30 m。掠海升阻比按该高度的动压、废阻和诱导阻力计算，不再用固定的全掠海/全高空射程比去缩放。
非高超巡航弹另给一条混合弹道：大部分燃油在 10 km 飞，中空搜索和末段掠海的长度由雷达视距决定，燃油从终点往回扣。
低速发射的亚音速弹先扣一截可抛弃固体助推器，助推器占燃油舱、不带进巡航质量。
冲压弹先用固体火箭助推到接力马赫数，再用剩余燃油巡航。接不上接力马赫数时只计助推后的弹道弧。
亚燃是固冲一体：药柱铸在燃烧室里，和煤油分同一块能源容积。
超燃不是双模态，燃烧室留空，固体助推器单独占舱，燃油用高密度吸热型液体碳氢燃料。
亚燃在 10 km 以下按稠密大气加大助推损失。超燃地面发射不加这一档，巡航高度仍按超燃设计点，不改到 10 km。
亚超结合的巡航比冲与涡扇同一档，末端冲刺统一按伯克级雷达对掠海目标的视距计入。
普通弹道导弹只在前方用头锥：按长径比算圆锥容积，制导和战斗部先扣掉头锥，剩下的头锥和后面的圆柱都装药。
弹道弹是否两级由显式开关控制，默认两级。燃烧明显长于地面标定弹时，海平面再加一段大气阻力。
关机后的真空弹道再按弹道系数折减大气滑行阻力。
轻型战术弹推重比更高，地面 4 m 级默认两级时按 PrSM 的 499 km 标定。
"""
from __future__ import annotations

import math

from utils.missile_interception.missile_interception_radar import radar_horizon_km
from utils.missile_range.estimate import (
    DEFAULT_ISP_S,
    DEFAULT_PROPELLANT_DENSITY,
    G0,
    CHAMBER_FILL,
    PROPELLANT_MASS_FRACTION,
    R_EARTH_M,
    head_and_booster_lengths_m,
    glide_body_mass_kg,
    motor_cross_section_m2,
    propellant_mass_kg,
)

LHV_J_KG = 43.0e6
ISA_R = 287.05287
# 折叠弹翼：高空巡航设计升力系数、展弦比、相对厚度，面密度含折叠铰链。
# 奥斯瓦尔德效率计入弹体对诱导阻力的干扰，低于孤立机翼。
FOLDED_WING_CL = 0.65
FOLDED_WING_AR = 5.0
FOLDED_WING_OSWALD = 0.75
FOLDED_WING_TC = 0.08
# 有全高空/全掠海两档的弹种共用这一对高度。超燃没有掠海档，不使用。
CRUISE_HIGH_ALT_KM = 10.0
CRUISE_SEA_ALT_KM = 0.030
# 中空搜索视距取掠海末段的倍数，用来罩住高空巡航积下的惯导散布。
GUIDANCE_SEARCH_HORIZON_FACTOR = 3.0
FOLDED_WING_AREAL_KG_M2 = 42.0
# 折进弹体后，翼盒厚度不得超过弹径的这一比例
FOLDED_WING_THICKNESS_FRAC = 0.45
BODY_PACK = 0.68
BOOST_FILL = 0.76
TERMINAL_FILL = 0.78
TERMINAL_PMF = 0.85
BOOST_CASE_FRAC = 0.12
# 重型弹道弹起飞推重比。轻弹按质量再加上一截：战术固体火箭燃烧更短。
# 4.0 m × 0.43 m、战斗部 91 kg、地面静止发射，默认两级时标定到 PrSM 的 499 km。
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
# 头锥长径比。圆锥半角约 11°，只占弹头前方，后面的发动机仍是圆柱。
BALLISTIC_NOSE_FINENESS = 2.5
# 战斗部（炸药和壳体）当量密度。制导舱更疏，按封装密度另计。
BALLISTIC_WARHEAD_DENSITY_KG_M3 = 1650.0
BALLISTIC_GUIDANCE_DENSITY_KG_M3 = 900.0
# 制导与舵机：电子舱有一个下限，其余随截面积。
BALLISTIC_GUIDANCE_FLOOR_KG = 10.0
BALLISTIC_GUIDANCE_AREA_KG_M2 = 160.0
# 头锥加战斗部舱最长占全长的这一比例，其余留给发动机。
BALLISTIC_HEAD_LENGTH_CAP = 0.65
# 关机后大气滑行。动压高、弹道系数低、关机高度低的弹减得多。
# 系数使 4.0 m × 0.43 m、战斗部 91 kg 的地面发射在默认两级时为 PrSM 的 499 km。
BALLISTIC_COAST_K = 0.0011945
# 亚音速发动机接力马赫数。更慢的发射要带可抛弃固体助推器。
SUBSONIC_TAKEOVER_MACH = 0.62
SUBSONIC_BOOSTER_ISP_S = 235.0
# 表单把吸气比冲圆到 0.1 s 再送回时，仍用标定耗油率，避免航程被小数往返带动。
ISP_MATCH_TOL_S = 0.25
# 海平面从静止推到接力速度时，重力与阻力约占理想速度增量的 45%，随高度衰减。
SUBSONIC_BOOSTER_LOSS = 0.45
# 药柱只有一部分挤占燃油舱，喷管和尾裙落在油箱以外。
BOOSTER_TANK_SHARE = 0.50
# 亚燃助推损失在 10 km 标定高度以上不变；海平面提高到约 1.8 倍。
# 超燃固体助推直接推到超燃接力，地面发射不加这一档。
RAMJET_LOSS_REF_KM = 10.0
RAMJET_SURFACE_LOSS_GAIN = 0.80
# 加速耗油不超过全部燃油的这一比例。
DUCT_ACCEL_FUEL_CAP = 0.65
# 高密度吸热型液体碳氢燃料，密度高于普通煤油，按 0.98 g/cm³。
SCRAMJET_ENDOTHERMIC_FUEL_KG_M3 = 980.0
# 超燃燃烧室流道：直径约为弹径的 55%，长度不超过弹长的 25%，也不超过 8 倍弹径。
SCRAMJET_COMBUSTOR_DIAMETER_FRAC = 0.55
SCRAMJET_COMBUSTOR_LENGTH_FRAC = 0.25
SCRAMJET_COMBUSTOR_FINENESS = 8.0
TERMINAL_COAST_CAP_M = 150000.0
RHO_SEA_KG_M3 = 1.225
TERMINAL_CD = 0.40
# 伯克级雷达天线中心高度，与拦截模型舰载雷达同一档。
BURKE_RADAR_HEIGHT_M = 25.0
# 掠海来袭弹高度，与拦截模型掠海目标同一档。
BURKE_SEA_TARGET_HEIGHT_M = 10.0

MISSILE_CLASS_ORDER: list[dict[str, str]] = [
    {
        'id': 'hgv_biconic',
        'label': '双锥体助推滑翔',
        'blurb': '两级固体助推。双锥体底径锁定为弹径，只搜索长度：先保证战斗部、制导与控制组件容积和气动长细比，壳体按湿面积计，再把剩余长度留给助推级，按底径对应的半锥角估算升阻比并积分滑翔航程。',
    },
    {
        'id': 'hgv_waverider',
        'label': '乘波体助推滑翔',
        'blurb': '两级固体助推。乘波体前段为扁平三角，后缘锁定为弹径，只搜索长度。升阻比高于同长的双锥体，容积更扁，同样战斗部会更长；壳体按湿面积计，剩余长度留给助推级并积分滑翔航程。',
    },
    {
        'id': 'scramjet',
        'label': '超燃冲压导弹',
        'blurb': '固体助推器与超燃燃烧室分开，不是双模态。助推到超燃接力后，用高密度吸热型液体碳氢燃料巡航。助推用固体比冲，巡航用吸气比冲。',
    },
    {
        'id': 'ramjet',
        'label': '亚燃冲压导弹',
        'blurb': '固冲一体：固体药柱铸在亚燃燃烧室里，和煤油分同一块能源容积。助推用固体比冲，巡航用更高的吸气比冲。全高空 10 km 与全掠海 30 m 分开算，掠海升阻比按动压下的阻力，不按固定射程比缩放；更细的弹巡航比冲按弹径下降。另给高空巡航、中空搜索、末段掠海的混合弹道，两段末端长度由雷达视距决定。',
    },
    {
        'id': 'turbofan_stealth',
        'label': '涡扇亚音速隐身巡航',
        'blurb': '涡扇吸气比冲远高于固体火箭。低速发射另加一截可抛弃固体助推器，助推与巡航比冲分开算。弹体按扁五边形而不是圆。全高空 10 km 与全掠海 30 m 分开算，掠海升阻比按动压下的阻力。另给高空巡航、中空搜索、末段掠海的混合弹道，两段末端长度由雷达视距决定。弹翼折叠在弹体内，质量计入死重，占用容积不再装油。',
    },
    {
        'id': 'turbojet_subsonic',
        'label': '涡喷亚音速非隐身巡航',
        'blurb': '涡喷吸气比冲高于固体火箭，但低于涡扇。低速发射的可抛弃助推器另按固体比冲计。全高空 10 km 与全掠海 30 m 分开算，掠海升阻比按动压下的阻力。另给高空巡航、中空搜索、末段掠海的混合弹道，两段末端长度由雷达视距决定。弹翼折叠在弹体内，质量计入死重，占用容积不再装油。',
    },
    {
        'id': 'turbofan_rocket',
        'label': '亚超结合导弹',
        'blurb': '巡航段用涡扇吸气比冲。末端冲刺不单列，统一按伯克级雷达对掠海目标的地球曲率视距加进总射程。低速发射还可再带一截比冲更低的可抛弃助推器。全高空 10 km 与全掠海 30 m 都加上同一段视距，掠海升阻比按动压下的阻力。混合弹道在高空巡航后做中空搜索，末段仍用这一段视距，不再另飞亚音速掠海。弹翼折叠在弹体内。',
    },
    {
        'id': 'ballistic',
        'label': '普通弹道导弹',
        'blurb': '头锥按长径比占一段容积，制导和战斗部从中扣除，剩下的头锥和后面的圆柱都装固体药。关机后取最优弹道弧并计入大气滑行阻力，不含滑翔增程。',
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
        'alt_km': CRUISE_HIGH_ALT_KM,
        'ld_base': 4.2,
        'ld_slope': 0.16,
        'ld_min': 4.6,
        'ld_max': 6.6,
        'eta': 0.32,
        # 高空升阻比仍按长细比。掠海不再乘固定系数，见 sea_skim_ld。
        'reserve': 0.08,
        'sea_alt_km': CRUISE_SEA_ALT_KM,
        'folded_wing': 1.0,
    },
    'turbojet_subsonic': {
        # 小涡喷（鱼叉、飞鱼一类）比冲约 2800 s，耗油率约 1.2 lb/(lbf·h)。
        # 隐身涡扇约 4743 s，两者大约差 1.7 倍，不再把短射程全部压进 1500 s。
        'body_pack': 0.64,
        'areal': 18.0,
        'eng_coeff': 210.0,
        'eng_density': 580.0,
        'payload_density': 2100.0,
        'void_frac': 0.10,
        'fuel_density': 800.0,
        'tsfc': 1.0 / (2800.0 * G0),
        'mach': 0.80,
        'alt_km': CRUISE_HIGH_ALT_KM,
        'ld_base': 3.6,
        'ld_slope': 0.12,
        'ld_min': 4.0,
        'ld_max': 5.8,
        'eta': 0.22,
        'reserve': 0.08,
        'sea_alt_km': CRUISE_SEA_ALT_KM,
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
        # 超燃不共用这组系数：燃烧室不铸药柱，固体助推器另占一舱。
        # 质量锚在鹰击-15：简氏外形约 6.5 m×0.50 m、战斗部 200 kg、
        # Ma 0.9 @ 12 km 空射，公开估计约 1.5 t。装填 0.805 才够这发装到 1.5 t；
        # 鹰击-91 会因此略重于公开的 600 kg。质量不跟着航程一起放宽。
        # 航程与助推滑翔同一档乐观：公开高空约 800 km，这里用偏高的吸气比冲和升阻比，
        # 同一发落到约 1100 km。0.50 m 及以上共用这一代耗油率。
        # 更细的弹（Kh-31PD）按弹径加耗油，避免小弹跟着变远。
        'body_pack': 0.805,
        'areal': 40.9,
        'eng_coeff': 263.0,
        'eng_density': 1168.0,
        'payload_density': 2800.0,
        'void_frac': 0.14,
        'fuel_density': 820.0,
        # 1500 s：煤油亚燃偏乐观的一档，高于按鹰击-15 公开 800 km 反推的约 1250 s。
        'tsfc': 1.0 / (1500.0 * G0),
        'tsfc_ref_diameter_m': 0.50,
        'tsfc_diameter_exponent': 2.2,
        'tsfc_wide_exponent': 0.0,
        'tsfc_scale_min': 1.0,
        'tsfc_scale_max': 2.5,
        'mach_takeover': 1.95,
        'mach_cruise': 2.8,
        'alt_km': CRUISE_HIGH_ALT_KM,
        # 亚燃弹翼比折叠巡航翼小。设计升力系数只用来拆开诱导阻力和废阻。
        'wing_cl': 0.40,
        'wing_ar': 2.5,
        'wing_oswald': 0.70,
        'ld_base': 1.95,
        'ld_slope': 0.085,
        'ld_min': 2.35,
        'ld_max': 3.25,
        'eta': 0.21,
        'reserve': 0.08,
        'loss_frac': 0.13,
        'accel_excess': 0.30,
        'fuel_floor_frac': 0.28,
        'sea_alt_km': CRUISE_SEA_ALT_KM,
        'sea_mach': 2.0,
    },
    'scramjet': {
        # 不是双模态，也不把药柱铸进燃烧室。燃烧室流道另算，先从能源容积里扣掉。
        # 固体助推器单独占舱，剩下的才装高密度吸热型液体碳氢燃料。
        # 碳氢超燃在约 Ma 4.2 接力，巡航点仍取 Ma 5.2、24 km、比冲约 1200 s。
        # 隔离段固定占 0.22 m³，这段是进气道而不是燃烧室。
        'body_pack': 0.78,
        'areal': 36.0,
        'eng_coeff': 220.0,
        'eng_density': 1050.0,
        'payload_density': 2400.0,
        'void_frac': 0.11,
        'fixed_void_m3': 0.22,
        'fuel_density': SCRAMJET_ENDOTHERMIC_FUEL_KG_M3,
        'tsfc': 1.0 / (1200.0 * G0),
        'mach_takeover': 4.2,
        'mach_cruise': 5.2,
        'alt_km': 24.0,
        'ld_base': 2.35,
        'ld_slope': 0.05,
        'ld_min': 2.6,
        'ld_max': 3.6,
        'eta': 0.32,
        'reserve': 0.08,
        'loss_frac': 0.10,
        'accel_excess': 0.55,
        'fuel_floor_frac': 0.32,
    },
}

_ROCKET_CRUISE = {
    # 对照 3M54K：8.22 m×0.533 m、战斗部 200 kg、舰面/潜射，出口型 3M54E 全重 1951 kg。
    # 巡航是涡扇，比冲与隐身涡扇同一档，不再低于涡喷。
    # 出口型 220 km 是 MTCR 上限，不拿来标定。末端级最多占弹体两成容积。
    # 末端冲刺距离不按装药反推，统一用伯克级雷达视距。
    # 视距在全高空和全掠海两端相同，不进升阻比。
    'body_pack': 0.62,
    'areal': 36.0,
    'eng_coeff': 200.0,
    'eng_density': 650.0,
    'payload_density': 2600.0,
    'void_frac': 0.10,
    'fuel_density': 800.0,
    'tsfc': 2.15e-5,
    'mach': 0.80,
    'alt_km': CRUISE_HIGH_ALT_KM,
    'ld_base': 3.4,
    'ld_slope': 0.08,
    'ld_min': 3.8,
    'ld_max': 5.0,
    'eta': 0.28,
    'reserve': 0.08,
    'sea_alt_km': CRUISE_SEA_ALT_KM,
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


def isa_temperature_k(altitude_km: float) -> float:
    """国际标准大气静温。11 km 以下对流层递减，其上分段等温或缓增。"""
    if altitude_km < 0:
        raise ValueError('高度不能为负')
    height_m = altitude_km * 1000.0
    if height_m <= 11000.0:
        return 288.15 - 0.0065 * height_m
    if height_m <= 20000.0:
        return 216.65
    if height_m <= 32000.0:
        return 216.65 + 0.001 * (height_m - 20000.0)
    return 228.65 + 0.0028 * (min(height_m, 47000.0) - 32000.0)


def speed_of_sound_m_s(altitude_km: float) -> float:
    """国际标准大气近似下的声速。"""
    return math.sqrt(1.4 * ISA_R * isa_temperature_k(altitude_km))



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


def sutherland_viscosity_pa_s(temperature_k: float) -> float:
    """萨瑟兰公式下的空气动力粘度。"""
    if temperature_k <= 0:
        raise ValueError('静温必须大于 0')
    return 1.716e-5 * (temperature_k / 273.15) ** 1.5 * (273.15 + 110.4) / (temperature_k + 110.4)


def dynamic_pressure_pa(mach: float, altitude_km: float) -> float:
    """给定马赫数和高度的动压。"""
    if mach <= 0:
        raise ValueError('马赫数必须大于 0')
    speed = mach * speed_of_sound_m_s(altitude_km)
    return 0.5 * isa_density_kg_m3(altitude_km) * speed * speed


def parasite_friction_share(mach: float) -> float:
    """废阻里表面摩阻所占份额。亚音速以摩阻为主，超音速以波阻和底部阻力为主。"""
    if mach < 0:
        raise ValueError('马赫数不能为负')
    if mach >= 1.2:
        return 0.35
    return 0.65


def skin_friction_ratio(
    length_m: float,
    mach: float,
    altitude_km: float,
    mach_ref: float,
    altitude_ref_km: float,
) -> float:
    """湍流平板摩阻相对参考状态，Cf 按雷诺数的 -0.2 次方。"""
    if length_m <= 0:
        raise ValueError('弹长必须大于 0')
    if mach <= 0 or mach_ref <= 0:
        raise ValueError('马赫数必须大于 0')

    def reynolds(m: float, h: float) -> float:
        speed = m * speed_of_sound_m_s(h)
        viscosity = sutherland_viscosity_pa_s(isa_temperature_k(h))
        return isa_density_kg_m3(h) * speed * length_m / viscosity

    re_new = reynolds(mach, altitude_km)
    re_ref = reynolds(mach_ref, altitude_ref_km)
    return (re_ref / re_new) ** 0.2


def wing_polar(spec: dict[str, float]) -> tuple[float, float, float]:
    """巡航翼面的设计升力系数、展弦比和奥斯瓦尔德效率。

    亚音速折叠弹翼用统一设计点。亚燃弹翼更小，写在弹种参数里。
    """
    cl = float(spec.get('wing_cl', FOLDED_WING_CL))
    aspect = float(spec.get('wing_ar', FOLDED_WING_AR))
    oswald = float(spec.get('wing_oswald', FOLDED_WING_OSWALD))
    if cl <= 0 or aspect <= 0 or oswald <= 0:
        raise ValueError('翼面升力系数、展弦比与奥斯瓦尔德效率必须大于 0')
    return cl, aspect, oswald


def sea_skim_ld(
    ld_design: float,
    mach_design: float,
    alt_design_km: float,
    mach_sea: float,
    alt_sea_km: float,
    length_m: float,
    cl_design: float,
    aspect_ratio: float,
    oswald: float,
) -> float:
    """由高空设计点升阻比推出掠海升阻比。

    设计点升力等于重量。诱导阻力份额是 CL/(π·AR·e)，剩下的是废阻。
    掠海动压升高后，同一副翼只用更小的升力系数，诱导阻力下降；
    废阻随动压上升。摩阻那一部分再按雷诺数略减，波阻不减。
    30 m 对导弹翼展仍远高于地面效应，不计海面增升。
    """
    if ld_design <= 0 or cl_design <= 0 or aspect_ratio <= 0 or oswald <= 0:
        raise ValueError('升阻比、升力系数、展弦比与奥斯瓦尔德效率必须大于 0')
    q_design = dynamic_pressure_pa(mach_design, alt_design_km)
    q_sea = dynamic_pressure_pa(mach_sea, alt_sea_km)
    drag_over_weight = 1.0 / ld_design
    induced = cl_design / (math.pi * aspect_ratio * oswald)
    # 翼面参数和设计升阻比矛盾时，诱导阻力最多占八成五，其余留给废阻。
    induced = min(induced, 0.85 * drag_over_weight)
    parasite = drag_over_weight - induced
    cf_ratio = skin_friction_ratio(length_m, mach_sea, alt_sea_km, mach_design, alt_design_km)
    friction = parasite_friction_share(mach_design)
    drag_scale = friction * cf_ratio + (1.0 - friction)
    cl_sea = cl_design * q_design / q_sea
    induced_sea = cl_sea / (math.pi * aspect_ratio * oswald)
    parasite_sea = parasite * (q_sea / q_design) * drag_scale
    total = parasite_sea + induced_sea
    if total <= 0:
        raise ValueError('掠海阻力必须大于 0')
    return 1.0 / total


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


def breguet_fuel_for_range_kg(
    range_m: float,
    speed_m_s: float,
    tsfc_kg_n_s: float,
    ld: float,
    mass_final_kg: float,
) -> float:
    """飞完固定距离所需燃油。由较轻的终点质量往回推到起点。"""
    if range_m < 0:
        raise ValueError('航程不能为负')
    if speed_m_s <= 0 or tsfc_kg_n_s <= 0 or ld <= 0 or mass_final_kg <= 0:
        raise ValueError('速度、耗油率、升阻比与终点质量必须大于 0')
    if range_m == 0.0:
        return 0.0
    exponent = range_m * G0 * tsfc_kg_n_s / (speed_m_s * ld)
    return mass_final_kg * math.expm1(exponent)


def isp_from_tsfc_s(tsfc_kg_n_s: float) -> float:
    """耗油率 kg/(N·s) 换成比冲（秒）。吸气发动机 Isp = 1/(g·TSFC)。"""
    if tsfc_kg_n_s <= 0:
        raise ValueError('耗油率必须大于 0')
    return 1.0 / (tsfc_kg_n_s * G0)


def tsfc_from_isp_s(isp_s: float) -> float:
    """比冲（秒）换成耗油率 kg/(N·s)。"""
    if isp_s <= 0:
        raise ValueError('比冲必须大于 0')
    return 1.0 / (isp_s * G0)


def cruise_tsfc_base(spec: dict[str, float], isp_air_s: float | None) -> float:
    """巡航耗油率。未给吸气比冲、或与弹种默认值很接近时，用标定耗油率。"""
    nominal = spec['tsfc']
    if nominal <= 0:
        raise ValueError('耗油率必须大于 0')
    if isp_air_s is None:
        return nominal
    if abs(float(isp_air_s) - isp_from_tsfc_s(nominal)) <= ISP_MATCH_TOL_S:
        return nominal
    return tsfc_from_isp_s(isp_air_s)


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
    cruise_tsfc: float | None = None,
) -> dict[str, float]:
    """全高空、全掠海与高中低混合巡航航程。预留容积和惰性质量给末端火箭。

    亚音速弹种带折叠弹翼时，翼面质量和占用容积从燃油舱里扣出，计入死重。
    发射速度低于接力马赫数时，可抛弃助推器再占一截燃油舱，巡航质量不含助推器。
    隐身涡扇可另给宽和高，按扁五边形算容积，不再把较长的一边当成圆直径。
    cruise_tsfc 覆盖弹种标定耗油率，用来代入另一档吸气比冲。
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
    tsfc_hi = spec['tsfc'] if cruise_tsfc is None else cruise_tsfc
    if tsfc_hi <= 0:
        raise ValueError('耗油率必须大于 0')
    booster_mass = booster_prop * (1.0 + BOOST_CASE_FRAC)
    ld = subsonic_ld(length_m, section['d_eq'], spec)
    if wing_fill < 1.0:
        ld *= 0.55 + 0.45 * wing_fill
    sound_hi = speed_of_sound_m_s(spec['alt_km'])
    sound_sea = speed_of_sound_m_s(spec['sea_alt_km'])
    mach_sea = spec.get('sea_mach', spec['mach'])
    speed_hi = spec['mach'] * sound_hi
    speed_sea = mach_sea * sound_sea
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
    cl_design, aspect, oswald = wing_polar(spec)
    ld_sea = sea_skim_ld(
        ld, spec['mach'], spec['alt_km'], mach_sea, spec['sea_alt_km'], length_m,
        cl_design, aspect, oswald,
    )
    range_high = breguet_cruise_range_m(
        speed_hi, tsfc_hi, ld, launch_mass, launch_mass - usable_hi,
    )
    range_sea = breguet_cruise_range_m(
        speed_sea, tsfc_hi, ld_sea, launch_mass, launch_mass - usable_sea,
    )
    mixed = mixed_guidance_range_m(
        length_m=length_m,
        launch_mass_kg=launch_mass,
        usable_fuel_kg=usable_hi,
        tsfc_kg_n_s=tsfc_hi,
        ld_high=ld,
        mach_high=spec['mach'],
        alt_high_km=spec['alt_km'],
        ld_low=ld_sea,
        mach_low=mach_sea,
        alt_low_km=spec['sea_alt_km'],
        cl_design=cl_design,
        aspect_ratio=aspect,
        oswald=oswald,
    )
    bay = payload / spec['payload_density']
    head_len = min(length_m * 0.45, bay / max(section['area'], 1e-6))
    return {
        'm_0': launch_mass,
        'fuel_kg': fuel_kg,
        'ld': ld,
        'ld_sea': ld_sea,
        'range_high_m': range_high,
        'range_sea_m': range_sea,
        'range_mixed_m': mixed['range_m'],
        'ld_med': mixed['ld_med'],
        'alt_med_km': mixed['alt_med_km'],
        'range_med_m': mixed['range_med_m'],
        'range_low_m': mixed['range_low_m'],
        'med_shortened': mixed['med_shortened'],
        'low_shortened': mixed['low_shortened'],
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
        'isp_cruise_s': isp_from_tsfc_s(tsfc_hi),
    }


def scramjet_combustor_volume_m3(length_m: float, diameter_m: float) -> float:
    """超燃燃烧室流道容积。这段不装固体药，也不装燃油。"""
    if length_m <= 0 or diameter_m <= 0:
        raise ValueError('弹长与弹径必须大于 0')
    flow_diameter = diameter_m * SCRAMJET_COMBUSTOR_DIAMETER_FRAC
    combustor_length = min(
        length_m * SCRAMJET_COMBUSTOR_LENGTH_FRAC,
        SCRAMJET_COMBUSTOR_FINENESS * diameter_m,
    )
    return math.pi * (flow_diameter / 2.0) ** 2 * combustor_length


def split_scramjet_booster_and_fuel(
    energy_volume_m3_value: float,
    combustor_volume_m3: float,
    fixed_mass_kg: float,
    dv_boost_m_s: float,
    isp_s: float,
    propellant_density: float,
    fuel_density: float,
    fuel_floor_frac: float,
) -> tuple[float, float, float]:
    """燃烧室先留空，剩下的能源容积才分给单独的固体助推舱和燃油舱。"""
    if combustor_volume_m3 < 0:
        raise ValueError('燃烧室容积不能为负')
    # 燃烧室再大也不能超过能源容积的四成，否则小弹没有油箱。
    combustor = min(combustor_volume_m3, 0.40 * energy_volume_m3_value)
    bay = energy_volume_m3_value - combustor
    if bay <= 0.02:
        raise ValueError('超燃燃烧室挤掉了燃油舱')
    return split_boost_and_fuel(
        bay, fixed_mass_kg, dv_boost_m_s, isp_s,
        propellant_density, fuel_density, fuel_floor_frac,
    )


def split_boost_and_fuel(
    energy_volume_m3_value: float,
    fixed_mass_kg: float,
    dv_boost_m_s: float,
    isp_s: float,
    propellant_density: float,
    fuel_density: float,
    fuel_floor_frac: float,
) -> tuple[float, float, float]:
    """固冲一体：助推药铸在燃烧室里，和燃油分同一块能源容积。"""
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


def takeover_progress_frac(mach_boost: float, mach_takeover: float) -> float:
    """助推实际马赫相对接力马赫的完成比例，夹在 0 到 1。"""
    if mach_takeover <= 0:
        raise ValueError('接力马赫数必须大于 0')
    if mach_boost < 0:
        raise ValueError('助推马赫数不能为负')
    return min(1.0, mach_boost / mach_takeover)


def duct_cruise_tsfc(missile_class: str, diameter_m: float, spec: dict[str, float]) -> float:
    """巡航耗油率。亚燃在参考弹径及以上用同一耗油率，更细则更费油。

    参考弹径是鹰击-15。更细的进气道损失更大，避免小弹跟着这一代耗油率变远。
    """
    tsfc = spec['tsfc']
    narrow = spec.get('tsfc_diameter_exponent', 0.0)
    wide = spec.get('tsfc_wide_exponent', 0.0)
    if narrow <= 0 and wide <= 0:
        return tsfc
    if diameter_m <= 0:
        raise ValueError('弹径必须大于 0')
    ref = spec.get('tsfc_ref_diameter_m', diameter_m)
    if ref <= 0:
        raise ValueError('耗油率参考弹径必须大于 0')
    if diameter_m <= ref:
        scale = (ref / diameter_m) ** narrow
    else:
        scale = (diameter_m / ref) ** wide
    return tsfc * clamp(
        scale,
        spec.get('tsfc_scale_min', 1.0),
        spec.get('tsfc_scale_max', 2.5),
    )


def _air_spec(missile_class: str) -> dict[str, float] | None:
    """吸气式弹种的标定。纯火箭返回 None。"""
    canon = normalize_missile_class(missile_class)
    if canon in _SUBSONIC_SPECS:
        return _SUBSONIC_SPECS[canon]
    if canon in _DUCT_SPECS:
        return _DUCT_SPECS[canon]
    if canon == 'turbofan_rocket':
        return _ROCKET_CRUISE
    return None


def resolved_cruise_tsfc(
    missile_class: str,
    diameter_m: float,
    isp_air_s: float | None = None,
) -> float:
    """巡航耗油率。冲压弹再按弹径修正；亚音速只用吸气比冲对应的耗油率。"""
    canon = normalize_missile_class(missile_class)
    spec = _air_spec(canon)
    if spec is None:
        raise ValueError('该弹种没有吸气巡航')
    base = dict(spec)
    base['tsfc'] = cruise_tsfc_base(spec, isp_air_s)
    if canon in _DUCT_SPECS:
        return duct_cruise_tsfc(canon, diameter_m, base)
    return base['tsfc']


def airbreathing_stage_isp(
    missile_class: str,
    diameter_m: float,
    isp_rocket_s: float = DEFAULT_ISP_S,
    isp_air_s: float | None = None,
) -> dict[str, float | None]:
    """吸气式导弹的比冲拆成助推固体和巡航吸气两段。

    冲压弹助推跟固体火箭比冲走，巡航比冲更高，细弹再按弹径下降。
    亚音速可抛弃助推器固定用较低的固体比冲，不跟弹道弹的比冲走。
    亚超结合的末端火箭另记一档固体比冲，和可抛弃助推器不是同一段。
    """
    canon = normalize_missile_class(missile_class)
    if _air_spec(canon) is None:
        raise ValueError('该弹种没有吸气巡航')
    if isp_rocket_s <= 0:
        raise ValueError('比冲必须大于 0')
    cruise = isp_from_tsfc_s(resolved_cruise_tsfc(canon, diameter_m, isp_air_s))
    if canon in _DUCT_SPECS:
        return {
            'isp_boost_s': float(isp_rocket_s),
            'isp_cruise_s': cruise,
            'isp_rocket_s': None,
        }
    if canon == 'turbofan_rocket':
        return {
            'isp_boost_s': SUBSONIC_BOOSTER_ISP_S,
            'isp_cruise_s': cruise,
            'isp_rocket_s': float(isp_rocket_s),
        }
    return {
        'isp_boost_s': SUBSONIC_BOOSTER_ISP_S,
        'isp_cruise_s': cruise,
        'isp_rocket_s': None,
    }


def class_isp_defaults(missile_class: str) -> dict[str, float | None]:
    """弹种默认比冲，供表单和目录使用。吸气巡航取参考弹径，不含细弹惩罚。"""
    canon = resolve_missile_class(missile_class)
    if _air_spec(canon) is None:
        return {
            'isp_boost_s': None,
            'isp_cruise_s': None,
            'isp_rocket_s': round(DEFAULT_ISP_S, 1),
        }
    stages = airbreathing_stage_isp(canon, 1.0, DEFAULT_ISP_S, None)
    return {
        key: None if value is None else round(float(value), 1)
        for key, value in stages.items()
    }


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


def burke_radar_los_km(
    radar_height_m: float = BURKE_RADAR_HEIGHT_M,
    target_height_m: float = BURKE_SEA_TARGET_HEIGHT_M,
) -> float:
    """伯克级雷达对掠海目标的地球曲率视距（公里）。

    亚超结合的末端冲刺统一用这一段，不再按固体装药反推冲刺航程。
    """
    if radar_height_m < 0 or target_height_m < 0:
        raise ValueError('雷达高度与目标高度不能为负')
    return radar_horizon_km(radar_height_m, target_height_m)


def guidance_search_horizon_km(
    radar_height_m: float = BURKE_RADAR_HEIGHT_M,
    target_height_m: float = BURKE_SEA_TARGET_HEIGHT_M,
    search_factor: float = GUIDANCE_SEARCH_HORIZON_FACTOR,
) -> float:
    """中空搜索视距（公里）：掠海末段视距乘以搜索倍数。"""
    if search_factor <= 0:
        raise ValueError('搜索视距倍数必须大于 0')
    return search_factor * burke_radar_los_km(radar_height_m, target_height_m)


def guidance_medium_altitude_m(
    radar_height_m: float = BURKE_RADAR_HEIGHT_M,
    search_horizon_km: float | None = None,
) -> float:
    """由导引头对舰桅的视距反解中空高度（米）。"""
    if radar_height_m < 0:
        raise ValueError('舰桅高度不能为负')
    if search_horizon_km is None:
        horizon = guidance_search_horizon_km(radar_height_m)
    else:
        horizon = float(search_horizon_km)
    if horizon <= 0:
        raise ValueError('搜索视距必须大于 0')
    # 与 radar_horizon_km 同一系数：视距 = k·(√h + √桅高)，k 取高度 1 m、桅高 0。
    scale = radar_horizon_km(1.0, 0.0)
    if scale <= 0:
        raise ValueError('雷达视距系数无效')
    inside = horizon / scale - math.sqrt(radar_height_m)
    if inside <= 0:
        raise ValueError('搜索视距短于舰桅自身视距，无法反解高度')
    return inside * inside


def mixed_guidance_legs_m(
    usable_fuel_kg: float,
    mass_final_kg: float,
    tsfc_kg_n_s: float,
    speed_high_m_s: float,
    ld_high: float,
    speed_med_m_s: float,
    ld_med: float,
    speed_low_m_s: float,
    ld_low: float,
    low_leg_m: float,
    med_leg_m: float,
) -> dict:
    """从终点往回分配高、中、低三段航程。油不够时先缩短中段，再缩短低段。"""
    if usable_fuel_kg < 0 or mass_final_kg <= 0:
        raise ValueError('可用燃油不能为负，终点质量必须大于 0')
    if low_leg_m < 0 or med_leg_m < 0:
        raise ValueError('末端航段不能为负')
    if min(speed_high_m_s, speed_med_m_s, speed_low_m_s, ld_high, ld_med, ld_low, tsfc_kg_n_s) <= 0:
        raise ValueError('速度、升阻比与耗油率必须大于 0')
    mass_start = mass_final_kg + usable_fuel_kg
    if usable_fuel_kg == 0.0:
        return {
            'range_high_m': 0.0,
            'range_med_m': 0.0,
            'range_low_m': 0.0,
            'range_m': 0.0,
            'med_shortened': med_leg_m > 0.0,
            'low_shortened': low_leg_m > 0.0,
        }

    fuel_low = breguet_fuel_for_range_kg(
        low_leg_m, speed_low_m_s, tsfc_kg_n_s, ld_low, mass_final_kg,
    )
    if fuel_low > usable_fuel_kg + 1e-9:
        flown_low = breguet_cruise_range_m(
            speed_low_m_s, tsfc_kg_n_s, ld_low, mass_start, mass_final_kg,
        )
        return {
            'range_high_m': 0.0,
            'range_med_m': 0.0,
            'range_low_m': flown_low,
            'range_m': flown_low,
            'med_shortened': med_leg_m > 0.0,
            'low_shortened': True,
        }

    mass_before_low = mass_final_kg + fuel_low
    fuel_left = usable_fuel_kg - fuel_low
    fuel_med = breguet_fuel_for_range_kg(
        med_leg_m, speed_med_m_s, tsfc_kg_n_s, ld_med, mass_before_low,
    )
    if fuel_med > fuel_left + 1e-9:
        if fuel_left <= 1e-9:
            flown_med = 0.0
        else:
            flown_med = breguet_cruise_range_m(
                speed_med_m_s, tsfc_kg_n_s, ld_med,
                mass_before_low + fuel_left, mass_before_low,
            )
        return {
            'range_high_m': 0.0,
            'range_med_m': flown_med,
            'range_low_m': low_leg_m,
            'range_m': flown_med + low_leg_m,
            'med_shortened': True,
            'low_shortened': False,
        }

    mass_before_med = mass_before_low + fuel_med
    if mass_start <= mass_before_med + 1e-6:
        flown_high = 0.0
    else:
        flown_high = breguet_cruise_range_m(
            speed_high_m_s, tsfc_kg_n_s, ld_high, mass_start, mass_before_med,
        )
    return {
        'range_high_m': flown_high,
        'range_med_m': med_leg_m,
        'range_low_m': low_leg_m,
        'range_m': flown_high + med_leg_m + low_leg_m,
        'med_shortened': False,
        'low_shortened': False,
    }


def mixed_guidance_range_m(
    *,
    length_m: float,
    launch_mass_kg: float,
    usable_fuel_kg: float,
    tsfc_kg_n_s: float,
    ld_high: float,
    mach_high: float,
    alt_high_km: float,
    ld_low: float,
    mach_low: float,
    alt_low_km: float,
    cl_design: float,
    aspect_ratio: float,
    oswald: float,
    include_low_leg: bool = True,
    mach_med: float | None = None,
) -> dict:
    """高空巡航、中空搜索、末段掠海的混合航程。

    爬升耗油已经从可用燃油里扣掉。中空升阻比按该高度的动压计算。
    亚超结合把末段掠海换成固体冲刺时，include_low_leg 取 False，冲刺距离由调用方另加。
    稠密大气里飞不了高空设计马赫数时，传入较低的 mach_med。
    """
    if usable_fuel_kg < 0 or launch_mass_kg <= usable_fuel_kg:
        raise ValueError('巡航终点质量必须大于 0')
    if length_m <= 0 or mach_high <= 0 or mach_low <= 0:
        raise ValueError('弹长与马赫数必须大于 0')
    if alt_high_km < 0 or alt_low_km < 0:
        raise ValueError('高度不能为负')
    mach_at_med = mach_low if mach_med is None else float(mach_med)
    if mach_at_med <= 0:
        raise ValueError('中空马赫数必须大于 0')
    alt_med_km = guidance_medium_altitude_m() / 1000.0
    ld_med = sea_skim_ld(
        ld_high, mach_high, alt_high_km, mach_at_med, alt_med_km, length_m,
        cl_design, aspect_ratio, oswald,
    )
    low_leg_m = burke_radar_los_km() * 1000.0 if include_low_leg else 0.0
    med_leg_m = guidance_search_horizon_km() * 1000.0
    legs = mixed_guidance_legs_m(
        usable_fuel_kg,
        launch_mass_kg - usable_fuel_kg,
        tsfc_kg_n_s,
        mach_high * speed_of_sound_m_s(alt_high_km),
        ld_high,
        mach_at_med * speed_of_sound_m_s(alt_med_km),
        ld_med,
        mach_low * speed_of_sound_m_s(alt_low_km),
        ld_low,
        low_leg_m,
        med_leg_m,
    )
    legs['alt_med_km'] = alt_med_km
    legs['ld_med'] = ld_med
    legs['med_leg_requested_m'] = med_leg_m
    legs['low_leg_requested_m'] = low_leg_m
    return legs


def mixed_profile_sentence(
    range_mixed_km: float,
    alt_med_m: float,
    med_leg_km: float,
    low_leg_km: float,
    ld_med: float,
    *,
    dash_replaces_low: bool = False,
    med_shortened: bool = False,
    low_shortened: bool = False,
) -> str:
    """混合弹道的一句说明：中空高度、两段末端和中空升阻比。"""
    if range_mixed_km < 0 or alt_med_m < 0 or med_leg_km < 0 or low_leg_km < 0 or ld_med <= 0:
        raise ValueError('混合弹道说明的射程、高度与升阻比无效')
    med_txt = f"中空 {alt_med_m:.0f} m 搜索 {med_leg_km:.0f} km"
    if med_shortened:
        med_txt += "（燃油不足，搜索段缩短）"
    if dash_replaces_low:
        low_txt = "末段为伯克级雷达视距冲刺"
    else:
        low_txt = f"末段 {low_leg_km:.0f} km 掠海"
        if low_shortened:
            low_txt += "（燃油不足，掠海段缩短）"
    return (
        f"混合弹道 {range_mixed_km:.0f} km：高空巡航后{med_txt}，{low_txt}，"
        f"中空升阻比 {ld_med:.2f}。"
    )


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


def ballistic_guidance_mass_kg(diameter_m: float) -> float:
    """制导与控制质量：电子舱有下限，舵机随截面积增加。"""
    if diameter_m <= 0:
        raise ValueError('弹径必须大于 0')
    area = math.pi * (diameter_m / 2.0) ** 2
    return BALLISTIC_GUIDANCE_FLOOR_KG + BALLISTIC_GUIDANCE_AREA_KG_M2 * area


def ballistic_nose_length_m(length_m: float, diameter_m: float) -> float:
    """头锥长度。长径比固定，且不超过战斗部舱允许占的弹长。"""
    if length_m <= 0 or diameter_m <= 0:
        raise ValueError('弹长与弹径必须大于 0')
    return min(BALLISTIC_NOSE_FINENESS * diameter_m, length_m * BALLISTIC_HEAD_LENGTH_CAP)


def ballistic_body_volume_m3(length_m: float, diameter_m: float) -> float:
    """整弹容积：圆锥头加上后面的圆柱。圆锥体积是同样长度圆柱的三分之一。"""
    nose = ballistic_nose_length_m(length_m, diameter_m)
    area = math.pi * (diameter_m / 2.0) ** 2
    return area * (length_m - nose) + area * nose / 3.0


def ballistic_head_lengths_m(
    length_m: float,
    diameter_m: float,
    warhead_mass_kg: float,
) -> tuple[float, float, float]:
    """头锥按长径比占一段，制导和战斗部先扣掉头锥容积，装不下再占用后面的圆柱。

    返回弹头段长度、圆柱发动机长度、制导与控制质量。
    头锥里没用掉的容积另计装药，不缩短这段头锥。
    """
    if length_m <= 0 or diameter_m <= 0:
        raise ValueError('弹长与弹径必须大于 0')
    if warhead_mass_kg < 0:
        raise ValueError('战斗部质量不能为负')
    nose = ballistic_nose_length_m(length_m, diameter_m)
    area = math.pi * (diameter_m / 2.0) ** 2
    cone_volume = area * nose / 3.0
    guidance = ballistic_guidance_mass_kg(diameter_m)
    payload_volume = (
        warhead_mass_kg / BALLISTIC_WARHEAD_DENSITY_KG_M3
        + guidance / BALLISTIC_GUIDANCE_DENSITY_KG_M3
    )
    if payload_volume <= cone_volume:
        head = nose
    else:
        head = nose + (payload_volume - cone_volume) / area
    head = min(head, length_m * BALLISTIC_HEAD_LENGTH_CAP)
    return head, length_m - head, guidance


def ballistic_nose_propellant_volume_m3(
    length_m: float,
    diameter_m: float,
    warhead_mass_kg: float,
) -> float:
    """头锥扣掉制导和战斗部后还能装药的几何容积。载荷超出头锥时这里为零。"""
    if length_m <= 0 or diameter_m <= 0:
        raise ValueError('弹长与弹径必须大于 0')
    if warhead_mass_kg < 0:
        raise ValueError('战斗部质量不能为负')
    nose = ballistic_nose_length_m(length_m, diameter_m)
    area = math.pi * (diameter_m / 2.0) ** 2
    cone_volume = area * nose / 3.0
    guidance = ballistic_guidance_mass_kg(diameter_m)
    payload_volume = (
        warhead_mass_kg / BALLISTIC_WARHEAD_DENSITY_KG_M3
        + guidance / BALLISTIC_GUIDANCE_DENSITY_KG_M3
    )
    return max(0.0, cone_volume - payload_volume)


def ballistic_nose_propellant_kg(
    length_m: float,
    diameter_m: float,
    warhead_mass_kg: float,
    propellant_density: float,
) -> float:
    """剩余头锥按圆柱药柱的同样弹径收缩和装填系数装药。"""
    if propellant_density <= 0:
        raise ValueError('推进剂密度必须大于 0')
    leftover = ballistic_nose_propellant_volume_m3(length_m, diameter_m, warhead_mass_kg)
    body_area = math.pi * (diameter_m / 2.0) ** 2
    grain_frac = motor_cross_section_m2(diameter_m) / body_area * CHAMBER_FILL
    return leftover * grain_frac * propellant_density


def ballistic_coast_range_km(
    vacuum_km: float,
    speed_m_s: float,
    altitude_km: float,
    burnout_mass_kg: float,
    diameter_m: float,
) -> float:
    """真空弹道再按关机后的大气阻力折减。

    罚项正比于动压、反比于弹道系数，并随关机高度按大气标高衰减。
    高空关机几乎保持真空射程。
    """
    if vacuum_km < 0 or speed_m_s < 0 or altitude_km < 0:
        raise ValueError('真空射程、速度与高度不能为负')
    if burnout_mass_kg <= 0 or diameter_m <= 0:
        raise ValueError('关机质量与弹径必须大于 0')
    if vacuum_km == 0.0 or speed_m_s == 0.0:
        return 0.0
    area = math.pi * (diameter_m / 2.0) ** 2
    beta = burnout_mass_kg / area
    penalty = (speed_m_s ** 2) * math.exp(-altitude_km / BALLISTIC_DRAG_SCALE_KM) / beta
    return vacuum_km * math.exp(-BALLISTIC_COAST_K * penalty)


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
    range_mixed_km: float | None = None,
    range_cruise_km: float | None = None,
    range_terminal_km: float | None = None,
    cruise_mach: float | None = None,
    cruise_alt_km: float | None = None,
    m_dead_kg: float | None = None,
    m_wing_kg: float | None = None,
    isp_boost_s: float | None = None,
    isp_cruise_s: float | None = None,
    isp_rocket_s: float | None = None,
    reached_takeover: bool | None = None,
    mach_takeover: float | None = None,
    mach_boost: float | None = None,
    m_booster_kg: float | None = None,
    m_fuel_kg: float | None = None,
    takeover_progress: float | None = None,
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
        'range_mixed_km': None if range_mixed_km is None else round(range_mixed_km, 1),
        'range_cruise_km': None if range_cruise_km is None else round(range_cruise_km, 1),
        'range_terminal_km': None if range_terminal_km is None else round(range_terminal_km, 1),
        'cruise_mach': None if cruise_mach is None else round(cruise_mach, 2),
        'cruise_alt_km': None if cruise_alt_km is None else round(cruise_alt_km, 1),
        'm_dead_kg': None if m_dead_kg is None else round(m_dead_kg, 1),
        'm_wing_kg': None if m_wing_kg is None else round(m_wing_kg, 1),
        'isp_boost_s': None if isp_boost_s is None else round(isp_boost_s, 1),
        'isp_cruise_s': None if isp_cruise_s is None else round(isp_cruise_s, 1),
        'isp_rocket_s': None if isp_rocket_s is None else round(isp_rocket_s, 1),
        'reached_takeover': reached_takeover,
        'mach_takeover': None if mach_takeover is None else round(mach_takeover, 2),
        'mach_boost': None if mach_boost is None else round(mach_boost, 2),
        'm_booster_kg': None if m_booster_kg is None else round(m_booster_kg, 1),
        'm_fuel_kg': None if m_fuel_kg is None else round(m_fuel_kg, 1),
        'takeover_progress': None if takeover_progress is None else round(takeover_progress, 3),
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
    isp_air_s: float | None = None,
) -> dict:
    """涡扇隐身或涡喷非隐身的全高空、全掠海射程。

    隐身涡扇可另给宽和高。不给时，弹径是最大外廓，短边按弹种高宽比收成扁五边形。
    巡航用吸气比冲。低速发射的可抛弃助推器另用较低的固体比冲。
    """
    canon = normalize_missile_class(missile_class)
    if canon not in _SUBSONIC_SPECS:
        raise ValueError('该函数只用于亚音速巡航弹')
    spec = _SUBSONIC_SPECS[canon]
    cruise_tsfc = resolved_cruise_tsfc(canon, diameter_m, isp_air_s)
    sized = cruise_range_pair_km(
        length_m=length_m,
        diameter_m=diameter_m,
        warhead_mass_kg=warhead_mass_kg,
        v_launch_mach=v_launch_mach,
        h_launch_km=h_launch_km,
        spec=spec,
        width_m=width_m,
        height_m=height_m,
        cruise_tsfc=cruise_tsfc,
    )
    high_km = sized['range_high_m'] / 1000.0
    sea_km = sized['range_sea_m'] / 1000.0
    mixed_km = sized['range_mixed_m'] / 1000.0
    mix_txt = mixed_profile_sentence(
        mixed_km,
        sized['alt_med_km'] * 1000.0,
        sized['range_med_m'] / 1000.0,
        sized['range_low_m'] / 1000.0,
        sized['ld_med'],
        med_shortened=bool(sized['med_shortened']),
        low_shortened=bool(sized['low_shortened']),
    )
    ignition = sized['m_0'] + sized['m_booster_kg']
    dead = deadweight_kg(ignition, sized['fuel_kg'], warhead_mass_kg, sized['m_booster_kg'])
    fit = '' if sized['wing_fill'] >= 0.995 else f"弹舱只能放下设计翼面积的 {sized['wing_fill'] * 100:.0f}%。"
    isp_boost = None
    boost_txt = ''
    if sized['m_booster_kg'] > 1.0:
        isp_boost = SUBSONIC_BOOSTER_ISP_S
        boost_txt = f"可抛弃助推器 {sized['m_booster_kg']:.0f} kg，固体比冲 {isp_boost:.0f} s。"
    note = (
        f"{class_label(canon)}：主射程为全高空 {spec['alt_km']:.0f} km、"
        f"Ma {spec['mach']:.2f}；全掠海为 {spec['sea_alt_km'] * 1000:.0f} m。"
        f"高空升阻比 {sized['ld']:.2f}，掠海升阻比 {sized['ld_sea']:.2f}，"
        f"巡航吸气比冲 {sized['isp_cruise_s']:.0f} s。"
        f"{boost_txt}折叠弹翼 {sized['m_wing_kg']:.0f} kg，死重 {dead:.0f} kg。{fit}"
        f"{mix_txt}"
    )
    return _base_fields(
        canon, ignition, sized['l_head_m'], length_m - sized['l_head_m'],
        sized['fuel_kg'], spec['mach'], sized['ld'], high_km, note,
        range_high_km=high_km, range_sea_km=sea_km, range_mixed_km=mixed_km,
        range_cruise_km=high_km, cruise_mach=spec['mach'], cruise_alt_km=spec['alt_km'],
        m_dead_kg=dead, m_wing_kg=sized['m_wing_kg'],
        isp_boost_s=isp_boost, isp_cruise_s=sized['isp_cruise_s'],
        m_booster_kg=sized['m_booster_kg'], m_fuel_kg=sized['fuel_kg'],
    )


def accel_fuel_for_dv(mass_kg: float, dv_m_s: float, isp_s: float, accel_excess: float) -> float:
    """一段加速的耗油。阻力使同样的速度增量比理想火箭更费油。"""
    if mass_kg <= 0 or isp_s <= 0 or accel_excess <= 0:
        raise ValueError('加速耗油的质量、比冲与超额系数必须大于 0')
    if dv_m_s < 0:
        raise ValueError('速度增量不能为负')
    if dv_m_s <= 1.0:
        return 0.0
    frac = 1.0 - math.exp(-dv_m_s / (isp_s * G0 * accel_excess))
    return frac * mass_kg


def estimate_ducted(
    missile_class: str,
    length_m: float,
    diameter_m: float,
    warhead_mass_kg: float,
    v_launch_mach: float,
    h_launch_km: float,
    isp_s: float,
    propellant_density: float,
    isp_air_s: float | None = None,
) -> dict:
    """超燃或亚燃：固体助推和吸气巡航分开计比冲。

    亚燃按固冲一体，药柱和煤油分同一块能源容积。
    超燃燃烧室先留空，固体助推器另占一舱，燃油是高密度吸热型碳氢燃料。
    """
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
    stages = airbreathing_stage_isp(canon, diameter_m, isp_s, isp_air_s)
    isp_boost = float(stages['isp_boost_s'])
    if canon == 'scramjet':
        propellant, fuel, launch_mass = split_scramjet_booster_and_fuel(
            tank, scramjet_combustor_volume_m3(length_m, diameter_m),
            fixed, dv_need, isp_boost, propellant_density, spec['fuel_density'], spec['fuel_floor_frac'],
        )
    else:
        propellant, fuel, launch_mass = split_boost_and_fuel(
            tank, fixed, dv_need, isp_boost, propellant_density, spec['fuel_density'], spec['fuel_floor_frac'],
        )
    ideal = achieved_boost_dv_m_s(propellant, launch_mass, isp_boost)
    if dv_need <= 1.0:
        speed_after = launch_speed
    else:
        speed_after = launch_speed + gap * min(1.0, ideal / dv_need)
    reached = speed_after >= takeover_speed * 0.98
    tsfc = resolved_cruise_tsfc(canon, diameter_m, isp_air_s)
    isp_cruise = isp_from_tsfc_s(tsfc)
    ld = duct_ld(length_m, diameter_m, spec)
    burn_time = ballistic_burn_time_s(propellant, launch_mass, isp_boost) if propellant > 0 else 0.0
    boost_range = 0.5 * (launch_speed + speed_after) * burn_time
    mass_after_boost = launch_mass - propellant
    mach_boost = speed_after / sound
    mach_takeover = spec['mach_takeover']
    booster_mass = propellant * (1.0 + BOOST_CASE_FRAC) if propellant > 0 else 0.0
    sea_ld = None
    mixed_km = None
    mix_txt = ''
    if not reached:
        # 接不上接力马赫数时，不能在高空用巡航速度做布雷盖。
        burnout_alt = burnout_altitude_km(max(speed_after, 50.0), h_launch_km)
        try:
            coast_km = ballistic_range_km(max(speed_after, 50.0), burnout_alt)
        except ValueError:
            coast_km = 0.0
        high_km = boost_range / 1000.0 + coast_km
        sea_km = high_km if spec.get('sea_alt_km') is not None else None
        cruise_m = 0.0
        cruise_mach = speed_after / speed_of_sound_m_s(0.0)
        cruise_alt = burnout_alt
        trimmed = f'冲压未接入设计马赫数（助推达 Ma {mach_boost:.2f}，低于接力 Ma {mach_takeover:.2f}），射程只计助推后的弹道弧。'
    else:
        cruise_alt = spec['alt_km']
        cruise_speed = spec['mach_cruise'] * sound
        cruise_mach = cruise_speed / sound
        accel = max(0.0, cruise_speed - speed_after)
        accel_fuel = min(
            fuel * DUCT_ACCEL_FUEL_CAP,
            accel_fuel_for_dv(mass_after_boost, accel, isp_cruise, spec['accel_excess']),
        )
        trimmed = ''
        climb = climb_fuel_kg(
            mass_after_boost,
            (cruise_alt - h_launch_km) * 1000.0,
            cruise_speed ** 2 - speed_after ** 2,
            spec['eta'],
        )
        climb = min(climb, max(0.0, fuel - accel_fuel) * 0.40)
        cruise_fuel = max(0.0, fuel - accel_fuel - climb) * (1.0 - spec['reserve'])
        if cruise_fuel <= 1.0:
            raise ValueError('冲压燃油不足以完成巡航')
        cruise_m = breguet_cruise_range_m(
            cruise_speed, tsfc, ld, mass_after_boost, mass_after_boost - cruise_fuel,
        )
        high_km = (cruise_m + boost_range) / 1000.0
        sea_km = None
        if spec.get('sea_alt_km') is not None:
            sea_mach = spec.get('sea_mach', spec['mach_cruise'])
            sea_sound = speed_of_sound_m_s(spec['sea_alt_km'])
            sea_speed = sea_mach * sea_sound
            cl_design, aspect, oswald = wing_polar(spec)
            sea_ld = sea_skim_ld(
                ld, spec['mach_cruise'], spec['alt_km'], sea_mach, spec['sea_alt_km'], length_m,
                cl_design, aspect, oswald,
            )
            sea_accel = max(0.0, sea_speed - speed_after)
            sea_accel_fuel = min(
                fuel * DUCT_ACCEL_FUEL_CAP,
                accel_fuel_for_dv(mass_after_boost, sea_accel, isp_cruise, spec['accel_excess']),
            )
            sea_climb = climb_fuel_kg(
                mass_after_boost,
                (spec['sea_alt_km'] - h_launch_km) * 1000.0,
                0.0,
                spec['eta'],
            )
            sea_climb = min(sea_climb, max(0.0, fuel - sea_accel_fuel) * 0.40)
            sea_fuel = max(0.0, fuel - sea_accel_fuel - sea_climb) * (1.0 - spec['reserve'])
            if sea_fuel > 1.0:
                sea_m = breguet_cruise_range_m(
                    sea_speed, tsfc, sea_ld, mass_after_boost, mass_after_boost - sea_fuel,
                )
                sea_km = (sea_m + boost_range) / 1000.0
                mixed = mixed_guidance_range_m(
                    length_m=length_m,
                    launch_mass_kg=mass_after_boost,
                    usable_fuel_kg=cruise_fuel,
                    tsfc_kg_n_s=tsfc,
                    ld_high=ld,
                    mach_high=spec['mach_cruise'],
                    alt_high_km=cruise_alt,
                    ld_low=sea_ld,
                    mach_low=sea_mach,
                    alt_low_km=spec['sea_alt_km'],
                    cl_design=cl_design,
                    aspect_ratio=aspect,
                    oswald=oswald,
                    mach_med=sea_mach,
                )
                mixed_km = (mixed['range_m'] + boost_range) / 1000.0
                mix_txt = mixed_profile_sentence(
                    mixed_km,
                    mixed['alt_med_km'] * 1000.0,
                    mixed['range_med_m'] / 1000.0,
                    mixed['range_low_m'] / 1000.0,
                    mixed['ld_med'],
                    med_shortened=bool(mixed['med_shortened']),
                    low_shortened=bool(mixed['low_shortened']),
                )
    dead = deadweight_kg(launch_mass, fuel, warhead_mass_kg, propellant)
    bay = payload / spec['payload_density']
    section = math.pi * (diameter_m / 2.0) ** 2
    head_len = min(length_m * 0.45, bay / section)
    sea_txt = ''
    if sea_km is not None and sea_ld is not None:
        sea_txt = (
            f"全掠海 {spec['sea_alt_km'] * 1000:.0f} m、{sea_km:.0f} km，"
            f"掠海升阻比 {sea_ld:.2f}。"
        )
    boost_txt = ''
    isp_boost_out = None
    if propellant > 1.0:
        isp_boost_out = isp_boost
        boost_txt = f"助推固体比冲 {isp_boost:.0f} s，"
    if canon == 'scramjet':
        layout = '燃烧室与固体助推分开，燃油为高密度吸热型碳氢燃料。'
    else:
        layout = '固冲一体，药柱铸在燃烧室里。'
    note = (
        f"{class_label(canon)}：{layout}{boost_txt}巡航吸气比冲 {isp_cruise:.0f} s。"
        f"高空巡航 Ma {cruise_mach:.2f} @ {cruise_alt:.0f} km，"
        f"设计 Ma {spec['mach_cruise']:.1f}。{trimmed}{sea_txt}{mix_txt}"
        f"死重 {dead:.0f} kg。"
    )
    return _base_fields(
        canon, launch_mass, head_len, length_m - head_len, fuel + propellant,
        cruise_mach, ld, high_km, note,
        range_high_km=high_km if sea_km is not None else None,
        range_sea_km=sea_km,
        range_mixed_km=mixed_km,
        range_cruise_km=cruise_m / 1000.0,
        cruise_mach=cruise_mach, cruise_alt_km=cruise_alt,
        m_dead_kg=dead,
        isp_boost_s=isp_boost_out, isp_cruise_s=isp_cruise,
        reached_takeover=reached,
        mach_takeover=mach_takeover,
        mach_boost=mach_boost,
        m_booster_kg=booster_mass,
        m_fuel_kg=fuel,
        takeover_progress=takeover_progress_frac(mach_boost, mach_takeover),
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
    cruise_tsfc: float | None = None,
) -> tuple[float, dict]:
    """按较重的巡航终点质量迭代末端装药。折叠弹翼先占燃油舱，装药不得挤掉弹翼。

    末端火箭用固体比冲。巡航耗油率另传，对应更高的吸气比冲。
    """
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
                cruise_tsfc=cruise_tsfc,
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
                cruise_tsfc=cruise_tsfc,
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
    isp_air_s: float | None = None,
) -> dict:
    """涡扇巡航加上末端固体火箭。巡航吸气比冲与末端固体比冲分开。"""
    if isp_s <= 0 or propellant_density <= 0:
        raise ValueError('比冲与推进剂密度必须大于 0')
    spec = _ROCKET_CRUISE
    cruise_tsfc = resolved_cruise_tsfc('turbofan_rocket', diameter_m, isp_air_s)
    propellant, sized = terminal_propellant_for_dash(
        length_m, diameter_m, warhead_mass_kg, v_launch_mach, h_launch_km,
        isp_s, propellant_density, spec, cruise_tsfc,
    )
    dash_km = burke_radar_los_km()
    high_km = sized['range_high_m'] / 1000.0 + dash_km
    sea_km = sized['range_sea_m'] / 1000.0 + dash_km
    # 末段冲刺就是掠海视距，混合弹道不再另扣一段亚音速掠海燃油。
    cl_design, aspect, oswald = wing_polar(spec)
    mixed = mixed_guidance_range_m(
        length_m=length_m,
        launch_mass_kg=sized['m_0'],
        usable_fuel_kg=sized['usable_high_kg'],
        tsfc_kg_n_s=cruise_tsfc,
        ld_high=sized['ld'],
        mach_high=spec['mach'],
        alt_high_km=spec['alt_km'],
        ld_low=sized['ld_sea'],
        mach_low=spec.get('sea_mach', spec['mach']),
        alt_low_km=spec['sea_alt_km'],
        cl_design=cl_design,
        aspect_ratio=aspect,
        oswald=oswald,
        include_low_leg=False,
    )
    mixed_km = mixed['range_m'] / 1000.0 + dash_km
    mix_txt = mixed_profile_sentence(
        mixed_km,
        mixed['alt_med_km'] * 1000.0,
        mixed['range_med_m'] / 1000.0,
        dash_km,
        mixed['ld_med'],
        dash_replaces_low=True,
        med_shortened=bool(mixed['med_shortened']),
    )
    ignition = sized['m_0'] + sized['m_booster_kg']
    dead = deadweight_kg(
        ignition, sized['fuel_kg'], warhead_mass_kg, propellant + sized['m_booster_kg'],
    )
    fit = '' if sized['wing_fill'] >= 0.995 else f"弹舱只能放下设计翼面积的 {sized['wing_fill'] * 100:.0f}%。"
    isp_boost = None
    boost_txt = ''
    if sized['m_booster_kg'] > 1.0:
        isp_boost = SUBSONIC_BOOSTER_ISP_S
        boost_txt = f"可抛弃助推器 {sized['m_booster_kg']:.0f} kg，固体比冲 {isp_boost:.0f} s。"
    note = (
        f"亚超结合：涡扇巡航 Ma {spec['mach']:.2f}，吸气比冲 {sized['isp_cruise_s']:.0f} s，"
        f"末端固体比冲 {isp_s:.0f} s。"
        f"全高空 {spec['alt_km']:.0f} km / 全掠海 {spec['sea_alt_km'] * 1000:.0f} m，"
        f"高空升阻比 {sized['ld']:.2f}，掠海升阻比 {sized['ld_sea']:.2f}。"
        f"末端冲刺按伯克级雷达视距计入总射程。"
        f"{mix_txt}"
        f"{boost_txt}折叠弹翼 {sized['m_wing_kg']:.0f} kg，死重 {dead:.0f} kg。{fit}"
    )
    return _base_fields(
        'turbofan_rocket', ignition, sized['l_head_m'], length_m - sized['l_head_m'],
        sized['fuel_kg'] + propellant, spec['mach'], sized['ld'], high_km, note,
        range_high_km=high_km, range_sea_km=sea_km, range_mixed_km=mixed_km,
        range_cruise_km=sized['range_high_m'] / 1000.0,
        range_terminal_km=None,
        cruise_mach=spec['mach'], cruise_alt_km=spec['alt_km'],
        m_dead_kg=dead, m_wing_kg=sized['m_wing_kg'],
        isp_boost_s=isp_boost, isp_cruise_s=sized['isp_cruise_s'], isp_rocket_s=isp_s,
        m_booster_kg=sized['m_booster_kg'], m_fuel_kg=sized['fuel_kg'],
    )


def estimate_ballistic(
    length_m: float,
    diameter_m: float,
    warhead_mass_kg: float,
    v_launch_mach: float,
    h_launch_km: float,
    isp_s: float,
    propellant_density: float,
    warhead_section: str = 'cylinder',
    coast_drag: bool = True,
    two_stage: bool = True,
) -> dict:
    """普通弹道导弹：头锥扣掉制导和战斗部后的剩余容积与圆柱段一起装药，再计重力阻力与大气滑行。

    warhead_section 为 biconic 或 waverider 时沿用滑翔体弹头，供同一助推器的弹道弧对照。
    coast_drag 为假时保留真空弹道，滑翔弹的下限对照用这一档。
    two_stage 控制固体助推是否按两级分段；默认两级，不再按弹长自动切换。
    """
    if length_m <= 0 or diameter_m <= 0:
        raise ValueError('弹长与弹径必须大于 0')
    if warhead_mass_kg < 0 or v_launch_mach < 0 or h_launch_km < 0:
        raise ValueError('战斗部、发射马赫数与高度不能为负')
    if isp_s <= 0 or propellant_density <= 0:
        raise ValueError('比冲与推进剂密度必须大于 0')
    nose_propellant = 0.0
    if warhead_section == 'cylinder':
        head_len, booster_len, guidance = ballistic_head_lengths_m(
            length_m, diameter_m, warhead_mass_kg,
        )
        payload_mass = warhead_mass_kg + guidance
        nose_propellant = ballistic_nose_propellant_kg(
            length_m, diameter_m, warhead_mass_kg, propellant_density,
        )
    elif warhead_section in ('biconic', 'waverider'):
        head_len, booster_len = head_and_booster_lengths_m(
            length_m, diameter_m, warhead_mass_kg, warhead_section,
        )
        payload_mass = glide_body_mass_kg(
            head_len, diameter_m, warhead_mass_kg, warhead_section,
        )
    else:
        raise ValueError(f'未知战斗部截面: {warhead_section}')
    propellant = propellant_mass_kg(diameter_m, booster_len, propellant_density) + nose_propellant
    dry = propellant * (1.0 - PROPELLANT_MASS_FRACTION) / PROPELLANT_MASS_FRACTION
    launch_mass = payload_mass + dry + propellant
    ve = isp_s * G0
    if two_stage:
        dv_ideal = _ideal_two_stage_dv(launch_mass, propellant, dry, ve)
        burnout_mass = launch_mass - propellant - dry * 0.60
        stages = '两级'
    else:
        if propellant >= launch_mass:
            raise ValueError('推进剂质量超过起飞质量')
        dv_ideal = ve * math.log(launch_mass / (launch_mass - propellant))
        burnout_mass = launch_mass - propellant
        stages = '单级'
    burn_time = ballistic_burn_time_s(
        propellant, launch_mass, isp_s, ballistic_liftoff_twr(launch_mass),
    )
    loss = ballistic_loss_m_s(dv_ideal, burn_time, h_launch_km)
    launch_speed = v_launch_mach * speed_of_sound_m_s(h_launch_km)
    speed = max(50.0, launch_speed + dv_ideal - loss)
    altitude = burnout_altitude_km(speed, h_launch_km)
    ground_km = ballistic_range_km(speed, altitude)
    if coast_drag:
        ground_km = ballistic_coast_range_km(
            ground_km, speed, altitude, burnout_mass, diameter_m,
        )
    section = '头锥扣除制导与战斗部，' if warhead_section == 'cylinder' else ''
    note = (
        f"普通弹道导弹：{stages}固体，{section}比冲 {isp_s:.0f} s，"
        f"关机速度 {speed / 1000.0:.2f} km/s，"
        f"关机高度 {altitude:.0f} km，按最优倾角取射程，不含滑翔。"
    )
    return _base_fields(
        'ballistic', launch_mass, head_len, booster_len, propellant,
        speed / speed_of_sound_m_s(0.0), None, ground_km, note,
        cruise_alt_km=altitude,
        isp_rocket_s=isp_s,
    )


def glide_floor_range_km(glide_range_km: float, ballistic_km: float, ld_ratio: float) -> float:
    """平衡滑翔短于同一助推器的弹道弧时，改用按升阻比延伸的再入航程。

    升阻比为 1 时与弹道弧相同，更高的升阻比按每 1 个单位加 8% 拉开。
    平衡滑翔已经更远时保持原值，大弹的滑翔标定不动。
    """
    if glide_range_km < 0 or ballistic_km <= 0 or ld_ratio <= 0:
        raise ValueError('滑翔航程、弹道航程与升阻比无效')
    lifting = ballistic_km * (1.0 + 0.08 * max(0.0, ld_ratio - 1.0))
    return max(glide_range_km, lifting)


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
    isp_air_s: float | None = None,
    ballistic_two_stage: bool = True,
    optimize_geometry: bool = True,
    l_head_m: float | None = None,
    d_head_m: float | None = None,
) -> dict:
    """按弹种估算。双锥体和乘波体助推滑翔由 missile_class 区分。

    隐身涡扇的宽和高可选。给出后按扁五边形外廓算质量，不再把弹径当成圆。
    isp_s 是固体火箭比冲。isp_air_s 只覆盖吸气巡航；不给时用弹种自己的吸气比冲。
    助推滑翔默认在底径锁定为弹径时搜索滑翔体长度；也可指定独立 l_head_m / d_head_m，或关闭 optimize_geometry。
    """
    canon = resolve_missile_class(missile_class)
    shape = glide_shape(canon)
    if shape is not None:
        from utils.missile_range.estimate import estimate_hgv
        use_opt = bool(optimize_geometry) and l_head_m is None and d_head_m is None
        result = estimate_hgv(
            length_m, diameter_m, warhead_mass_kg, shape,
            v_launch_mach, h_launch_km, isp_s, propellant_density,
            l_head_m=l_head_m, d_head_m=d_head_m,
            optimize_geometry=use_opt,
        )
        result = dict(result)
        # 滑翔下限仍对照双锥体助推器的真空弹道，弹道基线固定按默认两级。
        ballistic = estimate_ballistic(
            length_m, diameter_m, warhead_mass_kg,
            v_launch_mach, h_launch_km, isp_s, propellant_density,
            warhead_section='biconic',
            coast_drag=False,
            two_stage=True,
        )
        floored = glide_floor_range_km(
            float(result['range_km']), float(ballistic['range_km']), float(result['ld_ratio']),
        )
        result['missile_class'] = canon
        result['class_label'] = class_label(canon)
        note = class_blurb(canon) + f' 固体比冲 {isp_s:.0f} s。'
        if result.get('optimal_geometry'):
            span_name = '后缘宽度' if shape == 'waverider' else '底径'
            note += (
                f" 经几何搜索寻优：滑翔体长 {result['l_head_m']:.2f} m、"
                f"{span_name} {result['d_head_m']:.3f} m（长细比 {result['fineness']:.2f}，"
                f"升阻比 {result['ld_ratio']:.2f}），"
                f"总射程相比基线提升 {result['range_gain_km']:.1f} km (+{result['range_gain_pct']:.1f}%)。"
            )
        if floored > float(result['range_km']) + 0.05:
            result['range_km'] = round(floored, 1)
            note += '平衡滑翔短于同一助推器的弹道弧，改为按升阻比延伸后的再入航程。'
        result['note'] = note
        result['isp_boost_s'] = None
        result['isp_cruise_s'] = None
        result['isp_rocket_s'] = round(isp_s, 1)
        return result
    if canon in _SUBSONIC_SPECS:
        return estimate_subsonic_class(
            canon, length_m, diameter_m, warhead_mass_kg, v_launch_mach, h_launch_km,
            width_m, height_m, isp_air_s,
        )
    if canon in _DUCT_SPECS:
        return estimate_ducted(
            canon, length_m, diameter_m, warhead_mass_kg,
            v_launch_mach, h_launch_km, isp_s, propellant_density, isp_air_s,
        )
    if canon == 'turbofan_rocket':
        return estimate_turbofan_rocket(
            length_m, diameter_m, warhead_mass_kg,
            v_launch_mach, h_launch_km, isp_s, propellant_density, isp_air_s,
        )
    if canon == 'ballistic':
        return estimate_ballistic(
            length_m, diameter_m, warhead_mass_kg,
            v_launch_mach, h_launch_km, isp_s, propellant_density,
            two_stage=ballistic_two_stage,
        )
    raise ValueError(f'未知弹种: {missile_class}')
