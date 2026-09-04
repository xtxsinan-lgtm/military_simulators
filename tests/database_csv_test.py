"""舰载机 / 航母 / 饱和打击导弹与雷达 CSV 导入导出单元测试。"""
import pytest

from utils.database_csv import (
    AIRCRAFT_CSV_COLUMNS,
    COMBAT_RADIUS_AIRCRAFT_CSV_COLUMNS,
    COMBAT_RADIUS_ENGINE_CSV_COLUMNS,
    MISSILE_INTERCEPTION_MISSILE_CSV_COLUMNS,
    MISSILE_INTERCEPTION_RADAR_CSV_COLUMNS,
    _combat_radius_item_from_row,
    _estimate_cd0_for_item,
    _parse_int,
    _parse_optional_float,
    _read_unified_aircraft_rows,
    _row_has_takeoff_spec,
    export_aircraft_csv,
    list_model_ids_from_missile_interception_csv,
    load_aircraft_csv,
    load_carriers_csv,
    load_combat_radius_aircraft_csv,
    load_combat_radius_engine_csv,
    load_missile_interception_missile_csv,
    load_missile_interception_presets_csv,
    load_missile_interception_radar_csv,
)
from utils.paths import (
    AIRCRAFT_CSV,
    CARRIERS_CSV,
    COMBAT_RADIUS_AIRCRAFT_CSV,
    COMBAT_RADIUS_ENGINE_CSV,
    MISSILE_INTERCEPTION_MISSILE_CSV,
    MISSILE_INTERCEPTION_RADAR_CSV,
)


def test_load_aircraft_csv_count():
    """起飞仿真加载填写了 mtow_kg 的机型（含陆基歼-10C / 歼-20 滑跃假设）。"""
    aircraft = load_aircraft_csv(AIRCRAFT_CSV)
    assert 'F-35B' in aircraft
    assert 'AV-8B' in aircraft
    assert 'J-15' in aircraft
    assert 'F-14' in aircraft
    assert 'FA-18C' in aircraft
    assert 'MV-22' in aircraft
    assert 'F-35C' in aircraft
    assert 'J-50N' in aircraft
    assert 'J-35' in aircraft
    assert '53636' in aircraft
    assert '53636N' in aircraft
    assert aircraft['53636'].mtow_kg == pytest.approx(14600)
    assert aircraft['53636N'].mtow_kg == pytest.approx(15200)
    assert aircraft['53636'].t_max_sl_n == pytest.approx(132000)
    assert 'NG6C' in aircraft
    assert 'NG6B' in aircraft
    assert 'J-10C' in aircraft
    assert 'J-20' in aircraft
    assert 'F-35A' in aircraft
    assert 'F-15' in aircraft
    assert 'F-16' in aircraft
    assert 'Typhoon' in aircraft
    assert 'Rafale' in aircraft
    assert 'Rafale-M' in aircraft
    assert 'Su-57' in aircraft
    assert 'KF-21' in aircraft
    assert 'KAAN' in aircraft
    assert 'Su-75' in aircraft
    assert 'Gripen-CD' in aircraft
    assert 'Gripen-EF' in aircraft
    assert 'F-CK-1' in aircraft
    assert 'FC-1' in aircraft
    assert 'Tejas' in aircraft
    assert 'A-6' in aircraft
    assert 'A-7' in aircraft
    assert 'S-3' in aircraft
    assert 'C-2' in aircraft
    assert 'A-3' in aircraft
    assert 'A-5' in aircraft
    assert aircraft['NG6C'].type_label == 'conventional'
    assert aircraft['NG6B'].type_label == 'v/stol'
    assert aircraft['NG6C'].t_max_sl_n == pytest.approx(185000)
    assert aircraft['NG6B'].t_liftfan_sl_n == pytest.approx(83260)
    assert aircraft['J-10C'].t_max_sl_n == pytest.approx(144000)
    assert aircraft['J-20'].t_max_sl_n == pytest.approx(312000)
    assert aircraft['F-35A'].t_max_sl_n == pytest.approx(191000)
    assert 'F-22' not in aircraft
    assert 'J-50' not in aircraft
    assert 'NG6A' not in aircraft
    assert all(ac.cd0 > 0 for ac in aircraft.values())


def test_row_has_takeoff_spec_requires_mtow():
    """只有填写最大起飞重量的行才进入起飞仿真。"""
    assert _row_has_takeoff_spec({'mtow_kg': '19277'}) is True
    assert _row_has_takeoff_spec({'mtow_kg': ''}) is False
    assert _row_has_takeoff_spec({}) is False


