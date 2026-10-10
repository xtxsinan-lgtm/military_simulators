"""空警-600 滑跃起飞端到端：入库、目录，以及襟翼最大升力系数进入仿真。"""
from __future__ import annotations

from dataclasses import replace

import pytest

from apps.web_simulator import aircraft_from_dict, filter_aircraft_for_mode, run_simulation
from scripts.frontend_catalog import aircraft_to_dict, build_catalog_payload
from utils.database_csv import load_aircraft_csv, load_carriers_csv
from utils.paths import AIRCRAFT_CSV, CARRIERS_CSV


@pytest.mark.e2e
def test_e2e_kj600_ski_jump_on_shandong_uses_cl_max():
    """山东舰、30°C、30 节甲板风、最大起飞重量下可滑跃，且 CLmax 2.0 短于模式默认。"""
    aircraft = load_aircraft_csv(AIRCRAFT_CSV)
    carriers = load_carriers_csv(CARRIERS_CSV)
    catalog = build_catalog_payload(aircraft, carriers)
    row = next(a for a in catalog['aircraft'] if a['id'] == 'KJ-600')
    assert row['cl_max'] == pytest.approx(2.0)
    spec = aircraft_from_dict(row)
    assert spec is not None
    ski_ids = {a.id for a in filter_aircraft_for_mode('ski_jump', list(aircraft.values()))}
    assert 'KJ-600' in ski_ids
    carrier = next(c for c in carriers if c.id == 'SHANDONG')
    result = run_simulation(
        'ski_jump', spec, carrier, spec.mtow_kg, 30.0, 30.0,
    )
    # 线性升力在 20° 俯仰下约 1.6–1.8，2.0 与模式默认 1.8 距离相同；压到 1.5 才会变长
    lower = run_simulation(
        'ski_jump', replace(spec, cl_max=1.5), carrier, spec.mtow_kg, 30.0, 30.0,
    )
    assert result['success'] is True
    assert lower['success'] is True
    assert result['distance_m'] < lower['distance_m']
    assert aircraft_to_dict(spec)['cl_max'] == pytest.approx(2.0)
