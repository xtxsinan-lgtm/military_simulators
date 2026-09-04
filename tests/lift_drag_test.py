"""巡航升阻比估算单元测试。"""
from __future__ import annotations

import math

import pytest

from utils.combat_radius.lift_drag import (
    CDW_BWB,
    CDW_CANARD,
    CDW_KORN_COEF,
    CDW_SS_BODY,
    CDW_SS_BODY_POST,
    CDW_SS_LIFT,
    CDW_SS_LIFT_MACH_CAP,
    CDW_SS_ROUGH_BODY,
    CDW_SS_ROUGH_LIFT,
    CDW_SS_ROUGH_WING,
    CDW_SS_WING,
    CDW_TAILLESS,
    CDW_PELICAN,
    CDW_SMALL_HTAIL,
    CDW_MEDIUM_HTAIL,
    LAYOUT_CDW_VOL,
    LAYOUT_MULT,
    CDW_TRANS_AMP,
    CDW_TRANS_PEAK,
    CDW_TRANS_WIDTH,
    CDW_TRANS_WIDTH_LO,
    TRANSONIC_ONSET,
    CD_AOA_COEF,
    CL_AOA_ONSET,
    CF0_REF,
    F22_SUPERCRUISE_MACH,
    F22_MAX_SPEED_MACH,
    J20_SUPERCRUISE_MACH,
    KAPPA_A,
    KORN_DM_CAP,
    K_E_REF,
    FUSE_BODY_AREA_MAX,
    FUSE_BODY_AREA_MIN,
    FUSE_REF_HEIGHT_M,
    FUSE_REF_WIDTH_M,
    FUSE_WETTED_FRAC,
    NO_CANOPY_MULT,
    BUMP_FRICTION_MULT,
    BUMP_FORM_MULT,
    BUMP_MULT,
    RHO11,
    SUPERCRUISE_BAND_HI,
    Aircraft,
    aircraft_from_dict,
    aircraft_mach_angle_rad,
    aircraft_to_dict,
    calibrate_default_anchors,
    default_ld_anchor_aircraft,
    estimate_takeoff_cd0,
    parasite_cd0,
    atmosphere,
    calibrate,
    cd_high_aoa,
    cd_wave,
    cd_wave_korn,
    cd_wave_mach_angle,
    cd_wave_supersonic,
    cd_wave_transonic,
    transonic_gaussian,
    cl_cruise,
    components,
    drag_divergence_mach,
    drag_divergence_mach_at,
    double_delta_area_weights,
    double_delta_kink_span_frac,
    double_delta_panels,
    blend_sweep_quantity,
    has_double_delta_sweep,
    mach_angle_rad,
    mach_cone_limit,
    oswald_e_for_aircraft,
    oswald_e_raw,
    oswald_sweep_deg,
    predict_ld,
    fuse_body_area_factor,
    fuse_section_area_m2,
    fuse_wetted_factor,
    ellipse_perimeter_m,
    wetted_area_factor,
    rough_wetted_mult,
    rough_form_cd0_mult,
    cone_lateral_area_m2,
    frustum_lateral_area_m2,
    box_surface_area_m2,
    has_geometric_wetted,
    has_geometric_wetted_dict,
    geometric_wetted_area_m2,
    geometric_wetted_ratio,
    fuselage_geometric_wetted_m2,
    lifting_planform_wetted_m2,
    WETTED_RATIO_REF,
    LIFTING_WETTED_SIDES,
    cd_wave_korn_at,
    cd_wave_ss_body_post,
    cd_wave_ss_rough,
    cd_wave_ss_rough_wing_at,
    cd_wave_ss_wing_at,
    cd_wave_transonic_at,
    lift_wave_mach_factor,
    INLET_CARET_CDW,
    INLET_CARET_WETTED,
    inlet_cdw_vol_mult,
    inlet_wetted_mult,
    parse_inlet,
    parse_store_mount,
    store_one_wetted_m2,
    store_one_front_m2,
    cd_store_parasite,
    cd_store_wave,
    cd_store,
    _as_bool,
    _canopy_from_dict,
    _fuse_section_dims,
    _n_stores_from_dict,
    _optional_positive_float,
)


def _f35c() -> Aircraft:
    return Aircraft(
        'F-35C', AR=2.77, sweep_deg=30.9, wing_loading=0.341,
        tc=0.0510, mach=0.8, alt_m=11300,
        planform='trapezoidal', layout='conventional',
        bwb=False, rough=True,
    )


def _f22() -> Aircraft:
    return Aircraft(
        'F-22', AR=2.37, sweep_deg=41.3, wing_loading=0.318,
        tc=0.0520, mach=0.8, alt_m=11800,
        planform='trapezoidal', layout='conventional',
        bwb=False, rough=False,
    )


def _j20() -> Aircraft:
    return Aircraft(
        'J-20', AR=2.32, sweep_deg=46.3, wing_loading=0.329,
        tc=0.0430, mach=0.8, alt_m=12000,
        planform='trapezoidal', layout='canard',
        bwb=False, rough=False,
    )


def test_as_bool_parses_common_tokens():
    assert _as_bool(True) is True
    assert _as_bool(False) is False
    assert _as_bool('是') is True
    assert _as_bool('否') is False
    assert _as_bool(1) is True
    assert _as_bool(0) is False
    assert _as_bool(None, True) is True
    with pytest.raises(ValueError):
        _as_bool('maybe')


def test_aircraft_from_dict_and_to_dict_roundtrip():
    ac = aircraft_from_dict({
        'name': 'J-20', 'AR': 2.32, 'sweep_deg': 46.3, 'wing_loading': 0.329,
        'tc': 0.043, 'mach': 0.8, 'alt_m': 12000,
        'planform': 'trapezoidal', 'layout': 'canard', 'bwb': 0, 'rough': '否',
        'mach_angle_deg': 21.7,
    })
    d = aircraft_to_dict(ac)
    assert d['name'] == 'J-20'
    assert d['planform'] == 'trapezoidal'
    assert d['mach_angle_deg'] == pytest.approx(21.7)
    assert d['bwb'] is False
    assert d['rough'] is False
    assert d['inlet'] == 'dsi'
    assert d['store_mount'] == 'internal'
    assert d['n_stores'] == pytest.approx(0.0)
    again = aircraft_from_dict(d)
    assert again.AR == pytest.approx(2.32)
    assert again.length_m == pytest.approx(0.0)
    assert again.wingspan_m == pytest.approx(0.0)
    assert again.fuse_width_m == pytest.approx(0.0)
    assert again.fuse_height_m == pytest.approx(0.0)
    caret = aircraft_from_dict({**d, 'inlet': '加莱特'})
    assert caret.inlet == 'caret'


def test_parse_inlet_aliases_and_default():
    """空值视为 DSI；加莱特/caret/garrett 归一为 caret。"""
    assert parse_inlet(None) == 'dsi'
    assert parse_inlet('') == 'dsi'
    assert parse_inlet('DSI') == 'dsi'
    assert parse_inlet('caret') == 'caret'
    assert parse_inlet('Garrett') == 'caret'
    assert parse_inlet('加莱特进气道') == 'caret'
    with pytest.raises(ValueError, match='未知进气道'):
        parse_inlet('pitot')


def test_inlet_wetted_and_cdw_multipliers():
    """加莱特抬高浸润、压低超音速体积波阻；非法 id 报错。"""
    assert inlet_wetted_mult('dsi') == pytest.approx(1.0)
    assert inlet_wetted_mult('caret') == pytest.approx(INLET_CARET_WETTED)
    assert inlet_cdw_vol_mult('dsi') == pytest.approx(1.0)
    assert inlet_cdw_vol_mult('caret') == pytest.approx(INLET_CARET_CDW)
    assert INLET_CARET_WETTED > 1.0
    assert 0.5 < INLET_CARET_CDW < 1.0
    with pytest.raises(ValueError, match='未知进气道'):
        inlet_wetted_mult('pitot')
    with pytest.raises(ValueError, match='未知进气道'):
        inlet_cdw_vol_mult('pitot')


def test_caret_inlet_raises_cd0_and_lowers_volume_wave_drag():
    """同一几何：加莱特亚音速 L/D 略降，超音速体积波阻低于 DSI。"""
    dsi = _f22()
    caret = Aircraft(**{**aircraft_to_dict(dsi), 'inlet': 'caret'})
    assert wetted_area_factor(caret) == pytest.approx(
        wetted_area_factor(dsi) * INLET_CARET_WETTED,
    )
    cf0, k_e = calibrate_default_anchors()
    ld_dsi, d_dsi = predict_ld(dsi, cf0, k_e)
    ld_caret, d_caret = predict_ld(caret, cf0, k_e)
    assert d_caret['CD0'] > d_dsi['CD0']
    assert ld_caret < ld_dsi
    vol_dsi = cd_wave_supersonic(1.7, dsi, 0.0)
    vol_caret = cd_wave_supersonic(1.7, caret, 0.0)
    assert vol_caret == pytest.approx(vol_dsi * INLET_CARET_CDW)
    lift_dsi = cd_wave_supersonic(1.7, dsi, 0.25) - vol_dsi
    lift_caret = cd_wave_supersonic(1.7, caret, 0.25) - vol_caret
    assert lift_caret == pytest.approx(lift_dsi)