def _unified_csv_text(data_rows: list[dict[str, str]]) -> str:
    """拼出带表头的统一机型库文本。"""
    lines = [','.join(AIRCRAFT_CSV_COLUMNS)]
    for src in data_rows:
        row = {c: '' for c in AIRCRAFT_CSV_COLUMNS}
        row.update(src)
        lines.append(','.join(str(row[c]) for c in AIRCRAFT_CSV_COLUMNS))
    return '\n'.join(lines) + '\n'


def _valid_land_row(**over: str) -> dict[str, str]:
    base = {
        'id': 'X1', 'name': '测试', 'nation': '中国', 'carrier': '0',
        'type_label': 'conventional',
        'AR': '2.5', 'sweep_deg': '30', 'wing_loading': '0.3', 'tc': '0.05',
        'mach': '0.8', 'alt_m': '12000', 'planform': 'trapezoidal',
        'layout': 'conventional', 'bwb': '0', 'rough': '0', 'inlet': 'dsi',
        'wing_area_m2': '60', 'wingspan_m': '13',
        'empty_kg': '15000', 'internal_fuel_kg': '8000',
        'n_pilots': '1', 'missile_mass_kg': '150', 'n_engines': '1',
    }
    base.update(over)
    return base


def _wetted_fields(**over: str) -> dict[str, str]:
    """测试用分段浸润几何（使该行进入作战半径机型列表）。"""
    base = {
        'nose_cone_length_m': '1.06', 'nose_cone_diameter_m': '1.02',
        'nose_length_m': '3.26', 'nose_root_diameter_m': '1.90',
        'fuse_body_length_m': '9.66', 'fuse_width_m': '3.40', 'fuse_height_m': '1.97',
        'main_wing_area_m2': '24.48', 'canard_htail_area_m2': '11.12',
        'vtail_area_m2': '8.46',
        'wing_area_m2': '42.74',
    }
    base.update(over)
    return base


def test_load_carriers_csv_count():
    """起飞仿真：CSV 中的航母型号应全部可加载。"""
    carriers = load_carriers_csv(CARRIERS_CSV)
    assert len(carriers) >= 9
    ids = {c.id for c in carriers}
    assert 'SHANDONG' in ids
    assert 'WASP' in ids


def test_aircraft_a2a_mass_via_specs():
    from utils.specs import A2A_MISSILE_COUNT, PILOT_LOAD_KG

    aircraft = load_aircraft_csv(AIRCRAFT_CSV)
    j15 = aircraft['J-15']
    assert j15.a2a_mass_kg == pytest.approx(
        j15.empty_kg + j15.internal_fuel_kg + A2A_MISSILE_COUNT * j15.missile_mass_kg + PILOT_LOAD_KG
    )
    f14 = aircraft['F-14']
    assert f14.wingspan_m == pytest.approx(19.54)
    assert f14.t_max_sl_n == pytest.approx(250900)
    hornet = aircraft['FA-18C']
    assert hornet.wing_area_m2 == pytest.approx(38.0)
    assert hornet.t_max_sl_n == pytest.approx(156600)


def test_load_missile_interception_missile_csv_groups():
    """饱和打击：导弹库含反舰弹与防空弹。"""
    data = load_missile_interception_missile_csv(MISSILE_INTERCEPTION_MISSILE_CSV)
    assert set(data) == {'asm', 'sam'}
    assert len(data['asm']) >= 7
    assert len(data['sam']) >= 8
    assert data['asm'][0]['id'] == 'exocet'
    assert 'vm' in data['asm'][0]
    assert 'guidance' in data['sam'][0]


def test_load_missile_interception_radar_csv_groups():
    """饱和打击：雷达库含预警机与舰载雷达。"""
    data = load_missile_interception_radar_csv(MISSILE_INTERCEPTION_RADAR_CSV)
    assert set(data) == {'aew', 'ship'}
    assert len(data['aew']) >= 4
    assert len(data['ship']) >= 5
    assert 'area' in data['aew'][0]
    assert 'standoff' in data['aew'][0]
    assert 'area' in data['ship'][0]
    assert 'standoff' not in data['ship'][0]


def test_load_missile_interception_presets_csv_merges():
    """合并双库后应得到四类预设。"""
    data = load_missile_interception_presets_csv()
    assert set(data) == {'asm', 'aew', 'ship', 'sam'}
    assert data['asm'][0]['id'] == 'exocet'
    assert data['aew'][0]['id'] == 'e2d'


