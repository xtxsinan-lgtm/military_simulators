#!/usr/bin/env python3
"""合并 PR 时自动处理生成物与挂载数据冲突。"""
from __future__ import annotations

import csv
import json
import subprocess
import sys
from io import StringIO
from pathlib import Path

GENERATED = {
    'data/combat_radius_results.json',
    'docs/data.json',
    'ios/CarrierTakeOff/Resources/data.json',
    'miniprogram/data/data.js',
    'miniprogram/data/data.json',
}

DATA_MERGE = {
    'data/aircraft_stations_database.json',
    'docs/py/data/aircraft_stations_database.json',
}

CSV_MERGE = {
    'data/munitions_database.csv',
    'docs/py/data/munitions_database.csv',
}

AIRCRAFT_CSV = 'data/aircraft_database.csv'

SYNC_PAIRS = [
    ('utils/combat_radius/loadout.py', 'docs/py/utils/combat_radius/loadout.py'),
    ('data/aircraft_stations_database.json', 'docs/py/data/aircraft_stations_database.json'),
    ('data/munitions_database.csv', 'docs/py/data/munitions_database.csv'),
]


def git_show(ref: str, path: str) -> str:
    return subprocess.check_output(['git', 'show', f'{ref}:{path}'], text=True)


def conflicted_files() -> list[str]:
    out = subprocess.check_output(['git', 'diff', '--name-only', '--diff-filter=U'], text=True)
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


def merge_json_aircraft(path: str) -> None:
    ours = json.loads(git_show('HEAD', path))
    theirs = json.loads(git_show('MERGE_HEAD', path))
    merged_aircraft = dict(ours.get('aircraft', {}))
    for k, v in theirs.get('aircraft', {}).items():
        if k not in merged_aircraft:
            merged_aircraft[k] = v
    out = {
        'version': max(int(ours.get('version', 1)), int(theirs.get('version', 1))),
        'aircraft': merged_aircraft,
    }
    Path(path).write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def _normalize_csv_fieldnames(fieldnames: list[str]) -> list[str]:
    if fieldnames and fieldnames[0].startswith('\ufeff'):
        fieldnames[0] = fieldnames[0].lstrip('\ufeff')
    return fieldnames


def _row_id(row: dict[str, str]) -> str:
    return row.get('id') or row.get('\ufeffid', '')


def merge_aircraft_csv(path: str) -> None:
    """按 id 合并机型 CSV：已有行保留 HEAD（含浸润倒推），新机型从 MERGE_HEAD 追加。"""
    def read_rows(ref: str) -> tuple[list[str], list[dict[str, str]], dict[str, dict[str, str]]]:
        text = git_show(ref, path)
        if text.startswith('\ufeff'):
            text = text.lstrip('\ufeff')
        reader = csv.DictReader(StringIO(text))
        fieldnames = _normalize_csv_fieldnames(list(reader.fieldnames or []))
        rows: list[dict[str, str]] = []
        by_id: dict[str, dict[str, str]] = {}
        for raw in reader:
            row = {_normalize_csv_fieldnames([k])[0] if k.startswith('\ufeff') else k: v for k, v in raw.items()}
            aid = _row_id(row)
            rows.append(row)
            by_id[aid] = row
        return fieldnames, rows, by_id

    fieldnames, ours_rows, ours_map = read_rows('HEAD')
    _, theirs_rows, theirs_map = read_rows('MERGE_HEAD')
    merged_map = dict(ours_map)
    for aid, row in theirs_map.items():
        if aid not in merged_map:
            merged_map[aid] = row
    out_rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in ours_rows:
        aid = _row_id(row)
        out_rows.append(merged_map[aid])
        seen.add(aid)
    for row in theirs_rows:
        aid = _row_id(row)
        if aid not in seen:
            out_rows.append(merged_map[aid])
            seen.add(aid)
    buf = StringIO()
    w = csv.DictWriter(buf, fieldnames=fieldnames, lineterminator='\n')
    w.writeheader()
    for row in out_rows:
        w.writerow(row)
    Path(path).write_text(buf.getvalue(), encoding='utf-8')


def merge_csv(path: str) -> None:
    def read_map(ref: str) -> tuple[list[str], dict[str, dict[str, str]]]:
        text = git_show(ref, path)
        reader = csv.DictReader(StringIO(text))
        fieldnames = list(reader.fieldnames or [])
        return fieldnames, {r['id']: r for r in reader}

    fieldnames, ours_map = read_map('HEAD')
    _, theirs_map = read_map('MERGE_HEAD')
    merged = dict(ours_map)
    for k, v in theirs_map.items():
        if k not in merged:
            merged[k] = v
    buf = StringIO()
    w = csv.DictWriter(buf, fieldnames=fieldnames, lineterminator='\n')
    w.writeheader()
    for row in merged.values():
        w.writerow(row)
    Path(path).write_text(buf.getvalue(), encoding='utf-8')


def checkout_ours(path: str) -> None:
    subprocess.check_call(['git', 'checkout', '--ours', path])
    subprocess.check_call(['git', 'add', path])


def sync_docs_copies() -> None:
    for src, dst in SYNC_PAIRS:
        if Path(src).exists():
            Path(dst).write_text(Path(src).read_text(encoding='utf-8'), encoding='utf-8')
            subprocess.check_call(['git', 'add', src, dst])


def main() -> int:
    manual: list[str] = []
    for path in conflicted_files():
        if path in GENERATED:
            checkout_ours(path)
        elif path in DATA_MERGE or path.endswith('aircraft_stations_database.json'):
            merge_json_aircraft(path)
            subprocess.check_call(['git', 'add', path])
        elif path == AIRCRAFT_CSV:
            merge_aircraft_csv(path)
            subprocess.check_call(['git', 'add', path])
        elif path in CSV_MERGE or path.endswith('munitions_database.csv'):
            merge_csv(path)
            subprocess.check_call(['git', 'add', path])
        elif path == 'utils/combat_radius/loadout.py':
            manual.append(path)
        elif path == 'docs/py/utils/combat_radius/loadout.py':
            manual.append(path)
        elif path == 'miniprogram/pages/combat_radius/combat_radius.js':
            manual.append(path)
        else:
            manual.append(path)

    sync_docs_copies()

    if manual:
        print('MANUAL CONFLICTS:', *manual, sep='\n  ')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
