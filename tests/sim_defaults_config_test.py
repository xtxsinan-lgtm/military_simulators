"""data/takeoff_config.json 与 data/missile_interception_config.json 加载测试。"""
from __future__ import annotations

from utils.paths import MISSILE_INTERCEPTION_CONFIG_JSON, TAKEOFF_CONFIG_JSON
from utils.missile_interception.missile_interception_config import load_missile_interception_config, ui_config as sat_ui
from utils.takeoff.takeoff_config import load_takeoff_config, shared_config


def test_takeoff_config_file_exists_and_unified_mu():
    assert TAKEOFF_CONFIG_JSON.is_file()
    cfg = load_takeoff_config()
    mu = cfg['shared']['mu']
    for mode in cfg['modes']:
        assert mode in ('short_takeoff', 'short_ski_jump', 'ski_jump', 'tiltrotor_short_takeoff')
    assert shared_config()['mu'] == mu


def test_missile_interception_config_file_exists_and_ui_defaults():
    assert MISSILE_INTERCEPTION_CONFIG_JSON.is_file()
    ui = sat_ui()
    assert ui['nm'] == 24
    assert ui['pk'] == 0.7
    assert load_missile_interception_config()['physics']['mach_mps'] == 340.0
    assert 'glide' in load_missile_interception_config()['traj_types']
    assert 'ballistic' in load_missile_interception_config()['traj_types']


def test_combat_radius_config_file_exists_and_ui_defaults():
    from utils.combat_radius.combat_radius_config import ui_config as cr_ui
    from utils.paths import COMBAT_RADIUS_CONFIG_JSON

    assert COMBAT_RADIUS_CONFIG_JSON.is_file()
    ui = cr_ui()
    assert ui['default_anchor1_id'] == 'F-35C'
    assert ui['default_ld1'] == 8.8
    assert ui['default_engine_id'] == 'f119'
