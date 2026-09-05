"""作战半径配置加载单元测试。"""
from __future__ import annotations

import pytest

from utils.combat_radius.combat_radius_config import (
    F135_TSFC_TOGGLE_LPC_ONLY,
    F135_TSFC_TOGGLE_PUBLISHED,
    build_combat_radius_config_payload,
    dry_to_max_thrust_ratio,
    f135_tsfc_install_mult_for_mode,
    f135_tsfc_toggle_config,
    inject_combat_radius_config,
    inlet_labels,
    layout_labels,
    load_combat_radius_config,
    mission_fuel_config,
    planform_labels,
    resolve_ui_tsfc_install_mult,
    shows_f135_tsfc_toggle,
    store_mount_labels,
    reserve_kind_label,
    reserve_min_for_mission,
    ui_config,
    uses_land_fuel_reserve,
)
from utils.paths import COMBAT_RADIUS_CONFIG_JSON


def test_load_combat_radius_config_file_exists_and_ui_defaults():
    assert COMBAT_RADIUS_CONFIG_JSON.is_file()
    ui = ui_config()
    assert ui['default_target_id'] == 'J-20'
    assert ui['default_engine_id'] == 'f119'
    assert 'default_anchor1_id' not in ui
    assert ui['default_eta_c'] == 0.87
    assert ui['default_eps'] == 0.83
    assert load_combat_radius_config()['version'] == 7


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
    assert ly['pelican'] == 'Pelican尾'
    assert ly['small_htail'] == '小平尾'
    assert ly['medium_htail'] == '中等平尾'
    inn = inlet_labels()
    assert inn['dsi'] == 'DSI'
    assert inn['caret'] == '加莱特'
    sm = store_mount_labels()
    assert sm['internal'] == '内埋弹舱'
    assert sm['semi_recessed'] == '半埋'
    assert sm['pylon'] == '挂架'
    from utils.combat_radius.lift_drag import LAYOUT_MULT, PLANFORM_MULT, STORE_EXPOSED_FRAC
    assert set(pf) == set(PLANFORM_MULT)
    assert set(ly) == set(LAYOUT_MULT)
    assert set(sm) == set(STORE_EXPOSED_FRAC)


def test_build_combat_radius_config_payload():
    payload = build_combat_radius_config_payload()
    assert payload['ui']['default_target_id'] == 'J-20'
    assert 'default_ld1' not in payload['ui']
    assert payload['ui']['default_thrust_alt_m'] == 11000
    assert payload['ui']['default_thrust_mach'] == 1.5
    assert payload['mission_fuel']['carrier_reserve_min'] == 45
    assert payload['mission_fuel']['land_reserve_min'] == 30
    assert payload['mission_fuel']['climb_extra_km'] == 120
    assert payload['mission_fuel']['descent_save_km'] == 87.5
    assert payload['mission_fuel']['reserve_cruise_kph'] == 850
    assert payload['engine']['dry_to_max_thrust_ratio'] == 0.7
    assert 'trapezoidal' in payload['planform_labels']
    assert 'conventional' in payload['layout_labels']
    assert payload['inlet_labels']['caret'] == '加莱特'
    assert payload['store_mount_labels']['semi_recessed'] == '半埋'
    assert payload['f135_tsfc_toggle']['aircraft_ids'] == ['F-35A', 'F-35B', 'F-35C']
    assert payload['f135_tsfc_toggle']['published'] == pytest.approx(1.22)
    assert payload['f135_tsfc_toggle']['lpc_only'] == pytest.approx(1.04)


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
    assert load_combat_radius_config()['version'] == 7


def test_mission_fuel_config_defaults():
    """舰载 45 min / 陆基 30 min，爬升 120 km，降落 87.5 km。"""
    mf = mission_fuel_config()
    assert mf['reserve_cruise_kph'] == 850
    assert mf['carrier_reserve_min'] == 45
    assert mf['land_reserve_min'] == 30
    assert mf['climb_extra_km'] == 120
    assert mf['descent_save_km'] == 87.5