def test_list_model_ids_from_missile_interception_csv():
    """列出双库型号 id，供前端自动同步断言。"""
    ids = list_model_ids_from_missile_interception_csv()
    assert 'yj12' in ids['asm']
    assert 'e2d' in ids['aew']
    assert 'type055' in ids['ship']
    assert 'hhq9' in ids['sam']


def test_missile_interception_csv_columns_include_nation():
    """双库表头须含 nation 列，且位于 name 之后。"""
    for columns in (MISSILE_INTERCEPTION_MISSILE_CSV_COLUMNS, MISSILE_INTERCEPTION_RADAR_CSV_COLUMNS):
        assert 'nation' in columns
        assert columns.index('nation') == columns.index('name') + 1


def test_missile_interception_presets_all_have_nation():
    """四类预设每条记录均带非空国别（两级选择器依赖）。"""
    data = load_missile_interception_presets_csv()
    for cat in ('asm', 'sam', 'ship', 'aew'):
        assert data[cat], f'{cat} 无记录'
        for item in data[cat]:
            assert item.get('nation'), f"{cat} {item['id']} 缺少国别"


@pytest.mark.parametrize(('cat', 'item_id', 'nation'), [
    ('asm', 'yj12', '中国'),
    ('asm', 'harpoon', '美国'),
    ('sam', 'sm6', '美国'),
    ('sam', 'hhq9', '中国'),
    ('ship', 'type055', '中国'),
    ('ship', 'burke3', '美国'),
    ('aew', 'kj600', '中国'),
    ('aew', 'e2d', '美国'),
])
def test_missile_interception_preset_nation_samples(cat: str, item_id: str, nation: str):
    """抽样校验各类装备国别取值。"""
    data = load_missile_interception_presets_csv()
    item = next(x for x in data[cat] if x['id'] == item_id)
    assert item['nation'] == nation


def test_missile_interception_missile_csv_missing_nation_raises(tmp_path):
    """国别为空时导弹库加载须报错，避免出现无国别型号。"""
    path = tmp_path / 'missile.csv'
    path.write_text(
        ','.join(MISSILE_INTERCEPTION_MISSILE_CSV_COLUMNS) + '\n'
        'asm,x1,测试弹,,2.0,0.2,sea,,,,,\n',
        encoding='utf-8',
    )
    with pytest.raises(ValueError, match='nation'):
        load_missile_interception_missile_csv(path)


def test_missile_interception_radar_csv_missing_nation_raises(tmp_path):
    """国别为空时雷达库加载须报错。"""
    path = tmp_path / 'radar.csv'
    path.write_text(
        ','.join(MISSILE_INTERCEPTION_RADAR_CSV_COLUMNS) + '\n'
        'ship,x1,测试舰,,12,aesa,,\n',
        encoding='utf-8',
    )
    with pytest.raises(ValueError, match='nation'):
        load_missile_interception_radar_csv(path)


