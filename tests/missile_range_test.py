"""导弹射程估算单元测试。"""
from __future__ import annotations

import math

import pytest

from apps.missile_range_web import run_missile_range, run_missile_range_json
from simulators.missile_range.missile_range import (
    _required_float,
    include_dataset_rows,
    opt_float,
    opt_optional_float,
    run_dataset_from_params,
    run_estimate_from_params,
    run_presets_from_params,
)
from utils.missile_range.dataset import (
    MISSILE_DATASET,
    PROPULSION_DATASET,
    _cached_default_dataset,
    all_missile_cases,
    build_missile_range_catalog_payload,
    dataset_propellant_key,
    evaluate_case,
    evaluate_dataset,
    filter_takeover_failed,
    format_launch,
    format_size_m,
    _row_liftoff_t,
    missile_case_label,
    sort_missile_range_rows,
)
from utils.missile_range.estimate import (
    G0,
    GLIDE_EXIT_SPEED_M_S,
    GLIDE_HEAT_EXPONENT,
    GLIDE_HEAT_RATIO,
    HGV_CHAMBER_DEDUCT_CAP_M,
    HGV_CHAMBER_DEDUCT_FRAC,
    HGV_CHAMBER_FILL,
    HGV_MIN_BOOSTER_M,
    HGV_MOTOR_DIAMETER_RATIO,
    HGV_PROPELLANT_MASS_FRACTION,
    HGV_BETA_SCALE_MAX,
    HGV_BETA_SCALE_MIN,
    HGV_DRAG_AT_13_M_S,
    HGV_DRAG_SCALE_KM,
    HGV_DRAG_SHARE_CAP,
    HGV_LOSS_AT_13_M_S,
    HGV_LOSS_AT_SEA_M_S,
    HGV_LOSS_FLOOR_M_S,
    HGV_LOSS_PER_KM_ABOVE_13,
    HGV_REF_DIAMETER_M,
    HGV_REF_MASS_KG,
    R_EARTH_M,
    SOUND_SPEED_M_S,
    _require_non_negative,
    _round_hgv_result,
    chamber_length_m,
    boost_drag_height_factor,
    estimate_hgv,
    estimate_hgv_unrounded,
    glide_exit_ratio,
    glide_heat_factor,
    glide_range_m,
    hgv_burnout_altitude_km,
    hgv_propellant_mass_kg,
    gravity_drag_loss_m_s,
    head_and_booster_lengths_m,
    head_aux_ratio,
    head_density_kg_m3,
    head_packaging_volume_m3,
    head_total_mass_kg,
    head_volume_factor,
    head_volume_m3,
    hgv_altitude_loss_m_s,
    hgv_head_diameter_bounds,
    hgv_min_fineness,
    lift_drag_ratio,
    min_head_length_m,
    motor_cross_section_m2,
    normalize_hgv_type,
    optimize_hgv_geometry,
    propellant_mass_kg,
    uncapped_head_length_m,
    _optimize_geometry_cache_key,
    _optimize_hgv_geometry_cached,
    _optimize_hgv_geometry_compute,
)


def _reference_hgv_loss(h_launch_km: float, mass_kg: float, diameter_m: float) -> float:
    """与 gravity_drag_loss_m_s 对照的独立公式。"""
    if h_launch_km >= 13.0:
        baseline = max(
            HGV_LOSS_FLOOR_M_S,
            HGV_LOSS_AT_13_M_S - (h_launch_km - 13.0) * HGV_LOSS_PER_KM_ABOVE_13,
        )
    else:
        span = HGV_LOSS_AT_SEA_M_S - HGV_LOSS_AT_13_M_S
        baseline = HGV_LOSS_AT_13_M_S + (13.0 - h_launch_km) * span / 13.0
    drag_ref = HGV_DRAG_AT_13_M_S * math.exp(-(h_launch_km - 13.0) / HGV_DRAG_SCALE_KM)
    drag_ref = min(drag_ref, baseline * HGV_DRAG_SHARE_CAP)
    beta_ref = HGV_REF_MASS_KG / (math.pi * (HGV_REF_DIAMETER_M / 2.0) ** 2)
    beta = mass_kg / (math.pi * (diameter_m / 2.0) ** 2)
    scale = min(HGV_BETA_SCALE_MAX, max(HGV_BETA_SCALE_MIN, beta_ref / beta))
    return baseline - drag_ref + drag_ref * scale


def _oracle(
    length_m: float,
    diameter_m: float,
    warhead_mass_kg: float,
    hgv_type: str = 'biconic',
    v_launch_mach: float = 0.85,
    h_launch_km: float = 13.0,
    isp_s: float = 264.0,
    propellant_density: float = 1760.0,
) -> dict:
    """与给出的估算脚本逐行一致的对照实现。"""
    hgv_type = hgv_type.lower().strip()
    g0 = 9.80665
    r_e = 6371000.0
    v_launch_ms = v_launch_mach * 295.0
    aux_head_ratio = 0.35 if warhead_mass_kg <= 250 else 0.28
    m_head_total = warhead_mass_kg + max(40.0, warhead_mass_kg * aux_head_ratio)
    # 乘波体密度更低、容积系数更小，弹头更长，助推级更短。
    head_density = 1800.0 if hgv_type == 'biconic' else 1650.0
    v_head_req = m_head_total / head_density
    volume_factor = 0.2618 if hgv_type == 'biconic' else 0.1745
    fineness_min = 1.8 if hgv_type == 'biconic' else 2.2
    l_head_calc = max(
        v_head_req / (volume_factor * (diameter_m ** 2)),
        fineness_min * diameter_m,
    )
    l_head = min(l_head_calc, length_m * 0.45)
    l_booster_gross = length_m - l_head
    d_motor = diameter_m * 0.90
    area_motor = math.pi * (d_motor / 2.0) ** 2
    l_deduct = min(1.50, l_booster_gross * 0.25)
    l_chamber_eff = max(0.2, l_booster_gross - l_deduct)
    m_propellant = area_motor * l_chamber_eff * 0.81 * propellant_density
    pmf = 0.87
    m_booster_dry = m_propellant * (1.0 - pmf) / pmf
    m_0 = m_head_total + m_booster_dry + m_propellant
    v_e = isp_s * g0
    m_p1, m_p2 = m_propellant * 0.58, m_propellant * 0.42
    m_s1 = m_booster_dry * 0.60
    m_stg1_out = m_0 - m_p1
    dv1 = v_e * math.log(m_0 / m_stg1_out)
    m_stg2_in = m_stg1_out - m_s1
    dv2 = v_e * math.log(m_stg2_in / (m_stg2_in - m_p2))
    gravity_drag_loss = _reference_hgv_loss(h_launch_km, m_0, diameter_m)
    v_burnout = v_launch_ms + (dv1 + dv2) - gravity_drag_loss
    fineness = l_head / diameter_m
    if hgv_type == 'biconic':
        ld_ratio = max(1.8, min(3.5, 1.5 + 0.18 * fineness))
    else:
        ld_ratio = max(2.8, min(5.0, 2.4 + 0.32 * fineness))
    v_eff2 = v_burnout ** 2 + 2.0 * g0 * (h_launch_km * 1000.0)
    ratio_v2 = v_eff2 / (g0 * r_e)
    exit_ratio = (GLIDE_EXIT_SPEED_M_S ** 2) / (g0 * r_e)
    if ratio_v2 >= 0.95:
        r_glide = 16000000.0
    elif ratio_v2 <= exit_ratio:
        r_glide = 0.0
    else:
        r_glide = (
            0.5 * r_e * ld_ratio
            * math.log((1.0 - exit_ratio) / (1.0 - ratio_v2))
            * (1.0 + 0.35 * ratio_v2)
        )
    r_boost = (v_launch_ms + v_burnout) / 2.0 * 60.0 + h_launch_km * 1000.0 * 2.0
    total_range_km = (r_boost + r_glide) / 1000.0
    return {
        'm_0_t': round(m_0 / 1000.0, 2),
        'l_head_m': round(l_head, 2),
        'l_booster_m': round(l_booster_gross, 2),
        'm_p_total_kg': round(m_propellant, 1),
        'v_burnout_mach': round(v_burnout / 295.0, 2),
        'ld_ratio': round(ld_ratio, 2),
        'range_km': round(total_range_km, 1),
        'd_head_m': round(diameter_m, 3),
        'fineness': round(l_head / diameter_m, 2),
    }


def test_normalize_hgv_type_aliases():
    assert normalize_hgv_type('  Biconic ') == 'biconic'
    assert normalize_hgv_type('双锥体') == 'biconic'
    assert normalize_hgv_type('乘波体') == 'waverider'
    with pytest.raises(ValueError, match='未知构型'):
        normalize_hgv_type('cone')


def test_head_aux_ratio_threshold():
    assert head_aux_ratio(250) == 0.35
    assert head_aux_ratio(250.1) == 0.28


def test_head_total_mass_kg_uses_floor():
    assert head_total_mass_kg(10) == pytest.approx(50.0)
    assert head_total_mass_kg(200) == pytest.approx(270.0)


def test_head_density_kg_m3():
    assert head_density_kg_m3('biconic') == 1800.0
    assert head_density_kg_m3('waverider') == 1650.0


def test_head_volume_m3():
    assert head_volume_m3(200, 'biconic') == pytest.approx(270.0 / 1800.0)


def test_uncapped_head_length_m():
    vol = 270.0 / 1800.0
    expect = vol / (0.2618 * 1.0)
    assert uncapped_head_length_m(vol, 1.0, 'biconic') == pytest.approx(expect)
    with pytest.raises(ValueError):
        uncapped_head_length_m(vol, 0, 'biconic')


def test_head_and_booster_lengths_m_caps_at_45_percent():
    """默认弹头不超过全长 45%；要求装下战斗部时，乘波体比双锥体更长。"""
    l_head, l_boost = head_and_booster_lengths_m(6.35, 0.46, 300, 'biconic')
    assert l_head == pytest.approx(6.35 * 0.45)
    assert l_boost == pytest.approx(6.35 - l_head)
    bic, _bic_boost = head_and_booster_lengths_m(
        6.35, 0.46, 300, 'biconic', pack_warhead=True,
    )
    wave, wave_boost = head_and_booster_lengths_m(
        6.35, 0.46, 300, 'waverider', pack_warhead=True,
    )
    assert bic == pytest.approx(min_head_length_m(300, 0.46, 'biconic'))
    assert wave > bic > 6.35 * 0.45
    assert wave_boost >= HGV_MIN_BOOSTER_M - 1e-9
    with pytest.raises(ValueError):
        head_and_booster_lengths_m(0, 0.5, 100, 'biconic')
    with pytest.raises(ValueError, match='助推级'):
        head_and_booster_lengths_m(0.2, 0.3, 50, 'waverider', pack_warhead=True)


def test_motor_cross_section_m2():
    d = 1.0 * 0.9
    assert motor_cross_section_m2(1.0) == pytest.approx(math.pi * (d / 2) ** 2)


def test_chamber_length_m_floor_and_deduct():
    assert chamber_length_m(10.0) == pytest.approx(8.5)
    assert chamber_length_m(0.1) == pytest.approx(0.2)


def test_propellant_mass_kg_positive():
    mass = propellant_mass_kg(1.0, 9.93, 1760.0)
    assert mass > 1000


def test_gravity_drag_loss_m_s_clamps():
    assert hgv_altitude_loss_m_s(13.0) == pytest.approx(320.0)
    assert hgv_altitude_loss_m_s(0.0) == pytest.approx(1000.0)
    assert gravity_drag_loss_m_s(13.0) == pytest.approx(320.0)
    assert gravity_drag_loss_m_s(19.0) == pytest.approx(230.0)
    assert gravity_drag_loss_m_s(40.0) == pytest.approx(180.0)
    assert gravity_drag_loss_m_s(0.0) == pytest.approx(1000.0)
    reference = gravity_drag_loss_m_s(13.0, HGV_REF_MASS_KG, HGV_REF_DIAMETER_M)
    assert reference == pytest.approx(320.0)
    light = gravity_drag_loss_m_s(0.0, 1100.0, 0.51)
    heavy = gravity_drag_loss_m_s(0.0, HGV_REF_MASS_KG, HGV_REF_DIAMETER_M)
    assert light > heavy
    with pytest.raises(ValueError):
        hgv_altitude_loss_m_s(-1)
    with pytest.raises(ValueError):
        gravity_drag_loss_m_s(0.0, 1000.0, None)
    with pytest.raises(ValueError):
        gravity_drag_loss_m_s(0.0, 0.0, 1.0)


def test_lift_drag_ratio_bounds():
    """升阻比用滑翔体自身长细比；过短落到下限，过长封在上限。"""
    assert lift_drag_ratio(0.57, 1.0, 'biconic') == pytest.approx(1.8)
    assert lift_drag_ratio(4.0, 0.8, 'waverider') == pytest.approx(4.0)
    assert lift_drag_ratio(20.0, 0.86, 'waverider') == pytest.approx(5.0)
    with pytest.raises(ValueError):
        lift_drag_ratio(10, 0, 'biconic')
    with pytest.raises(ValueError):
        lift_drag_ratio(0, 1.0, 'biconic')


def test_glide_range_m_cap_and_formula():
    assert glide_range_m(0.96, 3.0) == 16000000.0
    ratio = 0.2
    ld = 3.0
    exit_ratio = (GLIDE_EXIT_SPEED_M_S ** 2) / (G0 * R_EARTH_M)
    expected = (
        0.5 * R_EARTH_M * ld
        * math.log((1.0 - exit_ratio) / (1.0 - ratio))
        * (1.0 + 0.35 * ratio)
        * glide_heat_factor(ratio)
    )
    assert glide_range_m(ratio, ld) == pytest.approx(expected)
    assert glide_heat_factor(GLIDE_HEAT_RATIO) == 1.0
    hot = 0.7
    assert glide_heat_factor(hot) == pytest.approx((GLIDE_HEAT_RATIO / hot) ** GLIDE_HEAT_EXPONENT)
    unheated = expected / glide_heat_factor(ratio) * (
        math.log((1.0 - exit_ratio) / (1.0 - hot)) / math.log((1.0 - exit_ratio) / (1.0 - ratio))
    ) * ((1.0 + 0.35 * hot) / (1.0 + 0.35 * ratio))
    assert glide_range_m(hot, ld) < unheated
    assert glide_range_m(exit_ratio, ld) == 0.0
    with pytest.raises(ValueError, match='不能为负'):
        glide_heat_factor(-0.1)
    full_to_zero = (
        0.5 * R_EARTH_M * ld * math.log(1.0 / (1.0 - ratio)) * (1.0 + 0.35 * ratio)
    )
    assert glide_range_m(ratio, ld) < full_to_zero
    with pytest.raises(ValueError):
        glide_range_m(-0.1, 3.0)


def test_boost_drag_height_factor_and_lofted_loss():
    """高抛后阻力低于全程停在发射高度，爬升很短时不打折。"""
    assert boost_drag_height_factor(0.0, 0.5) == 1.0
    assert boost_drag_height_factor(0.0, 40.0) < 1.0
    assert boost_drag_height_factor(13.0, 70.0) < boost_drag_height_factor(0.0, 20.0)
    sea = gravity_drag_loss_m_s(0.0, 3360.0, 0.8)
    lofted = gravity_drag_loss_m_s(0.0, 3360.0, 0.8, 45.0)
    assert lofted < sea
    with pytest.raises(ValueError, match='不能为负'):
        boost_drag_height_factor(-1.0, 10.0)
    with pytest.raises(ValueError, match='不能低于'):
        boost_drag_height_factor(20.0, 10.0)
    with pytest.raises(ValueError, match='质量与弹径'):
        gravity_drag_loss_m_s(0.0, h_burnout_km=30.0)


def test_hgv_propellant_mass_kg_packs_tighter_than_ballistic():
    """滑翔弹药柱比弹道弹少留壳体和空腔，药量更高。"""
    ballistic = propellant_mass_kg(0.8, 6.0, 1760.0)
    hgv = hgv_propellant_mass_kg(0.8, 6.0, 1760.0)
    assert hgv > ballistic
    hand = (
        math.pi * ((0.8 * HGV_MOTOR_DIAMETER_RATIO) / 2.0) ** 2
        * max(0.2, 6.0 - min(HGV_CHAMBER_DEDUCT_CAP_M, 6.0 * HGV_CHAMBER_DEDUCT_FRAC))
        * HGV_CHAMBER_FILL
        * 1760.0
    )
    assert hgv == pytest.approx(hand)
    assert 0.87 < HGV_PROPELLANT_MASS_FRACTION < 0.92
    with pytest.raises(ValueError, match='直径比例'):
        motor_cross_section_m2(1.0, 1.2)
    with pytest.raises(ValueError, match='扣除'):
        chamber_length_m(4.0, deduct_cap_m=-1)
    with pytest.raises(ValueError, match='装填系数'):
        propellant_mass_kg(1.0, 4.0, 1760.0, chamber_fill=0)


def test_hgv_burnout_altitude_and_vls_bands():
    """关机高度沿用弹道爬升。850 垂发乘波体、双锥体落在目标区间附近。"""
    from utils.missile_range.classes import estimate_by_class

    assert hgv_burnout_altitude_km(3000.0, 0.0) > 30.0
    assert glide_exit_ratio() == pytest.approx((GLIDE_EXIT_SPEED_M_S ** 2) / (G0 * R_EARTH_M))
    wave = estimate_hgv(8.55, 0.8, 300, 'waverider', 0.0, 0.0, optimize_geometry=True)
    bic = estimate_hgv(8.55, 0.8, 300, 'biconic', 0.0, 0.0, optimize_geometry=True)
    assert 1500.0 <= wave['range_km'] <= 2100.0
    assert 1000.0 <= bic['range_km'] <= 1500.0
    assert wave['h_burnout_km'] > 20.0
    assert '临近空间' in estimate_by_class(
        'hgv_waverider', 8.55, 0.8, 300, 0.0, 0.0,
    )['note']


def test_h6_biconic_air_launch_stays_in_jinglei_band():
    """轰-6 机腹最大的双锥体按惊雷-1 量级：战斗部 200 kg 以内，射程 5000–7000 km。"""
    from utils.missile_range.classes import estimate_by_class

    light = estimate_by_class('hgv_biconic', 11.95, 1.1818, 150, 0.85, 13.0)
    heavier = estimate_by_class('hgv_biconic', 11.95, 1.1818, 200, 0.85, 13.0)
    assert 5000.0 <= light['range_km'] <= 7000.0
    assert 5000.0 <= heavier['range_km'] <= 7000.0
    assert heavier['range_km'] < light['range_km']


def test_require_non_negative():
    assert _require_non_negative('战斗部质量', 0) == 0
    with pytest.raises(ValueError, match='战斗部质量'):
        _require_non_negative('战斗部质量', -1)


