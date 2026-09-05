"""巡航高度 / 最大马赫搜索单元测试。"""
from __future__ import annotations

import inspect

import pytest

from utils.combat_radius.combat_radius_presets import get_preset_by_id, load_engine_presets, load_presets
from utils.combat_radius.cruise_load import combat_mass_kg
from utils.combat_radius.cruise_search import (
    ALT_MAX_M,
    ALT_MIN_M,
    ALT_REFINE_M,
    FIXED_MACHS,
    MACH_PROFILE_STEP,
    MACH_SEARCH_LO,
    PEAK_ALT_DROP_M,
    PRACTICAL_MAX_CRUISE_MACH_LO,
    SUPERSONIC_MACH,
    CruiseContext,
    any_feasible_altitude,
    altitude_grid,
    contiguous_peak_max_mach,
    cruise_point_feasible,
    evaluate_cruise_forces,
    flyable_forces,
    max_ld_fields,
    profile_machs,
    scan_best_altitude_profile,
    scan_altitudes_at_mach,
    score_cruise_point,
    scored_to_dict,
    search_best_altitude,
    snap_mach,
    altitude_scan_fields,
    build_altitude_scan,
    _require_mach_search_bounds,
    search_max_possible_cruise_mach,
    search_max_cruise_mach,
    search_max_ld_altitude,
    try_cruise_forces,
    _search_max_ld_on_band,
    THRUST_MARGIN_DEFAULT,
)
from utils.combat_radius.max_speed_search import MAX_SPEED_THRUST_MARGIN
from utils.combat_radius.lift_drag import (
    F22_SUPERCRUISE_MACH,
    J20_SUPERCRUISE_MACH,
    Aircraft,
    aircraft_from_dict,
    model_coefficients,
)


def _f35c() -> Aircraft:
    return Aircraft(
        'F-35C', AR=2.77, sweep_deg=30.9, wing_loading=0.341,
        tc=0.0510, mach=0.8, alt_m=11300,
        planform='trapezoidal', layout='conventional',
        bwb=False, rough=True, length_m=15.67, wingspan_m=13.1,
    )


def _f22() -> Aircraft:
    return Aircraft(
        'F-22', AR=2.37, sweep_deg=41.3, wing_loading=0.318,
        tc=0.0520, mach=0.8, alt_m=11800,
        planform='trapezoidal', layout='conventional',
        bwb=False, rough=False, length_m=18.92, wingspan_m=13.56,
    )


def _f22_ctx() -> CruiseContext:
    cf0, k_e = model_coefficients()
    mass = combat_mass_kg(19700, 8200, 1, 152, 4)
    return CruiseContext(
        target=_f22(),
        cf0=cf0,
        k_e=k_e,
        mass_kg=mass,
        n_engines=2,
        bpr=0.30,
        opr=26.0,
        t4_K=1922.0,
        tsl_N=116000.0,
    )


def test_altitude_grid_inclusive_and_integer_steps():
    g = altitude_grid(11000, 14000, 1000)
    assert g == [11000.0, 12000.0, 13000.0, 14000.0]
    with pytest.raises(ValueError, match='步长'):
        altitude_grid(0, 1, 0)
    with pytest.raises(ValueError, match='上界'):
        altitude_grid(2, 1, 1)


def test_evaluate_cruise_forces_f22_cruise_is_feasible():
    ctx = _f22_ctx()
    f = evaluate_cruise_forces(ctx, 0.8, 11800)
    assert f.ld == pytest.approx(8.97, abs=0.05)
    assert f.feasible is True
    assert f.load_raw < 0.92
    assert cruise_point_feasible(ctx, 0.8, 11800) is True


def test_score_cruise_point_infeasible_cycle():
    """效率循环无解时评分须为 -1，且不给出 TSFC。"""
    ctx = _f22_ctx()
    forces = evaluate_cruise_forces(ctx, 0.8, 11800)
    ctx.bpr = 8.0
    ctx.opr = 50.0
    ctx.t4_K = 700.0
    scored = score_cruise_point(ctx, forces)
    assert scored.score == pytest.approx(-1.0)
    assert scored.warning == 'cycle_infeasible'
    assert scored.tsfc_mg_n_s is None


