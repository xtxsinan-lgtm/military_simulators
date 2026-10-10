"""饱和打击 CSV 预设单元测试。"""
from __future__ import annotations

from utils.missile_interception.missile_interception_presets import (
    AEW_PRESETS,
    ASM_PRESETS,
    SAM_PRESETS,
    SHIP_PRESETS,
    build_missile_interception_presets_payload,
    filter_presets_by_nation,
    get_preset_by_id,
    load_presets,
    nations_sorted,
    nations_union,
)
from utils.paths import MISSILE_INTERCEPTION_MISSILE_CSV, MISSILE_INTERCEPTION_RADAR_CSV


def test_get_preset_by_id_found():
    """能按 id 找到反舰导弹预设。"""
    p = get_preset_by_id(ASM_PRESETS, 'yj12')
    assert p is not None
    assert p['vm'] == 3.5
    assert p['traj'] == 'high'


def test_missile_presets_have_positive_max_g():
    """反舰弹与防空弹预设都带正的末端过载，供运动学 Pk 使用。"""
    for group in (ASM_PRESETS, SAM_PRESETS):
        assert group
        for item in group:
            assert item.get('max_g', 0) > 0, item['id']


def test_published_g_anchors():
    """少量有公开或广泛引用量级的过载锚点：Aster 30 高过载，亚音速鱼叉远低于它。"""
    aster = get_preset_by_id(SAM_PRESETS, 'aster30')
    essm = get_preset_by_id(SAM_PRESETS, 'essm')
    harpoon = get_preset_by_id(ASM_PRESETS, 'harpoon')
    zircon = get_preset_by_id(ASM_PRESETS, 'zircon')
    yj21 = get_preset_by_id(ASM_PRESETS, 'yj21')
    assert aster is not None and aster['max_g'] >= 50
    assert essm is not None and essm['max_g'] >= 40
    assert harpoon is not None and harpoon['max_g'] <= 6
    assert zircon is not None and zircon['max_g'] <= harpoon['max_g'] + 3
    assert yj21 is not None and yj21['max_g'] > zircon['max_g']


def test_yj17_yj20_yj21_traj_types():
    """鹰击-17 为滑翔体弹道，鹰击-20/21 为弹道导弹弹道。"""
    yj17 = get_preset_by_id(ASM_PRESETS, 'yj17')
    yj20 = get_preset_by_id(ASM_PRESETS, 'yj20')
    yj21 = get_preset_by_id(ASM_PRESETS, 'yj21')
    assert yj17 is not None and yj17['traj'] == 'glide'
    assert yj20 is not None and yj20['traj'] == 'ballistic'
    assert yj21 is not None and yj21['traj'] == 'ballistic'


def test_get_preset_by_id_missing():
    """未知 id 返回 None。"""
    assert get_preset_by_id(ASM_PRESETS, 'no-such') is None


def test_build_missile_interception_presets_payload_keys():
    """目录载荷含四类预设且与 CSV 一致。"""
    payload = build_missile_interception_presets_payload()
    assert set(payload) == {'asm', 'aew', 'ship', 'sam'}
    assert len(payload['asm']) == len(ASM_PRESETS)
    assert len(payload['aew']) == len(AEW_PRESETS)
    assert len(payload['ship']) == len(SHIP_PRESETS)
    assert len(payload['sam']) == len(SAM_PRESETS)
    assert all('id' in x and 'name' in x for x in payload['sam'])


def test_load_presets_from_csv_path():
    """显式双库路径加载与默认路径一致。"""
    a = load_presets(MISSILE_INTERCEPTION_MISSILE_CSV, MISSILE_INTERCEPTION_RADAR_CSV)
    b = load_presets()
    assert [x['id'] for x in a['asm']] == [x['id'] for x in b['asm']]
    assert [x['id'] for x in a['aew']] == [x['id'] for x in b['aew']]


def test_load_presets_missing_file_returns_empty():
    """任一 CSV 不存在时返回空分组（Pyodide 等环境）。"""
    empty = load_presets('/tmp/no-such-missile.csv', '/tmp/no-such-radar.csv')
    assert empty == {'asm': [], 'aew': [], 'ship': [], 'sam': []}
    half = load_presets('/tmp/no-such-missile.csv', MISSILE_INTERCEPTION_RADAR_CSV)
    assert half == {'asm': [], 'aew': [], 'ship': [], 'sam': []}


def test_nations_sorted_dedups_by_first_appearance():
    """国别按首次出现顺序去重，忽略空白与缺失。"""
    presets = [
        {'id': 'a', 'nation': '中国'},
        {'id': 'b', 'nation': '美国'},
        {'id': 'c', 'nation': '中国'},
        {'id': 'd', 'nation': ' '},
        {'id': 'e'},
    ]
    assert nations_sorted(presets) == ['中国', '美国']


def test_nations_sorted_on_real_presets():
    """真实预设的国别列表非空且不含空串。"""
    for presets in (ASM_PRESETS, SAM_PRESETS, SHIP_PRESETS, AEW_PRESETS):
        nations = nations_sorted(presets)
        assert nations
        assert all(n.strip() for n in nations)
    assert '中国' in nations_sorted(ASM_PRESETS)
    assert '美国' in nations_sorted(SHIP_PRESETS)


def test_filter_presets_by_nation():
    """按国别过滤只返回该国别型号。"""
    china = filter_presets_by_nation(ASM_PRESETS, '中国')
    assert china
    assert all(x['nation'] == '中国' for x in china)
    assert 'yj12' in [x['id'] for x in china]
    assert 'harpoon' not in [x['id'] for x in china]


def test_filter_presets_by_nation_empty_returns_all():
    """国别为空视为不限国别，返回全部型号。"""
    assert len(filter_presets_by_nation(SAM_PRESETS, '')) == len(SAM_PRESETS)
    assert filter_presets_by_nation(SAM_PRESETS, '  ') == list(SAM_PRESETS)
    assert filter_presets_by_nation(SAM_PRESETS, '不存在的国别') == []


def test_nations_union_merges_ship_and_sam():
    """驱护+防空国别合并为并集，保留首次出现顺序且去重。"""
    a = [{'id': '1', 'nation': '中国'}, {'id': '2', 'nation': '美国'}]
    b = [{'id': '3', 'nation': '美国'}, {'id': '4', 'nation': '欧洲'}]
    assert nations_union(a, b) == ['中国', '美国', '欧洲']
    assert nations_union([], []) == []
    # 真实数据：共用国别选择器应同时覆盖舰艇与防空弹两侧
    union = nations_union(SHIP_PRESETS, SAM_PRESETS)
    assert '中国' in union and '美国' in union
    for n in nations_sorted(SHIP_PRESETS) + nations_sorted(SAM_PRESETS):
        assert n in union


def test_payload_presets_carry_nation():
    """目录载荷四类预设均带国别，供前端两级选择。"""
    payload = build_missile_interception_presets_payload()
    for cat in ('asm', 'sam', 'ship', 'aew'):
        assert all(x.get('nation') for x in payload[cat]), f'{cat} 存在无国别预设'
