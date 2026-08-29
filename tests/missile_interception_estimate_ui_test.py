"""饱和打击「估算交战距离与拦截率」三端 UI 同步单元测试。"""
from __future__ import annotations

import re

from utils.paths import ROOT

ESTIMATE_BTN = '◈ 估算交战距离与拦截率'
# 按钮下方三项探测/拦截率结果字段（文案关键词，须按此顺序出现）
BELOW_LABELS = ('预警机雷达探测距离', '舰载雷达探测距离', '单发拦截成功概率')
# 交战距离公式说明文案关键片段（三端均含俯冲进入距离项；HTML 写全称，小程序/iOS 简称）
FORMULA_NOTE_KEY = '拦截弹射程 [, 俯冲进入距离]'
# 须移到按钮上方的字段关键词（各端文案略有差异时用元组表示任一即可）
ABOVE_KEYS = (
    ('拦截弹数量',),
    ('拦截弹飞行速度', '拦截弹速度'),
    ('拦截弹直径',),
    ('火控锁定',),
    ('最小交战距离',),
)


def _first_match_index(text: str, options: tuple[str, ...]) -> tuple[str, int]:
    """返回首个命中关键词及其下标。"""
    for key in options:
        idx = text.find(key)
        if idx >= 0:
            return key, idx
    raise AssertionError(f'未找到任一关键词: {options}')


def test_first_match_index_prefers_earlier_option():
    """_first_match_index 按选项顺序返回首个命中。"""
    key, idx = _first_match_index('拦截弹飞行速度 Ma', ('拦截弹飞行速度', '拦截弹速度'))
    assert key == '拦截弹飞行速度'
    assert idx == 0
    key2, idx2 = _first_match_index('拦截弹速度 Ma', ('拦截弹飞行速度', '拦截弹速度'))
    assert key2 == '拦截弹速度'
    assert idx2 == 0


def _assert_merged_estimate_layout(text: str, channel: str, engage_marker: str) -> None:
    """断言合并估算按钮、旧双按钮消失、按钮下方三探测/交战距离字段与公式说明。

    ``engage_marker`` 为该端「交战距离」输入字段的唯一标识子串（须包含足够上下文，
    避免与「最小交战距离」标签、公式说明文案或按钮自身文案中的「交战距离」字样混淆）。
    """
    assert ESTIMATE_BTN in text, f'{channel} 缺少合并估算按钮文案'
    assert text.count(ESTIMATE_BTN) == 1, f'{channel} 合并估算按钮应仅出现一次'
    # 旧独立按钮不得残留
    assert '估算 Pk' not in text, f'{channel} 仍含旧「估算 Pk」按钮'
    assert '估算交战距离"' not in text and "估算交战距离'" not in text
    assert '◈ 估算交战距离\n' not in text
    assert '◈ 估算交战距离<' not in text
    # 旧「雷达发现距离」标签须已被「交战距离」取代
    assert '雷达发现距离' not in text, f'{channel} 仍残留旧「雷达发现距离」字段文案'

    btn_idx = text.index(ESTIMATE_BTN)
    for options in ABOVE_KEYS:
        key, idx = _first_match_index(text, options)
        assert idx < btn_idx, f'{channel} 字段「{key}」须在估算按钮上方'

    assert FORMULA_NOTE_KEY in text, f'{channel} 缺少交战距离公式说明文案'
    formula_idx = text.index(FORMULA_NOTE_KEY)
    assert formula_idx > btn_idx, f'{channel} 公式说明须在估算按钮下方'

    for label in BELOW_LABELS:
        assert label in text, f'{channel} 缺少下方字段: {label}'
        assert text.index(label) > btn_idx, f'{channel} 字段「{label}」须在估算按钮下方'

    assert engage_marker in text, f'{channel} 缺少「交战距离」输入字段: {engage_marker}'
    engage_idx = text.index(engage_marker)
    assert engage_idx > btn_idx, f'{channel} 「交战距离」字段须在估算按钮下方'

    # 下方字段相对顺序：预警机雷达探测距离 → 舰载雷达探测距离 → 交战距离 → 单发拦截成功概率
    awacs_idx = text.index(BELOW_LABELS[0])
    ship_idx = text.index(BELOW_LABELS[1])
    pk_idx = text.index(BELOW_LABELS[2])
    assert awacs_idx < ship_idx < engage_idx < pk_idx, (
        f'{channel} 下方字段顺序应为 预警机雷达探测距离 → 舰载雷达探测距离 → 交战距离 → 单发拦截成功概率'
    )


