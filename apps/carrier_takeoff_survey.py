"""
舰载机 × 航母最小起飞距离遍历（30°C，甲板风 = 航母最大航速）。

F-35B：策略 A（short_take_off / short_ski_jump_take_off）
常规型：ski_jump_take_off 最小总距搜索（仅 STOBAR 航母，不含 F-35B 适用舰）
"""
from __future__ import annotations

from typing import Any

import numpy as np

import simulators.takeoff.short_ski_jump_take_off as ski_stovl
import simulators.takeoff.short_take_off as flat_stovl
import simulators.takeoff.ski_jump_take_off as ski_conv
from utils.paths import AIRCRAFT_CSV, CARRIERS_CSV, SURVEY_RESULTS_TXT
from utils.specs import A2A_MISSILE_COUNT, AircraftSpec, CarrierSpec, PILOT_LOAD_KG

SURVEY_TEMP_C = 30.0
# 与仿真模块一致：俯仰角硬上限（°）
PITCH_MAX_DEG = ski_conv.PITCH_MAX_DEG

# 保存搜索范围默认值，便于多次运行前恢复
_SEARCH_DEFAULTS = {
    'flat_stovl': dict(
        NOZZLE_FINAL_DEG_START=flat_stovl.NOZZLE_FINAL_DEG_START,
        NOZZLE_FINAL_DEG_END=flat_stovl.NOZZLE_FINAL_DEG_END,
        V_TRANS_START_MPS=flat_stovl.V_TRANS_START_MPS,
        V_TRANS_END_MPS=flat_stovl.V_TRANS_END_MPS,
    ),
    'ski_stovl': dict(
        FLAT_LENGTH_M_LIST_A=list(ski_stovl.FLAT_LENGTH_M_LIST_A),
        NOZZLE_TAKEOFF_DEG_LIST_A=list(ski_stovl.NOZZLE_TAKEOFF_DEG_LIST_A),
        V_TRANS_MPS_LIST_A=list(ski_stovl.V_TRANS_MPS_LIST_A),
    ),
    'ski_conv': dict(
        PITCH_SEARCH_MIN=ski_conv.PITCH_SEARCH_MIN,
        PITCH_SEARCH_MAX=ski_conv.PITCH_SEARCH_MAX,
        FLAT_SEARCH_MAX_M=ski_conv.FLAT_SEARCH_MAX_M,
    ),
}
# 记录搜索边界是否被最优解触及，用于事后收紧未使用的边界
BOUNDARY_HITS: dict[str, set[str]] = {
    'flat_stovl': set(),
    'ski_stovl': set(),
    'ski_conv': set(),
}


AIRCRAFT: dict[str, AircraftSpec] = {
    'F-35B': AircraftSpec(
        id='F-35B', name='F-35B Lightning II', type_label='v/stol',
        mtow_kg=27200, empty_kg=14651, internal_fuel_kg=6400, max_payload_kg=6800,
        bvr_missile='AIM-120C AMRAAM', missile_mass_kg=152.0,
        sweep_le_deg=35, wingspan_m=10.7, wing_area_m2=42.7, wing_height_m=1.96,
        cd0=0.039,
        t_main_stovl_sl_n=83260, t_liftfan_sl_n=83260, t_rollposts_sl_n=14600,
        notes='STOVL 推力为垂起模式海平面标定值（15°C）；含升力风扇',
    ),
    'AV-8B': AircraftSpec(
        id='AV-8B', name='AV-8B Harrier II', type_label='v/stol',
        mtow_kg=14061, empty_kg=6340, internal_fuel_kg=3540, max_payload_kg=4200,
        bvr_missile='AIM-120C AMRAAM', missile_mass_kg=152.0,
        sweep_le_deg=37, wingspan_m=9.25, wing_area_m2=21.37, wing_height_m=1.55,
        cd0=0.043,
        t_main_stovl_sl_n=105000, t_liftfan_sl_n=0, t_rollposts_sl_n=1080,
        exhaust_mdot_kg_s=195.95, exhaust_d0_m=1.219, exhaust_height_m=1.55,
        notes='Pegasus F402-408；四矢量喷口、无升力风扇',
    ),
    'J-15': AircraftSpec(
        id='J-15', name='歼-15', type_label='conventional',
        mtow_kg=33000, empty_kg=17500, internal_fuel_kg=9800, max_payload_kg=6500,
        bvr_missile='PL-12', missile_mass_kg=199.0,
        sweep_le_deg=42, wingspan_m=14.7, wing_area_m2=67.84, wing_height_m=2.55,
        cd0=0.0475, t_max_sl_n=251000,
        notes='WS-10H/AL-31 双发最大加力约 251 kN（15°C 标定）',
    ),
    'J-15T': AircraftSpec(
        id='J-15T', name='歼-15T', type_label='conventional',
        mtow_kg=36300, empty_kg=18200, internal_fuel_kg=10000, max_payload_kg=8000,
        bvr_missile='PL-15', missile_mass_kg=210.0,
        sweep_le_deg=42, wingspan_m=14.7, wing_area_m2=67.84, wing_height_m=2.55,
        cd0=0.0475, t_max_sl_n=264000,
        notes='弹射型，滑跃舰上仍按 STOBAR 仿真；加力约 264 kN',
    ),
    'J-35': AircraftSpec(
        id='J-35', name='歼-35', type_label='conventional',
        mtow_kg=29500, empty_kg=15500, internal_fuel_kg=8000, max_payload_kg=8000,
        bvr_missile='PL-15', missile_mass_kg=210.0,
        sweep_le_deg=38, wingspan_m=13.6, wing_area_m2=66.9, wing_height_m=1.96,
        cd0=0.039, t_max_sl_n=186000,
        notes='WS-21 级双发加力约 186 kN（公开估算）',
    ),
    'MiG-29K': AircraftSpec(
        id='MiG-29K', name='MiG-29K', type_label='conventional',
        mtow_kg=24500, empty_kg=12000, internal_fuel_kg=4560, max_payload_kg=5500,
        bvr_missile='RVV-AE (R-77)', missile_mass_kg=175.0,
        sweep_le_deg=40, wingspan_m=11.99, wing_area_m2=34.5, wing_height_m=1.89,
        cd0=0.043, t_max_sl_n=176380,
        notes='2×RD-33MK 加力各 88.3 kN；Cd0=20°襟翼+落架+挂载',
    ),
    'Rafale-M': AircraftSpec(
        id='Rafale-M', name='阵风 M', type_label='conventional',
        mtow_kg=24500, empty_kg=10600, internal_fuel_kg=4700, max_payload_kg=9500,
        bvr_missile='MBDA Meteor', missile_mass_kg=190.0,
        sweep_le_deg=48, wingspan_m=10.80, wing_area_m2=45.7, wing_height_m=1.90,
        cd0=0.039, t_max_sl_n=150000,
        notes='2×M88-2/E4 加力各 75 kN（15°C SL）；Cd0=20°襟翼+落架+挂载',
    ),
    'FA-18E': AircraftSpec(
        id='FA-18E', name='F/A-18E Super Hornet', type_label='conventional',
        mtow_kg=29937, empty_kg=14552, internal_fuel_kg=6667, max_payload_kg=8050,
        bvr_missile='AIM-120C AMRAAM', missile_mass_kg=152.0,
        sweep_le_deg=20, wingspan_m=13.62, wing_area_m2=46.5, wing_height_m=1.55,
        cd0=0.044, t_max_sl_n=195800,
        notes='2×F414-GE-400 加力各 97.9 kN（15°C SL）；Cd0=20°襟翼+落架+挂载',
    ),
    'FA-18C': AircraftSpec(
        id='FA-18C', name='F/A-18C/D Hornet', type_label='conventional',
        mtow_kg=23541, empty_kg=10680, internal_fuel_kg=4930, max_payload_kg=6215,
        bvr_missile='AIM-120C AMRAAM', missile_mass_kg=152.0,
        sweep_le_deg=20, wingspan_m=11.43, wing_area_m2=38.0, wing_height_m=1.52,
        cd0=0.045, t_max_sl_n=156600,
        notes='2×F404-GE-402 加力各 78.3 kN（15°C SL）；Classic Hornet',
    ),
    'F-14': AircraftSpec(
        id='F-14', name='F-14 Tomcat', type_label='conventional',
        mtow_kg=33724, empty_kg=18955, internal_fuel_kg=7348, max_payload_kg=6700,
        bvr_missile='AIM-120C AMRAAM', missile_mass_kg=152.0,
        sweep_le_deg=20, wingspan_m=19.54, wing_area_m2=52.49, wing_height_m=2.10,
        cd0=0.046, t_max_sl_n=250900,
        notes='F-14B/D；2×F110-GE-400 加力共约 251 kN；起飞翼后掠 20°',
    ),
}