def test_estimate_hgv_matches_reference_dataset():
    """弹头划分仍按容积公式；助推分级改为按射程搜索，不再对照旧的固定两级。"""
    got = estimate_hgv(10.5, 1.0, 200)
    ref = _oracle(10.5, 1.0, 200)
    assert got['l_head_m'] == ref['l_head_m']
    assert got['l_booster_m'] == ref['l_booster_m']
    assert got['ld_ratio'] == ref['ld_ratio']
    assert got['n_stages'] == 3
    assert got['stage_split'] == '70/22/8'
    assert got['range_km'] == 3200.1
    assert got['stage_hardware_kg'] > 0
    for case in MISSILE_DATASET:
        from utils.missile_range.classes import glide_shape
        shape = glide_shape(case['missile_class'])
        row = estimate_hgv(
            length_m=case['length'],
            diameter_m=case['diameter'],
            warhead_mass_kg=case['warhead'],
            hgv_type=shape,
            v_launch_mach=case['v_mach'],
            h_launch_km=case['h_km'],
        )
        geom = _oracle(
            case['length'], case['diameter'], case['warhead'], shape,
            case['v_mach'], case['h_km'],
        )
        assert row['l_head_m'] == geom['l_head_m']
        assert row['l_booster_m'] == geom['l_booster_m']
        assert row['n_stages'] in (1, 2, 3)
        assert row['range_km'] > 0
    custom = estimate_hgv(8.0, 0.7, 400, 'waverider', 1.2, 15.0, isp_s=280, propellant_density=1800)
    assert custom['n_stages'] in (1, 2, 3)
    assert custom['range_km'] > 0


def test_estimate_hgv_rejects_bad_inputs():
    with pytest.raises(ValueError):
        estimate_hgv(0, 1, 100)
    with pytest.raises(ValueError):
        estimate_hgv(10, 1, -1)
    with pytest.raises(ValueError):
        estimate_hgv(10, 1, 100, isp_s=0)


def test_format_size_and_launch():
    assert format_size_m(10.5, 1) == '10.50 x 1.000'
    assert format_launch(0.85, 13) == 'Ma 0.85 @ 13km'


def test_missile_case_label_and_evaluate_case():
    case = MISSILE_DATASET[0]
    assert case['bay'] == '隐身超音速轰炸机弹仓'
    assert case['length'] == 11.3
    assert case['diameter'] == 0.86
    assert missile_case_label(case).startswith('#1  隐身超音速轰炸机弹仓 · 11.30 x 0.860')
    row = evaluate_case(case)
    assert row['id'] == 1
    assert row['bay'] == '隐身超音速轰炸机弹仓'
    assert row['alt_launches'][0]['label'] == '轰-6'
    assert 'type_label' not in row
    assert 'hgv_type' not in row
    assert row['missile_class'] == 'hgv_biconic'
    assert row['class_label'] == '双锥体助推滑翔'
    from utils.missile_range.classes import estimate_by_class
    expected = estimate_by_class(
        'hgv_biconic', case['length'], case['diameter'], case['warhead'],
        case['v_mach'], case['h_km'],
    )
    assert row['range_km'] == expected['range_km']
    assert row['ld_ratio'] == expected['ld_ratio']
    assert row['d_head_m'] == expected['d_head_m']
    assert expected['optimal_geometry'] is True


def test_evaluate_dataset_and_catalog():
    rows = evaluate_dataset()
    assert len(rows) == len(all_missile_cases())
    assert [r['id'] for r in rows] == list(range(1, len(rows) + 1))
    assert rows[0]['bay'] == rows[1]['bay']
    assert rows[0]['warhead_kg'] <= rows[1]['warhead_kg']
    if rows[0]['warhead_kg'] == rows[1]['warhead_kg']:
        assert rows[0]['range_km'] >= rows[1]['range_km']
    heavier = evaluate_dataset(isp_s=300, propellant_density=1900)
    glide = next(row for row in rows if row['missile_class'] == 'hgv_biconic')
    glide_heavier = next(
        row for row in heavier
        if row['missile_class'] == 'hgv_biconic'
        and row['bay'] == glide['bay']
        and row['length_m'] == glide['length_m']
        and row['warhead_kg'] == glide['warhead_kg']
    )
    assert glide_heavier['range_km'] != glide['range_km']
    payload = build_missile_range_catalog_payload()
    assert 'type_labels' not in payload
    assert payload['defaults']['missile_class'] == 'hgv_biconic'
    assert 'hgv_type' not in payload['defaults']
    assert payload['defaults']['ballistic_single_stage'] is False
    assert {item['id'] for item in payload['classes']} >= {
        'hgv_biconic', 'hgv_waverider', 'scramjet', 'ramjet', 'turbofan_stealth',
        'turbojet_subsonic', 'turbofan_rocket', 'ballistic',
    }
    assert 'hgv' not in {item['id'] for item in payload['classes']}
    assert payload['cases'][0]['bay'] == rows[0]['bay']
    assert payload['cases'][0]['warhead_kg'] <= payload['cases'][1]['warhead_kg']
    top_bay = rows[0]['bay']
    same_bay = [r for r in rows if r['bay'] == top_bay]
    assert len(same_bay) >= 2
    assert same_bay[0]['warhead_kg'] <= same_bay[1]['warhead_kg']
    assert payload['defaults']['isp_s'] == 264.0
    assert payload['cases'][0]['range_km'] == rows[0]['range_km']
    assert G0 == pytest.approx(9.80665)
    assert SOUND_SPEED_M_S == 295.0


def test_dataset_propellant_key_rounds():
    """推进剂缓存键按六位小数对齐，避免浮点噪声拆成两次整表计算。"""
    assert dataset_propellant_key(264, 1760) == (264.0, 1760.0)
    assert dataset_propellant_key(264.0000004, 1760.0000004) == (264.0, 1760.0)
    assert dataset_propellant_key('300', '1900') == (300.0, 1900.0)


def test_cached_default_dataset_copy_is_isolated():
    """默认样本表走缓存，调用方改射程不会污染下一次结果。"""
    key = dataset_propellant_key(264, 1760)
    first = evaluate_dataset()
    cached = _cached_default_dataset(*key)
    first[0]['range_km'] = -1
    again = evaluate_dataset()
    assert again[0]['range_km'] != -1
    assert again[0]['range_km'] == cached[0]['range_km']
    assert again == evaluate_dataset(isp_s=264, propellant_density=1760)


def test_include_dataset_rows_flag():
    """include_rows 为假时只返回当前这一发，不再附带整张样本表。"""
    assert include_dataset_rows({}) is True
    assert include_dataset_rows({'include_rows': True}) is True
    assert include_dataset_rows({'include_rows': False}) is False
    assert include_dataset_rows({'include_rows': 'false'}) is False
    assert include_dataset_rows({'include_rows': '0'}) is False
    skipped = run_estimate_from_params({
        'length_m': 6.35,
        'diameter_m': 0.51,
        'warhead_kg': 160,
        'missile_class': 'ramjet',
        'include_rows': False,
    })
    assert skipped['success'] is True
    assert 'rows' not in skipped
    assert skipped['result']['range_km'] > 0
    kept = run_estimate_from_params({
        'length_m': 6.35,
        'diameter_m': 0.51,
        'warhead_kg': 160,
        'missile_class': 'ramjet',
        'include_rows': True,
    })
    assert len(kept['rows']) == len(all_missile_cases())
    assert kept['result']['range_km'] == skipped['result']['range_km']


def test_row_liftoff_t():
    assert _row_liftoff_t({'m_0_t': 2.5}) == 2.5
    assert _row_liftoff_t({}) == 0.0
    assert _row_liftoff_t({'m_0_t': None}) == 0.0


def test_sort_missile_range_rows_by_bay_and_range():
    """载机按最大起飞质量降序；同质量按名称。组内不按尺寸。"""
    rows = sort_missile_range_rows([
        {
            'id': 9,
            'name': 'A',
            'bay': '小平台',
            'length_m': 12.0,
            'diameter_m': 1.2,
            'm_0_t': 0.4,
            'warhead_kg': 100,
            'range_km': 120.0,
        },
        {
            'id': 3,
            'name': 'B',
            'bay': '大平台',
            'length_m': 4.0,
            'diameter_m': 0.3,
            'm_0_t': 1.2,
            'warhead_kg': 300,
            'range_km': 80.0,
        },
        {
            'id': 2,
            'name': 'C',
            'bay': '大平台',
            'length_m': 8.0,
            'diameter_m': 0.8,
            'm_0_t': 5.0,
            'warhead_kg': 100,
            'range_km': 100.0,
        },
        {
            'id': 6,
            'name': 'D',
            'bay': '中平台',
            'length_m': 10.0,
            'diameter_m': 1.0,
            'm_0_t': 3.0,
            'warhead_kg': 150,
            'range_km': 200.0,
        },
    ])
    assert [row['bay'] for row in rows] == ['大平台', '大平台', '中平台', '小平台']
    assert [(row['warhead_kg'], row['range_km']) for row in rows[:2]] == [
        (100, 100.0),
        (300, 80.0),
    ]
    assert [row['id'] for row in rows] == [1, 2, 3, 4]
    assert rows[0]['name'].startswith('#1  ')
    assert rows[1]['name'].startswith('#2  ')


def test_sort_same_bay_by_warhead_then_range():
    """同一载机先按战斗部重量升序，同一战斗部再按射程降序。"""
    rows = sort_missile_range_rows([
        {
            'id': 1,
            'name': '轻战斗部远',
            'bay': '超音速隐身轰炸机·轰6发射',
            'length_m': 10.5,
            'diameter_m': 1.1,
            'm_0_t': 4.0,
            'warhead_kg': 150,
            'range_km': 900.0,
        },
        {
            'id': 2,
            'name': '轻战斗部近',
            'bay': '超音速隐身轰炸机·轰6发射',
            'length_m': 11.3,
            'diameter_m': 0.86,
            'm_0_t': 8.0,
            'warhead_kg': 150,
            'range_km': 100.0,
        },
        {
            'id': 3,
            'name': '重战斗部',
            'bay': '超音速隐身轰炸机·轰6发射',
            'length_m': 10.5,
            'diameter_m': 1.1,
            'm_0_t': 6.0,
            'warhead_kg': 600,
            'range_km': 200.0,
        },
        {
            'id': 4,
            'name': '中战斗部',
            'bay': '超音速隐身轰炸机·轰6发射',
            'length_m': 11.3,
            'diameter_m': 0.86,
            'm_0_t': 5.0,
            'warhead_kg': 500,
            'range_km': 800.0,
        },
    ])
    assert [(row['warhead_kg'], row['range_km']) for row in rows] == [
        (150, 900.0),
        (150, 100.0),
        (500, 800.0),
        (600, 200.0),
    ]


def test_evaluate_dataset_splits_h6_belly_from_max():
    """轰-6 机腹与轰-6机腹最大分成两个平台；组内按战斗部升序、同战斗部射程降序。"""
    from itertools import groupby

    rows = evaluate_dataset()
    bays = [row['bay'] for row in rows]
    assert '超音速隐身轰炸机·轰6发射' not in bays
    stealth = [row for row in rows if row['bay'] == '隐身超音速轰炸机弹仓']
    assert {(round(row['length_m'], 2), round(row['diameter_m'], 3)) for row in stealth} == {(11.3, 0.86)}
    for row in stealth:
        assert [item['label'] for item in row['alt_launches']] == ['轰-6', '轰-20', '歼-36']
    largest = [row for row in rows if row['bay'] == '轰-6机腹最大']
    assert len({(row['length_m'], row['diameter_m']) for row in largest}) > 1
    assert all(row['length_m'] <= 12.0 and row['m_0_t'] <= 10.0 for row in largest)
    bay_order: list[str] = []
    bay_mass: dict[str, float] = {}
    for row in rows:
        bay = row['bay']
        if bay not in bay_mass:
            bay_order.append(bay)
            bay_mass[bay] = float(row['m_0_t'])
        else:
            bay_mass[bay] = max(bay_mass[bay], float(row['m_0_t']))
    masses = [bay_mass[bay] for bay in bay_order]
    assert masses == sorted(masses, reverse=True)
    for _, group in groupby(rows, key=lambda row: row['bay']):
        bay_rows = list(group)
        warheads = [row['warhead_kg'] for row in bay_rows]
        assert warheads == sorted(warheads)
        for _, same in groupby(bay_rows, key=lambda row: row['warhead_kg']):
            ranges = [row['range_km'] for row in same]
            assert ranges == sorted(ranges, reverse=True)


def test_opt_float_and_required_float():
    assert opt_float('', 1.5) == 1.5
    assert opt_float(None, 2) == 2
    assert opt_float('3.5', 1) == 3.5
    assert opt_optional_float(None) is None
    assert opt_optional_float('') is None
    assert opt_optional_float('1500') == 1500.0
    assert _required_float({'length_m': '4'}, 'length_m') == 4
    with pytest.raises(ValueError, match='缺少参数'):
        _required_float({}, 'length_m')


def test_run_estimate_dataset_and_presets():
    from utils.missile_range.classes import estimate_by_class
    bad = run_estimate_from_params({})
    assert bad['success'] is False
    ok = run_estimate_from_params({
        'length_m': 10.5,
        'diameter_m': 1,
        'warhead_kg': 200,
        'missile_class': 'hgv_biconic',
    })
    assert ok['success'] is True
    assert ok['result']['optimal_geometry'] is True
    assert ok['result']['range_km'] == estimate_by_class('hgv_biconic', 10.5, 1, 200)['range_km']
    assert len(ok['rows']) == len(all_missile_cases())
    table = run_dataset_from_params({'isp_s': '264'})
    assert table['count'] == len(all_missile_cases())
    presets = run_presets_from_params()
    assert presets['success'] is True
    assert len(presets['cases']) == len(all_missile_cases())


def test_run_missile_range_json_actions():
    from utils.missile_range.classes import estimate_by_class
    missing = run_missile_range('nope', {})
    assert missing['success'] is False
    parsed = run_missile_range_json('{"action":"dataset"}')
    assert parsed['success'] is True
    assert parsed['count'] == len(all_missile_cases())
    bad_json = run_missile_range_json('{')
    assert bad_json['success'] is False
    assert run_missile_range_json([1, 2])['success'] is False
    flat = run_missile_range_json({
        'action': 'estimate',
        'length_m': 10.5,
        'diameter_m': 1,
        'warhead_kg': 200,
    })
    assert flat['result']['optimal_geometry'] is True
    assert flat['result']['range_km'] == estimate_by_class('hgv_biconic', 10.5, 1, 200)['range_km']
    assert run_missile_range_json({'action': 'estimate', 'params': []})['success'] is False


def test_normalize_missile_class_and_labels():
    from utils.missile_range.classes import (
        class_blurb,
        class_label,
        glide_shape,
        normalize_missile_class,
        resolve_missile_class,
    )

    assert normalize_missile_class(' 超燃冲压 ') == 'scramjet'
    assert normalize_missile_class('涡扇亚音速隐身巡航') == 'turbofan_stealth'
    assert normalize_missile_class('亚超结合导弹') == 'turbofan_rocket'
    assert normalize_missile_class('双锥体助推滑翔') == 'hgv_biconic'
    assert normalize_missile_class('乘波体') == 'hgv_waverider'
    assert class_label('ballistic') == '普通弹道导弹'
    assert class_label('hgv_biconic') == '双锥体助推滑翔'
    assert class_label('hgv_waverider') == '乘波体助推滑翔'
    assert '全掠海' in class_blurb('turbojet_subsonic')
    assert '混合弹道' in class_blurb('turbojet_subsonic')
    assert '混合弹道' in class_blurb('ramjet')
    assert '视距' in class_blurb('turbofan_rocket')
    assert glide_shape('hgv_biconic') == 'biconic'
    assert glide_shape('hgv_waverider') == 'waverider'
    assert glide_shape('scramjet') is None
    assert resolve_missile_class('hgv') == 'hgv_biconic'
    assert resolve_missile_class('助推滑翔弹') == 'hgv_biconic'
    assert resolve_missile_class('乘波体助推滑翔') == 'hgv_waverider'
    with pytest.raises(ValueError, match='未知弹种'):
        normalize_missile_class('laser')
    with pytest.raises(ValueError, match='未知弹种'):
        normalize_missile_class('hgv')


