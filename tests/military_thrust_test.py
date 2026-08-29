"""军推理想循环估算单元测试。"""
from __future__ import annotations

import math

import pytest

from utils.combat_radius.military_thrust import (
    ETA_C_DEFAULT,
    GAMMA,
    TF_TO_N,
    estimate_military_thrust,
    fan_pressure_ratio,
    ideal_stream_velocities,
    isa,
    thrust_result_to_dict,
)


def test_isa_sea_level_and_tropopause():
    t0, p0 = isa(0.0)
    assert t0 == pytest.approx(288.15, abs=1e-9)
    assert p0 == pytest.approx(101325.0, abs=1e-6)
    t11, p11 = isa(11000.0)
    assert t11 == pytest.approx(216.65, abs=1e-9)
    assert p11 == pytest.approx(22632.0, rel=1e-3)


def test_isa_isothermal_and_upper_stratosphere():
    t15, p15 = isa(15000.0)
    assert t15 == pytest.approx(216.65, abs=1e-9)
    assert p15 < 22632.0
    t25, p25 = isa(25000.0)
    assert t25 == pytest.approx(221.65, abs=1e-9)
    assert 0 < p25 < p15


def test_fan_pressure_ratio_empirical_curve():
    assert fan_pressure_ratio(0.0) == pytest.approx(3.2, abs=1e-12)
    assert fan_pressure_ratio(0.30) == pytest.approx(1.2 + 2.0 * math.exp(-0.35 * 0.30))
    assert fan_pressure_ratio(10.0) == pytest.approx(1.2, abs=0.07)
    assert fan_pressure_ratio(10.0) > 1.2


def test_ideal_stream_velocities_physical_and_unphysical():
    t0 = 288.15
    tau_c = 26.0 ** ((GAMMA - 1.0) / GAMMA)
    tau_f = fan_pressure_ratio(0.30) ** ((GAMMA - 1.0) / GAMMA)
    ok = ideal_stream_velocities(t0, 1.0, tau_c, 1922.0 / t0, tau_f, 0.30, 1.0 / 0.87)
    assert ok is not None
    assert ok.V9 > 0 and ok.V19 > 0
    assert 0 < ok.tau_t < 1
    dead = ideal_stream_velocities(t0, 1.0, tau_c, 400.0 / t0, tau_f, 0.30, 1.0 / 0.87)
    assert dead is None


def test_thrust_result_to_dict_includes_kn_and_tf():
    r = estimate_military_thrust(
        bpr=0.30, opr=26.0, t4_K=1922.0, tsl_N=116000.0, alt_m=11000.0, mach=1.5,
    )
    d = thrust_result_to_dict(r)
    assert d['thrust_kN'] == pytest.approx(r.thrust_N / 1000.0)
    assert d['thrust_tf'] == pytest.approx(r.thrust_N / TF_TO_N)
    assert d['fan_pr'] == pytest.approx(fan_pressure_ratio(0.30))


def test_estimate_military_thrust_f119_cruise_point():
    """F119 在 11000 m、Ma 1.5 下可用军推应明显低于海平面静止值。"""
    r = estimate_military_thrust(
        bpr=0.30,
        opr=26.0,
        t4_K=1922.0,
        tsl_N=116000.0,
        alt_m=11000.0,
        mach=1.5,
        eta_c=ETA_C_DEFAULT,
    )
    assert r.thrust_N > 0
    assert r.thrust_N < 116000.0
    assert 0.1 < r.alpha < 0.6
    assert r.tau_r == pytest.approx(1.0 + 0.2 * 1.5 ** 2)
    assert r.T0 == pytest.approx(216.65, abs=1e-9)
    assert r.mdot_ratio < 1.0
    assert r.fan_pr > 1.0


def test_estimate_military_thrust_fan_override_and_sls_static():
    sls = estimate_military_thrust(
        bpr=0.30, opr=26.0, t4_K=1922.0, tsl_N=116000.0, alt_m=0.0, mach=0.0,
    )
    assert sls.thrust_N == pytest.approx(116000.0, rel=1e-9)
    assert sls.alpha == pytest.approx(1.0, abs=1e-12)
    over = estimate_military_thrust(
        bpr=0.30, opr=26.0, t4_K=1922.0, tsl_N=116000.0,
        alt_m=0.0, mach=0.0, fan_pr_override=1.8,
    )
    assert over.fan_pr == pytest.approx(1.8)


def test_estimate_military_thrust_rejects_bad_inputs():
    with pytest.raises(ValueError, match='有效范围'):
        estimate_military_thrust(bpr=-0.1, opr=26.0, t4_K=1922.0, tsl_N=1.0, alt_m=0.0, mach=0.0)
    with pytest.raises(ValueError, match='eta_c'):
        estimate_military_thrust(bpr=0.3, opr=26.0, t4_K=1922.0, tsl_N=1.0, alt_m=0.0, mach=0.0, eta_c=0.0)
    with pytest.raises(ValueError, match='风扇压比'):
        estimate_military_thrust(
            bpr=0.3, opr=26.0, t4_K=1922.0, tsl_N=1.0, alt_m=0.0, mach=0.0, fan_pr_override=1.0,
        )


def test_estimate_military_thrust_no_cycle_solution():
    with pytest.raises(ValueError, match='无解'):
        estimate_military_thrust(bpr=2.0, opr=40.0, t4_K=900.0, tsl_N=100000.0, alt_m=0.0, mach=0.0)


def test_estimate_military_thrust_negative_specific_thrust():
    with pytest.raises(ValueError, match='比推力'):
        estimate_military_thrust(
            bpr=0.30, opr=26.0, t4_K=1922.0, tsl_N=116000.0, alt_m=0.0, mach=3.0,
        )
