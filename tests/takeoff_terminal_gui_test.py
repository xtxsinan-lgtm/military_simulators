"""起飞三端战术终端 GUI 同步单元测试。"""
from __future__ import annotations

import re

from utils.paths import ROOT

# 六段卡片英文 tag，须与 HTML / 小程序 / iOS 一致
CARD_TAGS = ('MODE', 'CARRIER', 'AIRCRAFT', 'INPUT', 'OUTPUT', 'TRAJECTORY')
TERMINAL_TITLE = '航母舰载机起飞距离仿真终端'
# 起飞蓝青主题（不得改成饱和打击琥珀橙）
TAKEOFF_ACCENT = '#38bdf8'
TAKEOFF_BG = '#0f1419'


def test_docs_takeoff_terminal_chrome():
    """HTML 起飞页须具备扫描线、终端头、蓝青配色与卡片 tag。"""
    html = (ROOT / 'docs' / 'takeoff.html').read_text(encoding='utf-8')
    css = (ROOT / 'docs' / 'css' / 'style.css').read_text(encoding='utf-8')
    app_js = (ROOT / 'docs' / 'js' / 'app.js').read_text(encoding='utf-8')

    assert 'class="scanline"' in html
    assert 'terminal-header' in html
    assert TERMINAL_TITLE in html
    assert 'id="takeoffClock"' in html
    for tag in CARD_TAGS:
        assert f'class="tag">{tag}</span>' in html or f'>{tag}</span>' in html

    assert TAKEOFF_BG in css
    assert TAKEOFF_ACCENT in css
    assert '.scanline' in css
    assert "var(--mono)" in css or '--mono:' in css
    assert 'id="outputSummary"' in html
    assert 'id="highlights"' in html
    assert 'id="staleBanner"' in html
    assert 'id="backToTop"' in html
    assert 'massRangeHint' in html
    assert 'formatOutputSummary' in app_js
    assert 'validateTakeoffMass' in app_js
    assert 'markResultsStale' in app_js
    assert 'LOCAL PYODIDE' not in html
    assert 'PYODIDE LOCAL' not in html
    assert '<tr><th>空重</th>' in app_js

    ver_js = re.search(r'const APP_VERSION\s*=\s*(\d+)', app_js)
    ver_app = re.search(r'app\.js\?v=(\d+)', html)
    ver_css = re.search(r'style\.css\?v=(\d+)', html)
    assert ver_js and ver_app and ver_css
    assert ver_js.group(1) == ver_app.group(1) == ver_css.group(1), (
        f'缓存版本不一致: APP_VERSION={ver_js.group(1)} '
        f'app.js?v={ver_app.group(1)} style.css?v={ver_css.group(1)}'
    )
    assert 'takeoffClock' in app_js
    assert 'isTilt || isProp' in app_js


def test_miniprogram_takeoff_terminal_chrome():
    """小程序起飞页须与 HTML 同构：终端标题、card-tag、蓝青网格底纹。"""
    wxml = (ROOT / 'miniprogram' / 'pages' / 'index' / 'index.wxml').read_text(encoding='utf-8')
    wxss = (ROOT / 'miniprogram' / 'app.wxss').read_text(encoding='utf-8')

    assert TERMINAL_TITLE in wxml
    assert 'outputSummary' in wxml or 'output-summary' in wxml
    assert 'highlights' in wxml
    assert 'resultStale' in wxml or 'stale-banner' in wxml
    assert 'massRangeHint' in wxml
    index_js = (ROOT / 'miniprogram' / 'pages' / 'index' / 'index.js').read_text(encoding='utf-8')
    assert "label: '空重'" in index_js
    assert 'isTilt || isProp' in index_js
    for tag in CARD_TAGS:
        assert f'card-tag">{tag}</text>' in wxml or f'>{tag}</text>' in wxml
    assert TAKEOFF_BG in wxss
    assert TAKEOFF_ACCENT in wxss
    assert 'Courier New' in wxss
    assert '.card-tag' in wxss
    assert 'background-size: 56rpx 56rpx' in wxss


def test_ios_takeoff_terminal_chrome():
    """iOS ContentView / Theme 须与 Web 同标题、同 tag、同蓝青色。"""
    content = (ROOT / 'ios' / 'CarrierTakeOff' / 'ContentView.swift').read_text(encoding='utf-8')
    theme = (ROOT / 'ios' / 'CarrierTakeOff' / 'Theme.swift').read_text(encoding='utf-8')
    card = (ROOT / 'ios' / 'CarrierTakeOff' / 'Components' / 'SpecList.swift').read_text(
        encoding='utf-8'
    )

    assert TERMINAL_TITLE in content
    assert 'trailingSummary' in content or 'outputSummary' in content
    assert 'highlights' in content
    assert 'resultStale' in content
    vm = (ROOT / 'ios' / 'CarrierTakeOff' / 'SimulatorViewModel.swift').read_text(encoding='utf-8')
    assert 'validateTakeoffMass' in vm
    assert 'label: "空重"' in vm
    assert 'isTilt || isProp' in vm
    assert 'LOCAL PYODIDE' not in content
    assert 'PYODIDE LOCAL' not in content
    for tag in CARD_TAGS:
        assert f'tag: "{tag}"' in content
    assert '0x0F1419' in theme
    assert '0x38BDF8' in theme
    assert 'var tag: String' in card or 'tag: String' in card
    assert 'design: .monospaced' in content
