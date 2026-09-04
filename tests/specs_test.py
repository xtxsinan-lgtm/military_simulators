"""AircraftSpec / 载弹量字段单元测试。"""
import pytest

from utils.database_csv import load_aircraft_csv
from utils.paths import AIRCRAFT_CSV
from utils.specs import (
    A2A_MISSILE_COUNT,
    PILOT_LOAD_KG,
    is_vtol_aircraft,
    simulation_uses_plume_model,
    uses_propeller_power,
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
    assert aircraft['J-15T'].empty_kg == pytest.approx(18200)
    assert aircraft['J-15T'].internal_fuel_kg == pytest.approx(10000)
    assert aircraft['J-15T'].mtow_kg == pytest.approx(36300)
    assert aircraft['J-35'].max_payload_kg == 8000
    assert aircraft['J-35'].empty_kg == 15000
    assert aircraft['J-50N'].empty_kg == 19900
    assert aircraft['J-50N'].internal_fuel_kg == 13000
    assert aircraft['J-50N'].mtow_kg == pytest.approx(41800)
    assert aircraft['NG6C'].mtow_kg == 29000
    assert aircraft['NG6C'].max_payload_kg == 8000
    assert aircraft['NG6B'].mtow_kg == pytest.approx(28340)
    assert aircraft['NG6B'].max_payload_kg == 8000
    assert aircraft['NG6B'].is_vtol is True
    assert aircraft['NG6C'].a2a_mass_kg == pytest.approx(13700 + 8400 + 100 + 4 * 210)
    assert aircraft['NG6B'].internal_fuel_kg == pytest.approx(7230)
    assert aircraft['NG6B'].a2a_mass_kg == pytest.approx(13900 + 7230 + 100 + 4 * 210)
    assert aircraft['J-10C'].mtow_kg == pytest.approx(19277)
    assert aircraft['J-10C'].max_payload_kg == pytest.approx(5600)
    assert aircraft['J-10C'].a2a_mass_kg == pytest.approx(9750 + 3860 + 100 + 4 * 210)
    assert aircraft['J-20'].mtow_kg == pytest.approx(37000)
    assert aircraft['J-20'].max_payload_kg == pytest.approx(9500)
    assert aircraft['J-20'].a2a_mass_kg == pytest.approx(18000 + 10000 + 100 + 4 * 210)
    assert 'J-50' not in aircraft
    assert 'NG6A' not in aircraft


def test_j50n_a2a_mass_full_internal_fuel_four_missiles():
    """4 枚中距弹满内油空战起飞重量 = 空重 + 内油 + 4×弹 + 飞行员。"""
    ac = load_aircraft_csv(AIRCRAFT_CSV)['J-50N']
    assert ac.a2a_mass_kg == pytest.approx(
        19900 + 13000 + A2A_MISSILE_COUNT * ac.missile_mass_kg + ac.n_pilots * PILOT_LOAD_KG
    )
    assert ac.a2a_mass_kg == pytest.approx(33840)
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
    assert aircraft['A-6'].max_payload_kg == 8170
    assert aircraft['A-7'].max_payload_kg == 6800
    assert aircraft['S-3'].max_payload_kg == 1800
    assert aircraft['C-2'].max_payload_kg == 4536
    assert aircraft['A-3'].max_payload_kg == 5440
    assert aircraft['A-5'].max_payload_kg == 2000
    assert aircraft['F-35A'].max_payload_kg == 8160
    assert aircraft['F-15'].max_payload_kg == 7300
    assert aircraft['F-16'].max_payload_kg == 7800
    assert aircraft['Typhoon'].max_payload_kg == 9000
    assert aircraft['Gripen-CD'].max_payload_kg == 5300
    assert aircraft['Gripen-EF'].max_payload_kg == 7200
    assert aircraft['F-CK-1'].max_payload_kg == 3600
    assert aircraft['FC-1'].max_payload_kg == 3600
    assert aircraft['Tejas'].max_payload_kg == 3500


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
    assert ac.uses_propeller_power is True


def test_usn_legacy_carrier_specs_from_public_sources():
    """A-6/A-7/S-3/C-2/A-3/A-5 起飞机库字段与公开资料一致。"""
    from utils.specs import is_conventional_aircraft
    from utils.takeoff.propeller_thrust import (
        DEFAULT_FIGURE_OF_MERIT,
        calc_prop_disk_area_m2,
        calc_propeller_thrust_n,
    )
    from utils.takeoff.takeoff_physics import calc_sea_level_density_kg_m3

    aircraft = load_aircraft_csv(AIRCRAFT_CSV)
    expected = {
        'A-6': dict(empty_kg=12093, fuel=7230, mtow=27397, thrust=82800, span=16.15, area=49.14, pilots=2),
        'A-7': dict(empty_kg=8676, fuel=3945, mtow=19050, thrust=66700, span=11.80, area=34.83, pilots=1),
        'S-3': dict(empty_kg=12057, fuel=5962, mtow=23831, thrust=82600, span=20.93, area=55.56, pilots=4),
        'C-2': dict(empty_kg=15307, fuel=5625, mtow=26082, thrust=110130, span=24.56, area=65.03, pilots=4),
        'A-3': dict(empty_kg=17876, fuel=13570, mtow=37195, thrust=110400, span=22.10, area=75.4, pilots=3),
        'A-5': dict(empty_kg=14870, fuel=8652, mtow=28615, thrust=151200, span=16.16, area=65.1, pilots=2),
    }
    for aid, exp in expected.items():
        ac = aircraft[aid]
        assert is_conventional_aircraft(ac) is True, aid
        assert ac.empty_kg == pytest.approx(exp['empty_kg'])
        assert ac.internal_fuel_kg == pytest.approx(exp['fuel'])
        assert ac.mtow_kg == pytest.approx(exp['mtow'])
        assert ac.t_max_sl_n == pytest.approx(exp['thrust'])
        assert ac.wingspan_m == pytest.approx(exp['span'])
        assert ac.wing_area_m2 == pytest.approx(exp['area'])
        assert ac.n_pilots == exp['pilots']
        assert ac.a2a_mass_kg < ac.mtow_kg, aid

    c2 = aircraft['C-2']
    rho = calc_sea_level_density_kg_m3(15.0)
    disk = calc_prop_disk_area_m2(c2.prop_diameter_m, 2)
    t_eq = calc_propeller_thrust_n(
        c2.shaft_power_sl_w, rho, disk, 0.0,
        DEFAULT_FIGURE_OF_MERIT, c2.nacelle_blockage_frac,
    )
    assert c2.t_max_sl_n == pytest.approx(t_eq, rel=1e-3)
    assert c2.shaft_power_sl_w == pytest.approx(6860440)
    assert c2.prop_diameter_m == pytest.approx(4.11)
    assert c2.nacelle_blockage_frac == pytest.approx(0.08)
    assert uses_propeller_power(c2) is True
    assert c2.uses_propeller_power is True
    assert uses_propeller_power(aircraft['A-6']) is False
    assert uses_propeller_power(aircraft['J-15']) is False
    assert aircraft['J-10C'].layout == 'canard'
    assert aircraft['J-10C'].canard_htail_area_m2 == pytest.approx(4.9)
    assert aircraft['Typhoon'].canard_htail_area_m2 == pytest.approx(2.4)
    assert aircraft['Rafale-M'].canard_htail_area_m2 == pytest.approx(5.5)
    assert aircraft['Gripen-CD'].canard_htail_area_m2 == pytest.approx(4.5)


def test_land_fighters_ski_jump_specs_from_public_sources():
    """歼-10C / 歼-20 / F-35A 及新加入的陆基战斗机可上滑跃机库。"""
    from utils.specs import is_conventional_aircraft

    aircraft = load_aircraft_csv(AIRCRAFT_CSV)
    expected = {
        'J-10C': dict(mtow=19277, thrust=144000, span=9.8, area=37.0),
        'J-20': dict(mtow=37000, thrust=312000, span=13.01, area=76.8),
        'F-35A': dict(mtow=31751, thrust=191000, span=10.7, area=42.74),
        'F-15': dict(mtow=30844, thrust=211400, span=13.06, area=56.5),
        'F-16': dict(mtow=19187, thrust=131200, span=9.96, area=28.0),
        'Typhoon': dict(mtow=23500, thrust=180000, span=10.95, area=51.2),
        'Gripen-CD': dict(mtow=14000, thrust=80500, span=8.4, area=30.0),
        'Gripen-EF': dict(mtow=16500, thrust=98000, span=8.6, area=31.0),
        'F-CK-1': dict(mtow=12247, thrust=84200, span=9.0, area=24.2),
        'FC-1': dict(mtow=13500, thrust=91200, span=9.44, area=24.43),
        'Tejas': dict(mtow=13500, thrust=85000, span=8.20, area=38.4),
    }
    for aid, exp in expected.items():
        ac = aircraft[aid]
        assert is_conventional_aircraft(ac) is True, aid
        assert ac.mtow_kg == pytest.approx(exp['mtow'])
        assert ac.t_max_sl_n == pytest.approx(exp['thrust'])
        assert ac.wingspan_m == pytest.approx(exp['span'])
        assert ac.wing_area_m2 == pytest.approx(exp['area'])
        assert ac.a2a_mass_kg < ac.mtow_kg, aid


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