def test_optional_positive_float_blank_and_numeric():
    assert _optional_positive_float(None) == 0.0
    assert _optional_positive_float('') == 0.0
    assert _optional_positive_float('18.92') == pytest.approx(18.92)


def test_mach_angle_and_cone_limit():
    phi = mach_angle_rad(18.92, 13.56)
    assert 0 < phi < math.pi / 2
    assert math.degrees(phi) == pytest.approx(math.degrees(math.atan(6.78 / 18.92)))
    m_lim = mach_cone_limit(phi)
    assert m_lim == pytest.approx(1.0 / math.sin(phi))
    with pytest.raises(ValueError, match='机身长度'):
        mach_angle_rad(0, 10)
    with pytest.raises(ValueError, match='马赫角'):
        mach_cone_limit(0.0)


def test_cd_wave_mach_angle_zero_below_limit():
    phi = mach_angle_rad(18.92, 13.56)
    assert cd_wave_mach_angle(0.8, phi) == 0.0
    # 远超锥限时附加波阻为正
    assert cd_wave_mach_angle(mach_cone_limit(phi) + 0.5, phi) > 0


def test_aircraft_mach_angle_rad_prefers_degrees():
    """预设马赫角优先于机长/翼展估算。"""
    from_deg = Aircraft(**{**aircraft_to_dict(_f22()), 'mach_angle_deg': 28.5, 'length_m': 18.92, 'wingspan_m': 13.56})
    phi = aircraft_mach_angle_rad(from_deg)
    assert phi is not None
    assert math.degrees(phi) == pytest.approx(28.5)
    fallback = Aircraft(**{**aircraft_to_dict(_f22()), 'mach_angle_deg': 0, 'length_m': 18.92, 'wingspan_m': 13.56})
    assert aircraft_mach_angle_rad(fallback) == pytest.approx(mach_angle_rad(18.92, 13.56))
    assert aircraft_mach_angle_rad(_f22()) is None


def test_cd_wave_includes_mach_angle_extra_at_high_mach():
    base = Aircraft(**{**aircraft_to_dict(_f22()), 'mach': 3.5, 'length_m': 0, 'wingspan_m': 0})
    with_geom = Aircraft(**{**aircraft_to_dict(_f22()), 'mach': 3.5, 'length_m': 18.92, 'wingspan_m': 13.56})
    with_deg = Aircraft(**{**aircraft_to_dict(_f22()), 'mach': 3.5, 'mach_angle_deg': 28.5})
    cl = cl_cruise(base)
    assert cd_wave(cl, with_geom) > cd_wave(cl, base)
    assert cd_wave(cl, with_deg) > cd_wave(cl, base)


def test_aircraft_from_dict_rejects_unknown_planform():
    with pytest.raises(ValueError, match='未知翼型'):
        aircraft_from_dict({
            'name': 'x', 'AR': 2, 'sweep_deg': 30, 'wing_loading': 0.3,
            'tc': 0.05, 'mach': 0.8, 'alt_m': 12000,
            'planform': 'ellipse', 'layout': 'conventional',
        })


def test_aircraft_from_dict_rejects_unknown_layout():
    with pytest.raises(ValueError, match='未知布局'):
        aircraft_from_dict({
            'name': 'x', 'AR': 2, 'sweep_deg': 30, 'wing_loading': 0.3,
            'tc': 0.05, 'mach': 0.8, 'alt_m': 12000,
            'planform': 'delta', 'layout': 'tandem',
        })


def test_aircraft_from_dict_accepts_medium_htail():
    """中等平尾须能通过机型字典解析。"""
    ac = aircraft_from_dict({
        'name': 'x', 'AR': 2, 'sweep_deg': 30, 'wing_loading': 0.3,
        'tc': 0.05, 'mach': 0.8, 'alt_m': 12000,
        'planform': 'lambda', 'layout': 'medium_htail',
    })
    assert ac.layout == 'medium_htail'


def test_atmosphere_at_tropopause():
    rho, a = atmosphere(11000)
    assert rho == pytest.approx(RHO11)
    assert a == pytest.approx(math.sqrt(1.4 * 287.05287 * 216.65))


def test_atmosphere_density_falls_with_altitude():
    rho_lo, _ = atmosphere(11000)
    rho_hi, _ = atmosphere(15000)
    assert rho_hi < rho_lo


def test_cl_cruise_positive_and_below_one():
    cl = cl_cruise(_f35c())
    assert 0.1 < cl < 0.8


def test_oswald_e_raw_swept_fighter_range():
    e = oswald_e_raw(2.77, 30.9)
    assert 0.5 < e < 1.2


def test_wetted_area_factor_independent_switches():
    base = _f22()
    bwb = Aircraft(**{**aircraft_to_dict(base), 'bwb': True})
    rough = Aircraft(**{**aircraft_to_dict(base), 'rough': True})
    w0 = wetted_area_factor(base)
    assert wetted_area_factor(bwb) == pytest.approx(w0 * 0.90)
    assert wetted_area_factor(rough) == pytest.approx(w0 * BUMP_FRICTION_MULT)
    no_canopy = Aircraft(**{**aircraft_to_dict(base), 'canopy': False})
    assert wetted_area_factor(no_canopy) == pytest.approx(w0 * NO_CANOPY_MULT)


def test_canopy_from_dict_infers_from_n_pilots():
    """显式 canopy 优先；否则 n_pilots=0 视为无座舱。"""
    assert _canopy_from_dict({}) is True
    assert _canopy_from_dict({'n_pilots': 1}) is True
    assert _canopy_from_dict({'n_pilots': 0}) is False
    assert _canopy_from_dict({'n_pilots': 0, 'canopy': True}) is True
    uav = aircraft_from_dict({
        'name': 'UAV', 'AR': 2.5, 'sweep_deg': 50, 'wing_loading': 0.18,
        'tc': 0.043, 'mach': 0.8, 'alt_m': 12000,
        'planform': 'lambda', 'layout': 'tailless', 'n_pilots': 0,
    })
    assert uav.canopy is False


def test_wetted_area_factor_planform_and_layout():
    ac = _f22()
    w_trap = wetted_area_factor(ac)
    delta = Aircraft(**{**aircraft_to_dict(ac), 'planform': 'delta'})
    diamond = Aircraft(**{**aircraft_to_dict(ac), 'planform': 'diamond'})
    lam = Aircraft(**{**aircraft_to_dict(ac), 'planform': 'lambda'})
    double_delta = Aircraft(**{**aircraft_to_dict(ac), 'planform': 'double_delta'})
    swept = Aircraft(**{**aircraft_to_dict(ac), 'planform': 'swept'})
    unswept = Aircraft(**{**aircraft_to_dict(ac), 'planform': 'unswept'})
    canard = Aircraft(**{**aircraft_to_dict(ac), 'layout': 'canard'})
    tailless = Aircraft(**{**aircraft_to_dict(ac), 'layout': 'tailless'})
    pelican = Aircraft(**{**aircraft_to_dict(ac), 'layout': 'pelican'})
    small_htail = Aircraft(**{**aircraft_to_dict(ac), 'layout': 'small_htail'})
    medium_htail = Aircraft(**{**aircraft_to_dict(ac), 'layout': 'medium_htail'})
    assert wetted_area_factor(delta) < w_trap
    assert wetted_area_factor(diamond) < wetted_area_factor(delta)
    assert wetted_area_factor(lam) == pytest.approx(wetted_area_factor(diamond))
    assert wetted_area_factor(delta) < wetted_area_factor(double_delta) < w_trap
    assert wetted_area_factor(swept) < w_trap
    assert wetted_area_factor(unswept) > w_trap
    assert wetted_area_factor(canard) > w_trap
    assert wetted_area_factor(tailless) < w_trap
    assert (
        wetted_area_factor(tailless)
        < wetted_area_factor(small_htail)
        < wetted_area_factor(pelican)
        < wetted_area_factor(medium_htail)
        < w_trap
    )


def test_ellipse_perimeter_m_circle_and_rejects_nonpositive():
    """圆截面周长为 2πr；宽高须为正。"""
    assert ellipse_perimeter_m(2.0, 2.0) == pytest.approx(2.0 * math.pi)
    with pytest.raises(ValueError, match='机身宽高'):
        ellipse_perimeter_m(0.0, 1.0)
    with pytest.raises(ValueError, match='机身宽高'):
        ellipse_perimeter_m(1.0, -0.5)


