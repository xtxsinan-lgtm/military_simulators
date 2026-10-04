"""把各碎片挂载目录合并进作战半径统一挂点/弹药模型。

各 PR 曾分别新增 MiG-29K、F-14、F-16、阵风、台风、FC-1、FA-50、光辉、
鹰狮等挂点 CSV，但作战半径交互 UI 只读 `aircraft_stations_database.json`
与 `munitions_database.csv`。本模块在构建 catalog / 解析挂载时把碎片源
规范成同一结构，避免只显示示意图却无法按挂点选弹并重算半径。
"""
from __future__ import annotations

import re
from typing import Any

# 类别缺几何时的代表尺寸（m）
_CATEGORY_GEOMETRY: dict[str, tuple[float, float]] = {
    'aam': (3.65, 0.178),
    'aam_bvr': (3.65, 0.178),
    'aam_mrm': (4.0, 0.23),
    'aam_wvr': (2.90, 0.13),
    'a2a': (3.65, 0.178),
    'ir_aam': (2.90, 0.13),
    'radar_aam': (3.65, 0.178),
    'agm': (2.50, 0.30),
    'asm': (4.0, 0.35),
    'arm': (4.2, 0.25),
    'bomb': (2.2, 0.27),
    'unguided_bomb': (2.2, 0.27),
    'bomb_unguided': (2.2, 0.27),
    'bombs_conventional': (2.2, 0.27),
    'guided_bomb': (3.3, 0.27),
    'bomb_guided': (3.3, 0.27),
    'bombs_guided': (3.3, 0.27),
    'laser_bomb': (3.3, 0.27),
    'jdam': (3.5, 0.35),
    'pgb': (3.3, 0.35),
    'pgbb': (3.3, 0.35),
    'pgm': (3.3, 0.35),
    'lgb': (3.3, 0.27),
    'glide_bomb': (3.5, 0.30),
    'cluster': (2.3, 0.40),
    'dispenser': (2.3, 0.40),
    'battlefield': (2.5, 0.35),
    'rocket': (1.8, 0.25),
    'rocket_pod': (2.5, 0.35),
    'fuel_tank': (4.5, 0.55),
    'tank': (4.5, 0.55),
    'fuel': (4.5, 0.55),
    'pods_fuel': (4.5, 0.55),
    'pod': (2.3, 0.35),
    'pod_optronic': (2.3, 0.35),
    'targeting': (2.3, 0.35),
    'targeting_pod': (2.3, 0.35),
    'laser_designation': (2.3, 0.35),
    'recon': (2.5, 0.40),
    'ecm': (2.2, 0.30),
    'electronic_warfare': (2.2, 0.30),
    'ew': (2.2, 0.30),
    'training': (2.0, 0.20),
    'standoff': (5.0, 0.55),
    'cruise': (5.0, 0.45),
    'air_to_air': (3.2, 0.16),
    'air_to_ground': (3.5, 0.35),
    'air_to_sea': (4.5, 0.35),
    'nuclear': (5.2, 0.55),
    'wvr': (2.90, 0.13),
    'bvr': (3.65, 0.178),
    'target': (2.0, 0.25),
    'aux': (4.5, 0.45),
}

# 鹰狮 E/F：类型令牌 → 代表性弹药 id（须已在统一弹药库或本模块规格表中）
_GRIPEN_EF_TYPE_OPTIONS: dict[str, list[str]] = {
    'a2a_ir': ['iris_t', 'aim9'],
    'a2a_radar': ['meteor', 'aim120'],
    'anti_ship': ['rbs15', 'harpoon'],
    'smart_bomb': ['gbu12', 'gbu31'],
    'sdb': ['gbu39'],
    'sdb_alt': ['gbu39'],
    'fuel_tank': ['ft1100'],
    'ecm_pod': ['bo20'],
    'recce_pod': ['spk39'],
    'flir_ldp': ['litening'],
    'aacmi_pod': ['ais_pod'],
}

