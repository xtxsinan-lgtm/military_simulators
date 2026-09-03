"""单次起飞仿真 Web API（供 Pyodide / 本地 CLI 调用）。"""
from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout
from typing import Any

import simulators.takeoff.short_ski_jump_take_off as ski_stovl
import simulators.takeoff.short_take_off as flat_stovl
import simulators.takeoff.ski_jump_take_off as ski_conv
import simulators.takeoff.tiltrotor_short_take_off as tilt_stovl
from utils.takeoff.ski_jump_geometry import SKI_JUMP_REF_RADIUS_M, compute_ski_jump_arc
from utils.takeoff.trajectory import build_deck_profile
from utils.specs import (
    AircraftSpec,
    CarrierSpec,
    CONVENTIONAL_TYPE_LABEL,
    TILTROTOR_TYPE_LABEL,
    VTOL_TYPE_LABEL,
    simulation_uses_plume_model,
)
from utils.takeoff.takeoff_input import (
    build_takeoff_highlights,
    extract_exit_kinematics,
    validate_takeoff_mass,
)
from utils.takeoff.takeoff_physics import (
    FLAP_DEFLECTION_DEG,
    FLAP_EFFICIENCY,
    PITCH_MAX_DEG,
    WING_INCIDENCE_DEG,
    calc_cl_alpha,
    calc_cl_from_alpha_deg,
    calc_oswald_e,
    taxi_alpha_deg,
)

MODES = {
    'ski_jump': '滑跃起飞',
    'short_takeoff': '短距起飞',
    'short_ski_jump': '短距滑跃起飞',
    'tiltrotor_short_takeoff': '倾转短距起飞',
}

# STOVL 短距 / 短距滑跃可选喷口策略
STOVL_STRATEGIES = {
    'A': '策略 A — 延迟偏转喷口',
    'B': '策略 B — 全程固定喷口',
    'C': '策略 C — 尾流约束最优偏转',
}

# 倾转旋翼短距仅 A/B（暂不计尾流）
TILTROTOR_STRATEGIES = {
    'A': '策略 A — 延迟倾转短舱',
    'B': '策略 B — 全程固定短舱角',
}


def aircraft_from_dict(d: dict[str, Any]) -> AircraftSpec:
    return AircraftSpec(
        id=d['id'],
        name=d['name'],
        type_label=d['type_label'],
        mtow_kg=float(d['mtow_kg']),
        empty_kg=float(d['empty_kg']),
        internal_fuel_kg=float(d['internal_fuel_kg']),
        max_payload_kg=float(d['max_payload_kg']),
        bvr_missile=d['bvr_missile'],
        missile_mass_kg=float(d['missile_mass_kg']),
        sweep_le_deg=float(d['sweep_le_deg']),
        wingspan_m=float(d['wingspan_m']),
        wing_area_m2=float(d['wing_area_m2']),
        wing_height_m=float(d['wing_height_m']),
        cd0=float(d.get('cd0', 0.039)),
        t_max_sl_n=_opt_float(d.get('t_max_sl_n')),
        t_main_stovl_sl_n=_opt_float(d.get('t_main_stovl_sl_n')),
        t_liftfan_sl_n=_opt_float(d.get('t_liftfan_sl_n')),
        t_rollposts_sl_n=_opt_float(d.get('t_rollposts_sl_n')),
        exhaust_mdot_kg_s=_opt_float(d.get('exhaust_mdot_kg_s')),
        exhaust_d0_m=_opt_float(d.get('exhaust_d0_m')),
        exhaust_height_m=_opt_float(d.get('exhaust_height_m')),
        shaft_power_sl_w=_opt_float(d.get('shaft_power_sl_w')),
        prop_diameter_m=_opt_float(d.get('prop_diameter_m')),
        nacelle_blockage_frac=_opt_float(d.get('nacelle_blockage_frac')),
        n_pilots=int(d['n_pilots']) if d.get('n_pilots') not in (None, '') else 1,
        notes=d.get('notes', ''),
    )


