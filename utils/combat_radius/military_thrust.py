"""军推（最大不加力推力）简化理想循环估算。

模型假设：
- 理想 Brayton 循环：等熵压缩/膨胀、燃烧无压损、尾喷管完全膨胀至环境压力；
  核心流与涵道流分开（不混排），γ=1.4、cp=1004 J/(kg·K) 全程恒定。
- 军推按「T4 温度限制」工作点建模：全包线内涡轮前总温 T4 保持为输入值。
- 风扇压比不作为必填，按涵道比的经验关系估算（可手动覆盖）。
- 质量流量按「最大换算转速下换算流量恒定」假设，由海平面静止推力反标定，
  再随 P0·πr / sqrt(T0·τr) 缩放到当前高度/速度。

不包含进气道/喷管损失、放气、附件功、雷诺数修正等真实修正项 ——
结果为概念设计级估算，不能替代发动机厂商性能谱或整机热力循环仿真。
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

GAMMA = 1.4
CP = 1004.0  # J/(kg·K)
R = 287.0  # J/(kg·K)
G0 = 9.80665
TF_TO_N = 9806.65  # 1 吨力 = 9806.65 N
ETA_C_DEFAULT = 0.87


@dataclass
class StreamResult:
    """双涵道理想循环的排气速度与涡轮温比。"""

    V9: float  # 核心排气速度 (m/s)
    V19: float  # 涵道排气速度 (m/s)
    tau_t: float  # 涡轮总温比


@dataclass
class ThrustResult:
    """给定高度/马赫数下的可用军推及中间量。"""

    thrust_N: float  # 飞行条件下可用推力 (N)
    alpha: float  # 推力衰减比 T_flight / T_SL
    tau_r: float  # 来流总温比
    mdot_ratio: float  # 质量流比 flight / SLS
    T0: float  # 环境静温 (K)
    P0: float  # 环境静压 (Pa)
    fan_pr: float  # 实际使用的风扇压比


def isa(h_m: float) -> tuple[float, float]:
    """ISA 标准大气，返回 (T0 [K], P0 [Pa])；适用位势高度约 0–32 km。"""
    if h_m <= 11000:
        temp = 288.15 - 0.0065 * h_m
        pressure = 101325.0 * (temp / 288.15) ** 5.2559
    elif h_m <= 20000:
        temp = 216.65
        pressure = 22632.0 * math.exp(-G0 * (h_m - 11000.0) / (R * 216.65))
    else:
        temp = 216.65 + 0.001 * (h_m - 20000.0)
        pressure = 5474.9 * (216.65 / temp) ** 34.163
    return temp, pressure


def fan_pressure_ratio(bpr: float) -> float:
    """由涵道比估算风扇压比的经验式。"""
    return 1.2 + 2.0 * math.exp(-0.35 * bpr)


def ideal_stream_velocities(
    T0: float,
    tau_r: float,
    tau_c: float,
    tau_lambda: float,
    tau_f: float,
    bpr: float,
    eta_c_factor: float,
) -> StreamResult | None:
    """理想循环核心流 + 涵道流排气速度（不混排涡扇）。

    eta_c_factor >= 1 粗略放大压气机/风扇功，以惩罚非理想压缩（= 1/η_c）。
    若该组输入无物理解，返回 None。
    """
    work_term = ((tau_c - 1.0) + bpr * (tau_f - 1.0)) * eta_c_factor
    tau_t = 1.0 - (tau_r / tau_lambda) * work_term
    if tau_t <= 0:
        return None

    tt5 = T0 * tau_lambda * tau_t
    t9 = T0 * tau_lambda / (tau_r * tau_c)
    dt9 = tt5 - t9
    if dt9 < 0:
        return None
    v9 = math.sqrt(2.0 * CP * dt9)

    dt19 = tau_r * tau_f - 1.0
    if dt19 < 0:
        return None
    v19 = math.sqrt(2.0 * CP * T0 * dt19)

    return StreamResult(V9=v9, V19=v19, tau_t=tau_t)


def thrust_result_to_dict(result: ThrustResult) -> dict[str, Any]:
    """ThrustResult → 可 JSON 序列化的字典，并附带 kN / 吨力。"""
    d = asdict(result)
    d['thrust_kN'] = result.thrust_N / 1000.0
    d['thrust_tf'] = result.thrust_N / TF_TO_N
    return d


def estimate_military_thrust(
    bpr: float,
    opr: float,
    t4_K: float,
    tsl_N: float,
    alt_m: float,
    mach: float,
    eta_c: float = ETA_C_DEFAULT,
    fan_pr_override: float | None = None,
) -> ThrustResult:
    """估算给定高度/马赫数下的最大军推（不加力）。

    bpr: 涵道比；opr: 总压比；t4_K: 涡轮前总温 (K)，全包线保持；
    tsl_N: 海平面静止军推 (N)，标定点；alt_m / mach: 飞行条件；
    eta_c: 压气机/风扇等熵效率；fan_pr_override: 手动风扇压比，缺省由 BPR 估算。
    """
    if bpr < 0 or opr <= 1 or t4_K <= 0 or tsl_N <= 0 or alt_m < 0 or mach < 0:
        raise ValueError('参数超出有效范围')
    if eta_c <= 0 or eta_c > 1:
        raise ValueError('压气机效率 eta_c 须在 (0, 1] 内')

    eta_factor = 1.0 / eta_c
    if fan_pr_override is None:
        pi_f = fan_pressure_ratio(bpr)
    else:
        if fan_pr_override <= 1:
            raise ValueError('风扇压比须大于 1')
        pi_f = fan_pr_override

    tau_c = opr ** ((GAMMA - 1.0) / GAMMA)
    tau_f = pi_f ** ((GAMMA - 1.0) / GAMMA)

    t0, p0 = isa(alt_m)
    tau_r = 1.0 + (GAMMA - 1.0) / 2.0 * mach ** 2
    pi_r = tau_r ** (GAMMA / (GAMMA - 1.0))
    a0 = math.sqrt(GAMMA * R * t0)
    v0 = mach * a0
    tau_lambda = t4_K / t0

    flight = ideal_stream_velocities(t0, tau_r, tau_c, tau_lambda, tau_f, bpr, eta_factor)

    t0_ref, p0_ref = isa(0.0)
    tau_lambda_ref = t4_K / t0_ref
    ref = ideal_stream_velocities(t0_ref, 1.0, tau_c, tau_lambda_ref, tau_f, bpr, eta_factor)

    if flight is None or ref is None:
        raise ValueError(
            '当前参数组合下理想循环无解（T4 相对增压比/涵道比偏低，压气机耗功超出可用热焓）。'
            '请提高 T4 或降低 OPR/BPR。'
        )

    spec_ref = ref.V9 + bpr * ref.V19  # 海平面静止 V0=0
    mdot_core_sls = tsl_N / spec_ref

    mdot_flight = mdot_core_sls * (p0 / p0_ref) * pi_r * math.sqrt(t0_ref / (t0 * tau_r))
    spec_flight = (flight.V9 - v0) + bpr * (flight.V19 - v0)

    if spec_flight <= 0:
        raise ValueError(
            '该飞行条件下理想比推力 ≤ 0，超出模型有效范围'
            '（可能马赫数过高，或高度/温度组合极端）。'
        )

    thrust_n = mdot_flight * spec_flight
    return ThrustResult(
        thrust_N=thrust_n,
        alpha=thrust_n / tsl_N,
        tau_r=tau_r,
        mdot_ratio=mdot_flight / mdot_core_sls,
        T0=t0,
        P0=p0,
        fan_pr=pi_f,
    )
