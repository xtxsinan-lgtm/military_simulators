"""AircraftSpec / 载弹量字段单元测试。"""
import pytest

from utils.database_csv import load_aircraft_csv
from utils.paths import AIRCRAFT_CSV
from utils.specs import (
    A2A_MISSILE_COUNT,
    PILOT_LOAD_KG,
    is_vtol_aircraft,
    simulation_uses_plume_model,
)


def test_a2a_mass_and_catalog_payload():
    """空战起飞重量仍为推算；最大载弹量取自 CSV 资料值。"""
    ac = load_aircraft_csv(AIRCRAFT_CSV)['J-15']
    assert ac.a2a_mass_kg == ac.empty_kg + ac.internal_fuel_kg + A2A_MISSILE_COUNT * ac.missile_mass_kg + PILOT_LOAD_KG
    assert ac.max_payload_kg == 6500


def test_max_payload_kg_user_specified_chinese_types():
    aircraft = load_aircraft_csv(AIRCRAFT_CSV)
    assert aircraft['J-15'].max_payload_kg == 6500
    assert aircraft['J-15T'].max_payload_kg == 8000
    assert aircraft['J-35'].max_payload_kg == 8000
    assert aircraft['J-35'].empty_kg == 14000
    assert aircraft['J-50N'].empty_kg == 20800
    assert aircraft['J-50N'].internal_fuel_kg == 13000
    assert aircraft['J-50N'].mtow_kg == 41000
    assert aircraft['NG6C'].mtow_kg == 29000
    assert aircraft['NG6C'].max_payload_kg == 8000
    assert aircraft['NG6B'].mtow_kg == 27000
    assert aircraft['NG6B'].max_payload_kg == 6800
    assert aircraft['NG6B'].is_vtol is True
    assert aircraft['NG6C'].a2a_mass_kg == pytest.approx(12700 + 8500 + 100 + 4 * 210)
    assert aircraft['NG6B'].a2a_mass_kg == pytest.approx(12900 + 7900 + 100 + 4 * 210)
    assert 'J-50' not in aircraft
    assert 'NG6A' not in aircraft


def test_j50n_a2a_mass_full_internal_fuel_four_missiles():
    """4 枚中距弹满内油空战起飞重量 = 空重 + 内油 + 4×弹 + 飞行员。"""
    ac = load_aircraft_csv(AIRCRAFT_CSV)['J-50N']
    assert ac.a2a_mass_kg == pytest.approx(
        20800 + 13000 + A2A_MISSILE_COUNT * ac.missile_mass_kg + ac.n_pilots * PILOT_LOAD_KG
    )
    assert ac.a2a_mass_kg == pytest.approx(34740)
    assert ac.a2a_mass_kg < ac.mtow_kg


def test_uav_carrier_a2a_mass_zero_pilots():
    """舰载无人机空战重量不计飞行员。"""
    ac = load_aircraft_csv(AIRCRAFT_CSV)['53636N']
    assert ac.n_pilots == 0
    assert ac.a2a_mass_kg == pytest.approx(
        ac.empty_kg + ac.internal_fuel_kg + A2A_MISSILE_COUNT * ac.missile_mass_kg
    )


def test_max_payload_kg_wikipedia_sourced_types():
    """其余机型载弹量为公开资料（Wikipedia / 厂商）圆整值。"""
    aircraft = load_aircraft_csv(AIRCRAFT_CSV)
    assert aircraft['F-35B'].max_payload_kg == 6800
    assert aircraft['AV-8B'].max_payload_kg == 4200
    assert aircraft['MiG-29K'].max_payload_kg == 5500
    assert aircraft['Rafale-M'].max_payload_kg == 9500
    assert aircraft['FA-18E'].max_payload_kg == 8050
    assert aircraft['FA-18C'].max_payload_kg == 6215
    assert aircraft['F-14'].max_payload_kg == 6700


def test_carrier_deck_wind_defaults_to_max_speed():
    """默认甲板风等于航母最大航速。"""
    from utils.database_csv import load_carriers_csv
    from utils.paths import CARRIERS_CSV

    wasp = next(c for c in load_carriers_csv(CARRIERS_CSV) if c.id == 'WASP')
    assert wasp.ski_jump is False
    assert wasp.deck_wind_kt() == wasp.max_speed_kt

    shandong = next(c for c in load_carriers_csv(CARRIERS_CSV) if c.id == 'SHANDONG')
    assert shandong.deck_wind_kt() == shandong.max_speed_kt


def test_carrier_ski_jump_geom():
    from utils.database_csv import load_carriers_csv
    from utils.paths import CARRIERS_CSV

    carrier = next(c for c in load_carriers_csv(CARRIERS_CSV) if c.id == 'SHANDONG')
    geom = carrier.ski_jump_geom()
    assert geom is not None
    assert carrier.ski_jump_horizontal_m() == geom.horizontal_m


def test_is_vtol_aircraft():
    aircraft = load_aircraft_csv(AIRCRAFT_CSV)
    assert aircraft['F-35B'].is_vtol is True
    assert is_vtol_aircraft(aircraft['J-15']) is False


def test_mv22_tiltrotor_spec_from_wikipedia():
    from utils.specs import is_tiltrotor_aircraft

    ac = load_aircraft_csv(AIRCRAFT_CSV)['MV-22']
    assert ac.is_tiltrotor is True
    assert is_tiltrotor_aircraft(ac) is True
    assert ac.mtow_kg == pytest.approx(25855)
    assert ac.shaft_power_sl_w == pytest.approx(9180000)
    assert ac.prop_diameter_m == pytest.approx(11.61)
    assert ac.nacelle_blockage_frac == pytest.approx(0.10)
    assert ac.t_liftfan_sl_n is None
    assert ac.t_rollposts_sl_n is None


def test_simulation_uses_plume_model_only_vtol_short_modes():
    aircraft = load_aircraft_csv(AIRCRAFT_CSV)
    f35b = aircraft['F-35B']
    j15 = aircraft['J-15']
    mv22 = aircraft['MV-22']
    assert simulation_uses_plume_model('short_takeoff', f35b) is True
    assert simulation_uses_plume_model('short_ski_jump', f35b) is True
    assert simulation_uses_plume_model('ski_jump', j15) is False
    assert simulation_uses_plume_model('short_takeoff', j15) is False
    assert simulation_uses_plume_model('tiltrotor_short_takeoff', mv22) is False
