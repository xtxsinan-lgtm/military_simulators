"""巡航高度 / 最大马赫搜索单元测试。"""
from __future__ import annotations

import pytest

from utils.combat_radius.cruise_load import combat_mass_kg
from utils.combat_radius.cruise_search import (
    ALT_MAX_M,
    ALT_MIN_M,
    CruiseContext,
    any_feasible_altitude,
    altitude_grid,
    cruise_point_feasible,
    evaluate_cruise_forces,
    score_cruise_point,
    scored_to_dict,
    search_best_altitude,
    search_max_cruise_mach,
)
from utils.combat_radius.lift_drag import Aircraft, calibrate


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
    assert d['thrust_avail_kN'] == pytest.approx(s.thrust_avail_N / 1000.0)


def test_any_feasible_altitude_true_at_mach_08():
    ctx = _f22_ctx()
    assert any_feasible_altitude(ctx, 0.8, ALT_MIN_M, ALT_MAX_M, 2000.0) is True


def test_search_best_altitude_mach_08():
    ctx = _f22_ctx()
    best = search_best_altitude(ctx, 0.8, ALT_MIN_M, ALT_MAX_M, 2000.0, 1000.0)
    assert best is not None
    assert best.feasible is True
    assert ALT_MIN_M <= best.alt_m <= ALT_MAX_M
    assert best.score > 0


def test_search_best_altitude_none_when_overloaded():
    ctx = _f22_ctx()
    ctx.n_engines = 1
    ctx.tsl_N = 1000.0  # 几乎没有推力
    assert search_best_altitude(ctx, 0.8, ALT_MIN_M, ALT_MAX_M, 2000.0, 1000.0) is None


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