def carrier_from_dict(d: dict[str, Any]) -> CarrierSpec:
    return CarrierSpec(
        id=d['id'],
        name=d['name'],
        nation=d['nation'],
        max_speed_kt=float(d['max_speed_kt']),
        ski_jump=bool(d['ski_jump']),
        total_deck_length_m=float(d['total_deck_length_m']),
        ski_jump_angle_deg=float(d.get('ski_jump_angle_deg') or 0),
        ski_jump_height_m=_opt_float(d.get('ski_jump_height_m')),
        f35b_capable=bool(d.get('f35b_capable')),
        notes=d.get('notes', ''),
        deck_length_source=d.get('deck_length_source', ''),
    )


def _opt_float(v: Any) -> float | None:
    if v is None or v == '':
        return None
    return float(v)


def normalize_stovl_strategy(strategy: str | None) -> str:
    """规范化 STOVL 策略代号；缺省为 A。"""
    if strategy is None or strategy == '':
        return 'A'
    key = str(strategy).strip().upper()
    if key not in STOVL_STRATEGIES:
        raise ValueError(f'未知 STOVL 策略: {strategy}（可选 A/B/C）')
    return key


def normalize_tiltrotor_strategy(strategy: str | None) -> str:
    """规范化倾转旋翼策略代号；缺省为 A，仅允许 A/B。"""
    if strategy is None or strategy == '':
        return 'A'
    key = str(strategy).strip().upper()
    if key not in TILTROTOR_STRATEGIES:
        raise ValueError(f'未知倾转旋翼策略: {strategy}（可选 A/B）')
    return key


def run_stovl_strategy_search(mod, strategy: str):
    """按策略调用对应搜索入口，返回结果 dict 或 None。"""
    strategy = normalize_stovl_strategy(strategy)
    if strategy == 'A':
        return mod.run_strategy_a_search()
    if strategy == 'B':
        return mod.run_strategy_b_search()
    return mod.run_strategy_c_search()


def run_tiltrotor_strategy_search(mod, strategy: str):
    """倾转旋翼策略搜索（仅 A/B）。"""
    strategy = normalize_tiltrotor_strategy(strategy)
    if strategy == 'A':
        return mod.run_strategy_a_search()
    return mod.run_strategy_b_search()


def resolve_ski_jump_geom(
    angle_deg: float,
    height_m: float | None = None,
    arc_length_m: float | None = None,
) -> dict[str, float]:
    """根据角度及可选高度/弧长，补全滑跃几何（缺失项用计算值）。"""
    angle_rad = angle_deg * 3.141592653589793 / 180.0
    if angle_deg <= 0:
        raise ValueError('滑跃角必须为正')

    if arc_length_m is not None and arc_length_m > 0:
        radius_m = arc_length_m / angle_rad
        lip_height_m = radius_m * (1.0 - __import__('math').cos(angle_rad))
        arc = compute_ski_jump_arc(angle_deg, radius_m=radius_m)
    elif height_m is not None and height_m > 0:
        arc = compute_ski_jump_arc(angle_deg, lip_height_m=height_m)
    else:
        arc = compute_ski_jump_arc(angle_deg)

    return {
        'angle_deg': arc.angle_deg,
        'radius_m': arc.radius_m,
        'arc_length_m': arc.arc_length_m,
        'horizontal_m': arc.horizontal_m,
        'lip_height_m': arc.lip_height_m,
        'ref_radius_m': SKI_JUMP_REF_RADIUS_M,
    }


def compute_aircraft_aero(ac: AircraftSpec) -> dict[str, float]:
    ar = ac.wingspan_m ** 2 / ac.wing_area_m2
    eta = calc_oswald_e(ar, ac.sweep_le_deg)
    cl_alpha = calc_cl_alpha(ar, eta, ac.sweep_le_deg)
    alpha_taxi = taxi_alpha_deg(FLAP_DEFLECTION_DEG, FLAP_EFFICIENCY, WING_INCIDENCE_DEG)
    return {
        'aspect_ratio': ar,
        'oswald_e': eta,
        'cl_alpha_per_rad': cl_alpha,
        'taxi_alpha_deg': alpha_taxi,
        'cl_taxi': calc_cl_from_alpha_deg(alpha_taxi, cl_alpha),
        'cl_20deg': calc_cl_from_alpha_deg(20.0, cl_alpha),
        'cd0': ac.cd0,
    }


