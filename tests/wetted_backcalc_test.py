"""浸润面积倒推与机身尺寸分解单元测试。"""
from __future__ import annotations

import math

import pytest

from utils.combat_radius.breguet import combat_radius_m
from utils.combat_radius.lift_drag import (
    box_surface_area_m2,
    geometric_wetted_area_m2,
    aircraft_from_dict,
)
from utils.combat_radius.wetted_backcalc import (
    F35_BODY_FRAC,
    F35_CONE_FRAC,
    F35_NOSE_FRAC,
    fuse_dims_for_target_swet,
    geometry_dict_for_csv,
    iterate_fuse_dims_with_nose_scale,
    ld_from_combat_radius_m,
    ld_from_ferry_range_m,
    length_segments_from_aircraft_length,
    lifting_wetted_from_planforms,
    nose_wetted_m2,
    scale_nose_diameters_to_fuse_width,
    solve_box_width_height,
    tsfc_lb_lbf_h_to_kg_n_s,
)


def test_ld_from_combat_radius_roundtrip():
    """作战半径 ↔ L/D 互逆。"""
    v, c, ld = 240.0, 2.8e-5, 10.0
    wi, wf = 15000.0, 11000.0
    r = combat_radius_m(v, c, ld, wi, wf)
    assert ld_from_combat_radius_m(r, v, c, wi, wf) == pytest.approx(ld)


def test_ld_from_ferry_range_is_half_radius_formula():
    """航程反推的 L/D 与「航程/2 作战半径」一致。"""
    v, c, ld = 250.0, 3.0e-5, 9.5
    wi, wf = 12000.0, 9000.0
    ferry = 2.0 * combat_radius_m(v, c, ld, wi, wf)
    assert ld_from_ferry_range_m(ferry, v, c, wi, wf) == pytest.approx(ld)


def test_tsfc_unit_conversion():
    """0.8 lb/lbf·h 约为 2.27e-5 kg/(N·s)。"""
    si = tsfc_lb_lbf_h_to_kg_n_s(0.8)
    assert si == pytest.approx(0.8 / (9.80665 * 3600.0))


def test_length_segments_f35_fractions():
    """F-35A 比例切分后三段之和约为 0.89·L。"""
    segs = length_segments_from_aircraft_length(15.7)
    assert segs['nose_cone_length_m'] == pytest.approx(15.7 * F35_CONE_FRAC, abs=5e-3)
    assert segs['nose_length_m'] == pytest.approx(15.7 * F35_NOSE_FRAC, abs=5e-3)
    assert segs['fuse_body_length_m'] == pytest.approx(15.7 * F35_BODY_FRAC, abs=5e-3)
    total = sum(segs.values())
    assert total == pytest.approx(15.7 * (F35_CONE_FRAC + F35_NOSE_FRAC + F35_BODY_FRAC), abs=1e-2)


def test_solve_box_width_height_matches_surface():
    """宽高比固定时，解出的长方体表面积等于目标。"""
    w, h = solve_box_width_height(10.0, 80.0, 1.2)
    assert box_surface_area_m2(10.0, w, h) == pytest.approx(80.0)
    assert w / h == pytest.approx(1.2)


def test_fuse_dims_for_target_swet_f16_jsbsim():
    """F-16：按 JSBSim 升力面与目标总浸润倒推机身宽高。"""
    # JSBSim：总浸润约 130.4 m²；升力面平面合计约 28.28 m²
    calc = fuse_dims_for_target_swet(
        130.4,
        nose_cone_length_m=1.02,
        nose_cone_diameter_m=0.57,
        nose_length_m=2.94,
        nose_root_diameter_m=0.94,
        fuse_body_length_m=10.17,
        main_wing_area_m2=15.85,
        canard_htail_area_m2=5.92,
        ventral_fin_area_m2=1.42,
        vtail_area_m2=5.09,
        width_height_ratio=1.12,
    )
    assert calc['total_swet_m2'] == pytest.approx(130.4, abs=0.05)
    assert 1.4 < calc['fuse_width_m'] < 1.8
    assert 1.2 < calc['fuse_height_m'] < 1.6


def test_iterate_fuse_dims_with_nose_scale_converges():
    """机头直径随机身宽缩放时仍能对齐目标浸润。"""
    segs = length_segments_from_aircraft_length(15.06)
    out = iterate_fuse_dims_with_nose_scale(
        130.4,
        nose_cone_length_m=segs['nose_cone_length_m'],
        nose_length_m=segs['nose_length_m'],
        fuse_body_length_m=segs['fuse_body_length_m'],
        main_wing_area_m2=15.85,
        canard_htail_area_m2=5.92,
        ventral_fin_area_m2=1.42,
        vtail_area_m2=5.09,
        width_height_ratio=1.12,
        seed_width_m=1.6,
    )
    assert out['total_swet_m2'] == pytest.approx(130.4, abs=0.15)
    assert out['nose_cone_diameter_m'] < out['nose_root_diameter_m'] < out['fuse_width_m']


def test_lifting_and_nose_helpers():
    """归一化辅助函数。"""
    assert lifting_wetted_from_planforms(10.0, 2.0, 1.0, 3.0) == pytest.approx(32.0)
    assert nose_wetted_m2(1.0, 0.8, 2.0, 1.2) > 0
    d = scale_nose_diameters_to_fuse_width(2.0)
    assert d['nose_cone_diameter_m'] == pytest.approx(0.72)
    assert d['nose_root_diameter_m'] == pytest.approx(1.2)


def test_geometry_dict_for_csv_empty_optional_surfaces():
    """无平尾/腹鳍时 CSV 字段为空串。"""
    calc = {
        'nose_cone_length_m': 1.0,
        'nose_cone_diameter_m': 0.6,
        'nose_length_m': 2.5,
        'nose_root_diameter_m': 1.0,
        'fuse_body_length_m': 9.0,
        'fuse_width_m': 1.7,
        'fuse_height_m': 1.5,
    }
    row = geometry_dict_for_csv(calc, {'main_wing_area_m2': 20.0, 'vtail_area_m2': 4.0})
    assert row['main_wing_area_m2'] == 20.0
    assert row['canard_htail_area_m2'] == ''
    assert row['ventral_fin_area_m2'] == ''
    assert row['vtail_area_m2'] == 4.0


def test_ld_from_combat_radius_rejects_bad_mass():
    """质量比非法时抛错。"""
    with pytest.raises(ValueError, match='起飞质量'):
        ld_from_combat_radius_m(1e6, 240.0, 3e-5, 1000.0, 1000.0)