def test_load_combat_radius_aircraft_csv():
    """作战半径机型须含分段浸润几何，且不含歼-15 等起飞专用机。"""
    rows = load_combat_radius_aircraft_csv(COMBAT_RADIUS_AIRCRAFT_CSV)
    ids = [r['id'] for r in rows]
    assert ids == [
        'F-35C', 'F-22', 'F-35A', 'J-20', 'J-10C', 'J-50', 'J-50N', 'J-36',
        'J-35', 'J-35A', '53636', '53636N', '53536',
        'F-35B',
        'Rafale-M', 'Rafale',
        'NG6C', 'NG6B', 'NG6A',
        'Typhoon',
        'Su-57', 'KF-21', 'KAAN', 'Su-75',
    ]
    for aid in ('NG6C', 'NG6B', 'NG6A'):
        ng6 = next(r for r in rows if r['id'] == aid)
        expected_htail = 16.7 if aid == 'NG6C' else 13.9
        assert ng6['canard_htail_area_m2'] == pytest.approx(expected_htail), aid
        expected_phi = 29.3 if aid == 'NG6C' else 27.3
        assert ng6['mach_angle_deg'] == pytest.approx(expected_phi), aid
    ng6b = next(r for r in rows if r['id'] == 'NG6B')
    assert ng6b['internal_fuel_kg'] == pytest.approx(7230)
    assert 'J-15' not in ids
    assert 'AV-8B' not in ids
    assert 'FA-18C' not in ids
    f35b = next(r for r in rows if r['id'] == 'F-35B')
    assert f35b['engine_id'] == 'f135b'
    assert f35b['canard_htail_area_m2'] == pytest.approx(5.56 * 2)
    assert f35b['vtail_area_m2'] == pytest.approx(4.23 * 2)
    assert f35b['main_wing_area_m2'] == pytest.approx(24.48)
    assert rows[0]['carrier'] is True
    assert next(r for r in rows if r['id'] == 'F-22')['carrier'] is False
    assert rows[0]['rough'] is True
    assert rows[0]['inlet'] == 'dsi'
    assert rows[0]['vtail_area_m2'] == pytest.approx(5.18 * 2)
    f22 = next(r for r in rows if r['id'] == 'F-22')
    j20 = next(r for r in rows if r['id'] == 'J-20')
    assert f22['inlet'] == 'caret'
    assert f22['store_mount'] == 'internal'
    assert j20['inlet'] == 'dsi'
    assert j20['store_mount'] == 'internal'
    assert j20.get('ld_known') is None
    assert j20['carrier'] is False
    assert j20['wing_area_m2'] == pytest.approx(76.8)
    j10c = next(r for r in rows if r['id'] == 'J-10C')
    assert j10c['carrier'] is False
    assert j10c['planform'] == 'delta'
    assert j10c['layout'] == 'canard'
    assert j10c['store_mount'] == 'pylon'
    assert j10c['engine_id'] == 'ws10b'
    assert j10c['wing_area_m2'] == pytest.approx(37.0)
    assert j10c['empty_kg'] == pytest.approx(9750)
    assert j10c['internal_fuel_kg'] == pytest.approx(3860)
    assert j20['ventral_fin_area_m2'] == pytest.approx(3.19 * 2)
    assert j20['canard_htail_area_m2'] == pytest.approx(3.45 * 2)
    assert j20['vtail_area_m2'] == pytest.approx(9.07 * 2)
    assert f22['empty_kg'] == 19800
    assert f22['n_engines'] == 2
    assert f22['engine_id'] == 'f119'
    assert f22['mach_angle_deg'] == pytest.approx(28.5)
    assert f22['wing_area_m2'] == pytest.approx(78.0)
    assert f22['fuse_width_m'] == pytest.approx(4.0)
    assert f22['fuse_height_m'] == pytest.approx(1.8)
    assert f22['canard_htail_area_m2'] == pytest.approx(7.6 * 2)
    assert f22['vtail_area_m2'] == pytest.approx(9.94 * 2)
    assert rows[0]['n_engines'] == 1
    uav = next(r for r in rows if r['id'] == '53636')
    assert uav['n_pilots'] == 0
    assert uav['inlet'] == 'caret'
    assert uav['engine_id'] == 'ws10c'
    uav_n = next(r for r in rows if r['id'] == '53636N')
    assert uav_n['inlet'] == 'caret'
    assert uav_n['engine_id'] == 'ws10c'
    assert uav_n['internal_fuel_kg'] == pytest.approx(4870)
    assert uav_n['empty_kg'] == pytest.approx(8300)
    j36 = next(r for r in rows if r['id'] == 'J-36')
    assert j36['n_engines'] == 3
    assert j36['n_pilots'] == 2
    assert j36['planform'] == 'double_delta'
    assert j36['inlet'] == 'caret'
    assert j36['sweep_inner_deg'] == pytest.approx(67.8)
    assert j36['sweep_outer_deg'] == pytest.approx(55.3)
    assert j36['fuse_width_m'] == pytest.approx(6.1)
    assert j36['fuse_height_m'] == pytest.approx(2.4)
    assert j36['wing_area_m2'] == pytest.approx(196.0)
    assert j36['wingspan_m'] == pytest.approx(19.24)
    assert j36['AR'] == pytest.approx(19.24 ** 2 / 196.0, abs=0.005)
    j50 = next(r for r in rows if r['id'] == 'J-50')
    j50n = next(r for r in rows if r['id'] == 'J-50N')
    assert j50['empty_kg'] == pytest.approx(18300)
    assert j50n['empty_kg'] == pytest.approx(19900)
    assert j50['wingspan_m'] == pytest.approx(16.4)
    assert j50['wing_area_m2'] == pytest.approx(107.0)
    assert j50['main_wing_area_m2'] == pytest.approx(66.0)
    assert j50['nose_length_m'] == pytest.approx(5.0)
    assert j50['fuse_body_length_m'] == pytest.approx(10.0)
    assert j50['fuse_width_m'] == pytest.approx(3.5)
    assert j50['fuse_height_m'] == pytest.approx(1.7)
    assert j50n['wingspan_m'] == pytest.approx(16.4)
    assert j50n['wing_area_m2'] == pytest.approx(107.0)
    assert j50n['fuse_width_m'] == pytest.approx(3.5)
    j35 = next(r for r in rows if r['id'] == 'J-35')
    assert j35['vtail_area_m2'] == pytest.approx(6.62 * 2)
    assert j35['length_m'] == pytest.approx(17.7)
    assert j35['fuse_width_m'] == pytest.approx(3.70)
    assert j35['fuse_height_m'] == pytest.approx(1.48)
    assert j35['carrier'] is True
    j35a = next(r for r in rows if r['id'] == 'J-35A')
    assert j35a['vtail_area_m2'] == pytest.approx(10.86)
    assert j35a['length_m'] == pytest.approx(17.7)
    assert j35a['empty_kg'] == pytest.approx(13000)
    assert j35a['internal_fuel_kg'] == pytest.approx(7600)
    assert j35a['main_wing_area_m2'] == pytest.approx(28.0)
    assert j35a['canard_htail_area_m2'] == pytest.approx(10.66)
    assert j35a['wing_area_m2'] == pytest.approx(50.7)
    assert j35a['sweep_deg'] == pytest.approx(40.5)
    assert j35a['mach_angle_deg'] == pytest.approx(27.2)
    assert j35a['wingspan_m'] == pytest.approx(11.8)
    assert uav['length_m'] == pytest.approx(14.7)
    assert uav['wingspan_m'] == pytest.approx(10.2)
    assert uav['wing_area_m2'] == pytest.approx(50.23)
    assert uav['sweep_deg'] == pytest.approx(56.1)
    assert uav['mach_angle_deg'] == pytest.approx(23.1)
    assert uav['empty_kg'] == pytest.approx(7700)
    assert uav['internal_fuel_kg'] == pytest.approx(4870)
    assert uav['fuse_width_m'] == pytest.approx(2.26)
    assert uav['fuse_height_m'] == pytest.approx(1.62)
    uav535 = next(r for r in rows if r['id'] == '53536')
    assert uav535['length_m'] == pytest.approx(16.7)
    assert uav535['wingspan_m'] == pytest.approx(9.11)
    assert uav535['wing_area_m2'] == pytest.approx(53.04)
    assert uav535['sweep_deg'] == pytest.approx(52.3)
    assert uav535['mach_angle_deg'] == pytest.approx(21.6)
    assert uav535['empty_kg'] == pytest.approx(8000)
    assert uav535['internal_fuel_kg'] == pytest.approx(5690)
    assert uav535['fuse_width_m'] == pytest.approx(2.36)
    assert uav535['fuse_height_m'] == pytest.approx(1.61)
    assert uav535['bwb'] is True
    assert uav535['engine_id'] == 'ws10c'
    assert j36['bwb'] is True