def test_html_missile_interception_merged_estimate_ui():
    """HTML 饱和页：合并估算按钮，预警机/舰载探测距离 + 交战距离 + Pk 在下方。"""
    html = (ROOT / 'docs' / 'missile-interception-strike.html').read_text(encoding='utf-8')
    js = (ROOT / 'docs' / 'js' / 'missile_interception.js').read_text(encoding='utf-8')
    _assert_merged_estimate_layout(
        html, 'HTML', '<label>交战距离 <span class="unit">km</span></label>'
    )
    assert 'id="awacsDetectKm"' in html
    assert 'id="shipDetectKm"' in html
    assert 'id="estimateBtn"' in html
    assert 'id="distBtn"' not in html
    assert 'id="estBtn"' not in html
    assert 'onEstimateDistanceAndPk' in js
    assert "callPython('estimate_distance'" in js
    assert "callPython('estimate_pk'" in js
    # 缓存版本与 HTML 引用一致
    ver_js = re.search(r'const APP_VERSION\s*=\s*(\d+)', js)
    ver_html = re.search(r'missile_interception\.js\?v=(\d+)', html)
    assert ver_js and ver_html and ver_js.group(1) == ver_html.group(1)


def test_miniprogram_missile_interception_merged_estimate_ui():
    """小程序饱和页：合并估算按钮与 HTML 同构。"""
    wxml = (ROOT / 'miniprogram' / 'pages' / 'missile_interception' / 'missile_interception.wxml').read_text(
        encoding='utf-8'
    )
    js = (ROOT / 'miniprogram' / 'pages' / 'missile_interception' / 'missile_interception.js').read_text(
        encoding='utf-8'
    )
    _assert_merged_estimate_layout(
        wxml, '小程序',
        '<view class="field-label"><text>交战距离</text><text class="unit">km</text></view>',
    )
    assert 'awacsDetectKm' in wxml
    assert 'shipDetectKm' in wxml
    assert 'bindtap="onEstimateDistanceAndPk"' in wxml
    assert 'onEstimateDistanceAndPk' in js
    assert "action: 'estimate_distance'" in js
    assert "action: 'estimate_pk'" in js
    assert 'bindtap="onEstimateDistance"' not in wxml
    assert 'bindtap="onEstimatePk"' not in wxml


def test_ios_missile_interception_merged_estimate_ui():
    """iOS 饱和页：合并估算按钮与 HTML / 小程序同构。"""
    view = (ROOT / 'ios' / 'CarrierTakeOff' / 'MissileInterceptionStrikeView.swift').read_text(
        encoding='utf-8'
    )
    vm = (ROOT / 'ios' / 'CarrierTakeOff' / 'MissileInterceptionViewModel.swift').read_text(
        encoding='utf-8'
    )
    _assert_merged_estimate_layout(
        view, 'iOS', 'field("交战距离 (km)", text: $vm.discoveryKm)'
    )
    assert 'awacsDetectKm' in view and 'awacsDetectKm' in vm
    assert 'shipDetectKm' in view and 'shipDetectKm' in vm
    assert 'estimateDistanceAndPk' in view
    assert 'func estimateDistanceAndPk' in vm
    assert '"estimate_distance"' in vm
    assert '"estimate_pk"' in vm
    assert 'Button("◈ 估算交战距离")' not in view
    assert 'Button("◈ 估算 Pk")' not in view
    assert 'func estimateDistance()' not in vm
    assert 'func estimatePk()' not in vm


def test_catalog_missile_interception_subtitle_mentions_intercept_rate():
    """启动页副标题须反映交战距离与拦截率估算（非旧 Pk 文案）。"""
    from scripts.frontend_catalog import SIMULATORS

    sat = next(s for s in SIMULATORS if s['id'] == 'missile_interception')
    assert '拦截率' in sat['subtitle']
    assert 'Pk 估算' not in sat['subtitle']
    assert sat['eyebrow'] == 'SHIPBORNE MISSILE INTERCEPTION'