# 阵风弹药公开量级规格（碎片 CSV 只有名称）
_RAFALE_STORE_SPECS: dict[str, dict[str, Any]] = {
    'mica_ir_ng': {'name': 'MICA IR (NG)', 'category': 'aam', 'mass_kg': 112, 'length_m': 3.1, 'diameter_m': 0.16},
    'mica_em_ng': {'name': 'MICA EM (NG)', 'category': 'aam', 'mass_kg': 112, 'length_m': 3.1, 'diameter_m': 0.16},
    'meteor': {'name': 'METEOR', 'category': 'aam', 'mass_kg': 190, 'length_m': 3.65, 'diameter_m': 0.178},
    'mk_82': {'name': 'MK-82', 'category': 'unguided_bomb', 'mass_kg': 241, 'length_m': 2.21, 'diameter_m': 0.273},
    'mk_83': {'name': 'MK-83', 'category': 'unguided_bomb', 'mass_kg': 454, 'length_m': 2.99, 'diameter_m': 0.356},
    'mk_84': {'name': 'MK-84', 'category': 'unguided_bomb', 'mass_kg': 925, 'length_m': 3.84, 'diameter_m': 0.46},
    'gbu_12_22_49': {'name': 'GBU-12 / 22 / 49', 'category': 'laser_bomb', 'mass_kg': 230, 'length_m': 3.27, 'diameter_m': 0.273},
    'gbu_16': {'name': 'GBU-16', 'category': 'laser_bomb', 'mass_kg': 454, 'length_m': 3.78, 'diameter_m': 0.356},
    'gbu_10_24': {'name': 'GBU-10 / 24', 'category': 'laser_bomb', 'mass_kg': 1000, 'length_m': 4.3, 'diameter_m': 0.46},
    'sbu_21_56_66_hammer': {'name': 'HAMMER 250 kg 级', 'category': 'guided_bomb', 'mass_kg': 340, 'length_m': 3.1, 'diameter_m': 0.32},
    'sbu_58_54_64_hammer': {'name': 'HAMMER 500 kg 级', 'category': 'guided_bomb', 'mass_kg': 540, 'length_m': 3.3, 'diameter_m': 0.35},
    'sbu_hammer_xlr': {'name': 'HAMMER XLR', 'category': 'guided_bomb', 'mass_kg': 680, 'length_m': 3.5, 'diameter_m': 0.35},
    'scalp_eg': {'name': 'SCALP-EG', 'category': 'standoff', 'mass_kg': 1300, 'length_m': 5.1, 'diameter_m': 0.63},
    'am39_exocet': {'name': 'AM-39 Exocet', 'category': 'asm', 'mass_kg': 670, 'length_m': 4.7, 'diameter_m': 0.35},
    'rpl_701_1250l': {
        'name': 'RPL-701 1250L 副油箱', 'category': 'fuel_tank',
        'mass_kg': 1100, 'dry_mass_kg': 120, 'fuel_kg': 980,
        'length_m': 4.8, 'diameter_m': 0.55,
    },
    'rpl_741_2000l': {
        'name': 'RPL-741 2000L 副油箱', 'category': 'fuel_tank',
        'mass_kg': 1720, 'dry_mass_kg': 160, 'fuel_kg': 1560,
        'length_m': 5.5, 'diameter_m': 0.65,
    },
    'cft_1150l': {
        'name': 'CFT 1150L 保形油箱', 'category': 'fuel_tank',
        'mass_kg': 1000, 'dry_mass_kg': 120, 'fuel_kg': 880,
        'length_m': 4.0, 'diameter_m': 0.50,
    },
    'sniper': {'name': 'SNIPER', 'category': 'pod', 'mass_kg': 200, 'length_m': 2.41, 'diameter_m': 0.305},
    'talios': {'name': 'TALIOS', 'category': 'pod', 'mass_kg': 250, 'length_m': 2.5, 'diameter_m': 0.35},
    'damocles_mp': {'name': 'DAMOCLES MP', 'category': 'pod', 'mass_kg': 250, 'length_m': 2.5, 'diameter_m': 0.35},
    'pod_tr': {'name': 'POD TR', 'category': 'pod', 'mass_kg': 200, 'length_m': 2.3, 'diameter_m': 0.35},
    'areos': {'name': 'AREOS 侦察吊舱', 'category': 'pod', 'mass_kg': 500, 'length_m': 3.5, 'diameter_m': 0.45},
    'esj': {'name': 'ESJ 电子战吊舱', 'category': 'ecm', 'mass_kg': 300, 'length_m': 2.5, 'diameter_m': 0.40},
    'x_guard_towed_decoy': {'name': 'X-GUARD Towed Decoy', 'category': 'ecm', 'mass_kg': 40, 'length_m': 1.2, 'diameter_m': 0.12},
    'narang_buddy': {'name': 'NARANG 伙伴加油吊舱', 'category': 'pod', 'mass_kg': 400, 'length_m': 3.0, 'diameter_m': 0.45},
    'al_tariq_er': {'name': 'AL-TARIQ ER', 'category': 'guided_bomb', 'mass_kg': 450, 'length_m': 3.5, 'diameter_m': 0.35},
    'al_tariq_s': {'name': 'AL-TARIQ S', 'category': 'guided_bomb', 'mass_kg': 300, 'length_m': 3.2, 'diameter_m': 0.32},
    'lr68': {'name': 'LR68', 'category': 'rocket_pod', 'mass_kg': 150, 'length_m': 2.5, 'diameter_m': 0.35},
    'rj10_anti_radar': {'name': 'RJ-10 Anti-Radar', 'category': 'arm', 'mass_kg': 500, 'length_m': 4.2, 'diameter_m': 0.35},
    'rj10_anti_ship': {'name': 'RJ-10 Anti-Ship', 'category': 'asm', 'mass_kg': 550, 'length_m': 4.5, 'diameter_m': 0.35},
    'smart_cruiser': {'name': 'SMART CRUISER', 'category': 'standoff', 'mass_kg': 900, 'length_m': 4.8, 'diameter_m': 0.50},
    'thunder_p32': {'name': 'THUNDER P-32', 'category': 'guided_bomb', 'mass_kg': 450, 'length_m': 3.5, 'diameter_m': 0.35},
    'tp_15': {'name': 'TP-15', 'category': 'agm', 'mass_kg': 300, 'length_m': 3.0, 'diameter_m': 0.30},
    'asmp_a': {'name': 'ASMP-A', 'category': 'nuclear', 'mass_kg': 860, 'length_m': 5.38, 'diameter_m': 0.38},
    'asn4g': {'name': 'ASN4G', 'category': 'nuclear', 'mass_kg': 800, 'length_m': 5.0, 'diameter_m': 0.40},
}

