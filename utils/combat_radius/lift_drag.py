"""战斗机巡航升阻比 (L/D) 估算。

用两个已知 L/D 的锚点机型，闭式线性解标定 (Cf0, k_e)，
再代入任意第三型机估算其 L/D。

物理框架：
    CD = CD0(摩擦/寄生阻力) + CDi(诱导阻力) + CDw(跨声速波阻)
    L/D = CL / CD

标定原理（闭式线性解）：
    CDi = K_raw / k_e，其中 K_raw = CL²/(π·AR·e_raymer)，k_e 未知
    CD0 = Cf0 · W，其中 W 为浸润面积代理因子，Cf0 未知
    对每个锚点 i：CL_i / (Cf0·W_i + K_i/k_e + CDw_i) = target_i
    整理为线性方程组（令 x=Cf0, y=1/k_e）：
        W_1·x + K_1·y = C_1
        W_2·x + K_2·y = C_2
    其中 C_i = CL_i/target_i - CDw_i，用克莱姆法则直接求解，无需迭代。
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Literal

# ---------------------------------------------------------------------------
# 常数（ISA 11~20 km 等温层 + Korn 翼型技术因子）
# ---------------------------------------------------------------------------
G0 = 9.80665
R_AIR = 287.05287
GAMMA = 1.4
T_ISO = 216.65  # 11~20 km 等温层温度 (K)
RHO11 = 0.36391  # 11000 m 处密度 (kg/m^3)
KAPPA_A = 0.90  # Korn 方程翼型技术因子，固定为超临界翼型典型值
# Ma 0.8 巡航下 CDw≈0，此系数不参与 2 变量标定，留给更高马赫数场景

PlanformId = Literal[
    'trapezoidal', 'swept', 'delta', 'diamond', 'unswept', 'lambda', 'double_delta',
]
LayoutId = Literal['conventional', 'canard', 'tailless']

# 浸润面积/参考面积的相对因子（绝对量级由 Cf0 吸收，这里只保留相对趋势）
PLANFORM_MULT: dict[str, float] = {
    'trapezoidal': 1.00,  # 梯形翼
    'swept': 0.99,  # 后掠翼：相对梯形略减（后掠角本身另计入 Oswald）
    'delta': 0.97,  # 三角翼
    'double_delta': 0.975,  # 双三角翼：略多于单三角
    'diamond': 0.96,  # 钻石翼
    'lambda': 0.96,  # 兰姆达翼
    'unswept': 1.02,  # 平直翼：相对梯形略增
}
LAYOUT_MULT: dict[str, float] = {
    'conventional': 1.00,  # 常规
    'canard': 1.05,  # 鸭式：多一个升力面，浸润/干扰阻力↑
    'tailless': 0.93,  # 无尾：浸润面积↓
}


@dataclass
class Aircraft:
    """升阻比估算用的机翼/布局几何参数。"""

    name: str
    AR: float  # 展弦比
    sweep_deg: float  # 前缘后掠角 (度)
    wing_loading: float  # 翼载荷 (t/m^2)
    tc: float  # 厚弦比 (小数，如 0.051)
    mach: float
    alt_m: float
    planform: PlanformId
    layout: LayoutId
    bwb: bool  # 翼身融合 —— 独立开关，与机型无绑定关系
    rough: bool  # 表面是否不平整 —— 独立开关，与机型无绑定关系
    length_m: float = 0.0  # 机身长度，未给马赫角时用于估算；缺省 0 表示不启用
    wingspan_m: float = 0.0  # 翼展；缺省 0 表示不启用
    mach_angle_deg: float = 0.0  # 翼尖-机头连线与机身轴线夹角（度）；优先于机长/翼展


def _as_bool(value: Any, default: bool = False) -> bool:
    """将常见真假表示转为 bool（兼容 CSV/JSON/表单）。"""
    if value is None or value == '':
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value) and value != 0
    text = str(value).strip().lower()
    if text in ('1', 'true', 'yes', 'y', '是'):
        return True
    if text in ('0', 'false', 'no', 'n', '否'):
        return False
    raise ValueError(f'无法解析布尔值: {value!r}')


def aircraft_from_dict(data: dict[str, Any]) -> Aircraft:
    """从 JSON/表单字典构造 Aircraft；翼型或布局非法时抛出 ValueError。"""
    planform = str(data.get('planform') or 'trapezoidal').strip()
    if planform not in PLANFORM_MULT:
        raise ValueError(f'未知翼型 {planform!r}，可选: {", ".join(PLANFORM_MULT)}')
    layout = str(data.get('layout') or 'conventional').strip()
    if layout not in LAYOUT_MULT:
        raise ValueError(f'未知布局 {layout!r}，可选: {", ".join(LAYOUT_MULT)}')
    return Aircraft(
        name=str(data.get('name') or '未命名'),
        AR=float(data['AR']),
        sweep_deg=float(data['sweep_deg']),
        wing_loading=float(data['wing_loading']),
        tc=float(data['tc']),
        mach=float(data['mach']),
        alt_m=float(data['alt_m']),
        planform=planform,  # type: ignore[arg-type]
        layout=layout,  # type: ignore[arg-type]
        bwb=_as_bool(data.get('bwb'), False),
        rough=_as_bool(data.get('rough'), False),
        length_m=_optional_positive_float(data.get('length_m')),
        wingspan_m=_optional_positive_float(data.get('wingspan_m')),
        mach_angle_deg=_optional_positive_float(data.get('mach_angle_deg')),
    )


def _optional_positive_float(value: Any) -> float:
    """空值视为 0；否则转为 float（允许 0，负值在马赫角函数里再拒绝）。"""
    if value is None or value == '':
        return 0.0
    return float(value)


def aircraft_to_dict(ac: Aircraft) -> dict[str, Any]:
    """Aircraft → 可 JSON 序列化的字典。"""
    return asdict(ac)


def atmosphere(h_m: float) -> tuple[float, float]:
    """返回 (rho, a)：密度 (kg/m^3)、声速 (m/s)。适用于 11–20 km 等温层。"""
    factor = math.exp(-G0 * (h_m - 11000.0) / (R_AIR * T_ISO))
    rho = RHO11 * factor
    a = math.sqrt(GAMMA * R_AIR * T_ISO)
    return rho, a


def cl_cruise(ac: Aircraft) -> float:
    """由翼载荷与动压反推平飞所需升力系数。"""
    rho, a = atmosphere(ac.alt_m)
    speed = ac.mach * a
    q = 0.5 * rho * speed ** 2
    ws_pa = ac.wing_loading * 1000.0 * G0  # t/m^2 → N/m^2
    return ws_pa / q


def oswald_e_raw(AR: float, sweep_deg: float) -> float:
    """Raymer 经验公式：后掠翼的机翼 Oswald 效率因子（未乘 k_e 标定值）。"""
    sweep = math.radians(sweep_deg)
    return 4.61 * (1.0 - 0.045 * AR ** 0.68) * math.cos(sweep) ** 0.15 - 3.1


def wetted_area_factor(ac: Aircraft) -> float:
    """浸润面积/参考面积的相对因子。

    - 翼型越厚，浸润面积/摩擦阻力略增
    - 三角翼/双三角/钻石翼/兰姆达翼相比梯形翼浸润面积/参考面积略小；平直翼略大
    - 鸭式布局多一个升力面；无尾布局减少
    - 翼身融合 (bwb) 与表面不平整 (rough) 是两个完全独立的开关
    """
    planform_mult = PLANFORM_MULT[ac.planform]
    layout_mult = LAYOUT_MULT[ac.layout]
    bwb_mult = 0.90 if ac.bwb else 1.00
    rough_mult = 1.08 if ac.rough else 1.00
    thickness_mult = 1.0 + 4.0 * ac.tc
    return thickness_mult * planform_mult * layout_mult * bwb_mult * rough_mult


def mach_angle_rad(length_m: float, wingspan_m: float) -> float:
    """由机长与翼展估算翼尖-机头连线相对机身中轴线的夹角（弧度）。"""
    if length_m <= 0 or wingspan_m <= 0:
        raise ValueError('机身长度与翼展须为正才能计算马赫角')
    return math.atan((wingspan_m / 2.0) / length_m)


def aircraft_mach_angle_rad(ac: Aircraft) -> float | None:
    """机型马赫角（弧度）：优先用预设度数，否则由机长/翼展估算；都没有则 None。"""
    if ac.mach_angle_deg > 0.0:
        phi = math.radians(ac.mach_angle_deg)
        if math.sin(phi) <= 1e-12:
            raise ValueError('马赫角须在 (0, 90°) 内')
        return phi
    if ac.length_m > 0.0 and ac.wingspan_m > 0.0:
        return mach_angle_rad(ac.length_m, ac.wingspan_m)
    return None


def mach_cone_limit(phi_rad: float) -> float:
    """马赫锥刚好贴合翼尖-机头连线时的马赫数 M = 1 / sin(φ)。"""
    sine = math.sin(phi_rad)
    if sine <= 1e-12:
        raise ValueError('马赫角须在 (0, 90°) 内')
    return 1.0 / sine


def cd_wave_mach_angle(mach: float, phi_rad: float) -> float:
    """飞行马赫超过马赫角允许值后的附加波阻（与 Korn 同形的四次方）。

    法向马赫数 M·sin(φ) > 1 时，机翼处于马赫锥外，附加 CDw。
    """
    excess = mach * math.sin(phi_rad) - 1.0
    return 20.0 * excess ** 4 if excess > 0.0 else 0.0


def cd_wave(CL: float, ac: Aircraft) -> float:
    """Korn 方程估算阻力发散马赫数，超过后用四次方经验式估算波阻。

    若提供马赫角（或机长/翼展），再叠加超过马赫角后的附加波阻。
    """
    sweep = math.radians(ac.sweep_deg)
    cos_s = math.cos(sweep)
    m_dd = KAPPA_A / cos_s - ac.tc / cos_s - CL / (10.0 * cos_s ** 2)
    dm = ac.mach - m_dd
    cdw = 20.0 * dm ** 4 if dm > 0.0 else 0.0
    phi = aircraft_mach_angle_rad(ac)
    if phi is not None:
        cdw += cd_wave_mach_angle(ac.mach, phi)
    return cdw


def components(ac: Aircraft) -> dict[str, float]:
    """单机中间量：CL、e_raw、K(=CDi 当 k_e=1)、W(浸润因子)、CDw。"""
    CL = cl_cruise(ac)
    e_raw = oswald_e_raw(ac.AR, ac.sweep_deg)
    k_ind = CL ** 2 / (math.pi * ac.AR * e_raw)
    wetted = wetted_area_factor(ac)
    cdw = cd_wave(CL, ac)
    return dict(CL=CL, e_raw=e_raw, K=k_ind, W=wetted, CDw=cdw)


def calibrate(
    anchor1: Aircraft,
    ld1_target: float,
    anchor2: Aircraft,
    ld2_target: float,
) -> tuple[float, float]:
    """用两个已知 L/D 的锚点解出 (Cf0, k_e)。"""
    c1 = components(anchor1)
    c2 = components(anchor2)

    c_rhs1 = c1['CL'] / ld1_target - c1['CDw']
    c_rhs2 = c2['CL'] / ld2_target - c2['CDw']

    det = c1['W'] * c2['K'] - c2['W'] * c1['K']
    if abs(det) < 1e-12:
        raise ValueError('两锚点参数过于接近/退化，方程组奇异，无法唯一标定')

    cf0 = (c_rhs1 * c2['K'] - c_rhs2 * c1['K']) / det  # x = Cf0
    y_inv_ke = (c1['W'] * c_rhs2 - c2['W'] * c_rhs1) / det  # y = 1/k_e
    k_e = 1.0 / y_inv_ke

    if cf0 <= 0 or k_e <= 0:
        raise ValueError(
            f'标定结果物理无意义 (Cf0={cf0:.5f}, k_e={k_e:.5f})，'
            f'请检查锚点参数/目标 L/D 是否合理'
        )
    return cf0, k_e


def predict_ld(ac: Aircraft, cf0: float, k_e: float) -> tuple[float, dict[str, float]]:
    """用标定好的 (Cf0, k_e) 计算任意机型的 L/D 及阻力分解。"""
    c = components(ac)
    cdi = c['K'] / k_e
    cd0 = cf0 * c['W']
    cdw = c['CDw']
    cd = cd0 + cdi + cdw
    ld = c['CL'] / cd
    return ld, dict(
        CL=c['CL'],
        e_used=k_e * c['e_raw'],
        CD0=cd0,
        CDi=cdi,
        CDw=cdw,
        CD=cd,
    )


def parasite_cd0(ac: Aircraft, cf0: float) -> float:
    """由标定 Cf0 与浸润因子估算零升阻力系数 CD0（起飞可用）。"""
    if cf0 <= 0:
        raise ValueError('Cf0 须为正才能估算 CD0')
    return cf0 * wetted_area_factor(ac)


def default_ld_anchor_aircraft() -> tuple[Aircraft, float, Aircraft, float]:
    """默认两锚点：F-35C (L/D=8.52) 与 F-22 (L/D=8.62)，几何与机型库一致。"""
    f35c = Aircraft(
        'F-35C', AR=2.77, sweep_deg=30.9, wing_loading=0.341,
        tc=0.0510, mach=0.8, alt_m=11300,
        planform='trapezoidal', layout='conventional',
        bwb=False, rough=True,
    )
    f22 = Aircraft(
        'F-22', AR=2.37, sweep_deg=41.3, wing_loading=0.318,
        tc=0.0520, mach=0.8, alt_m=11800,
        planform='trapezoidal', layout='conventional',
        bwb=False, rough=False,
    )
    return f35c, 8.52, f22, 8.62


def calibrate_default_anchors() -> tuple[float, float]:
    """用默认 F-35C / F-22 锚点标定 (Cf0, k_e)。"""
    a1, ld1, a2, ld2 = default_ld_anchor_aircraft()
    return calibrate(a1, ld1, a2, ld2)


def estimate_takeoff_cd0(ac: Aircraft) -> float:
    """用默认锚点标定后，估算该机起飞用零升阻力系数。"""
    cf0, _k_e = calibrate_default_anchors()
    return parasite_cd0(ac, cf0)