def filter_carriers_for_mode(mode: str, carriers: list[CarrierSpec]) -> list[CarrierSpec]:
    if mode == 'ski_jump':
        return [c for c in carriers if c.ski_jump]
    if mode in ('short_takeoff', 'tiltrotor_short_takeoff'):
        return [c for c in carriers if c.f35b_capable and not c.ski_jump]
    if mode == 'short_ski_jump':
        return [c for c in carriers if c.f35b_capable and c.ski_jump]
    raise ValueError(f'未知模式: {mode}')


def filter_aircraft_for_mode(mode: str, aircraft: list[AircraftSpec]) -> list[AircraftSpec]:
    if mode == 'ski_jump':
        return [a for a in aircraft if a.type_label == CONVENTIONAL_TYPE_LABEL]
    if mode in ('short_takeoff', 'short_ski_jump'):
        return [a for a in aircraft if a.type_label == VTOL_TYPE_LABEL]
    if mode == 'tiltrotor_short_takeoff':
        return [a for a in aircraft if a.type_label == TILTROTOR_TYPE_LABEL]
    raise ValueError(f'未知模式: {mode}')


def _deck_launch_label(success: bool, distance_m: float | None, deck_length_m: float) -> str:
    if not success or distance_m is None:
        return '仿真失败'
    margin = deck_length_m - distance_m
    if margin >= 0:
        return f'甲板可用（余量 {margin:.1f} m）'
    return f'甲板不足（超出 {-margin:.1f} m）'


def result_distance_m(result: dict) -> float | None:
    """读取起飞距离；0 m（垂起）为有效值，不能用布尔 or 丢掉。"""
    for key in ('distance_m', 'total_m'):
        value = result.get(key)
        if value is not None:
            return float(value)
    return None


def format_output_summary(
    distance_m: float | None,
    deck_margin_m: float | None,
) -> str:
    """仿真输出卡片标题右侧摘要：起飞总距离 + 甲板余量/超出。"""
    if distance_m is None:
        return ''
    dist = f'起飞 {float(distance_m):.1f} m'
    if deck_margin_m is None:
        return dist
    margin = float(deck_margin_m)
    if margin >= 0:
        return f'{dist} · 余量 {margin:.1f} m'
    return f'{dist} · 超出 {-margin:.1f} m'


def _configure_flat_stovl(ac: AircraftSpec, mass_kg: float, temp_c: float, wind_kt: float):
    geom = dict(mass_kg=mass_kg, s_ref_m2=ac.wing_area_m2, wingspan_m=ac.wingspan_m,
                wing_height_m=ac.wing_height_m, sweep_le_deg=ac.sweep_le_deg, cd0=ac.cd0)
    flat_stovl.apply_thrust_temperature(temp_c)
    flat_stovl.apply_stovl_thrust_sl(
        ac.t_main_stovl_sl_n, ac.t_liftfan_sl_n or 0.0, ac.t_rollposts_sl_n or 0.0)
    flat_stovl.apply_exhaust_plume_params(ac.exhaust_plume_params())
    flat_stovl.apply_wind_knots(wind_kt)
    flat_stovl.apply_aircraft_geometry(**geom)
    return flat_stovl


def _configure_ski_stovl(ac: AircraftSpec, mass_kg: float, temp_c: float, wind_kt: float,
                         ski_angle: float, lip_height_m: float | None):
    geom = dict(mass_kg=mass_kg, s_ref_m2=ac.wing_area_m2, wingspan_m=ac.wingspan_m,
                wing_height_m=ac.wing_height_m, sweep_le_deg=ac.sweep_le_deg, cd0=ac.cd0)
    ski_stovl.apply_thrust_temperature(temp_c)
    ski_stovl.apply_stovl_thrust_sl(
        ac.t_main_stovl_sl_n, ac.t_liftfan_sl_n or 0.0, ac.t_rollposts_sl_n or 0.0)
    ski_stovl.apply_exhaust_plume_params(ac.exhaust_plume_params())
    ski_stovl.apply_wind_knots(wind_kt)
    ski_stovl.apply_aircraft_geometry(**geom)
    ski_stovl.apply_ski_jump_deck(ski_angle, lip_height_m)
    return ski_stovl


