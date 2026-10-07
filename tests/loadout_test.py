"""挂载库与 F-15E 挂点解析单元测试。"""
from __future__ import annotations

import pytest

from utils.combat_radius.lift_drag import (
    Aircraft,
    StoreSpec,
    cd_store,
    iter_store_specs,
    store_spec_front_m2,
    store_spec_wetted_m2,
)
from utils.combat_radius.loadout import (
    apply_loadout_to_params,
    build_loadout_catalog_payload,
    clear_loadout_caches,
    default_loadout_selection,
    expand_station_options,
    get_aircraft_station_def,
    load_munitions,
    option_key,
    option_label,
    resolve_loadout,
    resolve_station_span_frac,
)


@pytest.fixture(autouse=True)
def _clear_caches():
    """每个用例前清空挂载缓存，避免注入残留。"""
    clear_loadout_caches()
    yield
    clear_loadout_caches()


def test_load_munitions_has_aim120_and_drop_tank():
    """弹药库含 AIM-120 与副油箱，质量/尺寸为正。"""
    mun = load_munitions()
    assert 'aim120' in mun
    assert mun['aim120']['mass_kg'] == pytest.approx(152)
    assert mun['aim120']['length_m'] > 0
    tank = mun['drop_tank_610']
    assert tank['fuel_kg'] == pytest.approx(1855)
    assert tank['dry_mass_kg'] == pytest.approx(120)


def test_get_aircraft_station_def_f15e():
    """F-15E 挂点表含翼下与 CFT 站。"""
    ac = get_aircraft_station_def('F-15E')
    assert ac is not None
    ids = {st['id'] for st in ac['stations']}
    assert {'sta2', 'sta5', 'sta8', 'lcft_inbd', 'ltp', 'lnp'} <= ids


def test_option_key_and_label():
    """选项键与显示名。"""
    assert option_key('aim120', 2) == 'aim120@2'
    assert option_label({'name': 'AIM-120'}, 1) == 'AIM-120'
    assert option_label({'name': 'AIM-120'}, 2) == 'AIM-120 ×2'
    assert option_label({'name': 'X'}, 3, '自定义') == '自定义'


def test_expand_station_options_includes_empty():
    """挂点选项首位为空挂。"""
    mun = load_munitions()
    st = {'id': 'sta2', 'options': [{'munition_id': 'mk82', 'qty': 1}]}
    rows = expand_station_options(st, mun)
    assert rows[0]['key'] == ''
    assert rows[1]['munition_id'] == 'mk82'


def test_resolve_loadout_default_four_aim120():
    """默认四枚 AIM-120：干重 608 kg，无外油。"""
    ac = get_aircraft_station_def('F-15E')
    sel = {
        sid: {'munition_id': v['munition_id'], 'qty': v['qty']}
        for sid, v in (ac.get('default_selection') or {}).items()
    }
    summary = resolve_loadout('F-15E', sel)
    assert summary.weapons_mass_kg == pytest.approx(608)
    assert summary.external_fuel_kg == pytest.approx(0)
    assert summary.n_store_units == pytest.approx(4)
    assert len(summary.store_specs) == 4


def test_resolve_loadout_drop_tanks_add_fuel():
    """翼下副油箱计入外油与油箱干重。"""
    summary = resolve_loadout('F-15E', {
        'sta2': 'drop_tank_610@1',
        'sta8': 'drop_tank_610@1',
    })
    assert summary.external_fuel_kg == pytest.approx(1855 * 2)
    assert summary.tank_dry_mass_kg == pytest.approx(120 * 2)
    assert summary.weapons_mass_kg == pytest.approx(0)


def test_resolve_loadout_rejects_illegal_option():
    """不允许的挂载抛错。"""
    with pytest.raises(ValueError, match='不允许'):
        resolve_loadout('F-15E', {'sta2': 'aim120@1'})


def test_apply_loadout_to_params_sets_store_specs_and_fuel():
    """请求参数注入挂载后覆盖质量、油量与 store_specs。"""
    params = {
        'empty_kg': 17690,
        'internal_fuel_kg': 10100,
        'n_pilots': 2,
        'missile_mass_kg': 152,
        'n_missiles': 4,
        'target': {'store_mount': 'pylon', 'wing_area_m2': 56.5},
        'loadout': {
            'aircraft_id': 'F-15E',
            'selection': {
                'sta2': 'drop_tank_610@1',
                'sta2a': 'aim120@1',
            },
        },
    }
    out = apply_loadout_to_params(params)
    assert out['internal_fuel_kg'] == pytest.approx(10100 + 1855)
    assert out['payload_mass_kg'] == pytest.approx(120 + 152)
    assert out['missile_mass_kg'] == pytest.approx(0)
    assert out['n_missiles'] == pytest.approx(0)
    assert len(out['target']['store_specs']) == 2
    assert 'store_mount' not in out['target']
    assert out['loadout_summary']['external_fuel_kg'] == pytest.approx(1855)


