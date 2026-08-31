"""发动机总效率与 TSFC 单元测试。"""
from __future__ import annotations

import math

import pytest

from utils.combat_radius.engine_efficiency import (
    F135_TSFC_INSTALL_MULT,
    FUEL_LHV_J_KG,
    G0,
    TSFC_INSTALL_MULT_DEFAULT,
    _find_valid_floor,
    compute_engine_efficiency,
    cycle_for_t4,
    engine_result_to_dict,
    eta_o_after_install,
    find_optimal_load,
    fpr_default,
    isa,
    opr_default,
    parse_tsfc_install_mult,
    solve_t4_for_thrust,
    tsfc_from_eta_o,
)


def test_isa_sea_level_and_tropopause():
    t0, p0 = isa(0.0)
    assert t0 == pytest.approx(288.15)
    assert p0 == pytest.approx(101325.0, rel=1e-6)
    t11, _ = isa(11000.0)
    assert t11 == pytest.approx(216.65)
    t15, p15 = isa(15000.0)
    assert t15 == pytest.approx(216.65)
    assert p15 < 22632.0


def test_opr_and_fpr_defaults_bounded():
    assert opr_default(0.0) == pytest.approx(12.0)
    assert opr_default(100.0) == 50.0
    assert opr_default(-10.0) == 8.0
    assert 1.15 <= fpr_default(0.3) <= 1.8
    assert fpr_default(0.0) == pytest.approx(1.8)


def _f135_cycle(t4: float, bleed: float = 0.0):
    t0, p0 = isa(10000.0)
    v0 = 0.8 * math.sqrt(1.4 * 287.0 * t0)
    tau_r = 1.0 + 0.2 * 0.8 ** 2
    return cycle_for_t4(
        t4, 0.57, t0, p0, v0, tau_r, 28.0, fpr_default(0.57), 0.83, 0.83, 0.95, bleed,
    )


def test_cycle_for_t4_valid_and_qin_failure():
    ok = _f135_cycle(2260.0)
    assert ok.valid is True
    assert ok.thrust_spec > 0
    assert 0 < ok.eta_o < 1
    dead = _f135_cycle(200.0)
    assert dead.valid is False
    assert dead.reason == 'qin'


def test_find_valid_floor_and_solve_t4_for_thrust():
    t0, p0 = isa(10000.0)
    v0 = 0.8 * math.sqrt(1.4 * 287.0 * t0)
    tau_r = 1.0 + 0.2 * 0.8 ** 2
    fpr = fpr_default(0.57)
    floor = _find_valid_floor(
        0.57, t0, p0, v0, tau_r, 28.0, fpr, 0.83, 0.83, 0.95, 0.0, 500.0, 2260.0,
    )
    assert cycle_for_t4(floor, 0.57, t0, p0, v0, tau_r, 28.0, fpr, 0.83, 0.83, 0.95, 0.0).valid
    max_r = cycle_for_t4(2260.0, 0.57, t0, p0, v0, tau_r, 28.0, fpr, 0.83, 0.83, 0.95, 0.0)
    mid_target = 0.5 * max_r.thrust_spec
    t4 = solve_t4_for_thrust(
        mid_target, 0.57, t0, p0, v0, tau_r, 28.0, fpr, 0.83, 0.83, 0.95, 0.0,
        lo_raw=500.0, hi=2260.0,
    )
    got = cycle_for_t4(t4, 0.57, t0, p0, v0, tau_r, 28.0, fpr, 0.83, 0.83, 0.95, 0.0)
    assert got.thrust_spec == pytest.approx(mid_target, rel=0.02)