# 鹰狮 C/D 碎片弹药：与统一库同 id 的直接复用；其余补规格
_GRIPEN_CD_EXTRA: dict[str, dict[str, Any]] = {
    'aim9lm': {'name': 'AIM-9L/M', 'category': 'aam', 'mass_kg': 86, 'length_m': 2.87, 'diameter_m': 0.127},
    'iris_t': {'name': 'IRIS-T', 'category': 'aam', 'mass_kg': 87, 'length_m': 2.94, 'diameter_m': 0.127},
    'a_darter': {'name': 'A-Darter', 'category': 'aam', 'mass_kg': 90, 'length_m': 2.98, 'diameter_m': 0.166},
    'aacmi': {'name': 'AACMI 训练吊舱', 'category': 'training', 'mass_kg': 50, 'length_m': 2.0, 'diameter_m': 0.20},
    'meteor': {'name': 'Meteor', 'category': 'aam', 'mass_kg': 190, 'length_m': 3.65, 'diameter_m': 0.178},
    'skyflash': {'name': 'Skyflash', 'category': 'aam', 'mass_kg': 193, 'length_m': 3.68, 'diameter_m': 0.203},
    'gbu49': {'name': 'GBU-49', 'category': 'laser_bomb', 'mass_kg': 250, 'length_m': 3.3, 'diameter_m': 0.273},
    'gbu32': {'name': 'GBU-32 JDAM', 'category': 'jdam', 'mass_kg': 460, 'length_m': 3.0, 'diameter_m': 0.356},
    'bk90': {'name': 'Bk 90', 'category': 'cluster', 'mass_kg': 600, 'length_m': 3.5, 'diameter_m': 0.45},
    'bo20': {'name': 'BO20 干扰吊舱', 'category': 'ecm', 'mass_kg': 200, 'length_m': 2.2, 'diameter_m': 0.30},
    'estl': {'name': 'ESTL 拖曳诱饵', 'category': 'ecm', 'mass_kg': 40, 'length_m': 1.2, 'diameter_m': 0.12},
    'rbs15': {'name': 'RBS-15', 'category': 'asm', 'mass_kg': 650, 'length_m': 4.35, 'diameter_m': 0.50},
    'taurus350': {'name': 'TAURUS KEPD 350', 'category': 'standoff', 'mass_kg': 1400, 'length_m': 5.1, 'diameter_m': 0.63},
    'ft1100': {
        'name': '1100 L 副油箱', 'category': 'fuel_tank',
        'mass_kg': 900, 'dry_mass_kg': 100, 'fuel_kg': 800,
        'length_m': 4.6, 'diameter_m': 0.52,
    },
    'erielectron': {'name': 'Erieye/自卫干扰吊舱', 'category': 'ecm', 'mass_kg': 220, 'length_m': 2.3, 'diameter_m': 0.32},
    'vicon': {'name': 'Vinten Vicon 侦察吊舱', 'category': 'recon', 'mass_kg': 250, 'length_m': 2.5, 'diameter_m': 0.40},
    'spk39': {'name': 'SPK 39 侦察吊舱', 'category': 'recon', 'mass_kg': 280, 'length_m': 2.6, 'diameter_m': 0.40},
    'mrp': {'name': 'Modular Reconnaissance Pod', 'category': 'recon', 'mass_kg': 300, 'length_m': 2.8, 'diameter_m': 0.42},
}

# 油箱：从 notes 抽「含燃油约 N kg」或「约 N kg 燃油」
_FUEL_NOTE_RE = re.compile(
    r'(?:含燃油|燃油约|约)\s*([0-9]+(?:\.[0-9]+)?)\s*kg',
    re.IGNORECASE,
)


def _f(value: Any, default: float = 0.0) -> float:
    """解析浮点。"""
    if value is None or value == '':
        return default
    return float(value)


def _is_gun(category: str, store_id: str = '', name: str = '') -> bool:
    """内置航炮不计外挂。"""
    cat = (category or '').lower()
    sid = (store_id or '').lower()
    nm = (name or '').lower()
    if cat in {'gun', 'fixed'}:
        return True
    if sid in {'g', 'bk27', 'built_in_gun'}:
        return True
    if '航炮' in nm or 'cannon' in nm:
        return True
    return False


def _is_fuel_category(category: str, store_id: str = '', name: str = '') -> bool:
    """是否副油箱/保形油箱类。"""
    cat = (category or '').lower()
    sid = (store_id or '').lower()
    nm = (name or '').lower()
    if cat in {'fuel_tank', 'tank', 'fuel'}:
        return True
    if 'tank' in cat or cat.endswith('_fuel'):
        return True
    if 'tank' in sid or sid in {'fuel', 'ft1100', 'ft_800', 'ft_1100', 'tank150'}:
        return True
    if '副油箱' in nm or 'drop tank' in nm or 'fuel tank' in nm:
        return True
    return False


