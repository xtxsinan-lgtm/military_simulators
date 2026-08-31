"""战斗机巡航升阻比 (L/D) 统一物理估算。

全机队共用固定 (Cf0, k_e)，由几何/布局/表面直接预测 L/D，
不再用 F-35C/F-22 的「已知升阻比」做两机闭式标定。

物理框架：
    CD = CD0(摩擦/寄生阻力) + CDi(诱导阻力) + CDa(大迎角附加) + CDw(波阻)
    L/D = CL / CD

大迎角项：超过典型巡航 CL 后诱导/分离阻力按 (CL-CL_on)² 上升，
避免抛物线极曲线把 L/Dmax 推到 CL≈0.57（Ma 0.8 约 15 km）。
低翼载飞机同一高度 CL 更小，可以飞得更高。
无座舱无人机去掉风挡浸润；机长只进入马赫锥项（Ma 1.5 通常未触发）。
F-35 等 rough=True 机型加大浸润（肥机身 + 外形不平整，非微观表面粗糙），相对光滑隐身机降 L/D。
进气道独立于翼型/布局：DSI 无隔道、浸润基准；加莱特（caret）有隔道板与唇口，
亚/跨声速寄生阻力更高，但二维压缩面使超音速体积波阻更低（利于超巡）。
rough 的亚音速惩罚只进 CD0，拆成 FAT_MULT（肥胖）× BUMP_MULT（不平整）；
超音速另叠加肥机身/锯齿/厚翼体积波阻，
避免只靠加大浸润把加力极速仍推到 Ma 2+（公开包线约 Ma 1.6）。

波阻分四段，避免把跨声速 Korn 四次方直接外推到超音速（否则 Ma 1.5+ 的 CDw 会到 O(1)，L/D 崩掉）：
    1. 跨声速 Korn：CDw = 20·min(M-Mdd, 0.10)⁴，只刻画机翼阻力发散附近的小超量；
    2. 跨声速鼓包：机身阻力上升，从 Ma 0.90 起、在 Ma 1.08 附近见顶；
       不跟翼型 Korn Mdd 门控（大后掠 Mdd>1 会把 Ma 1 整段关掉，半径倒挂）；
    3. 超音速体积波阻：机身面积律 (M-1)² + 超音速前缘机翼项
       + 升力波阻 CL²·lift_wave_mach_factor(M) + 鸭翼附加 (M-1)²
       + rough 机肥机身/厚翼附加（不作用于光滑隐身机，保住 F-22 超巡）；
    4. 超过马赫锥后的附加波阻（翼尖-机头连线）。
    升力波阻马赫因子：刚超音速按 (M-1)，Ma 1.5–1.76 封顶，过了 1.76 再加重。
    线性 (M-1) 会让超巡带极曲线继续变陡、高度掉下来；封顶后 1.5–1.76
    仍贴着峰值高度，kg/km 大约只高 7%。Ma 1.5 的布雷盖惩罚不变。
    超过超巡带后再加重，是为了让能停在峰值的飞机在 1.76 之后开始掉高。
    实用最大巡航由 0.01 马赫高度搜索给出，不是把结果钉在 1.76。系数对全机队共用。
    允许掉到 11 km 后还能更快。

双三角翼（planform=double_delta 且给出内/外段后掠）按两段前缘分别算
Oswald 与机翼波阻，再按面积加权合成。折点半展站位可由展弦比与两段后掠
在「后缘近似平直、翼尖尖削」假设下反解；也可显式给出。
单段 sweep_deg 仍作为其它翼型或未填两段时的回退。

(Cf0, k_e) 取绝对值：历史闭式解再按 s≈1.194 统一抬升（歼-20≈1350 km），
ROUGH_MULT≈1.33 单独压 F-35（舰载 45 min 下≈1400 km）；运行时不读锚点。
Oswald 修正含在 k_e 中。仍保留 calibrate() 供对照/单元测试，运行时默认走 model_coefficients()。
"""
from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any, Literal