def test_evaluate_cruise_forces_rejects_nonpositive_mach():
    with pytest.raises(ValueError, match='马赫数'):
        evaluate_cruise_forces(_f22_ctx(), 0.0, 12000)


def test_score_cruise_point_positive_efficiency():
    ctx = _f22_ctx()
    f = evaluate_cruise_forces(ctx, 0.8, 11800)
    s = score_cruise_point(ctx, f)
    assert s.eta_o > 0
    assert s.tsfc_mg_n_s is not None and s.tsfc_mg_n_s > 0
    assert s.score == pytest.approx(s.ld * s.eta_o)
    d = scored_to_dict(s)
    assert d['feasible'] is True
    assert d['CDa'] is not None
    assert d['CDs'] is not None
    assert d['thrust_avail_kN'] == pytest.approx(s.thrust_avail_N / 1000.0)


def test_score_cruise_point_applies_tsfc_install_mult():
    """循环外 TSFC 乘数须抬高 TSFC、压低对外 η_o 与评分，且评分仍为 L/D×η_o。"""
    ctx = _f22_ctx()
    f = evaluate_cruise_forces(ctx, 0.8, 11800)
    base = score_cruise_point(ctx, f)
    ctx.tsfc_install_mult = 1.22
    penalized = score_cruise_point(ctx, f)
    assert penalized.tsfc_kg_n_s == pytest.approx(base.tsfc_kg_n_s * 1.22)
    assert penalized.eta_o == pytest.approx(base.eta_o / 1.22)
    assert penalized.score == pytest.approx(penalized.ld * penalized.eta_o)
    assert penalized.score < base.score


def test_any_feasible_altitude_true_at_mach_08():
    ctx = _f22_ctx()
    assert any_feasible_altitude(ctx, 0.8, ALT_MIN_M, ALT_MAX_M, 2000.0) is True


def test_search_best_altitude_mach_08():
    ctx = _f22_ctx()
    best = search_best_altitude(ctx, 0.8, ALT_MIN_M, ALT_MAX_M, 2000.0, 1000.0)
    assert best is not None
    assert best.feasible is True
    assert ALT_MIN_M <= best.alt_m <= 13000.0
    assert best.score > 0


def test_search_best_altitude_none_when_overloaded():
    ctx = _f22_ctx()
    ctx.n_engines = 1
    ctx.tsl_N = 1000.0  # 几乎没有推力
    assert search_best_altitude(ctx, 0.8, ALT_MIN_M, ALT_MAX_M, 2000.0, 1000.0) is None


def test_search_best_altitude_rejects_nonpositive_mach():
    with pytest.raises(ValueError, match='马赫数'):
        search_best_altitude(_f22_ctx(), 0.0)


def test_require_mach_search_bounds_rejects_bad_interval():
    """马赫搜索区间与迭代次数非法时须抛错。"""
    _require_mach_search_bounds(0.5, 2.0, 4)
    with pytest.raises(ValueError, match='区间'):
        _require_mach_search_bounds(1.0, 0.5, 2)
    with pytest.raises(ValueError, match='迭代'):
        _require_mach_search_bounds(0.5, 1.0, 0)


def test_search_max_cruise_mach_none_when_unpowered():
    ctx = _f22_ctx()
    ctx.tsl_N = 1.0
    assert search_max_cruise_mach(ctx, 0.5, 0.8, iters=2, step_m=3000.0) is None
    assert any_feasible_altitude(ctx, 0.8, ALT_MIN_M, ALT_MAX_M, 3000.0) is False
    ctx = _f22_ctx()
    m = search_max_cruise_mach(ctx, 0.5, 2.0, iters=6, step_m=2000.0)
    assert m is not None
    assert 0.5 <= m <= 2.0
    with pytest.raises(ValueError, match='区间'):
        search_max_cruise_mach(ctx, 1.0, 0.5, iters=2)
    with pytest.raises(ValueError, match='迭代'):
        search_max_cruise_mach(ctx, 0.5, 1.0, iters=0)