CARRIERS: list[CarrierSpec] = [
    CarrierSpec(
        id='QE', name='伊丽莎白女王级', nation='英国',
        max_speed_kt=25, ski_jump=True, ski_jump_angle_deg=13.0,
        ski_jump_height_m=6.0, f35b_capable=True,
        total_deck_length_m=280.0,
        deck_length_source='Royal Navy：flight deck 280 m',
        notes='公开数据：>25 kn，13° ski-jump，跳台高约 6 m',
    ),
    CarrierSpec(
        id='IZUMO', name='出云级', nation='日本',
        max_speed_kt=30, ski_jump=False, f35b_capable=True,
        total_deck_length_m=248.0,
        deck_length_source='Defense Media Network：舰长 248 m',
        notes='改装后无 ski-jump，F-35B 短距滑跑起飞',
    ),
    CarrierSpec(
        id='CAVOUR', name='加富尔级', nation='意大利',
        max_speed_kt=29, ski_jump=True, ski_jump_angle_deg=12.0,
        f35b_capable=True,
        total_deck_length_m=232.6,
        deck_length_source='Fincantieri：flight deck 232.6 m',
        notes='29 kn，12° 圆弧 ski-jump',
    ),
    CarrierSpec(
        id='TRIESTE', name='的里雅斯特级', nation='意大利',
        max_speed_kt=25, ski_jump=True, ski_jump_angle_deg=12.0,
        f35b_capable=True,
        total_deck_length_m=230.0,
        deck_length_source='Fincantieri / Wikipedia：flight deck 230 m',
        notes='LHD Trieste，25 kn，12° ski-jump',
    ),
    CarrierSpec(
        id='WASP', name='黄蜂级', nation='美国',
        max_speed_kt=22, ski_jump=False, f35b_capable=True,
        total_deck_length_m=253.2,
        deck_length_source='US Navy LHD-1：844 ft = 253.2 m',
        notes='LHD/LHA，22 kn，平直甲板 STOVL',
    ),
    CarrierSpec(
        id='KUZNETSOV', name='库兹涅佐夫级', nation='中/俄',
        max_speed_kt=30, ski_jump=True, ski_jump_angle_deg=14.0,
        f35b_capable=False,
        total_deck_length_m=304.5,
        deck_length_source='Navypedia / 维基：flight deck 304.5 m',
        notes='辽宁舰/库兹涅佐夫号；30 kn，14°',
    ),
    CarrierSpec(
        id='SHANDONG', name='山东号', nation='中国',
        max_speed_kt=30, ski_jump=True, ski_jump_angle_deg=12.0,
        ski_jump_height_m=5.099,  # 唇口高度使滑跃弧长 ≈ 库兹涅佐夫级（R=200 m, 14°）
        f35b_capable=False,
        total_deck_length_m=300.0,
        deck_length_source='GlobalSecurity Type 001A：flight deck 300 m',
        notes='002 型；30 kn，12°；滑跃弧长与库兹涅佐夫级一致（水平投影约 49 m）',
    ),
    CarrierSpec(
        id='VIKRAMADITYA', name='超日王号', nation='印度',
        max_speed_kt=29, ski_jump=True, ski_jump_angle_deg=14.3,
        f35b_capable=False,
        total_deck_length_m=273.1,
        deck_length_source='Navypedia：flight deck 273.1 m',
        notes='改装自戈尔什科夫号；29 kn，14.3°',
    ),
    CarrierSpec(
        id='VIKRANT', name='维克兰特号', nation='印度',
        max_speed_kt=28, ski_jump=True, ski_jump_angle_deg=14.0,
        f35b_capable=False,
        total_deck_length_m=262.0,
        deck_length_source='PIB / Wikipedia：舰长 262 m',
        notes='国产 STOBAR；28 kn，14°',
    ),
]

AIRCRAFT_CSV_PATH = str(AIRCRAFT_CSV)
CARRIERS_CSV_PATH = str(CARRIERS_CSV)


