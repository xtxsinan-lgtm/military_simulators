"""浸润倒推后的作战半径端到端：目标机型可算且网页目录含几何。"""
from __future__ import annotations

import pytest

from apps.combat_radius_web import run_combat_radius_json
from scripts.frontend_catalog import build_catalog_payload
from utils.combat_radius.combat_radius_presets import (
    get_preset_by_id,
    load_presets,
    preset_to_aircraft,
)
from utils.combat_radius.combat_radius_results import run_preset_dashboard
from utils.combat_radius.lift_drag import geometric_wetted_area_m2
from utils.database_csv import load_aircraft_csv, load_carriers_csv
from utils.paths import AIRCRAFT_CSV, CARRIERS_CSV

_BACKCALC_IDS = (
    'F-16', 'FA-18C', 'FA-18E', 'F-14', 'F-15E', 'L-15B', 'FC-1', 'J-10C',
    'MiG-29K', 'J-15T', 'Rafale-M', 'Typhoon', 'Gripen-CD', 'Gripen-EF',
    'Mirage-2000', 'FA-50', 'KF-21',
)


@pytest.mark.e2e
def test_e2e_wetted_backcalc_fleet_combat_radius_and_catalog():
    """倒推几何后各机进入作战半径，Ma 0.8 半径可算，目录含分段字段。"""
    presets = load_presets()
    aircraft = load_aircraft_csv(AIRCRAFT_CSV)
    catalog = build_catalog_payload(aircraft, load_carriers_csv(CARRIERS_CSV))
    cr_ids = {p['id'] for p in catalog['combat_radius_presets']}

    for aid in _BACKCALC_IDS:
        assert aid in cr_ids, aid
        tgt = get_preset_by_id(presets, aid)
        assert tgt is not None, aid
        assert tgt['nose_cone_length_m'] > 0, aid
        assert tgt['fuse_width_m'] > 0, aid
        assert tgt['main_wing_area_m2'] > 0, aid
        ac = preset_to_aircraft(tgt)
        swet = geometric_wetted_area_m2(ac)
        assert 80.0 < swet < 400.0, (aid, swet)
        ld = run_combat_radius_json({'action': 'predict_ld', 'params': {'target': tgt}})
        assert ld['success'] is True, aid
        dash = run_preset_dashboard(aid)
        assert dash['success'] is True, aid
        m08 = next(p for p in dash['points'] if p['id'] == 'mach_0_8')
        assert m08['feasible'] is True, aid
        assert m08['radius_km'] > 300, (aid, m08['radius_km'])

    f16 = preset_to_aircraft(get_preset_by_id(presets, 'F-16'))
    assert geometric_wetted_area_m2(f16) == pytest.approx(130.4, abs=0.5)
    j10 = get_preset_by_id(presets, 'J-10C')
    assert j10['vtail_area_m2'] == pytest.approx(5.5)
