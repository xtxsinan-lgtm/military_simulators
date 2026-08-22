"""涡桨 / 倾转旋翼推力换算单元测试。"""
from __future__ import annotations

import math

import pytest

from utils.takeoff.propeller_thrust import (
    calc_effective_disk_area_m2,
    calc_ideal_static_thrust_n,
    calc_ideal_thrust_with_axial_speed_n,
    calc_prop_disk_area_m2,
    calc_propeller_thrust_n,
)


def test_calc_prop_disk_area_two_rotors():
    area = calc_prop_disk_area_m2(11.61, 2)
    assert area == pytest.approx(2 * math.pi * (11.61 / 2) ** 2)


def test_calc_effective_disk_area_applies_blockage():
    assert calc_effective_disk_area_m2(100.0, 0.1) == pytest.approx(90.0)


def test_calc_ideal_static_thrust_matches_closed_form():
    p, rho, a = 1e6, 1.225, 50.0
    t = calc_ideal_static_thrust_n(p, rho, a)
    assert t == pytest.approx((p * p * 2 * rho * a) ** (1 / 3))


def test_calc_ideal_thrust_with_zero_speed_equals_static():
    p, rho, a = 2e6, 1.225, 100.0
    assert calc_ideal_thrust_with_axial_speed_n(p, rho, a, 0.0) == pytest.approx(
        calc_ideal_static_thrust_n(p, rho, a)
    )


def test_calc_ideal_thrust_decreases_with_forward_speed():
    p, rho, a = 9.18e6, 1.225, 210.0
    t0 = calc_ideal_thrust_with_axial_speed_n(p, rho, a, 0.0)
    t40 = calc_ideal_thrust_with_axial_speed_n(p, rho, a, 40.0)
    assert t40 < t0


def test_calc_propeller_thrust_applies_fm_and_blockage():
    p, rho, a = 1e6, 1.225, 50.0
    ideal = calc_ideal_static_thrust_n(p, rho, a * 0.9)
    actual = calc_propeller_thrust_n(p, rho, a, 0.0, figure_of_merit=0.8, nacelle_blockage_frac=0.1)
    assert actual == pytest.approx(0.8 * ideal)


def test_calc_rotor_induced_velocity_hover_closed_form():
    from utils.takeoff.propeller_thrust import calc_rotor_induced_velocity_mps

    t, rho, a = 200000.0, 1.225, 190.0
    vi = calc_rotor_induced_velocity_mps(t, rho, a, 0.0)
    assert vi == pytest.approx(math.sqrt(t / (2 * rho * a)))


def test_calc_rotor_induced_velocity_edgewise_lower_than_axial():
    from utils.takeoff.propeller_thrust import calc_rotor_induced_velocity_mps

    t, rho, a = 250000.0, 1.225, 190.0
    vi_ax = calc_rotor_induced_velocity_mps(t, rho, a, 10.0, 0.0)
    vi_ed = calc_rotor_induced_velocity_mps(t, rho, a, 10.0, 20.0)
    assert vi_ed < vi_ax


def test_calc_ideal_thrust_with_inflow_matches_axial_when_no_edge():
    from utils.takeoff.propeller_thrust import calc_ideal_thrust_with_inflow_n

    p, rho, a = 9.18e6, 1.225, 190.0
    axial = calc_ideal_thrust_with_axial_speed_n(p, rho, a, 15.0)
    inflow = calc_ideal_thrust_with_inflow_n(p, rho, a, 15.0, 0.0)
    assert inflow == pytest.approx(axial, rel=1e-6)


def test_calc_ideal_thrust_with_inflow_increases_with_edgewise():
    from utils.takeoff.propeller_thrust import calc_ideal_thrust_with_inflow_n

    p, rho, a = 9.18e6, 1.225, 190.0
    t0 = calc_ideal_thrust_with_inflow_n(p, rho, a, 15.0, 0.0)
    t_ed = calc_ideal_thrust_with_inflow_n(p, rho, a, 15.0, 26.0)
    assert t_ed > t0


def test_calc_propeller_thrust_edgewise_increases():
    p, rho, a = 9.18e6, 1.225, 211.0
    t0 = calc_propeller_thrust_n(p, rho, a, 10.0, v_edgewise_mps=0.0)
    t_ed = calc_propeller_thrust_n(p, rho, a, 10.0, v_edgewise_mps=15.0)
    assert t_ed > t0
