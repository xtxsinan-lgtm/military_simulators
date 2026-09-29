"""导弹射程估算单元测试。"""
from __future__ import annotations

import math

import pytest

from apps.missile_range_web import run_missile_range, run_missile_range_json
from simulators.missile_range.missile_range import (
    _required_float,
    opt_float,
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
    format_launch,
    format_size_m,
    missile_case_label,
)
from utils.missile_range.estimate import (
    G0,
    GLIDE_EFF,
    R_EARTH_M,
    SOUND_SPEED_M_S,
    _require_non_negative,
    chamber_length_m,
    estimate_hgv,
    glide_range_m,
    gravity_drag_loss_m_s,
    head_and_booster_lengths_m,
    head_aux_ratio,
    head_density_kg_m3,
    head_total_mass_kg,
    head_volume_m3,
    lift_drag_ratio,
    motor_cross_section_m2,
    normalize_hgv_type,
    propellant_mass_kg,
    uncapped_head_length_m,
)


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
    head_density = 1800.0 if hgv_type == 'biconic' else 1650.0
    v_head_req = m_head_total / head_density
    if hgv_type == 'biconic':
        l_head_calc = v_head_req / (0.2618 * (diameter_m ** 2))
    else:
        l_head_calc = v_head_req / (0.1745 * (diameter_m ** 2))
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
    gravity_drag_loss = max(180.0, 320.0 - (h_launch_km - 13.0) * 15.0)
    v_burnout = v_launch_ms + (dv1 + dv2) - gravity_drag_loss
    fineness = length_m / diameter_m
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
    assert gravity_drag_loss_m_s(13.0) == pytest.approx(320.0)
    assert gravity_drag_loss_m_s(19.0) == pytest.approx(230.0)
    assert gravity_drag_loss_m_s(40.0) == pytest.approx(180.0)


