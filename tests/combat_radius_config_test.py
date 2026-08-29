"""作战半径配置加载单元测试。"""
from __future__ import annotations

import pytest

from utils.combat_radius.combat_radius_config import (
    build_combat_radius_config_payload,
    dry_to_max_thrust_ratio,
    inject_combat_radius_config,
    layout_labels,
    load_combat_radius_config,
    mission_fuel_config,
    planform_labels,
    ui_config,
)
from utils.paths import COMBAT_RADIUS_CONFIG_JSON


def test_load_combat_radius_config_file_exists_and_ui_defaults():
    assert COMBAT_RADIUS_CONFIG_JSON.is_file()
    ui = ui_config()
    assert ui['default_anchor1_id'] == 'F-35C'
    assert ui['default_target_id'] == 'J-20'
    assert ui['default_engine_id'] == 'f119'
    assert ui['default_eta_c'] == 0.87
    assert ui['default_eps'] == 0.83
    assert load_combat_radius_config()['version'] == 3


def test_planform_and_layout_labels():
    pf = planform_labels()
    assert pf['delta'] == '三角翼'
    assert pf['double_delta'] == '双三角翼'
    assert pf['lambda'] == '兰姆达翼'
    assert pf['diamond'] == '钻石翼'
    assert pf['unswept'] == '平直翼'
    ly = layout_labels()
    assert ly['canard'] == '鸭翼'
    assert ly['tailless'] == '无尾'


def test_build_combat_radius_config_payload():
    payload = build_combat_radius_config_payload()
    assert payload['ui']['default_ld1'] == 8.52
    assert payload['ui']['default_ld2'] == 8.62
    assert payload['ui']['default_thrust_alt_m'] == 11000
    assert payload['ui']['default_thrust_mach'] == 1.5
    assert payload['mission_fuel']['carrier_reserve_min'] == 40
    assert payload['mission_fuel']['land_reserve_min'] == 30
    assert payload['mission_fuel']['climb_extra_km'] == 120
    assert payload['mission_fuel']['descent_save_km'] == 87.5
    assert payload['mission_fuel']['reserve_cruise_kph'] == 850
    assert payload['engine']['dry_to_max_thrust_ratio'] == 0.7
    assert 'trapezoidal' in payload['planform_labels']
    assert 'conventional' in payload['layout_labels']


def test_load_combat_radius_config_custom_path(tmp_path):
    """显式路径加载配置，不走默认文件。"""
    from utils.combat_radius import combat_radius_config as mod

    p = tmp_path / 'cfg.json'
    p.write_text(
        '{"version": 7, "ui": {"default_ld1": 3.0}, "planform_labels": {}, "layout_labels": {}}',
        encoding='utf-8',
    )
    injected = mod._INJECTED
    try:
        mod._INJECTED = None
        load_combat_radius_config.cache_clear()
        cfg = load_combat_radius_config(p)
        assert cfg['version'] == 7
        assert cfg['ui']['default_ld1'] == 3.0
    finally:
        mod._INJECTED = injected
        load_combat_radius_config.cache_clear()


def test_inject_combat_radius_config_overrides_disk():
    from utils.combat_radius import combat_radius_config as mod

    try:
        inject_combat_radius_config(
            {'version': 99, 'ui': {'default_ld1': 1.0}, 'planform_labels': {}, 'layout_labels': {}}
        )
        assert load_combat_radius_config()['version'] == 99
        assert ui_config()['default_ld1'] == 1.0
    finally:
        mod._INJECTED = None
        load_combat_radius_config.cache_clear()
    assert load_combat_radius_config()['version'] == 3


def test_mission_fuel_config_defaults():
    """舰载 40 min / 陆基 30 min，爬升 120 km，降落 87.5 km。"""
    mf = mission_fuel_config()
    assert mf['reserve_cruise_kph'] == 850
    assert mf['carrier_reserve_min'] == 40
    assert mf['land_reserve_min'] == 30
    assert mf['climb_extra_km'] == 120
    assert mf['descent_save_km'] == 87.5


def test_dry_to_max_thrust_ratio_default_and_invalid_inject():
    """缺 engine 段或比例非法时回退 0.7。"""
    from utils.combat_radius import combat_radius_config as mod

    assert dry_to_max_thrust_ratio() == pytest.approx(0.7)
    try:
        inject_combat_radius_config(
            {'version': 1, 'ui': {}, 'planform_labels': {}, 'layout_labels': {}, 'engine': {'dry_to_max_thrust_ratio': 2.5}}
        )
        assert dry_to_max_thrust_ratio() == pytest.approx(0.7)
        inject_combat_radius_config({'version': 1, 'ui': {}, 'planform_labels': {}, 'layout_labels': {}})
        assert dry_to_max_thrust_ratio() == pytest.approx(0.7)
    finally:
        mod._INJECTED = None
        load_combat_radius_config.cache_clear()
