"""空战重量、平飞阻力与负载比单元测试。"""
from __future__ import annotations

import pytest

from utils.combat_radius.cruise_load import (
    G0,
    PILOT_MASS_KG,
    clamp_load,
    combat_mass_breakdown,
    combat_mass_kg,
    cruise_drag_n,
    engine_load_ratio,
)


def test_combat_mass_kg_half_fuel_pilots_and_missiles():
    mass = combat_mass_kg(
        empty_kg=19700, internal_fuel_kg=8200, n_pilots=1, missile_mass_kg=152, n_missiles=4,
    )
    assert mass == pytest.approx(19700 + 0.5 * 8200 + 100 + 4 * 152)
    assert PILOT_MASS_KG == 100.0


def test_combat_mass_kg_zero_pilots_uav():
    """无人机飞行员数为 0 时不计入乘员质量。"""
    mass = combat_mass_kg(
        empty_kg=7300, internal_fuel_kg=4740, n_pilots=0, missile_mass_kg=210, n_missiles=4,
    )
    assert mass == pytest.approx(7300 + 0.5 * 4740 + 4 * 210)


def test_combat_mass_kg_rejects_bad_inputs():
    with pytest.raises(ValueError, match='不能为负'):
        combat_mass_kg(empty_kg=-1, internal_fuel_kg=1)
    with pytest.raises(ValueError, match='飞行员'):
        combat_mass_kg(empty_kg=1, internal_fuel_kg=1, n_pilots=-1)
    with pytest.raises(ValueError, match='内油使用比例'):
        combat_mass_kg(empty_kg=1, internal_fuel_kg=1, fuel_fraction=1.5)
    with pytest.raises(ValueError, match='飞行员质量'):
        combat_mass_kg(empty_kg=1, internal_fuel_kg=1, pilot_mass_kg=-1)


def test_combat_mass_breakdown_sums_to_total():
    d = combat_mass_breakdown(empty_kg=10000, internal_fuel_kg=4000, n_pilots=2, missile_mass_kg=150, n_missiles=4)
    assert d['total_kg'] == pytest.approx(d['empty_kg'] + d['fuel_kg'] + d['pilots_kg'] + d['missiles_kg'])
    assert d['fuel_kg'] == pytest.approx(2000)
    assert d['pilots_kg'] == pytest.approx(200)


def test_cruise_drag_n_is_weight_over_ld():
    drag = cruise_drag_n(10000.0, 8.0)
    assert drag == pytest.approx(10000.0 * G0 / 8.0)
    with pytest.raises(ValueError, match='质量'):
        cruise_drag_n(0.0, 8.0)
    with pytest.raises(ValueError, match='升阻比'):
        cruise_drag_n(1000.0, 0.0)


def test_engine_load_ratio_and_clamp():
    assert engine_load_ratio(50.0, 100.0) == pytest.approx(0.5)
    assert engine_load_ratio(150.0, 100.0) == pytest.approx(1.5)
    with pytest.raises(ValueError, match='阻力'):
        engine_load_ratio(-1.0, 10.0)
    with pytest.raises(ValueError, match='推力'):
        engine_load_ratio(1.0, 0.0)
    assert clamp_load(-0.2) == 0.0
    assert clamp_load(0.4) == pytest.approx(0.4)
    assert clamp_load(1.7) == 1.0
