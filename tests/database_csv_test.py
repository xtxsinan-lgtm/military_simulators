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
    """起飞仿真只加载 carrier=1 的舰载机。"""
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
    assert '53636N' in aircraft
    assert 'F-22' not in aircraft
    assert 'J-20' not in aircraft
    assert 'J-50' not in aircraft
    assert 'F-35A' not in aircraft
    assert all(ac.cd0 > 0 for ac in aircraft.values())


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
        'layout': 'conventional', 'bwb': '0', 'rough': '0',
        'wing_area_m2': '60', 'wingspan_m': '13',
        'empty_kg': '15000', 'internal_fuel_kg': '8000',
        'n_pilots': '1', 'missile_mass_kg': '150', 'n_engines': '1',
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
    """作战半径机型 CSV 须含锚点与扩充机型，且列齐全。"""
    rows = load_combat_radius_aircraft_csv(COMBAT_RADIUS_AIRCRAFT_CSV)
    ids = [r['id'] for r in rows]
    assert ids[:12] == [
        'F-35C', 'F-22', 'F-35A', 'J-20', 'J-50', 'J-50N', 'J-36',
        'J-35', 'J-35A', '53636', '53636N', '53536',
    ]
    assert 'J-15' in ids
    assert 'F-35B' in ids
    assert rows[0]['carrier'] is True
    assert next(r for r in rows if r['id'] == 'F-22')['carrier'] is False
    assert rows[0]['rough'] is True
    f22 = next(r for r in rows if r['id'] == 'F-22')
    j20 = next(r for r in rows if r['id'] == 'J-20')
    assert 'ld_known' not in j20
    assert f22['empty_kg'] == 19800
    assert f22['n_engines'] == 2
    assert f22['engine_id'] == 'f119'
    assert f22['mach_angle_deg'] == pytest.approx(28.5)
    assert f22['wing_area_m2'] == pytest.approx(78.0)
    assert rows[0]['n_engines'] == 1
    uav = next(r for r in rows if r['id'] == '53636')
    assert uav['n_pilots'] == 0
    j36 = next(r for r in rows if r['id'] == 'J-36')
    assert j36['n_engines'] == 3
    assert j36['n_pilots'] == 2
    assert j36['planform'] == 'double_delta'
    j35 = next(r for r in rows if r['id'] == 'J-35')
    assert j35['length_m'] == pytest.approx(17.3)
    assert j35['carrier'] is True


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


def test_combat_radius_csv_empty_raises(tmp_path):
    path = tmp_path / 'cr.csv'
    path.write_text(_unified_csv_text([]), encoding='utf-8')
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
    assert by_id['f135']['t4_K'] == 2260.0
    assert 'tsl_kN' not in by_id['ws15']
    assert by_id['f414']['bpr'] == pytest.approx(0.40)
    assert by_id['ws10h']['tsl_kN'] == 89.0


def test_combat_radius_engine_csv_empty_raises(tmp_path):
    path = tmp_path / 'eng.csv'
    path.write_text(','.join(COMBAT_RADIUS_ENGINE_CSV_COLUMNS) + '\n', encoding='utf-8')
    with pytest.raises(ValueError, match='未读到'):
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
    with pytest.raises(ValueError, match='舰载机'):
        load_aircraft_csv(path)


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
        ),
    ]), encoding='utf-8')
    aircraft = load_aircraft_csv(src)
    out = tmp_path / 'out.csv'
    out.write_text(src.read_text(encoding='utf-8'), encoding='utf-8')
    export_aircraft_csv(out, aircraft)
    items = load_combat_radius_aircraft_csv(out)
    assert items[0]['AR'] == pytest.approx(2.7)
    assert items[0]['carrier'] is True