def export_databases_to_csv(
    aircraft_path: str = AIRCRAFT_CSV_PATH,
    carriers_path: str = CARRIERS_CSV_PATH,
) -> None:
    from utils.database_csv import export_aircraft_csv, export_carriers_csv

    export_aircraft_csv(aircraft_path, AIRCRAFT)
    export_carriers_csv(carriers_path, CARRIERS)
    print(f'已写入 {aircraft_path}（{len(AIRCRAFT)} 架）')
    print(f'已写入 {carriers_path}（{len(CARRIERS)} 艘）')


def load_databases_from_csv(
    aircraft_path: str = AIRCRAFT_CSV_PATH,
    carriers_path: str = CARRIERS_CSV_PATH,
) -> bool:
    """若两个 CSV 均存在则从文件加载，覆盖模块内默认 AIRCRAFT / CARRIERS。"""
    global AIRCRAFT, CARRIERS
    from pathlib import Path

    from utils.database_csv import load_aircraft_csv, load_carriers_csv

    ap, cp = Path(aircraft_path), Path(carriers_path)
    if not ap.is_file() or not cp.is_file():
        return False
    AIRCRAFT = load_aircraft_csv(ap)
    CARRIERS = load_carriers_csv(cp)
    return True


def _carrier_deck_desc(c: CarrierSpec) -> str:
    if c.ski_jump:
        g = c.ski_jump_geom()
        return (f"滑跃弧 {g.arc_length_m:.0f} m（水平 {g.horizontal_m:.0f} m）/ {c.ski_jump_angle_deg:.1f}°，"
                f"飞行甲板总长 {c.total_deck_length_m:.0f} m，"
                f"最大航速 {c.max_speed_kt:.0f} kt（甲板风）")
    return (f"平直甲板，飞行甲板总长 {c.total_deck_length_m:.0f} m，"
            f"最大航速 {c.max_speed_kt:.0f} kt（甲板风）")


def _annotate_deck_feasibility(result: dict[str, Any], carrier: CarrierSpec) -> dict[str, Any]:
    """在仿真可行解上标注：所需总距是否不超过飞行甲板总长。"""
    out = dict(result)
    out['total_deck_length_m'] = carrier.total_deck_length_m
    if not out.get('success') or out.get('distance_m') is None:
        out['deck_launch_ok'] = None
        out['deck_margin_m'] = None
        return out
    margin = carrier.total_deck_length_m - float(out['distance_m'])
    out['deck_margin_m'] = margin
    out['deck_launch_ok'] = margin >= 0
    return out


def _deck_launch_label(r: dict[str, Any]) -> str:
    if not r.get('success'):
        return '仿真失败'
    if r.get('deck_launch_ok') is True:
        return f"甲板可用（余量 {r['deck_margin_m']:.1f} m）"
    if r.get('deck_launch_ok') is False:
        return f"甲板不足（超出 {-r['deck_margin_m']:.1f} m）"
    return '—'


def _configure_stovl(ac: AircraftSpec, carrier: CarrierSpec, mass_kg: float):
    geom = dict(mass_kg=mass_kg, s_ref_m2=ac.wing_area_m2, wingspan_m=ac.wingspan_m,
                wing_height_m=ac.wing_height_m, sweep_le_deg=ac.sweep_le_deg, cd0=ac.cd0)
    wind_kt = carrier.deck_wind_kt()
    if carrier.ski_jump:
        ski_stovl.apply_thrust_temperature(SURVEY_TEMP_C)
        ski_stovl.apply_stovl_thrust_sl(
            ac.t_main_stovl_sl_n, ac.t_liftfan_sl_n or 0.0, ac.t_rollposts_sl_n or 0.0)
        ski_stovl.apply_exhaust_plume_params(ac.exhaust_plume_params())
        ski_stovl.apply_wind_knots(wind_kt)
        ski_stovl.apply_aircraft_geometry(**geom)
        ski_stovl.apply_ski_jump_deck(carrier.ski_jump_angle_deg, carrier.ski_jump_height_m)
        return ski_stovl
    flat_stovl.apply_thrust_temperature(SURVEY_TEMP_C)
    flat_stovl.apply_stovl_thrust_sl(
        ac.t_main_stovl_sl_n, ac.t_liftfan_sl_n or 0.0, ac.t_rollposts_sl_n or 0.0)
    flat_stovl.apply_exhaust_plume_params(ac.exhaust_plume_params())
    flat_stovl.apply_wind_knots(wind_kt)
    flat_stovl.apply_aircraft_geometry(**geom)
    return flat_stovl


_configure_f35b = _configure_stovl  # 兼容旧名


def _configure_conventional(ac: AircraftSpec, carrier: CarrierSpec, mass_kg: float):
    ski_conv.apply_thrust_temperature(SURVEY_TEMP_C)
    ski_conv.apply_wind_knots(carrier.deck_wind_kt())
    ski_conv.apply_ski_jump_deck(carrier.ski_jump_angle_deg, carrier.ski_jump_height_m)
    ski_conv.apply_aircraft_geometry(
        mass_kg=mass_kg, s_ref_m2=ac.wing_area_m2, wingspan_m=ac.wingspan_m,
        wing_height_m=ac.wing_height_m, sweep_le_deg=ac.sweep_le_deg,
        cd0=ac.cd0, t_max_sl_n=ac.t_max_sl_n,
        layout=ac.layout, canard_htail_area_m2=ac.canard_htail_area_m2)
    if ac.uses_propeller_power:
        ski_conv.apply_propulsion_sl(
            ac.shaft_power_sl_w,
            ac.prop_diameter_m,
            nacelle_blockage_frac=ac.nacelle_blockage_frac,
        )
    return ski_conv


def _check_flat_stovl_boundaries(mod, result: dict) -> set[str]:
    hits = set()
    if result['nozzle_deg'] <= mod.NOZZLE_FINAL_DEG_START + 1:
        hits.add('nozzle_low')
    if result['nozzle_deg'] >= mod.NOZZLE_FINAL_DEG_END - 1:
        hits.add('nozzle_high')
    if result['v_trans_mps'] <= mod.V_TRANS_START_MPS + 1:
        hits.add('vtrans_low')
    if result['v_trans_mps'] >= mod.V_TRANS_END_MPS - 1:
        hits.add('vtrans_high')
    return hits


def _assert_pitch_within_limit(pitch_deg: float):
    if pitch_deg > PITCH_MAX_DEG:
        raise ValueError(f"俯仰角 {pitch_deg}° 超过硬上限 {PITCH_MAX_DEG}°")