# ---------------------------------------------------------------------------
# 常数（ISA 11~20 km 等温层 + Korn 跨声速 + F-22/歼-20 超巡波阻标定）
# ---------------------------------------------------------------------------
G0 = 9.80665
R_AIR = 287.05287
GAMMA = 1.4
T_ISO = 216.65  # 11~20 km 等温层温度 (K)
RHO11 = 0.36391  # 11000 m 处密度 (kg/m^3)
KAPPA_A = 0.90  # Korn 方程翼型技术因子，固定为超临界翼型典型值
CDW_KORN_COEF = 20.0  # Mason/Lock-Korn 四次方系数，仅用于跨声速小超量
KORN_DM_CAP = 0.10  # Korn 超量马赫封顶；再大则交给超音速项，避免 (M-Mdd)⁴ 爆炸
COS_SWEEP_MIN = 0.20  # 后掠余弦下限，避免 90° 前缘时翼项发散
# 超音速波阻：体积/升力项使光滑隐身机超巡可飞；实用最大巡航由 Ma 1.2 以上
# 高度极值搜索给出（0.01 马赫网格；能飞满超巡带的机型约 Ma 1.79，歼-20 约 Ma 1.73）。
# 机身项 × (M-1)²；机翼项 × (t/c_n)² · max(M·cosΛ-1, 0)²
# 升力项 × CL²·lift_wave_mach_factor：Ma 1.5 压住超音速 L/D 避免半径倒挂，
# 1.5–1.76 不再随马赫加重，过了超巡带再加重，使峰值高度在 1.76 后回落。
SUPERCRUISE_BAND_HI = 1.76  # 超巡带上沿：此后升力波阻再随马赫加重
F22_SUPERCRUISE_MACH = SUPERCRUISE_BAND_HI
J20_SUPERCRUISE_MACH = 1.73
J35A_SUPERCRUISE_MACH = 1.61
CDW_SS_BODY = 0.00450
CDW_SS_WING = 3.00
CDW_SS_LIFT = 0.65
CDW_SS_LIFT_MACH_CAP = 0.50  # 升力波阻马赫因子封顶，对应 Ma 1.5
CDW_SS_LIFT_POST = 2.0  # 超过超巡带后的马赫因子斜率，1.80 相对峰值掉超过一格高度
CDW_CANARD = 0.004  # 鸭翼附加，乘 (M-1)²；90 kN→Ma 1.5、142 kN 加力→Ma 2.0
# 肥机身/不平整表面的超音速附加：只作用于 rough，亚音速 CD0 不变。
# 机身项 × (M-1)²：面积律差、锯齿缝、吸波涂层的型阻/波阻。
# 厚翼项 × (t/c_n)² (M-1)²：不要求前缘超音速，补上 Ma 1.3–1.8 厚翼体积波阻。
# 升力项 × CL²(M-1)：粗糙外形升力分布更差。
# 标定：FAT/BUMP=1 后靠厚翼项把 F-35A 加力收到约 Ma 1.64、C 约 1.54
# （公开包线 1.6；C 翼面积更大故略慢）；光滑 F-22 极速/超巡不变。
F35_MAX_SPEED_MACH = 1.6
CDW_SS_ROUGH_BODY = 0.006
CDW_SS_ROUGH_WING = 15.0
CDW_SS_ROUGH_LIFT = 0.15
# 跨声速阻力鼓包：机身项，不跟翼型 Korn Mdd。
# 峰值在 Ma 1.08（Ma 1.0 与 1.2 都靠近峰值），左侧较陡、右侧较缓，
# Ma 0.8 仍为零，Ma 1.5 已基本衰减（保住超巡 L/D）。
# 幅度须让布雷盖半径 Ma 1 / 1.2 < Ma 0.8，且 1.2 低于 1.35。
TRANSONIC_ONSET = 0.90
CDW_TRANS_AMP = 0.018
CDW_TRANS_PEAK = 1.08
CDW_TRANS_WIDTH_LO = 0.12
CDW_TRANS_WIDTH = 0.18
# 无尾/翼身融合面积律更好，只打折体积波阻（机身+机翼项），升力波阻仍按 CL
CDW_TAILLESS = 0.72
CDW_BWB = 0.90
# 无座舱浸润折扣：去掉风挡/框与座舱鼓包，机头更圆滑（相对有座舱约 −3%）
NO_CANOPY_MULT = 0.97
# 进气道：DSI 无附面层隔道，浸润取基准；加莱特有隔道板/唇口，寄生阻力↑
# 超音速体积波阻：加莱特二维压缩面更干净，相对 DSI 鼓包打折（只乘体积项）
INLET_DSI_WETTED = 1.00
INLET_CARET_WETTED = 1.05
INLET_DSI_CDW = 1.00
INLET_CARET_CDW = 0.90
# 肥电总包：F-35 等 rough=True 相对光滑隐身机抬高巡航 CD0。
# 拆成两项物理含义不同的乘数，避免用「表面粗糙」一个数扛全部：
#   FAT_MULT  —— 肥胖/容积率高：短粗机身、内埋容积，等效浸润面积放大
#   BUMP_MULT —— 外形不平整：DSI 鼓包、锯齿缝、舱门台阶、RAM 涂层局部干扰
# 微观表面粗糙次要，并入 BUMP。超音速另用 CDW_SS_ROUGH_*，不靠这两个数压极速。
# 统一极曲线：在历史闭式解 (Cf0,k_e) 上按尺度 s≈1.194 抬升，使歼-20 Ma0.8≈1350 km。
# F-35 航程短板拆成两块：机身残余 FAT×BUMP≈1.10（肥胖为主、不平整为辅），
# 发动机安装 F135 tsfc_install_mult=1.15（宽风扇/大核心）。二者合计压到约 1400 km。
FAT_MULT = 1.06
BUMP_MULT = 1.04
CF0_REF = 0.018831312446174107
K_E_REF = 1.9677054936141871
# 大迎角附加阻力：超过巡航 CL 后 (CL-CL_on)²，使 L/D 在标定高度附近见顶。
CL_AOA_ONSET = 0.35
CD_AOA_COEF = 2.0
# 双三角折点：几何无法闭合时的默认半展站位（内段占半展的比例）
DOUBLE_DELTA_KINK_DEFAULT = 0.45