def test_geometry_and_breguet_helpers():
    import math

    from utils.missile_range.classes import (
        BODY_PACK,
        G0,
        LHV_J_KG,
        _SUBSONIC_SPECS,
        _base_fields,
        _ideal_two_stage_dv,
        achieved_boost_dv_m_s,
        ballistic_burn_time_s,
        ballistic_liftoff_twr,
        ballistic_loss_m_s,
        ballistic_range_km,
        breguet_cruise_range_m,
        body_volume_m3,
        burnout_altitude_km,
        clamp,
        climb_fuel_kg,
        drag_coast_range_m,
        duct_ld,
        energy_volume_m3,
        engine_mass_kg,
        fineness_ratio,
        payload_mass_kg,
        speed_of_sound_m_s,
        split_boost_and_fuel,
        structural_mass_kg,
        subsonic_ld,
        terminal_dash_range_m,
    )

    assert clamp(3, 1, 2) == 2
    assert fineness_ratio(10, 0.5) == 20
    with pytest.raises(ValueError):
        fineness_ratio(0, 1)
    sea = math.sqrt(1.4 * 287.05287 * 288.15)
    assert speed_of_sound_m_s(0) == pytest.approx(sea)
    assert speed_of_sound_m_s(10) < speed_of_sound_m_s(0)
    with pytest.raises(ValueError):
        speed_of_sound_m_s(-1)
    assert body_volume_m3(8, 0.5) == pytest.approx(BODY_PACK * math.pi * 0.25 ** 2 * 8)
    with pytest.raises(ValueError, match='装填系数'):
        body_volume_m3(8, 0.5, pack=0.2)
    assert payload_mass_kg(100) == pytest.approx(118)
    assert payload_mass_kg(10) == pytest.approx(28)
    with pytest.raises(ValueError):
        payload_mass_kg(-1)
    assert structural_mass_kg(8, 0.5, 20) == pytest.approx(20 * math.pi * 0.5 * 8 * 1.15)
    with pytest.raises(ValueError):
        structural_mass_kg(8, 0.5, 0)
    assert engine_mass_kg(8, 0.5, 100) == pytest.approx(100 * 0.25 * (8 ** 0.15))
    volume = body_volume_m3(8, 0.6)
    leftover = energy_volume_m3(volume, 200, 1500, 80, 500, 0.08)
    assert leftover < volume
    tighter = energy_volume_m3(volume, 200, 1500, 80, 500, 0.08, fixed_void_m3=0.05)
    assert tighter < leftover
    with pytest.raises(ValueError, match='固定空腔'):
        energy_volume_m3(volume, 200, 1500, 80, 500, 0.08, fixed_void_m3=-0.1)
    with pytest.raises(ValueError, match='放不下'):
        energy_volume_m3(0.05, 500, 800, 40, 400, 0.1)
    spec = _SUBSONIC_SPECS['turbofan_stealth']
    fineness = 6.2 / 0.55
    assert subsonic_ld(6.2, 0.55, spec) == pytest.approx(
        clamp(spec['ld_base'] + spec['ld_slope'] * fineness, spec['ld_min'], spec['ld_max'])
    )
    assert duct_ld(8.9, 0.7, {'ld_base': 1.9, 'ld_slope': 0.11, 'ld_min': 2.3, 'ld_max': 3.6}) > 2
    span = breguet_cruise_range_m(250, 2e-5, 6, 1000, 800)
    expect = (250 / (G0 * 2e-5)) * 6 * math.log(1000 / 800)
    assert span == pytest.approx(expect)
    with pytest.raises(ValueError):
        breguet_cruise_range_m(250, 2e-5, 6, 800, 800)
    climb = climb_fuel_kg(1000, 10000, 0, 0.3)
    assert climb == pytest.approx(1000 * G0 * 10000 / (LHV_J_KG * 0.3))
    prop, fuel, mass = split_boost_and_fuel(1.2, 800, 400, 260, 1760, 810, 0.3)
    assert prop > 0 and fuel > 0 and mass > 800
    assert achieved_boost_dv_m_s(prop, mass, 260) > 0
    assert achieved_boost_dv_m_s(0, mass, 260) == 0
    assert drag_coast_range_m(900, 400, 800, 0.5) > 0
    assert drag_coast_range_m(300, 400, 800, 0.5) == 0
    assert terminal_dash_range_m(1200, 250, 0.5, 260, 250) > 0
    assert terminal_dash_range_m(1200, 0, 0.5, 260, 250) == 0
    short = ballistic_range_km(900, 0)
    assert 40 < short < 160
    assert burnout_altitude_km(3000, 0) > burnout_altitude_km(1000, 0)
    assert ballistic_loss_m_s(2000, 40, 0) > ballistic_loss_m_s(2000, 40, 12)
    assert ballistic_liftoff_twr(400) > ballistic_liftoff_twr(8000)
    assert ballistic_liftoff_twr(20000) == pytest.approx(2.3, abs=0.05)
    with pytest.raises(ValueError):
        ballistic_liftoff_twr(0)
    assert ballistic_burn_time_s(500, 1000, 250) == pytest.approx(500 * 250 / (2.3 * 1000))
    light_twr = ballistic_liftoff_twr(500)
    assert ballistic_burn_time_s(500, 1000, 250, light_twr) == pytest.approx(
        500 * 250 / (light_twr * 1000)
    )
    dv = _ideal_two_stage_dv(1000, 600, 90, 2500)
    assert dv > 0
    packed = _base_fields('ramjet', 2000, 1.2, 6, 400, 3, 3.2, 800.04, '说明', range_high_km=None)
    assert packed['range_km'] == 800.0
    assert packed['class_label'] == '亚燃冲压导弹'
    assert packed['range_high_km'] is None


def test_ballistic_nose_holds_guidance_and_warhead():
    """头锥按长径比占容积，制导和战斗部先扣锥内，装不下再占用后面的圆柱。"""
    import math

    from utils.missile_range.classes import (
        BALLISTIC_GUIDANCE_DENSITY_KG_M3,
        BALLISTIC_NOSE_FINENESS,
        BALLISTIC_WARHEAD_DENSITY_KG_M3,
        ballistic_body_volume_m3,
        ballistic_coast_range_km,
        ballistic_guidance_mass_kg,
        ballistic_head_lengths_m,
        ballistic_nose_length_m,
        estimate_ballistic,
    )
    from utils.missile_range.estimate import head_and_booster_lengths_m, head_volume_m3, uncapped_head_length_m

    nose = ballistic_nose_length_m(4.0, 0.43)
    assert nose == pytest.approx(BALLISTIC_NOSE_FINENESS * 0.43)
    area = math.pi * (0.43 / 2.0) ** 2
    cone = area * nose / 3.0
    guidance = ballistic_guidance_mass_kg(0.43)
    payload = 91 / BALLISTIC_WARHEAD_DENSITY_KG_M3 + guidance / BALLISTIC_GUIDANCE_DENSITY_KG_M3
    assert payload > cone
    head, boost, guide = ballistic_head_lengths_m(4.0, 0.43, 91)
    assert guide == pytest.approx(guidance)
    assert head == pytest.approx(nose + (payload - cone) / area, abs=0.01)
    assert head > nose
    bi, _ = head_and_booster_lengths_m(4.0, 0.43, 91, 'biconic')
    assert head < bi
    assert boost == pytest.approx(4.0 - head)
    full = math.pi * (0.43 / 2.0) ** 2 * 4.0
    assert ballistic_body_volume_m3(4.0, 0.43) == pytest.approx(full - area * nose * 2.0 / 3.0)
    assert ballistic_guidance_mass_kg(0.9) > ballistic_guidance_mass_kg(0.3)
    raw_bi = uncapped_head_length_m(head_volume_m3(90, 'biconic'), 0.227, 'biconic')
    assert raw_bi > 3.96
    gmlrs_head, _, _ = ballistic_head_lengths_m(3.96, 0.227, 90)
    assert gmlrs_head > ballistic_nose_length_m(3.96, 0.227)
    assert gmlrs_head < 3.96 * 0.65
    from utils.missile_range.classes import (
        ballistic_nose_propellant_kg,
        ballistic_nose_propellant_volume_m3,
    )
    from utils.missile_range.estimate import CHAMBER_FILL, motor_cross_section_m2

    assert ballistic_nose_propellant_volume_m3(4.0, 0.43, 91) == 0.0
    assert ballistic_nose_propellant_kg(4.0, 0.43, 91, 1760) == 0.0
    leftover = ballistic_nose_propellant_volume_m3(9.1, 1.0, 500)
    assert leftover > 0.1
    body_area = math.pi * (1.0 / 2.0) ** 2
    grain = motor_cross_section_m2(1.0) / body_area * CHAMBER_FILL
    assert ballistic_nose_propellant_kg(9.1, 1.0, 500, 1760) == pytest.approx(leftover * grain * 1760)
    df15 = estimate_ballistic(9.1, 1.0, 500, 0, 0, 264, 1760)
    assert df15['m_p_total_kg'] > 4625.0
    assert df15['range_km'] == 487.2
    with pytest.raises(ValueError):
        ballistic_nose_propellant_volume_m3(0, 1.0, 10)
    with pytest.raises(ValueError):
        ballistic_nose_propellant_kg(9.1, 1.0, 500, 0)
    with pytest.raises(ValueError):
        ballistic_nose_length_m(0, 0.4)
    with pytest.raises(ValueError):
        ballistic_guidance_mass_kg(0)
    with pytest.raises(ValueError):
        ballistic_body_volume_m3(4, 0)
    with pytest.raises(ValueError):
        ballistic_head_lengths_m(0, 0.4, 10)
    with pytest.raises(ValueError):
        ballistic_head_lengths_m(4, 0, 10)
    with pytest.raises(ValueError):
        ballistic_head_lengths_m(4, 0.4, -1)

    assert ballistic_coast_range_km(500, 2000, 30, 800, 0.5) > ballistic_coast_range_km(500, 2000, 0, 800, 0.5)
    assert ballistic_coast_range_km(500, 2000, 0, 2000, 0.5) > ballistic_coast_range_km(500, 2000, 0, 400, 0.5)
    assert ballistic_coast_range_km(0, 2000, 0, 800, 0.5) == 0
    assert ballistic_coast_range_km(500, 0, 0, 800, 0.5) == 0
    with pytest.raises(ValueError):
        ballistic_coast_range_km(-1, 100, 0, 800, 0.5)
    with pytest.raises(ValueError):
        ballistic_coast_range_km(100, 100, 0, 0, 0.5)

    default_stage = estimate_ballistic(4.0, 0.43, 91, 0, 0, 264, 1760)
    assert default_stage['range_km'] == 410.5
    assert default_stage['n_stages'] == 1
    assert '单级' in default_stage['note']

    # 双锥体装不进全长 45% 时弹头加长、助推级缩短，真空单级射程随之下降。
    legacy = estimate_ballistic(
        4.8, 0.40, 200, 0, 0, 264, 1760,
        warhead_section='biconic', coast_drag=False, single_stage=True,
    )
    assert legacy['range_km'] == 187.4
    gmlrs = estimate_ballistic(3.96, 0.227, 90, 0, 0, 264, 1760)
    assert 65.0 <= gmlrs['range_km'] <= 92.0
    with pytest.raises(ValueError, match='战斗部截面'):
        estimate_ballistic(4.0, 0.43, 91, 0, 0, 264, 1760, warhead_section='ogive')


def test_six_classes_ranges_and_profiles():
    from utils.missile_range.classes import (
        estimate_ballistic,
        estimate_by_class,
        estimate_ducted,
        estimate_subsonic_class,
        estimate_turbofan_rocket,
        terminal_propellant_for_dash,
        _ROCKET_CRUISE,
    )

    same = dict(length_m=6.2, diameter_m=0.55, warhead_mass_kg=450, v_launch_mach=0.7, h_launch_km=0.2)
    stealth = estimate_subsonic_class('涡扇隐身', **same)
    plain = estimate_subsonic_class('涡喷', **same)
    assert stealth['range_high_km'] == 1203.9
    assert stealth['range_sea_km'] == 621.7
    assert stealth['cruise_alt_km'] == 10.0
    assert '30 m' in stealth['note']
    assert '掠海升阻比' in stealth['note']
    assert stealth['m_wing_kg'] == 84.4
    assert stealth['m_dead_kg'] == 645.8
    assert '折叠弹翼' in stealth['note']
    assert stealth['range_high_km'] > stealth['range_mixed_km'] > stealth['range_sea_km']
    assert '混合弹道' in stealth['note']
    assert '中空 380 m' in stealth['note']
    assert plain['range_high_km'] > plain['range_mixed_km'] > plain['range_sea_km']
    heavier = estimate_subsonic_class('turbofan_stealth', 6.2, 0.55, 700, 0.7, 0.2)
    assert heavier['range_km'] < stealth['range_km']

    scram = estimate_ducted('scramjet', 9.2, 0.7, 180, 0.85, 12, 264, 1760)
    ram = estimate_ducted('ramjet', 8.9, 0.7, 250, 0.85, 12, 264, 1760)
    assert scram['range_km'] == 1925.2
    assert scram['cruise_mach'] == 5.2
    assert ram['range_km'] == 1846.8
    assert ram['cruise_alt_km'] == 10.0
    assert ram['v_burnout_mach'] == 2.8
    assert scram['range_sea_km'] is None
    assert scram['range_mixed_km'] is None
    assert ram['range_high_km'] > ram['range_mixed_km'] > ram['range_sea_km'] > 0
    assert '混合弹道' in ram['note']

    prop, sized = terminal_propellant_for_dash(8.2, 0.53, 300, 0.7, 0.05, 264, 1760, _ROCKET_CRUISE)
    assert prop > 0 and sized['fuel_kg'] > 0
    combo = estimate_turbofan_rocket(8.2, 0.53, 300, 0.7, 0.05, 264, 1760)
    assert combo['range_terminal_km'] is None
    assert combo['range_high_km'] - combo['range_cruise_km'] == pytest.approx(33.6, abs=0.2)
    assert combo['range_high_km'] > combo['range_mixed_km'] > combo['range_sea_km']
    assert combo['range_km'] == combo['range_high_km']
    assert '视距冲刺' in combo['note']
    assert combo['range_high_km'] - combo['range_mixed_km'] < 0.5 * (
        combo['range_high_km'] - combo['range_sea_km']
    )
    same_combo = estimate_turbofan_rocket(6.2, 0.55, 450, 0.7, 0.2, 264, 1760)
    assert same_combo['range_high_km'] < stealth['range_high_km']

    short = estimate_ballistic(4.8, 0.40, 200, 0, 0, 264, 1760)
    long = estimate_ballistic(11.2, 0.88, 980, 0, 0, 264, 1760)
    assert short['range_km'] == 204.9
    assert long['range_km'] == 351.6
    assert long['range_km'] > short['range_km']
    assert long['n_stages'] == 1
    assert '单级' in long['note']
    assert '头锥扣除制导与战斗部' in long['note']
    # PrSM Increment 1：4.0 m × 0.43 m、战斗部 91 kg、地面发射。搜索后取单级，410.5 km。
    prsm = estimate_ballistic(4.0, 0.43, 91, 0, 0, 264, 1760)
    assert prsm['range_km'] == 410.5
    same = dict(length_m=10.5, diameter_m=1.1, warhead_mass_kg=200, v_launch_mach=0.85, h_launch_km=13.0)
    glide = estimate_by_class('hgv_biconic', **same)
    ballistic_air = estimate_by_class('ballistic', **same)
    assert glide['range_km'] - ballistic_air['range_km'] > 1000
    legacy = estimate_by_class('hgv', 10.5, 1, 200)
    assert legacy['optimal_geometry'] is True
    assert legacy['d_head_m'] < 1.0
    assert legacy['range_km'] > 4000
    assert legacy['missile_class'] == 'hgv_biconic'
    wave = estimate_by_class('乘波体助推滑翔', 10.5, 1, 200, 0.85, 13, 264, 1760)
    assert wave['missile_class'] == 'hgv_waverider'
    assert wave['range_km'] == estimate_hgv(10.5, 1, 200, 'waverider', optimize_geometry=True)['range_km']
    assert wave['range_km'] != legacy['range_km']
    with pytest.raises(ValueError):
        estimate_subsonic_class('ramjet', 6, 0.5, 100, 0.7, 1)
    # 冲压、亚音速与弹道。歼-36 弹仓和单独的轰-6 发射隐轰组已去掉。
    assert len(PROPULSION_DATASET) == 80
    labels = {row['missile_class'] for row in PROPULSION_DATASET}
    assert labels == {
        'scramjet', 'ramjet', 'turbofan_stealth',
        'turbojet_subsonic', 'turbofan_rocket', 'ballistic',
    }


def test_folded_wing_mass_occupies_fuel_and_deadweight():
    """弹翼折进弹体：质量进入死重，容积挤占燃油。"""
    from utils.missile_range.classes import (
        _SUBSONIC_SPECS,
        cruise_range_pair_km,
        deadweight_kg,
        folded_wing_package,
        isa_density_kg_m3,
        stow_folded_wing,
    )

    assert isa_density_kg_m3(0) == pytest.approx(1.225, rel=1e-3)
    assert isa_density_kg_m3(10) < isa_density_kg_m3(0)
    with pytest.raises(ValueError):
        isa_density_kg_m3(-1)
    area, mass, volume = folded_wing_package(1000, 0.75, 10, 0.7)
    assert area > 0 and mass > 0 and volume > 0
    with pytest.raises(ValueError):
        folded_wing_package(0, 0.75, 10, 0.7)
    with pytest.raises(ValueError, match='折进弹体'):
        folded_wing_package(8000, 0.75, 10, 0.05)
    shrunk_area, _, shrunk_volume, fill = stow_folded_wing(800, 0.75, 10, 0.48, 0.01)
    assert fill < 1
    assert shrunk_area < area
    assert shrunk_volume <= 0.01 + 1e-9
    with pytest.raises(ValueError, match='燃油舱'):
        stow_folded_wing(400, 0.75, 10, 0.5, 0)
    assert deadweight_kg(1000, 200, 100, 50) == 650
    with pytest.raises(ValueError):
        deadweight_kg(10, 20, 5)

    kwargs = dict(length_m=6.35, diameter_m=0.69, warhead_mass_kg=1000, v_launch_mach=0.85, h_launch_km=15)
    spec = dict(_SUBSONIC_SPECS['turbofan_stealth'])
    folded = cruise_range_pair_km(spec=spec, **kwargs)
    spec['folded_wing'] = 0
    bare = cruise_range_pair_km(spec=spec, **kwargs)
    assert folded['m_wing_kg'] > 0
    assert folded['fuel_kg'] < bare['fuel_kg']
    assert deadweight_kg(folded['m_0'], folded['fuel_kg'], 1000) > deadweight_kg(
        bare['m_0'], bare['fuel_kg'], 1000,
    )


def test_presets_follow_bay_list_for_each_speed_class():
    """超音速弹种共用 CSV 超音速弹仓，亚音速（含亚超结合）共用亚音速弹仓；
    弹种专属行覆盖同弹仓的共用行。"""
    from utils.missile_range.dataset import (
        SUBSONIC_CLASSES,
        SUPERSONIC_CLASSES,
        build_preset_cases,
        grouped_preset_bays,
    )

    grouped = grouped_preset_bays()
    cases = build_preset_cases()
    # 去掉歼-36 弹仓、歼-36 弹仓的歼-15 发射，以及单独的轰-6 发射隐轰组。
    # 533 mm 弹道多 300 kg；亚音速鱼雷管多 300/600 kg；地面战术弹与火箭炮另计。合计 106。
    assert [case['id'] for case in cases] == list(range(1, 107))

    # 共用的弹仓行。533 mm 弹道的专属行不计入共用行。
    super_generic = [
        (bay['bay'], length, diameter, warhead, bay['v_mach'], bay['h_km'])
        for bay in grouped['supersonic']
        if bay.get('missile_class') is None
        for length, diameter, warhead in bay['rounds']
    ]
    sub_generic = [
        (bay['bay'], length, diameter, warhead, bay['v_mach'], bay['h_km'])
        for bay in grouped['subsonic']
        if bay.get('missile_class') is None
        for length, diameter, warhead in bay['rounds']
    ]
    assert len(super_generic) == 9
    assert len(sub_generic) == 8
    assert any(item[0] == '1280垂发' for item in super_generic)
    assert any(item[0] == '533mm鱼雷' and item[3] == 600 for item in sub_generic)
    assert 'ballistic' in SUPERSONIC_CLASSES
    assert 'turbofan_rocket' in SUBSONIC_CLASSES
    assert 'turbofan_rocket' not in SUPERSONIC_CLASSES

    # 亚燃没有 533 mm 专属覆盖，前 9 条仍是共用行，其后是机腹、翼下和 750 战术导弹。
    for missile_class in SUPERSONIC_CLASSES:
        got = [
            (case['bay'], case['length'], case['diameter'], case['warhead'], case['v_mach'], case['h_km'])
            for case in cases if case['missile_class'] == missile_class
        ]
        if missile_class == 'ramjet':
            assert len(got) == 14
            assert got[:9] == super_generic
        elif missile_class == 'ballistic':
            assert len(got) == 23
            assert got[:9] == super_generic
        elif missile_class in ('hgv_biconic', 'hgv_waverider', 'scramjet'):
            assert len(got) == 13
            assert got[:9] == super_generic
    for missile_class in SUBSONIC_CLASSES:
        got = [
            (case['bay'], case['length'], case['diameter'], case['warhead'], case['v_mach'], case['h_km'])
            for case in cases if case['missile_class'] == missile_class
        ]
        # 共用行含鱼雷管 160/300/600 kg，其后还有机腹和翼下两条歼-15 专属样例
        assert len(got) == 10
        assert got[:8] == sub_generic

    assert not any(case['bay'] in ('歼-36弹仓', '歼-36弹仓·歼-15发射') for case in cases)
    assert not any(case['bay'] == '超音速隐身轰炸机·轰6发射' for case in cases)

    assert all(row['range_km'] > 0 for row in evaluate_dataset())


