"""轨迹功能的端到端回归测试（run_simulation 全链路）。"""
import pytest

from apps.web_simulator import run_simulation
from utils.database_csv import load_aircraft_csv, load_carriers_csv
from utils.paths import AIRCRAFT_CSV, CARRIERS_CSV


@pytest.fixture(scope='module')
def aircraft():
    return load_aircraft_csv(AIRCRAFT_CSV)


@pytest.fixture(scope='module')
def carriers():
    return load_carriers_csv(CARRIERS_CSV)


@pytest.mark.e2e
def test_e2e_ski_jump_trajectory(aircraft, carriers):
    """滑跃起飞：run_simulation 应返回稳定结构的轨迹与甲板折线。"""
    carrier = next(c for c in carriers if c.id == 'SHANDONG')
    ac = aircraft['J-15']
    result = run_simulation(
        'ski_jump', ac, carrier, ac.a2a_mass_kg, 30.0, carrier.max_speed_kt,
    )
    assert result['success'] is True
    assert result['distance_m'] == pytest.approx(85.6, rel=0.02)
    assert '起飞' in result['output_summary']
    assert '余量' in result['output_summary'] or '超出' in result['output_summary']
    assert result['highlights']
    assert any(c['key'] == 'distance' for c in result['highlights'])

    traj = result['trajectory']
    deck = result['deck_profile']
    assert len(traj) >= 20
    assert traj[0] == {'x': 0.0, 'y': 0.0, 't': 0.0, 'phase': 'flat'}
    phases = {p['phase'] for p in traj}
    assert phases >= {'flat', 'arc', 'air', 'deck_exit'}
    assert deck['flat_length_m'] == pytest.approx(result['result']['flat_m'], rel=0.01)
    assert deck['points'][0] == [0.0, 0.0]
    assert deck['total_deck_length_m'] == carrier.total_deck_length_m
    assert max(p['y'] for p in traj if p['phase'] == 'arc') == pytest.approx(deck['lip_height_m'], rel=0.05)


@pytest.mark.e2e
def test_e2e_short_ski_jump_trajectory(aircraft, carriers):
    """短距滑跃起飞：run_simulation 应返回轨迹且 y 随滑跃升高。"""
    carrier = next(c for c in carriers if c.ski_jump and c.f35b_capable)
    ac = aircraft['F-35B']
    result = run_simulation(
        'short_ski_jump', ac, carrier, ac.a2a_mass_kg, 30.0, 22.0,
    )
    assert result['success'] is True
    assert result['trajectory']
    assert result['deck_profile']
    traj = result['trajectory']
    assert {p['phase'] for p in traj} >= {'flat', 'arc', 'air'}
    assert traj[-1]['y'] > traj[0]['y']


@pytest.mark.e2e
def test_e2e_short_takeoff_no_trajectory(aircraft, carriers):
    """短距平直起飞：不应返回轨迹数据。"""
    carrier = next(c for c in carriers if c.id == 'WASP')
    ac = aircraft['F-35B']
    result = run_simulation(
        'short_takeoff', ac, carrier, ac.a2a_mass_kg, 30.0, 22.0,
    )
    assert result['success'] is True
    assert result['trajectory'] is None
    assert result['deck_profile'] is None
