"""E2E regression: full simulator snapshots match baseline_before.json."""
import pytest

import simulators.takeoff.ski_jump_take_off as ski_conv
from utils.sim_snapshots import (
    assert_matches_baseline,
    collect_snapshots,
    diff_snapshots,
    load_baseline,
    normalize,
    reset_takeoff_module_defaults,
)


def test_reset_takeoff_module_defaults_restores_ski_conv_reference():
    """先前仿真改过 CD0/温度后，快照须能恢复为配置里的参考机。"""
    ski_conv.apply_thrust_temperature(15.0)
    ski_conv.apply_aircraft_geometry(20000.0, 50.0, 12.0, 2.0, 30.0, 0.015, 100000.0)
    reset_takeoff_module_defaults(ski_conv)
    ref = ski_conv._REF
    assert ski_conv.CD0 == pytest.approx(float(ref['cd0']))
    assert ski_conv.T_MAX_SL_N == pytest.approx(float(ref['t_max_sl_n']))
    assert ski_conv.AMBIENT_TEMP_C == pytest.approx(float(ski_conv._MODE['ambient_temp_c']))
    assert ski_conv.MASS_KG == pytest.approx(float(ref['mass_kg']))


def test_reset_takeoff_module_defaults_restores_stovl_exhaust_plume():
    """STOVL 仿真改过尾流参数后，快照须回到默认 F-35B 尾流。"""
    import simulators.takeoff.short_take_off as flat
    from utils.takeoff.exhaust_plume import ExhaustPlumeParams, default_exhaust_plume_params

    flat.apply_exhaust_plume_params(ExhaustPlumeParams(mdot_kg_s=50.0, u0_mps=400.0))
    reset_takeoff_module_defaults(flat)
    expected = default_exhaust_plume_params()
    assert flat.PLUME_PARAMS.mdot_kg_s == pytest.approx(expected.mdot_kg_s)
    assert flat.PLUME_PARAMS.u0_mps == pytest.approx(expected.u0_mps)
    assert flat.CD0 == pytest.approx(float(flat._REF['cd0']))


def test_normalize_and_diff_snapshots():
    """浮点四舍五入与字典排序后才能比较快照。"""
    assert normalize(1.2345678901) == round(1.2345678901, 9)
    assert normalize({'b': 2, 'a': 1}) == {'a': 1, 'b': 2}
    assert diff_snapshots({'x': {'n': 1.0}}, {'x': {'n': 1.0}}) == []
    assert diff_snapshots({'x': {'n': 1.0}, 'y': 1}, {'x': {'n': 2.0}, 'y': 1}) == ['x']


@pytest.mark.e2e
def test_refactor_snapshots_match_baseline():
    """Equivalent to running verify_refactor.py."""
    assert_matches_baseline()


@pytest.mark.e2e
def test_collect_snapshots_has_all_modules():
    snap = collect_snapshots()
    assert set(snap.keys()) == {'flat', 'ski_stovl', 'ski_conv'}
    before = load_baseline()
    assert diff_snapshots(before, snap) == []