def test_tube_and_ground_launcher_presets():
    """533 mm 鱼雷管补亚音速与弹道战斗部；地面战术弹和火箭炮按给定尺寸冷发射。"""
    from utils.missile_range.classes import estimate_by_class
    from utils.missile_range.dataset import SUBSONIC_CLASSES, build_preset_cases

    cases = build_preset_cases()

    def pick(bay: str, missile_class: str) -> list[dict]:
        return [
            case for case in cases
            if case['bay'] == bay and case['missile_class'] == missile_class
        ]

    tube_sub = {missile_class: pick('533mm鱼雷', missile_class) for missile_class in SUBSONIC_CLASSES}
    for missile_class, rows in tube_sub.items():
        assert {row['warhead'] for row in rows} == {160, 300, 600}
        assert all(row['length'] == pytest.approx(6.35) and row['diameter'] == pytest.approx(0.51) for row in rows)
        assert all(row['v_mach'] == 0 and row['h_km'] == 0 for row in rows)
    tube_ballistic = pick('533mm鱼雷', 'ballistic')
    assert {row['warhead'] for row in tube_ballistic} == {160, 300}
    assert all(row['v_mach'] == 0 and row['h_km'] == 0 for row in tube_ballistic)

    expected = {
        ('750战术导弹', 'ramjet'): {(7.80, 0.750, 500)},
        ('750战术导弹', 'ballistic'): {(7.80, 0.750, 150), (7.80, 0.750, 300)},
        ('370远火', 'ballistic'): {(7.80, 0.370, 90), (7.80, 0.370, 160), (7.80, 0.370, 300)},
        ('300远火', 'ballistic'): {(7.30, 0.300, 300)},
        ('海马斯火箭弹', 'ballistic'): {(3.96, 0.227, 90)},
        ('PrSM', 'ballistic'): {(4.00, 0.430, 90)},
        ('ATACMS', 'ballistic'): {(4.70, 0.470, 90)},
    }
    for (bay, missile_class), sizes in expected.items():
        rows = pick(bay, missile_class)
        assert {
            (round(row['length'], 2), round(row['diameter'], 3), row['warhead'])
            for row in rows
        } == sizes
        assert all(row['v_mach'] == 0 and row['h_km'] == 0 for row in rows)
        for row in rows:
            result = estimate_by_class(
                row['missile_class'], row['length'], row['diameter'], row['warhead'],
                row['v_mach'], row['h_km'],
            )
            assert result['range_km'] > 0
            assert result['m_0_t'] > 0


def test_carrier_launch_envelope():
    """歼-36、中型六代机、歼-15、轰-6 与隐身超音速轰炸机按给定极速和升限发射。"""
    from utils.missile_range.dataset import build_preset_cases

    expected = {
        '中型六代机弹仓': (1.75, 18.0),
        '歼-15机腹': (1.5, 14.0),
        '歼-15翼下': (1.5, 14.0),
        '隐身超音速轰炸机弹仓': (1.75, 18.0),
        '轰-6机腹最大': (0.85, 13.0),
    }
    seen = {bay: 0 for bay in expected}
    for case in build_preset_cases():
        bay = case['bay']
        if bay not in expected:
            continue
        mach, height = expected[bay]
        assert case['v_mach'] == pytest.approx(mach)
        assert case['h_km'] == pytest.approx(height)
        seen[bay] += 1
    assert all(count > 0 for count in seen.values())


def test_j15_wing_presets_stay_inside_pylon_box():
    """歼-15 翼下弹长 6.5 m，全部弹种起飞质量不超过 1500 kg。

    超音速除亚燃外仍是弹径 0.50 m。亚燃助推按轰-6 切分，弹径收到质量上限。
    亚音速弹径不超过 0.60 m。冲压战斗部 300 kg，三种高超 200 kg，普通弹道和亚音速 500 kg。
    """
    from utils.missile_range.dataset import J15_HYPERSONIC_CLASSES, evaluate_dataset

    wings = [row for row in evaluate_dataset() if row['bay'] == '歼-15翼下']
    assert len(wings) == 8
    for row in wings:
        assert row['length_m'] == pytest.approx(6.50)
        assert row['m_0_t'] <= 1.50
        assert row['range_km'] > 0
        if row['missile_class'] in ('turbofan_stealth', 'turbojet_subsonic', 'turbofan_rocket'):
            assert row['diameter_m'] <= 0.60
            assert row['warhead_kg'] == 500
            if row['diameter_m'] < 0.60:
                assert row['m_0_t'] == pytest.approx(1.50)
        else:
            assert row['diameter_m'] == pytest.approx(0.50)
            if row['missile_class'] == 'ramjet':
                assert row['warhead_kg'] == 300
            elif row['missile_class'] in J15_HYPERSONIC_CLASSES:
                assert row['warhead_kg'] == 200
            else:
                assert row['missile_class'] == 'ballistic'
                assert row['warhead_kg'] == 500


def test_j15_belly_presets_hold_2500kg():
    """歼-15 机腹仍是 8.5 m、2500 kg 档，弹径不超过 0.70 m。

    助推切分按轰-6 发射条件冻结后再核算质量。三种高超战斗部 300 kg，其余 500 kg。
    弹径还能加粗时，冻结结构的起飞质量贴住 2500 kg。
    """
    from utils.missile_range.dataset import J15_HYPERSONIC_CLASSES, evaluate_dataset

    bellies = [row for row in evaluate_dataset() if row['bay'] == '歼-15机腹']
    assert len(bellies) == 8
    for row in bellies:
        assert row['length_m'] == pytest.approx(8.50)
        assert row['diameter_m'] <= 0.70
        if row['missile_class'] in J15_HYPERSONIC_CLASSES:
            assert row['warhead_kg'] == 300
        else:
            assert row['warhead_kg'] == 500
        assert row['m_0_t'] <= 2.50
        if row['diameter_m'] < 0.70:
            assert row['m_0_t'] == pytest.approx(2.50, abs=0.02)
        assert row['range_km'] > 0
        assert [item['label'] for item in row['alt_launches']] == ['轰-6', '轰-20', '歼-36']


def test_j36_bay_presets_removed():
    """歼-36 弹仓和歼-36 弹仓·歼-15 发射不再单列预设。"""
    from utils.missile_range.dataset import build_preset_cases

    bays = {case['bay'] for case in build_preset_cases()}
    assert '歼-36弹仓' not in bays
    assert '歼-36弹仓·歼-15发射' not in bays


def test_j15_alt_launches_keep_structure_on_panel():
    """翼下按歼-15 定结构；机腹按轰-6 定助推切分。面板仍给轰-6、轰-20、歼-36 射程。"""
    from utils.missile_range.classes import estimate_by_class
    from utils.missile_range.dataset import (
        H6_STRUCTURE_LAUNCH,
        J15_ALT_LAUNCHES,
        J15_STRUCTURE_BAYS,
        evaluate_dataset,
    )

    rows = [
        row for row in evaluate_dataset()
        if row['bay'] in J15_STRUCTURE_BAYS
    ]
    assert len(rows) == 16
    assert not any('轰-6发射' in str(row['bay']) for row in rows)
    for row in rows:
        assert row['alt_range_text']
        expected_launches = J15_ALT_LAUNCHES
        assert len(row['alt_launches']) == len(expected_launches)
        for launch, expected in zip(row['alt_launches'], expected_launches):
            label, mach, height = expected
            assert launch['label'] == label
            assert launch['v_mach'] == pytest.approx(mach)
            assert launch['h_km'] == pytest.approx(height)
            assert launch['range_km'] > 0
        if row['missile_class'] in ('hgv_biconic', 'hgv_waverider'):
            assert row['l_head_m'] > 0
            assert row['d_head_m'] > 0
            assert row['stage_split']
        if row['range_sea_km'] is not None:
            assert row['profile_text'].count('/') == 2
            assert ' · ' in row['alt_range_text']
        if row['bay'] == '歼-15机腹' and row['missile_class'] in (
            'hgv_biconic', 'hgv_waverider', 'ballistic',
        ):
            ref = estimate_by_class(
                row['missile_class'], row['length_m'], row['diameter_m'], row['warhead_kg'],
                *H6_STRUCTURE_LAUNCH,
            )
            assert row['stage_split'] == ref['stage_split']


def test_fighter_bay_uses_unified_sizes():
    """普通战斗机弹仓：亚音速 4.25 x 0.505、战斗部 300 kg；广义超音速 4.25 x 0.415、战斗部 120 kg。"""
    from utils.missile_range.dataset import SUBSONIC_CLASSES, SUPERSONIC_CLASSES, build_preset_cases

    cases = [case for case in build_preset_cases() if case['bay'] == '普通战斗机弹仓']
    super_cases = [case for case in cases if case['missile_class'] in SUPERSONIC_CLASSES]
    sub_cases = [case for case in cases if case['missile_class'] in SUBSONIC_CLASSES]
    assert {case['missile_class'] for case in super_cases} == set(SUPERSONIC_CLASSES)
    assert {case['missile_class'] for case in sub_cases} == set(SUBSONIC_CLASSES)
    for case in super_cases:
        assert (case['length'], case['diameter'], case['warhead']) == pytest.approx((4.25, 0.415, 120))
        assert (case['v_mach'], case['h_km']) == pytest.approx((1.50, 14.0))
    for case in sub_cases:
        assert (case['length'], case['diameter'], case['warhead']) == pytest.approx((4.25, 0.505, 300))
        assert (case['v_mach'], case['h_km']) == pytest.approx((1.50, 14.0))


def test_fighter_bay_hgv_masses_differ_and_lists_bomber_ranges():
    """战斗机弹仓里乘波体弹头更长、总重更轻；轰-20 / 歼-36 用优化后的同一构型另算射程。"""
    from utils.missile_range.classes import estimate_by_class
    from utils.missile_range.dataset import FIGHTER_ALT_LAUNCHES, evaluate_dataset
    from utils.missile_range.estimate import parse_stage_fractions

    rows = [row for row in evaluate_dataset() if row['bay'] == '普通战斗机弹仓']
    assert rows
    for row in rows:
        assert row['v_mach'] == pytest.approx(1.50)
        assert row['h_km'] == pytest.approx(14.0)
        if row['missile_class'] == 'ramjet':
            continue
        assert [item['label'] for item in row['alt_launches']] == [
            label for label, _, _ in FIGHTER_ALT_LAUNCHES
        ]
        for launch, expected in zip(row['alt_launches'], FIGHTER_ALT_LAUNCHES):
            _label, mach, height = expected
            assert launch['v_mach'] == pytest.approx(mach)
            assert launch['h_km'] == pytest.approx(height)
            assert launch['range_km'] > 0
    wave = next(row for row in rows if row['missile_class'] == 'hgv_waverider')
    bic = next(row for row in rows if row['missile_class'] == 'hgv_biconic')
    assert wave['l_head_m'] > bic['l_head_m']
    assert wave['m_0_t'] < bic['m_0_t']
    assert wave['warhead_kg'] == bic['warhead_kg']
    j36 = next(item for item in wave['alt_launches'] if item['label'] == '歼-36')
    h20 = next(item for item in wave['alt_launches'] if item['label'] == '轰-20')
    assert h20['v_mach'] == pytest.approx(1.75)
    assert h20['h_km'] == pytest.approx(18.0)
    assert j36['v_mach'] == pytest.approx(2.15)
    assert j36['h_km'] == pytest.approx(20.0)
    locked = estimate_by_class(
        'hgv_waverider', wave['length_m'], wave['diameter_m'], wave['warhead_kg'],
        j36['v_mach'], j36['h_km'],
        l_head_m=wave['l_head_m'],
        d_head_m=wave['d_head_m'],
        stage_fractions=parse_stage_fractions(wave['stage_split']),
    )
    assert j36['range_km'] == pytest.approx(locked['range_km'], abs=0.2)


def test_format_cruise_profile_joins_three_ranges():
    """巡航三档射程用斜线收成一栏；没有掠海档时不给这栏。"""
    from utils.missile_range.dataset import format_alt_launch_text, format_cruise_profile

    assert format_cruise_profile({
        'range_high_km': 1200.0, 'range_mixed_km': 800.5, 'range_sea_km': 400.0,
    }) == '1200.0/800.5/400.0'
    assert format_cruise_profile({'range_high_km': 10.0, 'range_sea_km': 4.0}) == '10.0/—/4.0'
    assert format_cruise_profile({'range_km': 10.0}) is None
    assert format_alt_launch_text(['1.0', '2.0', '3.0']) == '1.0 · 2.0 · 3.0'
    with pytest.raises(ValueError, match='三档射程'):
        format_alt_launch_text(['1.0', '2.0'])


def test_parse_stage_fractions_round_trip():
    """分级文案能还原成份额，单级是 100。"""
    from utils.missile_range.estimate import format_stage_split, parse_stage_fractions

    assert parse_stage_fractions('70/30') == (0.70, 0.30)
    assert parse_stage_fractions('100') == (1.0,)
    assert format_stage_split(parse_stage_fractions('64/26/10')) == '64/26/10'
    with pytest.raises(ValueError):
        parse_stage_fractions('70/20')


def test_layout_fixed_booster_keeps_propellant():
    """锁定助推药后，燃油只填剩余容积，不再按速度增量重切。"""
    from utils.missile_range.classes import layout_fixed_booster

    propellant, fuel, launch = layout_fixed_booster(
        0.20, 40.0, 200.0, 1760.0, 800.0, 0.25,
    )
    assert propellant == pytest.approx(40.0)
    assert fuel > 0
    assert launch > 200.0 + fuel
    with pytest.raises(ValueError):
        layout_fixed_booster(0.05, 500.0, 200.0, 1760.0, 800.0, 0.25)


def test_diameter_for_liftoff_mass_hits_target_or_cap():
    """弹径收到目标质量；到上限仍偏轻时取上限。"""
    from utils.missile_range.sizing import diameter_for_liftoff_mass

    hit = diameter_for_liftoff_mass(
        'turbofan_stealth', 6.5, 500, 1.5,
        max_diameter_m=0.6, v_launch_mach=1.5, h_launch_km=14.0,
    )
    assert hit['diameter_m'] < 0.6
    assert hit['m_0_t'] == pytest.approx(1.5)
    capped = diameter_for_liftoff_mass(
        'turbojet_subsonic', 6.5, 500, 1.5,
        max_diameter_m=0.6, v_launch_mach=1.5, h_launch_km=14.0,
    )
    assert capped['diameter_m'] == pytest.approx(0.6)
    assert capped['m_0_t'] < 1.5
    with pytest.raises(ValueError):
        diameter_for_liftoff_mass(
            'turbofan_stealth', 6.5, 500, 0,
            max_diameter_m=0.6, v_launch_mach=1.5, h_launch_km=14.0,
        )


def test_locked_ramjet_booster_does_not_follow_launch_speed():
    """亚燃按歼-15 切好的助推药换平台时，助推器质量保持不变。"""
    from utils.missile_range.classes import BOOST_CASE_FRAC, estimate_by_class

    base = estimate_by_class('ramjet', 6.5, 0.5, 300, 1.5, 14.0)
    grain = base['m_booster_kg'] / (1.0 + BOOST_CASE_FRAC)
    slower = estimate_by_class(
        'ramjet', 6.5, 0.5, 300, 0.85, 13.0, booster_propellant_kg=grain,
    )
    faster = estimate_by_class(
        'ramjet', 6.5, 0.5, 300, 2.15, 20.0, booster_propellant_kg=grain,
    )
    assert slower['m_booster_kg'] == pytest.approx(base['m_booster_kg'], abs=0.2)
    assert faster['m_booster_kg'] == pytest.approx(base['m_booster_kg'], abs=0.2)
    assert slower['range_km'] > 0
    assert faster['range_km'] > 0


def test_airbreathing_range_model_differs_from_boost_and_ballistic():
    """吸气式走巡航航程，助推滑翔和弹道不走同一套。"""
    from utils.missile_range.classes import estimate_by_class

    geom = dict(length_m=10.5, diameter_m=1.1, warhead_mass_kg=200, v_launch_mach=0.85, h_launch_km=13.0)
    hgv = estimate_by_class('hgv_biconic', **geom)
    ballistic = estimate_by_class('ballistic', **geom)
    scram = estimate_by_class('scramjet', **geom)
    ram = estimate_by_class('ramjet', **geom)
    fan = estimate_by_class('turbofan_stealth', **geom)
    ranges = {hgv['range_km'], ballistic['range_km'], scram['range_km'], ram['range_km'], fan['range_km']}
    assert len(ranges) == 5
    assert hgv.get('range_sea_km') is None
    assert hgv.get('range_mixed_km') is None
    assert ballistic.get('range_sea_km') is None
    assert ballistic.get('range_mixed_km') is None
    assert '不含滑翔' in ballistic['note']
    assert scram['range_sea_km'] is None
    assert scram['range_mixed_km'] is None
    assert scram['cruise_alt_km'] == 24.0
    assert ram['cruise_alt_km'] == 10.0
    assert scram.get('m_wing_kg') is None
    assert ram['range_high_km'] > ram['range_mixed_km'] > ram['range_sea_km'] > 0
    assert fan['range_high_km'] > fan['range_mixed_km'] > fan['range_sea_km'] > 0
    assert fan['m_wing_kg'] > 0
    assert fan['m_dead_kg'] > fan['m_wing_kg']
    assert '折叠弹翼' in fan['note']
    slow = estimate_by_class('turbojet_subsonic', **geom, isp_s=180)
    fast = estimate_by_class('turbojet_subsonic', **geom, isp_s=320)
    assert slow['range_km'] == fast['range_km']
    assert slow['isp_cruise_s'] == fast['isp_cruise_s']
    assert slow['isp_cruise_s'] > 264
    assert estimate_by_class('hgv_biconic', **geom, isp_s=180)['range_km'] != estimate_by_class(
        'hgv_biconic', **geom, isp_s=320,
    )['range_km']
    assert estimate_by_class('ramjet', **geom, isp_s=180)['range_km'] != estimate_by_class(
        'ramjet', **geom, isp_s=320,
    )['range_km']


def test_build_preset_cases_rejects_unknown_class(monkeypatch):
    import utils.missile_range.dataset as dataset

    monkeypatch.setattr(dataset, 'MISSILE_CLASS_ORDER', [{'id': 'laser', 'label': '激光', 'blurb': ''}])
    with pytest.raises(ValueError, match='没有预设弹仓'):
        dataset.build_preset_cases()