PlanformId = Literal[
    'trapezoidal', 'swept', 'delta', 'diamond', 'unswept', 'lambda', 'double_delta',
]
LayoutId = Literal['conventional', 'canard', 'tailless']
InletId = Literal['dsi', 'caret']

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
# 进气道浸润乘数（绝对量级由 Cf0 吸收，这里只保留相对趋势）
INLET_WETTED_MULT: dict[str, float] = {
    'dsi': INLET_DSI_WETTED,  # DSI：无隔道
    'caret': INLET_CARET_WETTED,  # 加莱特：隔道板 + 唇口
}
# 进气道超音速体积波阻乘数（升力波阻不打折）
INLET_CDW_VOL_MULT: dict[str, float] = {
    'dsi': INLET_DSI_CDW,
    'caret': INLET_CARET_CDW,
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
    rough: bool  # 肥电总包（肥胖 + 外形不平整）—— 独立开关，与机型无绑定关系
    inlet: InletId = 'dsi'  # 进气道：dsi / caret（加莱特）；缺省 DSI
    length_m: float = 0.0  # 机身长度，未给马赫角时用于估算；缺省 0 表示不启用
    wingspan_m: float = 0.0  # 翼展；缺省 0 表示不启用
    mach_angle_deg: float = 0.0  # 翼尖-机头连线与机身轴线夹角（度）；优先于机长/翼展
    canopy: bool = True  # 有座舱风挡；无人机为 False，浸润更小
    sweep_inner_deg: float = 0.0  # 双三角内段前缘后掠（度）；0 表示未启用两段
    sweep_outer_deg: float = 0.0  # 双三角外段前缘后掠（度）；0 表示未启用两段
    sweep_kink_span_frac: float = 0.0  # 折点半展站位 (0,1)；0 表示由几何反解


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


def _canopy_from_dict(data: dict[str, Any]) -> bool:
    """座舱开关：显式 canopy 优先；否则 n_pilots>0 视为有座舱，无人机为无。"""
    if data.get('canopy') not in (None, ''):
        return _as_bool(data.get('canopy'), True)
    n_pilots = data.get('n_pilots')
    if n_pilots not in (None, ''):
        return float(n_pilots) > 0
    return True


def parse_inlet(value: Any) -> InletId:
    """解析进气道类型；空值视为 DSI。"""
    if value is None or value == '':
        return 'dsi'
    text = str(value).strip().lower()
    aliases = {
        'dsi': 'dsi',
        'caret': 'caret',
        'garrett': 'caret',
        '加莱特': 'caret',
        '加莱特进气道': 'caret',
    }
    if text not in aliases:
        raise ValueError(f'未知进气道 {value!r}，可选: dsi, caret')
    return aliases[text]  # type: ignore[return-value]


def inlet_wetted_mult(inlet: str) -> float:
    """进气道对浸润/寄生阻力的乘数。"""
    if inlet not in INLET_WETTED_MULT:
        raise ValueError(f'未知进气道 {inlet!r}，可选: {", ".join(INLET_WETTED_MULT)}')
    return INLET_WETTED_MULT[inlet]


def inlet_cdw_vol_mult(inlet: str) -> float:
    """进气道对超音速体积波阻的乘数（升力波阻不乘）。"""
    if inlet not in INLET_CDW_VOL_MULT:
        raise ValueError(f'未知进气道 {inlet!r}，可选: {", ".join(INLET_CDW_VOL_MULT)}')
    return INLET_CDW_VOL_MULT[inlet]


def aircraft_from_dict(data: dict[str, Any]) -> Aircraft:
    """从 JSON/表单字典构造 Aircraft；翼型或布局非法时抛出 ValueError。"""
    planform = str(data.get('planform') or 'trapezoidal').strip()
    if planform not in PLANFORM_MULT:
        raise ValueError(f'未知翼型 {planform!r}，可选: {", ".join(PLANFORM_MULT)}')
    layout = str(data.get('layout') or 'conventional').strip()
    if layout not in LAYOUT_MULT:
        raise ValueError(f'未知布局 {layout!r}，可选: {", ".join(LAYOUT_MULT)}')
    inlet = parse_inlet(data.get('inlet'))
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
        inlet=inlet,
        length_m=_optional_positive_float(data.get('length_m')),
        wingspan_m=_optional_positive_float(data.get('wingspan_m')),
        mach_angle_deg=_optional_positive_float(data.get('mach_angle_deg')),
        canopy=_canopy_from_dict(data),
        sweep_inner_deg=_optional_positive_float(data.get('sweep_inner_deg')),
        sweep_outer_deg=_optional_positive_float(data.get('sweep_outer_deg')),
        sweep_kink_span_frac=_optional_positive_float(data.get('sweep_kink_span_frac')),
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


def has_double_delta_sweep(ac: Aircraft) -> bool:
    """是否启用双三角两段后掠（翼型为 double_delta 且内外段均已给出）。"""
    return (
        ac.planform == 'double_delta'
        and ac.sweep_inner_deg > 0.0
        and ac.sweep_outer_deg > 0.0
    )


def double_delta_kink_span_frac(
    inner_deg: float,
    outer_deg: float,
    AR: float,
    kink_span_frac: float = 0.0,
) -> float:
    """双三角折点半展站位 η（内段占半展的比例）。

    若给定 kink_span_frac ∈ (0,1) 则用之；
    否则假定后缘近似平直、翼尖尖削，由展弦比与两段后掠反解：
        4/AR = tan(Λ_out) + (tan(Λ_in) − tan(Λ_out)) · η²
    解出的 η 越界则回落到默认 0.45。
    """
    if 0.0 < kink_span_frac < 1.0:
        return kink_span_frac
    tan_in = math.tan(math.radians(inner_deg))
    tan_out = math.tan(math.radians(outer_deg))
    if AR <= 0.0 or abs(tan_in - tan_out) < 1e-9:
        return DOUBLE_DELTA_KINK_DEFAULT
    eta2 = (4.0 / AR - tan_out) / (tan_in - tan_out)
    if eta2 <= 1e-12 or eta2 >= 1.0:
        return DOUBLE_DELTA_KINK_DEFAULT
    return math.sqrt(eta2)


def double_delta_area_weights(
    inner_deg: float,
    outer_deg: float,
    kink_span_frac: float,
) -> tuple[float, float]:
    """尖翼尖、平直后缘假设下的内外段面积权重 (w_in, w_out)。"""
    eta = kink_span_frac
    if eta <= 0.0 or eta >= 1.0:
        raise ValueError('折点半展站位须在 (0, 1) 内')
    tan_in = math.tan(math.radians(inner_deg))
    tan_out = math.tan(math.radians(outer_deg))
    s_in = eta * (eta * tan_in + 2.0 * (1.0 - eta) * tan_out)
    s_out = (1.0 - eta) ** 2 * tan_out
    total = s_in + s_out
    if total <= 1e-12:
        return 0.5, 0.5
    return s_in / total, s_out / total


def double_delta_panels(ac: Aircraft) -> tuple[float, float, float, float]:
    """返回 (内段后掠°, 外段后掠°, 内段面积权重, 外段面积权重)。"""
    if ac.sweep_inner_deg <= 0.0 or ac.sweep_outer_deg <= 0.0:
        raise ValueError('双三角两段后掠须给出正的内段与外段角度')
    eta = double_delta_kink_span_frac(
        ac.sweep_inner_deg, ac.sweep_outer_deg, ac.AR, ac.sweep_kink_span_frac,
    )
    w_in, w_out = double_delta_area_weights(
        ac.sweep_inner_deg, ac.sweep_outer_deg, eta,
    )
    return ac.sweep_inner_deg, ac.sweep_outer_deg, w_in, w_out


def blend_sweep_quantity(ac: Aircraft, fn: Callable[[float], float]) -> float:
    """后掠相关标量：双三角按面积加权两段，否则用单段 sweep_deg。"""
    if has_double_delta_sweep(ac):
        inner_deg, outer_deg, w_in, w_out = double_delta_panels(ac)
        return w_in * fn(inner_deg) + w_out * fn(outer_deg)
    return fn(ac.sweep_deg)


def oswald_sweep_deg(ac: Aircraft) -> float:
    """Oswald / 展示用等效前缘后掠：双三角为面积加权，否则为 sweep_deg。"""
    return blend_sweep_quantity(ac, lambda sweep: sweep)


def oswald_e_for_aircraft(ac: Aircraft) -> float:
    """机翼 Oswald 效率：双三角按两段 e(Λ) 面积加权。"""
    return blend_sweep_quantity(ac, lambda sweep: oswald_e_raw(ac.AR, sweep))


def wetted_area_factor(ac: Aircraft) -> float:
    """浸润面积/参考面积的相对因子。

    - 翼型越厚，浸润面积/摩擦阻力略增
    - 三角翼/双三角/钻石翼/兰姆达翼相比梯形翼浸润面积/参考面积略小；平直翼略大
    - 鸭式布局多一个升力面；无尾布局减少
    - 翼身融合 (bwb) 与肥电 (rough) 是两个完全独立的开关
    - rough 乘 FAT_MULT×BUMP_MULT（F-35 肥胖 + 外形不平整，非微观表面粗糙）
    - 无座舱（无人机）去掉风挡/框，机头更圆滑，浸润略减
    - 进气道：DSI 无隔道；加莱特隔道板/唇口抬高浸润
    """
    planform_mult = PLANFORM_MULT[ac.planform]
    layout_mult = LAYOUT_MULT[ac.layout]
    bwb_mult = 0.90 if ac.bwb else 1.00
    rough_mult = (FAT_MULT * BUMP_MULT) if ac.rough else 1.00
    canopy_mult = 1.0 if ac.canopy else NO_CANOPY_MULT
    inlet_mult = inlet_wetted_mult(ac.inlet)
    thickness_mult = 1.0 + 4.0 * ac.tc
    return (
        thickness_mult * planform_mult * layout_mult
        * bwb_mult * rough_mult * canopy_mult * inlet_mult
    )


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
    return CDW_KORN_COEF * excess ** 4 if excess > 0.0 else 0.0


def drag_divergence_mach_at(CL: float, sweep_deg: float, tc: float) -> float:
    """单段前缘的 Korn 阻力发散马赫数 Mdd。"""
    cos_s = math.cos(math.radians(sweep_deg))
    return KAPPA_A / cos_s - tc / cos_s - CL / (10.0 * cos_s ** 2)


def drag_divergence_mach(CL: float, ac: Aircraft) -> float:
    """Korn 方程阻力发散马赫数 Mdd；双三角为两段面积加权。"""
    return blend_sweep_quantity(
        ac, lambda sweep: drag_divergence_mach_at(CL, sweep, ac.tc),
    )


def cd_wave_korn_at(mach: float, CL: float, sweep_deg: float, tc: float) -> float:
    """单段前缘的封顶 Korn 波阻。"""
    dm = mach - drag_divergence_mach_at(CL, sweep_deg, tc)
    if dm <= 0.0:
        return 0.0
    return CDW_KORN_COEF * min(dm, KORN_DM_CAP) ** 4


def cd_wave_korn(CL: float, ac: Aircraft) -> float:
    """跨声速 Korn 波阻；超量马赫封顶，避免四次方在超音速爆炸。

    双三角按两段分别算再面积加权，避免先合成等效后掠再代入非线性 Korn。
    """
    return blend_sweep_quantity(
        ac, lambda sweep: cd_wave_korn_at(ac.mach, CL, sweep, ac.tc),
    )


def transonic_gaussian(mach: float) -> float:
    """跨声速鼓包形状（0–1）：机身阻力上升，与翼型 Korn Mdd 无关。

    峰值左侧较陡、右侧较缓，使 Ma 1.0 与 1.2 都靠近峰值、Ma 1.5 已衰减。
    """
    if mach <= 0:
        raise ValueError('马赫数须为正')
    if mach <= TRANSONIC_ONSET:
        return 0.0
    width = CDW_TRANS_WIDTH_LO if mach < CDW_TRANS_PEAK else CDW_TRANS_WIDTH
    x = (mach - CDW_TRANS_PEAK) / width
    return math.exp(-0.5 * x * x)


def cd_wave_transonic_at(mach: float, CL: float, sweep_deg: float, tc: float) -> float:
    """机身跨声速鼓包。CL/后掠/厚度保留签名以兼容双三角加权调用。"""
    del CL, sweep_deg, tc
    return CDW_TRANS_AMP * transonic_gaussian(mach)


def cd_wave_transonic(mach: float, CL: float, ac: Aircraft) -> float:
    """跨声速阻力鼓包：Ma 0.90 起、Ma 1.08 附近见顶，超音速衰减。"""
    if mach <= 0:
        raise ValueError('马赫数须为正')
    del CL, ac
    return CDW_TRANS_AMP * transonic_gaussian(mach)


def cd_wave_ss_wing_at(mach: float, sweep_deg: float, tc: float) -> float:
    """单段前缘的超音速机翼体积波阻。"""
    cos_s = max(abs(math.cos(math.radians(sweep_deg))), COS_SWEEP_MIN)
    excess_le = mach * cos_s - 1.0
    if excess_le <= 0.0:
        return 0.0
    return CDW_SS_WING * (tc / cos_s) ** 2 * excess_le ** 2


def cd_wave_ss_rough_wing_at(mach: float, sweep_deg: float, tc: float) -> float:
    """rough 机厚翼超音速体积波阻：M>1 即有，不要求前缘超音速。"""
    if mach <= 1.0:
        return 0.0
    cos_s = max(abs(math.cos(math.radians(sweep_deg))), COS_SWEEP_MIN)
    dm = mach - 1.0
    return CDW_SS_ROUGH_WING * (tc / cos_s) ** 2 * dm ** 2


def cd_wave_ss_rough(mach: float, ac: Aircraft, CL: float = 0.0) -> float:
    """肥机身/不平整表面的超音速附加波阻。

    只作用于 rough=True；光滑隐身机为 0，以免破坏 F-22 超巡标定。
    机身项与厚翼项按体积波阻 (M-1)²；升力项按 CL²(M-1)。
    双三角厚翼项按两段面积加权。
    """
    if not ac.rough or mach <= 1.0:
        return 0.0
    dm = mach - 1.0
    cdw = CDW_SS_ROUGH_BODY * dm ** 2
    cdw += blend_sweep_quantity(
        ac, lambda sweep: cd_wave_ss_rough_wing_at(mach, sweep, ac.tc),
    )
    if CL > 0.0:
        cdw += CDW_SS_ROUGH_LIFT * (CL ** 2) * dm
    return cdw


def lift_wave_mach_factor(mach: float) -> float:
    """升力波阻的马赫因子：刚超音速按 (M-1)，超巡带封顶，过后再加重。

    线性 (M-1) 会让 1.76 的极曲线 k 继续变大，最佳高度掉下来、CL 更低，
    每公里油耗比 1.5 高一截。1.5–1.76 封顶后 Ma 1.5 的布雷盖惩罚不变；
    过了 SUPERCRUISE_BAND_HI 再按 CDW_SS_LIFT_POST 加重，全机队共用。
    """
    if mach <= 1.0:
        return 0.0
    dm = mach - 1.0
    if dm <= CDW_SS_LIFT_MACH_CAP:
        return dm
    if mach <= SUPERCRUISE_BAND_HI:
        return CDW_SS_LIFT_MACH_CAP
    return CDW_SS_LIFT_MACH_CAP + CDW_SS_LIFT_POST * (mach - SUPERCRUISE_BAND_HI)


def cd_wave_supersonic(mach: float, ac: Aircraft, CL: float = 0.0) -> float:
    """M>1 后的体积波阻 + 升力波阻 + 鸭翼附加 + rough 超音速附加。

    机身/升力/鸭翼项整机计算一次；机翼前缘项双三角按两段面积加权。
    无尾/翼身融合/加莱特进气道只打折体积项，升力波阻与 rough 附加不打折。
    升力项在高空大 CL 时压低超音速 L/D，避免布雷盖半径超过亚音速；
    马赫因子在超巡带封顶，过了 1.76 再加重，峰值高度开始回落。
    """
    if mach <= 1.0:
        return 0.0
    dm = mach - 1.0
    cdw_wing = blend_sweep_quantity(
        ac, lambda sweep: cd_wave_ss_wing_at(mach, sweep, ac.tc),
    )
    cdw = CDW_SS_BODY * dm ** 2 + cdw_wing
    if ac.layout == 'tailless':
        cdw *= CDW_TAILLESS
    if ac.bwb:
        cdw *= CDW_BWB
    cdw *= inlet_cdw_vol_mult(ac.inlet)
    if ac.layout == 'canard':
        cdw += CDW_CANARD * dm ** 2
    if CL > 0.0:
        cdw += CDW_SS_LIFT * (CL ** 2) * lift_wave_mach_factor(mach)
    cdw += cd_wave_ss_rough(mach, ac, CL)
    return cdw


def cd_high_aoa(CL: float) -> float:
    """大迎角附加阻力：CL 超过巡航起点后按超出量平方增长。"""
    excess = CL - CL_AOA_ONSET
    return CD_AOA_COEF * excess ** 2 if excess > 0.0 else 0.0


def cd_wave(CL: float, ac: Aircraft) -> float:
    """总波阻 = 封顶 Korn + 跨声速鼓包 + 超音速体积/升力/鸭翼/rough 项 +（可选）马赫锥外附加。"""
    cdw = (
        cd_wave_korn(CL, ac)
        + cd_wave_transonic(ac.mach, CL, ac)
        + cd_wave_supersonic(ac.mach, ac, CL)
    )
    phi = aircraft_mach_angle_rad(ac)
    if phi is not None:
        cdw += cd_wave_mach_angle(ac.mach, phi)
    return cdw


def components(ac: Aircraft) -> dict[str, float]:
    """单机中间量：CL、e_raw、K(=CDi 当 k_e=1)、W(浸润因子)、CDw、CDa。"""
    CL = cl_cruise(ac)
    e_raw = oswald_e_for_aircraft(ac)
    k_ind = CL ** 2 / (math.pi * ac.AR * e_raw)
    wetted = wetted_area_factor(ac)
    cdw = cd_wave(CL, ac)
    cda = cd_high_aoa(CL)
    return dict(CL=CL, e_raw=e_raw, K=k_ind, W=wetted, CDw=cdw, CDa=cda)


def calibrate(
    anchor1: Aircraft,
    ld1_target: float,
    anchor2: Aircraft,
    ld2_target: float,
) -> tuple[float, float]:
    """用两个已知 L/D 的锚点解出 (Cf0, k_e)。"""
    c1 = components(anchor1)
    c2 = components(anchor2)

    c_rhs1 = c1['CL'] / ld1_target - c1['CDw'] - c1['CDa']
    c_rhs2 = c2['CL'] / ld2_target - c2['CDw'] - c2['CDa']

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
    cda = c['CDa']
    cd = cd0 + cdi + cdw + cda
    ld = c['CL'] / cd
    return ld, dict(
        CL=c['CL'],
        e_used=k_e * c['e_raw'],
        CD0=cd0,
        CDi=cdi,
        CDw=cdw,
        CDa=cda,
        CD=cd,
    )


def parasite_cd0(ac: Aircraft, cf0: float) -> float:
    """由标定 Cf0 与浸润因子估算零升阻力系数 CD0（起飞可用）。"""
    if cf0 <= 0:
        raise ValueError('Cf0 须为正才能估算 CD0')
    return cf0 * wetted_area_factor(ac)


def model_coefficients() -> tuple[float, float]:
    """统一物理模型的 (Cf0, k_e)，全机队共用。"""
    return CF0_REF, K_E_REF


def default_ld_anchor_aircraft() -> tuple[Aircraft, float, Aircraft, float]:
    """对照用参考机几何（不再作为运行时标定输入）。

    返回光滑 F-22 与粗糙 F-35C 在 CSV 巡航点的几何，以及模型预测 L/D，
    便于单元测试核对 rough 惩罚方向。
    """
    f35c = Aircraft(
        'F-35C', AR=2.77, sweep_deg=30.9, wing_loading=0.341,
        tc=0.0510, mach=0.8, alt_m=11300,
        planform='trapezoidal', layout='conventional',
        bwb=False, rough=True, inlet='dsi',
    )
    f22 = Aircraft(
        'F-22', AR=2.37, sweep_deg=41.3, wing_loading=0.318,
        tc=0.0520, mach=0.8, alt_m=11800,
        planform='trapezoidal', layout='conventional',
        bwb=False, rough=False, inlet='caret',
    )
    cf0, k_e = model_coefficients()
    ld35, _ = predict_ld(f35c, cf0, k_e)
    ld22, _ = predict_ld(f22, cf0, k_e)
    return f35c, ld35, f22, ld22


def calibrate_default_anchors() -> tuple[float, float]:
    """兼容旧名：返回统一模型系数。"""
    return model_coefficients()


def estimate_takeoff_cd0(ac: Aircraft) -> float:
    """用统一模型系数估算该机起飞用零升阻力系数。"""
    cf0, _k_e = model_coefficients()
    return parasite_cd0(ac, cf0)