def test_search_max_cruise_mach_returns_hi_if_feasible():
    ctx = _f22_ctx()
    m = search_max_cruise_mach(ctx, 0.5, 0.8, iters=3, step_m=3000.0)
    assert m == pytest.approx(0.8)


def test_search_max_possible_cruise_mach_faster_than_peak():
    """最大可能巡航应高于峰值高度段的实用最大巡航。"""
    ctx = _f22_csv_ctx()
    peak = search_max_cruise_mach(ctx)
    floor = search_max_possible_cruise_mach(ctx)
    assert peak is not None and floor is not None
    assert floor > peak
    assert search_max_possible_cruise_mach(ctx, 0.5, 0.8, iters=3, step_m=3000.0) == pytest.approx(0.8)
    dead = _f22_ctx()
    dead.tsl_N = 1.0
    assert search_max_possible_cruise_mach(dead, 0.5, 0.8, iters=2, step_m=3000.0) is None
    with pytest.raises(ValueError, match='区间'):
        search_max_possible_cruise_mach(ctx, 1.0, 0.5, iters=2)


def test_search_max_possible_cruise_mach_skips_transonic_hole():
    """跨声速空洞不能截断最大巡航：须落在空洞之后的超音速窗口上沿。"""
    ctx = _csv_ctx('NG6B')
    peak = search_max_cruise_mach(ctx)
    floor = search_max_possible_cruise_mach(ctx)
    assert peak is not None and floor is not None
    assert any_feasible_altitude(ctx, 1.2) is False
    assert any_feasible_altitude(ctx, peak) is True
    assert any_feasible_altitude(ctx, floor) is True
    assert floor + 1e-9 >= peak
    assert search_best_altitude(ctx, 1.2) is None


def test_fixed_machs_include_two_and_supersonic_threshold():
    assert FIXED_MACHS == (0.8, 1.0, 1.2, 1.35, 1.5, 1.75, 2.0)
    assert SUPERSONIC_MACH == 1.0
    assert SUPERSONIC_MACH in FIXED_MACHS
    assert PRACTICAL_MAX_CRUISE_MACH_LO == pytest.approx(1.2)
    assert PRACTICAL_MAX_CRUISE_MACH_LO in FIXED_MACHS


def _csv_ctx(aircraft_id: str, tsl_kn: float | None = None) -> CruiseContext:
    """与仪表盘一致：CSV 几何、统一模型系数、绑定发动机军推。"""
    presets = load_presets()
    engines = load_engine_presets()
    ac = get_preset_by_id(presets, aircraft_id)
    eng = get_preset_by_id(engines, str(ac['engine_id']))
    cf0, k_e = model_coefficients()
    mass = combat_mass_kg(
        ac['empty_kg'], ac['internal_fuel_kg'], ac.get('n_pilots') or 0,
        ac.get('missile_mass_kg') or 0, 4,
    )
    thrust_kn = float(eng['tsl_kN']) if tsl_kn is None else tsl_kn
    return CruiseContext(
        target=aircraft_from_dict({**ac, 'n_stores': 4}),
        cf0=cf0,
        k_e=k_e,
        mass_kg=mass,
        n_engines=int(ac['n_engines']),
        bpr=eng['bpr'],
        opr=eng['opr'],
        t4_K=eng['t4_K'],
        tsl_N=thrust_kn * 1000.0,
    )


def _f22_csv_ctx() -> CruiseContext:
    """F-22 + F119 仪表盘巡航上下文。"""
    return _csv_ctx('F-22')


def test_f22_max_cruise_mach_anchored_at_supercruise():
    """实用最大巡航取高度真正见顶的最大马赫；掉到 11 km 后还能更快。"""
    ctx = _f22_csv_ctx()
    m = search_max_cruise_mach(ctx)
    floor = search_max_possible_cruise_mach(ctx)
    assert m == pytest.approx(1.76, abs=0.005)
    assert floor is not None and floor > m + 0.05
    assert any_feasible_altitude(ctx, F22_SUPERCRUISE_MACH) is True
    assert any_feasible_altitude(ctx, 1.5) is True
    assert any_feasible_altitude(ctx, 2.2) is False
    best_15 = search_best_altitude(ctx, 1.5)
    best_sc = search_best_altitude(ctx, F22_SUPERCRUISE_MACH)
    assert best_15 is not None and best_sc is not None
    assert best_15.ld > 2.0
    assert best_15.cd_breakdown['CDw'] < 0.05
    assert best_sc.alt_m >= 13000.0
    with pytest.raises(ValueError, match='回落'):
        search_max_cruise_mach(ctx, peak_drop_m=-1.0)