def test_catalog_takeoff_eyebrow_is_carrier_takeoff():
    """起飞仿真启动页英文眉题为 CARRIER TAKEOFF。"""
    from scripts.frontend_catalog import SIMULATORS

    takeoff = next(s for s in SIMULATORS if s['id'] == 'takeoff')
    assert takeoff['eyebrow'] == 'CARRIER TAKEOFF'


def test_missile_interception_pages_english_eyebrow():
    """饱和打击页标题下方英文须为 SHIPBORNE MISSILE INTERCEPTION，且无 LOCAL PYODIDE。"""
    html = (ROOT / 'docs' / 'missile-interception-strike.html').read_text(encoding='utf-8')
    wxml = (ROOT / 'miniprogram' / 'pages' / 'missile_interception' / 'missile_interception.wxml').read_text(
        encoding='utf-8'
    )
    view = (ROOT / 'ios' / 'CarrierTakeOff' / 'MissileInterceptionStrikeView.swift').read_text(
        encoding='utf-8'
    )
    label = 'SHIPBORNE MISSILE INTERCEPTION'
    assert label in html
    assert label in wxml
    assert label in view
    assert 'LOCAL PYODIDE' not in view
    assert 'SATURATION ATTACK' not in html
    assert 'SATURATION ATTACK' not in view


def test_missile_interception_ui_no_ecm_fields():
    """三端 UI 与估算传参均不含抗干扰档数。"""
    html = (ROOT / 'docs' / 'missile-interception-strike.html').read_text(encoding='utf-8')
    web_js = (ROOT / 'docs' / 'js' / 'missile_interception.js').read_text(encoding='utf-8')
    wxml = (ROOT / 'miniprogram' / 'pages' / 'missile_interception' / 'missile_interception.wxml').read_text(
        encoding='utf-8'
    )
    mp_js = (ROOT / 'miniprogram' / 'pages' / 'missile_interception' / 'missile_interception.js').read_text(
        encoding='utf-8'
    )
    view = (ROOT / 'ios' / 'CarrierTakeOff' / 'MissileInterceptionStrikeView.swift').read_text(
        encoding='utf-8'
    )
    vm = (ROOT / 'ios' / 'CarrierTakeOff' / 'MissileInterceptionViewModel.swift').read_text(
        encoding='utf-8'
    )
    assert 'id="ecm"' not in html
    assert '抗干扰' not in html
    assert 'ecm:' not in web_js
    assert '抗干扰系数' not in web_js
    assert '抗干扰' not in wxml
    assert 'ecm:' not in mp_js
    assert '抗干扰' not in view
    assert '"ecm"' not in vm


def _assert_missile_counts_first(text: str, channel: str, nm_keys: tuple[str, ...], ni_keys: tuple[str, ...]) -> None:
    """断言来袭数量与拦截弹数量为参数区最先出现的两个数量输入。"""
    nm_key, nm_idx = _first_match_index(text, nm_keys)
    ni_key, ni_idx = _first_match_index(text, ni_keys)
    assert nm_idx < ni_idx, f'{channel} 应先「{nm_key}」后「{ni_key}」'
    # 二者须早于后续分区标题与预设
    for later in ('打击方', '预警机', '舰载雷达'):
        assert later in text, f'{channel} 缺少分区「{later}」'
        assert nm_idx < text.index(later) and ni_idx < text.index(later), (
            f'{channel} 导弹数量字段须位于「{later}」分区之前'
        )


