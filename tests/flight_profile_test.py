"""作战半径任务剖面单元测试。"""
from __future__ import annotations

import pytest

from utils.combat_radius.combat_radius_config import inject_combat_radius_config
from utils.combat_radius.flight_profile import (
    DEFAULT_PROFILE_ID,
    HI_LO_HI_LOW_MACH,
    default_flight_profile_id,
    flight_profile_options,
    profile_combat_radius_m,
    profile_mission_fuel_km,
    resolve_flight_profile,
)


def test_resolve_flight_profile_defaults_to_hi_hi_hi():
    """缺省与非法 id 均回退高-高-高。"""
    prof = resolve_flight_profile(None)
    assert prof['id'] == DEFAULT_PROFILE_ID
    assert prof['label'] == '高-高-高'
    assert resolve_flight_profile('bad_id')['id'] == DEFAULT_PROFILE_ID


def test_profile_mission_fuel_km_differs_by_profile():
    """三种剖面的爬升/降落等价距离不同。"""
    hi = profile_mission_fuel_km('hi_hi_hi')
    mix = profile_mission_fuel_km('hi_lo_hi')
    lo = profile_mission_fuel_km('lo_lo_lo')
    assert hi == (120.0, 87.5)
    assert mix == (180.0, 50.0)
    assert lo == (30.0, 25.0)
    assert mix[0] > hi[0]
    assert lo[0] < hi[0]


def test_flight_profile_options_order_and_labels():
    """前端选项顺序固定且含中文标签。"""
    opts = flight_profile_options()
    assert [o['id'] for o in opts] == ['hi_hi_hi', 'hi_lo_hi', 'lo_lo_lo']
    assert opts[1]['label'] == '高-低-高'


def test_config_payload_includes_flight_profiles():
    """build 载荷含剖面 default 与 options。"""
    from utils.combat_radius import combat_radius_config as mod
    from utils.combat_radius.combat_radius_config import build_combat_radius_config_payload

    try:
        inject_combat_radius_config({
            'version': 9,
            'ui': {},
            'mission_fuel': {'carrier_reserve_min': 45, 'land_reserve_min': 30},
            'flight_profiles': {'default': 'hi_lo_hi', 'profiles': {}},
        })
        payload = build_combat_radius_config_payload()
        assert payload['flight_profiles']['default'] == 'hi_lo_hi'
        assert len(payload['flight_profiles']['options']) == 3
    finally:
        mod._INJECTED = None
        mod.load_combat_radius_config.cache_clear()


class _Scored:
    """最小评分点桩。"""

    def __init__(self, v0: float, tsfc: float, ld: float, mach: float = 0.8):
        self.v0 = v0
        self.tsfc_kg_n_s = tsfc
        self.ld = ld
        self.mach = mach
        self.eta_o = 0.2


def test_profile_combat_radius_symmetric_high():
    """高-高-高与对称布雷盖一致。"""
    from utils.combat_radius.breguet import combat_radius_m

    high = _Scored(240.0, 2.5e-5, 8.0)
    prof = resolve_flight_profile('hi_hi_hi')
    wi, wf = 28000.0, 20000.0
    expected = combat_radius_m(240.0, 2.5e-5, 8.0, wi, wf)
    radius = profile_combat_radius_m(
        prof, high, mach=0.8, mass_initial_kg=wi, mass_final_kg=wf,
    )
    assert radius == pytest.approx(expected)


def test_profile_combat_radius_mixed_high_low_between_legs():
    """高-低-高混合半径应介于两段对称半径之间。"""
    high = _Scored(500.0, 5.0e-5, 5.0, mach=1.5)
    low = _Scored(220.0, 2.5e-5, 6.0, mach=HI_LO_HI_LOW_MACH)
    prof = resolve_flight_profile('hi_lo_hi')
    wi, wf = 28000.0, 20000.0

    class _Ctx:
        pass

    mixed = profile_combat_radius_m(
        prof, high, ctx=_Ctx(), mach=1.5,
        mass_initial_kg=wi, mass_final_kg=wf, low_scored=low,
    )
    from utils.combat_radius.breguet import combat_radius_m, mixed_combat_radius_m

    r_hi = combat_radius_m(500.0, 5.0e-5, 5.0, wi, wf)
    r_lo = combat_radius_m(220.0, 2.5e-5, 6.0, wi, wf)
    expected = mixed_combat_radius_m(
        500.0, 5.0e-5, 5.0, 220.0, 2.5e-5, 6.0, wi, wf,
    )
    assert mixed == pytest.approx(expected)
    lo_bound, hi_bound = sorted((r_hi, r_lo))
    assert lo_bound < mixed < hi_bound


def test_default_flight_profile_id_from_config():
    """JSON default 可覆盖缺省剖面。"""
    from utils.combat_radius import combat_radius_config as mod

    try:
        inject_combat_radius_config({
            'version': 9,
            'ui': {},
            'mission_fuel': {},
            'flight_profiles': {'default': 'lo_lo_lo', 'profiles': {}},
        })
        assert default_flight_profile_id() == 'lo_lo_lo'
    finally:
        mod._INJECTED = None
        mod.load_combat_radius_config.cache_clear()