def test_fuse_section_area_m2_ellipse_and_rejects_nonpositive():
    """椭圆面积 πwh/4；圆退化为 πr²。"""
    assert fuse_section_area_m2(2.0, 2.0) == pytest.approx(math.pi)
    assert fuse_section_area_m2(3.5, 1.82) == pytest.approx(math.pi * 3.5 * 1.82 / 4.0)
    with pytest.raises(ValueError, match='机身宽高'):
        fuse_section_area_m2(0.0, 1.82)


def test_fuse_section_dims_requires_both_positive():
    """宽或高缺省则视为未建模。"""
    assert _fuse_section_dims(_f22()) is None
    only_w = Aircraft(**{**aircraft_to_dict(_f22()), 'fuse_width_m': 3.5})
    assert _fuse_section_dims(only_w) is None
    both = Aircraft(**{**aircraft_to_dict(_f22()), 'fuse_width_m': 3.5, 'fuse_height_m': 1.82})
    assert _fuse_section_dims(both) == (3.5, 1.82)


def test_fuse_wetted_factor_ref_is_one_missing_is_one():
    """F-35 参考截面浸润乘数为 1；缺截面不改。"""
    assert fuse_wetted_factor(_f22()) == pytest.approx(1.0)
    ref = Aircraft(**{
        **aircraft_to_dict(_f35c()),
        'fuse_width_m': FUSE_REF_WIDTH_M, 'fuse_height_m': FUSE_REF_HEIGHT_M,
    })
    assert fuse_wetted_factor(ref) == pytest.approx(1.0)
    slim = Aircraft(**{**aircraft_to_dict(_f22()), 'fuse_width_m': 2.71, 'fuse_height_m': 1.29})
    fat = Aircraft(**{**aircraft_to_dict(_f22()), 'fuse_width_m': 4.7, 'fuse_height_m': 2.3})
    assert fuse_wetted_factor(slim) < 1.0
    assert fuse_wetted_factor(fat) > 1.0
    p_slim = ellipse_perimeter_m(2.71, 1.29)
    p_ref = ellipse_perimeter_m(FUSE_REF_WIDTH_M, FUSE_REF_HEIGHT_M)
    assert fuse_wetted_factor(slim) == pytest.approx(
        (1.0 - FUSE_WETTED_FRAC) + FUSE_WETTED_FRAC * (p_slim / p_ref),
    )


def _f35a_wetted() -> Aircraft:
    """F-35A 分段浸润几何（与 CSV / 归一化基准一致）。"""
    return Aircraft(**{
        **aircraft_to_dict(_f35c()),
        'name': 'F-35A',
        'tc': 0.06,
        'wing_loading': 0.432,
        'nose_cone_length_m': 1.06,
        'nose_cone_diameter_m': 1.02,
        'nose_length_m': 3.26,
        'nose_root_diameter_m': 1.90,
        'fuse_body_length_m': 9.66,
        'fuse_width_m': 3.40,
        'fuse_height_m': 1.97,
        'main_wing_area_m2': 24.48,
        'canard_htail_area_m2': 11.12,
        'ventral_fin_area_m2': 0.0,
        'vtail_area_m2': 4.23 * 2,
        'wing_area_m2': 42.74,
    })


def test_cone_frustum_box_surface_formulas():
    """圆锥/圆台/长方体表面积公式：单位圆、圆柱退化、单位立方。"""
    assert cone_lateral_area_m2(1.0, 2.0) == pytest.approx(math.pi * math.sqrt(2.0))
    assert frustum_lateral_area_m2(1.0, 2.0, 2.0) == pytest.approx(2.0 * math.pi)
    assert box_surface_area_m2(1.0, 1.0, 1.0) == pytest.approx(6.0)
    with pytest.raises(ValueError, match='机头锥'):
        cone_lateral_area_m2(0.0, 1.0)
    with pytest.raises(ValueError, match='圆台'):
        frustum_lateral_area_m2(1.0, 0.0, 1.0)
    with pytest.raises(ValueError, match='盒段'):
        box_surface_area_m2(1.0, 1.0, 0.0)


def test_geometric_wetted_f35a_is_ratio_ref():
    """F-35A 分段浸润比等于归一化基准，机身浸润乘数为 1。"""
    ac = _f35a_wetted()
    assert has_geometric_wetted(ac) is True
    assert has_geometric_wetted_dict(aircraft_to_dict(ac)) is True
    assert geometric_wetted_ratio(ac) == pytest.approx(WETTED_RATIO_REF)
    assert fuse_wetted_factor(ac) == pytest.approx(1.0)
    s_wet = geometric_wetted_area_m2(ac)
    lifting = LIFTING_WETTED_SIDES * (24.48 + 11.12 + 4.23 * 2)
    expected = (
        cone_lateral_area_m2(1.06, 1.02)
        + frustum_lateral_area_m2(3.26, 1.02, 1.90)
        + box_surface_area_m2(9.66, 3.40, 1.97)
        + lifting
    )
    assert s_wet == pytest.approx(expected)
    assert fuselage_geometric_wetted_m2(ac) == pytest.approx(expected - lifting)
    assert lifting_planform_wetted_m2(ac) == pytest.approx(lifting)


def test_lifting_planform_wetted_counts_both_sides():
    """升力面浸润须按平面面积×上下两面，再与机身表面积相加。"""
    ac = _f35a_wetted()
    planform = (
        ac.main_wing_area_m2 + ac.canard_htail_area_m2
        + ac.ventral_fin_area_m2 + ac.vtail_area_m2
    )
    assert LIFTING_WETTED_SIDES == pytest.approx(2.0)
    assert lifting_planform_wetted_m2(ac) == pytest.approx(2.0 * planform)
    assert geometric_wetted_area_m2(ac) == pytest.approx(
        fuselage_geometric_wetted_m2(ac) + 2.0 * planform,
    )
    missing = Aircraft(**{**aircraft_to_dict(ac), 'main_wing_area_m2': 0.0})
    assert has_geometric_wetted(missing) is False
    with pytest.raises(ValueError, match='分段几何'):
        geometric_wetted_area_m2(missing)


def test_geometric_wetted_larger_wing_lowers_ratio():
    """同机身更大主翼 → S_wet/S_ref 更小，浸润乘数低于 F-35A。"""
    a = _f35a_wetted()
    c = Aircraft(**{
        **aircraft_to_dict(a),
        'name': 'F-35C',
        'main_wing_area_m2': 38.84,
        'canard_htail_area_m2': 13.04,
        'vtail_area_m2': 5.18 * 2,
        'wing_area_m2': 62.06,
    })
    assert geometric_wetted_ratio(c) < geometric_wetted_ratio(a)
    assert fuse_wetted_factor(c) < 1.0
    j20 = Aircraft(**{
        **aircraft_to_dict(_j20()),
        'nose_cone_length_m': 1.54,
        'nose_cone_diameter_m': 1.24,
        'nose_length_m': 4.37,
        'nose_root_diameter_m': 1.29,
        'fuse_body_length_m': 13.87,
        'fuse_width_m': 3.80,
        'fuse_height_m': 1.88,
        'main_wing_area_m2': 32.93,
        'canard_htail_area_m2': 6.90,
        'ventral_fin_area_m2': 6.38,
        'vtail_area_m2': 9.07 * 2,
        'wing_area_m2': 76.8,
    })
    assert j20.ventral_fin_area_m2 == pytest.approx(3.19 * 2)
    assert has_geometric_wetted(j20) is True
    assert geometric_wetted_area_m2(j20) > geometric_wetted_area_m2(a)


def test_vtail_increases_lifting_wetted():
    """垂尾按左右两件×两面计入浸润；单侧单面 4.23 → 入库 8.46 → 浸润 16.92。"""
    base = _f35a_wetted()
    bare = Aircraft(**{**aircraft_to_dict(base), 'vtail_area_m2': 0.0})
    delta = lifting_planform_wetted_m2(base) - lifting_planform_wetted_m2(bare)
    assert base.vtail_area_m2 == pytest.approx(4.23 * 2)
    assert delta == pytest.approx(LIFTING_WETTED_SIDES * 4.23 * 2)
    assert geometric_wetted_area_m2(base) > geometric_wetted_area_m2(bare)


def test_has_geometric_wetted_dict_requires_all_fields():
    """缺任一必填分段字段则不算作战半径几何机型。"""
    d = aircraft_to_dict(_f35a_wetted())
    assert has_geometric_wetted_dict(d) is True
    d['nose_cone_length_m'] = 0
    assert has_geometric_wetted_dict(d) is False
    assert has_geometric_wetted_dict({}) is False


