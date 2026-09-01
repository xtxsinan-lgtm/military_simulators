"""Numeric snapshots for refactor / e2e regression verification."""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
from typing import Any

import simulators.takeoff.short_ski_jump_take_off as ski_stovl
import simulators.takeoff.short_take_off as flat
import simulators.takeoff.ski_jump_take_off as ski_conv
from utils.paths import BASELINE_JSON

BASELINE_PATH = BASELINE_JSON


def reset_takeoff_module_defaults(mod) -> None:
    """把起飞模块全局量恢复为 takeoff_config 参考机与环境，避免先前仿真污染快照。"""
    ref = mod._REF
    mode = mod._MODE
    mod.apply_thrust_temperature(float(mode['ambient_temp_c']))
    if hasattr(mod, 'apply_wind_knots'):
        mod.apply_wind_knots(float(mode['wind_kt']))
    mass = ref.get('mass_kg', ref.get('mass_kg_a2a'))
    geom = dict(
        mass_kg=float(mass),
        s_ref_m2=float(ref['s_ref_m2']),
        wingspan_m=float(ref['wingspan_m']),
        wing_height_m=float(ref['wing_height_m']),
        sweep_le_deg=float(ref['sweep_le_deg']),
        cd0=float(ref['cd0']),
    )
    if 't_max_sl_n' in ref:
        mod.apply_aircraft_geometry(**geom, t_max_sl_n=float(ref['t_max_sl_n']))
    else:
        mod.apply_aircraft_geometry(**geom)
        if hasattr(mod, 'apply_stovl_thrust_sl'):
            mod.apply_stovl_thrust_sl(
                float(ref['t_main_stovl_sl_n']),
                float(ref.get('t_liftfan_sl_n') or 0.0),
                float(ref.get('t_rollposts_sl_n') or 0.0),
            )
    if hasattr(mod, 'apply_ski_jump_deck') and 'ski_jump_angle_deg' in mode:
        lip = mode.get('ski_jump_lip_height_m')
        mod.apply_ski_jump_deck(
            float(mode['ski_jump_angle_deg']),
            lip_height_m=float(lip) if lip is not None else None,
        )
    # STOVL 仿真会改写尾流参数，快照前须回到 F-35B 默认
    if hasattr(mod, 'apply_exhaust_plume_params'):
        from utils.takeoff.exhaust_plume import default_exhaust_plume_params
        mod.apply_exhaust_plume_params(default_exhaust_plume_params())


def snap_flat() -> dict[str, Any]:
    reset_takeoff_module_defaults(flat)
    return {
        'rho': flat.RHO,
        'thrust_factor': flat.THRUST_TEMP_FACTOR,
        'oswald': flat.calc_oswald_e(flat.ASPECT_RATIO, flat.SWEEP_LE_DEG),
        'cl_alpha': flat.calc_cl_alpha(flat.ASPECT_RATIO, flat.OSWALD_E, flat.SWEEP_LE_DEG),
        'phi': flat.calc_ground_effect_phi(flat.WING_HEIGHT_M, flat.WINGSPAN_M),
        'exhaust_30': flat.calc_exhaust_safe_distance_m(30.0, flat.V_WIND_MPS),
        'exhaust_theta': flat.calc_exhaust_theta_deg_for_safe_distance_m(50.0, flat.V_WIND_MPS),
        'min_nozzle': flat.calc_min_nozzle_deg_for_plume(100.0, flat.MIN_SAFE_DISTANCE_M, flat.V_WIND_MPS),
        'strategy_c': flat.simulate_strategy_c(flat.MIN_SAFE_DISTANCE_M),
    }


def snap_ski_stovl() -> dict[str, Any]:
    reset_takeoff_module_defaults(ski_stovl)
    with contextlib.redirect_stdout(io.StringIO()):
        r = ski_stovl.search_strategy_c(ski_stovl.MIN_SAFE_DISTANCE_M)
    return {
        'rho': ski_stovl.RHO,
        'arc_horizontal': ski_stovl.SKI_JUMP_HORIZONTAL_M,
        'exhaust_30': ski_stovl.calc_exhaust_safe_distance_m(30.0, ski_stovl.V_WIND_MPS),
        'total_dist': ski_stovl.total_takeoff_distance_m(100.0),
        'simulate_ab': ski_stovl.simulate(80.0, 20.0, 45.0, 'A', 20.0),
        'strategy_c': r,
    }


def snap_ski_conv() -> dict[str, Any]:
    reset_takeoff_module_defaults(ski_conv)
    with contextlib.redirect_stdout(io.StringIO()):
        best = ski_conv.search_flat_length()
    return {
        'rho': ski_conv.RHO,
        'best_flat': best,
        'simulate_100_15': ski_conv.simulate(100.0, 15.0)[:5],
    }


def collect_snapshots() -> dict[str, Any]:
    return {
        'flat': snap_flat(),
        'ski_stovl': snap_ski_stovl(),
        'ski_conv': snap_ski_conv(),
    }


def normalize(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: normalize(v) for k, v in sorted(obj.items())}
    if isinstance(obj, (list, tuple)):
        return [normalize(v) for v in obj]
    if isinstance(obj, float):
        return round(obj, 9)
    return obj


def load_baseline(path: Path | None = None) -> dict[str, Any]:
    path = path or BASELINE_PATH
    return json.loads(path.read_text(encoding='utf-8'))


def write_baseline(path: Path | None = None) -> dict[str, Any]:
    path = path or BASELINE_PATH
    data = collect_snapshots()
    path.write_text(json.dumps(data, indent=2, default=str) + '\n', encoding='utf-8')
    return data


def diff_snapshots(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    before_n = normalize(before)
    after_n = normalize(after)
    return [key for key in before_n if before_n[key] != after_n[key]]


def assert_matches_baseline(path: Path | None = None) -> None:
    before = load_baseline(path)
    after = collect_snapshots()
    mismatches = diff_snapshots(before, after)
    if mismatches:
        raise AssertionError(f'snapshot mismatch in: {", ".join(mismatches)}')
