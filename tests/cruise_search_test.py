"""巡航高度 / 最大马赫搜索单元测试。"""
from __future__ import annotations

import pytest

from utils.combat_radius.combat_radius_presets import get_preset_by_id, load_engine_presets, load_presets
from utils.combat_radius.cruise_load import combat_mass_kg
from utils.combat_radius.cruise_search import (
    ALT_MAX_M,
    ALT_MIN_M,
    FIXED_MACHS,
    MACH_SEARCH_LO,
    SUPERSONIC_MACH,
    CruiseContext,
    any_feasible_altitude,
    altitude_grid,
    cruise_point_feasible,
    evaluate_cruise_forces,
    flyable_forces,
    max_ld_fields,
    score_cruise_point,
    scored_to_dict,
    search_best_altitude,
    search_max_cruise_mach,
    search_max_ld_altitude,
    try_cruise_forces,
)
from utils.combat_radius.lift_drag import (
    F22_SUPERCRUISE_MACH,
    J20_SUPERCRUISE_MACH,
    J35A_SUPERCRUISE_MACH,
    J35_SUPERCRUISE_MACH,
    Aircraft,
    aircraft_from_dict,
    calibrate,
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
    cf0, k_e = calibrate(_f35c(), 8.8, _f22(), 8.0)
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
    assert f.ld == pytest.approx(8.0, abs=1e-6)
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
    assert d['thrust_avail_kN'] == pytest.approx(s.thrust_avail_N / 1000.0)


def test_any_feasible_altitude_true_at_mach_08():
    ctx = _f22_ctx()
    assert any_feasible_altitude(ctx, 0.8, ALT_MIN_M, ALT_MAX_M, 2000.0) is True


def test_search_best_altitude_mach_08():
    ctx = _f22_ctx()
    best = search_best_altitude(ctx, 0.8, ALT_MIN_M, ALT_MAX_M, 2000.0, 1000.0)
    assert best is not None
    assert best.feasible is True
    assert ALT_MIN_M <= best.alt_m <= 12500.0
    assert best.score > 0


def test_search_best_altitude_none_when_overloaded():
    ctx = _f22_ctx()
    ctx.n_engines = 1
    ctx.tsl_N = 1000.0  # 几乎没有推力
    assert search_best_altitude(ctx, 0.8, ALT_MIN_M, ALT_MAX_M, 2000.0, 1000.0) is None


def test_search_best_altitude_rejects_nonpositive_mach():
    with pytest.raises(ValueError, match='马赫数'):
        search_best_altitude(_f22_ctx(), 0.0)


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


def test_fixed_machs_include_two_and_supersonic_threshold():
    assert FIXED_MACHS == (0.8, 1.5, 1.76, 2.0)
    assert SUPERSONIC_MACH == 1.0


def _csv_ctx(aircraft_id: str, tsl_kn: float | None = None) -> CruiseContext:
    """与仪表盘一致：CSV 几何、亚音速锚点 L/D、绑定发动机军推。"""
    presets = load_presets()
    engines = load_engine_presets()
    f35 = get_preset_by_id(presets, 'F-35C')
    f22 = get_preset_by_id(presets, 'F-22')
    ac = get_preset_by_id(presets, aircraft_id)
    eng = get_preset_by_id(engines, str(ac['engine_id']))
    a1 = aircraft_from_dict(f35)
    a2 = aircraft_from_dict(f22)
    cf0, k_e = calibrate(a1, f35['ld_known'], a2, f22['ld_known'])
    mass = combat_mass_kg(
        ac['empty_kg'], ac['internal_fuel_kg'], ac.get('n_pilots') or 0,
        ac.get('missile_mass_kg') or 0, 4,
    )
    thrust_kn = float(eng['tsl_kN']) if tsl_kn is None else tsl_kn
    return CruiseContext(
        target=aircraft_from_dict(ac),
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
    """超音速波阻须使 F-22 军推最大巡航落在超巡锚点 Ma 1.76 附近。"""
    ctx = _f22_csv_ctx()
    m = search_max_cruise_mach(ctx)
    assert m == pytest.approx(F22_SUPERCRUISE_MACH, abs=0.02)
    assert any_feasible_altitude(ctx, F22_SUPERCRUISE_MACH) is True
    assert any_feasible_altitude(ctx, 1.5) is True
    assert any_feasible_altitude(ctx, 2.0) is False
    best_15 = search_best_altitude(ctx, 1.5)
    assert best_15 is not None
    assert best_15.ld > 2.0
    assert best_15.cd_breakdown['CDw'] < 0.05


def test_j20_max_cruise_mach_anchored_below_f22():
    """涡扇15 105 kN 军推下，歼-20 最大巡航约 Ma 1.68，仍低于 F-22。"""
    ctx = _csv_ctx('J-20')
    m = search_max_cruise_mach(ctx)
    assert m == pytest.approx(J20_SUPERCRUISE_MACH, abs=0.02)
    assert any_feasible_altitude(ctx, 1.5) is True
    assert any_feasible_altitude(ctx, 1.76) is False


def test_j20_legacy_90kn_military_cruise_near_mach_15():
    """鸭翼波阻按早期 90 kN 军推对齐最大巡航约 Ma 1.5。"""
    m = search_max_cruise_mach(_csv_ctx('J-20', tsl_kn=90.0))
    assert m == pytest.approx(1.5, abs=0.02)
    current = search_max_cruise_mach(_csv_ctx('J-20'))
    assert current > m


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
    at_high = flyable_forces(mil, 2.0, 11000)
    assert at_high is None
    at_high_ab = flyable_forces(mil, 2.0, 11000, ab)
    assert at_high_ab is not None
    assert at_high_ab.thrust_mode == 'afterburner'
    with pytest.raises(ValueError, match='推力模式'):
        flyable_forces(mil, 0.8, 11800, primary_mode='idle')


def test_search_max_ld_altitude_cruise_and_ab():
    """Ma 0.8 最大 L/D 不低于巡航点；Ma 2.0 军推不可飞、加力可飞。"""
    mil = _f22_csv_ctx()
    ab = CruiseContext(**{**mil.__dict__, 'tsl_N': 156000.0})
    cruise = search_best_altitude(mil, 0.8)
    max_ld = search_max_ld_altitude(mil, 0.8)
    assert max_ld is not None and cruise is not None
    assert max_ld.thrust_mode == 'military'
    assert max_ld.forces.ld >= cruise.ld - 1e-9
    assert search_max_ld_altitude(mil, 2.0) is None
    ab_ld = search_max_ld_altitude(mil, 2.0, ab_ctx=ab)
    assert ab_ld is not None
    assert ab_ld.thrust_mode == 'afterburner'
    assert ab_ld.forces.ld > 0
    with pytest.raises(ValueError, match='马赫数'):
        search_max_ld_altitude(mil, 0.0)


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
    assert 11000.0 <= f22.alt_m <= 12500.0
    assert 11000.0 <= f35.alt_m <= 12500.0
    high = evaluate_cruise_forces(_f22_csv_ctx(), 0.8, 15000.0)
    assert high.ld < f22.ld


def test_low_wing_loading_can_cruise_higher_at_mach08():
    """低翼载机同一马赫 CL 更小，L/D×η_o 最佳高度应不低于 F-22。"""
    f22 = search_best_altitude(_f22_csv_ctx(), 0.8)
    light = search_best_altitude(_csv_ctx('53636'), 0.8)
    assert f22 is not None and light is not None
    assert light.alt_m >= f22.alt_m - 200.0


def test_f22_cruise_altitude_rises_until_mach_15_then_drops():
    """Ma 1.5 以前最佳高度随速度升高；接近最大巡航时军推不够，高度回落。"""
    ctx = _f22_csv_ctx()
    a08 = search_best_altitude(ctx, 0.8)
    a10 = search_best_altitude(ctx, 1.0)
    a12 = search_best_altitude(ctx, 1.2)
    a14 = search_best_altitude(ctx, 1.4)
    a15 = search_best_altitude(ctx, 1.5)
    a176 = search_best_altitude(ctx, 1.76)
    assert None not in (a08, a10, a12, a14, a15, a176)
    assert a08.alt_m < a10.alt_m < a12.alt_m
    assert a12.alt_m <= a14.alt_m + 200.0
    assert a15.alt_m >= a12.alt_m - 200.0
    assert a176.alt_m < a15.alt_m
    assert a15.load_raw > a08.load_raw
    assert a176.load_raw >= 0.90


def test_j35_and_j35a_max_cruise_anchored():
    """歼-35 / 歼-35A 军推最大巡航分别标定到 Ma 1.12 / 1.47。"""
    j35 = search_max_cruise_mach(_csv_ctx('J-35'))
    j35a = search_max_cruise_mach(_csv_ctx('J-35A'))
    assert j35 == pytest.approx(J35_SUPERCRUISE_MACH, abs=0.03)
    assert j35a == pytest.approx(J35A_SUPERCRUISE_MACH, abs=0.03)
    assert j35a > j35


def test_search_max_cruise_mach_when_low_mach_infeasible():
    """Ma 0.5 在 11 km 会因大迎角阻力不可飞，仍应搜到 F-22 超巡锚点。"""
    ctx = _f22_csv_ctx()
    assert any_feasible_altitude(ctx, MACH_SEARCH_LO) is False
    m = search_max_cruise_mach(ctx)
    assert m == pytest.approx(F22_SUPERCRUISE_MACH, abs=0.02)