def test_grouped_preset_bays_rejects_unknown_speed_group():
    """CSV 速度组必须是超音速或亚音速。"""
    from utils.missile_range.dataset import grouped_preset_bays

    with pytest.raises(ValueError, match='未知速度组'):
        grouped_preset_bays([{
            'speed_group': 'hypersonic',
            'bay': '试验',
            'length_m': 4.0,
            'diameter_m': 0.4,
            'warhead_kg': 100,
            'v_launch_mach': 0.0,
            'h_launch_km': 0.0,
        }])


def test_ramjet_launch_mass_matches_yj91():
    """鹰击-91 仍按 4.7 m×0.36 m 估算。质量锚在鹰击-15 后，这一发约为 0.66 t。"""
    from utils.missile_range.classes import estimate_by_class

    yj91 = estimate_by_class('ramjet', 4.7, 0.36, 90, 0.9, 10.0)
    assert yj91['m_0_t'] == pytest.approx(0.66, abs=0.02)
    fighter = estimate_by_class('ramjet', 4.25, 0.34, 90, 2.2, 19.0)
    assert fighter['m_0_t'] == pytest.approx(0.52, abs=0.03)
    scram = estimate_by_class('scramjet', 4.7, 0.36, 90, 0.9, 10.0)
    # 超燃燃烧室留空、助推另舱，同外形轻于固冲一体的亚燃。
    assert 0.45 <= scram['m_0_t'] < yj91['m_0_t']


def test_surface_static_launch_pays_booster_and_drag():
    """海面静止发射要比空射短：亚音速带可抛弃助推器，弹道多扣长时间燃烧的阻力。"""
    from utils.missile_range.classes import (
        ballistic_loss_m_s,
        booster_grain_volume_m3,
        dense_air_loss_frac,
        estimate_ballistic,
        estimate_by_class,
        jettisoned_booster_propellant_kg,
    )

    assert jettisoned_booster_propellant_kg(1200, 400, 10) == 0.0
    sea_prop = jettisoned_booster_propellant_kg(1200, 0, 0)
    high_prop = jettisoned_booster_propellant_kg(1200, 0, 10)
    assert sea_prop > high_prop > 0
    with pytest.raises(ValueError):
        jettisoned_booster_propellant_kg(0, 0, 0)
    with pytest.raises(ValueError):
        jettisoned_booster_propellant_kg(1000, -1, 0)
    assert booster_grain_volume_m3(0) == 0.0
    assert booster_grain_volume_m3(200) > 0
    with pytest.raises(ValueError):
        booster_grain_volume_m3(-1)
    assert dense_air_loss_frac(0.16, 10) == pytest.approx(0.16)
    assert dense_air_loss_frac(0.16, 14) == pytest.approx(0.16)
    assert dense_air_loss_frac(0.16, 0) == pytest.approx(0.16 * 1.8)
    with pytest.raises(ValueError):
        dense_air_loss_frac(-0.1, 0)
    assert ballistic_loss_m_s(3000, 80, 0) > ballistic_loss_m_s(3000, 40, 0) + 400

    tube = dict(length_m=6.35, diameter_m=0.51, warhead_mass_kg=160)
    surface = estimate_by_class('turbofan_stealth', **tube, v_launch_mach=0.0, h_launch_km=0.0)
    air = estimate_by_class('turbofan_stealth', **tube, v_launch_mach=0.85, h_launch_km=10.0)
    assert surface['m_0_t'] > air['m_0_t']
    assert surface['range_km'] < air['range_km']
    assert surface['range_sea_km'] < air['range_sea_km']
    assert '助推器' in surface['note']
    # 弹径是扁五边形的最大外廓，不是战斧的圆截面，同长度会比圆弹短一截。
    tomahawk = estimate_by_class('turbofan_stealth', 6.25, 0.52, 450, 0.0, 0.0)
    assert 700 <= tomahawk['range_high_km'] <= 1100
    assert tomahawk['range_sea_km'] < tomahawk['range_high_km']
    prsm = estimate_ballistic(4.0, 0.43, 91, 0, 0, 264, 1760)
    assert prsm['range_km'] == 410.5
    iskander = estimate_ballistic(7.3, 0.92, 480, 0, 0, 264, 1760)
    assert 350 <= iskander['range_km'] <= 400
    df15 = estimate_ballistic(9.1, 1.0, 500, 0, 0, 264, 1760)
    assert 450 <= df15['range_km'] <= 520
    assert '单级' in df15['note']


def test_stealth_pentagon_section_is_lighter_than_a_circle():
    """隐身巡航弹按宽高不同的五边形计容积，不用最大边长当圆直径。"""
    import math

    from utils.missile_range.classes import (
        estimate_by_class,
        outer_cross_section,
        packed_section_volume_m3,
        pentagon_cross_section,
        skin_mass_kg,
        _SUBSONIC_SPECS,
    )

    shoulder = _SUBSONIC_SPECS['turbofan_stealth']['pentagon_shoulder']
    area, perimeter = pentagon_cross_section(0.635, 0.450, shoulder)
    expect_area = 0.635 * 0.450 * (0.5 + 0.5 * shoulder)
    roof = (1.0 - shoulder) * 0.450
    expect_peri = 0.635 + 2.0 * shoulder * 0.450 + 2.0 * math.hypot(0.635 / 2.0, roof)
    assert area == pytest.approx(expect_area)
    assert perimeter == pytest.approx(expect_peri)
    assert area < math.pi * (0.635 / 2.0) ** 2
    with pytest.raises(ValueError):
        pentagon_cross_section(0, 0.4, shoulder)
    with pytest.raises(ValueError):
        pentagon_cross_section(0.4, 0.4, 0.01)
    circle = math.pi * (0.5 / 2.0) ** 2
    plain = outer_cross_section(0.5, {'areal': 1.0})
    assert plain['area'] == pytest.approx(circle)
    assert plain['d_eq'] == pytest.approx(0.5)
    stealth = outer_cross_section(0.635, _SUBSONIC_SPECS['turbofan_stealth'])
    explicit = outer_cross_section(
        0.635, _SUBSONIC_SPECS['turbofan_stealth'], width_m=0.635, height_m=0.450,
    )
    assert stealth['area'] == pytest.approx(explicit['area'])
    assert stealth['area'] < math.pi * (0.635 / 2.0) ** 2
    with pytest.raises(ValueError, match='同时给出'):
        outer_cross_section(0.5, _SUBSONIC_SPECS['turbofan_stealth'], width_m=0.5)
    assert packed_section_volume_m3(area, 4.26, 0.66) == pytest.approx(0.66 * area * 4.26)
    with pytest.raises(ValueError, match='装填系数'):
        packed_section_volume_m3(area, 4.26, 0.2)
    assert skin_mass_kg(perimeter, 4.26, 38.0) == pytest.approx(38.0 * perimeter * 4.26 * 1.15)
    with pytest.raises(ValueError):
        skin_mass_kg(perimeter, 4.26, 0)
    # JSM：宽 0.48 m、高 0.52 m。公开质量 416 kg，但外廓体积和 LRASM 接近，
    # 按同一套装填只能落到大约 0.84 t，仍高于公开值。
    jsm_area, _ = pentagon_cross_section(0.480, 0.520, shoulder)
    assert jsm_area < math.pi * (0.520 / 2.0) ** 2
    jsm = estimate_by_class(
        'turbofan_stealth', 4.00, 0.52, 120, 0.85, 10.0, width_m=0.480, height_m=0.520,
    )
    assert jsm['m_0_t'] == pytest.approx(0.84, abs=0.06)
    assert jsm['range_high_km'] > jsm['range_sea_km'] > 0


def test_duct_cruise_tsfc_penalizes_narrow_ramjets():
    """亚燃在 0.50 m 及以上共用鹰击-15 的耗油率，更细的弹更费油。超燃不随弹径改。"""
    from utils.missile_range.classes import _DUCT_SPECS, duct_cruise_tsfc

    ram = _DUCT_SPECS['ramjet']
    narrow = duct_cruise_tsfc('ramjet', 0.36, ram)
    yj15 = duct_cruise_tsfc('ramjet', 0.50, ram)
    oniks = duct_cruise_tsfc('ramjet', 0.70, ram)
    wide = duct_cruise_tsfc('ramjet', 1.20, ram)
    assert narrow > yj15 == oniks == wide == pytest.approx(1.0 / (1500.0 * 9.80665))
    assert duct_cruise_tsfc('scramjet', 0.36, _DUCT_SPECS['scramjet']) == pytest.approx(1.0 / (1200.0 * 9.80665))
    assert duct_cruise_tsfc('ramjet', 0.50, {'tsfc': 1.0e-4}) == pytest.approx(1.0e-4)
    with pytest.raises(ValueError):
        duct_cruise_tsfc('ramjet', 0, ram)
    with pytest.raises(ValueError):
        duct_cruise_tsfc('ramjet', 0.5, {**ram, 'tsfc_ref_diameter_m': 0})


def test_burke_radar_los_km_matches_horizon():
    """亚超结合末端冲刺取伯克级雷达对掠海目标的地球曲率视距。"""
    import math

    from utils.missile_interception.missile_interception_radar import radar_horizon_km
    from utils.missile_range.classes import (
        BURKE_RADAR_HEIGHT_M,
        BURKE_SEA_TARGET_HEIGHT_M,
        burke_radar_los_km,
    )

    assert BURKE_RADAR_HEIGHT_M == 25.0
    assert BURKE_SEA_TARGET_HEIGHT_M == 10.0
    expect = 4.12 * (math.sqrt(25.0) + math.sqrt(10.0))
    assert burke_radar_los_km() == pytest.approx(expect)
    assert burke_radar_los_km() == pytest.approx(radar_horizon_km(25.0, 10.0))
    with pytest.raises(ValueError):
        burke_radar_los_km(radar_height_m=-1)


def test_mixed_guidance_profile_splits_fuel_from_the_end():
    """混合弹道按视距定中低段，燃油从终点往回扣；油不够时先缩短中段。"""
    import math

    from utils.missile_interception.missile_interception_radar import radar_horizon_km
    from utils.missile_range.classes import (
        G0,
        GUIDANCE_SEARCH_HORIZON_FACTOR,
        breguet_cruise_range_m,
        breguet_fuel_for_range_kg,
        burke_radar_los_km,
        guidance_medium_altitude_m,
        guidance_search_horizon_km,
        mixed_guidance_legs_m,
        mixed_guidance_range_m,
        mixed_profile_sentence,
    )

    low = burke_radar_los_km()
    search = guidance_search_horizon_km()
    assert search == pytest.approx(GUIDANCE_SEARCH_HORIZON_FACTOR * low)
    alt_m = guidance_medium_altitude_m()
    assert alt_m == pytest.approx(379.7, abs=0.2)
    assert radar_horizon_km(alt_m, 25.0) == pytest.approx(search)
    with pytest.raises(ValueError, match='搜索视距倍数'):
        guidance_search_horizon_km(search_factor=0)
    with pytest.raises(ValueError, match='舰桅'):
        guidance_medium_altitude_m(radar_height_m=-1)
    with pytest.raises(ValueError, match='搜索视距必须大于 0'):
        guidance_medium_altitude_m(search_horizon_km=0)
    with pytest.raises(ValueError, match='无法反解'):
        guidance_medium_altitude_m(search_horizon_km=1.0)

    fuel = breguet_fuel_for_range_kg(80000, 250, 2e-5, 6, 800)
    assert fuel == pytest.approx(800 * math.expm1(80000 * G0 * 2e-5 / (250 * 6)))
    assert breguet_fuel_for_range_kg(0, 250, 2e-5, 6, 800) == 0
    recovered = breguet_cruise_range_m(250, 2e-5, 6, 800 + fuel, 800)
    assert recovered == pytest.approx(80000)
    with pytest.raises(ValueError, match='航程不能为负'):
        breguet_fuel_for_range_kg(-1, 250, 2e-5, 6, 800)
    with pytest.raises(ValueError, match='终点质量'):
        breguet_fuel_for_range_kg(1000, 250, 2e-5, 6, 0)

    full = mixed_guidance_legs_m(
        400, 600, 2e-5, 250, 6.0, 240, 3.0, 230, 2.0, 30000, 80000,
    )
    assert full['low_shortened'] is False and full['med_shortened'] is False
    assert full['range_low_m'] == 30000
    assert full['range_med_m'] == 80000
    assert full['range_high_m'] > 0
    assert full['range_m'] == pytest.approx(
        full['range_high_m'] + full['range_med_m'] + full['range_low_m']
    )
    all_high = breguet_cruise_range_m(250, 2e-5, 6.0, 1000, 600)
    all_low = breguet_cruise_range_m(230, 2e-5, 2.0, 1000, 600)
    assert all_low < full['range_m'] < all_high

    short_med = mixed_guidance_legs_m(
        80, 920, 2e-5, 250, 6.0, 240, 3.0, 230, 2.0, 20000, 500000,
    )
    assert short_med['low_shortened'] is False
    assert short_med['med_shortened'] is True
    assert short_med['range_high_m'] == 0
    assert 0 < short_med['range_med_m'] < 500000
    assert short_med['range_low_m'] == 20000

    short_low = mixed_guidance_legs_m(
        5, 995, 2e-5, 250, 6.0, 240, 3.0, 230, 2.0, 400000, 100000,
    )
    assert short_low['low_shortened'] is True
    assert short_low['med_shortened'] is True
    assert short_low['range_high_m'] == 0 and short_low['range_med_m'] == 0
    assert short_low['range_low_m'] == pytest.approx(
        breguet_cruise_range_m(230, 2e-5, 2.0, 1000, 995)
    )
    empty = mixed_guidance_legs_m(0, 1000, 2e-5, 250, 6, 240, 3, 230, 2, 1000, 1000)
    assert empty['range_m'] == 0 and empty['med_shortened'] is True
    with pytest.raises(ValueError, match='可用燃油'):
        mixed_guidance_legs_m(-1, 1000, 2e-5, 250, 6, 240, 3, 230, 2, 0, 0)
    with pytest.raises(ValueError, match='末端航段'):
        mixed_guidance_legs_m(10, 1000, 2e-5, 250, 6, 240, 3, 230, 2, -1, 0)
    with pytest.raises(ValueError, match='升阻比'):
        mixed_guidance_legs_m(10, 1000, 2e-5, 250, 0, 240, 3, 230, 2, 0, 0)

    profile = mixed_guidance_range_m(
        length_m=6.2,
        launch_mass_kg=1200,
        usable_fuel_kg=280,
        tsfc_kg_n_s=2.15e-5,
        ld_high=6.0,
        mach_high=0.8,
        alt_high_km=10.0,
        ld_low=2.4,
        mach_low=0.8,
        alt_low_km=0.03,
        cl_design=0.65,
        aspect_ratio=5.0,
        oswald=0.75,
    )
    assert profile['med_shortened'] is False and profile['low_shortened'] is False
    assert profile['range_low_m'] == pytest.approx(low * 1000)
    assert profile['range_med_m'] == pytest.approx(search * 1000)
    assert profile['alt_med_km'] == pytest.approx(alt_m / 1000.0)
    assert 2.0 < profile['ld_med'] < 6.0
    no_low = mixed_guidance_range_m(
        length_m=6.2,
        launch_mass_kg=1200,
        usable_fuel_kg=280,
        tsfc_kg_n_s=2.15e-5,
        ld_high=6.0,
        mach_high=0.8,
        alt_high_km=10.0,
        ld_low=2.4,
        mach_low=0.8,
        alt_low_km=0.03,
        cl_design=0.65,
        aspect_ratio=5.0,
        oswald=0.75,
        include_low_leg=False,
    )
    assert no_low['range_low_m'] == 0
    assert no_low['range_m'] > profile['range_m']
    fast_med = mixed_guidance_range_m(
        length_m=6.2,
        launch_mass_kg=1200,
        usable_fuel_kg=280,
        tsfc_kg_n_s=2.15e-5,
        ld_high=6.0,
        mach_high=2.8,
        alt_high_km=10.0,
        ld_low=2.4,
        mach_low=2.0,
        alt_low_km=0.03,
        cl_design=0.40,
        aspect_ratio=2.5,
        oswald=0.70,
        mach_med=2.0,
    )
    assert fast_med['ld_med'] < 6.0
    assert fast_med['range_m'] > 0
    with pytest.raises(ValueError, match='终点质量'):
        mixed_guidance_range_m(
            length_m=6.2, launch_mass_kg=200, usable_fuel_kg=200, tsfc_kg_n_s=2e-5,
            ld_high=5, mach_high=0.8, alt_high_km=10, ld_low=2, mach_low=0.8, alt_low_km=0.03,
            cl_design=0.6, aspect_ratio=5, oswald=0.7,
        )
    with pytest.raises(ValueError, match='中空马赫数'):
        mixed_guidance_range_m(
            length_m=6.2, launch_mass_kg=1200, usable_fuel_kg=200, tsfc_kg_n_s=2e-5,
            ld_high=5, mach_high=0.8, alt_high_km=10, ld_low=2, mach_low=0.8, alt_low_km=0.03,
            cl_design=0.6, aspect_ratio=5, oswald=0.7, mach_med=0,
        )

    sentence = mixed_profile_sentence(1073.4, alt_m, search, low, 2.84)
    assert '混合弹道 1073 km' in sentence
    assert '中空 380 m' in sentence
    assert '末段 34 km 掠海' in sentence
    dash = mixed_profile_sentence(832, alt_m, search, low, 1.87, dash_replaces_low=True)
    assert '视距冲刺' in dash
    short_txt = mixed_profile_sentence(
        40, alt_m, 12, 8, 2.1, med_shortened=True, low_shortened=True,
    )
    assert '搜索段缩短' in short_txt and '掠海段缩短' in short_txt
    with pytest.raises(ValueError, match='升阻比无效'):
        mixed_profile_sentence(10, alt_m, search, low, 0)