def _check_ski_stovl_boundaries(mod, result: dict) -> set[str]:
    hits = set()
    flats = list(mod.FLAT_LENGTH_M_LIST_A)
    nozzles = list(mod.NOZZLE_TAKEOFF_DEG_LIST_A)
    vtrans = list(mod.V_TRANS_MPS_LIST_A)
    pitches = list(mod.PITCH_DEG_LIST)
    if result['flat_m'] <= min(flats) + 5:
        hits.add('flat_low')
    if result['flat_m'] >= max(flats) - 5:
        hits.add('flat_high')
    if result['nozzle_deg'] <= min(nozzles) + 2:
        hits.add('nozzle_low')
    if result['nozzle_deg'] >= max(nozzles) - 2:
        hits.add('nozzle_high')
    if result['v_trans_mps'] <= min(vtrans) + 2:
        hits.add('vtrans_low')
    if result['v_trans_mps'] >= max(vtrans) - 2:
        hits.add('vtrans_high')
    if result['pitch_deg'] <= min(pitches):
        hits.add('pitch_low')
    if result['pitch_deg'] >= max(pitches):
        hits.add('pitch_high')
    return hits


def _capture_search_defaults():
    """从当前仿真模块读取搜索范围，供多次运行前恢复。"""
    _SEARCH_DEFAULTS['flat_stovl'] = dict(
        NOZZLE_FINAL_DEG_START=flat_stovl.NOZZLE_FINAL_DEG_START,
        NOZZLE_FINAL_DEG_END=flat_stovl.NOZZLE_FINAL_DEG_END,
        V_TRANS_START_MPS=flat_stovl.V_TRANS_START_MPS,
        V_TRANS_END_MPS=flat_stovl.V_TRANS_END_MPS,
    )
    _SEARCH_DEFAULTS['ski_stovl'] = dict(
        FLAT_LENGTH_M_LIST_A=list(ski_stovl.FLAT_LENGTH_M_LIST_A),
        NOZZLE_TAKEOFF_DEG_LIST_A=list(ski_stovl.NOZZLE_TAKEOFF_DEG_LIST_A),
        V_TRANS_MPS_LIST_A=list(ski_stovl.V_TRANS_MPS_LIST_A),
    )
    _SEARCH_DEFAULTS['ski_conv'] = dict(
        PITCH_SEARCH_MIN=ski_conv.PITCH_SEARCH_MIN,
        PITCH_SEARCH_MAX=ski_conv.PITCH_SEARCH_MAX,
        FLAT_SEARCH_MAX_M=ski_conv.FLAT_SEARCH_MAX_M,
    )


def _check_ski_conv_boundaries(mod, result: dict) -> set[str]:
    hits = set()
    if result['flat_m'] <= 5:
        hits.add('flat_low')
    if result['flat_m'] >= mod.FLAT_SEARCH_MAX_M - 5:
        hits.add('flat_high')
    if result['pitch_deg'] <= mod.PITCH_SEARCH_MIN + 1:
        hits.add('pitch_low')
    if result['pitch_deg'] >= mod.PITCH_SEARCH_MAX - 1:
        hits.add('pitch_high')
    return hits


def _record_hits(category: str, hits: set[str]):
    BOUNDARY_HITS[category].update(hits)


def _expand_flat_stovl_bounds(hits: set[str]):
    if 'nozzle_low' in hits:
        flat_stovl.NOZZLE_FINAL_DEG_START = max(5, flat_stovl.NOZZLE_FINAL_DEG_START - 10)
    if 'nozzle_high' in hits:
        flat_stovl.NOZZLE_FINAL_DEG_END = min(95, flat_stovl.NOZZLE_FINAL_DEG_END + 5)
    if 'vtrans_low' in hits:
        flat_stovl.V_TRANS_START_MPS = max(0, flat_stovl.V_TRANS_START_MPS - 10)
    if 'vtrans_high' in hits:
        flat_stovl.V_TRANS_END_MPS = min(90, flat_stovl.V_TRANS_END_MPS + 10)


def _expand_ski_stovl_bounds(hits: set[str]):
    if 'flat_low' in hits:
        lo = min(ski_stovl.FLAT_LENGTH_M_LIST_A)
        extra = list(range(max(10, lo - 40), lo, 5))
        merged = sorted(set(extra + list(ski_stovl.FLAT_LENGTH_M_LIST_A)))
        ski_stovl.FLAT_LENGTH_M_LIST_A = merged
    if 'flat_high' in hits:
        hi = max(ski_stovl.FLAT_LENGTH_M_LIST_A)
        extra = list(range(hi + 10, hi + 80, 10))
        merged = sorted(set(list(ski_stovl.FLAT_LENGTH_M_LIST_A) + extra))
        ski_stovl.FLAT_LENGTH_M_LIST_A = merged
    if 'nozzle_low' in hits:
        lo = min(ski_stovl.NOZZLE_TAKEOFF_DEG_LIST_A)
        extra = list(range(max(0, lo - 20), lo, 5))
        ski_stovl.NOZZLE_TAKEOFF_DEG_LIST_A = sorted(set(extra + list(ski_stovl.NOZZLE_TAKEOFF_DEG_LIST_A)))
    if 'nozzle_high' in hits:
        hi = max(ski_stovl.NOZZLE_TAKEOFF_DEG_LIST_A)
        extra = list(range(hi + 5, min(95, hi + 30), 5))
        ski_stovl.NOZZLE_TAKEOFF_DEG_LIST_A = sorted(set(list(ski_stovl.NOZZLE_TAKEOFF_DEG_LIST_A) + extra))
    if 'vtrans_low' in hits:
        lo = min(ski_stovl.V_TRANS_MPS_LIST_A)
        extra = list(range(max(0, lo - 15), lo, 5))
        ski_stovl.V_TRANS_MPS_LIST_A = sorted(set(extra + list(ski_stovl.V_TRANS_MPS_LIST_A)))
    if 'vtrans_high' in hits:
        hi = max(ski_stovl.V_TRANS_MPS_LIST_A)
        extra = list(range(hi + 5, hi + 30, 5))
        ski_stovl.V_TRANS_MPS_LIST_A = sorted(set(list(ski_stovl.V_TRANS_MPS_LIST_A) + extra))


