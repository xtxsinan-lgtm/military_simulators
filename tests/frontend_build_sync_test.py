"""前端构建产物新鲜度与 Python↔JS 物理对拍测试。"""
from __future__ import annotations

import json
import math
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from scripts.frontend_catalog import build_catalog_payload
from scripts.generate_frontend_physics import (
    DOCS_PHYSICS,
    IOS_PHYSICS,
    MINI_PHYSICS,
    render_cjs,
    render_esm,
    render_physics_body,
    render_swift,
    _load_constants,
)
from utils.database_csv import load_aircraft_csv, load_carriers_csv
from utils.paths import AIRCRAFT_CSV, CARRIERS_CSV, ROOT
from utils.takeoff.ski_jump_geometry import compute_ski_jump_arc
from utils.specs import A2A_MISSILE_COUNT, PILOT_LOAD_KG
from utils.takeoff.takeoff_physics import (
    PITCH_MAX_DEG,
    calc_cl_alpha,
    calc_cl_from_alpha_deg,
    calc_oswald_e,
    taxi_alpha_deg,
)

NODE = shutil.which('node')
OSASCRIPT = shutil.which('osascript')


def test_physics_js_artifacts_match_generator():
    """docs / 小程序 physics.js 与 iOS Physics.swift 必须与生成器输出一致（防手改漂移）。"""
    assert DOCS_PHYSICS.read_text(encoding='utf-8') == render_esm()
    assert MINI_PHYSICS.read_text(encoding='utf-8') == render_cjs()
    assert IOS_PHYSICS.read_text(encoding='utf-8') == render_swift()


def test_miniprogram_data_json_matches_catalog():
    """小程序 data.json 须与 CSV→catalog 实时结果一致。"""
    path = ROOT / 'miniprogram' / 'data' / 'data.json'
    expected = build_catalog_payload(
        load_aircraft_csv(AIRCRAFT_CSV),
        load_carriers_csv(CARRIERS_CSV),
    )
    actual = json.loads(path.read_text(encoding='utf-8'))
    assert actual == expected


def test_miniprogram_data_js_matches_catalog():
    """小程序 data.js（供 require）须与 catalog 一致。"""
    from scripts.build_miniprogram import render_data_js

    path = ROOT / 'miniprogram' / 'data' / 'data.js'
    expected = build_catalog_payload(
        load_aircraft_csv(AIRCRAFT_CSV),
        load_carriers_csv(CARRIERS_CSV),
    )
    assert path.read_text(encoding='utf-8') == render_data_js(expected)

def test_docs_data_json_catalog_section_matches():
    """docs/data.json 的目录字段须与 catalog 一致（忽略 py_sources）。"""
    path = ROOT / 'docs' / 'data.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    expected = build_catalog_payload(
        load_aircraft_csv(AIRCRAFT_CSV),
        load_carriers_csv(CARRIERS_CSV),
    )
    for key in expected:
        assert data[key] == expected[key], f'docs/data.json 字段 {key} 过期，请运行 build_all.py'
    assert 'py_sources' in data and len(data['py_sources']) >= 1


def test_ios_data_json_matches_catalog():
    """iOS Bundle data.json 目录字段须与 catalog 一致，并含本地仿真 py_sources。"""
    from scripts.build_docs import PY_LOAD_ORDER

    path = ROOT / 'ios' / 'CarrierTakeOff' / 'Resources' / 'data.json'
    expected = build_catalog_payload(
        load_aircraft_csv(AIRCRAFT_CSV),
        load_carriers_csv(CARRIERS_CSV),
    )
    assert path.is_file(), '缺少 ios/.../data.json，请运行 build_all.py'
    actual = json.loads(path.read_text(encoding='utf-8'))
    for key in expected:
        assert actual[key] == expected[key], f'ios data.json 字段 {key} 过期'
    assert 'py_sources' in actual and len(actual['py_sources']) >= 1
    assert actual['py_load_order'] == list(PY_LOAD_ORDER)


def test_generated_constants_match_python():
    """生成器注入的常量与 Python 模块一致。"""
    c = _load_constants()
    assert c['PILOT_LOAD_KG'] == float(PILOT_LOAD_KG)
    assert c['A2A_MISSILE_COUNT'] == int(A2A_MISSILE_COUNT)
    assert c['PITCH_MAX_DEG'] == float(PITCH_MAX_DEG)


def test_python_ski_jump_and_aero_reference_values():
    """Python 参考值（供与 JS 对拍）。"""
    arc = compute_ski_jump_arc(12.0)
    assert arc.radius_m == pytest.approx(200.0)
    assert arc.lip_height_m == pytest.approx(200.0 * (1 - math.cos(math.radians(12))))

    ar = (14.7 ** 2) / 67.84
    eta = calc_oswald_e(ar, 42.0)
    cl_a = calc_cl_alpha(ar, eta, 42.0)
    assert taxi_alpha_deg() == pytest.approx(12.0)
    assert calc_cl_from_alpha_deg(20, cl_a) == pytest.approx(math.radians(20) * cl_a)


def _parity_payload_py():
    """构造 Python 侧对拍期望值。"""
    ac = load_aircraft_csv(AIRCRAFT_CSV)['J-15']
    arc_py = compute_ski_jump_arc(14.0, lip_height_m=5.0)
    ar = (ac.wingspan_m ** 2) / ac.wing_area_m2
    eta = float(calc_oswald_e(ar, ac.sweep_le_deg))
    cl_a = float(calc_cl_alpha(ar, eta, ac.sweep_le_deg))
    alpha_taxi = float(taxi_alpha_deg())
    cl_taxi = float(calc_cl_from_alpha_deg(alpha_taxi, cl_a))
    return ac, {
        'radius_m': arc_py.radius_m,
        'lip_height_m': arc_py.lip_height_m,
        'horizontal_m': arc_py.horizontal_m,
        'oswald_e': eta,
        'cl_alpha': cl_a,
        'taxi_alpha': alpha_taxi,
        'cl_taxi': cl_taxi,
        'a2a': float(ac.a2a_mass_kg),
    }