def test_sea_skim_ld_follows_dynamic_pressure():
    """掠海升阻比由动压和废阻推出，设计点原样返回，30 m 低于 10 km。"""
    import math

    from utils.missile_range.classes import (
        CRUISE_HIGH_ALT_KM,
        CRUISE_SEA_ALT_KM,
        FOLDED_WING_AR,
        FOLDED_WING_CL,
        FOLDED_WING_OSWALD,
        dynamic_pressure_pa,
        isa_temperature_k,
        parasite_friction_share,
        sea_skim_ld,
        skin_friction_ratio,
        speed_of_sound_m_s,
        sutherland_viscosity_pa_s,
        wing_polar,
    )

    assert CRUISE_HIGH_ALT_KM == 10.0
    assert CRUISE_SEA_ALT_KM == 0.030
    assert isa_temperature_k(0.0) == pytest.approx(288.15)
    assert isa_temperature_k(10.0) == pytest.approx(223.15)
    assert speed_of_sound_m_s(0.0) == pytest.approx(math.sqrt(1.4 * 287.05287 * 288.15))
    assert sutherland_viscosity_pa_s(288.15) > sutherland_viscosity_pa_s(223.15) > 0
    assert dynamic_pressure_pa(0.8, 0.03) > dynamic_pressure_pa(0.8, 10.0)
    assert parasite_friction_share(0.8) == 0.65
    assert parasite_friction_share(2.8) == 0.35
    assert skin_friction_ratio(5.0, 0.8, 10.0, 0.8, 10.0) == pytest.approx(1.0)
    assert skin_friction_ratio(5.0, 0.8, 0.03, 0.8, 10.0) < 1.0
    assert wing_polar({}) == (FOLDED_WING_CL, FOLDED_WING_AR, FOLDED_WING_OSWALD)
    assert wing_polar({'wing_cl': 0.4, 'wing_ar': 2.5, 'wing_oswald': 0.7}) == (0.4, 2.5, 0.7)
    same = sea_skim_ld(5.2, 0.8, 10.0, 0.8, 10.0, 6.0, 0.65, 5.0, 0.75)
    sea = sea_skim_ld(5.2, 0.8, 10.0, 0.8, 0.03, 6.0, 0.65, 5.0, 0.75)
    assert same == pytest.approx(5.2)
    assert sea < same
    with pytest.raises(ValueError):
        isa_temperature_k(-1)
    with pytest.raises(ValueError):
        sutherland_viscosity_pa_s(0)
    with pytest.raises(ValueError):
        dynamic_pressure_pa(0, 10)
    with pytest.raises(ValueError):
        parasite_friction_share(-0.1)
    with pytest.raises(ValueError):
        skin_friction_ratio(0, 0.8, 10, 0.8, 10)
    with pytest.raises(ValueError):
        wing_polar({'wing_cl': 0})
    with pytest.raises(ValueError):
        sea_skim_ld(0, 0.8, 10, 0.8, 0.03, 6, 0.65, 5, 0.75)


def test_public_airbreathing_ranges_match_open_sources():
    """用公开弹种核对吸气式航程，并检查垂发零速零高。"""
    from utils.missile_range.classes import estimate_by_class

    # 鹰击-15：6.5 m×0.50 m、战斗部 200 kg、Ma 0.9 @ 12 km。质量仍约 1.5 t。
    # 公开高空约 800 km；吸气比冲和升阻比按偏乐观取后，高空约 1140 km。
    # 掠海按 30 m 动压下的阻力估算，不再压到高空的 1/2.3。
    yj15 = estimate_by_class('ramjet', 6.5, 0.50, 200, 0.9, 12.0)
    assert yj15['m_0_t'] == pytest.approx(1.50, abs=0.05)
    assert yj15['cruise_alt_km'] == 10.0
    assert 1050 <= yj15['range_high_km'] <= 1250
    assert yj15['range_high_km'] > yj15['range_sea_km'] > 0.45 * yj15['range_high_km']
    assert '30 m' in yj15['note']
    # 缟玛瑙级弹径共用同一耗油率，装填按鹰击-15 加满后高空更长。
    oniks_m = estimate_by_class('ramjet', 8.9, 0.70, 300, 0.0, 0.0)
    assert oniks_m['m_0_t'] == pytest.approx(3.7, abs=0.3)
    assert oniks_m['cruise_alt_km'] == 10.0
    assert 1250 <= oniks_m['range_high_km'] <= 1550
    assert oniks_m['range_high_km'] > oniks_m['range_sea_km'] > 0.45 * oniks_m['range_high_km']
    # Kh-31PD：5.34 m×0.36 m、战斗部 110 kg，Ma 1.5 @ 15 km。公开最大 180–250 km，乐观化后约 340 km。
    kh31pd = estimate_by_class('ramjet', 5.34, 0.36, 110, 1.5, 15.0)
    assert kh31pd['m_0_t'] == pytest.approx(0.72, abs=0.08)
    assert 280 <= kh31pd['range_high_km'] <= 420
    brahmos = estimate_by_class('ramjet', 8.4, 0.70, 250, 0.0, 0.0)
    assert 1200 <= brahmos['range_km'] <= 1600
    assert brahmos['range_high_km'] > brahmos['range_sea_km'] > 0.45 * brahmos['range_high_km']
    kh31 = estimate_by_class('ramjet', 5.2, 0.36, 90, 0.9, 10.0)
    assert 220 <= kh31['range_km'] <= 360
    assert kh31['range_sea_km'] < kh31['range_high_km']
    moskit = estimate_by_class('ramjet', 9.4, 0.76, 320, 0.0, 0.0)
    assert moskit['cruise_alt_km'] == 10.0
    assert moskit['range_high_km'] > moskit['range_sea_km'] > 0.45 * moskit['range_high_km']
    fighter = estimate_by_class('ramjet', 4.25, 0.345, 90, 2.2, 19.0)
    assert fighter['range_km'] > kh31['range_sea_km']
    assert fighter['range_km'] > 200
    # 3M54K：8.22 m×0.533 m、战斗部 200 kg、全重约 1.95 t。全高空 10 km，掠海按阻力估算。
    # 末端冲刺统一为伯克级雷达视距，不单列。
    kalibr = estimate_by_class('turbofan_rocket', 8.22, 0.533, 200, 0.0, 0.0)
    assert kalibr['m_0_t'] == pytest.approx(1.95, abs=0.15)
    assert kalibr['cruise_alt_km'] == 10.0
    assert kalibr['range_high_km'] == 965.4
    assert kalibr['range_sea_km'] == 464.1
    assert kalibr['range_terminal_km'] is None
    air_kalibr = estimate_by_class('turbofan_rocket', 8.22, 0.533, 200, 0.85, 6.0)
    assert air_kalibr['range_high_km'] > kalibr['range_high_km']
    assert air_kalibr['range_sea_km'] > kalibr['range_sea_km']
    yj18 = estimate_by_class('turbofan_rocket', 8.2, 0.514, 200, 0.0, 0.0)
    assert yj18['range_high_km'] > yj18['range_sea_km'] > 0
    assert yj18['range_terminal_km'] is None
    assert 1.5 <= yj18['m_0_t'] <= 2.2
    # 涡喷巡航高度是 10 km。已经高于掠海、又超过接力速度时，降低发射高度只少高空爬升油。
    jet = estimate_by_class('turbojet_subsonic', 6.2, 0.55, 450, 0.85, 6.0)
    jet_low = estimate_by_class('turbojet_subsonic', 6.2, 0.55, 450, 0.85, 0.2)
    assert jet['cruise_alt_km'] == 10.0
    assert jet['range_high_km'] > jet['range_sea_km']
    assert '30 m' in jet['note']
    assert '掠海升阻比' in jet['note']
    # 6 km 的声速更低，同样 0.85 马赫略慢于海平面，掠海要补一点加速油。
    assert jet_low['range_sea_km'] == pytest.approx(jet['range_sea_km'], abs=0.5)
    assert jet_low['range_high_km'] < jet['range_high_km']
    # LRASM：宽 0.635 m、高 0.450 m 的扁五边形，不是 0.55 m 圆。空射质量约 1.21 t。
    # 全高空仍约 970 km。掠海升阻比由 30 m 动压算出，不按 400/950 缩放。
    lrasm = estimate_by_class(
        'turbofan_stealth', 4.26, 0.635, 450, 0.85, 10.0, width_m=0.635, height_m=0.450,
    )
    assert lrasm['range_high_km'] == 967.6
    assert lrasm['range_sea_km'] == 451.5
    assert lrasm['cruise_alt_km'] == 10.0
    assert lrasm['m_0_t'] == pytest.approx(1.21, abs=0.06)
    lower = estimate_by_class(
        'turbofan_stealth', 4.26, 0.635, 450, 0.85, 0.2, width_m=0.635, height_m=0.450,
    )
    surface = estimate_by_class(
        'turbofan_stealth', 4.26, 0.635, 450, 0.0, 0.0, width_m=0.635, height_m=0.450,
    )
    # 已经高于掠海、又快过接力速度时，掠海航程不随发射高度变；高空航程会少一段爬升油。
    assert lower['range_sea_km'] == lrasm['range_sea_km']
    assert lower['range_high_km'] < lrasm['range_high_km']
    assert surface['range_sea_km'] < lrasm['range_sea_km']
    assert surface['range_high_km'] < lower['range_high_km']
    # 只给最大外廓时，短边按 LRASM 高宽比收进去，应和显式宽高一致。
    from_major = estimate_by_class('turbofan_stealth', 4.26, 0.635, 450, 0.85, 10.0)
    assert from_major['m_0_t'] == lrasm['m_0_t']
    assert from_major['range_high_km'] == lrasm['range_high_km']
    # 10 m 级高密度吸热型碳氢燃料超燃比冲 1200 s、巡航 Ma 5.2。地面发射大约 2000 km，仍低于 5000 km。
    cj = estimate_by_class('scramjet', 10.0, 1.05, 400, 0.0, 0.0)
    assert cj['isp_cruise_s'] == pytest.approx(1200.0, abs=0.2)
    assert 1800 <= cj['range_km'] <= 2400
    assert cj['cruise_mach'] == pytest.approx(5.2, abs=0.05)
    big_vls = estimate_by_class('scramjet', 11.5, 1.2, 500, 0.0, 0.0)
    assert big_vls['cruise_mach'] == pytest.approx(5.2, abs=0.05)
    assert big_vls['range_km'] > cj['range_km']
    small = estimate_by_class('scramjet', 6.35, 0.51, 160, 0.0, 0.0)
    assert small['reached_takeover'] is True
    assert small['mach_takeover'] == 3.0
    assert small['cruise_mach'] == pytest.approx(5.2, abs=0.05)
    assert small['range_cruise_km'] > 200
    assert '双模态' in small['note']
    assert '固冲一体' not in small['note']
    assert '不铸药' in small['note']
    tube_ram = estimate_by_class('ramjet', 6.35, 0.51, 160, 0.0, 0.0)
    assert tube_ram['range_km'] < brahmos['range_km']


def test_optimistic_duct_ranges_stay_below_same_size_hgv():
    """超燃、亚燃取偏乐观的吸气效率，同外形大弹仍短于助推滑翔。"""
    from utils.missile_range.classes import estimate_by_class

    geom = dict(length_m=10.5, diameter_m=1.1, warhead_mass_kg=200, v_launch_mach=0.85, h_launch_km=13.0)
    hgv = estimate_by_class('hgv_biconic', **geom)
    scram = estimate_by_class('scramjet', **geom)
    ram = estimate_by_class('ramjet', **geom)
    assert scram['isp_cruise_s'] == pytest.approx(1200.0, abs=0.2)
    assert ram['isp_cruise_s'] == pytest.approx(1500.0, abs=0.2)
    assert scram['cruise_mach'] == pytest.approx(5.2, abs=0.05)
    assert hgv['range_km'] > scram['range_km'] > ram['range_km']
    assert scram['range_km'] > 2500
    assert ram['range_km'] > 2200
    small = estimate_by_class('scramjet', 4.25, 0.345, 90, 2.2, 19.0)
    assert small['reached_takeover'] is True
    assert small['cruise_mach'] == pytest.approx(5.2, abs=0.05)


def test_glide_floor_range_km_lifts_only_short_glides():
    """平衡滑翔短于弹道弧时按升阻比抬高；已经更远时保持原航程。"""
    from utils.missile_range.classes import glide_floor_range_km

    assert glide_floor_range_km(100.0, 200.0, 3.5) == pytest.approx(200.0 * (1.0 + 0.08 * 2.5))
    assert glide_floor_range_km(500.0, 200.0, 3.0) == 500.0
    with pytest.raises(ValueError):
        glide_floor_range_km(-1, 200, 3)
    with pytest.raises(ValueError):
        glide_floor_range_km(100, 0, 3)
    with pytest.raises(ValueError):
        glide_floor_range_km(100, 200, 0)


def test_waverider_head_steals_propellant_from_same_envelope():
    """同一外形和战斗部，乘波体弹头更长，装药和起飞质量都更轻。"""
    bi = estimate_hgv(10.5, 1.1, 600, 'biconic')
    wave = estimate_hgv(10.5, 1.1, 600, 'waverider')
    assert wave['l_head_m'] > bi['l_head_m']
    assert wave['m_p_total_kg'] < bi['m_p_total_kg']
    assert wave['m_0_t'] < bi['m_0_t']


def test_same_tube_glide_outranges_ballistic_and_combo_keeps_turbofan_isp():
    """鱼雷管上乘波体装药更少但仍长于双锥体，双锥体长于弹道；亚超巡航比冲不低于涡喷。"""
    from utils.missile_range.classes import estimate_by_class

    tube = dict(length_m=6.35, diameter_m=0.51, warhead_mass_kg=160, v_launch_mach=0.0, h_launch_km=0.0)
    wave = estimate_by_class('hgv_waverider', **tube)
    biconic = estimate_by_class('hgv_biconic', **tube)
    ballistic = estimate_by_class('ballistic', **tube)
    assert wave['m_p_total_kg'] < biconic['m_p_total_kg']
    assert wave['m_0_t'] < biconic['m_0_t']
    assert wave['range_km'] > biconic['range_km'] > ballistic['range_km']
    assert '再入航程' in biconic['note']

    vls = dict(length_m=11.5, diameter_m=1.2, warhead_mass_kg=500, v_launch_mach=0.0, h_launch_km=0.0)
    fan = estimate_by_class('turbofan_stealth', **vls)
    jet = estimate_by_class('turbojet_subsonic', **vls)
    combo = estimate_by_class('turbofan_rocket', **vls)
    ram = estimate_by_class('ramjet', **vls)
    assert fan['range_high_km'] > jet['range_high_km'] > combo['range_high_km']
    assert combo['range_high_km'] > 0.45 * jet['range_high_km']
    assert combo['isp_cruise_s'] == pytest.approx(fan['isp_cruise_s'], abs=0.2)
    assert combo['isp_cruise_s'] > jet['isp_cruise_s']
    assert ram['cruise_alt_km'] == 10.0
    assert ram['range_high_km'] > ram['range_sea_km'] > 0.4 * ram['range_high_km']


def test_scramjet_without_takeover_coasts_instead_of_cruising():
    """接不上亚燃接力时只计弹道弧，不改用固冲一体巡航。鱼雷管双模态可以接到。"""
    from utils.missile_range.classes import estimate_by_class

    tiny = estimate_by_class('scramjet', 3.0, 0.30, 50, 0.0, 0.0)
    assert tiny['reached_takeover'] is False
    assert tiny['range_cruise_km'] == 0.0
    assert tiny['cruise_alt_km'] < 20.0
    assert '未接入' in tiny['note']
    assert '固冲一体' not in tiny['note']
    fighter = estimate_by_class('scramjet', 4.25, 0.345, 90, 2.2, 19.0)
    assert fighter['reached_takeover'] is True
    assert fighter['cruise_mach'] == pytest.approx(5.2, abs=0.05)
    assert fighter['range_cruise_km'] > 0
    assert fighter['isp_cruise_s'] == pytest.approx(1200.0, abs=0.2)
    tube = dict(length_m=6.35, diameter_m=0.51, warhead_mass_kg=160, v_launch_mach=0.0, h_launch_km=0.0)
    scram = estimate_by_class('scramjet', **tube)
    ram = estimate_by_class('ramjet', **tube)
    assert scram['reached_takeover'] is True
    assert scram['mach_takeover'] == 3.0
    assert scram['range_cruise_km'] > 0
    assert 0 < scram['range_km'] < ram['range_km']


def test_scramjet_combustor_is_separate_from_the_booster():
    """超燃燃烧室留空，固体助推和燃油另分；亚燃仍是固冲一体。"""
    import math

    from utils.missile_range.classes import (
        BOOST_FILL,
        SCRAMJET_COMBUSTOR_DIAMETER_FRAC,
        SCRAMJET_COMBUSTOR_FINENESS,
        SCRAMJET_COMBUSTOR_LENGTH_FRAC,
        SCRAMJET_ENDOTHERMIC_FUEL_KG_M3,
        _DUCT_SPECS,
        accel_fuel_for_dv,
        class_blurb,
        estimate_by_class,
        scramjet_combustor_volume_m3,
        split_boost_and_fuel,
        split_scramjet_booster_and_fuel,
    )

    assert accel_fuel_for_dv(1000, 0.5, 1200, 0.55) == 0.0
    slow = accel_fuel_for_dv(1000, 400, 1200, 0.55)
    fast = accel_fuel_for_dv(1000, 800, 1200, 0.55)
    thirsty = accel_fuel_for_dv(1000, 800, 900, 0.55)
    assert fast > slow > 0
    assert thirsty > fast
    with pytest.raises(ValueError):
        accel_fuel_for_dv(0, 10, 1200, 0.5)
    with pytest.raises(ValueError):
        accel_fuel_for_dv(1000, -1, 1200, 0.5)

    length, diameter = 10.0, 1.05
    flow = diameter * SCRAMJET_COMBUSTOR_DIAMETER_FRAC
    combustor_length = min(length * SCRAMJET_COMBUSTOR_LENGTH_FRAC, SCRAMJET_COMBUSTOR_FINENESS * diameter)
    chamber = scramjet_combustor_volume_m3(length, diameter)
    assert chamber == pytest.approx(math.pi * (flow / 2.0) ** 2 * combustor_length)
    assert chamber > 0
    with pytest.raises(ValueError):
        scramjet_combustor_volume_m3(0, 1)
    with pytest.raises(ValueError):
        split_scramjet_booster_and_fuel(1.0, -0.1, 800, 400, 260, 1760, 980, 0.3)
    with pytest.raises(ValueError, match='燃油舱'):
        split_scramjet_booster_and_fuel(0.03, 0.02, 800, 400, 260, 1760, 980, 0.3)

    bay_prop, bay_fuel, _ = split_boost_and_fuel(1.0, 800, 400, 260, 1760, 980, 0.3)
    split_prop, split_fuel, _ = split_scramjet_booster_and_fuel(1.2, 0.2, 800, 400, 260, 1760, 980, 0.3)
    assert split_prop == pytest.approx(bay_prop)
    assert split_fuel == pytest.approx(bay_fuel)
    assert split_prop / (1760 * BOOST_FILL) + split_fuel / 980 == pytest.approx(1.0)
    assert _DUCT_SPECS['scramjet']['fuel_density'] == SCRAMJET_ENDOTHERMIC_FUEL_KG_M3
    assert _DUCT_SPECS['scramjet']['mach_takeover'] == 3.0
    assert '固冲一体' in class_blurb('ramjet')
    assert '双模态' in class_blurb('scramjet')
    assert '不铸药' in class_blurb('scramjet')
    assert '高密度吸热型' in class_blurb('scramjet')
    scram = estimate_by_class('scramjet', 10.0, 1.05, 400, 0.0, 0.0)
    ram = estimate_by_class('ramjet', 6.5, 0.50, 200, 0.9, 12.0)
    assert '双模态' in scram['note']
    assert '不铸药' in scram['note']
    assert '高密度吸热型' in scram['note']
    assert '固冲一体' not in scram['note']
    assert '固冲一体' in ram['note']
    assert ram['m_0_t'] == pytest.approx(1.50, abs=0.05)


