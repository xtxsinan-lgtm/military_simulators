"""frontend_catalog / generate_frontend_physics / build_all 单元测试。"""
from __future__ import annotations

from scripts.frontend_catalog import MODES, aircraft_to_dict, build_catalog_payload, carrier_to_dict
from scripts.generate_frontend_physics import render_cjs, render_esm, _load_constants
from utils.database_csv import load_aircraft_csv, load_carriers_csv
from utils.paths import AIRCRAFT_CSV, CARRIERS_CSV


def test_carrier_to_dict_has_ski_jump_fields():
    carriers = load_carriers_csv(CARRIERS_CSV)
    d = carrier_to_dict(carriers[0])
    assert 'ski_jump' in d and 'total_deck_length_m' in d and 'id' in d


def test_aircraft_to_dict_strips_computed_props():
    ac = next(iter(load_aircraft_csv(AIRCRAFT_CSV).values()))
    d = aircraft_to_dict(ac)
    assert 'id' in d and 'name' in d
    assert 'a2a_mass_kg' not in d


def test_build_catalog_payload_modes():
    payload = build_catalog_payload(
        load_aircraft_csv(AIRCRAFT_CSV),
        load_carriers_csv(CARRIERS_CSV),
    )
    assert payload['modes'] == MODES
    assert 'tiltrotor_short_takeoff' in payload['modes']
    assert 'tiltrotor_strategies' in payload
    assert set(payload['tiltrotor_strategies']) == {'A', 'B'}
    assert 'py_sources' not in payload
    assert any(a['id'] == 'MV-22' for a in payload['aircraft'])
    # 第二功能：饱和打击预设
    assert 'missile_interception_presets' in payload
    assert set(payload['missile_interception_presets']) == {'asm', 'aew', 'ship', 'sam'}
    assert len(payload['missile_interception_presets']['asm']) >= 1
    assert 'takeoff_config' in payload
    assert 'missile_interception_config' in payload
    assert 'combat_radius_presets' in payload
    assert 'combat_radius_engine_presets' in payload
    assert 'combat_radius_config' in payload
    assert 'combat_radius_results' in payload
    assert payload['combat_radius_config']['mission_fuel']['carrier_reserve_min'] == 45
    assert payload['combat_radius_config']['engine']['dry_to_max_thrust_ratio'] == 0.7
    assert payload['combat_radius_config']['inlet_labels']['caret'] == '加莱特'
    assert any(p['id'] == 'J-20' for p in payload['combat_radius_presets'])
    assert any(p['id'] == 'J-50' for p in payload['combat_radius_presets'])
    assert any(p['id'] == 'J-15' for p in payload['combat_radius_presets'])
    assert any(p['id'] == '53636' for p in payload['combat_radius_presets'])
    assert any(p['id'] == 'f119' for p in payload['combat_radius_engine_presets'])
    assert any(p['id'] == 'f135' for p in payload['combat_radius_engine_presets'])
    assert any(p['id'] == 'f135b' for p in payload['combat_radius_engine_presets'])
    assert payload['takeoff_config']['shared']['mu'] == 0.025
    assert 'A' in payload['takeoff_config']['stovl_strategy_descriptions']
    assert set(payload['takeoff_config']['modes']) == set(payload['modes'])
    tilt_mode = payload['takeoff_config']['modes']['tiltrotor_short_takeoff']
    assert 'hover_download_frac' in tilt_mode
    assert 'slipstream_wake_factor' in tilt_mode
    assert 'A' in payload['takeoff_config']['tiltrotor_strategy_descriptions']
    assert payload['missile_interception_config']['traj_types']['glide']