def test_contiguous_peak_max_mach_does_not_jump_transonic_hole():
    """全局峰值在前段时，不能把掉高后再爬回的第二段算进去。"""
    profile = [
        (0.8, 12000.0), (1.0, 15000.0), (1.05, 15400.0),
        (1.2, 14000.0), (1.5, 15200.0), (1.76, 15200.0),
    ]
    assert contiguous_peak_max_mach(profile) == pytest.approx(1.05)
    assert inspect.signature(contiguous_peak_max_mach).parameters['peak_drop_m'].default == pytest.approx(0.0)
    assert contiguous_peak_max_mach([], peak_drop_m=200.0) is None
    with pytest.raises(ValueError, match='容差'):
        contiguous_peak_max_mach(profile, peak_drop_m=-1.0)
    # 超巡段才是全局峰值时，取高度真正见顶的最大马赫，不把已掉一格的点算进去
    f22 = [
        (0.8, 12400.0), (1.0, 15000.0), (1.07, 15800.0),
        (1.2, 14600.0), (1.5, 16000.0), (1.76, 16600.0), (1.77, 16600.0),
        (1.79, 16400.0), (1.80, 16200.0),
    ]
    assert contiguous_peak_max_mach(f22) == pytest.approx(1.77)
    assert contiguous_peak_max_mach(f22, peak_drop_m=200.0) == pytest.approx(1.79)
    assert contiguous_peak_max_mach(f22, mach_hi=1.70) == pytest.approx(1.70)


def test_j20_max_cruise_mach_anchored_below_f22():
    """涡扇15 105 kN 下，歼-20 实用最大巡航（高度未回落）低于 F-22。"""
    ctx = _csv_ctx('J-20')
    m = search_max_cruise_mach(ctx)
    assert m == pytest.approx(J20_SUPERCRUISE_MACH, abs=0.02)
    assert any_feasible_altitude(ctx, 1.5) is True
    assert any_feasible_altitude(ctx, 1.76) is True
    assert any_feasible_altitude(ctx, 2.0) is False
    assert m < search_max_cruise_mach(_csv_ctx('F-22'))


def test_j20_legacy_90kn_military_cruise_near_mach_15():
    """早期 90 kN 军推下，掉高度后上限仍低于现役 105 kN。"""
    legacy = _csv_ctx('J-20', tsl_kn=90.0)
    m = search_max_possible_cruise_mach(legacy)
    assert m == pytest.approx(1.53, abs=0.05)
    current = search_max_possible_cruise_mach(_csv_ctx('J-20'))
    assert current > m
    assert search_max_cruise_mach(legacy) < m


def test_transonic_cruise_score_below_subsonic_and_ma135():
    """Ma 1.0 / 1.2 的 L/D×η_o 须低于 Ma 0.8；1.2 还须低于 1.35。"""
    for aid in ('F-22', 'J-20'):
        ctx = _csv_ctx(aid)
        sub = search_best_altitude(ctx, 0.8)
        m10 = search_best_altitude(ctx, 1.0)
        m12 = search_best_altitude(ctx, 1.2)
        m135 = search_best_altitude(ctx, 1.35)
        assert None not in (sub, m10, m12, m135), aid
        assert m10.score < sub.score, aid
        assert m12.score < sub.score, aid
        assert m12.score < m135.score, aid
    uav = _csv_ctx('J-35')
    assert search_best_altitude(uav, 1.2) is None


def test_supersonic_cruise_score_below_subsonic():
    """Ma 1.5 的 L/D×η_o 不得高于 Ma 0.8，否则布雷盖半径会倒挂。"""
    for aid in ('F-22', 'J-20'):
        ctx = _csv_ctx(aid)
        sub = search_best_altitude(ctx, 0.8)
        super15 = search_best_altitude(ctx, 1.5)
        assert sub is not None and super15 is not None
        assert super15.score < sub.score