def _expand_ski_conv_bounds(hits: set[str]):
    if 'flat_low' in hits:
        pass  # 粗搜索已从 0 开始
    if 'flat_high' in hits:
        ski_conv.FLAT_SEARCH_MAX_M = min(400, ski_conv.FLAT_SEARCH_MAX_M + 60)
    if 'pitch_low' in hits:
        ski_conv.PITCH_SEARCH_MIN = max(5, ski_conv.PITCH_SEARCH_MIN - 3)
    if 'pitch_high' in hits:
        ski_conv.PITCH_SEARCH_MAX = min(PITCH_MAX_DEG, ski_conv.PITCH_SEARCH_MAX + 3)


def _carrier_deck_short(c: CarrierSpec) -> str:
    """汇总表用：仅航速与滑跃参数。"""
    if c.ski_jump:
        return (f"{c.max_speed_kt:.0f} kt，滑跃 {c.ski_jump_horizontal_m():.0f} m / "
                f"{c.ski_jump_angle_deg:.1f}°")
    return f"{c.max_speed_kt:.0f} kt，平直甲板"


def _build_f35b_result(ac, carrier, load_label, mass_kg, result, ski_jump: bool) -> dict[str, Any]:
    base = dict(
        success=True, aircraft=ac.id, aircraft_name=ac.name,
        carrier=carrier.id, carrier_name=carrier.name, load=load_label,
        mass_kg=mass_kg, temp_c=SURVEY_TEMP_C, wind_kt=carrier.deck_wind_kt(),
        carrier_desc=_carrier_deck_desc(carrier),
        carrier_short=_carrier_deck_short(carrier),
        nozzle_deg=result['nozzle_deg'],
        v_trans_mps=result['v_trans_mps'],
        min_plume_trailing_edge_m=result['min_plume_trailing_edge_m'],
    )
    if ski_jump:
        base.update(
            distance_m=float(result['total_m']),
            flat_m=float(result['flat_m']),
            pitch_deg=int(result['pitch_deg']),
            v_deck_mps=float(result['v_deck_mps']),
            t_deck_s=float(result['t_deck_s']),
        )
    else:
        base.update(
            distance_m=float(result['x_m']),
            flat_m=float(result['x_m']),
            pitch_deg=None,
            v_deck_mps=float(result['v_gs_mps']),
            t_deck_s=float(result['t_s']),
        )
    return base


def _build_conv_result(ac, carrier, load_label, mass_kg, result) -> dict[str, Any]:
    return dict(
        success=True, aircraft=ac.id, aircraft_name=ac.name,
        carrier=carrier.id, carrier_name=carrier.name, load=load_label,
        mass_kg=mass_kg, temp_c=SURVEY_TEMP_C, wind_kt=carrier.deck_wind_kt(),
        carrier_desc=_carrier_deck_desc(carrier),
        carrier_short=_carrier_deck_short(carrier),
        distance_m=float(result['total_m']),
        flat_m=float(result['flat_m']),
        pitch_deg=int(result['pitch_deg']),
        v_deck_mps=float(result['v_deck_mps']),
        t_deck_s=float(result['t_deck_s']),
        nozzle_deg=None, v_trans_mps=None, min_plume_trailing_edge_m=None,
    )


def run_stovl_case(ac: AircraftSpec, carrier: CarrierSpec, load_label: str, mass_kg: float) -> dict[str, Any]:
    mod = _configure_stovl(ac, carrier, mass_kg)
    for attempt in range(3):
        if carrier.ski_jump:
            result = mod.run_strategy_a_search()
            if result is None:
                return dict(success=False, aircraft=ac.id, carrier=carrier.id, load=load_label)
            _assert_pitch_within_limit(result['pitch_deg'])
            hits = _check_ski_stovl_boundaries(mod, result)
            _record_hits('ski_stovl', hits)
            if hits and attempt < 2:
                _expand_ski_stovl_bounds(hits)
                _configure_stovl(ac, carrier, mass_kg)
                continue
            return _annotate_deck_feasibility(
                _build_f35b_result(ac, carrier, load_label, mass_kg, result, ski_jump=True), carrier)
        else:
            result = mod.run_strategy_a_search()
            if result is None:
                return dict(success=False, aircraft=ac.id, carrier=carrier.id, load=load_label)
            hits = _check_flat_stovl_boundaries(mod, result)
            _record_hits('flat_stovl', hits)
            if hits and attempt < 2:
                _expand_flat_stovl_bounds(hits)
                _configure_stovl(ac, carrier, mass_kg)
                continue
            return _annotate_deck_feasibility(
                _build_f35b_result(ac, carrier, load_label, mass_kg, result, ski_jump=False), carrier)
    return dict(success=False, aircraft=ac.id, carrier=carrier.id, load=load_label)


run_f35b_case = run_stovl_case  # 兼容旧名
STOVL_AIRCRAFT_IDS = ('F-35B', 'AV-8B')


def run_conventional_case(ac: AircraftSpec, carrier: CarrierSpec, load_label: str, mass_kg: float) -> dict[str, Any]:
    if not carrier.ski_jump:
        return dict(success=False, aircraft=ac.id, carrier=carrier.id, load=load_label,
                    note='该舰无滑跃甲板')
    mod = _configure_conventional(ac, carrier, mass_kg)
    for attempt in range(2):
        result = mod.run_min_takeoff_search()
        if result is None:
            return dict(success=False, aircraft=ac.id, carrier=carrier.id, load=load_label)
        _assert_pitch_within_limit(result['pitch_deg'])
        hits = _check_ski_conv_boundaries(mod, result)
        _record_hits('ski_conv', hits)
        if hits & {'pitch_low', 'pitch_high'} and attempt == 0:
            _expand_ski_conv_bounds(hits)
            _configure_conventional(ac, carrier, mass_kg)
            continue
        return _annotate_deck_feasibility(
            _build_conv_result(ac, carrier, load_label, mass_kg, result), carrier)
    return dict(success=False, aircraft=ac.id, carrier=carrier.id, load=load_label)


