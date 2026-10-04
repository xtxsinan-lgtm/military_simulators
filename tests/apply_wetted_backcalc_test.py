"""浸润倒推写回脚本的单元测试。"""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

from scripts.apply_wetted_backcalc import (
    CALIBRATION,
    _append_note,
    _fmt,
    _swet_with_section,
    apply,
    build_geometry_for_row,
)
from utils.combat_radius.wetted_backcalc import length_segments_from_aircraft_length
from utils.paths import AIRCRAFT_CSV


def test_append_note_replaces_previous_backcalc_block():
    """重复写入时只保留一段浸润倒推说明。"""
    old = '陆基；浸润倒推：旧说明'
    new = _append_note(old, '新说明')
    assert new.count('浸润倒推：') == 1
    assert '新说明' in new
    assert '旧说明' not in new


def test_fmt_float_and_empty():
    """CSV 格式化去掉多余零，空值保持空串。"""
    assert _fmt(1.5) == '1.5'
    assert _fmt(2.0) == '2'
    assert _fmt('') == ''
    assert _fmt(None) == ''


def test_swet_with_section_positive():
    """锁定截面时浸润分解为正。"""
    segs = length_segments_from_aircraft_length(15.0)
    total, detail = _swet_with_section(
        segs=segs, width_m=1.6, height_m=1.4,
        cone_to_width=0.36, root_to_width=0.60,
        lifting={'main_wing_area_m2': 20.0, 'vtail_area_m2': 4.0},
    )
    assert total > 0
    assert detail['box_wetted_m2'] > 0
    assert detail['lifting_wetted_m2'] == pytest.approx(48.0)


def test_build_geometry_for_f16_hits_jsbsim_target():
    """F-16 校准行倒推后总浸润接近 JSBSim 锚点。"""
    with AIRCRAFT_CSV.open(encoding='utf-8-sig', newline='') as fh:
        row = next(r for r in csv.DictReader(fh) if r['id'] == 'F-16')
    geom = build_geometry_for_row(row, CALIBRATION['F-16'])
    assert geom['_total_swet_m2'] == pytest.approx(130.4, abs=0.3)
    assert geom['main_wing_area_m2'] == pytest.approx(15.85)
    assert geom['ventral_fin_area_m2'] == pytest.approx(1.42)


def test_apply_dry_run_does_not_rewrite_csv(tmp_path: Path):
    """dry-run 不修改目标 CSV。"""
    sample = tmp_path / 'ac.csv'
    sample.write_text(AIRCRAFT_CSV.read_text(encoding='utf-8-sig'), encoding='utf-8-sig')
    before = sample.read_text(encoding='utf-8-sig')
    summaries = apply(sample, dry_run=True)
    assert sample.read_text(encoding='utf-8-sig') == before
    assert any(s['id'] == 'F-16' for s in summaries)