def test_try_cruise_forces_none_on_bad_cycle():
    """推力循环无解时 try_cruise_forces 返回 None。"""
    ctx = _f22_ctx()
    ctx.opr = 0.5
    assert try_cruise_forces(ctx, 0.8, 12000) is None
    ctx = _f22_ctx()
    assert try_cruise_forces(ctx, 0.8, 11800) is not None


def test_flyable_forces_military_then_afterburner():
    """军推可行用军推；军推不够时用加力。"""
    mil = _f22_csv_ctx()
    ab = CruiseContext(**{**mil.__dict__, 'tsl_N': 156000.0})
    at_cruise = flyable_forces(mil, 0.8, 11800, ab)
    assert at_cruise is not None
    assert at_cruise.thrust_mode == 'military'
    at_high = flyable_forces(mil, 2.15, 11000)
    assert at_high is None
    at_high_ab = flyable_forces(mil, 2.15, 11000, ab)
    assert at_high_ab is not None
    assert at_high_ab.thrust_mode == 'afterburner'
    with pytest.raises(ValueError, match='推力模式'):
        flyable_forces(mil, 0.8, 11800, primary_mode='idle')


def test_search_max_ld_on_band_picks_highest_ld():
    """单一高度带上须返回可飞点中升阻比最大者。"""
    mil = _f22_csv_ctx()
    found = _search_max_ld_on_band(
        mil, 0.8, ALT_MIN_M, ALT_MAX_M, 2000.0, 1000.0, None, 'military',
    )
    assert found is not None
    assert found.thrust_mode == 'military'
    assert found.forces.ld > 0
    dead = _f22_csv_ctx()
    dead.tsl_N = 1.0
    assert _search_max_ld_on_band(
        dead, 0.8, ALT_MIN_M, ALT_MAX_M, 3000.0, 1500.0, None, 'military',
    ) is None


def test_search_max_ld_altitude_cruise_and_ab():
    """Ma 0.8 最大 L/D 不低于巡航点；Ma 2.15 军推不可飞、加力可飞。"""
    mil = _f22_csv_ctx()
    ab = CruiseContext(**{**mil.__dict__, 'tsl_N': 156000.0})
    cruise = search_best_altitude(mil, 0.8)
    max_ld = search_max_ld_altitude(mil, 0.8)
    assert max_ld is not None and cruise is not None
    assert max_ld.thrust_mode == 'military'
    assert max_ld.forces.ld >= cruise.ld - 1e-9
    assert search_max_ld_altitude(mil, 2.15) is None
    ab_ld = search_max_ld_altitude(mil, 2.15, ab_ctx=ab)
    assert ab_ld is not None
    assert ab_ld.thrust_mode == 'afterburner'
    assert ab_ld.forces.ld > 0
    with pytest.raises(ValueError, match='马赫数'):
        search_max_ld_altitude(mil, 0.0)


def test_search_max_ld_altitude_ab_full_thrust_and_sea_level_fallback():
    """加力按全部推力；巡航高度带不够时落到海平面包线。"""
    mil = _csv_ctx('F-35C')
    ab92 = CruiseContext(
        **{**mil.__dict__, 'tsl_N': 191000.0, 'thrust_margin': THRUST_MARGIN_DEFAULT},
    )
    ab100 = CruiseContext(
        **{**mil.__dict__, 'tsl_N': 191000.0, 'thrust_margin': MAX_SPEED_THRUST_MARGIN},
    )
    # 加力 92% 裕度在 Ma 1.50 仍不够（rough 超音速波阻）；全推力可飞
    assert search_max_ld_altitude(mil, 1.50, ab_ctx=ab92) is None
    full = search_max_ld_altitude(mil, 1.50, ab_ctx=ab100)
    assert full is not None
    assert full.thrust_mode == 'afterburner'
    assert full.forces.ld > 0
    low_only = search_max_ld_altitude(
        mil, 1.50, alt_min_m=18000.0, alt_max_m=20000.0, ab_ctx=ab100,
        ab_alt_min_m=0.0, ab_alt_max_m=20000.0,
    )
    assert low_only is not None
    assert low_only.thrust_mode == 'afterburner'