def test_csv_presets_use_geometric_wetted_and_exclude_j15():
    """CSV 作战半径机型走分段浸润；歼-15 不在列表。"""
    from utils.combat_radius.combat_radius_presets import get_preset_by_id, load_presets, preset_to_aircraft

    presets = load_presets()
    assert get_preset_by_id(presets, 'J-15') is None
    f35a = preset_to_aircraft(get_preset_by_id(presets, 'F-35A'))
    assert has_geometric_wetted(f35a) is True
    assert fuse_wetted_factor(f35a) == pytest.approx(1.0)
    f35c = preset_to_aircraft(get_preset_by_id(presets, 'F-35C'))
    assert fuse_wetted_factor(f35c) < fuse_wetted_factor(f35a)
    j20 = preset_to_aircraft(get_preset_by_id(presets, 'J-20'))
    assert j20.ventral_fin_area_m2 == pytest.approx(6.38)
    assert j20.vtail_area_m2 == pytest.approx(9.07 * 2)
    f22 = preset_to_aircraft(get_preset_by_id(presets, 'F-22'))
    assert f22.vtail_area_m2 == pytest.approx(9.94 * 2)


def test_fuse_body_area_factor_clamps_and_defaults():
    """截面积比钳位；缺截面为 1；参考截面为 1。"""
    assert fuse_body_area_factor(_f22()) == pytest.approx(1.0)
    ref = Aircraft(**{
        **aircraft_to_dict(_f35c()),
        'fuse_width_m': FUSE_REF_WIDTH_M, 'fuse_height_m': FUSE_REF_HEIGHT_M,
    })
    assert fuse_body_area_factor(ref) == pytest.approx(1.0)
    uav = Aircraft(**{**aircraft_to_dict(_f22()), 'fuse_width_m': 2.71, 'fuse_height_m': 1.29})
    assert fuse_body_area_factor(uav) == pytest.approx(FUSE_BODY_AREA_MIN)
    j36 = Aircraft(**{**aircraft_to_dict(_f22()), 'fuse_width_m': 4.7, 'fuse_height_m': 2.3})
    raw = (4.7 * 2.3) / (FUSE_REF_WIDTH_M * FUSE_REF_HEIGHT_M)
    assert raw > FUSE_BODY_AREA_MAX
    assert fuse_body_area_factor(j36) == pytest.approx(FUSE_BODY_AREA_MAX)
    mid = Aircraft(**{**aircraft_to_dict(_f22()), 'fuse_width_m': 3.21, 'fuse_height_m': 1.53})
    expected = (3.21 * 1.53) / (FUSE_REF_WIDTH_M * FUSE_REF_HEIGHT_M)
    assert FUSE_BODY_AREA_MIN < expected < FUSE_BODY_AREA_MAX
    assert fuse_body_area_factor(mid) == pytest.approx(expected)


def test_wetted_area_factor_scales_with_fuse_section():
    """机身截面只乘浸润份额，不改变其它开关。"""
    base = _f22()
    slim = Aircraft(**{**aircraft_to_dict(base), 'fuse_width_m': 2.71, 'fuse_height_m': 1.29})
    assert wetted_area_factor(slim) == pytest.approx(
        wetted_area_factor(base) * fuse_wetted_factor(slim),
    )


def test_cd_wave_transonic_scales_with_fuse_area():
    """跨声速鼓包按截面积比缩放；亚音速仍为零。"""
    base = _f22()
    slim = Aircraft(**{**aircraft_to_dict(base), 'fuse_width_m': 2.71, 'fuse_height_m': 1.29})
    cl = cl_cruise(base)
    assert cd_wave_transonic(0.8, cl, slim) == 0.0
    peak_base = cd_wave_transonic(CDW_TRANS_PEAK, cl, base)
    peak_slim = cd_wave_transonic(CDW_TRANS_PEAK, cl, slim)
    assert peak_slim == pytest.approx(peak_base * fuse_body_area_factor(slim))


def test_cd_wave_supersonic_scales_body_not_lift():
    """超音速机身体积项乘截面；升力波阻不乘。"""
    base = Aircraft(**{**aircraft_to_dict(_f22()), 'mach': 1.5})
    slim = Aircraft(**{**aircraft_to_dict(base), 'fuse_width_m': 2.71, 'fuse_height_m': 1.29})
    scale = fuse_body_area_factor(slim)
    body_base = cd_wave_supersonic(1.5, base, 0.0)
    body_slim = cd_wave_supersonic(1.5, slim, 0.0)
    dm = 0.5
    cdw_wing = body_base - CDW_SS_BODY * dm ** 2
    assert body_slim == pytest.approx(CDW_SS_BODY * dm ** 2 * scale + cdw_wing)
    d_lift_base = cd_wave_supersonic(1.5, base, 0.30) - cd_wave_supersonic(1.5, base, 0.0)
    d_lift_slim = cd_wave_supersonic(1.5, slim, 0.30) - cd_wave_supersonic(1.5, slim, 0.0)
    assert d_lift_slim == pytest.approx(d_lift_base)
    # 超巡带后附加体积项不乘截面
    dm_hi = F22_MAX_SPEED_MACH - 1.0
    hi_base = cd_wave_supersonic(F22_MAX_SPEED_MACH, base, 0.0)
    hi_slim = cd_wave_supersonic(F22_MAX_SPEED_MACH, slim, 0.0)
    assert hi_slim == pytest.approx(hi_base + CDW_SS_BODY * dm_hi ** 2 * (scale - 1.0))


def test_cd_wave_ss_rough_body_scales_with_fuse_area():
    """rough 机身体积附加随截面缩放；厚翼项不乘。"""
    base = Aircraft(**{**aircraft_to_dict(_f35c()), 'mach': 1.6})
    slim = Aircraft(**{**aircraft_to_dict(base), 'fuse_width_m': 2.71, 'fuse_height_m': 1.29})
    scale = fuse_body_area_factor(slim)
    dm = 0.6
    d_base = cd_wave_ss_rough(1.6, base, 0.0)
    d_slim = cd_wave_ss_rough(1.6, slim, 0.0)
    wing_term = d_base - CDW_SS_ROUGH_BODY * dm ** 2
    assert d_slim == pytest.approx(CDW_SS_ROUGH_BODY * dm ** 2 * scale + wing_term)


def test_cd_wave_zero_at_cruise_mach():
    ac = _f35c()
    cl = cl_cruise(ac)
    assert cd_wave(cl, ac) == 0.0


def test_cd_wave_positive_when_mach_exceeds_mdd():
    ac = Aircraft(**{**aircraft_to_dict(_f35c()), 'mach': 1.4})
    cl = cl_cruise(ac)
    assert cd_wave(cl, ac) > 0


def test_drag_divergence_mach_above_cruise():
    """F-22 超临界翼 Mdd 应高于 Ma 0.8，亚音速巡航无 Korn 波阻。"""
    ac = _f22()
    mdd = drag_divergence_mach(cl_cruise(ac), ac)
    assert mdd > ac.mach
    assert cd_wave_korn(cl_cruise(ac), ac) == 0.0


def test_korn_wave_drag_is_capped():
    """Korn 超量封顶后，Ma 1.76 的跨声速项应远小于未封顶的 (M-Mdd)⁴。"""
    ac = Aircraft(**{**aircraft_to_dict(_f22()), 'mach': 1.76, 'alt_m': 11000})
    cl = cl_cruise(ac)
    capped = cd_wave_korn(cl, ac)
    assert capped == pytest.approx(CDW_KORN_COEF * KORN_DM_CAP ** 4)
    uncapped = CDW_KORN_COEF * (1.76 - drag_divergence_mach(cl, ac)) ** 4
    assert capped < 0.01
    assert uncapped > 1.0


def test_cd_wave_supersonic_zero_at_or_below_sonic():
    ac = _f22()
    assert cd_wave_supersonic(0.8, ac) == 0.0
    assert cd_wave_supersonic(1.0, ac) == 0.0
    assert cd_wave_supersonic(1.5, ac) > 0.0


def test_transonic_gaussian_zero_below_onset_and_peaks_at_108():
    """鼓包在机身起点以下为零，峰值 1.08，Ma 1.5 已衰减，Ma 0.8 不受影响。"""
    assert transonic_gaussian(0.8) == 0.0
    assert transonic_gaussian(TRANSONIC_ONSET) == 0.0
    with pytest.raises(ValueError, match='马赫数'):
        transonic_gaussian(0.0)
    assert transonic_gaussian(CDW_TRANS_PEAK) == pytest.approx(1.0)
    assert transonic_gaussian(1.0) > transonic_gaussian(1.35)
    assert transonic_gaussian(1.2) > transonic_gaussian(1.35)
    assert transonic_gaussian(1.5) < 0.15
    assert CDW_TRANS_WIDTH_LO < CDW_TRANS_WIDTH