def test_no_awacs_option_present_in_all_channels():
    """三端均需支持"无预警机"选项：Web/小程序/iOS 均能设置 has_awacs=False。"""
    html = (ROOT / 'docs' / 'missile-interception-strike.html').read_text(encoding='utf-8')
    web_js = (ROOT / 'docs' / 'js' / 'missile_interception.js').read_text(encoding='utf-8')
    wxml = (ROOT / 'miniprogram' / 'pages' / 'missile_interception' / 'missile_interception.wxml').read_text(
        encoding='utf-8'
    )
    mp_js = (ROOT / 'miniprogram' / 'pages' / 'missile_interception' / 'missile_interception.js').read_text(
        encoding='utf-8'
    )
    view = (ROOT / 'ios' / 'CarrierTakeOff' / 'MissileInterceptionStrikeView.swift').read_text(
        encoding='utf-8'
    )
    vm = (ROOT / 'ios' / 'CarrierTakeOff' / 'MissileInterceptionViewModel.swift').read_text(
        encoding='utf-8'
    )

    assert '无预警机' in html, 'HTML 缺少无预警机选项文案'
    assert '__none__' in html and '__none__' in web_js, 'HTML/JS 缺少无预警机 __none__ value'
    assert 'has_awacs' in web_js, 'Web 估算参数缺少 has_awacs'

    assert '无预警机' in wxml, '小程序 wxml 缺少无预警机相关提示文案'
    assert '无预警机' in mp_js, '小程序 js 缺少无预警机选项名称'
    assert 'has_awacs' in mp_js, '小程序估算参数缺少 has_awacs'

    assert '无预警机' in (view + vm), 'iOS 缺少无预警机相关文案'
    assert 'has_awacs' in vm, 'iOS 估算参数缺少 has_awacs'


def test_two_level_nation_model_selectors_in_all_channels():
    """三端：反舰独立国别；驱护+防空共用「防御方国别」，且位于两侧型号选择器上方。"""
    html = (ROOT / 'docs' / 'missile-interception-strike.html').read_text(encoding='utf-8')
    web_js = (ROOT / 'docs' / 'js' / 'missile_interception.js').read_text(encoding='utf-8')
    wxml = (ROOT / 'miniprogram' / 'pages' / 'missile_interception' / 'missile_interception.wxml').read_text(
        encoding='utf-8'
    )
    mp_js = (ROOT / 'miniprogram' / 'pages' / 'missile_interception' / 'missile_interception.js').read_text(
        encoding='utf-8'
    )
    view = (ROOT / 'ios' / 'CarrierTakeOff' / 'MissileInterceptionStrikeView.swift').read_text(
        encoding='utf-8'
    )
    vm = (ROOT / 'ios' / 'CarrierTakeOff' / 'MissileInterceptionViewModel.swift').read_text(
        encoding='utf-8'
    )

    for channel, text, asm_nation, asm_model, ship_model, sam_model in (
        ('HTML', html, '反舰导弹国别', '反舰导弹型号', '驱护舰艇型号', '舰载防空导弹型号'),
        ('小程序', wxml, '反舰导弹国别', '反舰导弹型号', '驱护舰艇型号', '防空导弹型号'),
        ('iOS', view, '反舰导弹国别', '反舰导弹型号', '驱护舰艇型号', '防空导弹型号'),
    ):
        assert '防御方国别' in text, f'{channel} 缺少共用防御方国别选择器'
        assert asm_nation in text and asm_model in text, f'{channel} 缺少反舰国别/型号'
        assert ship_model in text and sam_model in text, f'{channel} 缺少驱护/防空型号'
        # 旧的分列国别选择器不得残留
        assert '驱护舰艇国别' not in text, f'{channel} 仍保留驱护舰艇国别'
        assert '防空导弹国别' not in text and '舰载防空导弹国别' not in text, (
            f'{channel} 仍保留防空导弹国别'
        )
        assert text.index(asm_nation) < text.index(asm_model)
        assert text.index('防御方国别') < text.index(ship_model) < text.index(sam_model)

    assert 'id="asmNation"' in html and 'id="defenderNation"' in html
    assert 'id="shipNation"' not in html and 'id="samNation"' not in html
    assert 'filterPresetsByNation' in web_js and 'nationsSorted' in web_js
    assert 'nationsUnion' in web_js and 'bindSharedNationModelSelects' in web_js
    assert 'bindNationModelSelects' in web_js

    assert 'bindchange="onAsmNation"' in wxml
    assert 'bindchange="onDefenderNation"' in wxml
    assert 'bindchange="onShipNation"' not in wxml
    assert 'bindchange="onSamNation"' not in wxml
    assert 'filterPresetsByNation' in mp_js and 'nationsSorted' in mp_js
    assert 'nationsUnion' in mp_js and 'onDefenderNation' in mp_js
    assert 'asmFiltered' in mp_js and 'samFiltered' in mp_js and 'shipFiltered' in mp_js

    assert 'nationPicker(' in view
    assert 'vm.asmModels' in view and 'vm.samModels' in view and 'vm.shipModels' in view
    assert 'vm.defenderNations' in view and 'resetDefenderModels' in view
    assert 'func nationsSorted' in vm and 'func filterPresets' in vm
    assert 'func nationsUnion' in vm
    assert 'selectedAsmNation' in vm and 'selectedDefenderNation' in vm
    assert 'selectedShipNation' not in vm and 'selectedSamNation' not in vm