def _assert_parity(got: dict, expected: dict) -> None:
    for key, exp in expected.items():
        assert got[key] == pytest.approx(exp, rel=1e-9), key


@pytest.mark.skipif(NODE is None and OSASCRIPT is None, reason='需要 node 或 osascript 做 JS 对拍')
def test_js_physics_parity_with_python():
    """同一组输入下，生成的 physics 脚本与 Python 数值一致。"""
    ac, expected = _parity_payload_py()

    if NODE:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'physics.js'
            path.write_text(render_cjs(), encoding='utf-8')
            js = f'''
const p = require({json.dumps(str(path))});
const arc = p.computeSkiJumpArc(14, 5, null);
const ac = {{
  empty_kg: {ac.empty_kg},
  internal_fuel_kg: {ac.internal_fuel_kg},
  missile_mass_kg: {ac.missile_mass_kg},
  n_pilots: {ac.n_pilots},
  mtow_kg: {ac.mtow_kg},
  wingspan_m: {ac.wingspan_m},
  wing_area_m2: {ac.wing_area_m2},
  sweep_le_deg: {ac.sweep_le_deg},
  cd0: {ac.cd0},
}};
const aero = p.computeAircraftAero(ac);
console.log(JSON.stringify({{
  radius_m: arc.radius_m,
  lip_height_m: arc.lip_height_m,
  horizontal_m: arc.horizontal_m,
  oswald_e: aero.oswald_e,
  cl_alpha: aero.cl_alpha_per_rad,
  taxi_alpha: aero.taxi_alpha_deg,
  cl_taxi: aero.cl_taxi,
  a2a: p.a2aMassKg(ac),
}}));
'''
            proc = subprocess.run(
                [NODE, '-e', js], check=True, capture_output=True, text=True)
            got = json.loads(proc.stdout.strip())
    else:
        # macOS JXA：执行生成的函数体并返回 JSON
        body = render_physics_body()
        jxa = body + f'''
var arc = computeSkiJumpArc(14, 5, null);
var ac = {{
  empty_kg: {ac.empty_kg},
  internal_fuel_kg: {ac.internal_fuel_kg},
  missile_mass_kg: {ac.missile_mass_kg},
  n_pilots: {ac.n_pilots},
  mtow_kg: {ac.mtow_kg},
  wingspan_m: {ac.wingspan_m},
  wing_area_m2: {ac.wing_area_m2},
  sweep_le_deg: {ac.sweep_le_deg},
  cd0: {ac.cd0},
}};
var aero = computeAircraftAero(ac);
JSON.stringify({{
  radius_m: arc.radius_m,
  lip_height_m: arc.lip_height_m,
  horizontal_m: arc.horizontal_m,
  oswald_e: aero.oswald_e,
  cl_alpha: aero.cl_alpha_per_rad,
  taxi_alpha: aero.taxi_alpha_deg,
  cl_taxi: aero.cl_taxi,
  a2a: a2aMassKg(ac),
}});
'''
        proc = subprocess.run(
            [OSASCRIPT, '-l', 'JavaScript', '-e', jxa],
            check=True,
            capture_output=True,
            text=True,
        )
        got = json.loads(proc.stdout.strip())

    _assert_parity(got, expected)


def _eval_js_a2a(empty_kg, internal_fuel_kg, missile_mass_kg, n_pilots):
    """用生成的 physics.js 计算空战起飞重量。"""
    if NODE:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'physics.js'
            path.write_text(render_cjs(), encoding='utf-8')
            js = f'''
const p = require({json.dumps(str(path))});
const ac = {{
  empty_kg: {empty_kg},
  internal_fuel_kg: {internal_fuel_kg},
  missile_mass_kg: {missile_mass_kg},
  n_pilots: {n_pilots},
}};
console.log(JSON.stringify({{ a2a: p.a2aMassKg(ac) }}));
'''
            proc = subprocess.run(
                [NODE, '-e', js], check=True, capture_output=True, text=True)
            return json.loads(proc.stdout.strip())['a2a']
    body = render_physics_body()
    jxa = body + f'''
var ac = {{
  empty_kg: {empty_kg},
  internal_fuel_kg: {internal_fuel_kg},
  missile_mass_kg: {missile_mass_kg},
  n_pilots: {n_pilots},
}};
JSON.stringify({{ a2a: a2aMassKg(ac) }});
'''
    proc = subprocess.run(
        [OSASCRIPT, '-l', 'JavaScript', '-e', jxa],
        check=True, capture_output=True, text=True,
    )
    return json.loads(proc.stdout.strip())['a2a']


@pytest.mark.skipif(NODE is None and OSASCRIPT is None, reason='需要 node 或 osascript 做 JS 对拍')
def test_js_a2a_mass_uses_n_pilots():
    """前端空战重量须按飞行员人数计，无人机为 0、双座为 2。"""
    uav = load_aircraft_csv(AIRCRAFT_CSV)['53636N']
    f14 = load_aircraft_csv(AIRCRAFT_CSV)['F-14']
    assert _eval_js_a2a(
        uav.empty_kg, uav.internal_fuel_kg, uav.missile_mass_kg, uav.n_pilots,
    ) == pytest.approx(uav.a2a_mass_kg)
    assert _eval_js_a2a(
        f14.empty_kg, f14.internal_fuel_kg, f14.missile_mass_kg, f14.n_pilots,
    ) == pytest.approx(f14.a2a_mass_kg)