def test_cd_wave_transonic_zero_below_onset_and_peaks_near_108():
    """鼓包不跟 Korn Mdd；Ma 1.08 附近高于 Ma 1.5，且 Ma 0.8 标定不受影响。"""
    ac = _f22()
    cl = cl_cruise(ac)
    assert cd_wave_transonic(0.8, cl, ac) == 0.0
    with pytest.raises(ValueError, match='马赫数'):
        cd_wave_transonic(0.0, cl, ac)
    peak = cd_wave_transonic(CDW_TRANS_PEAK, cl, Aircraft(**{**aircraft_to_dict(ac), 'mach': CDW_TRANS_PEAK}))
    at15 = cd_wave_transonic(1.5, cl, Aircraft(**{**aircraft_to_dict(ac), 'mach': 1.5}))
    at176 = cd_wave_transonic(1.76, cl, Aircraft(**{**aircraft_to_dict(ac), 'mach': 1.76}))
    assert peak == pytest.approx(CDW_TRANS_AMP)
    assert peak > at15 > at176
    assert at15 < 0.4 * CDW_TRANS_AMP


def test_cd_wave_transonic_on_at_mach_1_even_if_mdd_above_one():
    """大后掠 Korn Mdd>1 时，Ma 1 仍须有机身跨声速鼓包，否则半径会倒挂。"""
    ac = Aircraft(**{**aircraft_to_dict(_f22()), 'mach': 1.0, 'alt_m': 12000})
    cl = cl_cruise(ac)
    mdd = drag_divergence_mach(cl, ac)
    assert mdd > 1.0
    bump = cd_wave_transonic(1.0, cl, ac)
    assert bump > 0.01
    assert cd_wave(cl, ac) >= bump


def test_cd_wave_supersonic_falls_with_sweep_and_rises_with_thickness():
    """后掠越大前缘法向马赫越低；厚翼超音速波阻更大。"""
    base = Aircraft(**{**aircraft_to_dict(_f22()), 'mach': 1.76, 'sweep_deg': 30.0, 'tc': 0.05})
    swept = Aircraft(**{**aircraft_to_dict(base), 'sweep_deg': 55.0})
    thick = Aircraft(**{**aircraft_to_dict(base), 'tc': 0.08})
    assert cd_wave_supersonic(1.76, swept) < cd_wave_supersonic(1.76, base)
    assert cd_wave_supersonic(1.76, thick) > cd_wave_supersonic(1.76, base)
    assert CDW_SS_BODY > 0 and CDW_SS_WING > 0


def test_cd_wave_ss_rough_zero_when_smooth_or_subsonic():
    """光滑机或亚音速时 rough 超音速附加应为 0。"""
    f22 = Aircraft(**{**aircraft_to_dict(_f22()), 'mach': 1.6})
    f35 = Aircraft(**{**aircraft_to_dict(_f35c()), 'mach': 0.8})
    assert cd_wave_ss_rough(1.6, f22, 0.10) == 0.0
    assert cd_wave_ss_rough(0.8, f35, 0.20) == 0.0
    assert cd_wave_ss_rough(1.0, f35, 0.20) == 0.0
    assert cd_wave_ss_rough_wing_at(0.9, 30.9, 0.051) == 0.0


def test_cd_wave_ss_rough_wing_rises_with_thickness_and_normal_tc():
    """厚翼体积项随 t/c 与法向厚弦比上升；Ma 1.6 即有、不要求前缘超音速。"""
    thin = cd_wave_ss_rough_wing_at(1.6, 33.7, 0.04)
    thick = cd_wave_ss_rough_wing_at(1.6, 33.7, 0.06)
    more_sweep = cd_wave_ss_rough_wing_at(1.6, 50.0, 0.06)
    assert thick > thin > 0.0
    assert more_sweep > thick
    expect = CDW_SS_ROUGH_WING * (0.06 / math.cos(math.radians(33.7))) ** 2 * 0.6 ** 2
    assert thick == pytest.approx(expect)
    assert CDW_SS_ROUGH_BODY > 0 and CDW_SS_ROUGH_WING > 0 and CDW_SS_ROUGH_LIFT >= 0


def test_cd_wave_ss_rough_adds_body_wing_and_lift():
    """F-35 在 Ma 1.6 的 rough 附加 = 机身 + 厚翼 + 升力三项之和。"""
    ac = Aircraft(**{**aircraft_to_dict(_f35c()), 'mach': 1.6, 'alt_m': 11000})
    cl = 0.08
    got = cd_wave_ss_rough(1.6, ac, cl)
    body = CDW_SS_ROUGH_BODY * 0.6 ** 2
    wing = cd_wave_ss_rough_wing_at(1.6, ac.sweep_deg, ac.tc)
    lift = CDW_SS_ROUGH_LIFT * cl ** 2 * 0.6
    assert got == pytest.approx(body + wing + lift)
    assert got > cd_wave_ss_rough(1.6, ac, 0.0)


def test_rough_raises_f35_supersonic_cdw_not_f22():
    """Ma 1.6 时 F-35 波阻须明显高于关掉 rough 的孪生几何；F-22 不受该项。"""
    f35 = Aircraft(**{**aircraft_to_dict(_f35c()), 'mach': 1.6, 'alt_m': 11000})
    smooth = Aircraft(**{**aircraft_to_dict(f35), 'rough': False})
    f22 = Aircraft(**{**aircraft_to_dict(_f22()), 'mach': 1.6, 'alt_m': 11000})
    cl35 = cl_cruise(f35)
    cl22 = cl_cruise(f22)
    assert cd_wave_supersonic(1.6, f35, cl35) > cd_wave_supersonic(1.6, smooth, cl35)
    assert cd_wave_ss_rough(1.6, f35, cl35) == pytest.approx(
        cd_wave_supersonic(1.6, f35, cl35) - cd_wave_supersonic(1.6, smooth, cl35),
    )
    assert cd_wave_ss_rough(1.6, f22, cl22) == 0.0
    # 亚音速巡航点不受超音速 rough 项影响
    assert cd_wave(cl_cruise(_f35c()), _f35c()) == 0.0


def test_supersonic_total_cdw_is_order_one_hundredth():
    """F-22 超巡点总波阻应为百分位量级，不能再出现 CDw>1。"""
    ac = Aircraft(**{
        **aircraft_to_dict(_f22()), 'mach': F22_SUPERCRUISE_MACH,
        'alt_m': 11000, 'mach_angle_deg': 28.5,
    })
    cdw = cd_wave(cl_cruise(ac), ac)
    assert 0.005 < cdw < 0.02


def test_cd_wave_supersonic_rises_with_cl():
    """升力波阻随 CL 增大，高空超音速 L/D 会被压下来。"""
    ac = Aircraft(**{**aircraft_to_dict(_f22()), 'mach': 1.5})
    low = cd_wave_supersonic(1.5, ac, 0.08)
    high = cd_wave_supersonic(1.5, ac, 0.30)
    assert high > low
    assert CDW_SS_LIFT > 0
    assert high - low == pytest.approx(CDW_SS_LIFT * (0.30 ** 2 - 0.08 ** 2) * 0.5)


def test_lift_wave_mach_factor_caps_after_ma15():
    """刚超音速按 (M-1)；超巡带封顶，过了 1.76 再加重。"""
    from utils.combat_radius.lift_drag import CDW_SS_LIFT_POST, SUPERCRUISE_BAND_HI

    assert lift_wave_mach_factor(0.8) == 0.0
    assert lift_wave_mach_factor(1.0) == 0.0
    assert lift_wave_mach_factor(1.25) == pytest.approx(0.25)
    assert lift_wave_mach_factor(1.5) == pytest.approx(CDW_SS_LIFT_MACH_CAP)
    assert lift_wave_mach_factor(1.76) == pytest.approx(CDW_SS_LIFT_MACH_CAP)
    assert lift_wave_mach_factor(2.0) == pytest.approx(
        CDW_SS_LIFT_MACH_CAP + CDW_SS_LIFT_POST * (2.0 - SUPERCRUISE_BAND_HI),
    )
    assert CDW_SS_LIFT_MACH_CAP == pytest.approx(0.50)
    assert SUPERCRUISE_BAND_HI == pytest.approx(1.76)
    assert F22_SUPERCRUISE_MACH == pytest.approx(SUPERCRUISE_BAND_HI)


def test_lift_wave_drag_same_at_ma176_as_ma15():
    """同一 CL 下，Ma 1.76 的升力波阻应与 Ma 1.5 相同（体积项仍随马赫上升）。"""
    ac = _f22()
    cl = 0.20
    lift15 = cd_wave_supersonic(1.5, ac, cl) - cd_wave_supersonic(1.5, ac, 0.0)
    lift176 = cd_wave_supersonic(1.76, ac, cl) - cd_wave_supersonic(1.76, ac, 0.0)
    vol15 = cd_wave_supersonic(1.5, ac, 0.0)
    vol176 = cd_wave_supersonic(1.76, ac, 0.0)
    assert lift176 == pytest.approx(lift15)
    assert vol176 > vol15
    lift20 = cd_wave_supersonic(2.0, ac, cl) - cd_wave_supersonic(2.0, ac, 0.0)
    assert lift20 > lift176


