"""iOS GUI 通道相关单元测试（源码结构与本地引擎契约）。"""
from __future__ import annotations

from utils.paths import ROOT

IOS_ROOT = ROOT / 'ios' / 'CarrierTakeOff'


def test_ios_swift_sources_exist():
    """主界面与本地引擎模块文件必须存在。"""
    required = [
        'CarrierTakeOffApp.swift',
        'ContentView.swift',
        'SimulatorViewModel.swift',
        'MissileInterceptionStrikeView.swift',
        'MissileInterceptionViewModel.swift',
        'MissileInterceptionTheme.swift',
        'CombatRadiusView.swift',
        'CombatRadiusViewModel.swift',
        'CombatRadiusTheme.swift',
        'HubView.swift',
        'CatalogStore.swift',
        'LocalSimulatorEngine.swift',
        'Models.swift',
        'Physics.swift',
        'Config.swift',
        'Theme.swift',
        'Info.plist',
        'Components/ModeSelector.swift',
        'Components/SpecList.swift',
        'Components/TrajectoryChart.swift',
        'Resources/engine.html',
        'Resources/engine.js',
    ]
    for rel in required:
        path = IOS_ROOT / rel
        assert path.is_file(), f'缺少 iOS 源文件: {rel}'


def test_ios_app_has_hub_then_simulators():
    """App 入口为启动页 HubView，可进入起飞、饱和打击与作战半径。"""
    app = (IOS_ROOT / 'CarrierTakeOffApp.swift').read_text(encoding='utf-8')
    hub = (IOS_ROOT / 'HubView.swift').read_text(encoding='utf-8')
    assert 'HubView' in app
    assert 'NavigationStack' in app
    assert 'MissileInterceptionStrikeView' in hub
    assert 'CombatRadiusView' in hub
    assert 'ContentView' in hub
    assert (IOS_ROOT / 'HubView.swift').is_file()


def test_ios_content_view_has_six_sections():
    """起飞主界面文案须覆盖与小程序相同的 1–6 段卡片标题与 tag。"""
    text = (IOS_ROOT / 'ContentView.swift').read_text(encoding='utf-8')
    for title in (
        '1. 起飞模式',
        '2. 航母',
        '3. 战斗机',
        '4. 仿真条件',
        '5. 仿真输出',
        '6. 起飞轨迹',
    ):
        assert title in text, f'ContentView 缺少卡片: {title}'
    for tag in ('MODE', 'CARRIER', 'AIRCRAFT', 'INPUT', 'OUTPUT', 'TRAJECTORY'):
        assert f'tag: "{tag}"' in text, f'ContentView 缺少卡片 tag: {tag}'
    assert '航母舰载机起飞距离仿真终端' in text


def test_ios_uses_local_engine_not_http_api():
    """iOS 仿真应走 LocalSimulatorEngine，而非 HTTP API。"""
    vm = (IOS_ROOT / 'SimulatorViewModel.swift').read_text(encoding='utf-8')
    assert 'LocalSimulatorEngine' in vm
    assert 'apiBaseUrl' not in vm
    assert 'APIClient' not in vm
    engine_js = (IOS_ROOT / 'Resources' / 'engine.js').read_text(encoding='utf-8')
    assert 'run_simulation_json' in engine_js
    assert 'run_missile_interception_json' in engine_js
    assert '__missileInterceptionSim' in engine_js
    assert 'loadPyodide' in engine_js
    assert '__BUNDLED_CATALOG__' in engine_js
    engine_swift = (IOS_ROOT / 'LocalSimulatorEngine.swift').read_text(encoding='utf-8')
    assert '__BUNDLED_CATALOG__' in engine_swift
    assert 'runMissileInterception' in engine_swift
    assert 'func runMissileInterception(payload:' in engine_swift
    assert 'runCombatRadius' in engine_js
    assert '__combatRadiusSim' in engine_js
    assert 'run_combat_radius_json' in engine_js
    assert 'func runCombatRadius(payload:' in engine_swift
    sat_vm = (IOS_ROOT / 'MissileInterceptionViewModel.swift').read_text(encoding='utf-8')
    assert 'runMissileInterception(payload:' in sat_vm
    assert 'runMissileInterception([' not in sat_vm
    cr_vm = (IOS_ROOT / 'CombatRadiusViewModel.swift').read_text(encoding='utf-8')
    assert 'aircraft_dashboard' in cr_vm
    assert 'search_best_cruise' in cr_vm
    assert 'estimate_engine_cycle' in cr_vm
    assert 'func applyAircraft()' in cr_vm
    models = (IOS_ROOT / 'Models.swift').read_text(encoding='utf-8')
    assert 'combat_radius_results' in models
    assert 'combat_radius_engine_presets' in models
    assert 'mixed_radius_km' in models
    assert 'CombatRadiusCruisePoint' in models


def test_ios_project_yml_exists():
    """XcodeGen 工程描述须存在，便于生成 .xcodeproj。"""
    assert (ROOT / 'ios' / 'project.yml').is_file()