def test_reserve_min_for_mission_stovl_uses_land():
    """垂起/倾转即使舰载也按 30 min；弹射舰载 45 min。"""
    assert uses_land_fuel_reserve('v/stol') is True
    assert uses_land_fuel_reserve('tiltrotor') is True
    assert uses_land_fuel_reserve('conventional') is False
    assert uses_land_fuel_reserve(None) is False
    assert reserve_min_for_mission(True, 'conventional') == pytest.approx(45)
    assert reserve_min_for_mission(True, 'v/stol') == pytest.approx(30)
    assert reserve_min_for_mission(True, 'tiltrotor') == pytest.approx(30)
    assert reserve_min_for_mission(False, 'conventional') == pytest.approx(30)
    assert reserve_kind_label(True, 'v/stol') == '垂起'
    assert reserve_kind_label(True, 'conventional') == '舰载'
    assert reserve_kind_label(False, None) == '陆基'


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


def test_f135_tsfc_toggle_config_and_resolve():
    """F-35 三型显示切换；1.22 / 1.04 两档；其它机型用发动机乘数。"""
    from utils.combat_radius.engine_efficiency import F135_TSFC_INSTALL_MULT, F135_TSFC_LPC_ONLY_MULT

    cfg = f135_tsfc_toggle_config()
    assert cfg['published'] == pytest.approx(F135_TSFC_INSTALL_MULT)
    assert cfg['lpc_only'] == pytest.approx(F135_TSFC_LPC_ONLY_MULT)
    assert cfg['aircraft_ids'] == ['F-35A', 'F-35B', 'F-35C']
    assert cfg['published'] == pytest.approx(F135_TSFC_TOGGLE_PUBLISHED)
    assert cfg['lpc_only'] == pytest.approx(F135_TSFC_TOGGLE_LPC_ONLY)
    assert '公开军推' in cfg['published_label']
    assert '低压压气机' in cfg['lpc_only_label']
    assert '巡航不抽升力风扇' in cfg['note']
    assert shows_f135_tsfc_toggle('F-35A') is True
    assert shows_f135_tsfc_toggle('F-35B') is True
    assert shows_f135_tsfc_toggle('F-35C') is True
    assert shows_f135_tsfc_toggle('F-22') is False
    assert shows_f135_tsfc_toggle(None) is False
    assert f135_tsfc_install_mult_for_mode('published') == pytest.approx(1.22)
    assert f135_tsfc_install_mult_for_mode('lpc_only') == pytest.approx(1.04)
    assert f135_tsfc_install_mult_for_mode(None) == pytest.approx(1.22)
    assert resolve_ui_tsfc_install_mult('F-35A', 'lpc_only', 1.22) == pytest.approx(1.04)
    assert resolve_ui_tsfc_install_mult('F-35C', 'published') == pytest.approx(1.22)
    assert resolve_ui_tsfc_install_mult('F-22', 'lpc_only', 1.0) == pytest.approx(1.0)
    assert resolve_ui_tsfc_install_mult('J-20', None, None) == pytest.approx(1.0)
    with pytest.raises(ValueError, match='TSFC 乘数须为正'):
        resolve_ui_tsfc_install_mult('F-22', None, 0.0)


def test_f135_tsfc_toggle_falls_back_when_section_missing():
    """配置缺 f135_tsfc_toggle 段时仍给出默认三型与两档。"""
    from utils.combat_radius import combat_radius_config as mod

    try:
        inject_combat_radius_config({'version': 1, 'ui': {}, 'planform_labels': {}, 'layout_labels': {}})
        cfg = f135_tsfc_toggle_config()
        assert cfg['aircraft_ids'] == ['F-35A', 'F-35B', 'F-35C']
        assert cfg['published'] == pytest.approx(1.22)
        assert cfg['lpc_only'] == pytest.approx(1.04)
        assert shows_f135_tsfc_toggle('F-35B') is True
    finally:
        mod._INJECTED = None
        load_combat_radius_config.cache_clear()