def test_cd_wave_ss_body_post_zero_until_supercruise_then_rises():
    """超巡带上附加体积波阻为零；Ma 2.25 按 (M-1.76)² 上升。"""
    assert cd_wave_ss_body_post(1.0) == 0.0
    assert cd_wave_ss_body_post(SUPERCRUISE_BAND_HI) == 0.0
    assert cd_wave_ss_body_post(1.5) == 0.0
    extra = cd_wave_ss_body_post(F22_MAX_SPEED_MACH)
    dm = F22_MAX_SPEED_MACH - SUPERCRUISE_BAND_HI
    assert extra == pytest.approx(CDW_SS_BODY_POST * dm ** 2)
    assert extra > 0.0
    ac = _f22()
    vol176 = cd_wave_supersonic(SUPERCRUISE_BAND_HI, ac, 0.0)
    vol225 = cd_wave_supersonic(F22_MAX_SPEED_MACH, ac, 0.0)
    vol176_body = CDW_SS_BODY * (SUPERCRUISE_BAND_HI - 1.0) ** 2
    vol225_body = CDW_SS_BODY * (F22_MAX_SPEED_MACH - 1.0) ** 2
    # 光滑常规布局：后段体积增量 = 机身 (M-1)² 增量 + 后段项（机翼项取决于前缘）
    assert vol225 > vol176
    assert vol225 - vol176 >= (vol225_body - vol176_body) + extra - 1e-9
    assert F22_MAX_SPEED_MACH == pytest.approx(2.25)
    assert CDW_SS_BODY_POST == pytest.approx(0.038)


def test_body_post_volume_is_discounted_like_other_volume_terms():
    """后段体积波阻与机身/机翼项一样走无尾折扣。"""
    conv = Aircraft(**{**aircraft_to_dict(_f22()), 'mach': 2.25, 'layout': 'conventional'})
    tail = Aircraft(**{**aircraft_to_dict(conv), 'layout': 'tailless'})
    vol_conv = cd_wave_supersonic(2.25, conv, 0.0)
    vol_tail = cd_wave_supersonic(2.25, tail, 0.0)
    assert vol_tail == pytest.approx(vol_conv * CDW_TAILLESS)


def test_canard_adds_supersonic_wave_drag():
    """鸭翼在超音速多一项 (M-1)²，常规布局没有。"""
    conv = Aircraft(**{**aircraft_to_dict(_f22()), 'mach': 1.7, 'layout': 'conventional'})
    canard = Aircraft(**{**aircraft_to_dict(_f22()), 'mach': 1.7, 'layout': 'canard'})
    extra = cd_wave_supersonic(1.7, canard) - cd_wave_supersonic(1.7, conv)
    assert extra == pytest.approx(CDW_CANARD * 0.7 ** 2)
    assert J20_SUPERCRUISE_MACH == pytest.approx(1.67)


def test_tailless_and_bwb_discount_volume_wave_drag():
    """无尾/翼身融合只打折体积波阻，升力波阻不变。"""
    conv = Aircraft(**{**aircraft_to_dict(_f22()), 'mach': 1.5, 'layout': 'conventional', 'bwb': False})
    tail = Aircraft(**{**aircraft_to_dict(conv), 'layout': 'tailless'})
    bwb = Aircraft(**{**aircraft_to_dict(conv), 'bwb': True})
    vol_conv = cd_wave_supersonic(1.5, conv, 0.0)
    vol_tail = cd_wave_supersonic(1.5, tail, 0.0)
    vol_bwb = cd_wave_supersonic(1.5, bwb, 0.0)
    assert vol_tail == pytest.approx(vol_conv * CDW_TAILLESS)
    assert vol_bwb == pytest.approx(vol_conv * CDW_BWB)
    lift_conv = cd_wave_supersonic(1.5, conv, 0.25) - vol_conv
    lift_tail = cd_wave_supersonic(1.5, tail, 0.25) - vol_tail
    assert lift_tail == pytest.approx(lift_conv)
    assert 0.5 < CDW_TAILLESS < 1.0
    assert 0.5 < CDW_BWB < 1.0


def test_pelican_and_small_htail_discount_volume_between_tailless_and_conventional():
    """中等 Pelican / 小平尾 / 中等平尾体积波阻介于无尾与常规之间，升力波阻不变。"""
    conv = Aircraft(**{**aircraft_to_dict(_f22()), 'mach': 1.5, 'layout': 'conventional', 'bwb': False})
    pel = Aircraft(**{**aircraft_to_dict(conv), 'layout': 'pelican'})
    ht = Aircraft(**{**aircraft_to_dict(conv), 'layout': 'small_htail'})
    med = Aircraft(**{**aircraft_to_dict(conv), 'layout': 'medium_htail'})
    tail = Aircraft(**{**aircraft_to_dict(conv), 'layout': 'tailless'})
    vol_conv = cd_wave_supersonic(1.5, conv, 0.0)
    vol_pel = cd_wave_supersonic(1.5, pel, 0.0)
    vol_ht = cd_wave_supersonic(1.5, ht, 0.0)
    vol_med = cd_wave_supersonic(1.5, med, 0.0)
    vol_tail = cd_wave_supersonic(1.5, tail, 0.0)
    assert vol_pel == pytest.approx(vol_conv * CDW_PELICAN)
    assert vol_ht == pytest.approx(vol_conv * CDW_SMALL_HTAIL)
    assert vol_med == pytest.approx(vol_conv * CDW_MEDIUM_HTAIL)
    assert vol_tail < vol_pel < vol_ht < vol_med < vol_conv
    lift_conv = cd_wave_supersonic(1.5, conv, 0.25) - vol_conv
    lift_pel = cd_wave_supersonic(1.5, pel, 0.25) - vol_pel
    assert lift_pel == pytest.approx(lift_conv)
    assert LAYOUT_CDW_VOL['tailless'] == pytest.approx(CDW_TAILLESS)
    assert (
        LAYOUT_MULT['small_htail']
        < LAYOUT_MULT['pelican']
        < LAYOUT_MULT['medium_htail']
        < LAYOUT_MULT['conventional']
    )


def test_components_keys_and_signs():
    c = components(_j20())
    assert set(c) == {'CL', 'e_raw', 'K', 'W', 'F_form', 'CDw', 'CDa'}
    assert c['CL'] > 0 and c['K'] > 0 and c['W'] > 0
    assert c['CDw'] >= 0
    assert c['CDa'] >= 0


def test_cd_high_aoa_zero_near_cruise_cl_and_rises():
    """标定巡航 CL 附近附加阻力为零；再增大迎角则上升。"""
    assert cd_high_aoa(CL_AOA_ONSET) == 0.0
    assert cd_high_aoa(CL_AOA_ONSET - 0.05) == 0.0
    assert cd_high_aoa(cl_cruise(_f35c())) == 0.0
    assert cd_high_aoa(cl_cruise(_f22())) == 0.0
    assert cd_high_aoa(0.50) == pytest.approx(CD_AOA_COEF * (0.50 - CL_AOA_ONSET) ** 2)
    assert cd_high_aoa(0.58) > cd_high_aoa(0.45)
    # F-35A 11 km 巡航 CL≈0.42：只留轻惩罚，不得按大迎角把半径打到公开值以下
    assert CL_AOA_ONSET == pytest.approx(0.36)
    assert CD_AOA_COEF == pytest.approx(1.6)
    assert 0.0 < cd_high_aoa(0.42) < 0.006


def test_f22_ma08_ld_peaks_near_catalog_not_15km():
    """抛物线极曲线会把 L/Dmax 推到 15 km；大迎角项须让标定高度附近更高。"""
    cf0, k_e = calibrate_default_anchors()
    cruise = Aircraft(**{**aircraft_to_dict(_f22()), 'mach': 0.8, 'alt_m': 11800})
    high = Aircraft(**{**aircraft_to_dict(_f22()), 'mach': 0.8, 'alt_m': 15000})
    ld_c, _ = predict_ld(cruise, cf0, k_e)
    ld_h, d_h = predict_ld(high, cf0, k_e)
    assert d_h['CDa'] > 0
    assert ld_c > ld_h


def test_calibrate_reconstructs_anchor_ld():
    cf0, k_e = calibrate(_f35c(), 8.8, _f22(), 8.0)
    assert cf0 > 0 and k_e > 0
    ld1, _ = predict_ld(_f35c(), cf0, k_e)
    ld2, _ = predict_ld(_f22(), cf0, k_e)
    assert ld1 == pytest.approx(8.8, abs=1e-10)
    assert ld2 == pytest.approx(8.0, abs=1e-10)


def test_calibrate_singular_when_anchors_identical():
    ac = _f22()
    with pytest.raises(ValueError, match='奇异'):
        calibrate(ac, 8.0, ac, 8.0)