def normalize_munition_record(
    store_id: str,
    *,
    name: str,
    category: str,
    mass_kg: float,
    length_m: float | None = None,
    diameter_m: float | None = None,
    dry_mass_kg: float | None = None,
    fuel_kg: float | None = None,
    notes: str = '',
) -> dict[str, Any] | None:
    """规范单条弹药；航炮返回 None。"""
    if _is_gun(category, store_id, name):
        return None
    mass = float(mass_kg)
    if mass < 0:
        raise ValueError(f'弹药 {store_id} 质量不能为负')
    fuel = fuel_kg
    dry = dry_mass_kg
    if fuel is None or dry is None:
        if _is_fuel_category(category, store_id, name) or fuel_kg:
            # 优先 notes 里的燃油数字
            match = _FUEL_NOTE_RE.search(notes or '')
            if match:
                fuel = float(match.group(1))
                dry = max(mass - fuel, 40.0)
            else:
                # 湿重约 90% 为燃油
                fuel = round(mass * 0.88, 1) if fuel is None else float(fuel)
                dry = round(mass - fuel, 1) if dry is None else float(dry)
                if dry < 40:
                    dry = 40.0
                    fuel = max(mass - dry, 0.0)
        else:
            dry = mass if dry is None else float(dry)
            fuel = 0.0 if fuel is None else float(fuel)
    length = length_m
    diameter = diameter_m
    if not length or not diameter:
        geom = _CATEGORY_GEOMETRY.get((category or '').lower()) or _CATEGORY_GEOMETRY['aam']
        length = length or geom[0]
        diameter = diameter or geom[1]
    return {
        'id': store_id,
        'name': name or store_id,
        'category': category or 'store',
        'mass_kg': float(dry) + float(fuel),
        'dry_mass_kg': float(dry),
        'fuel_kg': float(fuel),
        'length_m': float(length),
        'diameter_m': float(diameter),
        'notes': notes or '',
    }


def mount_style_from_hints(
    *,
    position: str = '',
    zone: str = '',
    side: str = '',
    mount: str = '',
    station_id: str = '',
) -> str:
    """由挂点位置/挂装方式推断统一 mount_style。"""
    text = ' '.join([
        str(position or ''), str(zone or ''), str(side or ''),
        str(mount or ''), str(station_id or ''),
    ]).lower()
    if 'semi' in text or '半埋' in text:
        return 'semi_recessed'
    if 'cft' in text or 'conformal' in text or '保形' in text:
        return 'cft'
    if 'tip' in text or 'wingtip' in text or 'wing_tip' in text or '翼尖' in text:
        return 'wing_tip'
    if 'center' in text or 'centre' in text or 'fus_cent' in text or 'belly_center' in text:
        return 'centerline'
    if 'chin' in text or 'tgp' in text or 'intake' in text or '侧腹' in text or '进气' in text:
        return 'chin_pod' if ('chin' in text or 'tgp' in text or 'ldp' in text) else 'side_rail'
    if 'side' in text or 'rail' in text or 'lat' in text:
        return 'side_rail'
    if mount in {'centerline', 'wing_tip', 'wing_pylon', 'side_rail', 'cft', 'chin_pod', 'semi_recessed'}:
        return mount
    if mount == 'pylon':
        return 'wing_pylon'
    return 'wing_pylon'


def _merge_munition(dst: dict[str, dict[str, Any]], record: dict[str, Any] | None) -> None:
    """合并弹药；已有完整记录优先保留。"""
    if not record:
        return
    mid = record['id']
    old = dst.get(mid)
    if old is None:
        dst[mid] = record
        return
    # 旧记录缺几何/油量时用新记录补齐
    patched = dict(old)
    for key in ('length_m', 'diameter_m', 'dry_mass_kg', 'fuel_kg', 'mass_kg', 'name', 'category', 'notes'):
        if not patched.get(key) and record.get(key):
            patched[key] = record[key]
    if float(patched.get('length_m') or 0) <= 0:
        patched['length_m'] = record['length_m']
    if float(patched.get('diameter_m') or 0) <= 0:
        patched['diameter_m'] = record['diameter_m']
    dst[mid] = patched


def _station(
    station_id: str,
    label: str,
    mount_style: str,
    option_ids: list[str],
    *,
    qty_by_id: dict[str, float] | None = None,
) -> dict[str, Any]:
    """构造统一挂点定义。"""
    qty_map = qty_by_id or {}
    options = []
    seen: set[tuple[str, float]] = set()
    for mid in option_ids:
        if not mid or _is_gun('', mid, ''):
            continue
        qty = float(qty_map.get(mid, 1.0))
        key = (mid, qty)
        if key in seen:
            continue
        seen.add(key)
        options.append({'munition_id': mid, 'qty': qty})
    return {
        'id': str(station_id),
        'label': label or str(station_id),
        'mount_style': mount_style,
        'options': options,
    }


