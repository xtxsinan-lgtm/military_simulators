"""挂点 catalog 端到端：build 后 data.json 含光辉挂点表。"""
from __future__ import annotations

import json
import subprocess

import pytest

from utils.paths import ROOT


@pytest.mark.e2e
def test_built_data_json_includes_tejas_hardpoints():
    """build_all 后 docs/data.json 暴露光辉挂点与限重。"""
    subprocess.run(
        ['python3', 'scripts/build_all.py'],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    data = json.loads((ROOT / 'docs' / 'data.json').read_text(encoding='utf-8'))
    hp = data['aircraft_hardpoints']['by_aircraft']['Tejas']
    stations = {s['id']: s for s in hp['stations']}
    assert stations['wtip_r']['max_mass_kg'] == 310
    assert stations['wtip_r']['allowed_stores'] == ['aspj']
    assert stations['centre']['max_mass_kg'] == 740
    assert 'derby' not in stations['centre']['allowed_stores']
    assert hp['fixed_equipment'][0]['equipment_id'] == 'cmds'