def _configure_ski_conv(ac: AircraftSpec, mass_kg: float, temp_c: float, wind_kt: float,
                        ski_angle: float, lip_height_m: float | None):
    ski_conv.apply_thrust_temperature(temp_c)
    ski_conv.apply_wind_knots(wind_kt)
    ski_conv.apply_ski_jump_deck(ski_angle, lip_height_m)
    ski_conv.apply_aircraft_geometry(
        mass_kg=mass_kg, s_ref_m2=ac.wing_area_m2, wingspan_m=ac.wingspan_m,
        wing_height_m=ac.wing_height_m, sweep_le_deg=ac.sweep_le_deg,
        cd0=ac.cd0, t_max_sl_n=ac.t_max_sl_n)
    if ac.uses_propeller_power:
        ski_conv.apply_propulsion_sl(
            ac.shaft_power_sl_w,
            ac.prop_diameter_m,
            nacelle_blockage_frac=ac.nacelle_blockage_frac,
        )
    return ski_conv


def _configure_tiltrotor(ac: AircraftSpec, mass_kg: float, temp_c: float, wind_kt: float):
    """配置倾转旋翼短距模块（轴功率 → 推力）。"""
    if not ac.shaft_power_sl_w or not ac.prop_diameter_m:
        raise ValueError(f'{ac.id} 缺少轴功率或桨盘直径，无法进行倾转短距仿真')
    geom = dict(mass_kg=mass_kg, s_ref_m2=ac.wing_area_m2, wingspan_m=ac.wingspan_m,
                wing_height_m=ac.wing_height_m, sweep_le_deg=ac.sweep_le_deg, cd0=ac.cd0)
    tilt_stovl.apply_thrust_temperature(temp_c)
    tilt_stovl.apply_propulsion_sl(
        ac.shaft_power_sl_w,
        ac.prop_diameter_m,
        nacelle_blockage_frac=ac.nacelle_blockage_frac,
    )
    tilt_stovl.apply_wind_knots(wind_kt)
    tilt_stovl.apply_aircraft_geometry(**geom)
    return tilt_stovl


def _format_f35b_output(result: dict, deck_length_m: float, mode_label: str,
                        strategy: str | None = None,
                        strategy_labels: dict[str, str] | None = None,
                        angle_label: str = '喷管最终角') -> list[str]:
    pitch = '—' if result.get('pitch_deg') is None else f"{result['pitch_deg']}°"
    dist = result_distance_m(result)
    flat_m = result.get('flat_m', result.get('x_m'))
    labels = strategy_labels or STOVL_STRATEGIES
    lines = [
        f'模式: {mode_label}',
    ]
    if strategy:
        lines.append(f'  喷口策略:       {labels.get(strategy, strategy)}')
    lines += [
        f"  重量:             {result.get('mass_kg', '—')} kg",
        f"  最小总距离:       {dist:.1f} m" if dist is not None else '  最小总距离:       —',
        f"  飞行甲板总长:     {deck_length_m:.0f} m",
        f"  甲板起飞:         {_deck_launch_label(True, dist, deck_length_m)}",
        f"  平直段:           {flat_m:.0f} m" if flat_m is not None else '  平直段:           —',
        f"  {angle_label}:       {result.get('nozzle_deg')}°",
        f"  开始偏转地速:     {result.get('v_trans_mps')} m/s",
    ]
    plume = result.get('min_plume_trailing_edge_m')
    if plume is not None:
        lines.append(f"  尾流波及最后缘 (VTOL): {plume:.1f} m")
    v_deck = result.get('v_deck_mps') or result.get('v_gs_mps')
    t_deck = result.get('t_deck_s') or result.get('t_s')
    lines += [
        f"  俯仰角:           {pitch}",
        f"  离舰速度:         {v_deck:.1f} m/s" if v_deck else '  离舰速度:         —',
        f"  离舰用时:         {t_deck:.2f} s" if t_deck else '  离舰用时:         —',
    ]
    return lines