def _aircraft_entry(
    aircraft_id: str,
    name: str,
    stations: list[dict[str, Any]],
    default_selection: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """构造统一机型挂点条目。"""
    return {
        'id': aircraft_id,
        'name': name or aircraft_id,
        'default_selection': default_selection or {},
        'stations': stations,
    }


def _collect_mig29(munitions: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """MiG-29K：aircraft_stores CSV。"""
    from utils.stores.stores_config import load_aircraft_stations, load_stores_database

    stores = load_stores_database()
    for sid, row in stores.items():
        _merge_munition(munitions, normalize_munition_record(
            sid,
            name=str(row.get('name') or sid),
            category=str(row.get('category') or ''),
            mass_kg=_f(row.get('mass_kg')),
            length_m=_f(row.get('length_m')) or None,
            diameter_m=_f(row.get('diameter_m')) or None,
            notes=str(row.get('notes') or ''),
        ))
    stations_map = load_aircraft_stations()
    out: dict[str, dict[str, Any]] = {}
    for aid, stations in stations_map.items():
        st_list = []
        for st in stations:
            style = mount_style_from_hints(
                side=str(st.get('side') or ''),
                station_id=str(st.get('station_id') or ''),
                position=str(st.get('name') or ''),
            )
            st_list.append(_station(
                str(st['station_id']),
                str(st.get('name') or st['station_id']),
                style,
                list(st.get('allowed_stores') or []),
            ))
        # 默认：外侧近距 + 内侧中距（若有）
        defaults: dict[str, dict[str, Any]] = {}
        for st in st_list:
            opts = {o['munition_id'] for o in st['options']}
            sid = str(st['id'])
            if 'r73e' in opts and (sid.endswith('_outer_l') or sid.endswith('_outer_r')):
                defaults[sid] = {'munition_id': 'r73e', 'qty': 1}
            elif 'rvv_ae' in opts and 'inner' in sid:
                defaults[sid] = {'munition_id': 'rvv_ae', 'qty': 1}
        out[aid] = _aircraft_entry(aid, aid, st_list, defaults)
    return out


def _collect_f14(munitions: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """F-14：store_types + layouts + presets。"""
    from utils.stores.loadout import parse_loadout_string
    from utils.stores.store_catalog import (
        load_aircraft_loadout_presets_csv,
        load_aircraft_store_layouts_csv,
        load_store_types_csv,
    )

    for sid, stype in load_store_types_csv().items():
        cat = 'fuel_tank' if 'tank' in sid else 'store'
        _merge_munition(munitions, normalize_munition_record(
            sid,
            name=stype.name,
            category=cat,
            mass_kg=stype.mass_kg,
            length_m=stype.length_m,
            diameter_m=stype.diameter_m,
            notes=stype.notes,
        ))
    layouts = load_aircraft_store_layouts_csv()
    presets = load_aircraft_loadout_presets_csv()
    out: dict[str, dict[str, Any]] = {}
    for aid, stations in layouts.items():
        st_list = []
        for st in stations:
            style = mount_style_from_hints(zone=st.zone, station_id=st.station_id, position=st.label)
            st_list.append(_station(st.station_id, st.label, style, list(st.allowed_store_ids)))
        defaults: dict[str, dict[str, Any]] = {}
        for preset in presets.get(aid, []):
            if preset.preset_id == 'cap' or not defaults:
                for item in parse_loadout_string(preset.loadout):
                    defaults[item.station_id] = {'munition_id': item.store_id, 'qty': 1}
                if preset.preset_id == 'cap':
                    break
        out[aid] = _aircraft_entry(aid, aid, st_list, defaults)
    return out


def _collect_f16(munitions: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """F-16：aircraft_loadout catalog。"""
    from utils.aircraft_loadout.catalog import build_aircraft_loadout_catalog_payload

    payload = build_aircraft_loadout_catalog_payload()
    for row in payload.get('stores') or []:
        _merge_munition(munitions, normalize_munition_record(
            str(row['id']),
            name=str(row.get('name') or row['id']),
            category=str(row.get('category') or ''),
            mass_kg=_f(row.get('mass_kg')),
            length_m=_f(row.get('length_m')) or None,
            diameter_m=_f(row.get('diameter_m')) or None,
            notes=str(row.get('notes') or ''),
        ))
    out: dict[str, dict[str, Any]] = {}
    stations_by_ac = payload.get('aircraft_stations') or {}
    presets = payload.get('presets') or []
    for aid, stations in stations_by_ac.items():
        # 取首个 block
        block = stations[0]['block'] if stations else ''
        block_stations = [s for s in stations if s.get('block') == block]
        st_list = []
        for st in block_stations:
            style = mount_style_from_hints(
                position=str(st.get('position') or ''),
                station_id=str(st.get('station_id') or ''),
            )
            st_list.append(_station(
                str(st['station_id']),
                str(st.get('position_label') or st['station_id']),
                style,
                list(st.get('allowed_stores') or []),
            ))
        defaults: dict[str, dict[str, Any]] = {}
        for preset in presets:
            if preset.get('aircraft_id') != aid:
                continue
            if preset.get('id') == 'a2a_cap' or not defaults:
                for sid, store_id in (preset.get('stations') or {}).items():
                    defaults[str(sid)] = {'munition_id': str(store_id), 'qty': 1}
                if preset.get('id') == 'a2a_cap':
                    break
        out[aid] = _aircraft_entry(aid, aid, st_list, defaults)
    return out


def _collect_fa50(munitions: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """FA-50：stores_catalog / hardpoints。"""
    from utils.stores.hardpoints import build_stores_catalog_payload

    payload = build_stores_catalog_payload()
    for row in payload.get('stores') or []:
        _merge_munition(munitions, normalize_munition_record(
            str(row['id']),
            name=str(row.get('name') or row['id']),
            category=str(row.get('category') or ''),
            mass_kg=_f(row.get('mass_kg')),
            notes=str(row.get('notes') or ''),
        ))
    out: dict[str, dict[str, Any]] = {}
    for ac in payload.get('aircraft') or []:
        aid = str(ac['aircraft_id'])
        st_list = []
        for st in ac.get('stations') or []:
            style = mount_style_from_hints(
                station_id=str(st.get('station_id') or ''),
                position=str(st.get('name') or ''),
            )
            options = []
            for a in st.get('allowed_stores') or []:
                sid = str(a['store_id'])
                max_c = int(a.get('max_count') or 1)
                for q in range(1, max_c + 1):
                    options.append({'munition_id': sid, 'qty': float(q)})
            st_list.append({
                'id': str(st['station_id']),
                'label': str(st.get('name') or st['station_id']),
                'mount_style': style,
                'options': options,
            })
        defaults: dict[str, dict[str, Any]] = {}
        for preset in ac.get('loadout_presets') or []:
            if preset.get('id') == 'fa50_a2a_tip' or not defaults:
                for item in preset.get('stations') or []:
                    defaults[str(item['station_id'])] = {
                        'munition_id': str(item['store_id']),
                        'qty': float(item.get('count') or 1),
                    }
                if preset.get('id') == 'fa50_a2a_tip':
                    break
        out[aid] = _aircraft_entry(aid, aid, st_list, defaults)
    return out


def _collect_fc1(munitions: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """FC-1 / JF-17。"""
    from utils.aircraft_stores import build_fc1_stores_payload

    payload = build_fc1_stores_payload()
    for sid, row in (payload.get('stores') or {}).items():
        _merge_munition(munitions, normalize_munition_record(
            str(sid),
            name=str(row.get('name') or sid),
            category=str(row.get('category') or ''),
            mass_kg=_f(row.get('mass_kg')),
            length_m=_f(row.get('length_m')) or None,
            diameter_m=_f(row.get('diameter_m')) or None,
            notes=str(row.get('notes') or ''),
        ))
    out: dict[str, dict[str, Any]] = {}
    for aid, groups in (payload.get('aircraft') or {}).items():
        # 展开物理挂点
        station_opts: dict[str, dict[str, Any]] = {}
        for group in groups:
            style = mount_style_from_hints(
                position=str(group.get('group') or ''),
                station_id=str(group.get('label') or ''),
            )
            for sid in group.get('station_ids') or []:
                sid_s = str(sid)
                if sid_s not in station_opts:
                    station_opts[sid_s] = {
                        'id': sid_s,
                        'label': f"{group.get('label') or '挂点'} {sid_s}",
                        'mount_style': style,
                        'options': [],
                    }
                for item in group.get('stores') or []:
                    mid = str(item['store_id'])
                    max_q = int(item.get('max_qty') or 1)
                    for q in range(1, max_q + 1):
                        station_opts[sid_s]['options'].append({
                            'munition_id': mid, 'qty': float(q),
                        })
        st_list = [station_opts[k] for k in sorted(station_opts, key=lambda x: int(x))]
        defaults = {}
        for sid in ('1', '7'):
            if sid in station_opts:
                opts = {o['munition_id'] for o in station_opts[sid]['options']}
                if 'pl5e2' in opts:
                    defaults[sid] = {'munition_id': 'pl5e2', 'qty': 1}
        for sid in ('3', '5'):
            if sid in station_opts:
                opts = {o['munition_id'] for o in station_opts[sid]['options']}
                if 'pl12' in opts:
                    defaults[sid] = {'munition_id': 'pl12', 'qty': 1}
        out[aid] = _aircraft_entry(aid, 'JF-17/FC-1', st_list, defaults)
    return out


def _collect_tejas(munitions: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """LCA Tejas。"""
    from utils.aircraft_hardpoints import hardpoints_for_aircraft
    from utils.database_csv import load_aircraft_hardpoints_csv

    rows = load_aircraft_hardpoints_csv()
    aircraft_ids = sorted({r['aircraft_id'] for r in rows})
    out: dict[str, dict[str, Any]] = {}
    for aid in aircraft_ids:
        entry = hardpoints_for_aircraft(aid)
        if not entry:
            continue
        for sid, store in (entry.get('stores') or {}).items():
            _merge_munition(munitions, normalize_munition_record(
                str(sid),
                name=str(store.get('name_zh') or store.get('name_en') or sid),
                category=str(store.get('category') or ''),
                mass_kg=_f(store.get('typical_mass_kg') or store.get('mass_kg')),
                notes=str(store.get('notes') or ''),
            ))
        st_list = []
        for st in entry.get('stations') or []:
            style = mount_style_from_hints(
                position=str(st.get('position') or ''),
                side=str(st.get('side') or ''),
                station_id=str(st.get('id') or ''),
            )
            st_list.append(_station(
                str(st['id']),
                str(st.get('name_zh') or st['id']),
                style,
                list(st.get('allowed_stores') or []),
            ))
        defaults = {}
        for st in st_list:
            opts = {o['munition_id'] for o in st['options']}
            if 'r73e' in opts and 'wtip' in st['id']:
                defaults[st['id']] = {'munition_id': 'r73e', 'qty': 1}
            elif 'derby' in opts and 'mid' in st['id']:
                defaults[st['id']] = {'munition_id': 'derby', 'qty': 1}
        out[aid] = _aircraft_entry(aid, aid, st_list, defaults)
    return out


def _collect_typhoon(munitions: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """台风。"""
    from utils.weapon_loadout.typhoon_stores import build_typhoon_stores_payload

    payload = build_typhoon_stores_payload()
    for row in payload.get('weapons') or []:
        _merge_munition(munitions, normalize_munition_record(
            str(row['id']),
            name=str(row.get('name') or row['id']),
            category=str(row.get('category') or ''),
            mass_kg=_f(row.get('mass_kg')),
            length_m=_f(row.get('length_m')) or None,
            diameter_m=_f(row.get('diameter_m')) or None,
            notes=str(row.get('notes') or ''),
        ))
    st_list = []
    for st in payload.get('stations') or []:
        if str(st.get('mount') or '') == 'fixed':
            continue
        style = mount_style_from_hints(mount=str(st.get('mount') or ''), station_id=str(st.get('id')))
        options = []
        for item in st.get('stores') or []:
            mid = str(item['weapon_id'])
            if _is_gun(str(item.get('category') or ''), mid, str(item.get('name') or '')):
                continue
            max_q = int(item.get('max_qty') or 1)
            for q in range(1, max_q + 1):
                options.append({'munition_id': mid, 'qty': float(q)})
        st_list.append({
            'id': str(st['id']),
            'label': str(st.get('name') or st['id']),
            'mount_style': style,
            'options': options,
        })
    defaults = {}
    for sid in ('1', '9'):
        if any(s['id'] == sid for s in st_list):
            defaults[sid] = {'munition_id': 'aim9', 'qty': 1}
    for sid in ('4', '6'):
        if any(s['id'] == sid for s in st_list):
            defaults[sid] = {'munition_id': 'amraam', 'qty': 1}
    return {
        'Typhoon': _aircraft_entry('Typhoon', '台风', st_list, defaults),
    }


def _collect_rafale(munitions: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """阵风 / 阵风 M。"""
    from utils.aircraft_mount.rafale_mount import build_rafale_mount_model

    for sid, spec in _RAFALE_STORE_SPECS.items():
        _merge_munition(munitions, normalize_munition_record(
            sid,
            name=str(spec['name']),
            category=str(spec.get('category') or ''),
            mass_kg=_f(spec.get('mass_kg')),
            length_m=_f(spec.get('length_m')) or None,
            diameter_m=_f(spec.get('diameter_m')) or None,
            dry_mass_kg=spec.get('dry_mass_kg'),
            fuel_kg=spec.get('fuel_kg'),
        ))
    model = build_rafale_mount_model()
    st_list = []
    for st in model.get('stations') or []:
        sid = str(st['station_id'])
        style = mount_style_from_hints(
            position=str(st.get('position') or ''),
            mount=str(st.get('store_mount') or ''),
            station_id=sid,
            side=str(st.get('side') or ''),
        )
        option_ids = [str(x['id']) for x in (model['stores_by_station'].get(sid) or [])]
        st_list.append(_station(
            sid,
            str(st.get('label_zh') or st.get('station_label') or sid),
            style,
            option_ids,
        ))
    defaults = {}
    for sid in ('WING_TIP_L', 'WING_TIP_R'):
        defaults[sid] = {'munition_id': 'mica_ir_ng', 'qty': 1}
    for sid in ('FWD_LAT_L', 'FWD_LAT_R', 'AFT_LAT_L', 'AFT_LAT_R'):
        defaults[sid] = {'munition_id': 'mica_em_ng', 'qty': 1}
    entry = _aircraft_entry('Rafale', '阵风', st_list, defaults)
    entry_m = _aircraft_entry('Rafale-M', '阵风 M', st_list, defaults)
    return {'Rafale': entry, 'Rafale-M': entry_m}


def _collect_gripen_cd(munitions: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """鹰狮 C/D。"""
    from utils.aircraft_weapons.catalog import build_aircraft_weapons_payload

    for sid, spec in _GRIPEN_CD_EXTRA.items():
        _merge_munition(munitions, normalize_munition_record(
            sid,
            name=str(spec['name']),
            category=str(spec.get('category') or ''),
            mass_kg=_f(spec.get('mass_kg')),
            length_m=_f(spec.get('length_m')) or None,
            diameter_m=_f(spec.get('diameter_m')) or None,
            dry_mass_kg=spec.get('dry_mass_kg'),
            fuel_kg=spec.get('fuel_kg'),
        ))
    payload = build_aircraft_weapons_payload()
    out: dict[str, dict[str, Any]] = {}
    for aid, ac in (payload.get('aircraft') or {}).items():
        st_list = []
        for st in ac.get('stations') or []:
            if str(st.get('id')) == 'G':
                continue
            option_ids: list[str] = []
            for cat in st.get('categories') or []:
                if _is_gun(str(cat.get('id') or ''), '', str(cat.get('label') or '')):
                    continue
                for w in cat.get('weapons') or []:
                    wid = str(w.get('id') or '')
                    if not wid or _is_gun(str(cat.get('id') or ''), wid, str(w.get('name') or '')):
                        continue
                    # 若武器尚未入库，用名称补一条
                    if wid not in munitions:
                        _merge_munition(munitions, normalize_munition_record(
                            wid,
                            name=str(w.get('name') or wid),
                            category=str(cat.get('id') or 'store'),
                            mass_kg=150.0,
                            notes=str(w.get('notes') or ''),
                        ))
                    option_ids.append(wid)
            style = mount_style_from_hints(
                station_id=str(st.get('id') or ''),
                position=str(st.get('name') or ''),
            )
            st_list.append(_station(
                str(st['id']),
                f"{st.get('id')} · {st.get('name')}",
                style,
                option_ids,
            ))
        defaults = {}
        for sid in ('1',):
            if any(s['id'] == sid for s in st_list):
                defaults[sid] = {'munition_id': 'iris_t', 'qty': 1}
        for sid in ('2', '3'):
            if any(s['id'] == sid for s in st_list):
                defaults[sid] = {'munition_id': 'aim120', 'qty': 1}
        out[aid] = _aircraft_entry(aid, aid, st_list, defaults)
    return out


def _collect_gripen_ef(munitions: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """鹰狮 E/F：类型令牌展开为代表性弹药；对称挂点拆成左右。"""
    from utils.aircraft_pylon import load_pylon_models

    # 确保类型映射里的弹药存在
    for mid in {x for opts in _GRIPEN_EF_TYPE_OPTIONS.values() for x in opts}:
        if mid in munitions:
            continue
        if mid in _GRIPEN_CD_EXTRA:
            spec = _GRIPEN_CD_EXTRA[mid]
            _merge_munition(munitions, normalize_munition_record(
                mid,
                name=str(spec['name']),
                category=str(spec.get('category') or ''),
                mass_kg=_f(spec.get('mass_kg')),
                length_m=_f(spec.get('length_m')) or None,
                diameter_m=_f(spec.get('diameter_m')) or None,
                dry_mass_kg=spec.get('dry_mass_kg'),
                fuel_kg=spec.get('fuel_kg'),
            ))
        elif mid == 'harpoon':
            _merge_munition(munitions, normalize_munition_record(
                'harpoon', name='Harpoon', category='asm',
                mass_kg=691, length_m=4.63, diameter_m=0.343,
            ))
    models = load_pylon_models()
    out: dict[str, dict[str, Any]] = {}
    for aid, stations in models.items():
        st_list = []
        for st in stations:
            base_id = str(st['station_id'])
            label = str(st.get('label') or base_id)
            style = mount_style_from_hints(
                position=str(st.get('position') or ''),
                station_id=base_id,
            )
            option_ids: list[str] = []
            for token in st.get('allowed_stores') or []:
                option_ids.extend(_GRIPEN_EF_TYPE_OPTIONS.get(str(token), []))
            # 去重保序
            seen: set[str] = set()
            uniq = []
            for mid in option_ids:
                if mid in seen or mid not in munitions:
                    continue
                seen.add(mid)
                uniq.append(mid)
            if st.get('symmetric'):
                for side, suffix in (('左', 'L'), ('右', 'R')):
                    st_list.append(_station(
                        f'{base_id}{suffix}',
                        f'{label}（{side}）',
                        style,
                        uniq,
                    ))
            else:
                st_list.append(_station(base_id, label, style, uniq))
        defaults = {}
        for sid in ('1L', '1R'):
            if any(s['id'] == sid for s in st_list):
                defaults[sid] = {'munition_id': 'iris_t', 'qty': 1}
        for sid in ('2L', '2R'):
            if any(s['id'] == sid for s in st_list):
                defaults[sid] = {'munition_id': 'aim120', 'qty': 1}
        out[aid] = _aircraft_entry(aid, aid, st_list, defaults)
    return out


def collect_fragment_munitions() -> dict[str, dict[str, Any]]:
    """收集碎片源产生的弹药（不含 JSON 主库）。"""
    munitions: dict[str, dict[str, Any]] = {}
    # 预置鹰狮/阵风规格，供后续引用
    for sid, spec in {**_GRIPEN_CD_EXTRA, **_RAFALE_STORE_SPECS}.items():
        _merge_munition(munitions, normalize_munition_record(
            sid,
            name=str(spec['name']),
            category=str(spec.get('category') or ''),
            mass_kg=_f(spec.get('mass_kg')),
            length_m=_f(spec.get('length_m')) or None,
            diameter_m=_f(spec.get('diameter_m')) or None,
            dry_mass_kg=spec.get('dry_mass_kg'),
            fuel_kg=spec.get('fuel_kg'),
        ))
    collectors = (
        _collect_mig29,
        _collect_f14,
        _collect_f16,
        _collect_fa50,
        _collect_fc1,
        _collect_tejas,
        _collect_typhoon,
        _collect_rafale,
        _collect_gripen_cd,
        _collect_gripen_ef,
    )
    for fn in collectors:
        fn(munitions)
    return munitions


def collect_fragment_aircraft() -> dict[str, dict[str, Any]]:
    """收集碎片机型挂点定义（不含 JSON 主库已有机型）。"""
    munitions: dict[str, dict[str, Any]] = {}
    for sid, spec in {**_GRIPEN_CD_EXTRA, **_RAFALE_STORE_SPECS}.items():
        _merge_munition(munitions, normalize_munition_record(
            sid,
            name=str(spec['name']),
            category=str(spec.get('category') or ''),
            mass_kg=_f(spec.get('mass_kg')),
            length_m=_f(spec.get('length_m')) or None,
            diameter_m=_f(spec.get('diameter_m')) or None,
            dry_mass_kg=spec.get('dry_mass_kg'),
            fuel_kg=spec.get('fuel_kg'),
        ))
    aircraft: dict[str, dict[str, Any]] = {}
    for fn in (
        _collect_mig29,
        _collect_f14,
        _collect_f16,
        _collect_fa50,
        _collect_fc1,
        _collect_tejas,
        _collect_typhoon,
        _collect_rafale,
        _collect_gripen_cd,
        _collect_gripen_ef,
    ):
        part = fn(munitions)
        for aid, entry in part.items():
            # 主库优先：调用方负责跳过已有 id
            aircraft[aid] = entry
    return aircraft


def merge_munitions(
    base: dict[str, dict[str, Any]],
    extra: dict[str, dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    """主库弹药 + 碎片弹药。"""
    out = {k: dict(v) for k, v in base.items()}
    for mid, row in (extra if extra is not None else collect_fragment_munitions()).items():
        _merge_munition(out, row)
    return out


def merge_aircraft_stations(
    base_root: dict[str, Any],
    extra: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """主库挂点 JSON + 碎片机型（不覆盖主库已有 id）。"""
    root = {
        'version': int(base_root.get('version') or 1),
        'aircraft': {
            aid: dict(entry)
            for aid, entry in (base_root.get('aircraft') or {}).items()
        },
    }
    fragment = extra if extra is not None else collect_fragment_aircraft()
    for aid, entry in fragment.items():
        if aid in root['aircraft']:
            continue
        root['aircraft'][aid] = entry
    return root
