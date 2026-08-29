"""CSV 型号自动进入三端 catalog 的端到端测试。"""
from __future__ import annotations

import json

import pytest

from apps.miniprogram_api import handle_request
from scripts.frontend_catalog import SIMULATORS, build_catalog_payload
from utils.database_csv import (
    load_aircraft_csv,
    load_carriers_csv,
    load_missile_interception_presets_csv,
)
from utils.paths import AIRCRAFT_CSV, CARRIERS_CSV, ROOT


@pytest.mark.e2e
def test_e2e_catalog_auto_detects_csv_models():
    """起飞与饱和 CSV 中的型号须全部出现在 catalog / API data。"""
    aircraft = load_aircraft_csv(AIRCRAFT_CSV)
    carriers = load_carriers_csv(CARRIERS_CSV)
    sat = load_missile_interception_presets_csv()
    payload = build_catalog_payload(aircraft, carriers)

    assert {a['id'] for a in payload['aircraft']} == set(aircraft)
    assert {c['id'] for c in payload['carriers']} == {c.id for c in carriers}
    for cat in ('asm', 'aew', 'ship', 'sam'):
        assert [x['id'] for x in payload['missile_interception_presets'][cat]] == [
            x['id'] for x in sat[cat]
        ]
    assert payload['simulators'] == SIMULATORS

    status, _, body = handle_request('GET', '/api/data', None)
    assert status == 200
    api = json.loads(body.decode())
    assert api['simulators'] == SIMULATORS
    assert len(api['missile_interception_presets']['sam']) == len(sat['sam'])
    assert [p['id'] for p in api['combat_radius_presets']] == [
        'F-35C', 'F-22', 'F-35A', 'J-20', 'J-50', 'J-50N', 'J-36',
        'J-35', 'J-35A', '53636', '53636N', '53536',
    ]
    assert any(p['id'] == 'f119' for p in api['combat_radius_engine_presets'])


@pytest.mark.e2e
def test_e2e_docs_hub_and_takeoff_pages():
    """启动页与起飞页文件齐全，启动页从 simulators 渲染。"""
    hub = (ROOT / 'docs' / 'index.html').read_text(encoding='utf-8')
    hub_js = (ROOT / 'docs' / 'js' / 'hub.js').read_text(encoding='utf-8')
    assert 'hub.js' in hub
    assert 'data.simulators' in hub_js or 'simulators' in hub_js
    assert (ROOT / 'docs' / 'takeoff.html').is_file()
    assert (ROOT / 'docs' / 'missile-interception-strike.html').is_file()
    assert (ROOT / 'docs' / 'combat-radius.html').is_file()


@pytest.mark.e2e
def test_e2e_takeoff_terminal_gui_three_channels():
    """起飞战术终端观感须在 HTML / 小程序 / iOS 三端同时落地。"""
    title = '航母舰载机起飞距离仿真终端'
    tags = ('MODE', 'CARRIER', 'AIRCRAFT', 'INPUT', 'OUTPUT', 'TRAJECTORY')

    html = (ROOT / 'docs' / 'takeoff.html').read_text(encoding='utf-8')
    css = (ROOT / 'docs' / 'css' / 'style.css').read_text(encoding='utf-8')
    app_js = (ROOT / 'docs' / 'js' / 'app.js').read_text(encoding='utf-8')
    wxml = (ROOT / 'miniprogram' / 'pages' / 'index' / 'index.wxml').read_text(encoding='utf-8')
    wxss = (ROOT / 'miniprogram' / 'app.wxss').read_text(encoding='utf-8')
    index_js = (ROOT / 'miniprogram' / 'pages' / 'index' / 'index.js').read_text(encoding='utf-8')
    ios = (ROOT / 'ios' / 'CarrierTakeOff' / 'ContentView.swift').read_text(encoding='utf-8')
    theme = (ROOT / 'ios' / 'CarrierTakeOff' / 'Theme.swift').read_text(encoding='utf-8')
    vm = (ROOT / 'ios' / 'CarrierTakeOff' / 'SimulatorViewModel.swift').read_text(encoding='utf-8')

    for blob in (html, wxml, ios):
        assert title in blob
        for tag in tags:
            assert tag in blob

    assert 'id="outputSummary"' in html
    assert 'formatOutputSummary' in app_js
    assert 'output-summary' in wxml
    assert 'formatOutputSummary' in index_js
    assert 'outputSummary' in ios or 'trailingSummary' in ios
    assert 'formatOutputSummary' in vm
    assert 's.eyebrow' in (ROOT / 'docs' / 'js' / 'hub.js').read_text(encoding='utf-8')

    assert 'scanline' in html and '.scanline' in css
    assert '#38bdf8' in css and '#38bdf8' in wxss
    assert '0x38BDF8' in theme
    assert 'card-tag' in wxml and 'CardView' in ios