def test_compute_engine_efficiency_f135_partial_load():
    r = compute_engine_efficiency(
        bpr=0.57, mach=0.8, altitude_m=10000.0, load=0.5, OPR=28.0, T4max=2260.0,
    )
    assert r.valid is True
    assert r.T4_solved < 2260.0
    assert 0.1 < r.eta_o < 0.4
    d = engine_result_to_dict(r)
    assert d['eta_th'] == r.eta_th
    with pytest.raises(ValueError, match='负载'):
        compute_engine_efficiency(bpr=0.57, mach=0.8, altitude_m=10000.0, load=1.2)
    with pytest.raises(ValueError, match='有效范围'):
        compute_engine_efficiency(bpr=-1, mach=0.8, altitude_m=10000.0, load=0.5)


def test_compute_engine_efficiency_infeasible_cycle():
    r = compute_engine_efficiency(
        bpr=8.0, mach=0.8, altitude_m=10000.0, load=1.0, OPR=50.0, T4max=700.0,
    )
    assert r.valid is False
    assert r.warning == 'cycle_infeasible'


def test_find_optimal_load_returns_interior_maximum():
    load, eta = find_optimal_load(
        bpr=0.57, mach=0.8, altitude_m=10000.0, OPR=28.0, T4max=2260.0, coarse_step=0.05,
    )
    assert 0.05 <= load <= 1.0
    assert eta > 0.1


def test_find_optimal_load_increases_with_mach():
    """同一发动机在 tropopause，最佳负载须随马赫升高。"""
    kwargs = dict(bpr=0.30, altitude_m=12000.0, OPR=26.0, T4max=1922.0, coarse_step=0.02)
    lo, _ = find_optimal_load(mach=0.8, **kwargs)
    hi, _ = find_optimal_load(mach=1.5, **kwargs)
    assert hi > lo + 0.1


def test_tsfc_from_eta_o_identity():
    v0 = 240.0
    eta_o = 0.20
    d = tsfc_from_eta_o(v0, eta_o)
    assert d['tsfc_kg_n_s'] == pytest.approx(v0 / (eta_o * FUEL_LHV_J_KG))
    assert d['tsfc_mg_n_s'] == pytest.approx(d['tsfc_kg_n_s'] * 1e6)
    assert d['tsfc_lb_lbf_h'] == pytest.approx(d['tsfc_kg_n_s'] * G0 * 3600.0)
    with pytest.raises(ValueError, match='总效率'):
        tsfc_from_eta_o(240.0, 0.0)
    with pytest.raises(ValueError, match='速度'):
        tsfc_from_eta_o(-1.0, 0.2)
    with pytest.raises(ValueError, match='热值'):
        tsfc_from_eta_o(240.0, 0.2, fuel_lhv_j_kg=0.0)
    with pytest.raises(ValueError, match='安装'):
        tsfc_from_eta_o(240.0, 0.2, install_mult=0.0)


def test_parse_tsfc_install_mult_and_eta_o_after_install():
    """缺省 1.0；F135 推荐 1.15；惩罚须压低对外 η_o、抬高 TSFC。"""
    assert parse_tsfc_install_mult(None) == TSFC_INSTALL_MULT_DEFAULT
    assert parse_tsfc_install_mult('') == TSFC_INSTALL_MULT_DEFAULT
    assert parse_tsfc_install_mult(1.15) == pytest.approx(F135_TSFC_INSTALL_MULT)
    with pytest.raises(ValueError, match='安装'):
        parse_tsfc_install_mult(0.0)
    eta = 0.192
    assert eta_o_after_install(eta, 1.0) == pytest.approx(eta)
    assert eta_o_after_install(eta, 1.15) == pytest.approx(eta / 1.15)
    base = tsfc_from_eta_o(240.0, eta)
    penalized = tsfc_from_eta_o(240.0, eta, install_mult=1.15)
    assert penalized['tsfc_kg_n_s'] == pytest.approx(base['tsfc_kg_n_s'] * 1.15)
    assert penalized['tsfc_install_mult'] == pytest.approx(1.15)
    with pytest.raises(ValueError, match='安装'):
        eta_o_after_install(0.2, 0.0)