def test_parse_int_accepts_int_and_float_text():
    assert _parse_int('2', 'n') == 2
    assert _parse_int('1.0', 'n') == 1
    assert _parse_int('0', 'n_pilots') == 0
    with pytest.raises(ValueError, match='必填'):
        _parse_int('', 'n')


def test_combat_radius_csv_unknown_planform_raises(tmp_path):
    path = tmp_path / 'cr.csv'
    path.write_text(_unified_csv_text([_valid_land_row(planform='hex')]), encoding='utf-8')
    with pytest.raises(ValueError, match='planform'):
        load_combat_radius_aircraft_csv(path)


def test_combat_radius_csv_unknown_inlet_raises(tmp_path):
    """未知进气道须在加载时拒绝，避免 silently 当成 DSI。"""
    path = tmp_path / 'cr.csv'
    path.write_text(_unified_csv_text([_valid_land_row(inlet='pitot')]), encoding='utf-8')
    with pytest.raises(ValueError, match='进气道'):
        load_combat_radius_aircraft_csv(path)


def test_combat_radius_csv_unknown_store_mount_raises(tmp_path):
    """未知挂装方式须在加载时拒绝。"""
    path = tmp_path / 'cr.csv'
    path.write_text(_unified_csv_text([_valid_land_row(store_mount='wingtip')]), encoding='utf-8')
    with pytest.raises(ValueError, match='挂装方式'):
        load_combat_radius_aircraft_csv(path)


def test_combat_radius_csv_empty_raises(tmp_path):
    path = tmp_path / 'cr.csv'
    path.write_text(_unified_csv_text([]), encoding='utf-8')
    with pytest.raises(ValueError, match='未读到'):
        load_combat_radius_aircraft_csv(path)