def test_scan_altitudes_at_mach_covers_grid_and_scores():
    """给定马赫须按高度网格返回升阻比、推力、负载与效率。"""
    rows = scan_altitudes_at_mach(_f22_ctx(), 0.8, 11000, 14000, 1000)
    assert [p.alt_m for p in rows] == [11000.0, 12000.0, 13000.0, 14000.0]
    assert all(p.ld > 0 for p in rows)
    assert all(p.thrust_avail_N > 0 for p in rows)
    assert any(p.feasible for p in rows)
    packed = altitude_scan_fields(rows[0], selected=True)
    assert packed['selected'] is True
    assert packed['thrust_avail_kN'] == pytest.approx(rows[0].thrust_avail_N / 1000.0)
    assert packed['eta_th'] >= 0
    assert packed['eta_p'] >= 0
    assert packed['eta_o'] >= 0
    assert 'load' in packed
    with pytest.raises(ValueError, match='马赫数'):
        scan_altitudes_at_mach(_f22_ctx(), 0.0)


def test_build_altitude_scan_inserts_refined_best():
    """细化后的最佳高度若不在粗网格上，须插入并标 selected。"""
    ctx = _f22_ctx()
    selected = score_cruise_point(ctx, evaluate_cruise_forces(ctx, 0.8, 11800))
    scan = build_altitude_scan(ctx, 0.8, 11000, 14000, 1000, selected=selected)
    alts = [row['alt_m'] for row in scan]
    assert alts == sorted(alts)
    assert 11800.0 in alts
    assert 11000.0 in alts
    marked = [row for row in scan if row['selected']]
    assert len(marked) == 1
    assert marked[0]['alt_m'] == pytest.approx(11800.0)
    empty = build_altitude_scan(ctx, 0.8, 11000, 14000, 1000, selected=None)
    assert all(not row['selected'] for row in empty)
    assert 11800.0 not in [row['alt_m'] for row in empty]


def test_max_ld_fields_none_and_point():
    """最大升阻比字段在无点和有点时结构一致。"""
    empty = max_ld_fields(None)
    assert empty['max_ld'] is None
    assert empty['max_ld_thrust_mode'] is None
    mil = _f22_csv_ctx()
    point = search_max_ld_altitude(mil, 0.8)
    packed = max_ld_fields(point)
    assert packed['max_ld'] == pytest.approx(point.forces.ld)
    assert packed['max_ld_alt_m'] == pytest.approx(point.forces.alt_m)
    assert packed['max_ld_thrust_mode'] == 'military'


def test_f22_f35c_mach08_ld_eta_peaks_near_catalog_altitude():
    """Ma 0.8 的 L/D×η_o 应在标定巡航高度附近见顶，而不是 15 km。"""
    f22 = search_best_altitude(_f22_csv_ctx(), 0.8)
    f35 = search_best_altitude(_csv_ctx('F-35C'), 0.8)
    assert f22 is not None and f35 is not None
    assert 11000.0 <= f22.alt_m <= 13000.0
    assert 11000.0 <= f35.alt_m <= 13000.0
    high = evaluate_cruise_forces(_f22_csv_ctx(), 0.8, 15000.0)
    assert high.ld < f22.ld


def test_low_wing_loading_can_cruise_higher_at_mach08():
    """低翼载机同一马赫 CL 更小，L/D×η_o 最佳高度应不低于 F-22。"""
    f22 = search_best_altitude(_f22_csv_ctx(), 0.8)
    light = search_best_altitude(_csv_ctx('53636'), 0.8)
    assert f22 is not None and light is not None
    assert light.alt_m >= f22.alt_m - 200.0


