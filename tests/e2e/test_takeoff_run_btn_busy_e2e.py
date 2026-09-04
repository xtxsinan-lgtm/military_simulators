"""起飞页二次仿真时按钮应变灰、光标应变等待，不得卡在手型。"""
from __future__ import annotations

import re

import pytest

from utils.paths import ROOT


@pytest.mark.e2e
def test_e2e_takeoff_second_run_paints_busy_before_python():
    """HTML/CSS/JS 须同步：禁用按钮、整页 progress 光标、runPython 前让出绘制。"""
    html = (ROOT / 'docs' / 'takeoff.html').read_text(encoding='utf-8')
    css = (ROOT / 'docs' / 'css' / 'style.css').read_text(encoding='utf-8')
    app_js = (ROOT / 'docs' / 'js' / 'app.js').read_text(encoding='utf-8')

    ver_js = re.search(r'const APP_VERSION\s*=\s*(\d+)', app_js)
    ver_app = re.search(r'app\.js\?v=(\d+)', html)
    ver_css = re.search(r'style\.css\?v=(\d+)', html)
    assert ver_js and ver_app and ver_css
    assert ver_js.group(1) == ver_app.group(1) == ver_css.group(1)

    assert 'id="runBtn"' in html
    assert 'function yieldForUiPaint' in app_js
    assert 'await yieldForUiPaint()' in app_js
    assert 'function setRunBusy' in app_js
    assert 'sim-busy' in app_js
    assert 'body.sim-busy' in css
    assert 'cursor: progress' in css

    start = app_js.index('async function runSimulation()')
    end = app_js.index('\nfunction bindEvents()')
    body = app_js[start:end]
    assert body.index('await yieldForUiPaint()') < body.index('pyodide.runPython')
    assert 'setRunBusy(true)' in body
    assert 'setRunBusy(false)' in body