def test_load_combat_radius_aircraft_csv_skips_rows_without_wetted_geom(tmp_path):
    """无分段浸润几何的机型不进入作战半径列表。"""
    path = tmp_path / 'cr.csv'
    path.write_text(_unified_csv_text([_valid_land_row()]), encoding='utf-8')
    with pytest.raises(ValueError, match='未读到'):
        load_combat_radius_aircraft_csv(path)


def test_parse_optional_float_blank_and_number():
    assert _parse_optional_float('') is None
    assert _parse_optional_float('  ') is None
    assert _parse_optional_float('116.0') == 116.0


def test_load_combat_radius_engine_csv():
    rows = load_combat_radius_engine_csv(COMBAT_RADIUS_ENGINE_CSV)
    by_id = {r['id']: r for r in rows}
    assert by_id['f119']['tsl_kN'] == 116.0
    assert by_id['f119']['max_tsl_kN'] == 156.0
    assert by_id['f135']['max_tsl_kN'] == 191.0
    assert by_id['f135']['tsl_kN'] == pytest.approx(125.0)
    assert by_id['f135b']['tsl_kN'] == pytest.approx(120.0)
    assert by_id['f135b']['max_tsl_kN'] == pytest.approx(182.0)
    assert by_id['f135b']['bpr'] == pytest.approx(by_id['f135']['bpr'])
    assert by_id['f135b']['opr'] == pytest.approx(by_id['f135']['opr'])
    assert by_id['f135b']['t4_K'] == pytest.approx(by_id['f135']['t4_K'])
    assert by_id['f135b']['tsfc_install_mult'] == pytest.approx(1.22)
    assert by_id['ws15']['max_tsl_kN'] == 156.0
    assert by_id['ws15']['tsl_kN'] == 105.0
    assert by_id['ws15i']['max_tsl_kN'] == 185.0
    assert by_id['ws15i']['tsl_kN'] == pytest.approx(13.5 * 9.80665, abs=0.05)
    assert by_id['ws10c']['max_tsl_kN'] == 145.0
    assert by_id['ws10c']['tsl_kN'] == pytest.approx(90.0)
    assert by_id['ws10b']['max_tsl_kN'] == pytest.approx(144.0)
    assert by_id['ws10b']['tsl_kN'] == pytest.approx(89.17)
    assert by_id['ws19']['max_tsl_kN'] == 110.0
    assert by_id['ws19']['tsl_kN'] == pytest.approx(70.0)
    assert by_id['ws21']['max_tsl_kN'] == 95.0
    assert by_id['ws21']['tsl_kN'] == pytest.approx(66.2)
    assert by_id['f135']['t4_K'] == 2260.0
    assert by_id['f135']['tsfc_install_mult'] == pytest.approx(1.22)
    assert by_id['f119']['tsfc_install_mult'] == pytest.approx(1.0)
    assert by_id['f414']['bpr'] == pytest.approx(0.40)
    assert by_id['ws10h']['tsl_kN'] == 89.0
    assert by_id['ws10h']['max_tsl_kN'] == pytest.approx(125.5)
    assert by_id['f414']['max_tsl_kN'] == pytest.approx(97.9)
    assert by_id['f404']['max_tsl_kN'] == pytest.approx(78.3)
    assert by_id['f110']['max_tsl_kN'] == pytest.approx(125.5)
    assert by_id['rd33mk']['max_tsl_kN'] == pytest.approx(88.2)
    assert by_id['m88']['max_tsl_kN'] == pytest.approx(75.0)
    assert 'max_tsl_kN' not in by_id['f402']
    assert by_id['j52']['max_tsl_kN'] == pytest.approx(41.4)
    assert by_id['tf41']['bpr'] == pytest.approx(0.77)
    assert by_id['tf41']['max_tsl_kN'] == pytest.approx(66.7)
    assert by_id['tf34']['bpr'] == pytest.approx(6.20)
    assert by_id['tf34']['tsl_kN'] == pytest.approx(41.3)
    assert by_id['j57']['tsl_kN'] == pytest.approx(46.7)
    assert by_id['j57']['max_tsl_kN'] == pytest.approx(55.2)
    assert by_id['j79']['tsl_kN'] == pytest.approx(48.5)
    assert by_id['j79']['max_tsl_kN'] == pytest.approx(75.6)
    assert by_id['f100']['max_tsl_kN'] == pytest.approx(105.7)
    assert by_id['f110ge129']['max_tsl_kN'] == pytest.approx(131.2)
    assert by_id['ej200']['max_tsl_kN'] == pytest.approx(90.0)
    assert by_id['rm12']['max_tsl_kN'] == pytest.approx(80.5)
    assert by_id['f125']['max_tsl_kN'] == pytest.approx(42.1)
    assert by_id['rd93']['max_tsl_kN'] == pytest.approx(91.2)
    assert by_id['f404in20']['max_tsl_kN'] == pytest.approx(85.0)
    assert by_id['al41f1']['tsl_kN'] == pytest.approx(88.3)
    assert by_id['al41f1']['max_tsl_kN'] == pytest.approx(142.2)
    assert by_id['al51f1']['tsl_kN'] == pytest.approx(107.9)
    assert by_id['al51f1']['max_tsl_kN'] == pytest.approx(161.9)