def print_aircraft_database():
    print('=' * 88)
    print('舰载机参数库')
    print('=' * 88)
    for ac in AIRCRAFT.values():
        print(f"\n【{ac.name}】 ({ac.type_label})")
        print(f"  MTOW: {ac.mtow_kg:.0f} kg | 空重: {ac.empty_kg:.0f} kg | 内油: {ac.internal_fuel_kg:.0f} kg")
        print(f"  中距弹: {ac.bvr_missile} ×{A2A_MISSILE_COUNT}（{ac.missile_mass_kg:.0f} kg/枚）")
        print(f"  空战挂载: {ac.a2a_mass_kg:.0f} kg（含飞行员相关 {PILOT_LOAD_KG:.0f} kg）")
        print(f"  后掠角 {ac.sweep_le_deg}° | 翼展 {ac.wingspan_m} m | 面积 {ac.wing_area_m2} m² | 翼高 {ac.wing_height_m} m")
        if ac.is_vtol:
            print(f"  垂起推力(15°C SL): 主喷管 {ac.t_main_stovl_sl_n/1000:.1f} kN，"
                  f"升力风扇 {(ac.t_liftfan_sl_n or 0)/1000:.1f} kN，"
                  f"滚转 {(ac.t_rollposts_sl_n or 0)/1000:.1f} kN")
            plume = ac.exhaust_plume_params()
            print(f"  尾流 ṁ={plume.mdot_kg_s:.1f} kg/s，u₀={plume.u0_mps:.0f} m/s，d₀={plume.d0_m:.2f} m")
        else:
            print(f"  最大加力(15°C SL): {ac.t_max_sl_n/1000:.1f} kN | Cd0={ac.cd0}")
        if ac.notes:
            print(f"  备注: {ac.notes}")


def print_carrier_database():
    print('\n' + '=' * 88)
    print('航母参数库')
    print('=' * 88)
    for c in CARRIERS:
        cap = 'F-35B 适用' if c.f35b_capable else '常规滑跃机适用'
        print(f"\n【{c.name}】 ({c.nation}) — {cap}")
        print(f"  {_carrier_deck_desc(c)}")
        if c.deck_length_source:
            print(f"  甲板长度来源: {c.deck_length_source}")
        if c.notes:
            print(f"  备注: {c.notes}")


def _print_result_row(r: dict[str, Any]):
    if not r.get('success'):
        print(f"  ✗ {r['aircraft']} @ {r['carrier']} [{r['load']}] — 未能找到可行解")
        return
    deck = _deck_launch_label(r)
    print(f"  ✓ {r['aircraft']} @ {r['carrier']} [{r['load']}]  {r['mass_kg']:.0f} kg  "
          f"总距 {r['distance_m']:.1f} m | {deck}")


def _fmt_opt(v, fmt: str = '.1f', na: str = '—') -> str:
    if v is None:
        return na
    if fmt == 'd':
        return f"{int(v)}"
    return f"{v:{fmt}}"


def _format_f35b_detail_block(r: dict[str, Any]) -> list[str]:
    pitch = '—' if r['pitch_deg'] is None else f"{r['pitch_deg']}°"
    lines = [
        f"  重量:           {r['mass_kg']:.0f} kg",
        f"  最小总距离:     {r['distance_m']:.1f} m",
        f"  飞行甲板总长:   {r['total_deck_length_m']:.0f} m",
        f"  甲板起飞:       {_deck_launch_label(r)}",
        f"  平直段:         {r['flat_m']:.0f} m",
        f"  喷管最终角:     {r['nozzle_deg']}°",
        f"  开始偏转地速:   {r['v_trans_mps']} m/s",
        f"  尾流波及最后缘 (VTOL): {_fmt_opt(r['min_plume_trailing_edge_m'])} m",
        f"  俯仰角:         {pitch}",
        f"  离舰速度:       {r['v_deck_mps']:.1f} m/s",
        f"  离舰用时:       {r['t_deck_s']:.2f} s",
    ]
    return lines


def _format_conv_detail_block(r: dict[str, Any]) -> list[str]:
    return [
        f"  重量:           {r['mass_kg']:.0f} kg",
        f"  最小总距离:     {r['distance_m']:.1f} m",
        f"  飞行甲板总长:   {r['total_deck_length_m']:.0f} m",
        f"  甲板起飞:       {_deck_launch_label(r)}",
        f"  平直段:         {r['flat_m']:.0f} m",
        f"  俯仰角:         {r['pitch_deg']}°",
        f"  离舰速度:       {r['v_deck_mps']:.1f} m/s",
        f"  离舰用时:       {r['t_deck_s']:.2f} s",
    ]


def _deck_cell(r: dict[str, Any] | None) -> str:
    if not r or not r.get('success'):
        return '失败'
    mark = '✓' if r.get('deck_launch_ok') else '✗'
    return f"{r['distance_m']:.1f}{mark}"