def test_docs_missile_interception_page_exists_and_links():
    """饱和打击 HTML 页存在，并与起飞页/启动页互链。"""
    import re
    from utils.paths import ROOT

    sat = ROOT / 'docs' / 'missile-interception-strike.html'
    hub = ROOT / 'docs' / 'index.html'
    takeoff = ROOT / 'docs' / 'takeoff.html'
    assert sat.is_file()
    assert hub.is_file()
    assert takeoff.is_file()
    assert (ROOT / 'docs' / 'js' / 'missile_interception.js').is_file()
    assert (ROOT / 'docs' / 'css' / 'missile_interception.css').is_file()
    assert (ROOT / 'docs' / 'js' / 'hub.js').is_file()
    sat_html = sat.read_text(encoding='utf-8')
    hub_html = hub.read_text(encoding='utf-8')
    takeoff_html = takeoff.read_text(encoding='utf-8')
    sat_js = (ROOT / 'docs' / 'js' / 'missile_interception.js').read_text(encoding='utf-8')
    assert 'missile_interception.js' in sat_html
    assert 'index.html' in sat_html
    assert 'takeoff.html' in sat_html
    assert 'missile-interception-strike.html' in takeoff_html
    assert 'hub.js' in hub_html
    assert 'run_missile_interception_json' in sat_js
    assert 'rerunRequested' in sat_js
    ver_js = re.search(r'const APP_VERSION\s*=\s*(\d+)', sat_js)
    ver_html = re.search(r'missile_interception\.js\?v=(\d+)', sat_html)
    assert ver_js and ver_html
    assert ver_js.group(1) == ver_html.group(1)


def test_docs_combat_radius_page_exists_and_links():
    """作战半径 HTML 页存在，并与起飞页/启动页/饱和打击页互链。"""
    import re
    from utils.paths import ROOT

    page = ROOT / 'docs' / 'combat-radius.html'
    hub = ROOT / 'docs' / 'index.html'
    takeoff = ROOT / 'docs' / 'takeoff.html'
    sat = ROOT / 'docs' / 'missile-interception-strike.html'
    assert page.is_file()
    js = ROOT / 'docs' / 'js' / 'combat_radius.js'
    css = ROOT / 'docs' / 'css' / 'combat_radius.css'
    assert js.is_file() and css.is_file()
    html = page.read_text(encoding='utf-8')
    js_text = js.read_text(encoding='utf-8')
    assert 'combat_radius.js' in html
    assert 'index.html' in html
    assert 'run_combat_radius_json' in js_text
    assert 'aircraft_dashboard' in js_text
    assert 'search_best_cruise' in js_text
    assert 'estimate_engine_cycle' in js_text
    assert 'estimate_efficiency' in js_text
    assert 'engine_efficiency.py' in js_text
    assert '搜索最佳升阻比和巡航高度' in html
    assert '计算作战半径' in html
    assert 'data-run-dash' in html
    assert '混合作战半径' in html
    assert '最大 L/D' in html
    assert '选择战机' in html
    assert '实用最大巡航速度' in js_text
    assert '最大巡航速度' in js_text
    assert 'max_possible_cruise_mach' in js_text
    assert 'max_cruise_floor_mach' not in js_text
    assert 'floor_max_cruise' not in js_text
    assert 'max_radius_cruise' in js_text
    assert '最大半径超音速巡航速度' in js_text
    assert 'split_cruise_note' not in js_text
    assert '表下会并排' not in js_text
    assert '热效率' in js_text
    assert '推进效率' in js_text
    assert '总效率' in js_text
    assert '<th>η_th</th>' not in js_text
    assert '<th>η_p</th>' not in js_text
    assert '<th>η_o</th>' not in js_text
    assert '<th>速度/马赫</th>' in js_text
    assert '<th>平均油耗 kg/km</th>' in js_text
    assert '<th>点</th>' not in js_text
    assert '<th>Ma</th>' not in js_text
    assert '<th>kg/km</th>' not in js_text
    assert '锚点' not in html
    assert 'Ma 0.8 / 1.0 / 1.2 / 1.35 / 1.5 / 1.75 / 2.0' in html
    assert '表尾多一行最大半径超音速巡航速度' in html
    assert 'combat-radius.html' in takeoff.read_text(encoding='utf-8')
    assert 'combat-radius.html' in sat.read_text(encoding='utf-8')
    ver_js = re.search(r'const APP_VERSION\s*=\s*(\d+)', js_text)
    ver_html = re.search(r'combat_radius\.js\?v=(\d+)', html)
    ver_css = re.search(r'combat_radius\.css\?v=(\d+)', html)
    assert ver_js and ver_html and ver_css
    assert ver_js.group(1) == ver_html.group(1) == ver_css.group(1)
    assert 'resolveTslKN' in js_text
    assert 'tgt_sweep_inner' in js_text
    assert 'tgt_fuse_w' in js_text
    assert 'tgt_fuse_h' in js_text
    assert 'fuse_width_m' in js_text
    assert 'syncDoubleDeltaFields' in js_text
    assert "e.target.id === 'tgtPreset'" in js_text
    assert js_text.count("e.target.id === 'tgtPreset'") >= 2
    assert 'function requestLiveDash' in js_text
    assert 'data-run-dash' in js_text
    assert '计算作战半径' in js_text


