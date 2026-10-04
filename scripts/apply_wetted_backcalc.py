#!/usr/bin/env python3
"""按公开航程/作战半径锚点与构型尺寸，倒推并写回机型分段浸润几何。

优先锁定三面图/公开机身宽高；在此约束下用升力面与（可选）小幅宽高校准
对齐目标 S_wet。若未给锁定截面，则按宽高比反解盒段。

用法：
    python3 scripts/apply_wetted_backcalc.py
    python3 scripts/apply_wetted_backcalc.py --dry-run
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from utils.combat_radius.lift_drag import (
    box_surface_area_m2,
    cone_lateral_area_m2,
    frustum_lateral_area_m2,
)
from utils.combat_radius.wetted_backcalc import (
    geometry_dict_for_csv,
    iterate_fuse_dims_with_nose_scale,
    length_segments_from_aircraft_length,
    lifting_wetted_from_planforms,
    scale_nose_diameters_to_fuse_width,
)
from utils.paths import AIRCRAFT_CSV

# 目标 S_wet 来源：
# 1) F-16：JSBSim 部件和 ≈130.4 m²（硬锚）
# 2) 其余：公开航程/作战半径（去掉明显副油箱宣传值）+ 模型巡航 TSFC 量级
#    反推所需 L/D，再映射到合理 S_wet/S_ref（约 3.8–6.0），并受三面图截面约束。
CALIBRATION: dict[str, dict[str, Any]] = {
    'F-16': {
        'target_swet_m2': 130.4,
        'fuse_width_m': 1.55,
        'fuse_height_m': 1.40,
        'cone_to_width': 0.38,
        'root_to_width': 0.62,
        'lifting': {
            'main_wing_area_m2': 15.85,
            'canard_htail_area_m2': 5.92,
            'ventral_fin_area_m2': 1.42,
            'vtail_area_m2': 5.09,
        },
        # 截面锁定后若低于目标，允许把宽高当作等效矩形截面微调
        'allow_section_scale': True,
        'note': (
            'JSBSim 总浸润≈130.4 m²；平尾 Aerospaceweb 63.7 ft²；'
            '垂尾 JSBSim 54.75 ft²；腹鳍 JSBSim；主翼暴露≈15.85 m²；'
            '机身截面按细长单发等效矩形倒推'
        ),
    },
    'FA-18C': {
        'target_swet_m2': 210.0,
        'fuse_width_m': 2.45,
        'fuse_height_m': 1.55,
        'cone_to_width': 0.34,
        'root_to_width': 0.58,
        'lifting': {
            'main_wing_area_m2': 28.5,
            'canard_htail_area_m2': 8.0,
            'vtail_area_m2': 9.2,
        },
        'allow_section_scale': True,
        'note': (
            'Aerospaceweb 空优航程约 800 nmi；内油+4 弹模型锚≈900–950 km；'
            '双发舰载截面；边条计入主翼暴露；S_wet≈210 m²'
        ),
    },
    'FA-18E': {
        'target_swet_m2': 258.0,
        'fuse_width_m': 2.85,
        'fuse_height_m': 1.70,
        'cone_to_width': 0.34,
        'root_to_width': 0.58,
        'lifting': {
            'main_wing_area_m2': 35.0,
            'canard_htail_area_m2': 9.8,
            'vtail_area_m2': 12.0,
        },
        'allow_section_scale': True,
        'note': (
            '相对 FA-18C 加长加宽、内油 6667 kg；'
            '按尺寸比放大浸润至≈258 m²'
        ),
    },
    'F-14': {
        'target_swet_m2': 290.0,
        'fuse_width_m': 3.20,
        'fuse_height_m': 1.75,
        'cone_to_width': 0.32,
        'root_to_width': 0.55,
        'lifting': {
            'main_wing_area_m2': 36.5,
            'canard_htail_area_m2': 12.0,
            'vtail_area_m2': 10.5,
        },
        'allow_section_scale': True,
        'note': (
            '变后掠宽机身；公开作战半径约 500 nmi；'
            '前掠构型 S_wet≈290 m²'
        ),
    },
    'F-15E': {
        'target_swet_m2': 290.0,
        'fuse_width_m': 3.25,
        'fuse_height_m': 1.88,
        'cone_to_width': 0.33,
        'root_to_width': 0.58,
        'lifting': {
            'main_wing_area_m2': 40.0,
            'canard_htail_area_m2': 10.35,
            'vtail_area_m2': 9.78,
        },
        'allow_section_scale': True,
        'note': (
            '含保形油箱加宽；内油 10100 kg；'
            '公开约 1270 km → S_wet≈290 m²'
        ),
    },
    'L-15B': {
        'target_swet_m2': 112.0,
        'fuse_width_m': 1.42,
        'fuse_height_m': 1.38,
        'cone_to_width': 0.38,
        'root_to_width': 0.62,
        'lifting': {
            'main_wing_area_m2': 17.0,
            'canard_htail_area_m2': 4.6,
            'vtail_area_m2': 3.2,
        },
        'allow_section_scale': True,
        'note': (
            '高级教练/轻战；内油约 1.7 t；'
            '小截面；公开航程多含副油箱；S_wet≈112 m²'
        ),
    },
    'FC-1': {
        'target_swet_m2': 128.0,
        'fuse_width_m': 1.55,
        'fuse_height_m': 1.42,
        'cone_to_width': 0.38,
        'root_to_width': 0.62,
        'lifting': {
            'main_wing_area_m2': 17.2,
            'canard_htail_area_m2': 5.2,
            'vtail_area_m2': 4.0,
        },
        'allow_section_scale': True,
        'note': (
            '枭龙；宣传半径常含副油箱；'
            '内油 2449 kg 模型锚≈780–820 km；DSI；S_wet≈128 m²'
        ),
    },
    'J-10C': {
        'target_swet_m2': 175.0,
        'fuse_width_m': 1.95,
        'fuse_height_m': 1.50,
        'cone_to_width': 0.36,
        'root_to_width': 0.60,
        'lifting': {
            'main_wing_area_m2': 26.5,
            'canard_htail_area_m2': 4.9,
            'ventral_fin_area_m2': 1.7,
            'vtail_area_m2': 5.5,
        },
        'allow_section_scale': True,
        'note': (
            '三角翼鸭式；补单垂尾≈5.5 m²；'
            '公开约 1100–1200 km 多含副油箱；内油模型 S_wet≈175 m²'
        ),
    },
    'MiG-29K': {
        'target_swet_m2': 190.0,
        'fuse_width_m': 2.35,
        'fuse_height_m': 1.55,
        'cone_to_width': 0.34,
        'root_to_width': 0.58,
        'lifting': {
            'main_wing_area_m2': 24.0,
            'canard_htail_area_m2': 8.5,
            'ventral_fin_area_m2': 1.8,
            'vtail_area_m2': 7.2,
        },
        'allow_section_scale': True,
        'note': (
            '双发舰载；公开约 850 km；'
            'S_wet≈190 m²'
        ),
    },
    'J-15T': {
        'target_swet_m2': 348.0,
        'fuse_width_m': 3.55,
        'fuse_height_m': 1.88,
        'cone_to_width': 0.33,
        'root_to_width': 0.56,
        'lifting': {
            'main_wing_area_m2': 46.0,
            'canard_htail_area_m2': 13.0,
            'ventral_fin_area_m2': 2.6,
            'vtail_area_m2': 11.0,
        },
        'allow_section_scale': True,
        'also_update': ['J-15'],
        'note': (
            '侧卫舰载弹射型；几何同歼-15；'
            '内油 10 t，公开约 1270 km；S_wet≈348 m²'
        ),
    },
    'Rafale-M': {
        'target_swet_m2': 192.0,
        'fuse_width_m': 2.40,
        'fuse_height_m': 1.55,
        'cone_to_width': 0.34,
        'root_to_width': 0.57,
        'lifting': {
            'main_wing_area_m2': 34.0,
            'canard_htail_area_m2': 5.5,
            'vtail_area_m2': 6.3,
        },
        'allow_section_scale': True,
        'note': (
            '近距耦合鸭式；宣传 1850 km 多含副油箱；'
            '内油 4700 kg 模型锚≈1000 km；S_wet≈192 m²'
        ),
    },
    'Typhoon': {
        'target_swet_m2': 200.0,
        'fuse_width_m': 2.25,
        'fuse_height_m': 1.62,
        'cone_to_width': 0.34,
        'root_to_width': 0.58,
        'lifting': {
            'main_wing_area_m2': 39.5,
            'canard_htail_area_m2': 2.4,
            'vtail_area_m2': 7.8,
        },
        'allow_section_scale': True,
        'note': (
            '公开 1389 km 多含副油箱；前翼 2.4 m² 为厂家值；'
            '内油 4500 kg 模型锚≈1000–1050 km；S_wet≈200 m²'
        ),
    },
    'Gripen-CD': {
        'target_swet_m2': 132.0,
        'fuse_width_m': 1.55,
        'fuse_height_m': 1.42,
        'cone_to_width': 0.38,
        'root_to_width': 0.62,
        'lifting': {
            'main_wing_area_m2': 19.0,
            'canard_htail_area_m2': 4.5,
            'vtail_area_m2': 4.0,
        },
        'allow_section_scale': True,
        'note': (
            '公开约 800 km；鸭翼约 4.5 m²；'
            'S_wet≈132 m²'
        ),
    },
    'Gripen-EF': {
        'target_swet_m2': 130.0,
        'fuse_width_m': 1.55,
        'fuse_height_m': 1.42,
        'cone_to_width': 0.38,
        'root_to_width': 0.62,
        'lifting': {
            'main_wing_area_m2': 20.4,
            'canard_htail_area_m2': 4.6,
            'vtail_area_m2': 4.2,
        },
        'allow_section_scale': True,
        'note': (
            '相对 C 型加长、内油 3400 kg；'
            '宣传 1500 km 含副油箱；内油模型 S_wet≈130 m²'
        ),
    },
    'Mirage-2000': {
        # 无尾细长机身 S_wet/S_ref 天然偏低；不靠虚高截面抬浸润
        'target_swet_m2': 148.0,
        'fuse_width_m': 1.55,
        'fuse_height_m': 1.42,
        'cone_to_width': 0.38,
        'root_to_width': 0.62,
        'lifting': {
            'main_wing_area_m2': 31.0,
            'vtail_area_m2': 5.8,
        },
        'allow_section_scale': True,
        'max_section_scale': 1.15,
        'note': (
            '无尾三角细长机身；公开含副油箱航程不直接用；'
            '按真实细长截面+大三角暴露翼得 S_wet≈148 m²'
        ),
    },
    'FA-50': {
        'target_swet_m2': 120.0,
        'fuse_width_m': 1.50,
        'fuse_height_m': 1.40,
        'cone_to_width': 0.38,
        'root_to_width': 0.62,
        'lifting': {
            'main_wing_area_m2': 16.5,
            'canard_htail_area_m2': 4.8,
            'vtail_area_m2': 3.2,
        },
        'allow_section_scale': True,
        'max_section_scale': 1.20,
        'note': (
            '轻型战斗机；空重低使内油剖面半径不低；'
            '按小截面 S_wet≈120 m²（公开对地半径更短）'
        ),
    },
    'KF-21': {
        'target_swet_m2': 245.0,
        'fuse_width_m': 3.20,
        'fuse_height_m': 1.80,
        'cone_to_width': 0.30,
        'root_to_width': 0.52,
        'lifting': {
            'main_wing_area_m2': 32.0,
            'canard_htail_area_m2': 9.0,
            'vtail_area_m2': 11.0,
        },
        'allow_section_scale': True,
        'note': (
            '双发常规+DSI；Block I 外挂中距弹；'
            '内油 5400 kg；S_wet≈245 m²'
        ),
    },
}


def _fmt(value: Any) -> str:
    """CSV 单元格：空值保持空，浮点去多余零。"""
    if value in (None, ''):
        return ''
    if isinstance(value, float):
        text = f'{value:.4f}'.rstrip('0').rstrip('.')
        return text
    return str(value)


def _append_note(old: str, extra: str) -> str:
    """把倒推说明合并进 notes，避免重复堆叠。"""
    marker = '浸润倒推：'
    base = old or ''
    if marker in base:
        head, _sep, _rest = base.partition(marker)
        base = head.rstrip('；').rstrip(';').rstrip()
    piece = f'{marker}{extra}'
    if not base:
        return piece
    if base.endswith('；') or base.endswith(';'):
        return f'{base}{piece}'
    return f'{base}；{piece}'


def _swet_with_section(
    *,
    segs: dict[str, float],
    width_m: float,
    height_m: float,
    cone_to_width: float,
    root_to_width: float,
    lifting: dict[str, float],
) -> tuple[float, dict[str, float]]:
    """给定截面计算总浸润与机头直径。"""
    nose_d = scale_nose_diameters_to_fuse_width(
        width_m, cone_to_width=cone_to_width, root_to_width=root_to_width,
    )
    nose = (
        cone_lateral_area_m2(segs['nose_cone_length_m'], nose_d['nose_cone_diameter_m'])
        + frustum_lateral_area_m2(
            segs['nose_length_m'],
            nose_d['nose_cone_diameter_m'],
            nose_d['nose_root_diameter_m'],
        )
    )
    box = box_surface_area_m2(
        segs['fuse_body_length_m'], width_m, height_m,
    )
    lift = lifting_wetted_from_planforms(
        float(lifting.get('main_wing_area_m2') or 0.0),
        float(lifting.get('canard_htail_area_m2') or 0.0),
        float(lifting.get('ventral_fin_area_m2') or 0.0),
        float(lifting.get('vtail_area_m2') or 0.0),
    )
    total = nose + box + lift
    detail = {
        **segs,
        **nose_d,
        'fuse_width_m': round(width_m, 3),
        'fuse_height_m': round(height_m, 3),
        'nose_wetted_m2': nose,
        'box_wetted_m2': box,
        'lifting_wetted_m2': lift,
        'total_swet_m2': total,
    }
    return total, detail


def build_geometry_for_row(row: dict[str, str], spec: dict[str, Any]) -> dict[str, Any]:
    """对单行机型倒推分段几何字段。"""
    length_m = float(row['length_m'])
    segs = length_segments_from_aircraft_length(length_m)
    lifting = dict(spec['lifting'])
    target = float(spec['target_swet_m2'])
    cone_r = float(spec.get('cone_to_width', 0.36))
    root_r = float(spec.get('root_to_width', 0.60))

    if spec.get('fuse_width_m') and spec.get('fuse_height_m'):
        w0 = float(spec['fuse_width_m'])
        h0 = float(spec['fuse_height_m'])
        total0, detail0 = _swet_with_section(
            segs=segs, width_m=w0, height_m=h0,
            cone_to_width=cone_r, root_to_width=root_r, lifting=lifting,
        )
        if spec.get('allow_section_scale') and abs(total0 - target) > 0.8:
            # 等比缩放截面使盒段+机头对齐目标（升力面固定）
            # 先用宽高比反解
            wh = w0 / h0
            calc = iterate_fuse_dims_with_nose_scale(
                target,
                nose_cone_length_m=segs['nose_cone_length_m'],
                nose_length_m=segs['nose_length_m'],
                fuse_body_length_m=segs['fuse_body_length_m'],
                main_wing_area_m2=float(lifting.get('main_wing_area_m2') or 0.0),
                canard_htail_area_m2=float(lifting.get('canard_htail_area_m2') or 0.0),
                ventral_fin_area_m2=float(lifting.get('ventral_fin_area_m2') or 0.0),
                vtail_area_m2=float(lifting.get('vtail_area_m2') or 0.0),
                width_height_ratio=wh,
                cone_to_width=cone_r,
                root_to_width=root_r,
                seed_width_m=w0,
            )
            max_scale = float(spec.get('max_section_scale', 1.25))
            min_scale = float(spec.get('min_section_scale', 0.85))
            scale_w = calc['fuse_width_m'] / w0
            if scale_w > max_scale or scale_w < min_scale:
                # 超出外形可信区间：夹紧截面，接受 S_wet 偏差
                scale = max(min_scale, min(max_scale, scale_w))
                total, detail = _swet_with_section(
                    segs=segs, width_m=w0 * scale, height_m=h0 * scale,
                    cone_to_width=cone_r, root_to_width=root_r, lifting=lifting,
                )
                calc = detail
                calc['total_swet_m2'] = total
            # else use calc as-is
        else:
            calc = detail0
    else:
        wh = float(spec['wh_ratio'])
        calc = iterate_fuse_dims_with_nose_scale(
            target,
            nose_cone_length_m=segs['nose_cone_length_m'],
            nose_length_m=segs['nose_length_m'],
            fuse_body_length_m=segs['fuse_body_length_m'],
            main_wing_area_m2=float(lifting.get('main_wing_area_m2') or 0.0),
            canard_htail_area_m2=float(lifting.get('canard_htail_area_m2') or 0.0),
            ventral_fin_area_m2=float(lifting.get('ventral_fin_area_m2') or 0.0),
            vtail_area_m2=float(lifting.get('vtail_area_m2') or 0.0),
            width_height_ratio=wh,
            cone_to_width=cone_r,
            root_to_width=root_r,
            seed_width_m=float(row.get('fuse_width_m') or 2.0),
        )

    geom = geometry_dict_for_csv(calc, lifting)
    geom['_total_swet_m2'] = calc['total_swet_m2']
    geom['_note'] = spec['note']
    return geom


def apply(csv_path: Path, *, dry_run: bool = False) -> list[dict[str, Any]]:
    """写回 CSV；返回变更摘要。"""
    with csv_path.open(encoding='utf-8-sig', newline='') as fh:
        reader = csv.DictReader(fh)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    by_id = {r['id']: r for r in rows}
    summaries: list[dict[str, Any]] = []
    updates: dict[str, dict[str, Any]] = {}

    for aid, spec in CALIBRATION.items():
        if aid not in by_id:
            raise KeyError(f'机型库缺少 {aid}')
        geom = build_geometry_for_row(by_id[aid], spec)
        targets = [aid] + list(spec.get('also_update') or [])
        for tid in targets:
            if tid not in by_id:
                raise KeyError(f'同步目标机型缺少 {tid}')
            updates[tid] = geom
            summaries.append({
                'id': tid,
                'source': aid,
                'swet': geom['_total_swet_m2'],
                'target': float(spec['target_swet_m2']),
                'fuse_w': geom['fuse_width_m'],
                'fuse_h': geom['fuse_height_m'],
                'main_wing': geom['main_wing_area_m2'],
            })

    for tid, geom in updates.items():
        row = by_id[tid]
        for key in (
            'nose_cone_length_m', 'nose_cone_diameter_m', 'nose_length_m',
            'nose_root_diameter_m', 'fuse_body_length_m', 'fuse_width_m',
            'fuse_height_m', 'main_wing_area_m2', 'canard_htail_area_m2',
            'ventral_fin_area_m2', 'vtail_area_m2',
        ):
            row[key] = _fmt(geom[key])
        row['notes'] = _append_note(row.get('notes') or '', geom['_note'])

    if not dry_run:
        with csv_path.open('w', encoding='utf-8-sig', newline='') as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames, lineterminator='\n')
            writer.writeheader()
            writer.writerows(rows)
    return summaries


def main() -> None:
    parser = argparse.ArgumentParser(description='倒推并写回分段浸润几何')
    parser.add_argument('--dry-run', action='store_true', help='只打印不写文件')
    parser.add_argument('--csv', type=Path, default=AIRCRAFT_CSV)
    args = parser.parse_args()
    summaries = apply(args.csv, dry_run=args.dry_run)
    print(f"{'id':10} {'Swet':>7} {'tgt':>7} {'W':>6} {'H':>6} {'main':>6}")
    for s in summaries:
        print(
            f"{s['id']:10} {s['swet']:7.1f} {s['target']:7.1f} "
            f"{s['fuse_w']:6.3f} {s['fuse_h']:6.3f} {s['main_wing']:6.2f}"
        )
    print(('dry-run OK' if args.dry_run else f'wrote {args.csv}') + f' ({len(summaries)} rows)')


if __name__ == '__main__':
    main()
