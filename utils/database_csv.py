"""舰载机 / 航母参数库 CSV 导入导出（UTF-8 BOM，便于 Excel 打开中文）。"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from utils.specs import AircraftSpec, CarrierSpec

AIRCRAFT_CSV_COLUMNS = (
    'id', 'name', 'type_label', 'mtow_kg', 'empty_kg', 'internal_fuel_kg', 'max_payload_kg',
    'bvr_missile', 'missile_mass_kg', 'sweep_le_deg', 'wingspan_m', 'wing_area_m2',
    'wing_height_m', 'cd0', 't_max_sl_n', 't_main_stovl_sl_n', 't_liftfan_sl_n',
    't_rollposts_sl_n', 'exhaust_mdot_kg_s', 'exhaust_d0_m', 'exhaust_height_m',
    'shaft_power_sl_w', 'prop_diameter_m', 'nacelle_blockage_frac', 'notes',
)

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

COMBAT_RADIUS_AIRCRAFT_CSV_COLUMNS = (
    'id', 'name', 'nation', 'AR', 'sweep_deg', 'wing_loading', 'tc',
    'mach', 'alt_m', 'planform', 'layout', 'bwb', 'rough', 'ld_known', 'notes',
)

COMBAT_RADIUS_ENGINE_CSV_COLUMNS = (
    'id', 'name', 'nation', 'bpr', 'opr', 't4_K', 'tsl_kN', 'notes',
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
    text = raw.strip()
    if not text:
        raise ValueError(f'缺少必填数值字段 {field}')
    return float(text)


def _parse_nation(row: dict[str, str], path: Path, item_id: str) -> str:
    """读取国别列；两级（国别 → 型号）选择器依赖该列，故要求非空。"""
    nation = (row.get('nation') or '').strip()
    if not nation:
        raise ValueError(f'{path} 记录 {item_id} 缺少 nation（国别）')
    return nation


def export_aircraft_csv(path: str | Path, aircraft: dict[str, 'AircraftSpec']) -> None:
    path = Path(path)
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=AIRCRAFT_CSV_COLUMNS)
        writer.writeheader()
        for ac in aircraft.values():
            writer.writerow({col: _cell_str(getattr(ac, col)) for col in AIRCRAFT_CSV_COLUMNS})


def export_carriers_csv(path: str | Path, carriers: list['CarrierSpec']) -> None:
    path = Path(path)
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=CARRIERS_CSV_COLUMNS)
        writer.writeheader()
        for c in carriers:
            writer.writerow({col: _cell_str(getattr(c, col)) for col in CARRIERS_CSV_COLUMNS})


def load_aircraft_csv(path: str | Path) -> dict[str, 'AircraftSpec']:
    from utils.specs import AircraftSpec

    path = Path(path)
    rows: list[dict[str, str]] = []
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f'{path} 缺少表头')
        missing = [c for c in AIRCRAFT_CSV_COLUMNS if c not in reader.fieldnames]
        if missing:
            raise ValueError(f'{path} 缺少列: {missing}')
        rows.extend(reader)

    aircraft: dict[str, AircraftSpec] = {}
    for row in rows:
        if not row.get('id', '').strip():
            continue
        ac_id = row['id'].strip()
        aircraft[ac_id] = AircraftSpec(
            id=ac_id,
            name=row['name'].strip(),
            type_label=row['type_label'].strip(),
            mtow_kg=_parse_float(row['mtow_kg'], 'mtow_kg'),
            empty_kg=_parse_float(row['empty_kg'], 'empty_kg'),
            internal_fuel_kg=_parse_float(row['internal_fuel_kg'], 'internal_fuel_kg'),
            max_payload_kg=_parse_float(row['max_payload_kg'], 'max_payload_kg'),
            bvr_missile=row['bvr_missile'].strip(),
            missile_mass_kg=_parse_float(row['missile_mass_kg'], 'missile_mass_kg'),
            sweep_le_deg=_parse_float(row['sweep_le_deg'], 'sweep_le_deg'),
            wingspan_m=_parse_float(row['wingspan_m'], 'wingspan_m'),
            wing_area_m2=_parse_float(row['wing_area_m2'], 'wing_area_m2'),
            wing_height_m=_parse_float(row['wing_height_m'], 'wing_height_m'),
            cd0=_parse_float(row['cd0'], 'cd0'),
            t_max_sl_n=_parse_optional_float(row['t_max_sl_n']),
            t_main_stovl_sl_n=_parse_optional_float(row['t_main_stovl_sl_n']),
            t_liftfan_sl_n=_parse_optional_float(row['t_liftfan_sl_n']),
            t_rollposts_sl_n=_parse_optional_float(row['t_rollposts_sl_n']),
            exhaust_mdot_kg_s=_parse_optional_float(row.get('exhaust_mdot_kg_s', '')),
            exhaust_d0_m=_parse_optional_float(row.get('exhaust_d0_m', '')),
            exhaust_height_m=_parse_optional_float(row.get('exhaust_height_m', '')),
            shaft_power_sl_w=_parse_optional_float(row.get('shaft_power_sl_w', '')),
            prop_diameter_m=_parse_optional_float(row.get('prop_diameter_m', '')),
            nacelle_blockage_frac=_parse_optional_float(row.get('nacelle_blockage_frac', '')),
            notes=row.get('notes', '').strip(),
        )
    if not aircraft:
        raise ValueError(f'{path} 未读到有效舰载机记录')
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
    """加载作战半径机型几何预设。

    返回字段与前端契约对齐：id/name/nation/AR/sweep_deg/wing_loading/tc/
    mach/alt_m/planform/layout/bwb/rough，以及可选 ld_known、notes。
    """
    from utils.paths import COMBAT_RADIUS_AIRCRAFT_CSV

    csv_path = Path(path) if path is not None else COMBAT_RADIUS_AIRCRAFT_CSV
    rows: list[dict[str, Any]] = []
    with csv_path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f'{csv_path} 缺少表头')
        missing = [c for c in COMBAT_RADIUS_AIRCRAFT_CSV_COLUMNS if c not in reader.fieldnames]
        if missing:
            raise ValueError(f'{csv_path} 缺少列: {missing}')
        for row in reader:
            item_id = (row.get('id') or '').strip()
            name = (row.get('name') or '').strip()
            if not item_id or not name:
                continue
            planform = (row.get('planform') or '').strip()
            layout = (row.get('layout') or '').strip()
            from utils.combat_radius.lift_drag import LAYOUT_MULT, PLANFORM_MULT
            if planform not in PLANFORM_MULT:
                raise ValueError(f'{csv_path} 记录 {item_id} 未知 planform={planform!r}')
            if layout not in LAYOUT_MULT:
                raise ValueError(f'{csv_path} 记录 {item_id} 未知 layout={layout!r}')
            item: dict[str, Any] = {
                'id': item_id,
                'name': name,
                'nation': _parse_nation(row, csv_path, item_id),
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
            }
            ld_known = _parse_optional_float(row.get('ld_known') or '')
            if ld_known is not None:
                item['ld_known'] = ld_known
            notes = (row.get('notes') or '').strip()
            if notes:
                item['notes'] = notes
            rows.append(item)
    if not rows:
        raise ValueError(f'{csv_path} 未读到有效作战半径机型记录')
    return rows


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
