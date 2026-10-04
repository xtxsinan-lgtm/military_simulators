"""F-2 挂点挂载模型单元测试。"""
from __future__ import annotations

import pytest

from utils.combat_radius.loadout import (
    clear_loadout_caches,
    expand_station_options,
    get_aircraft_station_def,
    load_munitions,
    resolve_loadout,
)


@pytest.fixture(autouse=True)
def _clear_caches():
    """每个用例前清空挂载缓存。"""
    clear_loadout_caches()
    yield
    clear_loadout_caches()


def test_f2_has_eleven_stations():
    """F-2 共 11 个挂点，编号 1–11。"""
    ac = get_aircraft_station_def('F-2')
    assert ac is not None
    ids = [st['id'] for st in ac['stations']]
    assert ids == [
        'sta1', 'sta2', 'sta3', 'sta4', 'sta5', 'sta6',
        'sta7', 'sta8', 'sta9', 'sta10', 'sta11',
    ]
    assert ac['stations'][0]['mount_style'] == 'wing_tip'
    assert ac['stations'][-1]['mount_style'] == 'wing_tip'


def test_f2_wingtip_aam3_or_aim9():
    """翼尖挂点（STA-1/11）仅 AAM-3 或 AIM-9L。"""
    ac = get_aircraft_station_def('F-2')
    mun = load_munitions()
    for sid in ('sta1', 'sta11'):
        st = next(s for s in ac['stations'] if s['id'] == sid)
        keys = {o['key'] for o in expand_station_options(st, mun) if o['key']}
        assert keys == {'aam3@1', 'aim9@1'}


def test_f2_outer_has_bvr_and_wvr():
    """外侧挂点（STA-2/10）含 AAM-3、AIM-9L、AIM-7M、AAM-4。"""
    ac = get_aircraft_station_def('F-2')
    mun = load_munitions()
    st = next(s for s in ac['stations'] if s['id'] == 'sta2')
    keys = {o['key'] for o in expand_station_options(st, mun) if o['key']}
    assert keys == {'aam3@1', 'aim9@1', 'aim7@1', 'aam4@1'}


def test_f2_mid_has_asm():
    """主挂点（STA-3/9，in/out）除空空弹外可挂 ASM-1/2。"""
    ac = get_aircraft_station_def('F-2')
    mun = load_munitions()
    st = next(s for s in ac['stations'] if s['id'] == 'sta3')
    keys = {o['key'] for o in expand_station_options(st, mun) if o['key']}
    assert 'asm1@1' in keys
    assert 'asm2@1' in keys
    assert 'aam4@1' in keys


def test_f2_inner_has_600_gal_tank():
    """内侧挂点（STA-4/8）可挂 600 加仑副油箱与反舰弹。"""
    ac = get_aircraft_station_def('F-2')
    mun = load_munitions()
    st = next(s for s in ac['stations'] if s['id'] == 'sta4')
    keys = {o['key'] for o in expand_station_options(st, mun) if o['key']}
    assert 'drop_tank_600@1' in keys
    assert 'asm2@1' in keys
    assert 'mk82_ter3@1' in keys


def test_f2_centerline_300_gal_tank():
    """中线挂点（STA-6）可挂 300 加仑副油箱。"""
    ac = get_aircraft_station_def('F-2')
    mun = load_munitions()
    st = next(s for s in ac['stations'] if s['id'] == 'sta6')
    keys = {o['key'] for o in expand_station_options(st, mun) if o['key']}
    assert 'drop_tank_300@1' in keys
    assert 'gbu31@1' in keys


def test_resolve_f2_default_cap():
    """默认空优：2×AAM-3 + 2×AAM-4。"""
    ac = get_aircraft_station_def('F-2')
    sel = {
        sid: f"{v['munition_id']}@{int(v['qty'])}"
        for sid, v in (ac.get('default_selection') or {}).items()
    }
    summary = resolve_loadout('F-2', sel)
    assert summary.weapons_mass_kg == pytest.approx(91 * 2 + 163 * 2)
    assert summary.external_fuel_kg == pytest.approx(0)
    assert summary.n_store_units == pytest.approx(4)


def test_resolve_f2_ferry_three_tanks():
    """转场三油箱：300 gal 中线 + 2×600 gal 内侧。"""
    summary = resolve_loadout('F-2', {
        'sta6': 'drop_tank_300@1',
        'sta4': 'drop_tank_600@1',
        'sta8': 'drop_tank_600@1',
    })
    assert summary.external_fuel_kg == pytest.approx(1015 + 1810 * 2)
    assert summary.tank_dry_mass_kg == pytest.approx(120 + 150 * 2)


def test_resolve_f2_asm_strike():
    """反舰：4×ASM-2 于主/内侧挂点。"""
    summary = resolve_loadout('F-2', {
        'sta3': 'asm2@1',
        'sta4': 'asm2@1',
        'sta8': 'asm2@1',
        'sta9': 'asm2@1',
        'sta1': 'aam3@1',
        'sta11': 'aam3@1',
    })
    assert summary.weapons_mass_kg == pytest.approx(754 * 4 + 91 * 2)
    assert summary.n_store_units == pytest.approx(6)
