"""F/A-18C/E 挂点挂载模型单元测试。"""
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


def test_fa18c_has_nine_stations_left_to_right():
    """F/A-18C 共 9 个挂点，编号 1–9。"""
    ac = get_aircraft_station_def('FA-18C')
    assert ac is not None
    ids = [st['id'] for st in ac['stations']]
    assert ids == [
        'sta1', 'sta2', 'sta3', 'sta4', 'sta5', 'sta6', 'sta7', 'sta8', 'sta9',
    ]
    assert ac['stations'][0]['mount_style'] == 'wing_tip'
    assert ac['stations'][-1]['mount_style'] == 'wing_tip'


def test_fa18e_has_eleven_stations():
    """F/A-18E 共 11 个挂点，编号 1–11。"""
    ac = get_aircraft_station_def('FA-18E')
    assert ac is not None
    assert len(ac['stations']) == 11
    assert ac['stations'][0]['label'].startswith('1 ')
    assert ac['stations'][-1]['id'] == 'sta11'


def test_fa18c_wingtip_only_aim9():
    """C 型翼尖仅 AIM-9。"""
    ac = get_aircraft_station_def('FA-18C')
    mun = load_munitions()
    for sid in ('sta1', 'sta9'):
        st = next(s for s in ac['stations'] if s['id'] == sid)
        opts = expand_station_options(st, mun)
        keys = {o['key'] for o in opts if o['key']}
        assert keys == {'aim9@1'}


def test_fa18c_inner_no_slam_er():
    """C 型内侧挂点无 SLAM-ER，但有 330 加仑副油箱。"""
    ac = get_aircraft_station_def('FA-18C')
    mun = load_munitions()
    st = next(s for s in ac['stations'] if s['id'] == 'sta3')
    keys = {o['key'] for o in expand_station_options(st, mun) if o['key']}
    assert 'slam_er@1' not in keys
    assert 'drop_tank_330@1' in keys
    assert 'agm84@1' in keys


def test_fa18c_outer_has_slam_er():
    """C 型外侧挂点含 SLAM-ER/GBU-24。"""
    ac = get_aircraft_station_def('FA-18C')
    mun = load_munitions()
    st = next(s for s in ac['stations'] if s['id'] == 'sta2')
    keys = {o['key'] for o in expand_station_options(st, mun) if o['key']}
    assert 'slam_er@1' in keys
    assert 'gbu24@1' in keys


def test_fa18e_outer_subset_no_harpoon():
    """E 型外侧挂点（sta2/sta10）无鱼叉与 JSOW/JDAM。"""
    ac = get_aircraft_station_def('FA-18E')
    mun = load_munitions()
    st = next(s for s in ac['stations'] if s['id'] == 'sta2')
    keys = {o['key'] for o in expand_station_options(st, mun) if o['key']}
    assert 'agm84@1' not in keys
    assert 'agm154@1' not in keys
    assert 'agm65@1' in keys
    assert 'agm88@1' in keys


def test_fa18e_inner_has_480_gal_tank():
    """E 型中内/中外挂点可挂 480 加仑副油箱。"""
    ac = get_aircraft_station_def('FA-18E')
    mun = load_munitions()
    for sid in ('sta3', 'sta4', 'sta8'):
        st = next(s for s in ac['stations'] if s['id'] == sid)
        keys = {o['key'] for o in expand_station_options(st, mun) if o['key']}
        assert 'drop_tank_480@1' in keys, sid


def test_fa18e_sta9_no_fuel_tank():
    """E 型 sta9 右中外挂点无副油箱。"""
    ac = get_aircraft_station_def('FA-18E')
    mun = load_munitions()
    st = next(s for s in ac['stations'] if s['id'] == 'sta9')
    keys = {o['key'] for o in expand_station_options(st, mun) if o['key']}
    assert 'drop_tank_480@1' not in keys
    assert 'slam_er@1' in keys


def test_fa18e_intake_sta5_bombs():
    """E 型左进气道侧可挂炸弹（相对 C 型扩展）。"""
    ac = get_aircraft_station_def('FA-18E')
    mun = load_munitions()
    st = next(s for s in ac['stations'] if s['id'] == 'sta5')
    keys = {o['key'] for o in expand_station_options(st, mun) if o['key']}
    assert 'mk82@1' in keys
    assert 'gbu16@1' in keys


def test_resolve_fa18c_default_cap():
    """C 型默认空优：2×AIM-9 + 2×AIM-120。"""
    ac = get_aircraft_station_def('FA-18C')
    sel = {
        sid: f"{v['munition_id']}@{int(v['qty'])}"
        for sid, v in (ac.get('default_selection') or {}).items()
    }
    summary = resolve_loadout('FA-18C', sel)
    assert summary.weapons_mass_kg == pytest.approx(86 * 2 + 152 * 2)
    assert summary.external_fuel_kg == pytest.approx(0)
    assert summary.n_store_units == pytest.approx(4)


def test_resolve_fa18e_tanker_loadout():
    """E 型三油箱转场：外油按 480 加仑×3 计。"""
    summary = resolve_loadout('FA-18E', {
        'sta3': 'drop_tank_480@1',
        'sta6': 'drop_tank_480@1',
        'sta8': 'drop_tank_480@1',
    })
    assert summary.external_fuel_kg == pytest.approx(1456 * 3)
    assert summary.tank_dry_mass_kg == pytest.approx(150 * 3)