def format_survey_report(f35b_results: list[dict], conv_results: list[dict]) -> str:
    """生成规整的文本报告。"""
    w = 96
    sep = '=' * w
    thin = '-' * w
    lines: list[str] = []

    lines += [
        sep,
        '舰载机最小起飞距离遍历报告',
        sep,
        f'条件: {SURVEY_TEMP_C:.0f}°C | 甲板风 = 航母最大航速 | 俯仰角硬上限 {PITCH_MAX_DEG}°',
        f'F-35B: 策略 A（short_take_off / short_ski_jump_take_off）；含 VTOL 主喷管尾流波及',
        f'常规型: ski_jump_take_off（仅 STOBAR 航母，不含 F-35B 适用舰；不计算尾流波及）',
        f'甲板判定: 所需总距 ≤ 飞行甲板总长 → 甲板起飞成功（✓），否则失败（✗）',
        '',
        '航母飞行甲板总长（公开资料，m）:',
    ]
    for c in CARRIERS:
        src = f" — {c.deck_length_source}" if c.deck_length_source else ''
        lines.append(f"  {c.name}: {c.total_deck_length_m:.1f}{src}")
    lines += ['', ]

    # ── F-35B 明细 ──
    lines += [sep, '一、F-35B 各航母组合优化结果', sep, '']
    f35b_carriers = [c for c in CARRIERS if c.f35b_capable]
    for carrier in f35b_carriers:
        lines.append(f"【{carrier.name}】 {_carrier_deck_short(carrier)}")
        for load in ('空战挂载', 'MTOW'):
            r = next((x for x in f35b_results
                      if x.get('carrier') == carrier.id and x.get('load') == load), None)
            if not r or not r.get('success'):
                lines.append(f"  [{load}]  ✗ 未能找到可行解")
                lines.append('')
                continue
            lines.append(f"  [{load}]")
            lines += _format_f35b_detail_block(r)
            lines.append('')
        lines.append(thin)

    # ── 常规型明细 ──
    lines += ['', sep, '二、常规舰载机 × STOBAR 航母优化结果', sep, '']
    conv_carriers = [c for c in CARRIERS if c.ski_jump and not c.f35b_capable]
    conv_ac_ids = ('J-15', 'J-15T', 'J-35', 'MiG-29K', 'Rafale-M', 'FA-18E', 'FA-18C', 'F-14')
    for aid in conv_ac_ids:
        ac = AIRCRAFT[aid]
        lines.append(f"【{ac.name}】")
        for carrier in conv_carriers:
            lines.append(f"  {carrier.name}（{_carrier_deck_short(carrier)}）")
            for load in ('空战挂载', 'MTOW'):
                r = next((x for x in conv_results
                          if x.get('aircraft') == aid and x.get('carrier') == carrier.id
                          and x.get('load') == load), None)
                if not r or not r.get('success'):
                    lines.append(f"    [{load}]  ✗ 未能找到可行解")
                    continue
                lines.append(f"    [{load}]")
                for ln in _format_conv_detail_block(r):
                    lines.append('  ' + ln)
            lines.append('')
        lines.append(thin)

    # ── F-35B 总表 ──
    lines += ['', sep, '三、F-35B 跨航母对比总表（✓=甲板可用 ✗=甲板不足）', sep, '']
    hdr = (f"{'航母':<16} {'甲板总长m':>8} {'空战kg':>8} {'空战总距m':>10} "
           f"{'MTOW kg':>8} {'MTOW总距m':>10}")
    lines += [hdr, thin]
    for carrier in f35b_carriers:
        r_a2a = next((x for x in f35b_results
                      if x.get('carrier') == carrier.id and x.get('load') == '空战挂载'), {})
        r_mt = next((x for x in f35b_results
                     if x.get('carrier') == carrier.id and x.get('load') == 'MTOW'), {})
        a2a_dist = _deck_cell(r_a2a) if r_a2a else '失败'
        mt_dist = _deck_cell(r_mt) if r_mt else '失败'
        a2a_kg = f"{r_a2a['mass_kg']:.0f}" if r_a2a.get('success') else '—'
        mt_kg = f"{r_mt['mass_kg']:.0f}" if r_mt.get('success') else '—'
        lines.append(
            f"{carrier.name:<16} {carrier.total_deck_length_m:>8.0f} "
            f"{a2a_kg:>8} {a2a_dist:>10} {mt_kg:>8} {mt_dist:>10}")

    # ── 常规型总表 ──
    lines += ['', sep, '四、常规舰载机 × STOBAR 航母对比总表（总距离 m，✓/✗=甲板可用性）', sep, '']
    carrier_labels = [f"{c.name}\n({_carrier_deck_short(c)})" for c in conv_carriers]
    col_w = 14
    lines.append(f"{'机型':<12} {'挂载':<8}" +
                 ''.join(f"{lbl.split(chr(10))[0]:>{col_w}}" for lbl in carrier_labels))
    lines.append(f"{'':12} {'':8}" +
                 ''.join(f"{c.ski_jump_arc_m():.0f}m/{c.ski_jump_angle_deg:.0f}°/{c.max_speed_kt:.0f}kt".center(col_w)
                         for c in conv_carriers))
    lines.append(f"{'':12} {'':8}" +
                 ''.join(f"{c.total_deck_length_m:.0f}m".center(col_w) for c in conv_carriers))
    lines.append(thin)
    for aid in conv_ac_ids:
        for load in ('空战挂载', 'MTOW'):
            row = f"{aid:<12} {load:<8}"
            for carrier in conv_carriers:
                r = next((x for x in conv_results
                          if x.get('aircraft') == aid and x.get('carrier') == carrier.id
                          and x.get('load') == load), None)
                row += f"{_deck_cell(r):>{col_w}}"
            lines.append(row)

    # ── 甲板可用性汇总 ──
    lines += ['', sep, '五、甲板起飞可用性汇总（仿真可行且总距≤甲板总长）', sep, '']
    all_results = f35b_results + conv_results
    ok_count = sum(1 for r in all_results if r.get('deck_launch_ok') is True)
    fail_count = sum(1 for r in all_results if r.get('deck_launch_ok') is False)
    sim_fail = sum(1 for r in all_results if not r.get('success'))
    lines.append(f"  仿真可行且甲板可用: {ok_count} 组 | 仿真可行但甲板不足: {fail_count} 组 | 仿真失败: {sim_fail} 组")
    lines.append('')
    lines.append(f"  {'机型':<10} {'航母':<14} {'挂载':<8} {'总距m':>8} {'甲板m':>8} {'判定':>6}")
    lines.append('  ' + thin)
    for r in all_results:
        if not r.get('success'):
            lines.append(f"  {r.get('aircraft', '?'):<10} {r.get('carrier', '?'):<14} "
                         f"{r.get('load', '?'):<8} {'—':>8} {'—':>8} {'仿真失败':>6}")
            continue
        mark = '成功' if r.get('deck_launch_ok') else '失败'
        lines.append(
            f"  {r['aircraft']:<10} {r['carrier']:<14} {r['load']:<8} "
            f"{r['distance_m']:>8.1f} {r['total_deck_length_m']:>8.0f} {mark:>6}")

    lines += ['', sep]
    return '\n'.join(lines)


def write_survey_report(path: str, f35b_results: list[dict], conv_results: list[dict]):
    text = format_survey_report(f35b_results, conv_results)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)
    return text


def _reset_search_ranges():
    d = _SEARCH_DEFAULTS['flat_stovl']
    flat_stovl.NOZZLE_FINAL_DEG_START = d['NOZZLE_FINAL_DEG_START']
    flat_stovl.NOZZLE_FINAL_DEG_END = d['NOZZLE_FINAL_DEG_END']
    flat_stovl.V_TRANS_START_MPS = d['V_TRANS_START_MPS']
    flat_stovl.V_TRANS_END_MPS = d['V_TRANS_END_MPS']
    d = _SEARCH_DEFAULTS['ski_stovl']
    ski_stovl.FLAT_LENGTH_M_LIST_A = list(d['FLAT_LENGTH_M_LIST_A'])
    ski_stovl.NOZZLE_TAKEOFF_DEG_LIST_A = list(d['NOZZLE_TAKEOFF_DEG_LIST_A'])
    ski_stovl.V_TRANS_MPS_LIST_A = list(d['V_TRANS_MPS_LIST_A'])
    d = _SEARCH_DEFAULTS['ski_conv']
    ski_conv.PITCH_SEARCH_MIN = d['PITCH_SEARCH_MIN']
    ski_conv.PITCH_SEARCH_MAX = d['PITCH_SEARCH_MAX']
    ski_conv.FLAT_SEARCH_MAX_M = d['FLAT_SEARCH_MAX_M']


