"""起飞输入校验与结果高亮卡片单元测试。"""
from __future__ import annotations

from utils.takeoff.takeoff_input import (
    build_takeoff_highlights,
    extract_exit_kinematics,
    mass_range_hint,
    validate_takeoff_mass,
)


def test_validate_takeoff_mass_ok():
    """空重与 MTOW 之间合法。"""
    assert validate_takeoff_mass(20000, 27200, 14651) is None


def test_validate_takeoff_mass_negative():
    """负重量立即拒绝。"""
    msg = validate_takeoff_mass(-500, 27200, 14651)
    assert msg is not None
    assert '正数' in msg


def test_validate_takeoff_mass_zero():
    """零重量非法。"""
    assert '正数' in (validate_takeoff_mass(0, 27200, 14651) or '')


def test_validate_takeoff_mass_above_mtow():
    """超出 MTOW 给出明确提示。"""
    msg = validate_takeoff_mass(50000, 27200, 14651)
    assert msg is not None
    assert '超出最大起飞重量' in msg
    assert '27200' in msg


def test_validate_takeoff_mass_below_empty():
    """低于空重给出提示。"""
    msg = validate_takeoff_mass(1000, 27200, 14651)
    assert msg is not None
    assert '空重' in msg


def test_validate_takeoff_mass_nan():
    """非数字拒绝。"""
    assert validate_takeoff_mass(float('nan'), 27200, 14651) is not None


def test_mass_range_hint():
    """范围文案含空重与 MTOW。"""
    hint = mass_range_hint(14651, 27200)
    assert '14651' in hint
    assert '27200' in hint
    assert hint.startswith('范围：')


def test_mass_range_hint_empty():
    """缺数据时返回空串。"""
    assert mass_range_hint(None, None) == ''


def test_build_takeoff_highlights_ok_margin():
    """甲板有余量时四张卡片。"""
    cards = build_takeoff_highlights(85.6, 120.4, 42.1, 8.2, True)
    keys = [c['key'] for c in cards]
    assert keys == ['distance', 'margin', 'speed', 'time']
    assert cards[0]['value'] == '85.6 m'
    assert cards[1]['tone'] == 'ok'
    assert '120.4' in cards[1]['value']
    assert cards[2]['value'] == '42.1 m/s'


def test_build_takeoff_highlights_overrun():
    """超出甲板时卡片标危险色。"""
    cards = build_takeoff_highlights(300.0, -12.3, 50.0, 10.0, False)
    margin = next(c for c in cards if c['key'] == 'margin')
    assert margin['tone'] == 'danger'
    assert margin['label'] == '超出甲板'
    assert '12.3' in margin['value']


def test_extract_exit_kinematics_prefers_deck_keys():
    """优先 v_deck_mps / t_deck_s。"""
    speed, time_s = extract_exit_kinematics({
        'v_deck_mps': 40.0, 'v_gs_mps': 1.0, 't_deck_s': 7.5, 't_s': 1.0,
    })
    assert speed == 40.0
    assert time_s == 7.5


def test_extract_exit_kinematics_fallback():
    """缺少甲板键时回退地速/总时间。"""
    speed, time_s = extract_exit_kinematics({'v_gs_mps': 33.0, 't_s': 9.0})
    assert speed == 33.0
    assert time_s == 9.0


def test_extract_exit_kinematics_empty():
    """空结果返回 None。"""
    assert extract_exit_kinematics(None) == (None, None)
    assert extract_exit_kinematics({}) == (None, None)
