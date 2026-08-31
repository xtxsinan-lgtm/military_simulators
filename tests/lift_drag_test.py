"""巡航升阻比估算单元测试。"""
from __future__ import annotations

import math

import pytest

from utils.combat_radius.lift_drag import (
    CDW_BWB,
    CDW_CANARD,
    CDW_KORN_COEF,
    CDW_SS_BODY,
    CDW_SS_LIFT,
    CDW_SS_WING,
    CDW_TAILLESS,
    CDW_TRANS_AMP,
    CDW_TRANS_PEAK,
    CD_AOA_COEF,
    CL_AOA_ONSET,
    CF0_REF,
    F22_SUPERCRUISE_MACH,
    J20_SUPERCRUISE_MACH,
    J35A_SUPERCRUISE_MACH,
    J35_SUPERCRUISE_MACH,
    KAPPA_A,
    KORN_DM_CAP,
    K_E_REF,
    NO_CANOPY_MULT,
    ROUGH_MULT,
    RHO11,
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
    wetted_area_factor,
    cd_wave_korn_at,
    cd_wave_ss_wing_at,
    cd_wave_transonic_at,
    _as_bool,
    _canopy_from_dict,
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
    again = aircraft_from_dict(d)
    assert again.AR == pytest.approx(2.32)
    assert again.length_m == pytest.approx(0.0)
    assert again.wingspan_m == pytest.approx(0.0)


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
    assert wetted_area_factor(rough) == pytest.approx(w0 * ROUGH_MULT)
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
    assert wetted_area_factor(delta) < w_trap
    assert wetted_area_factor(diamond) < wetted_area_factor(delta)
    assert wetted_area_factor(lam) == pytest.approx(wetted_area_factor(diamond))
    assert wetted_area_factor(delta) < wetted_area_factor(double_delta) < w_trap
    assert wetted_area_factor(swept) < w_trap
    assert wetted_area_factor(unswept) > w_trap
    assert wetted_area_factor(canard) > w_trap
    assert wetted_area_factor(tailless) < w_trap


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


def test_cd_wave_transonic_zero_below_mdd_and_peaks_near_115():
    """鼓包在 Mdd 以下为零，Ma 1.15 附近高于 Ma 1.5，且 Ma 0.8 标定不受影响。"""
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


def test_cd_wave_supersonic_falls_with_sweep_and_rises_with_thickness():
    """后掠越大前缘法向马赫越低；厚翼超音速波阻更大。"""
    base = Aircraft(**{**aircraft_to_dict(_f22()), 'mach': 1.76, 'sweep_deg': 30.0, 'tc': 0.05})
    swept = Aircraft(**{**aircraft_to_dict(base), 'sweep_deg': 55.0})
    thick = Aircraft(**{**aircraft_to_dict(base), 'tc': 0.08})
    assert cd_wave_supersonic(1.76, swept) < cd_wave_supersonic(1.76, base)
    assert cd_wave_supersonic(1.76, thick) > cd_wave_supersonic(1.76, base)
    assert CDW_SS_BODY > 0 and CDW_SS_WING > 0


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


def test_canard_adds_supersonic_wave_drag():
    """鸭翼在超音速多一项 (M-1)²，常规布局没有。"""
    conv = Aircraft(**{**aircraft_to_dict(_f22()), 'mach': 1.7, 'layout': 'conventional'})
    canard = Aircraft(**{**aircraft_to_dict(_f22()), 'mach': 1.7, 'layout': 'canard'})
    extra = cd_wave_supersonic(1.7, canard) - cd_wave_supersonic(1.7, conv)
    assert extra == pytest.approx(CDW_CANARD * 0.7 ** 2)
    assert J20_SUPERCRUISE_MACH == pytest.approx(1.71)


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


def test_components_keys_and_signs():
    c = components(_j20())
    assert set(c) == {'CL', 'e_raw', 'K', 'W', 'CDw', 'CDa'}
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
    """参考机：光滑 F-22 的 L/D 应高于 rough 惩罚后的 F-35C；系数取统一模型。"""
    a1, ld1, a2, ld2 = default_ld_anchor_aircraft()
    assert a1.name == 'F-35C' and a1.rough is True
    assert a2.name == 'F-22' and a2.rough is False
    assert ld2 > ld1
    assert ld2 == pytest.approx(11.11, abs=0.05)
    assert ld1 < 10.0  # rough≈1.33 相对光滑 F-22 再降一截
    cf0, k_e = calibrate_default_anchors()
    assert cf0 == pytest.approx(CF0_REF)
    assert k_e == pytest.approx(K_E_REF)


def test_rough_mult_penalizes_f35_vs_smooth():
    """F-35 系列 rough 乘数须明显高于 1，相对光滑机抬高浸润。"""
    assert ROUGH_MULT == pytest.approx(1.328, abs=0.01)
    assert wetted_area_factor(_f35c()) > wetted_area_factor(
        Aircraft(**{**aircraft_to_dict(_f35c()), 'rough': False}),
    )


def test_parasite_cd0_and_estimate_takeoff_cd0():
    """起飞 CD0 应由浸润因子与默认锚点 Cf0 给出，且为正的小量。"""
    ac = _f35c()
    cf0, _k_e = calibrate_default_anchors()
    cd0 = parasite_cd0(ac, cf0)
    assert cd0 == pytest.approx(cf0 * wetted_area_factor(ac))
    assert 0.01 < estimate_takeoff_cd0(ac) < 0.08
    with pytest.raises(ValueError, match='Cf0'):
        parasite_cd0(ac, 0.0)


def test_predict_ld_j20_between_anchors():
    cf0, k_e = calibrate(_f35c(), 8.8, _f22(), 8.0)
    ld, d = predict_ld(_j20(), cf0, k_e)
    assert 7.0 < ld < 10.0
    assert d['CD'] == pytest.approx(d['CD0'] + d['CDi'] + d['CDw'] + d['CDa'])
    assert KAPPA_A == pytest.approx(0.90)


def test_lambda_uav_ma15_ld_below_j50_because_cl_is_lower():
    """同为兰姆达无尾时，53636 翼载更低 → Ma 1.5 的 CL 更小，L/D 仍低于歼-50。

    无座舱只削 CD0；构型项（翼型/布局/粗糙度）与歼-50 相同，不是 L/D 差距来源。
    """
    from utils.combat_radius.combat_radius_presets import get_preset_by_id, load_presets, preset_to_aircraft

    presets = load_presets()
    uav = preset_to_aircraft(get_preset_by_id(presets, '53636'))
    j50 = preset_to_aircraft(get_preset_by_id(presets, 'J-50'))
    assert uav.planform == j50.planform == 'lambda'
    assert uav.layout == j50.layout == 'tailless'
    assert uav.rough is False and j50.rough is False
    assert uav.canopy is False and j50.canopy is True
    assert uav.wing_loading < j50.wing_loading
    cf0, k_e = calibrate_default_anchors()
    uav_m = Aircraft(**{**aircraft_to_dict(uav), 'mach': 1.5, 'alt_m': 11000})
    j50_m = Aircraft(**{**aircraft_to_dict(j50), 'mach': 1.5, 'alt_m': 11000})
    ld_u, d_u = predict_ld(uav_m, cf0, k_e)
    ld_j, d_j = predict_ld(j50_m, cf0, k_e)
    assert d_u['CL'] < d_j['CL']
    assert d_u['CD0'] < d_j['CD0']
    assert ld_u < ld_j
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
