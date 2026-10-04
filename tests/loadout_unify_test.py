"""碎片挂载目录合并进统一 loadout_catalog 的单元测试。"""
from __future__ import annotations

import pytest

from utils.combat_radius.loadout import (
    build_loadout_catalog_payload,
    clear_loadout_caches,
    inject_loadout_catalog_payload,
    load_munitions,
    resolve_loadout,
)
from utils.combat_radius.loadout_unify import (
    mount_style_from_hints,
    normalize_munition_record,
)


@pytest.fixture(autouse=True)
def _clear_caches():
    """每个用例清空挂载缓存。"""
    clear_loadout_caches()
    yield
    clear_loadout_caches()


def test_normalize_munition_splits_fuel_from_notes():
    """副油箱 notes 含燃油质量时拆出 dry/fuel。"""
    row = normalize_munition_record(
        'tank_1900l',
        name='1900L',
        category='tank',
        mass_kg=1520,
        length_m=5.4,
        diameter_m=0.6,
        notes='含燃油约 1450 kg',
    )
    assert row is not None
    assert row['fuel_kg'] == pytest.approx(1450)
    assert row['dry_mass_kg'] == pytest.approx(70)


def test_normalize_munition_skips_gun():
    """航炮不计外挂。"""
    assert normalize_munition_record(
        'bk27', name='航炮', category='gun', mass_kg=87,
    ) is None


def test_mount_style_from_hints():
    """挂点位置映射到 mount_style。"""
    assert mount_style_from_hints(position='wingtip') == 'wing_tip'
    assert mount_style_from_hints(mount='semi_recessed') == 'semi_recessed'
    assert mount_style_from_hints(station_id='FUS_CENT', position='center') == 'centerline'


def test_build_loadout_catalog_includes_fragment_aircraft():
    """合并后 catalog 含碎片机型与原有 F-15E 等。"""
    cat = build_loadout_catalog_payload()
    ids = set(cat['aircraft'])
    assert {'F-15E', 'FA-18C', 'F-2', 'FA-18E'} <= ids
    assert {
        'F-14', 'F-16', 'FA-50', 'FC-1', 'Gripen-CD', 'Gripen-EF',
        'MiG-29K', 'Rafale', 'Rafale-M', 'Tejas', 'Typhoon',
    } <= ids
    for aid in ids:
        ac = cat['aircraft'][aid]
        assert ac['stations'], aid
        for st in ac['stations']:
            assert st['options'][0]['key'] == ''
            assert any(o.get('munition_id') for o in st['options']), f'{aid}/{st["id"]}'


def test_resolve_fragment_defaults():
    """碎片机型默认挂载可解析出正质量。"""
    cat = build_loadout_catalog_payload()
    for aid in ('Typhoon', 'Rafale', 'F-16', 'MiG-29K', 'FA-50'):
        summary = resolve_loadout(aid, cat['aircraft'][aid]['default_selection'])
        assert summary.payload_mass_kg > 0
        assert summary.n_store_units > 0


def test_inject_loadout_catalog_payload_roundtrip():
    """前端 catalog 注入后可 resolve。"""
    cat = build_loadout_catalog_payload()
    clear_loadout_caches()
    inject_loadout_catalog_payload(cat)
    # 注入后不再读盘合并；直接 resolve
    summary = resolve_loadout('Typhoon', cat['aircraft']['Typhoon']['default_selection'])
    assert summary.weapons_mass_kg == pytest.approx(476.0)
    assert 'aim9' in load_munitions()
