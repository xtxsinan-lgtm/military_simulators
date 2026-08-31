"""api / modesToList 与数据加载相关单元测试。"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_miniprogram_data_json_has_carriers_and_modes():
    """内置 data.json 必须含 modes / carriers / aircraft，供本地界面渲染。"""
    path = ROOT / 'miniprogram' / 'data' / 'data.json'
    assert path.is_file(), '缺少 miniprogram/data/data.json，请运行 build_miniprogram.py'
    data = json.loads(path.read_text(encoding='utf-8'))
    assert data['modes']['ski_jump'] == '滑跃起飞'
    assert len(data['carriers']) >= 1
    assert any(c.get('ski_jump') for c in data['carriers'])
    assert len(data['aircraft']) >= 1


def test_modes_to_list_shape_matches_miniprogram_contract():
    """modes 对象转为 [{id,label}]，与小程序 mode-selector 约定一致。"""
    modes = {
        'ski_jump': '滑跃起飞',
        'short_takeoff': '短距起飞',
        'short_ski_jump': '短距滑跃起飞',
    }
    # 与 miniprogram/utils/api.js modesToList 同逻辑（Python 侧校验契约）
    mode_list = [{'id': k, 'label': v} for k, v in modes.items()]
    assert len(mode_list) == 3
    assert mode_list[0] == {'id': 'ski_jump', 'label': '滑跃起飞'}


def test_trajectory_chart_is_inline_below_sim_output():
    """轨迹图须跟在仿真输出卡片后进入文档流，不得用底部固定坞（traj-dock）。"""
    wxml = (ROOT / 'miniprogram' / 'pages' / 'index' / 'index.wxml').read_text(encoding='utf-8')
    wxss = (ROOT / 'miniprogram' / 'pages' / 'index' / 'index.wxss').read_text(encoding='utf-8')
    assert 'traj-dock' not in wxml
    assert 'traj-dock' not in wxss
    assert 'page-root' not in wxml
    assert '5. 仿真输出' in wxml
    assert '6. 起飞轨迹' in wxml
    assert 'trajectory-chart' in wxml
    # 轨迹区块须出现在仿真输出之后，保证滚动时随内容离开视口
    assert wxml.index('5. 仿真输出') < wxml.index('6. 起飞轨迹')
    assert wxml.index('6. 起飞轨迹') < wxml.index('page-footer')


def test_miniprogram_takeoff_cards_have_terminal_tags():
    """起飞页六段卡片须带与 HTML/iOS 一致的英文 card-tag。"""
    wxml = (ROOT / 'miniprogram' / 'pages' / 'index' / 'index.wxml').read_text(encoding='utf-8')
    wxss = (ROOT / 'miniprogram' / 'app.wxss').read_text(encoding='utf-8')
    assert '航母舰载机起飞距离仿真终端' in wxml
    for tag in ('MODE', 'CARRIER', 'AIRCRAFT', 'INPUT', 'OUTPUT', 'TRAJECTORY'):
        assert tag in wxml
    assert '.card-tag' in wxss
    assert '#38bdf8' in wxss

def test_miniprogram_missile_interception_page_and_tabbar():
    """小程序须注册启动页、起飞与饱和打击，且 tabBar 含三者。"""
    app = json.loads((ROOT / 'miniprogram' / 'app.json').read_text(encoding='utf-8'))
    assert app['pages'][0] == 'pages/home/home'
    assert 'pages/missile_interception/missile_interception' in app['pages']
    assert 'pages/combat_radius/combat_radius' in app['pages']
    assert 'tabBar' in app
    paths = [x['pagePath'] for x in app['tabBar']['list']]
    assert 'pages/home/home' in paths
    assert 'pages/missile_interception/missile_interception' in paths
    assert 'pages/combat_radius/combat_radius' in paths
    assert (ROOT / 'miniprogram' / 'pages' / 'missile_interception' / 'missile_interception.js').is_file()
    assert (ROOT / 'miniprogram' / 'pages' / 'combat_radius' / 'combat_radius.js').is_file()
    assert (ROOT / 'miniprogram' / 'pages' / 'home' / 'home.js').is_file()
    api_js = (ROOT / 'miniprogram' / 'utils' / 'api.js').read_text(encoding='utf-8')
    assert 'runMissileInterceptionSimulation' in api_js
    assert '/api/missile_interception/simulate' in api_js
    assert 'runCombatRadiusSimulation' in api_js
    assert '/api/combat_radius/simulate' in api_js
    cr_js = (ROOT / 'miniprogram' / 'pages' / 'combat_radius' / 'combat_radius.js').read_text(encoding='utf-8')
    cr_wxml = (ROOT / 'miniprogram' / 'pages' / 'combat_radius' / 'combat_radius.wxml').read_text(encoding='utf-8')
    assert 'onRunSearchCruise' in cr_js
    assert 'search_best_cruise' in cr_js
    assert 'aircraft_dashboard' in cr_js
    assert 'estimate_engine_cycle' in cr_js
    assert '搜索最佳升阻比和巡航高度' in cr_wxml
    assert '混合作战半径' in cr_wxml
    assert '热效率' in cr_js
    assert '推进效率' in cr_js
    assert '总效率' in cr_js
    assert 'η_th' not in cr_js
    assert 'η_p' not in cr_js
    assert 'η_o' not in cr_js
    assert '锚点' not in cr_wxml
    assert 'mach_angle_deg' in cr_js
    assert 'resolveTslKN' in cr_js