def test_scramjet_isolator_shrinks_with_cross_section():
    """隔离段在 1.05 m 及以上保持 0.22 m³，更细的弹按截面积缩小。"""
    from utils.missile_range.classes import (
        SCRAMJET_ISOLATOR_REF_DIAMETER_M,
        _DUCT_SPECS,
        scramjet_isolator_volume_m3,
    )

    reference = _DUCT_SPECS['scramjet']['fixed_void_m3']
    assert scramjet_isolator_volume_m3(SCRAMJET_ISOLATOR_REF_DIAMETER_M) == pytest.approx(reference)
    assert scramjet_isolator_volume_m3(1.20) == pytest.approx(reference)
    tube = scramjet_isolator_volume_m3(0.51)
    assert tube == pytest.approx(reference * (0.51 / SCRAMJET_ISOLATOR_REF_DIAMETER_M) ** 2)
    assert tube < reference
    with pytest.raises(ValueError):
        scramjet_isolator_volume_m3(0)
    saved = _DUCT_SPECS['scramjet']['fixed_void_m3']
    _DUCT_SPECS['scramjet']['fixed_void_m3'] = -0.1
    try:
        with pytest.raises(ValueError, match='隔离段'):
            scramjet_isolator_volume_m3(0.51)
    finally:
        _DUCT_SPECS['scramjet']['fixed_void_m3'] = saved


def test_isp_from_tsfc_round_trip():
    """吸气比冲与耗油率互为倒数，非法输入拒绝。"""
    from utils.missile_range.classes import isp_from_tsfc_s, tsfc_from_isp_s

    assert isp_from_tsfc_s(2.15e-5) == pytest.approx(1.0 / (2.15e-5 * 9.80665))
    assert tsfc_from_isp_s(isp_from_tsfc_s(6.8e-5)) == pytest.approx(6.8e-5)
    with pytest.raises(ValueError):
        isp_from_tsfc_s(0)
    with pytest.raises(ValueError):
        tsfc_from_isp_s(-1)


def test_cruise_tsfc_base_keeps_calibrated_value():
    """吸气比冲与标定值很接近时不改耗油率；差得多才换算。"""
    from utils.missile_range.classes import _DUCT_SPECS, cruise_tsfc_base, isp_from_tsfc_s

    ram = _DUCT_SPECS['ramjet']
    nominal = isp_from_tsfc_s(ram['tsfc'])
    assert cruise_tsfc_base(ram, None) == ram['tsfc']
    assert cruise_tsfc_base(ram, round(nominal, 1)) == ram['tsfc']
    assert cruise_tsfc_base(ram, 2000) != ram['tsfc']
    with pytest.raises(ValueError):
        cruise_tsfc_base({'tsfc': 0}, None)
    with pytest.raises(ValueError):
        cruise_tsfc_base(ram, 0)


def test_airbreathing_stage_isp_splits_booster_and_cruise():
    """吸气弹巡航比冲高于固体助推；纯火箭不拆这两段。"""
    from utils.missile_range.classes import (
        SUBSONIC_BOOSTER_ISP_S,
        airbreathing_stage_isp,
        class_isp_defaults,
        estimate_by_class,
    )

    ram = airbreathing_stage_isp('ramjet', 0.50, 264)
    narrow = airbreathing_stage_isp('ramjet', 0.36, 264)
    scram = airbreathing_stage_isp('scramjet', 0.36, 264)
    fan = airbreathing_stage_isp('turbofan_stealth', 0.63, 264)
    jet = airbreathing_stage_isp('turbojet_subsonic', 0.55, 264)
    combo = airbreathing_stage_isp('turbofan_rocket', 0.53, 264)
    assert ram['isp_boost_s'] == 264
    assert ram['isp_cruise_s'] > ram['isp_boost_s']
    assert narrow['isp_cruise_s'] < ram['isp_cruise_s']
    assert scram['isp_cruise_s'] == airbreathing_stage_isp('scramjet', 1.2, 264)['isp_cruise_s']
    assert fan['isp_cruise_s'] > jet['isp_cruise_s'] > 264
    assert jet['isp_cruise_s'] == pytest.approx(2800.0, abs=0.2)
    assert 1.6 <= fan['isp_cruise_s'] / jet['isp_cruise_s'] <= 2.0
    assert scram['isp_cruise_s'] == pytest.approx(1200.0, abs=0.2)
    assert scram['isp_cruise_s'] < ram['isp_cruise_s']
    assert fan['isp_boost_s'] == SUBSONIC_BOOSTER_ISP_S
    assert combo['isp_rocket_s'] == 264
    assert combo['isp_cruise_s'] > combo['isp_rocket_s'] > combo['isp_boost_s']
    with pytest.raises(ValueError, match='没有吸气巡航'):
        airbreathing_stage_isp('ballistic', 1.0, 264)
    with pytest.raises(ValueError):
        airbreathing_stage_isp('ramjet', 0.5, 0)
    defaults = class_isp_defaults('hgv_biconic')
    assert defaults['isp_cruise_s'] is None
    assert defaults['isp_rocket_s'] == 264.0
    assert class_isp_defaults('ramjet')['isp_cruise_s'] > class_isp_defaults('ramjet')['isp_boost_s']
    low = estimate_by_class('ramjet', 6.5, 0.5, 200, 0.9, 12, isp_s=180)
    high = estimate_by_class('ramjet', 6.5, 0.5, 200, 0.9, 12, isp_s=320)
    assert low['isp_cruise_s'] == high['isp_cruise_s']
    assert low['isp_boost_s'] == 180
    assert high['isp_boost_s'] == 320
    base = estimate_by_class('ramjet', 6.5, 0.5, 200, 0.9, 12)
    farther = estimate_by_class('ramjet', 6.5, 0.5, 200, 0.9, 12, isp_air_s=2000)
    assert farther['range_high_km'] > base['range_high_km']
    assert farther['isp_cruise_s'] > base['isp_cruise_s']
    surface = estimate_by_class('turbofan_stealth', 6.25, 0.52, 450, 0.0, 0.0)
    assert surface['isp_boost_s'] == SUBSONIC_BOOSTER_ISP_S
    assert surface['isp_cruise_s'] > surface['isp_boost_s']
    from utils.missile_range.classes import _air_spec, resolved_cruise_tsfc
    assert _air_spec('ramjet')['tsfc'] == pytest.approx(1.0 / (1500.0 * 9.80665))
    assert _air_spec('ballistic') is None
    assert resolved_cruise_tsfc('ramjet', 0.50) == pytest.approx(1.0 / (1500.0 * 9.80665))
    assert resolved_cruise_tsfc('ramjet', 0.36) > resolved_cruise_tsfc('ramjet', 0.50)
    with pytest.raises(ValueError, match='没有吸气巡航'):
        resolved_cruise_tsfc('ballistic', 1.0)


def test_bomber_small_warhead_presets_are_150kg():
    """隐身超音速轰炸机较小的战斗部预设应为 150kg。轰-6 机腹最大仍是 150/600 kg。"""
    from utils.missile_range.dataset import grouped_preset_bays

    grouped = grouped_preset_bays()
    stealth_bay = next(b for b in grouped['supersonic'] if b['bay'] == '隐身超音速轰炸机弹仓' and b.get('missile_class') is None)
    stealth_warheads = [r[2] for r in stealth_bay['rounds']]
    assert stealth_warheads == [150, 500]
    assert not any(b['bay'] == '超音速隐身轰炸机·轰6发射' for b in grouped['supersonic'])


def test_stealth_bomber_shows_h6_launch_in_alt_column():
    """隐身超音速轰炸机弹仓不再单列轰-6 发射组，轰-6 射程放进轰-6/轰-20/歼-36 一栏。"""
    from utils.missile_range.dataset import J15_ALT_LAUNCHES, build_preset_cases, evaluate_case

    cases = [
        case for case in build_preset_cases()
        if case['bay'] == '隐身超音速轰炸机弹仓'
    ]
    assert len(cases) == 10
    assert {(case['length'], case['diameter']) for case in cases} == {(11.30, 0.860)}
    assert {case['warhead'] for case in cases} == {150, 500}
    sample = next(case for case in cases if case['missile_class'] == 'hgv_biconic' and case['warhead'] == 150)
    row = evaluate_case(sample)
    assert row['v_mach'] == pytest.approx(1.75)
    assert row['h_km'] == pytest.approx(18.0)
    assert [item['label'] for item in row['alt_launches']] == [label for label, _, _ in J15_ALT_LAUNCHES]
    h6 = row['alt_launches'][0]
    assert h6['v_mach'] == pytest.approx(0.85)
    assert h6['h_km'] == pytest.approx(13.0)
    assert row['range_km'] > h6['range_km'] > 0


def test_missile_range_takeover_status():
    """冲压弹接力工作速度达成状态判定：达标与未达标标志位及马赫数字段。"""
    from utils.missile_range.classes import estimate_by_class

    # 1. 成功接入接力马赫数的大型超燃与空射亚燃
    scram_ok = estimate_by_class('scramjet', 10.0, 1.05, 400, 0.0, 0.0)
    assert scram_ok['reached_takeover'] is True
    assert scram_ok['mach_takeover'] == 3.0
    assert scram_ok['mach_boost'] >= 3.0 * 0.98
    assert scram_ok['cruise_mach'] == pytest.approx(5.2, abs=0.05)
    assert scram_ok['range_cruise_km'] > 0
    assert scram_ok['m_booster_kg'] > 0
    assert scram_ok['m_fuel_kg'] > 0

    ram_ok = estimate_by_class('ramjet', 6.5, 0.50, 200, 0.9, 12.0)
    assert ram_ok['reached_takeover'] is True
    assert ram_ok['mach_takeover'] == 1.95
    assert ram_ok['mach_boost'] >= 1.95 * 0.98
    assert ram_ok['m_booster_kg'] > 0
    assert ram_ok['m_fuel_kg'] > 0

    # 2. 未达亚燃接力的过小超燃；533 mm 鱼雷管双模态可以接到
    scram_fail = estimate_by_class('scramjet', 3.0, 0.30, 50, 0.0, 0.0)
    assert scram_fail['reached_takeover'] is False
    assert scram_fail['mach_takeover'] == 3.0
    assert scram_fail['mach_boost'] < 3.0 * 0.98
    tube = estimate_by_class('scramjet', 6.35, 0.51, 160, 0.0, 0.0)
    assert tube['reached_takeover'] is True
    assert tube['mach_boost'] >= 3.0 * 0.98
    assert scram_fail['range_cruise_km'] == 0.0
    assert '未接入' in scram_fail['note']
    assert 0 < scram_fail['takeover_progress'] < 1.0
    assert scram_ok['takeover_progress'] == pytest.approx(1.0)
    assert ram_ok['takeover_progress'] == pytest.approx(1.0)

    # 3. 非冲压弹种不进行冲压接力判定，reached_takeover 为 None
    ballistic = estimate_by_class('ballistic', 4.0, 0.43, 91, 0.0, 0.0)
    assert ballistic['reached_takeover'] is None
    assert ballistic['mach_takeover'] is None
    assert ballistic['takeover_progress'] is None


def test_takeover_progress_frac():
    """助推马赫相对接力马赫的进度条比例。"""
    from utils.missile_range.classes import takeover_progress_frac

    assert takeover_progress_frac(2.1, 4.2) == pytest.approx(0.5)
    assert takeover_progress_frac(4.2, 4.2) == pytest.approx(1.0)
    assert takeover_progress_frac(5.0, 4.2) == pytest.approx(1.0)
    assert takeover_progress_frac(0.0, 1.95) == pytest.approx(0.0)
    with pytest.raises(ValueError, match='接力马赫数必须大于 0'):
        takeover_progress_frac(1.0, 0.0)
    with pytest.raises(ValueError, match='助推马赫数不能为负'):
        takeover_progress_frac(-0.1, 4.2)


def test_filter_takeover_failed_and_labels():
    """样本表给未达接力速度的行加上标签，筛选只留下这些行。"""
    rows = evaluate_dataset()
    failed = filter_takeover_failed(rows, True)
    all_rows = filter_takeover_failed(rows, False)
    assert len(all_rows) == len(rows)
    assert all(row['reached_takeover'] is False for row in failed)
    assert all('未达工作速度' in row['name'] for row in failed)
    labelled = [row for row in rows if '未达工作速度' in row['name']]
    assert len(labelled) == len(failed)
    assert not any(row['bay'] in ('歼-36弹仓', '歼-36弹仓·歼-15发射') for row in rows)
    assert not any(
        row['missile_class'] == 'scramjet' and row.get('reached_takeover') is False
        for row in rows
    )
    synthetic = [
        {'name': '过小 · 未达工作速度', 'reached_takeover': False, 'missile_class': 'scramjet'},
        {'name': '够大', 'reached_takeover': True, 'missile_class': 'scramjet'},
    ]
    only_failed = filter_takeover_failed(synthetic, True)
    assert len(only_failed) == 1
    assert only_failed[0]['reached_takeover'] is False


def test_hgv_min_fineness():
    """测试不同滑翔体构型的长细比底线值及构型别名。"""
    assert hgv_min_fineness('biconic') == 1.8
    assert hgv_min_fineness('双锥体') == 1.8
    assert hgv_min_fineness('waverider') == 2.2
    assert hgv_min_fineness('乘波体') == 2.2
    with pytest.raises(ValueError, match='未知构型'):
        hgv_min_fineness('invalid_shape')


def test_min_head_length_m():
    """测试兼顾容积与长细比底线的滑翔体最小长度计算。"""
    # 战斗部 200kg 双锥体，在 D=1.0m 时纯容积仅需 0.57m，但长细比底线 1.8 m 占主导
    l_floor = min_head_length_m(200.0, 1.0, 'biconic', enforce_min_fineness=True)
    assert l_floor == pytest.approx(1.8)
    l_raw = min_head_length_m(200.0, 1.0, 'biconic', enforce_min_fineness=False)
    assert l_raw == pytest.approx(0.573, abs=0.01)

    # 直径必须大于 0
    with pytest.raises(ValueError, match='直径必须大于 0'):
        min_head_length_m(200.0, 0.0, 'biconic')


def test_head_and_booster_lengths_m_with_fineness():
    """测试带有长细比修正的弹头与助推器长度划分。"""
    lh, lb = head_and_booster_lengths_m(10.5, 1.0, 200.0, 'biconic')
    assert lh == pytest.approx(1.8, abs=0.01)
    assert lb == pytest.approx(8.7, abs=0.01)

    lh_raw, lb_raw = head_and_booster_lengths_m(
        10.5, 1.0, 200.0, 'biconic', enforce_min_fineness=False,
    )
    assert lh_raw == pytest.approx(0.57, abs=0.01)
    assert lb_raw == pytest.approx(9.93, abs=0.01)


def test_optimize_hgv_geometry():
    """测试滑翔体最优长宽搜索：综合权衡升阻比与助推器装药最大化射程。"""
    # 10.5m x 1.0m, 200kg 弹头（双锥体）
    opt_bi = optimize_hgv_geometry(10.5, 1.0, 200.0, 'biconic')
    assert opt_bi['max_range_km'] > opt_bi['baseline_range_km'] + 500.0
    assert opt_bi['range_gain_km'] > 500.0
    assert opt_bi['best_l_head_m'] > opt_bi['baseline_l_head_m']
    assert opt_bi['best_d_head_m'] < 1.0
    assert opt_bi['best_ld_ratio'] > opt_bi['baseline_ld_ratio']
    assert opt_bi['best_fineness'] >= 1.8
    assert opt_bi['result']['optimal_geometry'] is True

    # 10.5m x 1.0m, 200kg 弹头（乘波体）
    opt_wave = optimize_hgv_geometry(10.5, 1.0, 200.0, 'waverider')
    assert opt_wave['max_range_km'] > opt_wave['baseline_range_km'] + 500.0
    assert opt_wave['best_fineness'] >= 2.2
    assert opt_wave['best_ld_ratio'] > 4.0

    # 异常输入校验
    with pytest.raises(ValueError, match='长细比下限'):
        optimize_hgv_geometry(10.5, 1.0, 200.0, 'biconic', min_fineness=-1)
    with pytest.raises(ValueError, match='直径范围'):
        optimize_hgv_geometry(10.5, 1.0, 200.0, 'biconic', min_d_head_m=0)


def test_estimate_hgv_custom_geometry_and_optimization():
    """测试 estimate_hgv 支持自定义几何参数与自动寻优开关。"""
    # 自定义滑翔体长与直径
    custom = estimate_hgv(10.5, 1.0, 200.0, 'biconic', l_head_m=3.5, d_head_m=0.5)
    assert custom['l_head_m'] == 3.5
    assert custom['d_head_m'] == 0.5
    assert custom['fineness'] == 7.0
    assert custom['l_booster_m'] == 7.0
    assert custom['ld_ratio'] == pytest.approx(1.5 + 0.18 * 7.0, abs=0.01)

    # 开启 optimize_geometry
    optimized = estimate_hgv(10.5, 1.0, 200.0, 'biconic', optimize_geometry=True)
    assert optimized['optimal_geometry'] is True
    assert optimized['range_gain_km'] > 500.0
    assert optimized['range_km'] > 4000.0

    # 边界非法参数校验
    with pytest.raises(ValueError, match='不超过弹体直径'):
        estimate_hgv(10.5, 1.0, 200.0, 'biconic', d_head_m=1.2)
    with pytest.raises(ValueError, match='必须大于 0'):
        estimate_hgv(10.5, 1.0, 200.0, 'biconic', d_head_m=-0.5)
    with pytest.raises(ValueError, match='小于全弹长'):
        estimate_hgv(10.5, 1.0, 200.0, 'biconic', l_head_m=11.0)


def test_estimate_by_class_with_geometry_optimization():
    """测试 estimate_by_class 助推滑翔弹几何寻优。"""
    from utils.missile_range.classes import estimate_by_class

    res = estimate_by_class('hgv_biconic', 10.5, 1.0, 200.0, optimize_geometry=True)
    assert res['optimal_geometry'] is True
    assert res['range_gain_km'] > 500.0
    assert '几何搜索寻优' in res['note']

    wave = estimate_by_class('hgv_waverider', 10.5, 1.0, 200.0, optimize_geometry=True)
    assert wave['optimal_geometry'] is True
    assert '几何搜索寻优' in wave['note']