def _format_conv_output(result: dict, deck_length_m: float) -> list[str]:
    dist = result['total_m']
    return [
        '模式: 滑跃起飞',
        f"  重量:             {result.get('mass_kg', '—')} kg",
        f"  最小总距离:       {dist:.1f} m",
        f"  飞行甲板总长:     {deck_length_m:.0f} m",
        f"  甲板起飞:         {_deck_launch_label(True, dist, deck_length_m)}",
        f"  平直段:           {result['flat_m']:.0f} m",
        f"  俯仰角:           {result['pitch_deg']}°",
        f"  离舰速度:         {result['v_deck_mps']:.1f} m/s",
        f"  离舰用时:         {result['t_deck_s']:.2f} s",
    ]


def _capture_trajectory(
    mode: str,
    mod,
    result: dict,
    deck_length_m: float,
    strategy: str | None = None,
) -> tuple[list | None, dict | None]:
    """用最优参数重跑仿真，采样起飞轨迹与甲板折线（仅滑跃 / 短距滑跃）。"""
    if mode not in ('ski_jump', 'short_ski_jump'):
        return None, None
    traj: list[dict] = []
    flat_m = float(result['flat_m'])
    pitch_deg = float(result['pitch_deg'])
    if mode == 'ski_jump':
        mod.simulate(flat_m, pitch_deg, trajectory=traj)
    else:
        stovl_strategy = normalize_stovl_strategy(strategy)
        # 策略 C 使用独立 DP 仿真，暂不支持轨迹重放采样
        if stovl_strategy == 'C':
            return None, None
        v_trans = float(result['v_trans_mps']) if stovl_strategy == 'A' else 0.0
        mod.simulate(
            flat_m,
            v_trans,
            float(result['nozzle_deg']),
            stovl_strategy,
            pitch_deg,
            trajectory=traj,
        )
    deck = build_deck_profile(flat_m, mod.SKI_JUMP_ARC)
    deck['total_deck_length_m'] = float(deck_length_m)
    takeoff_m = result_distance_m(result)
    if takeoff_m is not None:
        deck['takeoff_distance_m'] = float(takeoff_m)
    elif deck['points']:
        deck['takeoff_distance_m'] = float(deck['points'][-1][0])
    return traj, deck