def test_lift_drag_ratio_bounds():
    assert lift_drag_ratio(10.5, 1.0, 'biconic') == pytest.approx(3.39)
    assert lift_drag_ratio(11.3, 0.86, 'waverider') == pytest.approx(5.0)
    with pytest.raises(ValueError):
        lift_drag_ratio(10, 0, 'biconic')


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
    assert estimate_hgv(10.5, 1.0, 200) == {
        'm_0_t': 9.05,
        'l_head_m': 0.57,
        'l_booster_m': 9.93,
        'm_p_total_kg': 7642.7,
        'v_burnout_mach': 20.49,
        'ld_ratio': 3.39,
        'range_km': 6157.7,
    }
    for case in MISSILE_DATASET:
        got = estimate_hgv(
            length_m=case['length'],
            diameter_m=case['diameter'],
            warhead_mass_kg=case['warhead'],
            hgv_type=case['type'],
            v_launch_mach=case['v_mach'],
            h_launch_km=case['h_km'],
        )
        assert got == _oracle(
            case['length'], case['diameter'], case['warhead'], case['type'],
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
    assert missile_case_label(case).startswith('#1  10.50 x 1.000')
    row = evaluate_case(case)
    assert row['id'] == 1
    assert row['type_label'] == '双锥体'
    assert row['missile_class'] == 'hgv_biconic'
    assert row['class_label'] == '双锥体助推滑翔'
    assert row['range_km'] == 6157.7


def test_evaluate_dataset_and_catalog():
    rows = evaluate_dataset()
    assert len(rows) == len(all_missile_cases())
    assert [r['id'] for r in rows] == list(range(1, len(rows) + 1))
    heavier = evaluate_dataset(isp_s=300, propellant_density=1900)
    assert heavier[0]['range_km'] != rows[0]['range_km']
    payload = build_missile_range_catalog_payload()
    assert payload['type_labels']['waverider'] == '乘波体'
    assert payload['defaults']['missile_class'] == 'hgv_biconic'
    assert {item['id'] for item in payload['classes']} >= {
        'hgv_biconic', 'hgv_waverider', 'scramjet', 'ramjet', 'turbofan_stealth',
        'turbojet_subsonic', 'turbofan_rocket', 'ballistic',
    }
    assert 'hgv' not in {item['id'] for item in payload['classes']}
    assert rows[0]['missile_class'] == 'hgv_biconic'
    assert rows[1]['missile_class'] == 'hgv_waverider'
    assert payload['defaults']['isp_s'] == 264.0
    assert payload['cases'][0]['range_km'] == rows[0]['range_km']
    assert G0 == pytest.approx(9.80665)
    assert SOUND_SPEED_M_S == 295.0


def test_opt_float_and_required_float():
    assert opt_float('', 1.5) == 1.5
    assert opt_float(None, 2) == 2
    assert opt_float('3.5', 1) == 3.5
    assert _required_float({'length_m': '4'}, 'length_m') == 4
    with pytest.raises(ValueError, match='缺少参数'):
        _required_float({}, 'length_m')


def test_run_estimate_dataset_and_presets():
    bad = run_estimate_from_params({})
    assert bad['success'] is False
    ok = run_estimate_from_params({
        'length_m': 10.5,
        'diameter_m': 1,
        'warhead_kg': 200,
        'hgv_type': '双锥体',
    })
    assert ok['success'] is True
    assert ok['result']['range_km'] == 6157.7
    assert len(ok['rows']) == len(all_missile_cases())
    table = run_dataset_from_params({'isp_s': '264'})
    assert table['count'] == len(all_missile_cases())
    presets = run_presets_from_params()
    assert presets['success'] is True
    assert len(presets['cases']) == len(all_missile_cases())


def test_run_missile_range_json_actions():
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
    assert flat['result']['range_km'] == 6157.7
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
    assert glide_shape('hgv_biconic') == 'biconic'
    assert glide_shape('hgv_waverider') == 'waverider'
    assert glide_shape('scramjet') is None
    assert resolve_missile_class('hgv', 'waverider') == 'hgv_waverider'
    assert resolve_missile_class('助推滑翔弹', 'biconic') == 'hgv_biconic'
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
    with pytest.raises(ValueError, match='放不下'):
        energy_volume_m3(0.05, 500, 800, 40, 400, 0.1)
    spec = _SUBSONIC_SPECS['turbofan_stealth']
    assert subsonic_ld(6.2, 0.55, spec) == pytest.approx(clamp(4.4 + 0.16 * (6.2 / 0.55), 5.0, 6.8))
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
    assert ballistic_burn_time_s(500, 1000, 250) == pytest.approx(500 * 250 / (2.3 * 1000))
    dv = _ideal_two_stage_dv(1000, 600, 90, 2500)
    assert dv > 0
    packed = _base_fields('ramjet', 2000, 1.2, 6, 400, 3, 3.2, 800.04, '说明', range_high_km=None)
    assert packed['range_km'] == 800.0
    assert packed['class_label'] == '亚燃冲压导弹'
    assert packed['range_high_km'] is None


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
    assert stealth['range_high_km'] == 2100.8
    assert stealth['range_sea_km'] == 1368.6
    assert stealth['range_high_km'] > stealth['range_sea_km']
    assert plain['range_high_km'] == 1410.1
    assert plain['range_sea_km'] == 889.1
    assert stealth['range_high_km'] > plain['range_high_km']
    heavier = estimate_subsonic_class('turbofan_stealth', 6.2, 0.55, 700, 0.7, 0.2)
    assert heavier['range_km'] < stealth['range_km']

    scram = estimate_ducted('scramjet', 9.2, 0.7, 180, 0.85, 12, 264, 1760)
    ram = estimate_ducted('ramjet', 8.9, 0.7, 250, 0.85, 12, 264, 1760)
    assert scram['range_km'] == 749.0
    assert scram['cruise_mach'] == 5.5
    assert ram['range_km'] == 1765.2
    assert ram['v_burnout_mach'] == 3.0
    assert scram['range_sea_km'] is None

    prop, sized = terminal_propellant_for_dash(8.2, 0.53, 300, 0.7, 0.05, 264, 1760, _ROCKET_CRUISE)
    assert prop > 0 and sized['fuel_kg'] > 0
    combo = estimate_turbofan_rocket(8.2, 0.53, 300, 0.7, 0.05, 264, 1760)
    assert combo['range_terminal_km'] == 20.8
    assert combo['range_high_km'] > combo['range_sea_km']
    assert combo['range_km'] == combo['range_high_km']
    same_combo = estimate_turbofan_rocket(6.2, 0.55, 450, 0.7, 0.2, 264, 1760)
    assert same_combo['range_high_km'] < stealth['range_high_km']

    short = estimate_ballistic(4.8, 0.40, 200, 0, 0, 264, 1760)
    long = estimate_ballistic(11.2, 0.88, 980, 0, 0, 264, 1760)
    assert short['range_km'] == 164.4
    assert long['range_km'] == 823.0
    assert long['range_km'] > short['range_km']
    assert '不含滑翔' in long['note']
    legacy = estimate_by_class('hgv', 10.5, 1, 200)
    assert legacy['range_km'] == 6157.7
    assert legacy['missile_class'] == 'hgv_biconic'
    wave = estimate_by_class('乘波体助推滑翔', 10.5, 1, 200, 'biconic', 0.85, 13, 264, 1760)
    assert wave['missile_class'] == 'hgv_waverider'
    assert wave['range_km'] == estimate_hgv(10.5, 1, 200, 'waverider')['range_km']
    assert wave['range_km'] != legacy['range_km']
    with pytest.raises(ValueError):
        estimate_subsonic_class('ramjet', 6, 0.5, 100, 0.7, 1)
    assert len(PROPULSION_DATASET) == 12
    labels = {row['missile_class'] for row in evaluate_dataset() if row['id'] >= 17}
    assert labels == {
        'scramjet', 'ramjet', 'turbofan_stealth',
        'turbojet_subsonic', 'turbofan_rocket', 'ballistic',
    }
