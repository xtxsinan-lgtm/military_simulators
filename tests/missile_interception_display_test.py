"""饱和打击结果展示辅助单元测试。"""
from __future__ import annotations

from utils.missile_interception.missile_interception_display import (
    annotate_strategy_candidates,
    build_plan_rows,
    relative_strategy_delta,
    round_kill_probability,
)


def test_round_kill_probability_fractional_allocation():
    """不足 1 枚/目标时不得因 floor 变成 0%。"""
    p = round_kill_probability(0.97, 16 / 24)
    assert p == 0.97 * (16 / 24)
    assert 0.6 < p < 0.7


def test_round_kill_probability_integer():
    """整数枚数时等于 1-(1-pk)^k。"""
    assert round_kill_probability(0.7, 2.0) == 1.0 - (1.0 - 0.7) ** 2
    assert round_kill_probability(0.5, 0.0) == 0.0
    assert round_kill_probability(1.0, 3.0) == 1.0


def test_round_kill_probability_clamps_pk():
    """pk 超出 [0,1] 时夹紧。"""
    assert round_kill_probability(-0.2, 1.0) == 0.0
    assert round_kill_probability(1.5, 1.0) == 1.0


def test_build_plan_rows_includes_kill_prob():
    """分配表行含杀伤概率且默认参数下不为 0。"""
    rows = build_plan_rows([4, 4, 4, 4], [24.0, 18.0, 12.0, 8.0], 0.7)
    assert len(rows) == 4
    assert rows[0]['round'] == 1
    assert rows[0]['budget'] == 4
    assert rows[0]['per_target'] == 4 / 24
    assert rows[0]['kill_prob'] > 0
    assert rows[0]['kill_prob'] == round_kill_probability(0.7, 4 / 24)


def test_build_plan_rows_zero_survivors():
    """轮初存活为 0 时每目标分配与杀伤概率为 0。"""
    rows = build_plan_rows([2], [0.0], 0.9)
    assert rows[0]['per_target'] == 0.0
    assert rows[0]['kill_prob'] == 0.0


def test_relative_strategy_delta_best():
    """与最优相同标「最优」。"""
    rel = relative_strategy_delta(10.0, 10.0)
    assert rel['label'] == '最优'
    assert rel['tone'] == 'best'
    assert rel['delta'] == 0.0


def test_relative_strategy_delta_worse():
    """突防更高标「更差」并给出相对增幅。"""
    rel = relative_strategy_delta(12.0, 10.0)
    assert rel['tone'] == 'worse'
    assert rel['delta'] == 2.0
    assert rel['delta_pct'] == 20.0
    assert '更差' in rel['label']
    assert '20%' in rel['label']


def test_annotate_strategy_candidates_marks_best():
    """最优方案标 is_best，其余带更差标签。"""
    cands = [
        {'name': '逐轮均分', 'plan': [4, 4], 'expected_leak': 8.0},
        {'name': '前重后轻', 'plan': [6, 2], 'expected_leak': 9.0},
    ]
    out = annotate_strategy_candidates(cands, 8.0, '逐轮均分', [4, 4])
    assert out[0]['is_best'] is True
    assert out[0]['relative_label'] == '最优'
    assert out[1]['is_best'] is False
    assert out[1]['relative_tone'] == 'worse'
    assert '更差' in out[1]['relative_label']