def run_simulation(
    mode: str,
    aircraft: AircraftSpec | dict[str, Any],
    carrier: CarrierSpec | dict[str, Any],
    mass_kg: float,
    temp_c: float,
    wind_kt: float,
    ski_jump_angle_deg: float | None = None,
    ski_jump_arc_length_m: float | None = None,
    ski_jump_height_m: float | None = None,
    total_deck_length_m: float | None = None,
    strategy: str | None = None,
) -> dict[str, Any]:
    """运行单次仿真，返回结构化结果与文本输出。"""
    if isinstance(aircraft, dict):
        aircraft = aircraft_from_dict(aircraft)
    if isinstance(carrier, dict):
        carrier = carrier_from_dict(carrier)

    deck_length = total_deck_length_m if total_deck_length_m is not None else carrier.total_deck_length_m
    buf = io.StringIO()
    stovl_strategy = None

    mass_err = validate_takeoff_mass(mass_kg, aircraft.mtow_kg, aircraft.empty_kg)
    if mass_err:
        return _fail(mass_err, '', mode)

    try:
        with redirect_stdout(buf):
            if mode == 'short_takeoff':
                if aircraft.type_label != 'v/stol':
                    raise ValueError('短距起飞仅适用于 STOVL 飞机')
                if carrier.ski_jump:
                    raise ValueError('短距起飞需要平直甲板航母')
                stovl_strategy = normalize_stovl_strategy(strategy)
                mod = _configure_flat_stovl(aircraft, mass_kg, temp_c, wind_kt)
                mod.print_config_summary()
                print()
                result = run_stovl_strategy_search(mod, stovl_strategy)
                if result is None:
                    return _fail('未能找到可行解', buf.getvalue(), mode)
                result['mass_kg'] = mass_kg
                result['distance_m'] = float(result['x_m'])
                result['strategy'] = stovl_strategy
                lines = _format_f35b_output(result, deck_length, MODES[mode], stovl_strategy)

            elif mode == 'short_ski_jump':
                if aircraft.type_label != 'v/stol':
                    raise ValueError('短距滑跃起飞仅适用于 STOVL 飞机')
                if not carrier.ski_jump:
                    raise ValueError('短距滑跃起飞需要滑跃甲板')
                stovl_strategy = normalize_stovl_strategy(strategy)
                angle = ski_jump_angle_deg if ski_jump_angle_deg is not None else carrier.ski_jump_angle_deg
                geom = resolve_ski_jump_geom(angle, ski_jump_height_m, ski_jump_arc_length_m)
                mod = _configure_ski_stovl(
                    aircraft, mass_kg, temp_c, wind_kt, geom['angle_deg'], geom['lip_height_m'])
                mod.print_config_summary()
                print()
                result = run_stovl_strategy_search(mod, stovl_strategy)
                if result is None:
                    return _fail('未能找到可行解', buf.getvalue(), mode)
                if result['pitch_deg'] > PITCH_MAX_DEG:
                    raise ValueError(f"俯仰角 {result['pitch_deg']}° 超过硬上限 {PITCH_MAX_DEG}°")
                result['mass_kg'] = mass_kg
                result['distance_m'] = float(result['total_m'])
                result['strategy'] = stovl_strategy
                lines = _format_f35b_output(result, deck_length, MODES[mode], stovl_strategy)

            elif mode == 'ski_jump':
                if not carrier.ski_jump:
                    raise ValueError('滑跃起飞需要滑跃甲板航母')
                if aircraft.type_label != CONVENTIONAL_TYPE_LABEL:
                    raise ValueError('滑跃起飞模式请选择常规固定翼舰载机')
                angle = ski_jump_angle_deg if ski_jump_angle_deg is not None else carrier.ski_jump_angle_deg
                geom = resolve_ski_jump_geom(angle, ski_jump_height_m, ski_jump_arc_length_m)
                mod = _configure_ski_conv(
                    aircraft, mass_kg, temp_c, wind_kt, geom['angle_deg'], geom['lip_height_m'])
                mod.print_config_summary()
                print()
                result = mod.run_min_takeoff_search()
                if result is None:
                    return _fail('未能找到可行解', buf.getvalue(), mode)
                if result['pitch_deg'] > PITCH_MAX_DEG:
                    raise ValueError(f"俯仰角 {result['pitch_deg']}° 超过硬上限 {PITCH_MAX_DEG}°")
                result['mass_kg'] = mass_kg
                lines = _format_conv_output(result, deck_length)

            elif mode == 'tiltrotor_short_takeoff':
                if aircraft.type_label != TILTROTOR_TYPE_LABEL:
                    raise ValueError('倾转短距起飞仅适用于倾转旋翼机')
                if carrier.ski_jump:
                    raise ValueError('倾转短距起飞需要平直甲板航母')
                stovl_strategy = normalize_tiltrotor_strategy(strategy)
                mod = _configure_tiltrotor(aircraft, mass_kg, temp_c, wind_kt)
                mod.print_config_summary()
                print()
                result = run_tiltrotor_strategy_search(mod, stovl_strategy)
                if result is None:
                    return _fail('未能找到可行解', buf.getvalue(), mode)
                result['mass_kg'] = mass_kg
                result['distance_m'] = float(result['x_m'])
                result['strategy'] = stovl_strategy
                lines = _format_f35b_output(
                    result, deck_length, MODES[mode], stovl_strategy,
                    strategy_labels=TILTROTOR_STRATEGIES,
                    angle_label='短舱倾转角',
                )

            else:
                raise ValueError(f'未知模式: {mode}')

        config_text = buf.getvalue()
        output_lines = [
            '=' * 60,
            '仿真配置',
            '=' * 60,
            config_text.rstrip(),
            '',
            '=' * 60,
            '优化结果',
            '=' * 60,
        ] + lines

        distance_m = result_distance_m(result)

        trajectory, deck_profile = _capture_trajectory(
            mode, mod, result, deck_length, stovl_strategy)
        plume_applicable = simulation_uses_plume_model(mode, aircraft)
        plume_edge = result.get('min_plume_trailing_edge_m') if plume_applicable else None
        deck_margin_m = deck_length - distance_m if distance_m is not None else None
        deck_launch_ok = distance_m is not None and distance_m <= deck_length
        exit_speed, exit_time = extract_exit_kinematics(result)

        return {
            'success': True,
            'mode': mode,
            'strategy': stovl_strategy,
            'output': '\n'.join(output_lines),
            'distance_m': distance_m,
            'deck_launch_ok': deck_launch_ok,
            'deck_margin_m': deck_margin_m,
            'output_summary': format_output_summary(distance_m, deck_margin_m),
            'highlights': build_takeoff_highlights(
                distance_m, deck_margin_m, exit_speed, exit_time, deck_launch_ok,
            ),
            'plume_applicable': plume_applicable,
            'min_plume_trailing_edge_m': plume_edge,
            'result': _json_safe(result),
            'trajectory': _json_safe(trajectory),
            'deck_profile': _json_safe(deck_profile),
        }
    except Exception as exc:
        config_text = buf.getvalue()
        msg = f'仿真错误: {exc}'
        output = config_text + ('\n' if config_text else '') + msg
        return {'success': False, 'mode': mode, 'strategy': stovl_strategy, 'output': output, 'error': str(exc)}