def run_conv_survey_subset(aircraft_ids: tuple[str, ...]):
    """仅对指定常规机型 × STOBAR 航母运行滑跃起飞搜索（不重复已有组合）。"""
    _capture_search_defaults()
    _reset_search_ranges()
    BOUNDARY_HITS['ski_conv'].clear()

    conv_carriers = [c for c in CARRIERS if c.ski_jump and not c.f35b_capable]
    missing = [aid for aid in aircraft_ids if aid not in AIRCRAFT]
    if missing:
        raise KeyError(f'未知机型: {missing}')

    print('=' * 88)
    print(f'常规舰载机增量遍历（{SURVEY_TEMP_C:.0f}°C，STOBAR 航母：'
          f'{", ".join(c.name for c in conv_carriers)}）')
    print('=' * 88)
    for aid in aircraft_ids:
        ac = AIRCRAFT[aid]
        print(f"\n【{ac.name}】 MTOW {ac.mtow_kg:.0f} kg | 空战 {ac.a2a_mass_kg:.0f} kg | "
              f"加力 {ac.t_max_sl_n/1000:.1f} kN")

    results = []
    for aid in aircraft_ids:
        ac = AIRCRAFT[aid]
        for carrier in conv_carriers:
            for load_label, mass in (('空战挂载', ac.a2a_mass_kg), ('MTOW', ac.mtow_kg)):
                print(f"\n--- {ac.name} | {carrier.name} | {load_label} ---")
                r = run_conventional_case(ac, carrier, load_label, mass)
                results.append(r)
                _print_result_row(r)

    print('\n' + '=' * 88)
    print('增量汇总表')
    print('=' * 88)
    print(f"\n{'机型':<10} {'航母':<14} {'挂载':<8} {'重量kg':>8} {'总距m':>8}  甲板条件")
    print('-' * 88)
    for r in results:
        if not r.get('success'):
            print(f"{r['aircraft']:<10} {r['carrier']:<14} {r['load']:<8} {'—':>8} {'失败':>8}")
            continue
        print(f"{r['aircraft']:<10} {r['carrier']:<14} {r['load']:<8} {r['mass_kg']:>8.0f} "
              f"{r['distance_m']:>8.1f}  {r['carrier_desc']}")
    report_path = str(SURVEY_RESULTS_TXT)
    # 增量模式：读取已有报告中的结果不可行，需全量重跑写入；此处仅追加控制台提示
    print(f'\n提示: 运行完整 survey 以更新 {report_path}')
    return results


def run_survey():
    _capture_search_defaults()
    _reset_search_ranges()
    BOUNDARY_HITS['flat_stovl'].clear()
    BOUNDARY_HITS['ski_stovl'].clear()
    BOUNDARY_HITS['ski_conv'].clear()
    print_aircraft_database()
    print_carrier_database()

    stovl_carriers = [c for c in CARRIERS if c.f35b_capable]
    conv_ac = [AIRCRAFT[k] for k in ('J-15', 'J-15T', 'J-35', 'MiG-29K', 'Rafale-M', 'FA-18E', 'FA-18C', 'F-14')]
    conv_carriers = [c for c in CARRIERS if c.ski_jump and not c.f35b_capable]

    print('\n' + '=' * 88)
    print(f'VTOL/STOVL 策略 A 遍历（{SURVEY_TEMP_C:.0f}°C，甲板风 = 航母最大航速）')
    print('=' * 88)
    f35b_results = []
    for ac_id in STOVL_AIRCRAFT_IDS:
        ac = AIRCRAFT[ac_id]
        for carrier in stovl_carriers:
            for load_label, mass in (('空战挂载', ac.a2a_mass_kg), ('MTOW', ac.mtow_kg)):
                print(f"\n--- {ac.name} | {carrier.name} | {load_label} ---")
                r = run_stovl_case(ac, carrier, load_label, mass)
                f35b_results.append(r)
                _print_result_row(r)

    print('\n' + '=' * 88)
    print(f'常规舰载机滑跃起飞遍历（{SURVEY_TEMP_C:.0f}°C，甲板风 = 航母最大航速，仅 STOBAR 航母）')
    print('=' * 88)
    conv_results = []
    for ac in conv_ac:
        for carrier in conv_carriers:
            for load_label, mass in (('空战挂载', ac.a2a_mass_kg), ('MTOW', ac.mtow_kg)):
                print(f"\n--- {ac.name} | {carrier.name} | {load_label} ---")
                r = run_conventional_case(ac, carrier, load_label, mass)
                conv_results.append(r)
                _print_result_row(r)

    print('\n' + '=' * 88)
    print('汇总表')
    print('=' * 88)
    print(f"\n{'机型':<10} {'航母':<14} {'挂载':<8} {'重量kg':>8} {'总距m':>8} {'甲板m':>8} {'甲板':>4}  条件")
    print('-' * 88)
    for r in f35b_results + conv_results:
        if not r.get('success'):
            print(f"{r['aircraft']:<10} {r['carrier']:<14} {r['load']:<8} {'—':>8} {'失败':>8} {'—':>8} {'—':>4}  —")
            continue
        deck = '✓' if r.get('deck_launch_ok') else '✗'
        print(f"{r['aircraft']:<10} {r['carrier']:<14} {r['load']:<8} {r['mass_kg']:>8.0f} "
              f"{r['distance_m']:>8.1f} {r['total_deck_length_m']:>8.0f} {deck:>4}  {r['carrier_desc']}")

    print('\n边界触及记录（供搜索范围调整参考）:')
    for key, hits in BOUNDARY_HITS.items():
        print(f"  {key}: {sorted(hits) if hits else '无'}")

    report_path = str(SURVEY_RESULTS_TXT)
    write_survey_report(report_path, f35b_results, conv_results)
    print(f'\n报告已写入 {report_path}')
    return f35b_results, conv_results


if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == '--export-db':
        export_databases_to_csv()
    elif len(sys.argv) > 1 and sys.argv[1] == '--conv-only':
        if load_databases_from_csv():
            print(f'已从 {AIRCRAFT_CSV_PATH} / {CARRIERS_CSV_PATH} 加载参数库')
        ids = tuple(sys.argv[2:]) if len(sys.argv) > 2 else ('Rafale-M', 'FA-18E')
        run_conv_survey_subset(ids)
    else:
        if load_databases_from_csv():
            print(f'已从 {AIRCRAFT_CSV_PATH} / {CARRIERS_CSV_PATH} 加载参数库')
        run_survey()