def test_run_optimize_geometry_from_params():
    """测试仿真器层面滑翔体几何优化 API 与常规单发估算 API。"""
    from simulators.missile_range.missile_range import (
        run_estimate_from_params,
        run_optimize_geometry_from_params,
    )

    # 正常助推滑翔寻优
    opt_res = run_optimize_geometry_from_params({
        'missile_class': 'hgv_biconic',
        'length_m': 10.5,
        'diameter_m': 1.0,
        'warhead_kg': 200.0,
    })
    assert opt_res['success'] is True
    assert opt_res['optimization']['range_gain_km'] > 500.0

    # 非 HGV 弹种报错
    err_res = run_optimize_geometry_from_params({
        'missile_class': 'ballistic',
        'length_m': 10.5,
        'diameter_m': 1.0,
        'warhead_kg': 200.0,
    })
    assert err_res['success'] is False
    assert '不是助推滑翔弹' in err_res['error']

    # estimate 接口带 optimize_geometry
    est_res = run_estimate_from_params({
        'missile_class': 'hgv_biconic',
        'length_m': 10.5,
        'diameter_m': 1.0,
        'warhead_kg': 200.0,
        'optimize_geometry': True,
    })
    assert est_res['success'] is True
    assert est_res['result']['optimal_geometry'] is True


def test_head_volume_factor_and_packaging_volume():
    """容积系数与外形容积：乘波体更扁，同样长径装得更少。"""
    assert head_volume_factor('biconic') == pytest.approx(0.2618)
    assert head_volume_factor('乘波体') == pytest.approx(0.1745)
    bi = head_packaging_volume_m3(3.0, 0.8, 'biconic')
    wave = head_packaging_volume_m3(3.0, 0.8, 'waverider')
    assert bi > wave
    with pytest.raises(ValueError, match='必须大于 0'):
        head_packaging_volume_m3(0, 1, 'biconic')


def test_hgv_head_diameter_bounds():
    """滑翔体直径搜索区间不超过弹径，且有装填口径下限。"""
    d_min, d_max = hgv_head_diameter_bounds(1.0)
    assert d_max == pytest.approx(1.0)
    assert d_min == pytest.approx(0.35)
    tight_min, tight_max = hgv_head_diameter_bounds(1.0, min_d_head_m=0.6, max_d_head_m=0.9)
    assert tight_min == pytest.approx(0.6)
    assert tight_max == pytest.approx(0.9)
    with pytest.raises(ValueError, match='弹径必须大于 0'):
        hgv_head_diameter_bounds(0)
    with pytest.raises(ValueError, match='直径范围'):
        hgv_head_diameter_bounds(1.0, min_d_head_m=0)


def test_round_hgv_result_and_unrounded():
    """未舍入估算与对外圆整字段一致。"""
    raw = estimate_hgv_unrounded(10.5, 1.0, 200.0, 'biconic')
    rounded = _round_hgv_result(
        raw['m_0'], raw['l_head_m'], raw['l_booster_m'], raw['m_propellant'],
        raw['v_burnout'], raw['ld_ratio'], raw['range_km'], raw['d_head_m'],
        raw['h_burnout_km'], stage=raw['stage'],
    )
    assert rounded == estimate_hgv(10.5, 1.0, 200.0, 'biconic')
    assert raw['l_head_m'] == pytest.approx(1.8)
    with pytest.raises(ValueError, match='容积不足以容纳'):
        estimate_hgv_unrounded(10.5, 1.0, 200.0, l_head_m=0.4, d_head_m=0.4)


def test_optimize_geometry_cache_key_and_compute():
    """寻优缓存键稳定，底层网格函数能算出正射程。"""
    key = _optimize_geometry_cache_key(
        10.5, 1.0, 200.0, 'biconic', 0.85, 13.0, 264.0, 1760.0,
        None, None, None, 0.45, 24, 24,
    )
    assert key[3] == 'biconic'
    cached = _optimize_hgv_geometry_cached(key)
    computed = _optimize_hgv_geometry_compute(*key)
    assert cached['max_range_km'] == computed['max_range_km']
    with pytest.raises(ValueError, match='搜索网格点数'):
        _optimize_hgv_geometry_compute(
            10.5, 1.0, 200.0, 'biconic', 0.85, 13.0, 264.0, 1760.0,
            None, None, None, 0.45, 0, 24,
        )


def test_estimate_by_class_defaults_to_geometry_search():
    """助推滑翔默认搜索滑翔体尺寸；关闭后回到长细比底线划分。"""
    from utils.missile_range.classes import estimate_by_class

    default = estimate_by_class('hgv_biconic', 10.5, 1.0, 200.0)
    packed = estimate_by_class('hgv_biconic', 10.5, 1.0, 200.0, optimize_geometry=False)
    assert default['optimal_geometry'] is True
    assert default['d_head_m'] < packed['d_head_m']
    assert default['range_km'] > packed['range_km']
    assert packed.get('optimal_geometry') is None
    with pytest.raises(ValueError, match='搜索网格点数'):
        optimize_hgv_geometry(10.5, 1.0, 200.0, grid_points_d=0)


def test_inclusive_grid_includes_both_ends():
    """长度网格包含下限、步长点和未对齐的上限。"""
    from utils.missile_range.sizing import _inclusive_grid_m

    assert _inclusive_grid_m(4.0, 5.0, 0.5) == [4.0, 4.5, 5.0]
    assert _inclusive_grid_m(1.0, 1.2, 0.5) == [1.0, 1.2]
    with pytest.raises(ValueError, match='步长必须大于 0'):
        _inclusive_grid_m(1.0, 2.0, 0)
    with pytest.raises(ValueError, match='上限不能小于下限'):
        _inclusive_grid_m(2.0, 1.0, 0.1)
    with pytest.raises(ValueError, match='步长过小'):
        _inclusive_grid_m(1.0, 2.0, 0.00001)


def test_envelope_rank_prefers_range_then_length():
    """射程相同的时候，更长的弹排在更粗的弹之前。"""
    from utils.missile_range.sizing import _envelope_rank

    short = {'range_km': 100.0, 'length_m': 8.0, 'diameter_m': 1.5}
    long = {'range_km': 100.0, 'length_m': 12.0, 'diameter_m': 0.8}
    far = {'range_km': 200.0, 'length_m': 4.0, 'diameter_m': 0.4}
    assert _envelope_rank(far) > _envelope_rank(long) > _envelope_rank(short)


def test_optimize_missile_envelope_matches_brute_force_grid():
    """小网格上的最优弹长弹径与逐点比较一致，且不超出质量上限。"""
    from utils.missile_range.classes import estimate_by_class
    from utils.missile_range.sizing import _inclusive_grid_m, optimize_missile_envelope

    kwargs = dict(
        max_length_m=8.0,
        max_mass_t=4.0,
        min_length_m=7.0,
        min_diameter_m=0.6,
        max_diameter_m=0.8,
        length_step_m=1.0,
        diameter_step_m=0.1,
        v_launch_mach=0.85,
        h_launch_km=13.0,
    )
    best = optimize_missile_envelope('ballistic', 200.0, **kwargs)
    scored = []
    for length_m in _inclusive_grid_m(7.0, 8.0, 1.0):
        for diameter_m in _inclusive_grid_m(0.6, 0.8, 0.1):
            result = estimate_by_class('ballistic', length_m, diameter_m, 200.0, 0.85, 13.0)
            if result['m_0_t'] <= 4.0:
                scored.append((result['range_km'], length_m, diameter_m))
    assert (best['range_km'], best['length_m'], best['diameter_m']) == max(scored)
    assert best['m_0_t'] <= 4.0
    assert best['length_m'] <= 8.0
    assert best['missile_class'] == 'ballistic'


def test_optimize_missile_envelope_respects_diameter_cap():
    """弹径上限是硬约束，默认轰-6 机腹为 1.2 m。"""
    from utils.missile_range.sizing import H6_BELLY_MAX_DIAMETER_M, optimize_missile_envelope

    assert H6_BELLY_MAX_DIAMETER_M == pytest.approx(1.2)
    best = optimize_missile_envelope(
        'ballistic', 150,
        max_length_m=8.0,
        max_mass_t=3.0,
        min_length_m=6.0,
        min_diameter_m=0.4,
        max_diameter_m=0.7,
        length_step_m=1.0,
        diameter_step_m=0.1,
    )
    assert best['diameter_m'] <= 0.7
    assert best['length_m'] <= 8.0
    assert best['m_0_t'] <= 3.0


def test_polish_missile_envelope_stays_inside_caps():
    """抛光不得超出弹长、弹径和质量上限，射程不低于起点。"""
    from utils.missile_range.sizing import optimize_missile_envelope, polish_missile_envelope

    kwargs = dict(
        max_length_m=8.0,
        max_mass_t=2.0,
        min_length_m=6.0,
        min_diameter_m=0.4,
        max_diameter_m=0.7,
        v_launch_mach=0.85,
        h_launch_km=13.0,
    )
    seed = optimize_missile_envelope(
        'ballistic', 150.0,
        length_step_m=1.0,
        diameter_step_m=0.1,
        **kwargs,
    )
    polished = polish_missile_envelope(seed, 150.0, steps_m=(0.2, 0.1), **kwargs)
    assert polished['range_km'] + 1e-6 >= seed['range_km']
    assert polished['length_m'] <= 8.0
    assert polished['diameter_m'] <= 0.7
    assert polished['m_0_t'] <= 2.0
    with pytest.raises(ValueError, match='抛光步长'):
        polish_missile_envelope(seed, 150.0, steps_m=(0,), **kwargs)
    with pytest.raises(ValueError, match='抛光起点'):
        polish_missile_envelope(
            {'missile_class': 'ballistic', 'length_m': 12.0, 'diameter_m': 1.2},
            600.0, **kwargs,
        )


def test_diameter_for_liftoff_mass_can_lock_structure_launch():
    """助推切分可按另一套发射条件搜索，再按交付条件核算质量。"""
    from utils.missile_range.classes import estimate_by_class
    from utils.missile_range.sizing import diameter_for_liftoff_mass

    sized = diameter_for_liftoff_mass(
        'ballistic', 6.0, 150, 1.2,
        max_diameter_m=0.55,
        v_launch_mach=1.5,
        h_launch_km=14.0,
        structure_v_mach=0.85,
        structure_h_km=13.0,
    )
    ref = estimate_by_class('ballistic', 6.0, sized['diameter_m'], 150, 0.85, 13.0)
    assert sized['m_0_t'] <= 1.2
    assert sized['diameter_m'] <= 0.55
    assert sized['result']['stage_split'] == ref['stage_split']
    with pytest.raises(ValueError, match='结构发射条件'):
        diameter_for_liftoff_mass(
            'ballistic', 6.0, 150, 1.2,
            max_diameter_m=0.55,
            v_launch_mach=1.5,
            h_launch_km=14.0,
            structure_v_mach=0.85,
        )


def test_fit_locked_head_restores_packaging_floor():
    """圆整后装不下战斗部时，滑翔体长度回到装填底线。"""
    from utils.missile_range.dataset import fit_locked_head
    from utils.missile_range.estimate import min_head_length_m

    floor = min_head_length_m(300, 0.55, 'biconic')
    fitted = fit_locked_head(
        {'l_head_m': 2.69, 'd_head_m': 0.55, 'stage_fractions': (0.72, 0.28)},
        8.5, 0.70, 300, 'hgv_biconic',
    )
    assert fitted['l_head_m'] == pytest.approx(floor)
    assert fitted['d_head_m'] == pytest.approx(0.55)
    unchanged = fit_locked_head({'stage_fractions': (1.0,)}, 8.5, 0.7, 300, 'ballistic')
    assert unchanged == {'stage_fractions': (1.0,)}


def test_optimize_missile_envelope_rejects_bad_limits():
    """上限、战斗部或搜不到点时拒绝。"""
    from utils.missile_range.sizing import optimize_missile_envelope

    with pytest.raises(ValueError, match='必须大于 0'):
        optimize_missile_envelope('ballistic', 100, max_length_m=0)
    with pytest.raises(ValueError, match='必须大于 0'):
        optimize_missile_envelope('ballistic', 100, max_mass_t=0)
    with pytest.raises(ValueError, match='不能为负'):
        optimize_missile_envelope('ballistic', -1)
    with pytest.raises(ValueError, match='弹径搜索范围'):
        optimize_missile_envelope('ballistic', 100, min_diameter_m=0)
    with pytest.raises(ValueError, match='没有可用尺寸'):
        optimize_missile_envelope(
            'ballistic', 600,
            max_length_m=4.0,
            max_mass_t=0.2,
            min_length_m=4.0,
            min_diameter_m=0.8,
            max_diameter_m=0.8,
            length_step_m=1.0,
            diameter_step_m=0.1,
        )


def test_h6_belly_max_presets_are_sized_per_missile():
    """轰-6机腹最大按弹种分别给尺寸，弹长不超过 12 m、弹径不超过 1.2 m、起飞质量不超过 10 t。"""
    from utils.missile_range.classes import estimate_by_class
    from utils.missile_range.dataset import SUPERSONIC_CLASSES, build_preset_cases

    expected = {
        ('hgv_biconic', 150): (11.95, 1.1818),
        ('hgv_biconic', 600): (12.00, 1.2000),
        ('hgv_waverider', 150): (12.00, 1.0959),
        ('hgv_waverider', 600): (12.00, 1.2000),
        ('scramjet', 150): (12.00, 1.1240),
        ('scramjet', 600): (12.00, 1.1100),
        ('ramjet', 150): (12.00, 1.1360),
        ('ramjet', 600): (12.00, 1.1100),
        ('ballistic', 150): (11.99, 1.0474),
        ('ballistic', 600): (11.94, 1.0469),
    }
    cases = build_preset_cases()
    largest = [case for case in cases if case['bay'] == '轰-6机腹最大']
    assert {(case['missile_class'], case['warhead']) for case in largest} == set(expected)
    assert {case['missile_class'] for case in largest} == set(SUPERSONIC_CLASSES)
    sizes = set()
    for case in largest:
        length, diameter = expected[(case['missile_class'], case['warhead'])]
        assert case['length'] == pytest.approx(length)
        assert case['diameter'] == pytest.approx(diameter)
        assert case['v_mach'] == pytest.approx(0.85)
        assert case['h_km'] == pytest.approx(13.0)
        result = estimate_by_class(
            case['missile_class'], case['length'], case['diameter'], case['warhead'],
            case['v_mach'], case['h_km'],
        )
        assert case['diameter'] <= 1.2
        assert result['m_0_t'] <= 10.0
        assert result['range_km'] > 0
        sizes.add((case['length'], case['diameter']))
    assert len(sizes) > 1


def test_booster_stage_search_penalizes_extra_stages():
    """每多一级有固定死重，分配搜索在一至三级里取更高的关机速度或射程。"""
    from utils.missile_range.estimate import (
        BOOST_TWR_HEAVY,
        _best_fraction_by_impulse,
        _fraction_candidates,
        _staged_dv_and_burn,
        booster_liftoff_twr,
        build_stage_plan,
        displaced_propellant_kg,
        format_stage_split,
        search_booster_stages,
        stage_event_dead_kg,
        stage_result_sentence,
    )
    from simulators.missile_range.missile_range import opt_bool, resolve_ballistic_single_stage

    assert booster_liftoff_twr(20000) == pytest.approx(BOOST_TWR_HEAVY, abs=0.05)
    assert booster_liftoff_twr(400) > booster_liftoff_twr(8000)
    with pytest.raises(ValueError, match='起飞质量'):
        booster_liftoff_twr(0)
    dead = stage_event_dead_kg(1.0)
    assert dead == pytest.approx(102.0 * math.pi * 0.25, abs=0.1)
    assert stage_event_dead_kg(0.2) == 12.0
    with pytest.raises(ValueError, match='弹径'):
        stage_event_dead_kg(0)
    assert displaced_propellant_kg(2700, 1760) == pytest.approx(1760)
    with pytest.raises(ValueError, match='死重'):
        displaced_propellant_kg(-1, 1760)
    assert format_stage_split((0.58, 0.42)) == '58/42'
    assert format_stage_split((1.0,)) == '100'
    assert format_stage_split((0.70, 0.22, 0.08)) == '70/22/8'
    with pytest.raises(ValueError, match='不能为空'):
        format_stage_split(())
    with pytest.raises(ValueError, match='不能为负'):
        format_stage_split((-0.1, 1.1))
    with pytest.raises(ValueError, match='之和'):
        format_stage_split((0.2, 0.2))
    grid = _fraction_candidates(2)
    assert grid[0][0] >= 0.04
    assert abs(sum(grid[0]) - 1) < 1e-9
    assert _fraction_candidates(1) == ((1.0,),)
    with pytest.raises(ValueError, match='级数'):
        _fraction_candidates(4)
    staged = _staged_dv_and_burn(200, 600, 0, 0, (0.6, 0.4), 250)
    assert staged is not None and staged[0] > 0
    assert _staged_dv_and_burn(10, 100, 0, 0, (1.5, -0.5), 250) is None
    single = build_stage_plan(200, 800, 0.5, 264, 1760, (1.0,))
    double = build_stage_plan(200, 800, 0.5, 264, 1760, (0.6, 0.4))
    assert single is not None and double is not None
    assert single['hardware_kg'] == 0
    assert double['hardware_kg'] > single['hardware_kg']
    assert double['propellant_kg'] < 800
    assert double['extra_gravity_m_s'] > 0
    assert '60/40' in double['stage_split']
    with pytest.raises(ValueError, match='载荷'):
        build_stage_plan(0, 800, 0.5, 264, 1760, (1.0,))
    with pytest.raises(ValueError, match='推进剂质量分数'):
        build_stage_plan(200, 800, 0.5, 264, 1760, (1.0,), propellant_mass_fraction=1.0)
    with pytest.raises(ValueError, match='推进剂质量分数'):
        _best_fraction_by_impulse(200, 800, 0.5, 264, 1760, 1, propellant_mass_fraction=0)
    best = _best_fraction_by_impulse(200, 800, 0.5, 264, 1760, 2)
    assert best is not None and abs(sum(best) - 1) < 1e-9
    assert _best_fraction_by_impulse(200, 1, 2.0, 264, 1760, 3) is None

    def speed_score(plan):
        return plan['dv_m_s'] - plan['extra_gravity_m_s']

    picked = search_booster_stages(180, 5000, 1.0, 264, 1760, speed_score, prescreen=True)
    forced = search_booster_stages(180, 5000, 1.0, 264, 1760, speed_score, stages=1)
    assert picked['n_stages'] in (2, 3)
    assert speed_score(picked) > speed_score(forced)
    assert '助推按射程取' in stage_result_sentence(picked)
    assert '已锁定单级' in stage_result_sentence(forced)
    assert opt_bool('off', True) is False
    assert opt_bool(None, True) is True
    assert resolve_ballistic_single_stage({}) is False
    assert resolve_ballistic_single_stage({'ballistic_single_stage': True}) is True
    assert resolve_ballistic_single_stage({'ballistic_two_stage': False}) is True
    assert resolve_ballistic_single_stage({
        'ballistic_single_stage': False,
        'ballistic_two_stage': False,
    }) is False
    with pytest.raises(ValueError, match='助推级数'):
        search_booster_stages(180, 500, 0.4, 264, 1760, speed_score, stages=4)

