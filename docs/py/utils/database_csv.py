"""舰载机 / 航母参数库 CSV 导入导出（UTF-8 BOM，便于 Excel 打开中文）。"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from utils.specs import AircraftSpec, CarrierSpec

# 统一机型库：作战半径几何 + 起飞字段；填写 mtow_kg 才进入起飞仿真（陆基机也可做滑跃假设）
AIRCRAFT_CSV_COLUMNS = (
    'id', 'name', 'nation', 'carrier', 'type_label',
    'AR', 'sweep_deg', 'sweep_inner_deg', 'sweep_outer_deg', 'sweep_kink_span_frac',
    'wing_loading', 'tc', 'mach', 'alt_m',
    'planform', 'layout', 'bwb', 'rough', 'inlet', 'store_mount', 'ld_known', 'notes',
    'wing_area_m2', 'mach_angle_deg', 'bvr_missile', 'length_m', 'wingspan_m',
    'fuse_width_m', 'fuse_height_m',
    'nose_cone_length_m', 'nose_cone_diameter_m', 'nose_length_m', 'nose_root_diameter_m',
    'fuse_body_length_m', 'main_wing_area_m2', 'canard_htail_area_m2', 'ventral_fin_area_m2',
    'vtail_area_m2',
    'empty_kg', 'internal_fuel_kg', 'n_pilots', 'missile_mass_kg', 'n_engines', 'engine_id',
    'mtow_kg', 'max_payload_kg', 'wing_height_m', 'cd0',
    't_max_sl_n', 't_main_stovl_sl_n', 't_liftfan_sl_n', 't_rollposts_sl_n',
    'exhaust_mdot_kg_s', 'exhaust_d0_m', 'exhaust_height_m',
    'shaft_power_sl_w', 'prop_diameter_m', 'nacelle_blockage_frac',
)

# 兼容旧名：作战半径从统一库抽取这些字段
COMBAT_RADIUS_AIRCRAFT_CSV_COLUMNS = AIRCRAFT_CSV_COLUMNS

CARRIERS_CSV_COLUMNS = (
    'id', 'name', 'nation', 'max_speed_kt', 'ski_jump', 'total_deck_length_m',
    'ski_jump_angle_deg', 'ski_jump_height_m', 'f35b_capable', 'deck_length_source', 'notes',
)

# 饱和打击导弹库（反舰弹 / 防空弹）
MISSILE_INTERCEPTION_MISSILE_CSV_COLUMNS = (
    'category', 'id', 'name', 'nation',
    'vm_ma', 'rcs_m2', 'traj', 'maneuver_class',
    'vi_ma', 'dia_m', 'guidance', 'range_km', 'max_alt_km',
    'notes',
)

# 饱和打击雷达库（预警机 / 舰载雷达）
MISSILE_INTERCEPTION_RADAR_CSV_COLUMNS = (
    'category', 'id', 'name', 'nation',
    'area_m2', 'radar_type', 'standoff_km',
    'notes',
)

MISSILE_INTERCEPTION_MISSILE_CATEGORIES = ('asm', 'sam')
MISSILE_INTERCEPTION_RADAR_CATEGORIES = ('aew', 'ship')
MISSILE_INTERCEPTION_CATEGORIES = ('asm', 'aew', 'ship', 'sam')

COMBAT_RADIUS_ENGINE_CSV_COLUMNS = (
    'id', 'name', 'nation', 'bpr', 'opr', 't4_K', 'tsl_kN', 'max_tsl_kN',
    'tsfc_install_mult', 'notes',
)

def _cell_str(value: Any) -> str:
    if value is None:
        return ''
    if isinstance(value, bool):
        return '1' if value else '0'
    return str(value)


def _parse_bool(raw: str) -> bool:
    text = raw.strip().lower()
    if text in ('1', 'true', 'yes', 'y', '是'):
        return True
    if text in ('0', 'false', 'no', 'n', '否', ''):
        return False
    raise ValueError(f'无法解析布尔值: {raw!r}')


def _parse_optional_float(raw: str) -> float | None:
    """解析可选浮点；空白视为未填写并返回 None。"""
    text = raw.strip()
    if not text:
        return None
    return float(text)


def _parse_float(raw: str, field: str) -> float:
    """解析必填浮点。"""
    text = raw.strip()
    if not text:
        raise ValueError(f'缺少必填数值字段 {field}')
    return float(text)


def _parse_int(raw: str, field: str) -> int:
    """解析必填整数（允许 1.0 这种浮点写法）。"""
    return int(_parse_float(raw, field))


def _parse_nation(row: dict[str, str], path: Path, item_id: str) -> str:
    """读取国别列；两级（国别 → 型号）选择器依赖该列，故要求非空。"""
    nation = (row.get('nation') or '').strip()
    if not nation:
        raise ValueError(f'{path} 记录 {item_id} 缺少 nation（国别）')
    return nation


def export_aircraft_csv(path: str | Path, aircraft: dict[str, 'AircraftSpec']) -> None:
    """写回起飞字段；若目标文件已是统一库，则保留作战半径几何列。"""
    path = Path(path)
    existing: dict[str, dict[str, str]] = {}
    if path.is_file():
        with path.open('r', encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f)
            if reader.fieldnames and set(AIRCRAFT_CSV_COLUMNS) <= set(reader.fieldnames):
                for row in reader:
                    rid = (row.get('id') or '').strip()
                    if rid:
                        existing[rid] = dict(row)
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=AIRCRAFT_CSV_COLUMNS)
        writer.writeheader()
        for ac in aircraft.values():
            row = dict(existing.get(ac.id, {}))
            row.update({
                'id': ac.id,
                'name': ac.name,
                'type_label': ac.type_label,
                'empty_kg': _cell_str(ac.empty_kg),
                'internal_fuel_kg': _cell_str(ac.internal_fuel_kg),
                'bvr_missile': ac.bvr_missile,
                'missile_mass_kg': _cell_str(ac.missile_mass_kg),
                'sweep_deg': _cell_str(ac.sweep_le_deg),
                'wingspan_m': _cell_str(ac.wingspan_m),
                'wing_area_m2': _cell_str(ac.wing_area_m2),
                'wing_height_m': _cell_str(ac.wing_height_m),
                'cd0': _cell_str(ac.cd0),
                't_max_sl_n': _cell_str(ac.t_max_sl_n),
                't_main_stovl_sl_n': _cell_str(ac.t_main_stovl_sl_n),
                't_liftfan_sl_n': _cell_str(ac.t_liftfan_sl_n),
                't_rollposts_sl_n': _cell_str(ac.t_rollposts_sl_n),
                'exhaust_mdot_kg_s': _cell_str(ac.exhaust_mdot_kg_s),
                'exhaust_d0_m': _cell_str(ac.exhaust_d0_m),
                'exhaust_height_m': _cell_str(ac.exhaust_height_m),
                'shaft_power_sl_w': _cell_str(ac.shaft_power_sl_w),
                'prop_diameter_m': _cell_str(ac.prop_diameter_m),
                'nacelle_blockage_frac': _cell_str(ac.nacelle_blockage_frac),
                'n_pilots': _cell_str(ac.n_pilots),
                'mtow_kg': _cell_str(ac.mtow_kg),
                'max_payload_kg': _cell_str(ac.max_payload_kg),
                'notes': ac.notes,
                'carrier': row.get('carrier') or '1',
            })
            writer.writerow({col: row.get(col, '') for col in AIRCRAFT_CSV_COLUMNS})


def export_carriers_csv(path: str | Path, carriers: list['CarrierSpec']) -> None:
    path = Path(path)
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=CARRIERS_CSV_COLUMNS)
        writer.writeheader()
        for c in carriers:
            writer.writerow({col: _cell_str(getattr(c, col)) for col in CARRIERS_CSV_COLUMNS})


def _read_unified_aircraft_rows(path: Path) -> list[dict[str, str]]:
    """读取统一机型库原始行；校验表头。"""
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f'{path} 缺少表头')
        missing = [c for c in AIRCRAFT_CSV_COLUMNS if c not in reader.fieldnames]
        if missing:
            raise ValueError(f'{path} 缺少列: {missing}')
        return [row for row in reader if (row.get('id') or '').strip() and (row.get('name') or '').strip()]


def _combat_radius_item_from_row(row: dict[str, str], csv_path: Path) -> dict[str, Any]:
    """统一库一行 → 作战半径预设字典。"""
    from utils.combat_radius.lift_drag import LAYOUT_MULT, PLANFORM_MULT, parse_inlet, parse_store_mount

    item_id = (row.get('id') or '').strip()
    planform = (row.get('planform') or '').strip()
    layout = (row.get('layout') or '').strip()
    if planform not in PLANFORM_MULT:
        raise ValueError(f'{csv_path} 记录 {item_id} 未知 planform={planform!r}')
    if layout not in LAYOUT_MULT:
        raise ValueError(f'{csv_path} 记录 {item_id} 未知 layout={layout!r}')
    try:
        inlet = parse_inlet(row.get('inlet'))
    except ValueError as exc:
        raise ValueError(f'{csv_path} 记录 {item_id} {exc}') from exc
    try:
        store_mount = parse_store_mount(row.get('store_mount'))
    except ValueError as exc:
        raise ValueError(f'{csv_path} 记录 {item_id} {exc}') from exc
    item: dict[str, Any] = {
        'id': item_id,
        'name': (row.get('name') or '').strip(),
        'nation': _parse_nation(row, csv_path, item_id),
        'carrier': _parse_bool(row.get('carrier') or '0'),
        'AR': _parse_float(row.get('AR') or '', 'AR'),
        'sweep_deg': _parse_float(row.get('sweep_deg') or '', 'sweep_deg'),
        'wing_loading': _parse_float(row.get('wing_loading') or '', 'wing_loading'),
        'tc': _parse_float(row.get('tc') or '', 'tc'),
        'mach': _parse_float(row.get('mach') or '', 'mach'),
        'alt_m': _parse_float(row.get('alt_m') or '', 'alt_m'),
        'planform': planform,
        'layout': layout,
        'bwb': _parse_bool(row.get('bwb') or '0'),
        'rough': _parse_bool(row.get('rough') or '0'),
        'inlet': inlet,
        'store_mount': store_mount,
        'empty_kg': _parse_float(row.get('empty_kg') or '', 'empty_kg'),
        'internal_fuel_kg': _parse_float(row.get('internal_fuel_kg') or '', 'internal_fuel_kg'),
        'n_pilots': _parse_int(row.get('n_pilots') or '', 'n_pilots'),
        'missile_mass_kg': _parse_float(row.get('missile_mass_kg') or '', 'missile_mass_kg'),
        'n_engines': _parse_int(row.get('n_engines') or '', 'n_engines'),
    }
    ld_known = _parse_optional_float(row.get('ld_known') or '')
    if ld_known is not None:
        item['ld_known'] = ld_known
    notes = (row.get('notes') or '').strip()
    if notes:
        item['notes'] = notes
    for key in (
        'wing_area_m2', 'mach_angle_deg', 'length_m', 'wingspan_m',
        'fuse_width_m', 'fuse_height_m',
        'nose_cone_length_m', 'nose_cone_diameter_m', 'nose_length_m', 'nose_root_diameter_m',
        'fuse_body_length_m', 'main_wing_area_m2', 'canard_htail_area_m2', 'ventral_fin_area_m2',
        'vtail_area_m2',
        'sweep_inner_deg', 'sweep_outer_deg', 'sweep_kink_span_frac',
    ):
        value = _parse_optional_float(row.get(key) or '')
        if value is not None:
            item[key] = value
    bvr = (row.get('bvr_missile') or '').strip()
    if bvr:
        item['bvr_missile'] = bvr
    engine_id = (row.get('engine_id') or '').strip()
    if engine_id:
        item['engine_id'] = engine_id
    type_label = (row.get('type_label') or '').strip()
    if type_label:
        item['type_label'] = type_label
    return item


def _estimate_cd0_for_item(item: dict[str, Any]) -> float:
    """用作战半径升阻比模型估算起飞 CD0。"""
    from utils.combat_radius.lift_drag import aircraft_from_dict, estimate_takeoff_cd0

    return estimate_takeoff_cd0(aircraft_from_dict(item))


def _row_has_takeoff_spec(row: dict[str, str]) -> bool:
    """是否具备起飞仿真必填字段（填写最大起飞重量即视为可上舰仿真）。"""
    return _parse_optional_float(row.get('mtow_kg') or '') is not None


def load_aircraft_csv(path: str | Path) -> dict[str, 'AircraftSpec']:
    """加载统一机型库中填写了起飞字段的机型，供起飞仿真使用。

    陆基机（carrier=0）只要填了 mtow_kg 等起飞字段，也可进入滑跃/短距仿真。
    """
    from utils.specs import AircraftSpec

    csv_path = Path(path)
    rows = _read_unified_aircraft_rows(csv_path)
    aircraft: dict[str, AircraftSpec] = {}
    for row in rows:
        if not _row_has_takeoff_spec(row):
            continue
        ac_id = row['id'].strip()
        cr_item = _combat_radius_item_from_row(row, csv_path)
        cd0_override = _parse_optional_float(row.get('cd0') or '')
        cd0 = cd0_override if cd0_override is not None else _estimate_cd0_for_item(cr_item)
        type_label = (row.get('type_label') or '').strip()
        if not type_label:
            raise ValueError(f'{csv_path} 起飞机型 {ac_id} 缺少 type_label')
        aircraft[ac_id] = AircraftSpec(
            id=ac_id,
            name=row['name'].strip(),
            type_label=type_label,
            mtow_kg=_parse_float(row.get('mtow_kg') or '', 'mtow_kg'),
            empty_kg=cr_item['empty_kg'],
            internal_fuel_kg=cr_item['internal_fuel_kg'],
            max_payload_kg=_parse_float(row.get('max_payload_kg') or '', 'max_payload_kg'),
            bvr_missile=(row.get('bvr_missile') or '').strip(),
            missile_mass_kg=cr_item['missile_mass_kg'],
            sweep_le_deg=cr_item['sweep_deg'],
            wingspan_m=_parse_float(row.get('wingspan_m') or '', 'wingspan_m'),
            wing_area_m2=_parse_float(row.get('wing_area_m2') or '', 'wing_area_m2'),
            wing_height_m=_parse_float(row.get('wing_height_m') or '', 'wing_height_m'),
            cd0=cd0,
            t_max_sl_n=_parse_optional_float(row.get('t_max_sl_n') or ''),
            t_main_stovl_sl_n=_parse_optional_float(row.get('t_main_stovl_sl_n') or ''),
            t_liftfan_sl_n=_parse_optional_float(row.get('t_liftfan_sl_n') or ''),
            t_rollposts_sl_n=_parse_optional_float(row.get('t_rollposts_sl_n') or ''),
            exhaust_mdot_kg_s=_parse_optional_float(row.get('exhaust_mdot_kg_s') or ''),
            exhaust_d0_m=_parse_optional_float(row.get('exhaust_d0_m') or ''),
            exhaust_height_m=_parse_optional_float(row.get('exhaust_height_m') or ''),
            shaft_power_sl_w=_parse_optional_float(row.get('shaft_power_sl_w') or ''),
            prop_diameter_m=_parse_optional_float(row.get('prop_diameter_m') or ''),
            nacelle_blockage_frac=_parse_optional_float(row.get('nacelle_blockage_frac') or ''),
            n_pilots=cr_item['n_pilots'],
            notes=(row.get('notes') or '').strip(),
            layout=cr_item['layout'],
            canard_htail_area_m2=_parse_optional_float(row.get('canard_htail_area_m2') or ''),
        )
    if not aircraft:
        raise ValueError(f'{csv_path} 未读到有效起飞仿真记录（须填写 mtow_kg）')
    return aircraft


def load_carriers_csv(path: str | Path) -> list['CarrierSpec']:
    from utils.specs import CarrierSpec

    path = Path(path)
    carriers: list[CarrierSpec] = []
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f'{path} 缺少表头')
        missing = [c for c in CARRIERS_CSV_COLUMNS if c not in reader.fieldnames]
        if missing:
            raise ValueError(f'{path} 缺少列: {missing}')
        for row in reader:
            if not row.get('id', '').strip():
                continue
            carriers.append(CarrierSpec(
                id=row['id'].strip(),
                name=row['name'].strip(),
                nation=row['nation'].strip(),
                max_speed_kt=_parse_float(row['max_speed_kt'], 'max_speed_kt'),
                ski_jump=_parse_bool(row['ski_jump']),
                total_deck_length_m=_parse_float(row['total_deck_length_m'], 'total_deck_length_m'),
                ski_jump_angle_deg=_parse_float(row.get('ski_jump_angle_deg') or '0', 'ski_jump_angle_deg'),
                ski_jump_height_m=_parse_optional_float(row.get('ski_jump_height_m', '')),
                f35b_capable=_parse_bool(row['f35b_capable']),
                deck_length_source=row.get('deck_length_source', '').strip(),
                notes=row.get('notes', '').strip(),
            ))
    if not carriers:
        raise ValueError(f'{path} 未读到有效航母记录')
    return carriers


def load_missile_interception_missile_csv(path: str | Path) -> dict[str, list[dict[str, Any]]]:
    """从导弹库 CSV 加载反舰弹 / 防空弹预设。

    返回 {'asm': [...], 'sam': [...]}；字段名与前端契约对齐（vm/rcs/traj/vi/dia/range）。
    """
    path = Path(path)
    grouped: dict[str, list[dict[str, Any]]] = {k: [] for k in MISSILE_INTERCEPTION_MISSILE_CATEGORIES}
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f'{path} 缺少表头')
        missing = [c for c in MISSILE_INTERCEPTION_MISSILE_CSV_COLUMNS if c not in reader.fieldnames]
        if missing:
            raise ValueError(f'{path} 缺少列: {missing}')
        for row in reader:
            cat = (row.get('category') or '').strip().lower()
            item_id = (row.get('id') or '').strip()
            name = (row.get('name') or '').strip()
            if not cat or not item_id or not name:
                continue
            if cat not in grouped:
                raise ValueError(f'{path} 未知 category={cat!r}（id={item_id}；导弹库仅允许 asm/sam）')
            item: dict[str, Any] = {
                'id': item_id, 'name': name, 'nation': _parse_nation(row, path, item_id),
            }
            notes = (row.get('notes') or '').strip()
            if notes:
                item['notes'] = notes
            if cat == 'asm':
                item['vm'] = _parse_float(row.get('vm_ma') or '', 'vm_ma')
                item['rcs'] = _parse_float(row.get('rcs_m2') or '', 'rcs_m2')
                traj = (row.get('traj') or '').strip()
                from utils.missile_interception.missile_interception_config import valid_traj_ids
                allowed = valid_traj_ids()
                if traj not in allowed:
                    raise ValueError(
                        f'{path} asm {item_id} traj 须为 {"|".join(sorted(allowed))} 之一，得到 {traj!r}'
                    )
                item['traj'] = traj
                mclass = (row.get('maneuver_class') or '').strip()
                if mclass:
                    item['maneuver_class'] = mclass
            else:  # sam
                item['vi'] = _parse_float(row.get('vi_ma') or '', 'vi_ma')
                item['dia'] = _parse_float(row.get('dia_m') or '', 'dia_m')
                item['guidance'] = (row.get('guidance') or '').strip()
                item['range'] = _parse_float(row.get('range_km') or '', 'range_km')
                max_alt = _parse_optional_float(row.get('max_alt_km') or '')
                if max_alt is not None:
                    item['max_alt'] = max_alt
            grouped[cat].append(item)
    for cat in MISSILE_INTERCEPTION_MISSILE_CATEGORIES:
        if not grouped[cat]:
            raise ValueError(f'{path} 类别 {cat} 无有效记录')
    return grouped


def load_missile_interception_radar_csv(path: str | Path) -> dict[str, list[dict[str, Any]]]:
    """从雷达库 CSV 加载预警机 / 舰载雷达预设。

    返回 {'aew': [...], 'ship': [...]}；字段名与前端契约对齐（area/type/standoff）。
    """
    path = Path(path)
    grouped: dict[str, list[dict[str, Any]]] = {k: [] for k in MISSILE_INTERCEPTION_RADAR_CATEGORIES}
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f'{path} 缺少表头')
        missing = [c for c in MISSILE_INTERCEPTION_RADAR_CSV_COLUMNS if c not in reader.fieldnames]
        if missing:
            raise ValueError(f'{path} 缺少列: {missing}')
        for row in reader:
            cat = (row.get('category') or '').strip().lower()
            item_id = (row.get('id') or '').strip()
            name = (row.get('name') or '').strip()
            if not cat or not item_id or not name:
                continue
            if cat not in grouped:
                raise ValueError(f'{path} 未知 category={cat!r}（id={item_id}；雷达库仅允许 aew/ship）')
            item: dict[str, Any] = {
                'id': item_id, 'name': name, 'nation': _parse_nation(row, path, item_id),
            }
            notes = (row.get('notes') or '').strip()
            if notes:
                item['notes'] = notes
            item['area'] = _parse_float(row.get('area_m2') or '', 'area_m2')
            item['type'] = (row.get('radar_type') or '').strip()
            if cat == 'aew':
                item['standoff'] = _parse_float(row.get('standoff_km') or '', 'standoff_km')
            grouped[cat].append(item)
    for cat in MISSILE_INTERCEPTION_RADAR_CATEGORIES:
        if not grouped[cat]:
            raise ValueError(f'{path} 类别 {cat} 无有效记录')
    return grouped


def load_missile_interception_presets_csv(
    missile_path: str | Path | None = None,
    radar_path: str | Path | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """合并导弹库与雷达库，返回四类预设（与前端 missile_interception_presets 一致）。"""
    from utils.paths import MISSILE_INTERCEPTION_MISSILE_CSV, MISSILE_INTERCEPTION_RADAR_CSV

    m_path = Path(missile_path) if missile_path is not None else MISSILE_INTERCEPTION_MISSILE_CSV
    r_path = Path(radar_path) if radar_path is not None else MISSILE_INTERCEPTION_RADAR_CSV
    missiles = load_missile_interception_missile_csv(m_path)
    radars = load_missile_interception_radar_csv(r_path)
    return {
        'asm': missiles['asm'],
        'aew': radars['aew'],
        'ship': radars['ship'],
        'sam': missiles['sam'],
    }


def load_combat_radius_aircraft_csv(path: str | Path | None = None) -> list[dict[str, Any]]:
    """从统一机型库加载作战半径预设（仅含完整分段浸润几何的机型）。"""
    from utils.combat_radius.lift_drag import has_geometric_wetted_dict
    from utils.paths import COMBAT_RADIUS_AIRCRAFT_CSV

    csv_path = Path(path) if path is not None else COMBAT_RADIUS_AIRCRAFT_CSV
    items = [_combat_radius_item_from_row(row, csv_path) for row in _read_unified_aircraft_rows(csv_path)]
    items = [item for item in items if has_geometric_wetted_dict(item)]
    if not items:
        raise ValueError(f'{csv_path} 未读到有效作战半径机型记录')
    return items


def load_combat_radius_engine_csv(path: str | Path | None = None) -> list[dict[str, Any]]:
    """加载作战半径发动机预设（涵道比/总压比/T4/海平面军推）。"""
    from utils.paths import COMBAT_RADIUS_ENGINE_CSV

    csv_path = Path(path) if path is not None else COMBAT_RADIUS_ENGINE_CSV
    rows: list[dict[str, Any]] = []
    with csv_path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f'{csv_path} 缺少表头')
        missing = [c for c in COMBAT_RADIUS_ENGINE_CSV_COLUMNS if c not in reader.fieldnames]
        if missing:
            raise ValueError(f'{csv_path} 缺少列: {missing}')
        for row in reader:
            item_id = (row.get('id') or '').strip()
            name = (row.get('name') or '').strip()
            if not item_id or not name:
                continue
            item: dict[str, Any] = {
                'id': item_id,
                'name': name,
                'nation': _parse_nation(row, csv_path, item_id),
                'bpr': _parse_float(row.get('bpr') or '', 'bpr'),
                'opr': _parse_float(row.get('opr') or '', 'opr'),
                't4_K': _parse_float(row.get('t4_K') or '', 't4_K'),
            }
            tsl = _parse_optional_float(row.get('tsl_kN') or '')
            if tsl is not None:
                item['tsl_kN'] = tsl
            max_tsl = _parse_optional_float(row.get('max_tsl_kN') or '')
            if max_tsl is not None:
                item['max_tsl_kN'] = max_tsl
            raw_install = (row.get('tsfc_install_mult') or '').strip()
            install_mult = float(raw_install) if raw_install else 1.0
            if install_mult <= 0:
                raise ValueError(f'{csv_path} {item_id}: tsfc_install_mult 须为正')
            item['tsfc_install_mult'] = install_mult
            notes = (row.get('notes') or '').strip()
            if notes:
                item['notes'] = notes
            rows.append(item)
    if not rows:
        raise ValueError(f'{csv_path} 未读到有效发动机记录')
    return rows


def list_model_ids_from_missile_interception_csv(
    missile_path: str | Path | None = None,
    radar_path: str | Path | None = None,
) -> dict[str, list[str]]:
    """列出导弹库 + 雷达库中各类装备 id（供前端/测试断言「自动识别型号」）。"""
    data = load_missile_interception_presets_csv(missile_path, radar_path)
    return {cat: [x['id'] for x in items] for cat, items in data.items()}