def test_pyodide_bundles_combat_radius_modules():
    """作战半径 Web 页须加载与 build_docs 一致的 Python 模块。"""
    from scripts.build_docs import PY_LOAD_ORDER
    from utils.paths import ROOT

    for rel in (
        'utils/combat_radius/lift_drag.py',
        'utils/combat_radius/military_thrust.py',
        'utils/combat_radius/engine_efficiency.py',
        'utils/combat_radius/cruise_load.py',
        'utils/combat_radius/breguet.py',
        'utils/combat_radius/cruise_search.py',
        'utils/combat_radius/max_speed_search.py',
        'simulators/combat_radius/combat_radius.py',
        'apps/combat_radius_web.py',
    ):
        assert rel in PY_LOAD_ORDER
    js = (ROOT / 'docs' / 'js' / 'combat_radius.js').read_text(encoding='utf-8')
    assert 'apps/combat_radius_web.py' in js
    assert 'utils.combat_radius.lift_drag' in js
    assert 'utils.combat_radius.military_thrust' in js
    assert 'utils.combat_radius.engine_efficiency' in js
    assert 'utils.combat_radius.breguet' in js
    assert 'utils.combat_radius.cruise_search' in js
    assert 'utils.combat_radius.max_speed_search' in js


def test_pyodide_bundles_missile_interception_presets_csv_deps():
    """Pyodide 须打包 missile_interception_presets 的 CSV 依赖，避免 ModuleNotFoundError。"""
    from scripts.build_docs import PY_IMPORT_ORDER, PY_LOAD_ORDER
    from utils.paths import ROOT

    for rel in ('utils/paths.py', 'utils/database_csv.py'):
        assert rel in PY_LOAD_ORDER
        assert PY_LOAD_ORDER.index(rel) < PY_LOAD_ORDER.index('utils/missile_interception/missile_interception_presets.py')
    for mod in ('utils.paths', 'utils.database_csv'):
        assert mod in PY_IMPORT_ORDER
        assert PY_IMPORT_ORDER.index(mod) < PY_IMPORT_ORDER.index('utils.missile_interception.missile_interception_presets')

    sat_js = (ROOT / 'docs' / 'js' / 'missile_interception.js').read_text(encoding='utf-8')
    assert "utils/paths.py" in sat_js
    assert "utils/database_csv.py" in sat_js
    assert "utils.paths" in sat_js
    assert "utils.database_csv" in sat_js
    assert "utils/missile_interception/missile_interception_display.py" in sat_js
    assert "utils.missile_interception.missile_interception_display" in sat_js
    assert 'utils/missile_interception/missile_interception_display.py' in PY_LOAD_ORDER
    assert 'utils.takeoff.takeoff_input' in PY_IMPORT_ORDER
    assert 'utils/takeoff/takeoff_input.py' in PY_LOAD_ORDER