def test_f22_cruise_altitude_dips_in_transonic_then_holds_supercruise():
    """Ma 0.8→1.0 爬高；跨声速鼓包抬高 CDw、压低评分；超巡带在 1.76 后回落。"""
    ctx = _f22_csv_ctx()
    a08 = search_best_altitude(ctx, 0.8)
    a10 = search_best_altitude(ctx, 1.0)
    a12 = search_best_altitude(ctx, 1.2)
    a15 = search_best_altitude(ctx, 1.5)
    a176 = search_best_altitude(ctx, 1.76)
    a180 = search_best_altitude(ctx, 1.80)
    assert None not in (a08, a10, a12, a15, a176, a180)
    assert a08.alt_m < a10.alt_m
    assert a12.cd_breakdown['CDw'] > a10.cd_breakdown['CDw']
    assert a12.score < a08.score
    assert a15.alt_m > a12.alt_m
    assert a176.alt_m >= a15.alt_m - 200.0
    assert a180.alt_m < a176.alt_m - PEAK_ALT_DROP_M + 1e-6
    assert a15.load_raw > a08.load_raw
    assert a176.load_raw >= 0.90


def test_search_max_cruise_mach_default_lo_is_mach_12():
    """实用最大巡航默认马赫下界须为 1.2，高度容差默认为 0（真正见顶）。"""
    params = inspect.signature(search_max_cruise_mach).parameters
    default_lo = params['mach_lo'].default
    assert default_lo == pytest.approx(PRACTICAL_MAX_CRUISE_MACH_LO)
    assert default_lo == pytest.approx(1.2)
    assert params['peak_drop_m'].default == pytest.approx(0.0)


def test_j35_and_j35a_max_cruise_anchored():
    """歼-35 军推穿不过跨声速空洞；歼-35A 涡扇19 军推 70 kN 后可超巡。"""
    j35 = search_max_cruise_mach(_csv_ctx('J-35'))
    j35a = search_max_cruise_mach(_csv_ctx('J-35A'))
    assert j35 is None
    assert j35a == pytest.approx(1.47, abs=0.02)
    assert any_feasible_altitude(_csv_ctx('J-35'), 1.2) is False
    assert any_feasible_altitude(_csv_ctx('J-35A'), 1.2) is False


def test_search_max_cruise_mach_when_low_mach_infeasible():
    """Ma 0.5 在 11 km 会因大迎角阻力不可飞，仍应搜到 F-22 超巡锚点。"""
    ctx = _f22_csv_ctx()
    assert any_feasible_altitude(ctx, MACH_SEARCH_LO) is False
    m = search_max_cruise_mach(ctx)
    assert m == pytest.approx(1.76, abs=0.005)


def test_snap_mach_quantizes_and_rejects_bad_step():
    """马赫须收到步长网格；步长非法时报错。"""
    assert snap_mach(1.6099999999999999, 0.01) == pytest.approx(1.61)
    assert snap_mach(1.76, 0.01) == pytest.approx(1.76)
    with pytest.raises(ValueError, match='步长'):
        snap_mach(1.2, 0.0)


def test_profile_machs_centi_step_hits_every_point_without_pins():
    """0.01 网格须扫到 1.21 / 1.76 / 1.77，不靠超巡钉子补点。"""
    machs = profile_machs(1.2, 2.5, step=0.01, extra=())
    assert machs[0] == pytest.approx(1.2)
    assert machs[-1] == pytest.approx(2.5)
    assert len(machs) == 131
    for target in (1.21, 1.76, 1.77, 1.79):
        assert any(abs(m - target) < 1e-9 for m in machs), target
    diffs = [round(machs[i + 1] - machs[i], 10) for i in range(len(machs) - 1)]
    assert set(diffs) == {0.01}


def test_profile_machs_includes_supercruise_band_and_rejects_bad_step():
    """粗步长仍可钉上固定评估点与超巡带上沿；端点为区间原值；步长/区间非法时报错。"""
    machs = profile_machs(0.5, 2.5, step=0.05)
    assert machs[0] == 0.5
    assert machs[-1] == 2.5
    assert 1.76 in machs
    assert 1.5 in machs
    for pin in FIXED_MACHS:
        assert pin in machs
    with pytest.raises(ValueError, match='步长'):
        profile_machs(0.8, 1.5, step=0.0)
    with pytest.raises(ValueError, match='区间'):
        profile_machs(1.5, 0.8, step=0.1)