def _json_safe(obj: Any) -> Any:
    """将 numpy 标量等转为 JSON 可序列化类型。"""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if str(k).startswith('_') or k == 'history':
                continue
            out[k] = _json_safe(v)
        return out
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if hasattr(obj, 'tolist'):
        return obj.tolist()
    if hasattr(obj, 'item'):
        try:
            return obj.item()
        except ValueError:
            return obj.tolist()
    if isinstance(obj, (int, float, str, bool)) or obj is None:
        return obj
    return str(obj)


def _fail(msg: str, config_text: str, mode: str) -> dict[str, Any]:
    output = (
        (config_text + '\n' if config_text else '')
        + f'✗ {msg}'
    )
    return {'success': False, 'mode': mode, 'output': output, 'error': msg}


def run_simulation_json(payload: dict[str, Any] | str) -> dict[str, Any]:
    """Pyodide 入口：接收 JSON dict 或 JSON 字符串，返回 JSON-serializable dict。"""
    if isinstance(payload, str):
        import json
        payload = json.loads(payload)
    elif hasattr(payload, 'to_py'):
        payload = payload.to_py()
    ac = payload['aircraft']
    carrier = payload['carrier']
    return run_simulation(
        mode=payload['mode'],
        aircraft=ac,
        carrier=carrier,
        mass_kg=float(payload['mass_kg']),
        temp_c=float(payload['temp_c']),
        wind_kt=float(payload['wind_kt']),
        ski_jump_angle_deg=_opt_float(payload.get('ski_jump_angle_deg')),
        ski_jump_arc_length_m=_opt_float(payload.get('ski_jump_arc_length_m')),
        ski_jump_height_m=_opt_float(payload.get('ski_jump_height_m')),
        total_deck_length_m=_opt_float(payload.get('total_deck_length_m')),
        strategy=payload.get('strategy'),
    )


if __name__ == '__main__':
    from utils.database_csv import load_aircraft_csv, load_carriers_csv
    from utils.paths import AIRCRAFT_CSV, CARRIERS_CSV

    ac_map = load_aircraft_csv(AIRCRAFT_CSV)
    carriers = load_carriers_csv(CARRIERS_CSV)
    carrier = next(c for c in carriers if c.id == 'SHANDONG')
    ac = ac_map['J-15']
    r = run_simulation('ski_jump', ac, carrier, ac.a2a_mass_kg, 30.0, carrier.max_speed_kt)
    print(r['output'])
    sys.exit(0 if r['success'] else 1)