def test_build_catalog_payload_includes_simulators_and_csv_presets():
    """catalog 须含启动页模拟器列表，且饱和预设与 CSV 一致。"""
    from utils.database_csv import load_missile_interception_presets_csv
    from scripts.frontend_catalog import SIMULATORS

    payload = build_catalog_payload(
        load_aircraft_csv(AIRCRAFT_CSV),
        load_carriers_csv(CARRIERS_CSV),
    )
    assert payload['simulators'] == SIMULATORS
    sat_cfg = payload['missile_interception_config']
    assert 'rcs' in sat_cfg['field_hints']
    assert 'seekerType' in sat_cfg['field_hints']
    assert sat_cfg['field_ranges']['nm']['min'] == 1
    csv_data = load_missile_interception_presets_csv()
    assert [x['id'] for x in payload['missile_interception_presets']['asm']] == [x['id'] for x in csv_data['asm']]
    assert [x['id'] for x in payload['missile_interception_presets']['aew']] == [x['id'] for x in csv_data['aew']]
    assert [p['id'] for p in payload['combat_radius_presets']][:12] == [
        'F-35C', 'F-22', 'F-35A', 'J-20', 'J-50', 'J-50N', 'J-36',
        'J-35', 'J-35A', '53636', '53636N', '53536',
    ]
    takeoff_ids = {a['id'] for a in payload['aircraft']}
    assert 'F-35C' in takeoff_ids
    assert 'J-50N' in takeoff_ids
    assert 'NG6C' in takeoff_ids
    assert 'NG6B' in takeoff_ids
    assert 'F-22' not in takeoff_ids
    assert 'J-50' not in takeoff_ids
    assert 'NG6A' not in takeoff_ids
    assert any(p['id'] == 'f119' for p in payload['combat_radius_engine_presets'])
    assert any(p['id'] == 'f135' for p in payload['combat_radius_engine_presets'])
    assert any(p['id'] == 'f135b' for p in payload['combat_radius_engine_presets'])
    assert len(payload['aircraft']) >= 1
    assert len(payload['carriers']) >= 1


def test_web_simulator_modes_match_frontend_catalog():
    """Web API 与前端 catalog 的模式/策略表必须一致，防止某一端漏加新模式。"""
    from apps import web_simulator as ws
    from scripts.frontend_catalog import STOVL_STRATEGIES, TILTROTOR_STRATEGIES

    assert ws.MODES == MODES
    assert ws.STOVL_STRATEGIES == STOVL_STRATEGIES
    assert ws.TILTROTOR_STRATEGIES == TILTROTOR_STRATEGIES


def test_docs_html_renders_modes_from_catalog_not_hardcoded():
    """起飞 HTML 模式按钮须由 data.modes 动态生成，禁止硬编码模式 id。"""
    import re
    from utils.paths import ROOT

    html = (ROOT / 'docs' / 'takeoff.html').read_text(encoding='utf-8')
    app_js = (ROOT / 'docs' / 'js' / 'app.js').read_text(encoding='utf-8')

    assert 'id="modeGroup"' in html
    assert 'data-mode="ski_jump"' not in html
    assert 'data-mode="tiltrotor_short_takeoff"' not in html
    assert 'function populateModeButtons' in app_js
    assert 'data.modes' in app_js

    ver_js = re.search(r'const APP_VERSION\s*=\s*(\d+)', app_js)
    ver_html = re.search(r'app\.js\?v=(\d+)', html)
    ver_css = re.search(r'style\.css\?v=(\d+)', html)
    assert ver_js and ver_html and ver_css
    assert ver_js.group(1) == ver_html.group(1) == ver_css.group(1), (
        f'缓存版本不一致: app.js APP_VERSION={ver_js.group(1)} '
        f'vs takeoff.html app.js?v={ver_html.group(1)} style.css?v={ver_css.group(1)}'
    )


def test_render_esm_and_cjs_contain_injected_constants():
    c = _load_constants()
    esm = render_esm(c)
    cjs = render_cjs(c)
    assert f"SKI_JUMP_REF_RADIUS_M = {c['SKI_JUMP_REF_RADIUS_M']}" in esm
    assert 'export {' in esm
    assert 'module.exports' in cjs
    assert '请勿手改' in esm and '请勿手改' in cjs


def test_render_includes_default_deck_wind_helper():
    from scripts.generate_frontend_physics import render_cjs

    text = render_cjs()
    assert 'function defaultDeckWindKt' in text
    assert 'max_speed_kt' in text


def test_load_constants_positive():
    c = _load_constants()
    assert c['SKI_JUMP_REF_RADIUS_M'] > 0
    assert c['A2A_MISSILE_COUNT'] >= 1
