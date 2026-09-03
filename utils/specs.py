"""舰载机 / 航母参数规格。"""
from __future__ import annotations

from dataclasses import dataclass

from utils.takeoff.ski_jump_geometry import compute_ski_jump_arc
from utils.takeoff.takeoff_config import physics_config

_PHYS = physics_config()
PILOT_LOAD_KG = float(_PHYS['pilot_load_kg'])
A2A_MISSILE_COUNT = int(_PHYS['a2a_missile_count'])

# 数据库 type_label：垂直/短距起降（VTOL/STOVL）与倾转旋翼
VTOL_TYPE_LABEL = 'v/stol'
TILTROTOR_TYPE_LABEL = 'tiltrotor'
CONVENTIONAL_TYPE_LABEL = 'conventional'

# 需要主喷管尾流波及模型的 Web/仿真模式（须配合 VTOL 机型）
PLUME_SIMULATION_MODES = frozenset({'short_takeoff', 'short_ski_jump'})


def is_vtol_aircraft(aircraft: AircraftSpec | str) -> bool:
    """是否为 VTOL/STOVL 机型（type_label == 'v/stol'）。"""
    label = aircraft if isinstance(aircraft, str) else aircraft.type_label
    return label == VTOL_TYPE_LABEL


def is_tiltrotor_aircraft(aircraft: AircraftSpec | str) -> bool:
    """是否为倾转旋翼机型（type_label == 'tiltrotor'）。"""
    label = aircraft if isinstance(aircraft, str) else aircraft.type_label
    return label == TILTROTOR_TYPE_LABEL


def is_conventional_aircraft(aircraft: AircraftSpec | str) -> bool:
    """是否为常规固定翼舰载机。"""
    label = aircraft if isinstance(aircraft, str) else aircraft.type_label
    return label == CONVENTIONAL_TYPE_LABEL


def simulation_uses_plume_model(mode: str, aircraft: AircraftSpec) -> bool:
    """当前仿真是否应计算主喷管尾流波及范围（仅 VTOL + 短距模式）。"""
    return mode in PLUME_SIMULATION_MODES and is_vtol_aircraft(aircraft)


def uses_propeller_power(aircraft: AircraftSpec) -> bool:
    """是否按恒定轴功率（桨盘动量理论）计算起飞推力，而非恒定喷气推力。"""
    return bool(
        aircraft.shaft_power_sl_w and aircraft.shaft_power_sl_w > 0
        and aircraft.prop_diameter_m and aircraft.prop_diameter_m > 0
    )


@dataclass(frozen=True)
class AircraftSpec:
    id: str
    name: str
    type_label: str  # 'conventional' | 'v/stol' | 'tiltrotor'
    mtow_kg: float
    empty_kg: float
    internal_fuel_kg: float
    max_payload_kg: float  # 最大外挂/载弹量（资料值，非 MTOW 推算）
    bvr_missile: str
    missile_mass_kg: float
    sweep_le_deg: float
    wingspan_m: float
    wing_area_m2: float
    wing_height_m: float
    cd0: float = 0.039
    t_max_sl_n: float | None = None
    t_main_stovl_sl_n: float | None = None
    t_liftfan_sl_n: float | None = None
    t_rollposts_sl_n: float | None = None
    exhaust_mdot_kg_s: float | None = None
    exhaust_d0_m: float | None = None
    exhaust_height_m: float | None = None
    # 倾转旋翼 / 涡桨：海平面总轴功率与桨盘直径（推力由功率换算）
    shaft_power_sl_w: float | None = None
    prop_diameter_m: float | None = None
    nacelle_blockage_frac: float | None = None
    n_pilots: int = 1
    notes: str = ''
    # 起飞增升：仅 layout=canard 且填了鸭翼面积时启用
    layout: str = 'conventional'
    canard_htail_area_m2: float | None = None

    @property
    def is_vtol(self) -> bool:
        """VTOL/STOVL 机型（如 F-35B、AV-8B）。"""
        return is_vtol_aircraft(self)

    @property
    def is_tiltrotor(self) -> bool:
        """倾转旋翼机型（如 MV-22）。"""
        return is_tiltrotor_aircraft(self)

    @property
    def uses_propeller_power(self) -> bool:
        """涡桨 / 倾转旋翼：有轴功率与桨盘直径，滑跃按恒定功率而非恒定推力。"""
        return uses_propeller_power(self)

    @property
    def has_lift_fan(self) -> bool:
        """是否配备升力风扇（F-35B 有，鹞式/AV-8B 无）。"""
        return bool(self.t_liftfan_sl_n and self.t_liftfan_sl_n > 0)

    def exhaust_plume_params(self):
        """构造本机尾流模型参数；未填 ṁ/d₀ 时用机型默认值或 Pegasus/F-35B 回退。"""
        from utils.takeoff.exhaust_plume import (
            EXHAUST_D0_M,
            EXHAUST_HEIGHT_M,
            EXHAUST_MDOT_KG_S,
            ExhaustPlumeParams,
            PEGASUS_AIRFLOW_LB_S,
            calc_exhaust_d0_from_engine_diameter,
            calc_exhaust_u0_from_thrust_mdot,
            lb_s_to_kg_s,
        )

        thrust = self.t_main_stovl_sl_n
        if thrust is None or thrust <= 0:
            return ExhaustPlumeParams()

        if self.exhaust_mdot_kg_s is not None:
            mdot = self.exhaust_mdot_kg_s
        elif self.id == 'AV-8B':
            mdot = lb_s_to_kg_s(PEGASUS_AIRFLOW_LB_S)
        else:
            mdot = EXHAUST_MDOT_KG_S

        u0 = calc_exhaust_u0_from_thrust_mdot(thrust, mdot)
        d0 = self.exhaust_d0_m
        if d0 is None and self.id == 'AV-8B':
            d0 = calc_exhaust_d0_from_engine_diameter(1.219)
        if d0 is None:
            d0 = EXHAUST_D0_M
        height = self.exhaust_height_m if self.exhaust_height_m is not None else self.wing_height_m
        if height is None:
            height = EXHAUST_HEIGHT_M
        return ExhaustPlumeParams(
            mdot_kg_s=mdot,
            u0_mps=u0,
            d0_m=d0,
            height_m=height,
        )

    @property
    def a2a_mass_kg(self) -> float:
        """正常起飞重量：空重 + 满内油 + 飞行员×0.1 t + 4 枚中距弹。"""
        return (self.empty_kg + self.internal_fuel_kg
                + A2A_MISSILE_COUNT * self.missile_mass_kg
                + self.n_pilots * PILOT_LOAD_KG)


@dataclass(frozen=True)
class CarrierSpec:
    id: str
    name: str
    nation: str
    max_speed_kt: float
    ski_jump: bool
    total_deck_length_m: float
    ski_jump_angle_deg: float = 0.0
    ski_jump_height_m: float | None = None
    f35b_capable: bool = False
    notes: str = ''
    deck_length_source: str = ''

    def deck_wind_kt(self) -> float:
        return self.max_speed_kt

    def ski_jump_geom(self):
        if not self.ski_jump:
            return None
        return compute_ski_jump_arc(self.ski_jump_angle_deg, lip_height_m=self.ski_jump_height_m)

    def ski_jump_arc_m(self) -> float:
        g = self.ski_jump_geom()
        return g.arc_length_m if g else 0.0

    def ski_jump_horizontal_m(self) -> float:
        g = self.ski_jump_geom()
        return g.horizontal_m if g else 0.0

    def deck_fits_distance(self, required_m: float) -> bool:
        return required_m <= self.total_deck_length_m