def test_combat_radius_csv_missing_nation_raises(tmp_path):
    path = tmp_path / 'cr.csv'
    path.write_text(_unified_csv_text([_valid_land_row(nation='')]), encoding='utf-8')
    with pytest.raises(ValueError, match='nation'):
        load_combat_radius_aircraft_csv(path)


def test_combat_radius_engine_csv_missing_nation_raises(tmp_path):
    path = tmp_path / 'eng.csv'
    path.write_text(
        ','.join(COMBAT_RADIUS_ENGINE_CSV_COLUMNS) + '\n'
        'x,涡扇,,0.3,26,1800,100,,1,测\n',
        encoding='utf-8',
    )
    with pytest.raises(ValueError, match='nation'):
        load_combat_radius_engine_csv(path)


def test_takeoff_cd0_matches_lift_drag_estimate():
    """舰载机 CD0 须与作战半径升阻比模型一致（CSV 留空时）。"""
    from utils.combat_radius.lift_drag import aircraft_from_dict, estimate_takeoff_cd0

    aircraft = load_aircraft_csv(AIRCRAFT_CSV)
    rows = _read_unified_aircraft_rows(AIRCRAFT_CSV)
    j15_row = next(r for r in rows if r['id'].strip() == 'J-15')
    j15_cr = _combat_radius_item_from_row(j15_row, AIRCRAFT_CSV)
    expected = estimate_takeoff_cd0(aircraft_from_dict(j15_cr))
    assert aircraft['J-15'].cd0 == pytest.approx(expected)
    f35c = next(r for r in load_combat_radius_aircraft_csv(COMBAT_RADIUS_AIRCRAFT_CSV) if r['id'] == 'F-35C')
    assert aircraft['F-35C'].cd0 == pytest.approx(
        estimate_takeoff_cd0(aircraft_from_dict(f35c))
    )


def test_combat_radius_engine_csv_empty_raises(tmp_path):
    path = tmp_path / 'eng.csv'
    path.write_text(','.join(COMBAT_RADIUS_ENGINE_CSV_COLUMNS) + '\n', encoding='utf-8')
    with pytest.raises(ValueError, match='未读到'):
        load_combat_radius_engine_csv(path)


def test_combat_radius_engine_csv_invalid_install_mult_raises(tmp_path):
    path = tmp_path / 'eng.csv'
    path.write_text(
        ','.join(COMBAT_RADIUS_ENGINE_CSV_COLUMNS) + '\n'
        'x,涡扇,中国,0.3,26,1800,100,,0,测\n',
        encoding='utf-8',
    )
    with pytest.raises(ValueError, match='tsfc_install_mult'):
        load_combat_radius_engine_csv(path)


def test_combat_radius_engine_csv_missing_column_raises(tmp_path):
    path = tmp_path / 'eng.csv'
    path.write_text('id,name,nation\nx,涡扇,中国\n', encoding='utf-8')
    with pytest.raises(ValueError, match='缺少列'):
        load_combat_radius_engine_csv(path)


def test_unified_csv_shared_between_takeoff_and_combat_radius():
    """两套仿真须读同一机型库文件。"""
    from utils.paths import AIRCRAFT_CSV as takeoff_path

    assert COMBAT_RADIUS_AIRCRAFT_CSV == takeoff_path
    assert COMBAT_RADIUS_AIRCRAFT_CSV_COLUMNS == AIRCRAFT_CSV_COLUMNS
    assert 'fuse_width_m' in AIRCRAFT_CSV_COLUMNS
    assert 'fuse_height_m' in AIRCRAFT_CSV_COLUMNS
    assert 'nose_cone_length_m' in AIRCRAFT_CSV_COLUMNS
    assert 'main_wing_area_m2' in AIRCRAFT_CSV_COLUMNS
    assert 'canard_htail_area_m2' in AIRCRAFT_CSV_COLUMNS
    assert 'ventral_fin_area_m2' in AIRCRAFT_CSV_COLUMNS
    assert 'vtail_area_m2' in AIRCRAFT_CSV_COLUMNS
    assert 'store_mount' in AIRCRAFT_CSV_COLUMNS


