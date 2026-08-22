"""倾转旋翼机翼–旋翼干涉单元测试。"""
from __future__ import annotations

import pytest

from utils.takeoff.takeoff_physics import G
from utils.takeoff.tiltrotor_aero import (
    calc_hover_download_schedule,
    calc_slipstream_dynamic_pressure,
    calc_slipstream_wing_speed_mps,
    calc_tiltrotor_download_n,
    calc_tiltrotor_vertical_force_n,
    calc_tiltrotor_wing_lift_n,
)


def test_calc_hover_download_schedule_endpoints():
    assert calc_hover_download_schedule(60.0) == 0.0
    assert calc_hover_download_schedule(45.0) == 0.0
    assert calc_hover_download_schedule(90.0) == 1.0
    assert calc_hover_download_schedule(100.0) == 1.0


def test_calc_hover_download_schedule_mid():
    mid = calc_hover_download_schedule(75.0)
    assert 0.4 < mid < 0.6


def test_calc_hover_download_schedule_inverted_range():
    assert calc_hover_download_schedule(90.0, zero_deg=90.0, full_deg=60.0) == 1.0
    assert calc_hover_download_schedule(45.0, zero_deg=90.0, full_deg=60.0) == 0.0


def test_calc_tiltrotor_download_n_hover_and_sto():
    t = 265000.0
    hover = calc_tiltrotor_download_n(t, 90.0, 0.117)
    sto = calc_tiltrotor_download_n(t, 60.0, 0.117)
    assert hover == pytest.approx(t * 0.117)
    assert sto == 0.0


def test_calc_slipstream_wing_speed_hover_equals_freestream():
    assert calc_slipstream_wing_speed_mps(8.0, 25.0, 90.0, 2.0) == pytest.approx(8.0)


def test_calc_slipstream_wing_speed_adds_axial_wash():
    v = calc_slipstream_wing_speed_mps(8.0, 20.0, 0.0, 2.0)
    assert v == pytest.approx(8.0 + 40.0)


def test_calc_slipstream_dynamic_pressure_wet_blend():
    rho = 1.225
    q = calc_slipstream_dynamic_pressure(rho, 10.0, 30.0, 0.5)
    expected = 0.5 * rho * (0.5 * 900.0 + 0.5 * 100.0)
    assert q == pytest.approx(expected)


def test_calc_tiltrotor_wing_lift_n_positive_in_sto():
    lift = calc_tiltrotor_wing_lift_n(
        1.225, 190.0, 250000.0, 8.0, 60.0, 1.4, 28.0,
    )
    assert lift > 1000.0


def test_calc_tiltrotor_vertical_force_n_hover_matches_download():
    t = 265300.0
    net = calc_tiltrotor_vertical_force_n(
        t, 1.225, 190.0, 0.0, 90.0, 1.4, 28.0, hover_download_frac=0.117,
    )
    assert net == pytest.approx(t * (1.0 - 0.117), rel=1e-3)
    assert net < 23859 * G + 800
    assert net > 23859 * G - 1500