def test_calibrate_rejects_unphysical_targets():
    with pytest.raises(ValueError, match='物理无意义'):
        calibrate(_f35c(), 20.0, _f22(), 2.0)


def test_default_ld_anchors_match_f35c_f22():
    """参考机 CSV 巡航点：F-35C 升阻比仍可略高于 F-22（翼面积更大）。"""
    a1, ld1, a2, ld2 = default_ld_anchor_aircraft()
    assert a1.name == 'F-35C' and a1.rough is True and a1.inlet == 'dsi'
    assert a2.name == 'F-22' and a2.rough is False and a2.inlet == 'caret'
    assert ld2 == pytest.approx(8.64, abs=0.10)
    assert ld1 == pytest.approx(9.27, abs=0.10)
    assert ld1 > ld2
    cf0, k_e = calibrate_default_anchors()
    assert cf0 == pytest.approx(CF0_REF)
    assert k_e == pytest.approx(K_E_REF)


def test_rough_wetted_mult():
    """不平整只放大浸润摩擦；光滑机为 1。"""
    assert rough_wetted_mult(_f35c()) == pytest.approx(BUMP_FRICTION_MULT)
    assert rough_wetted_mult(_f22()) == pytest.approx(1.0)


def test_rough_form_cd0_mult():
    """不平整形状阻力只乘 CD0；光滑机为 1。"""
    assert rough_form_cd0_mult(_f35c()) == pytest.approx(BUMP_FORM_MULT)
    assert rough_form_cd0_mult(_f22()) == pytest.approx(1.0)


def test_rough_mult_penalizes_f35_vs_smooth():
    """几何浸润已含肥胖；rough 只留很轻的摩擦/形状 BUMP>1，浸润高于光滑对照。"""
    assert BUMP_FRICTION_MULT == pytest.approx(1.006, abs=0.0005)
    assert BUMP_FORM_MULT == pytest.approx(1.001, abs=0.0005)
    assert BUMP_MULT == pytest.approx(BUMP_FRICTION_MULT)
    assert BUMP_FRICTION_MULT > 1.0
    assert BUMP_FORM_MULT > 1.0
    smooth = Aircraft(**{**aircraft_to_dict(_f35c()), 'rough': False})
    assert wetted_area_factor(_f35c()) == pytest.approx(
        wetted_area_factor(smooth) * BUMP_FRICTION_MULT,
    )


def test_parasite_cd0_and_estimate_takeoff_cd0():
    """起飞 CD0 应由浸润因子、形状阻力乘数与默认锚点 Cf0 给出。"""
    ac = _f35c()
    cf0, _k_e = calibrate_default_anchors()
    cd0 = parasite_cd0(ac, cf0)
    assert cd0 == pytest.approx(
        cf0 * wetted_area_factor(ac) * rough_form_cd0_mult(ac),
    )
    smooth = Aircraft(**{**aircraft_to_dict(ac), 'rough': False})
    assert parasite_cd0(ac, cf0) == pytest.approx(
        parasite_cd0(smooth, cf0) * BUMP_FRICTION_MULT * BUMP_FORM_MULT,
    )
    assert 0.01 < estimate_takeoff_cd0(ac) < 0.08
    with pytest.raises(ValueError, match='Cf0'):
        parasite_cd0(ac, 0.0)


def test_predict_ld_j20_between_anchors():
    cf0, k_e = calibrate(_f35c(), 8.8, _f22(), 8.0)
    ld, d = predict_ld(_j20(), cf0, k_e)
    assert 7.0 < ld < 10.0
    assert d['CD'] == pytest.approx(d['CD0'] + d['CDi'] + d['CDw'] + d['CDa'] + d['CDs'])
    assert KAPPA_A == pytest.approx(0.90)


def test_lambda_uav_ma15_cl_below_j50_ld_above_without_canopy():
    """同为兰姆达无尾时，53636 翼载更低 → Ma 1.5 的 CL 更小。

    歼-50 机身更细更短后 CD0 低于无人机；无座舱相对有座舱仍降低阻力。
    53636 为加莱特、歼-50 为 DSI，进气道不是主因。
    """
    from utils.combat_radius.combat_radius_presets import get_preset_by_id, load_presets, preset_to_aircraft

    presets = load_presets()
    uav = preset_to_aircraft(get_preset_by_id(presets, '53636'))
    j50 = preset_to_aircraft(get_preset_by_id(presets, 'J-50'))
    assert uav.planform == j50.planform == 'lambda'
    assert uav.layout == j50.layout == 'tailless'
    assert uav.rough is False and j50.rough is False
    assert uav.inlet == 'caret' and j50.inlet == 'dsi'
    assert uav.canopy is False and j50.canopy is True
    assert uav.wing_loading < j50.wing_loading
    cf0, k_e = calibrate_default_anchors()
    uav_m = Aircraft(**{**aircraft_to_dict(uav), 'mach': 1.5, 'alt_m': 11000})
    j50_m = Aircraft(**{**aircraft_to_dict(j50), 'mach': 1.5, 'alt_m': 11000})
    ld_u, d_u = predict_ld(uav_m, cf0, k_e)
    ld_j, d_j = predict_ld(j50_m, cf0, k_e)
    assert d_u['CL'] < d_j['CL']
    assert d_j['CD0'] < d_u['CD0']
    dsi_twin = Aircraft(**{**aircraft_to_dict(uav_m), 'inlet': 'dsi'})
    _, d_dsi = predict_ld(dsi_twin, cf0, k_e)
    assert d_u['CD0'] > d_dsi['CD0']
    manned = Aircraft(**{**aircraft_to_dict(uav_m), 'canopy': True})
    ld_manned, _ = predict_ld(manned, cf0, k_e)
    assert ld_u > ld_manned


def _j36_double_delta() -> Aircraft:
    """歼-36：双三角内段 67.8°、外段 55.3°。"""
    return Aircraft(
        'J-36', AR=2.49, sweep_deg=65.1, wing_loading=0.277,
        tc=0.043, mach=0.8, alt_m=12000,
        planform='double_delta', layout='tailless',
        bwb=True, rough=False,
        sweep_inner_deg=67.8, sweep_outer_deg=55.3,
        length_m=18.9, wingspan_m=19.24, mach_angle_deg=27.7,
    )


def test_has_double_delta_sweep_requires_planform_and_both_panels():
    ac = _j36_double_delta()
    assert has_double_delta_sweep(ac) is True
    no_inner = Aircraft(**{**aircraft_to_dict(ac), 'sweep_inner_deg': 0})
    no_outer = Aircraft(**{**aircraft_to_dict(ac), 'sweep_outer_deg': 0})
    trap = Aircraft(**{**aircraft_to_dict(ac), 'planform': 'trapezoidal'})
    assert has_double_delta_sweep(no_inner) is False
    assert has_double_delta_sweep(no_outer) is False
    assert has_double_delta_sweep(trap) is False
    assert has_double_delta_sweep(_f22()) is False


def test_double_delta_kink_span_frac_solves_from_ar_or_uses_given():
    """歼-36 展弦比与两段后掠应解出约 0.40 的折点；显式值优先。"""
    eta = double_delta_kink_span_frac(67.8, 55.3, 2.49)
    assert 0.35 < eta < 0.45
    assert double_delta_kink_span_frac(67.8, 55.3, 2.49, 0.55) == pytest.approx(0.55)
    from utils.combat_radius.lift_drag import DOUBLE_DELTA_KINK_DEFAULT
    assert double_delta_kink_span_frac(67.8, 55.3, 0.5) == pytest.approx(DOUBLE_DELTA_KINK_DEFAULT)
    assert double_delta_kink_span_frac(50.0, 50.0, 2.5) == pytest.approx(DOUBLE_DELTA_KINK_DEFAULT)


def test_double_delta_area_weights_inner_dominates_for_j36():
    eta = double_delta_kink_span_frac(67.8, 55.3, 2.49)
    w_in, w_out = double_delta_area_weights(67.8, 55.3, eta)
    assert w_in + w_out == pytest.approx(1.0)
    assert w_in > w_out
    assert 0.60 < w_in < 0.75
    with pytest.raises(ValueError, match='折点'):
        double_delta_area_weights(67.8, 55.3, 0.0)


def test_double_delta_panels_and_oswald_sweep():
    ac = _j36_double_delta()
    inner, outer, w_in, w_out = double_delta_panels(ac)
    assert inner == pytest.approx(67.8)
    assert outer == pytest.approx(55.3)
    assert w_in + w_out == pytest.approx(1.0)
    eq = oswald_sweep_deg(ac)
    assert eq == pytest.approx(w_in * 67.8 + w_out * 55.3)
    assert 60.0 < eq < 66.0
    assert oswald_sweep_deg(_f22()) == pytest.approx(41.3)
    single = Aircraft(**{**aircraft_to_dict(ac), 'sweep_inner_deg': 0, 'sweep_outer_deg': 0})
    with pytest.raises(ValueError, match='内段与外段'):
        double_delta_panels(single)