def test_read_unified_aircraft_rows_and_item(tmp_path):
    path = tmp_path / 'u.csv'
    path.write_text(_unified_csv_text([_valid_land_row(id='L1', name='陆基机')]), encoding='utf-8')
    rows = _read_unified_aircraft_rows(path)
    assert len(rows) == 1
    item = _combat_radius_item_from_row(rows[0], path)
    assert item['id'] == 'L1'
    assert item['carrier'] is False
    assert item['AR'] == 2.5
    cd0 = _estimate_cd0_for_item(item)
    assert 0.01 < cd0 < 0.08


def test_read_unified_aircraft_rows_missing_header_and_columns(tmp_path):
    empty = tmp_path / 'empty.csv'
    empty.write_text('', encoding='utf-8')
    with pytest.raises(ValueError, match='表头'):
        _read_unified_aircraft_rows(empty)
    thin = tmp_path / 'thin.csv'
    thin.write_text('id,name\nX,测\n', encoding='utf-8')
    with pytest.raises(ValueError, match='缺少列'):
        _read_unified_aircraft_rows(thin)


def test_load_aircraft_csv_skips_land_only_file(tmp_path):
    path = tmp_path / 'land.csv'
    path.write_text(_unified_csv_text([_valid_land_row()]), encoding='utf-8')
    with pytest.raises(ValueError, match='起飞仿真'):
        load_aircraft_csv(path)


def test_load_aircraft_csv_includes_land_with_takeoff_fields(tmp_path):
    """陆基机只要填写起飞字段即可进入滑跃仿真。"""
    path = tmp_path / 'land_to.csv'
    row = _valid_land_row(
        id='L1', name='陆基滑跃测试', carrier='0',
        mtow_kg='19000', max_payload_kg='5000', wing_height_m='1.7',
        t_max_sl_n='140000',
    )
    path.write_text(_unified_csv_text([row]), encoding='utf-8')
    ac = load_aircraft_csv(path)['L1']
    assert ac.mtow_kg == pytest.approx(19000)
    assert ac.t_max_sl_n == pytest.approx(140000)


def test_load_aircraft_csv_estimates_cd0_for_carrier(tmp_path):
    path = tmp_path / 'cv.csv'
    row = _valid_land_row(
        id='C1', name='舰载测试', carrier='1',
        mtow_kg='20000', max_payload_kg='4000', wing_height_m='2.0',
        t_max_sl_n='120000',
    )
    path.write_text(_unified_csv_text([row]), encoding='utf-8')
    ac = load_aircraft_csv(path)['C1']
    assert ac.sweep_le_deg == pytest.approx(30.0)
    assert 0.01 < ac.cd0 < 0.08
    assert ac.n_pilots == 1


def test_load_aircraft_csv_carrier_missing_type_label_raises(tmp_path):
    path = tmp_path / 'bad.csv'
    row = _valid_land_row(
        id='C1', name='舰载测试', carrier='1', type_label='',
        mtow_kg='20000', max_payload_kg='4000', wing_height_m='2.0',
    )
    path.write_text(_unified_csv_text([row]), encoding='utf-8')
    with pytest.raises(ValueError, match='type_label'):
        load_aircraft_csv(path)


def test_export_aircraft_csv_preserves_geometry(tmp_path):
    src = tmp_path / 'src.csv'
    src.write_text(_unified_csv_text([
        _valid_land_row(
            id='C1', name='舰载测试', carrier='1',
            mtow_kg='20000', max_payload_kg='4000', wing_height_m='2.0',
            t_max_sl_n='120000', AR='2.7',
            **_wetted_fields(),
        ),
    ]), encoding='utf-8')
    aircraft = load_aircraft_csv(src)
    out = tmp_path / 'out.csv'
    out.write_text(src.read_text(encoding='utf-8'), encoding='utf-8')
    export_aircraft_csv(out, aircraft)
    items = load_combat_radius_aircraft_csv(out)
    assert items[0]['AR'] == pytest.approx(2.7)
    assert items[0]['carrier'] is True
