"""舰载机 / 航母参数库 CSV 导入导出（UTF-8 BOM，便于 Excel 打开中文）。"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from utils.specs import AircraftSpec, CarrierSpec

# 统一机型库：作战半径几何 + 起飞字段；填写 mtow_kg 才进入起飞仿真（陆基机也可做滑跃假设）
AIRCRAFT_CSV_COLUMNS = (
    'id', 'name', 'nation', 'carrier', 'type_label', 'aircraft_role', 'wing_body_blend',
    'AR', 'sweep_deg', 'sweep_inner_deg', 'sweep_outer_deg', 'sweep_kink_span_frac',
    'wing_loading', 'tc', 'mach', 'alt_m',
    'planform', 'layout', 'rough', 'inlet', 'store_mount', 'ld_known', 'notes',
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

# 导弹射程预设：按速度组展开到各弹种；missile_class 留空表示该弹仓对该速度组全部弹种共用
MISSILE_RANGE_PRESET_CSV_COLUMNS = (
    'speed_group', 'bay', 'length_m', 'diameter_m', 'warhead_kg',
    'v_launch_mach', 'h_launch_km', 'notes', 'missile_class',
)
MISSILE_RANGE_SPEED_GROUPS = ('supersonic', 'subsonic')

# FC-1 外挂弹药目录（store_id 列）
FC1_STORE_CATALOG_CSV_COLUMNS = (
    'store_id', 'name', 'category', 'mass_kg', 'length_m', 'diameter_m', 'notes',
)
AIRCRAFT_STORE_MOUNTS_CSV_COLUMNS = (
    'aircraft_id', 'station_group', 'station_ids', 'group_label',
    'store_id', 'max_qty', 'notes',
)
AIRCRAFT_WEAPON_STATIONS_CSV_COLUMNS = (
    'aircraft_id', 'station_id', 'station_name', 'category', 'weapon_id', 'weapon_name', 'notes',
)
AIRCRAFT_STORES_CSV_COLUMNS = (
    'store_id', 'name_en', 'name_zh', 'category', 'typical_mass_kg', 'notes',
)
AIRCRAFT_HARDPOINTS_CSV_COLUMNS = (
    'aircraft_id', 'station_id', 'name_zh', 'position', 'side', 'max_mass_kg',
    'allowed_stores', 'notes',
)
AIRCRAFT_FIXED_EQUIPMENT_CSV_COLUMNS = (
    'aircraft_id', 'equipment_id', 'name_zh', 'location', 'notes',
)
WEAPON_STORE_CSV_COLUMNS = (
    'id', 'name', 'category', 'mass_kg', 'length_m', 'diameter_m', 'notes',
)
WEAPON_STORE_CATEGORIES = ('a2a', 'pgm', 'battlefield', 'asm', 'aux', 'fixed')
TYPHOON_STORE_STATIONS_CSV_COLUMNS = (
    'station_id', 'name', 'mount', 'position_index', 'notes',
)
TYPHOON_STORE_COMPATIBILITY_CSV_COLUMNS = (
    'station_id', 'weapon_id', 'max_qty', 'notes',
)
TYPHOON_STORE_MOUNTS = ('pylon', 'semi_recessed', 'centerline', 'fixed')

COMBAT_RADIUS_ENGINE_CSV_COLUMNS = (
    'id', 'name', 'nation', 'bpr', 'opr', 't4_K', 'tsl_kN', 'max_tsl_kN',
    'tsfc_install_mult', 'notes',
)

# 飞机挂点挂载：按 station_id 定义可挂载的 store 类型
AIRCRAFT_PYLON_CSV_COLUMNS = (
    'aircraft_id', 'station_id', 'label', 'position', 'symmetric', 'allowed_stores', 'notes',
)
# 挂载设备/弹药类型（与 Saab JAS-39E/F 挂点图分类一致）
STORE_TYPE_LABELS: dict[str, str] = {
    'a2a_ir': '红外制导空空导弹',
    'a2a_radar': '雷达制导空空导弹',
    'anti_ship': '反舰导弹',
    'smart_bomb': '精确制导炸弹',
    'sdb': '小直径炸弹',
    'sdb_alt': '替代型小直径炸弹',
    'fuel_tank': '副油箱',
    'recce_pod': '侦察吊舱',
    'flir_ldp': '前视红外/激光瞄准吊舱',
    'ecm_pod': '电子对抗吊舱',
    'aacmi_pod': 'AACMI 空战训练吊舱',
}
PYLON_POSITION_LABELS: dict[str, str] = {
    'wingtip': '翼尖',
    'outer_wing': '外侧翼下',
    'inner_wing': '内侧翼下',
    'intake_right': '进气道右侧',
    'belly': '机腹',
    'belly_center': '机腹中心',
}

# 阵风挂载模型：挂点定义与挂点-武器兼容表
RAFALE_MOUNT_STATIONS_CSV_COLUMNS = (
    'aircraft_id', 'station_id', 'station_label', 'label_zh', 'side', 'position',
    'store_mount', 'notes',
)
RAFALE_MOUNT_STORES_CSV_COLUMNS = (
    'aircraft_id', 'station_id', 'category', 'category_zh', 'store_id', 'store_name',
)
RAFALE_MOUNT_STORE_MOUNTS = ('pylon', 'semi_recessed', 'mixed', 'pod', 'conformal')
RAFALE_MOUNT_SIDES = ('left', 'right', 'center')

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
                'aircraft_role': ac.aircraft_role,
                'wing_body_blend': _cell_str(ac.wing_body_blend),
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
        'rough': _parse_bool(row.get('rough') or '0'),
        'inlet': inlet,
        'store_mount': store_mount,
        'empty_kg': _parse_float(row.get('empty_kg') or '', 'empty_kg'),
        'internal_fuel_kg': _parse_float(row.get('internal_fuel_kg') or '', 'internal_fuel_kg'),
        'n_pilots': _parse_int(row.get('n_pilots') or '', 'n_pilots'),
        'missile_mass_kg': _parse_float(row.get('missile_mass_kg') or '', 'missile_mass_kg'),
        'n_engines': _parse_int(row.get('n_engines') or '', 'n_engines'),
    }
    payload = _parse_optional_float(row.get('max_payload_kg') or '')
    if payload is not None:
        item['max_payload_kg'] = payload
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
    aircraft_role = (row.get('aircraft_role') or '').strip().lower()
    if aircraft_role:
        if aircraft_role not in {'fighter', 'bomber'}:
            raise ValueError(f'{csv_path} 记录 {item_id} aircraft_role={aircraft_role!r} 非法，需为 fighter 或 bomber')
        item['aircraft_role'] = aircraft_role
    else:
        item['aircraft_role'] = 'fighter'
    wing_body_blend = row.get('wing_body_blend')
    if wing_body_blend not in (None, ''):
        item['wing_body_blend'] = _parse_bool(str(wing_body_blend))
    else:
        item['wing_body_blend'] = False
    from utils.combat_radius.cruise_load import apply_derived_planform_loads

    return apply_derived_planform_loads(item)


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
        aircraft_role = (row.get('aircraft_role') or '').strip().lower() or 'fighter'
        if aircraft_role not in {'fighter', 'bomber'}:
            raise ValueError(f'{csv_path} 记录 {ac_id} aircraft_role={aircraft_role!r} 非法，需为 fighter 或 bomber')
        aircraft[ac_id] = AircraftSpec(
            id=ac_id,
            name=row['name'].strip(),
            type_label=type_label,
            aircraft_role=aircraft_role,
            wing_body_blend=_parse_bool(row.get('wing_body_blend') or '0'),
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


def load_fc1_store_catalog_csv(path: str | Path | None = None) -> list[dict[str, Any]]:
    """从 FC-1 外挂弹药目录 CSV 加载各型弹药/吊舱规格（store_id 列）。"""
    from utils.paths import FC1_STORE_CATALOG_CSV

    csv_path = Path(path) if path is not None else FC1_STORE_CATALOG_CSV
    if not csv_path.is_file():
        raise ValueError(f'{csv_path} 不存在')
    rows: list[dict[str, Any]] = []
    with csv_path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f'{csv_path} 缺少表头')
        missing = [c for c in FC1_STORE_CATALOG_CSV_COLUMNS if c not in reader.fieldnames]
        if missing:
            raise ValueError(f'{csv_path} 缺少列: {missing}')
        for row in reader:
            store_id = (row.get('store_id') or '').strip()
            if not store_id:
                continue
            rows.append({
                'store_id': store_id,
                'name': (row.get('name') or '').strip(),
                'category': (row.get('category') or '').strip(),
                'mass_kg': _parse_float(row.get('mass_kg') or '', 'mass_kg'),
                'length_m': _parse_float(row.get('length_m') or '', 'length_m'),
                'diameter_m': _parse_float(row.get('diameter_m') or '', 'diameter_m'),
                'notes': (row.get('notes') or '').strip(),
            })
    if not rows:
        raise ValueError(f'{csv_path} 未读到有效外挂弹药记录')
    return rows


def load_fc1_store_mounts_csv(path: str | Path | None = None) -> list[dict[str, Any]]:
    """从 FC-1 挂点兼容 CSV 加载各挂点组可选弹药。"""
    from utils.paths import FC1_STORE_MOUNTS_CSV

    csv_path = Path(path) if path is not None else FC1_STORE_MOUNTS_CSV
    if not csv_path.is_file():
        raise ValueError(f'{csv_path} 不存在')
    rows: list[dict[str, Any]] = []
    with csv_path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f'{csv_path} 缺少表头')
        missing = [c for c in AIRCRAFT_STORE_MOUNTS_CSV_COLUMNS if c not in reader.fieldnames]
        if missing:
            raise ValueError(f'{csv_path} 缺少列: {missing}')
        for row in reader:
            aircraft_id = (row.get('aircraft_id') or '').strip()
            if not aircraft_id:
                continue
            max_qty_raw = (row.get('max_qty') or '').strip()
            if not max_qty_raw:
                raise ValueError(f'{csv_path} 行 aircraft_id={aircraft_id} 缺少 max_qty')
            rows.append({
                'aircraft_id': aircraft_id,
                'station_group': (row.get('station_group') or '').strip(),
                'station_ids': (row.get('station_ids') or '').strip(),
                'group_label': (row.get('group_label') or '').strip(),
                'store_id': (row.get('store_id') or '').strip(),
                'max_qty': int(max_qty_raw),
                'notes': (row.get('notes') or '').strip(),
            })
    if not rows:
        raise ValueError(f'{csv_path} 未读到有效挂点兼容记录')
    return rows


def load_missile_range_preset_csv(path: str | Path | None = None) -> list[dict[str, Any]]:
    """从射程计算器预设 CSV 加载弹仓样本行。"""
    from utils.paths import MISSILE_RANGE_PRESET_CSV

    csv_path = Path(path) if path is not None else MISSILE_RANGE_PRESET_CSV
    if not csv_path.is_file():
        raise ValueError(f'{csv_path} 不存在')
    rows: list[dict[str, Any]] = []
    with csv_path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f'{csv_path} 缺少表头')
        missing = [c for c in MISSILE_RANGE_PRESET_CSV_COLUMNS if c not in reader.fieldnames]
        if missing:
            raise ValueError(f'{csv_path} 缺少列: {missing}')
        for row in reader:
            group = (row.get('speed_group') or '').strip().lower()
            bay = (row.get('bay') or '').strip()
            if not group and not bay:
                continue
            if group not in MISSILE_RANGE_SPEED_GROUPS:
                raise ValueError(
                    f'{csv_path} 未知 speed_group={group!r}（仅允许 {"/".join(MISSILE_RANGE_SPEED_GROUPS)}）'
                )
            if not bay:
                raise ValueError(f'{csv_path} 存在空的 bay')
            missile_class = (row.get('missile_class') or '').strip() or None
            if missile_class is not None and missile_class not in {
                'hgv_biconic', 'hgv_waverider', 'scramjet', 'ramjet',
                'turbofan_stealth', 'turbojet_subsonic', 'turbofan_rocket', 'ballistic',
            }:
                raise ValueError(
                    f'{csv_path} 未知 missile_class={missile_class!r}（行 bay={bay}）'
                )
            item: dict[str, Any] = {
                'speed_group': group,
                'bay': bay,
                'length_m': _parse_float(row.get('length_m') or '', 'length_m'),
                'diameter_m': _parse_float(row.get('diameter_m') or '', 'diameter_m'),
                'warhead_kg': _parse_float(row.get('warhead_kg') or '', 'warhead_kg'),
                'v_launch_mach': _parse_float(row.get('v_launch_mach') or '', 'v_launch_mach'),
                'h_launch_km': _parse_float(row.get('h_launch_km') or '', 'h_launch_km'),
                'missile_class': missile_class,
            }
            notes = (row.get('notes') or '').strip()
            if notes:
                item['notes'] = notes
            rows.append(item)
    if not rows:
        raise ValueError(f'{csv_path} 未读到有效射程预设')
    found = {item['speed_group'] for item in rows}
    missing_groups = [g for g in MISSILE_RANGE_SPEED_GROUPS if g not in found]
    if missing_groups:
        raise ValueError(f'{csv_path} 缺少速度组: {missing_groups}')
    return rows


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


AIRCRAFT_STORE_CATALOG_CSV_COLUMNS = (
    'id', 'name', 'category', 'mass_kg', 'length_m', 'diameter_m', 'store_mount', 'notes',
)

AIRCRAFT_STATION_CSV_COLUMNS = (
    'aircraft_id', 'block', 'station_id', 'position', 'position_label', 'allowed_stores', 'notes',
)

AIRCRAFT_LOADOUT_PRESET_CSV_COLUMNS = (
    'aircraft_id', 'block', 'preset_id', 'preset_name', 'station_id', 'store_id', 'notes',
)

AIRCRAFT_STORE_CATEGORIES = (
    'aam', 'arm', 'agm', 'bomb', 'cluster', 'guided_bomb', 'jdam', 'rocket',
    'ecm', 'targeting', 'fuel_tank', 'telemetry',
)

AIRCRAFT_STORE_MOUNT_IDS = ('internal', 'semi_recessed', 'pylon')


def _parse_allowed_stores(raw: str) -> list[str]:
    """解析分号分隔的外挂 id 列表。"""
    return [part.strip() for part in raw.split(';') if part.strip()]


def load_aircraft_store_catalog_csv(path: str | Path | None = None) -> list[dict[str, Any]]:
    """加载外挂弹药/设备目录。"""
    from utils.paths import AIRCRAFT_STORE_CATALOG_CSV

    csv_path = Path(path) if path is not None else AIRCRAFT_STORE_CATALOG_CSV
    rows: list[dict[str, Any]] = []
    with csv_path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f'{csv_path} 缺少表头')
        missing = [c for c in AIRCRAFT_STORE_CATALOG_CSV_COLUMNS if c not in reader.fieldnames]
        if missing:
            raise ValueError(f'{csv_path} 缺少列: {missing}')
        for row in reader:
            store_id = (row.get('id') or '').strip()
            name = (row.get('name') or '').strip()
            if not store_id or not name:
                continue
            category = (row.get('category') or '').strip()
            if category not in AIRCRAFT_STORE_CATEGORIES:
                raise ValueError(
                    f'{csv_path} 未知 category={category!r}（store={store_id}）'
                )
            mount = (row.get('store_mount') or '').strip()
            if mount not in AIRCRAFT_STORE_MOUNT_IDS:
                raise ValueError(
                    f'{csv_path} store_mount 须为 {"|".join(AIRCRAFT_STORE_MOUNT_IDS)} 之一，'
                    f'得到 {mount!r}（store={store_id}）'
                )
            item: dict[str, Any] = {
                'id': store_id,
                'name': name,
                'category': category,
                'mass_kg': _parse_float(row.get('mass_kg') or '', 'mass_kg'),
                'length_m': _parse_float(row.get('length_m') or '', 'length_m'),
                'diameter_m': _parse_float(row.get('diameter_m') or '', 'diameter_m'),
                'store_mount': mount,
            }
            notes = (row.get('notes') or '').strip()
            if notes:
                item['notes'] = notes
            rows.append(item)
    if not rows:
        raise ValueError(f'{csv_path} 未读到有效外挂记录')
    return rows


def load_aircraft_station_csv(path: str | Path | None = None) -> list[dict[str, Any]]:
    """加载机型挂点能力表。"""
    from utils.paths import AIRCRAFT_STATION_CSV

    csv_path = Path(path) if path is not None else AIRCRAFT_STATION_CSV
    rows: list[dict[str, Any]] = []
    with csv_path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f'{csv_path} 缺少表头')
        missing = [c for c in AIRCRAFT_STATION_CSV_COLUMNS if c not in reader.fieldnames]
        if missing:
            raise ValueError(f'{csv_path} 缺少列: {missing}')
        store_ids = {s['id'] for s in load_aircraft_store_catalog_csv(csv_path.parent / 'aircraft_store_catalog.csv')}
        for row in reader:
            aircraft_id = (row.get('aircraft_id') or '').strip()
            station_id = (row.get('station_id') or '').strip()
            if not aircraft_id or not station_id:
                continue
            block = (row.get('block') or '').strip()
            if not block:
                raise ValueError(f'{csv_path} {aircraft_id} 挂点 {station_id} 缺少 block')
            position = (row.get('position') or '').strip()
            position_label = (row.get('position_label') or '').strip()
            if not position or not position_label:
                raise ValueError(
                    f'{csv_path} {aircraft_id} 挂点 {station_id} 缺少 position/position_label'
                )
            allowed = _parse_allowed_stores(row.get('allowed_stores') or '')
            if not allowed:
                raise ValueError(f'{csv_path} {aircraft_id} 挂点 {station_id} 无 allowed_stores')
            unknown = [s for s in allowed if s not in store_ids]
            if unknown:
                raise ValueError(
                    f'{csv_path} {aircraft_id} 挂点 {station_id} 引用未知外挂: {unknown}'
                )
            item: dict[str, Any] = {
                'aircraft_id': aircraft_id,
                'block': block,
                'station_id': station_id,
                'position': position,
                'position_label': position_label,
                'allowed_stores': allowed,
            }
            notes = (row.get('notes') or '').strip()
            if notes:
                item['notes'] = notes
            rows.append(item)
    if not rows:
        raise ValueError(f'{csv_path} 未读到有效挂点记录')
    return rows


def load_aircraft_loadout_presets_csv(path: str | Path | None = None) -> list[dict[str, Any]]:
    """加载预设挂载方案（每行一个挂点分配）。"""
    from utils.paths import AIRCRAFT_LOADOUT_PRESETS_CSV

    csv_path = Path(path) if path is not None else AIRCRAFT_LOADOUT_PRESETS_CSV
    rows: list[dict[str, Any]] = []
    with csv_path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f'{csv_path} 缺少表头')
        missing = [c for c in AIRCRAFT_LOADOUT_PRESET_CSV_COLUMNS if c not in reader.fieldnames]
        if missing:
            raise ValueError(f'{csv_path} 缺少列: {missing}')
        store_ids = {s['id'] for s in load_aircraft_store_catalog_csv(csv_path.parent / 'aircraft_store_catalog.csv')}
        station_rows = load_aircraft_station_csv(csv_path.parent / 'aircraft_station_database.csv')
        station_allowed: dict[tuple[str, str, str], set[str]] = {}
        for st in station_rows:
            key = (st['aircraft_id'], st['block'], st['station_id'])
            station_allowed[key] = set(st['allowed_stores'])
        for row in reader:
            aircraft_id = (row.get('aircraft_id') or '').strip()
            preset_id = (row.get('preset_id') or '').strip()
            station_id = (row.get('station_id') or '').strip()
            store_id = (row.get('store_id') or '').strip()
            if not aircraft_id or not preset_id or not station_id or not store_id:
                continue
            block = (row.get('block') or '').strip()
            preset_name = (row.get('preset_name') or '').strip()
            if not block or not preset_name:
                raise ValueError(
                    f'{csv_path} 预设 {preset_id} 缺少 block 或 preset_name'
                )
            if store_id not in store_ids:
                raise ValueError(f'{csv_path} 预设 {preset_id} 引用未知外挂 {store_id!r}')
            key = (aircraft_id, block, station_id)
            if key not in station_allowed:
                raise ValueError(f'{csv_path} 预设 {preset_id} 引用未知挂点 {station_id!r}')
            if store_id not in station_allowed[key]:
                raise ValueError(
                    f'{csv_path} 预设 {preset_id} 在挂点 {station_id} 挂载 {store_id!r} 不被允许'
                )
            item: dict[str, Any] = {
                'aircraft_id': aircraft_id,
                'block': block,
                'preset_id': preset_id,
                'preset_name': preset_name,
                'station_id': station_id,
                'store_id': store_id,
            }
            notes = (row.get('notes') or '').strip()
            if notes:
                item['notes'] = notes
            rows.append(item)
    if not rows:
        raise ValueError(f'{csv_path} 未读到有效挂载预设')
    return rows


def list_model_ids_from_missile_interception_csv(
    missile_path: str | Path | None = None,
    radar_path: str | Path | None = None,
) -> dict[str, list[str]]:
    """列出导弹库 + 雷达库中各类装备 id（供前端/测试断言「自动识别型号」）。"""
    data = load_missile_interception_presets_csv(missile_path, radar_path)
    return {cat: [x['id'] for x in items] for cat, items in data.items()}


def load_aircraft_pylon_csv(path: str | Path | None = None) -> list[dict[str, Any]]:
    """从挂点挂载 CSV 加载各机型 station 配置。"""
    from utils.paths import AIRCRAFT_PYLON_CSV

    csv_path = Path(path) if path is not None else AIRCRAFT_PYLON_CSV
    if not csv_path.is_file():
        raise ValueError(f'{csv_path} 不存在')
    rows: list[dict[str, Any]] = []
    with csv_path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f'{csv_path} 缺少表头')
        missing = [c for c in AIRCRAFT_PYLON_CSV_COLUMNS if c not in reader.fieldnames]
        if missing:
            raise ValueError(f'{csv_path} 缺少列: {missing}')
        for row in reader:
            aircraft_id = (row.get('aircraft_id') or '').strip()
            station_id = (row.get('station_id') or '').strip()
            if not aircraft_id and not station_id:
                continue
            if not aircraft_id:
                raise ValueError(f'{csv_path} 存在空的 aircraft_id（station={station_id}）')
            if not station_id:
                raise ValueError(f'{csv_path} 机型 {aircraft_id} 存在空的 station_id')
            position = (row.get('position') or '').strip()
            if position not in PYLON_POSITION_LABELS:
                raise ValueError(
                    f'{csv_path} 机型 {aircraft_id} 挂点 {station_id} 未知 position={position!r}'
                )
            allowed_raw = (row.get('allowed_stores') or '').strip()
            if not allowed_raw:
                raise ValueError(
                    f'{csv_path} 机型 {aircraft_id} 挂点 {station_id} 缺少 allowed_stores'
                )
            allowed_stores = [part.strip() for part in allowed_raw.split('|') if part.strip()]
            unknown = [store for store in allowed_stores if store not in STORE_TYPE_LABELS]
            if unknown:
                raise ValueError(
                    f'{csv_path} 机型 {aircraft_id} 挂点 {station_id} 未知 store 类型: {unknown}'
                )
            item: dict[str, Any] = {
                'aircraft_id': aircraft_id,
                'station_id': station_id,
                'label': (row.get('label') or '').strip() or station_id,
                'position': position,
                'symmetric': _parse_bool(row.get('symmetric') or '0'),
                'allowed_stores': allowed_stores,
            }
            notes = (row.get('notes') or '').strip()
            if notes:
                item['notes'] = notes
            rows.append(item)
    if not rows:
        raise ValueError(f'{csv_path} 未读到有效挂点记录')
    return rows


def load_rafale_mount_stations_csv(path: str | Path | None = None) -> list[dict[str, Any]]:
    """从 CSV 加载阵风挂点定义。"""
    from utils.paths import RAFALE_MOUNT_STATIONS_CSV

    csv_path = Path(path) if path is not None else RAFALE_MOUNT_STATIONS_CSV
    if not csv_path.is_file():
        raise ValueError(f'{csv_path} 不存在')
    rows: list[dict[str, Any]] = []
    with csv_path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f'{csv_path} 缺少表头')
        missing = [c for c in RAFALE_MOUNT_STATIONS_CSV_COLUMNS if c not in reader.fieldnames]
        if missing:
            raise ValueError(f'{csv_path} 缺少列: {missing}')
        for row in reader:
            aircraft_id = (row.get('aircraft_id') or '').strip()
            station_id = (row.get('station_id') or '').strip()
            station_label = (row.get('station_label') or '').strip()
            label_zh = (row.get('label_zh') or '').strip()
            side = (row.get('side') or '').strip().lower()
            position = (row.get('position') or '').strip()
            store_mount = (row.get('store_mount') or '').strip().lower()
            if not aircraft_id or not station_id or not station_label:
                continue
            if side not in RAFALE_MOUNT_SIDES:
                raise ValueError(f'{csv_path} 挂点 {station_id} 未知 side={side!r}')
            if store_mount not in RAFALE_MOUNT_STORE_MOUNTS:
                raise ValueError(
                    f'{csv_path} 挂点 {station_id} 未知 store_mount={store_mount!r}'
                )
            item: dict[str, Any] = {
                'aircraft_id': aircraft_id,
                'station_id': station_id,
                'station_label': station_label,
                'label_zh': label_zh,
                'side': side,
                'position': position,
                'store_mount': store_mount,
            }
            notes = (row.get('notes') or '').strip()
            if notes:
                item['notes'] = notes
            rows.append(item)
    if not rows:
        raise ValueError(f'{csv_path} 未读到有效挂点记录')
    return rows


def load_rafale_mount_stores_csv(path: str | Path | None = None) -> list[dict[str, Any]]:
    """从 CSV 加载阵风挂点-武器兼容表。"""
    from utils.aircraft_mount.categories import RAFALE_MOUNT_CATEGORIES
    from utils.paths import RAFALE_MOUNT_STORES_CSV

    csv_path = Path(path) if path is not None else RAFALE_MOUNT_STORES_CSV
    if not csv_path.is_file():
        raise ValueError(f'{csv_path} 不存在')
    rows: list[dict[str, Any]] = []
    with csv_path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f'{csv_path} 缺少表头')
        missing = [c for c in RAFALE_MOUNT_STORES_CSV_COLUMNS if c not in reader.fieldnames]
        if missing:
            raise ValueError(f'{csv_path} 缺少列: {missing}')
        for row in reader:
            aircraft_id = (row.get('aircraft_id') or '').strip()
            station_id = (row.get('station_id') or '').strip()
            category = (row.get('category') or '').strip()
            category_zh = (row.get('category_zh') or '').strip()
            store_id = (row.get('store_id') or '').strip()
            store_name = (row.get('store_name') or '').strip()
            if not aircraft_id or not station_id or not store_id or not store_name:
                continue
            if category not in RAFALE_MOUNT_CATEGORIES:
                raise ValueError(
                    f'{csv_path} 挂点 {station_id} 未知 category={category!r}'
                )
            label_zh = category_zh or RAFALE_MOUNT_CATEGORIES[category]['label_zh']
            rows.append({
                'aircraft_id': aircraft_id,
                'station_id': station_id,
                'category': category,
                'category_zh': label_zh,
                'store_id': store_id,
                'store_name': store_name,
            })
    if not rows:
        raise ValueError(f'{csv_path} 未读到有效兼容记录')
    return rows


def load_aircraft_weapon_stations_csv(path: str | Path | None = None) -> list[dict[str, Any]]:
    """从战斗机外挂挂点 CSV 加载每行弹药记录。"""
    from utils.paths import AIRCRAFT_WEAPON_STATIONS_CSV

    csv_path = Path(path) if path is not None else AIRCRAFT_WEAPON_STATIONS_CSV
    if not csv_path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    with csv_path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f'{csv_path} 缺少表头')
        missing = [c for c in AIRCRAFT_WEAPON_STATIONS_CSV_COLUMNS if c not in reader.fieldnames]
        if missing:
            raise ValueError(f'{csv_path} 缺少列: {missing}')
        for row in reader:
            aircraft_id = (row.get('aircraft_id') or '').strip()
            station_id = (row.get('station_id') or '').strip()
            station_name = (row.get('station_name') or '').strip()
            category = (row.get('category') or '').strip()
            weapon_id = (row.get('weapon_id') or '').strip()
            weapon_name = (row.get('weapon_name') or '').strip()
            if not aircraft_id and not station_id and not weapon_id:
                continue
            if not all([aircraft_id, station_id, station_name, category, weapon_id, weapon_name]):
                raise ValueError(
                    f'{csv_path} 存在不完整行: aircraft={aircraft_id!r} station={station_id!r} '
                    f'weapon={weapon_id!r}'
                )
            item: dict[str, Any] = {
                'aircraft_id': aircraft_id,
                'station_id': station_id,
                'station_name': station_name,
                'category': category,
                'weapon_id': weapon_id,
                'weapon_name': weapon_name,
            }
            notes = (row.get('notes') or '').strip()
            if notes:
                item['notes'] = notes
            rows.append(item)
    return rows


def load_aircraft_stores_csv(path: str | Path | None = None) -> dict[str, dict[str, Any]]:
    """加载外挂弹药/装备规格表，按 store_id 索引。"""
    from utils.paths import AIRCRAFT_STORES_CSV

    csv_path = Path(path) if path is not None else AIRCRAFT_STORES_CSV
    stores: dict[str, dict[str, Any]] = {}
    with csv_path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f'{csv_path} 缺少表头')
        missing = [c for c in AIRCRAFT_STORES_CSV_COLUMNS if c not in reader.fieldnames]
        if missing:
            raise ValueError(f'{csv_path} 缺少列: {missing}')
        for row in reader:
            store_id = (row.get('store_id') or '').strip()
            if not store_id:
                continue
            if store_id in stores:
                raise ValueError(f'{csv_path} 重复 store_id: {store_id}')
            item: dict[str, Any] = {
                'id': store_id,
                'name_en': (row.get('name_en') or '').strip(),
                'name_zh': (row.get('name_zh') or '').strip(),
                'category': (row.get('category') or '').strip(),
                'typical_mass_kg': _parse_float(row.get('typical_mass_kg') or '', 'typical_mass_kg'),
            }
            notes = (row.get('notes') or '').strip()
            if notes:
                item['notes'] = notes
            stores[store_id] = item
    if not stores:
        raise ValueError(f'{csv_path} 未读到有效外挂记录')
    return stores


def load_aircraft_hardpoints_csv(path: str | Path | None = None) -> list[dict[str, Any]]:
    """加载 Tejas 等机型挂点表（aircraft_hardpoints_database.csv）。"""
    from utils.paths import AIRCRAFT_STORES_CSV, TEJAS_HARDPOINTS_CSV

    csv_path = Path(path) if path is not None else TEJAS_HARDPOINTS_CSV
    stores = load_aircraft_stores_csv(AIRCRAFT_STORES_CSV)
    rows: list[dict[str, Any]] = []
    with csv_path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f'{csv_path} 缺少表头')
        missing = [c for c in AIRCRAFT_HARDPOINTS_CSV_COLUMNS if c not in reader.fieldnames]
        if missing:
            raise ValueError(f'{csv_path} 缺少列: {missing}')
        for row in reader:
            aircraft_id = (row.get('aircraft_id') or '').strip()
            station_id = (row.get('station_id') or '').strip()
            if not aircraft_id or not station_id:
                continue
            allowed = _parse_allowed_stores(row.get('allowed_stores') or '')
            unknown = [sid for sid in allowed if sid not in stores]
            if unknown:
                raise ValueError(
                    f'{csv_path} {aircraft_id}/{station_id} 引用未知外挂: {unknown}'
                )
            item: dict[str, Any] = {
                'aircraft_id': aircraft_id,
                'station_id': station_id,
                'name_zh': (row.get('name_zh') or '').strip(),
                'position': (row.get('position') or '').strip(),
                'side': (row.get('side') or '').strip(),
                'max_mass_kg': _parse_float(row.get('max_mass_kg') or '', 'max_mass_kg'),
                'allowed_stores': allowed,
            }
            notes = (row.get('notes') or '').strip()
            if notes:
                item['notes'] = notes
            rows.append(item)
    if not rows:
        raise ValueError(f'{csv_path} 未读到有效挂点记录')
    return rows


def load_aircraft_fixed_equipment_csv(path: str | Path | None = None) -> list[dict[str, Any]]:
    """加载战斗机固定机载设备（非武器挂点）。"""
    from utils.paths import AIRCRAFT_FIXED_EQUIPMENT_CSV

    csv_path = Path(path) if path is not None else AIRCRAFT_FIXED_EQUIPMENT_CSV
    rows: list[dict[str, Any]] = []
    with csv_path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f'{csv_path} 缺少表头')
        missing = [c for c in AIRCRAFT_FIXED_EQUIPMENT_CSV_COLUMNS if c not in reader.fieldnames]
        if missing:
            raise ValueError(f'{csv_path} 缺少列: {missing}')
        for row in reader:
            aircraft_id = (row.get('aircraft_id') or '').strip()
            equipment_id = (row.get('equipment_id') or '').strip()
            if not aircraft_id or not equipment_id:
                continue
            item: dict[str, Any] = {
                'aircraft_id': aircraft_id,
                'equipment_id': equipment_id,
                'name_zh': (row.get('name_zh') or '').strip(),
                'location': (row.get('location') or '').strip(),
            }
            notes = (row.get('notes') or '').strip()
            if notes:
                item['notes'] = notes
            rows.append(item)
    return rows


def load_weapon_store_csv(path: str | Path | None = None) -> list[dict[str, Any]]:
    """加载战斗机外挂弹药/设备库。"""
    from utils.paths import WEAPON_STORE_CSV

    csv_path = Path(path) if path is not None else WEAPON_STORE_CSV
    rows: list[dict[str, Any]] = []
    with csv_path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f'{csv_path} 缺少表头')
        missing = [c for c in WEAPON_STORE_CSV_COLUMNS if c not in reader.fieldnames]
        if missing:
            raise ValueError(f'{csv_path} 缺少列: {missing}')
        for row in reader:
            item_id = (row.get('id') or '').strip()
            name = (row.get('name') or '').strip()
            category = (row.get('category') or '').strip()
            if not item_id or not name or not category:
                continue
            if category not in WEAPON_STORE_CATEGORIES:
                raise ValueError(
                    f'{csv_path} 未知 category={category!r}（id={item_id}）'
                )
            item: dict[str, Any] = {
                'id': item_id,
                'name': name,
                'category': category,
                'mass_kg': _parse_float(row.get('mass_kg') or '', 'mass_kg'),
                'length_m': _parse_float(row.get('length_m') or '', 'length_m'),
                'diameter_m': _parse_float(row.get('diameter_m') or '', 'diameter_m'),
            }
            notes = (row.get('notes') or '').strip()
            if notes:
                item['notes'] = notes
            rows.append(item)
    if not rows:
        raise ValueError(f'{csv_path} 未读到有效武器记录')
    return rows


def load_typhoon_store_stations_csv(path: str | Path | None = None) -> list[dict[str, Any]]:
    """加载台风挂点定义（图表从左至右编号）。"""
    from utils.paths import TYPHOON_STORE_STATIONS_CSV

    csv_path = Path(path) if path is not None else TYPHOON_STORE_STATIONS_CSV
    rows: list[dict[str, Any]] = []
    with csv_path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f'{csv_path} 缺少表头')
        missing = [c for c in TYPHOON_STORE_STATIONS_CSV_COLUMNS if c not in reader.fieldnames]
        if missing:
            raise ValueError(f'{csv_path} 缺少列: {missing}')
        for row in reader:
            station_id = (row.get('station_id') or '').strip()
            name = (row.get('name') or '').strip()
            mount = (row.get('mount') or '').strip()
            if not station_id or not name or not mount:
                continue
            if mount not in TYPHOON_STORE_MOUNTS:
                raise ValueError(
                    f'{csv_path} 未知 mount={mount!r}（station_id={station_id}）'
                )
            item: dict[str, Any] = {
                'station_id': _parse_int(station_id, 'station_id'),
                'name': name,
                'mount': mount,
                'position_index': _parse_int(row.get('position_index') or '', 'position_index'),
            }
            notes = (row.get('notes') or '').strip()
            if notes:
                item['notes'] = notes
            rows.append(item)
    if not rows:
        raise ValueError(f'{csv_path} 未读到有效挂点记录')
    return rows


def load_typhoon_store_compatibility_csv(path: str | Path | None = None) -> list[dict[str, Any]]:
    """加载台风挂点—弹药兼容表。"""
    from utils.paths import TYPHOON_STORE_COMPATIBILITY_CSV

    csv_path = Path(path) if path is not None else TYPHOON_STORE_COMPATIBILITY_CSV
    rows: list[dict[str, Any]] = []
    with csv_path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f'{csv_path} 缺少表头')
        missing = [c for c in TYPHOON_STORE_COMPATIBILITY_CSV_COLUMNS if c not in reader.fieldnames]
        if missing:
            raise ValueError(f'{csv_path} 缺少列: {missing}')
        for row in reader:
            station_id = (row.get('station_id') or '').strip()
            weapon_id = (row.get('weapon_id') or '').strip()
            if not station_id or not weapon_id:
                continue
            max_qty = _parse_int(row.get('max_qty') or '', 'max_qty')
            if max_qty <= 0:
                raise ValueError(
                    f'{csv_path} station_id={station_id} weapon_id={weapon_id} max_qty 须为正'
                )
            item: dict[str, Any] = {
                'station_id': _parse_int(station_id, 'station_id'),
                'weapon_id': weapon_id,
                'max_qty': max_qty,
            }
            notes = (row.get('notes') or '').strip()
            if notes:
                item['notes'] = notes
            rows.append(item)
    if not rows:
        raise ValueError(f'{csv_path} 未读到有效兼容记录')
    return rows