def test_blend_sweep_quantity_and_oswald_e_for_aircraft():
    ac = _j36_double_delta()
    assert blend_sweep_quantity(_f22(), lambda s: s) == pytest.approx(41.3)
    e_blend = oswald_e_for_aircraft(ac)
    inner, outer, w_in, w_out = double_delta_panels(ac)
    expect = w_in * oswald_e_raw(ac.AR, inner) + w_out * oswald_e_raw(ac.AR, outer)
    assert e_blend == pytest.approx(expect)
    assert e_blend != pytest.approx(oswald_e_raw(ac.AR, ac.sweep_deg))


def test_drag_divergence_and_korn_helpers_match_single_panel():
    ac = _f22()
    cl = cl_cruise(ac)
    assert drag_divergence_mach_at(cl, ac.sweep_deg, ac.tc) == pytest.approx(
        drag_divergence_mach(cl, ac),
    )
    assert cd_wave_korn_at(ac.mach, cl, ac.sweep_deg, ac.tc) == pytest.approx(
        cd_wave_korn(cl, ac),
    )
    assert cd_wave_transonic_at(0.8, cl, ac.sweep_deg, ac.tc) == 0.0
    assert cd_wave_transonic_at(1.0, cl, ac.sweep_deg, ac.tc) > 0.0


def test_j36_two_segment_outer_panel_starts_le_wave_earlier():
    """外段 55.3° 约 Ma 1.76 即超音速前缘；单段 65.1° 要到约 Ma 2.38。"""
    two = Aircraft(**{**aircraft_to_dict(_j36_double_delta()), 'mach': 1.90, 'alt_m': 11000})
    one = Aircraft(**{
        **aircraft_to_dict(two),
        'sweep_inner_deg': 0, 'sweep_outer_deg': 0, 'sweep_deg': 65.1,
    })
    assert cd_wave_ss_wing_at(1.90, 55.3, two.tc) > 0.0
    assert cd_wave_ss_wing_at(1.90, 67.8, two.tc) == 0.0
    assert cd_wave_ss_wing_at(1.90, 65.1, two.tc) == 0.0
    assert cd_wave_supersonic(1.90, two, 0.0) > cd_wave_supersonic(1.90, one, 0.0)
    assert cd_wave(cl_cruise(two), two) > cd_wave(cl_cruise(one), one)


def test_aircraft_from_dict_reads_double_delta_sweeps():
    ac = aircraft_from_dict({
        'name': '歼-36', 'AR': 2.49, 'sweep_deg': 65.1, 'wing_loading': 0.277,
        'tc': 0.043, 'mach': 0.8, 'alt_m': 12000,
        'planform': 'double_delta', 'layout': 'tailless', 'bwb': 1, 'rough': 0,
        'sweep_inner_deg': 67.8, 'sweep_outer_deg': 55.3,
    })
    assert ac.sweep_inner_deg == pytest.approx(67.8)
    assert ac.sweep_outer_deg == pytest.approx(55.3)
    d = aircraft_to_dict(ac)
    assert d['sweep_inner_deg'] == pytest.approx(67.8)
    again = aircraft_from_dict(d)
    assert again.sweep_outer_deg == pytest.approx(55.3)


def test_parse_store_mount_aliases_and_default():
    """空值视为内埋；半埋/挂架中英文别名归一。"""
    assert parse_store_mount(None) == 'internal'
    assert parse_store_mount('') == 'internal'
    assert parse_store_mount('弹舱') == 'internal'
    assert parse_store_mount('semi-recessed') == 'semi_recessed'
    assert parse_store_mount('半埋入') == 'semi_recessed'
    assert parse_store_mount('外挂') == 'pylon'
    with pytest.raises(ValueError, match='未知挂装方式'):
        parse_store_mount('wingtip')


def test_n_stores_from_dict_blank_and_rejects_negative():
    """挂弹数空值为 0，负数非法。"""
    assert _n_stores_from_dict(None) == 0.0
    assert _n_stores_from_dict('') == 0.0
    assert _n_stores_from_dict('4') == pytest.approx(4.0)
    with pytest.raises(ValueError, match='不能为负'):
        _n_stores_from_dict(-1)


def test_store_one_wetted_and_front_area():
    """内埋无外露面积；挂架浸润与迎风大于半埋。"""
    assert store_one_wetted_m2('internal') == pytest.approx(0.0)
    assert store_one_front_m2('internal') == pytest.approx(0.0)
    assert store_one_wetted_m2('pylon') > store_one_wetted_m2('semi_recessed') > 0
    assert store_one_front_m2('pylon') > store_one_front_m2('semi_recessed') > 0
    with pytest.raises(ValueError, match='未知挂装方式'):
        store_one_wetted_m2('wingtip')
    with pytest.raises(ValueError, match='未知挂装方式'):
        store_one_front_m2('wingtip')


def _typhoon_store_ac(**over) -> Aircraft:
    """台风量级参考面积，便于外挂阻力单测。"""
    base = dict(
        name='台风', AR=2.34, sweep_deg=53.0, wing_loading=0.276,
        tc=0.05, mach=0.8, alt_m=12000,
        planform='delta', layout='canard',
        bwb=False, rough=False, inlet='caret',
        wing_area_m2=51.2, store_mount='semi_recessed', n_stores=4.0,
    )
    base.update(over)
    return Aircraft(**base)


def test_cd_store_zero_when_internal_or_empty():
    """内埋或零枚弹不增加阻力；缺参考面积也无法无量纲化。"""
    loaded = _typhoon_store_ac()
    assert cd_store(Aircraft(**{**aircraft_to_dict(loaded), 'store_mount': 'internal'})) == 0.0
    assert cd_store(Aircraft(**{**aircraft_to_dict(loaded), 'n_stores': 0})) == 0.0
    assert cd_store(Aircraft(**{**aircraft_to_dict(loaded), 'wing_area_m2': 0})) == 0.0
    assert cd_store_parasite(loaded) > 0
    assert cd_store_wave(loaded) == pytest.approx(0.0)  # Ma 0.8 低于跨声速起点


def test_cd_store_wave_rises_supersonic_and_pylon_exceeds_semi():
    """半埋四弹超音速波阻为正；同几何挂架大于半埋。"""
    semi = _typhoon_store_ac(mach=1.5)
    pylon = Aircraft(**{**aircraft_to_dict(semi), 'store_mount': 'pylon'})
    assert cd_store_wave(semi) > cd_store_parasite(semi)
    assert cd_store(pylon) > cd_store(semi)
    sub = _typhoon_store_ac(mach=0.8)
    assert cd_store(semi) > cd_store(sub)
    with pytest.raises(ValueError, match='马赫数须为正'):
        cd_store_wave(_typhoon_store_ac(mach=0.0))


def test_predict_ld_adds_store_drag_without_changing_takeoff_cd0():
    """巡航 L/D 计入外挂；起飞 CD0 仍只看机体。"""
    clean = _typhoon_store_ac(n_stores=0.0)
    loaded = _typhoon_store_ac(n_stores=4.0, mach=1.5)
    clean_ss = Aircraft(**{**aircraft_to_dict(clean), 'mach': 1.5})
    cf0, k_e = calibrate_default_anchors()
    ld_c, d_c = predict_ld(clean_ss, cf0, k_e)
    ld_l, d_l = predict_ld(loaded, cf0, k_e)
    assert d_l['CDs'] > 0
    assert d_c['CDs'] == pytest.approx(0.0)
    assert d_l['CD'] > d_c['CD']
    assert ld_l < ld_c
    assert estimate_takeoff_cd0(loaded) == pytest.approx(estimate_takeoff_cd0(clean))


def test_aircraft_from_dict_reads_store_fields():
    """表单/CSV 的挂装与枚数进入 Aircraft。"""
    ac = aircraft_from_dict({
        'name': '台风', 'AR': 2.34, 'sweep_deg': 53, 'wing_loading': 0.276,
        'tc': 0.05, 'mach': 0.8, 'alt_m': 12000,
        'planform': 'delta', 'layout': 'canard', 'bwb': 0, 'rough': 0,
        'wing_area_m2': 51.2, 'store_mount': '半埋', 'n_stores': 4,
    })
    assert ac.store_mount == 'semi_recessed'
    assert ac.n_stores == pytest.approx(4.0)
    with pytest.raises(ValueError, match='不能为负'):
        aircraft_from_dict({
            'name': 'x', 'AR': 2, 'sweep_deg': 30, 'wing_loading': 0.3,
            'tc': 0.05, 'mach': 0.8, 'alt_m': 12000,
            'planform': 'trapezoidal', 'layout': 'conventional',
            'n_stores': -1,
        })
