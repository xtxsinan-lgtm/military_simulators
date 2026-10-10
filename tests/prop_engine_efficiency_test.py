"""涡桨作战半径效率模型单元测试。"""
from __future__ import annotations

import pytest

from utils.combat_radius.prop_engine_efficiency import (
    available_shaft_power_w,
    compute_prop_engine_efficiency,
    static_prop_thrust_sl_n,
    thermal_efficiency_for_load,
)
from utils.combat_radius.propulsion import is_turboprop_params, cruise_envelope_defaults
from utils.combat_radius.combat_radius_presets import get_preset_by_id, load_engine_presets, load_presets


def test_available_shaft_power_constant_below_critical_alt():
    p_sl = 7_606_140.0
    assert available_shaft_power_w(p_sl, 5000.0) == pytest.approx(p_sl)
    assert available_shaft_power_w(p_sl, 9000.0) < p_sl


def test_thermal_efficiency_increases_with_load():
    low = thermal_efficiency_for_load(0.2)
    high = thermal_efficiency_for_load(0.9)
    assert high > low


def test_static_prop_thrust_positive():
    thrust = static_prop_thrust_sl_n(7_606_140.0, 4.11, n_rotors=2)
    assert thrust > 50_000


def test_compute_prop_engine_efficiency_cruise_point():
    drag = 40_000.0
    result = compute_prop_engine_efficiency(
        drag_n=drag,
        mach=0.4,
        altitude_m=5000.0,
        shaft_power_sl_w=7_606_140.0,
        prop_diameter_m=4.11,
        n_rotors=2,
    )
    assert result.valid is True
    assert result.eta_o > 0.15
    assert result.eta_p > 0.5
    assert result.load > 0


def test_awacs_presets_in_combat_radius_catalog():
    presets = load_presets()
    engines = load_engine_presets()
    e2 = get_preset_by_id(presets, 'E-2')
    kj = get_preset_by_id(presets, 'KJ-600')
    assert e2 is not None
    assert kj is not None
    assert e2['aircraft_role'] == 'awacs'
    assert kj['aircraft_role'] == 'awacs'
    assert e2['engine_id'] == 't56-a425'
    assert kj['engine_id'] == 'aep500'
    t56 = next(e for e in engines if e['id'] == 't56-a425')
    assert t56['propulsion'] == 'turboprop'


def test_turboprop_envelope_defaults():
    params = {'propulsion': 'turboprop', 'shaft_power_sl_w': 1e7, 'prop_diameter_m': 4.0}
    assert is_turboprop_params(params) is True
    env = cruise_envelope_defaults(params)
    assert env['alt_max_m'] <= 12000
    assert max(env['fixed_machs']) <= 0.6
