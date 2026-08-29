"""饱和打击结果展示辅助：单目标杀伤概率与策略对比标签。

前端曾用 floor(每目标枚数) 计算杀伤概率，弹药不足 1 枚/目标时恒为 0%。
此处按「部分目标多分 1 枚」的混合期望，供三端直接展示。
"""
from __future__ import annotations

from typing import Any


def round_kill_probability(pk: float, interceptors_per_target: float) -> float:
    """本轮单目标期望杀伤概率。

    每目标约分配 n 枚时：floor(n) 枚分给全部目标，余数 frac 的目标再多 1 枚。
    例如 n=0.67、pk=0.97 → 67% 目标分到 1 枚，杀伤概率约 65%，而不是 floor 后的 0%。
    """
    pk = min(1.0, max(0.0, float(pk)))
    n = max(0.0, float(interceptors_per_target))
    k = int(n)
    frac = n - k
    p_k = 0.0 if k <= 0 else 1.0 - (1.0 - pk) ** k
    p_k1 = 1.0 - (1.0 - pk) ** (k + 1)
    return (1.0 - frac) * p_k + frac * p_k1


def build_plan_rows(
    plan: list[int],
    avg_survivors: list[float],
    pk: float,
) -> list[dict[str, Any]]:
    """由最优方案与轮初存活数生成弹药分配表行（含杀伤概率）。"""
    rows: list[dict[str, Any]] = []
    n_rounds = len(plan)
    for i in range(n_rounds):
        surv = float(avg_survivors[i]) if i < len(avg_survivors) else 0.0
        budget = int(plan[i])
        per_target = (budget / surv) if surv > 0 else 0.0
        rows.append({
            'round': i + 1,
            'budget': budget,
            'survivors': surv,
            'per_target': per_target,
            'kill_prob': round_kill_probability(pk, per_target),
        })
    return rows


def relative_strategy_delta(leak: float, best_leak: float) -> dict[str, Any]:
    """相对最优方案的突防差：标签 + 百分比 + 色调。

    突防越低越好；与最优相同标「最优」，否则标「更差」并给出相对增幅。
    """
    delta = float(leak) - float(best_leak)
    if abs(delta) < 1e-9:
        return {
            'delta': 0.0,
            'delta_pct': 0.0,
            'label': '最优',
            'tone': 'best',
        }
    pct = (delta / best_leak * 100.0) if best_leak > 1e-9 else None
    if pct is None:
        label = f'更差 +{delta:.2f}'
    else:
        label = f'更差 +{pct:.0f}%'
    return {
        'delta': delta,
        'delta_pct': pct,
        'label': label,
        'tone': 'worse',
    }


def annotate_strategy_candidates(
    candidates: list[dict[str, Any]],
    best_leak: float,
    best_name: str,
    best_plan: list[int],
) -> list[dict[str, Any]]:
    """为策略候选补充相对最优标签，不修改原字典以外的字段。"""
    best_key = ','.join(str(x) for x in best_plan)
    out: list[dict[str, Any]] = []
    for raw in candidates:
        item = dict(raw)
        plan = list(item.get('plan') or [])
        leak = float(item.get('expected_leak', 0.0))
        rel = relative_strategy_delta(leak, best_leak)
        is_best = item.get('name') == best_name and ','.join(str(x) for x in plan) == best_key
        if is_best:
            rel = {
                'delta': 0.0,
                'delta_pct': 0.0,
                'label': '最优',
                'tone': 'best',
            }
        item['relative_label'] = rel['label']
        item['relative_tone'] = rel['tone']
        item['delta'] = rel['delta']
        item['delta_pct'] = rel['delta_pct']
        item['is_best'] = is_best
        out.append(item)
    return out