def test_scan_best_altitude_profile_endpoints_and_rejects_bad_step():
    """剖面须包含区间端点；默认步长 0.01；步长/区间非法时报错。"""
    ctx = _f22_csv_ctx()
    prof = scan_best_altitude_profile(ctx, 0.8, 1.5, step=0.1)
    assert prof[0].mach == 0.8
    assert prof[-1].mach == 1.5
    assert MACH_PROFILE_STEP == pytest.approx(0.01)
    assert PEAK_ALT_DROP_M == pytest.approx(ALT_REFINE_M)
    with pytest.raises(ValueError, match='步长'):
        scan_best_altitude_profile(ctx, 0.8, 1.5, step=0.0)
    with pytest.raises(ValueError, match='区间'):
        scan_best_altitude_profile(ctx, 1.5, 0.8, step=0.1)


def test_practical_max_cruise_is_mach_at_peak_altitude():
    """实用最大巡航须等于最佳高度真正见顶的最大马赫，不能用掉高一格的容差往上加。"""
    for aid in ('F-22', 'J-20', 'J-50', 'NG6B'):
        ctx = _csv_ctx(aid)
        prof = scan_best_altitude_profile(ctx, PRACTICAL_MAX_CRUISE_MACH_LO)
        assert prof, aid
        peak = max(point.alt_m for point in prof)
        idx = next(i for i, point in enumerate(prof) if point.alt_m == peak)
        hi = idx
        while hi + 1 < len(prof) and prof[hi + 1].alt_m == peak:
            hi += 1
        mach = search_max_cruise_mach(ctx)
        assert mach == pytest.approx(prof[hi].mach), aid
        at = search_best_altitude(ctx, mach)
        assert at is not None
        assert at.alt_m == pytest.approx(peak)
        if hi + 1 < len(prof):
            assert prof[hi + 1].alt_m < peak, aid
    f22 = search_max_cruise_mach(_csv_ctx('F-22'))
    assert f22 == pytest.approx(1.76, abs=0.005)
    after = search_best_altitude(_csv_ctx('F-22'), 1.80)
    at = search_best_altitude(_csv_ctx('F-22'), f22)
    assert after is not None and at is not None
    assert after.alt_m < at.alt_m - PEAK_ALT_DROP_M + 1e-6


def test_ws10c_uav_slim_fuse_enables_53636_supercruise():
    """细机身无人机均可越过跨声速鼓包后超巡。"""
    assert search_max_cruise_mach(_csv_ctx('53636')) == pytest.approx(1.56, abs=0.02)
    assert any_feasible_altitude(_csv_ctx('53636'), 1.2) is True
    for aid in ('53536', '53636N'):
        m = search_max_cruise_mach(_csv_ctx(aid))
        assert m is not None and m >= PRACTICAL_MAX_CRUISE_MACH_LO, aid
        assert any_feasible_altitude(_csv_ctx(aid), 1.2) is True, aid


def test_j50_practical_max_from_centi_grid_not_f22_pin():
    """歼-50 按自身高度峰值取马赫，不是钉在 F-22。"""
    f22 = search_max_cruise_mach(_csv_ctx('F-22'))
    j50 = search_max_cruise_mach(_csv_ctx('J-50'))
    j50n = search_max_cruise_mach(_csv_ctx('J-50N'))
    assert f22 == pytest.approx(1.76, abs=0.005)
    assert j50 == pytest.approx(1.77, abs=0.005)
    assert j50n == pytest.approx(1.78, abs=0.005)
    a_f22 = search_best_altitude(_csv_ctx('F-22'), f22)
    a_j50 = search_best_altitude(_csv_ctx('J-50'), j50)
    assert a_f22 is not None and a_j50 is not None
    assert a_j50.alt_m > a_f22.alt_m + 500.0


def test_search_max_cruise_mach_skips_transonic_peak():
    """从 0.5 搜会停在跨声速高度峰值；默认 Ma 1.2 下界对穿不过空洞的机为 None。"""
    ctx = _csv_ctx('J-35')
    transonic = search_max_cruise_mach(ctx, 0.5, 2.5)
    assert transonic is not None
    assert transonic < PRACTICAL_MAX_CRUISE_MACH_LO
    skipped = search_max_cruise_mach(ctx)
    assert skipped is None
    f35c = search_max_cruise_mach(_csv_ctx('F-35C'))
    assert f35c is None
