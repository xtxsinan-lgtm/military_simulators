"""导弹射程估算单元测试。"""
from __future__ import annotations

import math

import pytest

from apps.missile_range_web import run_missile_range, run_missile_range_json
from simulators.missile_range.missile_range import (
    _required_float,
    opt_float,
    opt_optional_float,
    run_dataset_from_params,
    run_estimate_from_params,
    run_presets_from_params,
)
from utils.missile_range.dataset import (
    MISSILE_DATASET,
    PROPULSION_DATASET,
    all_missile_cases,
    build_missile_range_catalog_payload,
    evaluate_case,
    evaluate_dataset,
    filter_takeover_failed,
    format_launch,
    format_size_m,
    missile_case_label,
    sort_missile_range_rows,
)
from utils.missile_range.estimate import (
    G0,
    GLIDE_EFF,
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
    estimate_hgv,
    estimate_hgv_unrounded,
    glide_range_m,
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
    fineness_min = 2.5 if hgv_type == 'biconic' else 3.5
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
        ld_ratio = max(2.8, min(5.0, 2.2 + 0.28 * fineness))
    v_eff2 = v_burnout ** 2 + 2.0 * g0 * (h_launch_km * 1000.0)
    ratio_v2 = v_eff2 / (g0 * r_e)
    glide_eff = 0.513
    if ratio_v2 >= 0.95:
        r_glide = 16000000.0
    else:
        r_glide = (
            0.5 * r_e * ld_ratio * math.log(1.0 / (1.0 - ratio_v2))
            * (1.0 + 0.35 * ratio_v2) * glide_eff
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
    l_head, l_boost = head_and_booster_lengths_m(6.35, 0.46, 300, 'biconic')
    assert l_head == pytest.approx(6.35 * 0.45)
    assert l_boost == pytest.approx(6.35 - l_head)
    with pytest.raises(ValueError):
        head_and_booster_lengths_m(0, 0.5, 100, 'biconic')


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
    assert lift_drag_ratio(4.0, 0.8, 'waverider') == pytest.approx(3.6)
    assert lift_drag_ratio(20.0, 0.86, 'waverider') == pytest.approx(5.0)
    with pytest.raises(ValueError):
        lift_drag_ratio(10, 0, 'biconic')
    with pytest.raises(ValueError):
        lift_drag_ratio(0, 1.0, 'biconic')


def test_glide_range_m_cap_and_formula():
    assert glide_range_m(0.96, 3.0) == 16000000.0
    ratio = 0.2
    ld = 3.0
    expected = (
        0.5 * R_EARTH_M * ld * math.log(1.0 / (1.0 - ratio))
        * (1.0 + 0.35 * ratio) * GLIDE_EFF
    )
    assert glide_range_m(ratio, ld) == pytest.approx(expected)
    with pytest.raises(ValueError):
        glide_range_m(-0.1, 3.0)


def test_require_non_negative():
    assert _require_non_negative('战斗部质量', 0) == 0
    with pytest.raises(ValueError, match='战斗部质量'):
        _require_non_negative('战斗部质量', -1)


def test_estimate_hgv_matches_reference_dataset():
    assert estimate_hgv(10.5, 1.0, 200) == _oracle(10.5, 1.0, 200)
    for case in MISSILE_DATASET:
        from utils.missile_range.classes import glide_shape
        shape = glide_shape(case['missile_class'])
        got = estimate_hgv(
            length_m=case['length'],
            diameter_m=case['diameter'],
            warhead_mass_kg=case['warhead'],
            hgv_type=shape,
            v_launch_mach=case['v_mach'],
            h_launch_km=case['h_km'],
        )
        assert got == _oracle(
            case['length'], case['diameter'], case['warhead'], shape,
            case['v_mach'], case['h_km'],
        )
    custom = estimate_hgv(8.0, 0.7, 400, 'waverider', 1.2, 15.0, isp_s=280, propellant_density=1800)
    assert custom == _oracle(8.0, 0.7, 400, 'waverider', 1.2, 15.0, 280, 1800)


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
    assert case['bay'] == '轰-6机腹'
    assert case['diameter'] == 1.1
    assert missile_case_label(case).startswith('#1  轰-6机腹 · 10.50 x 1.100')
    row = evaluate_case(case)
    assert row['id'] == 1
    assert row['bay'] == '轰-6机腹'
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
    assert rows[0]['bay'] == '1280垂发'
    assert rows[1]['bay'] == '1280垂发'
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
    assert payload['defaults']['ballistic_two_stage'] is True
    assert {item['id'] for item in payload['classes']} >= {
        'hgv_biconic', 'hgv_waverider', 'scramjet', 'ramjet', 'turbofan_stealth',
        'turbojet_subsonic', 'turbofan_rocket', 'ballistic',
    }
    assert 'hgv' not in {item['id'] for item in payload['classes']}
    assert payload['cases'][0]['bay'] == '1280垂发'
    assert payload['cases'][0]['range_km'] >= payload['cases'][1]['range_km']
    top_bay = rows[0]['bay']
    same_bay = [r for r in rows if r['bay'] == top_bay]
    assert len(same_bay) >= 2
    assert same_bay[0]['range_km'] >= same_bay[1]['range_km']
    assert payload['defaults']['isp_s'] == 264.0
    assert payload['cases'][0]['range_km'] == rows[0]['range_km']
    assert G0 == pytest.approx(9.80665)
    assert SOUND_SPEED_M_S == 295.0


def test_sort_missile_range_rows_by_bay_and_range():
    rows = sort_missile_range_rows([
        {
            'id': 9,
            'name': 'A',
            'bay': '小平台',
            'length_m': 4.0,
            'diameter_m': 0.4,
            'warhead_kg': 100,
            'range_km': 120.0,
        },
        {
            'id': 3,
            'name': 'B',
            'bay': '大平台',
            'length_m': 10.0,
            'diameter_m': 1.0,
            'warhead_kg': 200,
            'range_km': 300.0,
        },
        {
            'id': 2,
            'name': 'C',
            'bay': '大平台',
            'length_m': 10.0,
            'diameter_m': 1.0,
            'warhead_kg': 200,
            'range_km': 100.0,
        },
        {
            'id': 6,
            'name': 'D',
            'bay': '中平台',
            'length_m': 8.0,
            'diameter_m': 0.7,
            'warhead_kg': 150,
            'range_km': 200.0,
        },
    ])
    assert [row['bay'] for row in rows] == ['大平台', '大平台', '中平台', '小平台']
    assert [row['range_km'] for row in rows[:2]] == [300.0, 100.0]
    assert [row['id'] for row in rows] == [1, 2, 3, 4]
    assert rows[0]['name'].startswith('#1  ')
    assert rows[1]['name'].startswith('#2  ')


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
    assert df15['range_km'] == 831.9
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
    assert default_stage['range_km'] == 499.0
    assert '两级' in default_stage['note']

    # 同一外形若显式保留单级、且不计滑行阻力，短弹保持改默认前的射程。
    legacy = estimate_ballistic(
        4.8, 0.40, 200, 0, 0, 264, 1760,
        warhead_section='biconic', coast_drag=False, two_stage=False,
    )
    assert legacy['range_km'] == 187.4
    gmlrs = estimate_ballistic(3.96, 0.227, 90, 0, 0, 264, 1760)
    assert 70.0 <= gmlrs['range_km'] <= 92.0
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
    assert scram['range_km'] == 1773.8
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
    assert short['range_km'] == 223.9
    assert long['range_km'] == 511.0
    assert long['range_km'] > short['range_km']
    assert '两级' in long['note']
    assert '头锥扣除制导与战斗部' in long['note']
    # PrSM Increment 1：4.0 m × 0.43 m、战斗部 91 kg、地面发射，默认两级时约 485 km
    prsm = estimate_ballistic(4.0, 0.43, 91, 0, 0, 264, 1760)
    assert prsm['range_km'] == 499.0
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
    assert len(PROPULSION_DATASET) == 75
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
    # 当前样本：5 超音速弹种 × 16 + 3 亚音速弹种 × 9 = 107
    assert [case['id'] for case in cases] == list(range(1, 108))

    # 共用的弹仓行
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
    assert len(super_generic) == 14
    assert len(sub_generic) == 7
    assert any(item[0] == '1280垂发' for item in super_generic)
    assert any(item[0] == '533mm鱼雷' for item in sub_generic)
    assert 'ballistic' in SUPERSONIC_CLASSES
    assert 'turbofan_rocket' in SUBSONIC_CLASSES
    assert 'turbofan_rocket' not in SUPERSONIC_CLASSES

    # 无专属覆盖时，弹种样例应与共用行完全一致
    for missile_class in SUPERSONIC_CLASSES:
        if missile_class == 'hgv_waverider':
            # 乘波体在歼-36弹仓有专属行，样例应体现覆盖
            continue
        got = [
            (case['bay'], case['length'], case['diameter'], case['warhead'], case['v_mach'], case['h_km'])
            for case in cases if case['missile_class'] == missile_class
        ]
        # 每个超音速弹种还有 2 条歼-15 专属样例
        assert len(got) == 16
        assert got[:14] == super_generic
    for missile_class in SUBSONIC_CLASSES:
        got = [
            (case['bay'], case['length'], case['diameter'], case['warhead'], case['v_mach'], case['h_km'])
            for case in cases if case['missile_class'] == missile_class
        ]
        # 每个亚音速弹种还有 2 条歼-15 专属样例
        assert len(got) == 9
        assert got[:7] == sub_generic

    # 乘波体在歼-36弹仓被专属行覆盖为 250 kg
    wave_j36 = next(
        case for case in cases
        if case['missile_class'] == 'hgv_waverider' and case['bay'] == '歼-36弹仓'
    )
    assert wave_j36['warhead'] == 250
    assert wave_j36['length'] == 6.35
    assert wave_j36['diameter'] == 0.59
    # 双锥体仍用共用行的 600 kg
    biconic_j36 = next(
        case for case in cases
        if case['missile_class'] == 'hgv_biconic' and case['bay'] == '歼-36弹仓'
    )
    assert biconic_j36['warhead'] == 600

    assert all(row['range_km'] > 0 for row in evaluate_dataset())


def test_carrier_launch_envelope():
    """歼-36、中型六代机、歼-15、轰-6 与隐身超音速轰炸机按给定极速和升限发射。"""
    from utils.missile_range.dataset import build_preset_cases

    expected = {
        '歼-36弹仓': (2.15, 20.0),
        '中型六代机弹仓': (1.75, 18.0),
        '歼-15机腹': (1.5, 14.0),
        '歼-15翼下': (1.5, 14.0),
        '隐身超音速轰炸机弹仓': (1.75, 18.0),
        '轰-6机腹': (0.85, 13.0),
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
    """歼-15 翼下预设落在弹长 6.5 m、弹径 0.70 m、起飞质量 1500 kg 以内。

    亚音速、亚燃、亚超结合和普通弹道用 500 kg 战斗部，其余翼下弹种仍是 300 kg。
    """
    from utils.missile_range.classes import estimate_by_class
    from utils.missile_range.dataset import build_preset_cases

    # 弹长、弹径、战斗部
    expected = {
        'hgv_biconic': (6.50, 0.5873, 300),
        'hgv_waverider': (6.50, 0.5873, 300),
        'scramjet': (4.13, 0.6996, 300),
        'ramjet': (5.46, 0.5006, 500),
        'ballistic': (6.50, 0.5480, 500),
        'turbofan_stealth': (6.50, 0.5727, 500),
        'turbojet_subsonic': (6.50, 0.6244, 500),
        'turbofan_rocket': (6.50, 0.4962, 500),
    }
    wings = [case for case in build_preset_cases() if case['bay'] == '歼-15翼下']
    assert {case['missile_class'] for case in wings} == set(expected)
    for case in wings:
        length, diameter, warhead = expected[case['missile_class']]
        assert case['length'] == pytest.approx(length)
        assert case['diameter'] == pytest.approx(diameter)
        assert case['warhead'] == warhead
        assert case['length'] <= 6.5
        assert case['diameter'] <= 0.70
        result = estimate_by_class(
            case['missile_class'], case['length'], case['diameter'], case['warhead'],
            case['v_mach'], case['h_km'],
        )
        assert result['m_0_t'] <= 1.50
        assert result['range_km'] > 0


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
    assert prsm['range_km'] == 499.0
    iskander = estimate_ballistic(7.3, 0.92, 480, 0, 0, 264, 1760)
    assert 480 <= iskander['range_km'] <= 560
    df15 = estimate_ballistic(9.1, 1.0, 500, 0, 0, 264, 1760)
    assert 720 <= df15['range_km'] <= 840
    assert '两级' in df15['note']


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
    assert small['range_km'] > 0
    assert small['range_cruise_km'] == 0.0
    assert '未接入' in small['note']
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
    assert small['cruise_mach'] < 4.0


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
    """接不上超燃接力时只计弹道弧，不改用亚燃模态巡航。"""
    from utils.missile_range.classes import estimate_by_class

    tiny = estimate_by_class('scramjet', 4.7, 0.36, 90, 0.9, 10.0)
    assert tiny['range_cruise_km'] == 0.0
    assert tiny['cruise_alt_km'] < 20.0
    assert '未接入' in tiny['note']
    assert '亚燃' not in tiny['note']
    fighter = estimate_by_class('scramjet', 4.25, 0.345, 90, 2.2, 19.0)
    assert '未接入' in fighter['note']
    assert '亚燃模态' not in fighter['note']
    assert fighter['cruise_mach'] < 4.0
    assert fighter['range_cruise_km'] == 0.0
    assert fighter['isp_cruise_s'] == pytest.approx(1200.0, abs=0.2)
    tube = dict(length_m=6.35, diameter_m=0.51, warhead_mass_kg=160, v_launch_mach=0.0, h_launch_km=0.0)
    scram = estimate_by_class('scramjet', **tube)
    ram = estimate_by_class('ramjet', **tube)
    assert scram['range_cruise_km'] == 0.0
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
    assert 'dual_mode' not in _DUCT_SPECS['scramjet']
    assert '固冲一体' in class_blurb('ramjet')
    assert '双模态' in class_blurb('scramjet')
    assert '高密度吸热型' in class_blurb('scramjet')
    scram = estimate_by_class('scramjet', 10.0, 1.05, 400, 0.0, 0.0)
    ram = estimate_by_class('ramjet', 6.5, 0.50, 200, 0.9, 12.0)
    assert '燃烧室与固体助推分开' in scram['note']
    assert '高密度吸热型' in scram['note']
    assert '亚燃' not in scram['note']
    assert '固冲一体' in ram['note']
    assert ram['m_0_t'] == pytest.approx(1.50, abs=0.05)


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
    """轰-6机腹与隐身超音速轰炸机较小的战斗部预设应为 150kg。"""
    from utils.missile_range.dataset import grouped_preset_bays

    grouped = grouped_preset_bays()
    h6_bay = next(b for b in grouped['supersonic'] if b['bay'] == '轰-6机腹' and b.get('missile_class') is None)
    stealth_bay = next(b for b in grouped['supersonic'] if b['bay'] == '隐身超音速轰炸机弹仓' and b.get('missile_class') is None)

    h6_warheads = [r[2] for r in h6_bay['rounds']]
    assert sorted(set(h6_warheads)) == [150, 500, 600]
    assert min(h6_warheads) == 150

    stealth_warheads = [r[2] for r in stealth_bay['rounds']]
    assert stealth_warheads == [150, 500]


def test_h6_and_stealth_bomber_shared_dimensions_presets():
    """轰-6机腹具备与隐身超音速轰炸机同尺寸（11.30 x 0.860）但初速与高度相应调整的射程预设。"""
    from utils.missile_range.classes import MISSILE_CLASS_ORDER, estimate_by_class
    from utils.missile_range.dataset import build_preset_cases, grouped_preset_bays

    grouped = grouped_preset_bays()
    h6_bay = next(b for b in grouped['supersonic'] if b['bay'] == '轰-6机腹' and b.get('missile_class') is None)
    stealth_bay = next(b for b in grouped['supersonic'] if b['bay'] == '隐身超音速轰炸机弹仓' and b.get('missile_class') is None)

    # 轰-6机腹具备同尺寸 (11.30, 0.860) 且战斗部为 150kg 与 500kg 的预设轮次
    h6_shared_rounds = [r for r in h6_bay['rounds'] if (r[0], r[1]) == (11.30, 0.860)]
    stealth_rounds = list(stealth_bay['rounds'])
    assert h6_shared_rounds == stealth_rounds == [(11.30, 0.860, 150), (11.30, 0.860, 500)]

    # 发射条件：轰-6 机腹相应调整为 Ma 0.85 @ 13.0km，隐身轰炸机为 Ma 1.75 @ 18.0km
    assert h6_bay['v_mach'] == 0.85 and h6_bay['h_km'] == 13.0
    assert stealth_bay['v_mach'] == 1.75 and stealth_bay['h_km'] == 18.0

    # 验证全部 5 类超音速弹种的预设样本中，隐轰发射射程均大于轰-6机腹发射射程
    cases = build_preset_cases()
    supersonic_classes = [item['id'] for item in MISSILE_CLASS_ORDER if item['id'] not in ('turbofan_stealth', 'turbojet_subsonic', 'turbofan_rocket')]
    for m_class in supersonic_classes:
        for warhead in (150, 500):
            h6_case = next(
                c for c in cases
                if c['missile_class'] == m_class and c['bay'] == '轰-6机腹'
                and (c['length'], c['diameter'], c['warhead']) == (11.30, 0.860, warhead)
            )
            stealth_case = next(
                c for c in cases
                if c['missile_class'] == m_class and c['bay'] == '隐身超音速轰炸机弹仓'
                and (c['length'], c['diameter'], c['warhead']) == (11.30, 0.860, warhead)
            )
            assert h6_case['v_mach'] == 0.85 and h6_case['h_km'] == 13.0
            assert stealth_case['v_mach'] == 1.75 and stealth_case['h_km'] == 18.0

            h6_res = estimate_by_class(m_class, 11.30, 0.860, warhead, 0.85, 13.0)
            stealth_res = estimate_by_class(m_class, 11.30, 0.860, warhead, 1.75, 18.0)
            assert h6_res['range_km'] > 0
            assert stealth_res['range_km'] > h6_res['range_km']


def test_missile_range_takeover_status():
    """冲压弹接力工作速度达成状态判定：达标与未达标标志位及马赫数字段。"""
    from utils.missile_range.classes import estimate_by_class

    # 1. 成功接入接力马赫数的大型超燃与空射亚燃
    scram_ok = estimate_by_class('scramjet', 10.0, 1.05, 400, 0.0, 0.0)
    assert scram_ok['reached_takeover'] is True
    assert scram_ok['mach_takeover'] == 4.2
    assert scram_ok['mach_boost'] >= 4.2 * 0.98
    assert scram_ok['range_cruise_km'] > 0
    assert scram_ok['m_booster_kg'] > 0
    assert scram_ok['m_fuel_kg'] > 0

    ram_ok = estimate_by_class('ramjet', 6.5, 0.50, 200, 0.9, 12.0)
    assert ram_ok['reached_takeover'] is True
    assert ram_ok['mach_takeover'] == 1.95
    assert ram_ok['mach_boost'] >= 1.95 * 0.98
    assert ram_ok['m_booster_kg'] > 0
    assert ram_ok['m_fuel_kg'] > 0

    # 2. 未达接力工作速度的小型超燃（地面发射或小尺寸）
    scram_fail = estimate_by_class('scramjet', 6.35, 0.51, 160, 0.0, 0.0)
    assert scram_fail['reached_takeover'] is False
    assert scram_fail['mach_takeover'] == 4.2
    assert scram_fail['mach_boost'] < 4.2 * 0.98
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
    assert failed
    assert all(row['reached_takeover'] is False for row in failed)
    assert all('未达工作速度' in row['name'] for row in failed)
    assert all(row['missile_class'] == 'scramjet' for row in failed)
    labelled = [row for row in rows if '未达工作速度' in row['name']]
    assert len(labelled) == len(failed)


def test_hgv_min_fineness():
    """测试不同滑翔体构型的长细比底线值及构型别名。"""
    assert hgv_min_fineness('biconic') == 2.5
    assert hgv_min_fineness('双锥体') == 2.5
    assert hgv_min_fineness('waverider') == 3.5
    assert hgv_min_fineness('乘波体') == 3.5
    with pytest.raises(ValueError, match='未知构型'):
        hgv_min_fineness('invalid_shape')


def test_min_head_length_m():
    """测试兼顾容积与长细比底线的滑翔体最小长度计算。"""
    # 战斗部 200kg 双锥体，在 D=1.0m 时纯容积仅需 0.57m，但长细比底线 2.5 m 占主导
    l_floor = min_head_length_m(200.0, 1.0, 'biconic', enforce_min_fineness=True)
    assert l_floor == pytest.approx(2.5)
    l_raw = min_head_length_m(200.0, 1.0, 'biconic', enforce_min_fineness=False)
    assert l_raw == pytest.approx(0.573, abs=0.01)

    # 直径必须大于 0
    with pytest.raises(ValueError, match='直径必须大于 0'):
        min_head_length_m(200.0, 0.0, 'biconic')


def test_head_and_booster_lengths_m_with_fineness():
    """测试带有长细比修正的弹头与助推器长度划分。"""
    lh, lb = head_and_booster_lengths_m(10.5, 1.0, 200.0, 'biconic')
    assert lh == pytest.approx(2.5, abs=0.01)
    assert lb == pytest.approx(8.0, abs=0.01)

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
    assert opt_bi['best_fineness'] >= 2.5
    assert opt_bi['result']['optimal_geometry'] is True

    # 10.5m x 1.0m, 200kg 弹头（乘波体）
    opt_wave = optimize_hgv_geometry(10.5, 1.0, 200.0, 'waverider')
    assert opt_wave['max_range_km'] > opt_wave['baseline_range_km'] + 500.0
    assert opt_wave['best_fineness'] >= 3.5
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
    )
    assert rounded == estimate_hgv(10.5, 1.0, 200.0, 'biconic')
    assert raw['l_head_m'] == pytest.approx(2.5)
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


