"""布雷盖航程与平均油耗单元测试。"""
from __future__ import annotations

import math

import pytest

from utils.combat_radius.breguet import (
    G0,
    average_fuel_kg_per_km,
    breguet_range_m,
    combat_radius_m,
)


def test_breguet_range_m_known_identity():
    """R = V/(g·c)·(L/D)·ln(Wi/Wf)。"""
    v, tsfc, ld, wi, wf = 240.0, 2.5e-5, 8.0, 28000.0, 20000.0
    expected = (v / (G0 * tsfc)) * ld * math.log(wi / wf)
    assert breguet_range_m(v, tsfc, ld, wi, wf) == pytest.approx(expected)


def test_combat_radius_m_is_half_range():
    r = breguet_range_m(240.0, 2.5e-5, 8.0, 28000.0, 20000.0)
    assert combat_radius_m(240.0, 2.5e-5, 8.0, 28000.0, 20000.0) == pytest.approx(r / 2.0)


def test_breguet_range_m_rejects_bad_inputs():
    with pytest.raises(ValueError, match='巡航速度'):
        breguet_range_m(0, 1e-5, 8, 2, 1)
    with pytest.raises(ValueError, match='TSFC'):
        breguet_range_m(100, 0, 8, 2, 1)
    with pytest.raises(ValueError, match='升阻比'):
        breguet_range_m(100, 1e-5, 0, 2, 1)
    with pytest.raises(ValueError, match='终了质量'):
        breguet_range_m(100, 1e-5, 8, 2, 0)
    with pytest.raises(ValueError, match='起飞质量'):
        breguet_range_m(100, 1e-5, 8, 1, 1)
    with pytest.raises(ValueError, match='重力'):
        breguet_range_m(100, 1e-5, 8, 2, 1, g0=0)


def test_average_fuel_kg_per_km():
    # 8000 kg 燃油、半径 1000 km → 往返 2000 km → 4 kg/km
    assert average_fuel_kg_per_km(8000.0, 1_000_000.0) == pytest.approx(4.0)
    with pytest.raises(ValueError, match='燃油'):
        average_fuel_kg_per_km(-1, 1000)
    with pytest.raises(ValueError, match='作战半径'):
        average_fuel_kg_per_km(100, 0)