def test_build_loadout_catalog_payload():
    """目录含弹药与 F-15E 展开选项。"""
    payload = build_loadout_catalog_payload()
    assert payload['version'] >= 1
    assert any(m['id'] == 'gbu39' for m in payload['munitions'])
    f15e = payload['aircraft']['F-15E']
    assert f15e['default_selection']['sta2a'] == 'aim120@1'
    sta2 = next(s for s in f15e['stations'] if s['id'] == 'sta2')
    assert any(o['key'] == 'agm65@3' for o in sta2['options'])


def test_store_spec_geometry_scales_with_size():
    """更大直径外挂迎风更大；多枚浸润按件数放大。"""
    small = StoreSpec(length_m=2.0, diameter_m=0.2, count=1, mount='pylon')
    big = StoreSpec(length_m=2.0, diameter_m=0.4, count=1, mount='pylon')
    assert store_spec_front_m2(big) > store_spec_front_m2(small)
    two = StoreSpec(length_m=2.0, diameter_m=0.2, count=2, mount='pylon')
    assert store_spec_wetted_m2(two) == pytest.approx(2 * store_spec_wetted_m2(small))


def test_cd_store_uses_explicit_store_specs():
    """有 store_specs 时按几何计阻，不再只用 n_stores×AIM-120。"""
    base = dict(
        name='t', AR=3.0, sweep_deg=40, wing_loading=0.4, tc=0.05,
        mach=0.8, alt_m=11000, planform='trapezoidal', layout='conventional',
        rough=False, wing_area_m2=56.5, store_mount='pylon', n_stores=0,
    )
    heavy = Aircraft(
        **base,
        store_specs=(StoreSpec(length_m=3.84, diameter_m=0.46, count=1, mount='pylon'),),
    )
    light = Aircraft(
        **base,
        store_specs=(StoreSpec(length_m=2.87, diameter_m=0.127, count=1, mount='pylon'),),
    )
    assert cd_store(heavy) > cd_store(light)
    legacy = Aircraft(**{**base, 'n_stores': 4})
    assert len(iter_store_specs(legacy)) == 1
    assert iter_store_specs(legacy)[0].count == pytest.approx(4)


def test_apply_loadout_noop_without_loadout():
    """无 loadout 字段时原样返回。"""
    params = {'n_missiles': 4, 'missile_mass_kg': 152}
    assert apply_loadout_to_params(params) is params or apply_loadout_to_params(params) == params


def test_default_loadout_selection_f15e():
    """F-15E 默认挂载为四站 AIM-120。"""
    sel = default_loadout_selection('F-15E')
    assert sel is not None
    assert len(sel) == 4
    assert all(v == 'aim120@1' for v in sel.values())


def test_resolve_station_span_frac_prefers_explicit_field():
    """显式 span_frac 优先于 label 推断。"""
    st = {'mount_style': 'wing_pylon', 'label': '外翼', 'span_frac': 0.35}
    assert resolve_station_span_frac(st) == pytest.approx(0.35)


def test_dashboard_params_use_default_loadout():
    """预计算参数对有挂点表的机型注入 default loadout。"""
    from utils.combat_radius.combat_radius_presets import get_preset_by_id, load_engine_presets, load_presets
    from utils.combat_radius.combat_radius_results import dashboard_params_from_preset

    ac = get_preset_by_id(load_presets(), 'F-15E')
    eng = get_preset_by_id(load_engine_presets(), ac['engine_id'])
    p = dashboard_params_from_preset(ac, eng)
    assert p.get('payload_mass_kg') == pytest.approx(608)
    assert len(p['target']['store_specs']) == 4


def test_f15e_wing_stations_harpoon_and_slam_er():
    """F-15E 翼下 2/8 号站可挂鱼叉与 SLAM-ER（F-15K/SA/QA 出口型能力），中线站不挂。"""
    summary = resolve_loadout('F-15E', {
        'sta2': 'agm84@1', 'sta8': 'slam_er@1', 'sta5': 'drop_tank_610@1',
    })
    assert summary.weapons_mass_kg == pytest.approx(520 + 725)
    assert summary.external_fuel_kg > 0
    with pytest.raises(ValueError):
        resolve_loadout('F-15E', {'sta5': 'agm84@1'})