def test_missile_counts_at_top_of_inputs():
    """三端：反舰/来袭数量与防空/拦截弹数量位于所有输入参数最上方。"""
    html = (ROOT / 'docs' / 'missile-interception-strike.html').read_text(encoding='utf-8')
    wxml = (ROOT / 'miniprogram' / 'pages' / 'missile_interception' / 'missile_interception.wxml').read_text(
        encoding='utf-8'
    )
    view = (ROOT / 'ios' / 'CarrierTakeOff' / 'MissileInterceptionStrikeView.swift').read_text(
        encoding='utf-8'
    )
    _assert_missile_counts_first(html, 'HTML', ('来袭导弹数量',), ('防空拦截弹数量', '拦截弹数量'))
    _assert_missile_counts_first(wxml, '小程序', ('来袭导弹数量',), ('拦截弹数量',))
    _assert_missile_counts_first(view, 'iOS', ('来袭数量',), ('拦截弹数量',))


def test_html_missile_interception_stale_nav_and_auto_estimate():
    """HTML 饱和页：探测距离不默认 0、启动自动估算、过期提示、章节跳转与回到顶部。"""
    html = (ROOT / 'docs' / 'missile-interception-strike.html').read_text(encoding='utf-8')
    js = (ROOT / 'docs' / 'js' / 'missile_interception.js').read_text(encoding='utf-8')
    assert 'id="awacsDetectKm"' in html
    assert 'value="0"' not in html.split('id="awacsDetectKm"', 1)[1][:200]
    assert 'placeholder="待估算"' in html
    assert 'id="staleBanner"' in html
    assert 'id="backToTop"' in html
    assert 'id="inputPanel"' in html
    assert 'href="#resultsPanel"' in html
    assert 'bootEstimateThenRun' in js
    assert 'markResultsStale' in js
    assert 'roundKillProbability' in js
    assert 'relative_label' in js
    assert 'field_hints' in js


def test_miniprogram_missile_interception_stale_and_kill_fallback():
    """小程序饱和页：过期提示、术语问号、杀伤概率回退与待估算探测距离。"""
    wxml = (ROOT / 'miniprogram' / 'pages' / 'missile_interception' / 'missile_interception.wxml').read_text(
        encoding='utf-8'
    )
    js = (ROOT / 'miniprogram' / 'pages' / 'missile_interception' / 'missile_interception.js').read_text(
        encoding='utf-8'
    )
    assert 'resultStale' in wxml
    assert '待估算' in wxml
    assert 'onBackToTop' in wxml
    assert 'data-key="rcs"' in wxml
    assert 'data-key="seekerType"' in wxml
    assert 'roundKillProbability' in js
    assert 'markResultsStale' in js
    assert 'relative_label' in js


def test_ios_missile_interception_stale_nav_and_auto_estimate():
    """iOS 饱和页：过期提示、启动估算、回到顶部、术语提示。"""
    view = (ROOT / 'ios' / 'CarrierTakeOff' / 'MissileInterceptionStrikeView.swift').read_text(
        encoding='utf-8'
    )
    vm = (ROOT / 'ios' / 'CarrierTakeOff' / 'MissileInterceptionViewModel.swift').read_text(
        encoding='utf-8'
    )
    assert 'resultStale' in view
    assert '待估算' in vm
    assert '↑ 顶部' in view
    assert 'pageTop' in view
    assert 'estimateDistanceAndPk' in view
    assert 'markResultsStale' in vm
    assert 'func rangeHint' in vm
    assert 'hintKey: "rcs"' in view
    assert 'hintKey: "seekerType"' in view
    assert 'relative_label' in view
    assert 'plan_rows' in view

