"""饱和打击 / 反导拦截仿真核心（可命令行运行）。

窗口数由发现距离、双方速度、火控锁定时间反推；分配策略采用蒙特卡洛 + 局部爬山，
寻找期望突防数最低的逐轮弹药方案。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

# 支持直接运行：python3 simulators/missile_interception/missile_interception_strike.py
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from utils.missile_interception.missile_interception_config import estimate_defaults, physics_config, simulation_config, ui_config
from utils.missile_interception.missile_interception_monte_carlo import optimize_plan
from utils.missile_interception.missile_interception_radar import (
    binding_limit_label,
    estimate_engagement_distance,
    estimate_pk,
)
from utils.missile_interception.missile_interception_windows import compute_windows
from utils.missile_interception.missile_interception_display import (
    annotate_strategy_candidates,
    build_plan_rows,
)

# 海平面标准声速（m/s）
MACH_MPS = float(physics_config()['mach_mps'])

_UI = ui_config()
_EST = estimate_defaults()
_SIM = simulation_config()


def run_missile_interception_strike(
    nm: int,
    vm_ma: float,
    discovery_km: float,
    ni: int,
    vi_ma: float,
    pk: float,
    t_lock_s: float,
    min_range_km: float,
    search_trials: int = 900,
    final_trials: int = 6000,
) -> dict[str, Any]:
    """运行饱和打击拦截仿真，返回结构化结果。"""
    nm = max(1, int(round(nm)))
    ni = max(1, int(round(ni)))
    vm_mps = max(0.1, float(vm_ma)) * MACH_MPS
    vi_mps = max(0.1, float(vi_ma)) * MACH_MPS
    discovery_m = max(0.1, float(discovery_km)) * 1000.0
    min_range_m = max(0.0, float(min_range_km)) * 1000.0
    pk = min(1.0, max(0.0, float(pk)))
    t_lock_s = max(0.0, float(t_lock_s))

    windows = compute_windows(discovery_m, vm_mps, vi_mps, t_lock_s, min_range_m)
    n_rounds = len(windows)

    base: dict[str, Any] = {
        'success': True,
        'nm': nm,
        'ni': ni,
        'pk': pk,
        't_lock_s': t_lock_s,
        'vm_ma': float(vm_ma),
        'vi_ma': float(vi_ma),
        'discovery_km': float(discovery_km),
        'min_range_km': float(min_range_km),
        'n_rounds': n_rounds,
        'windows': [
            {
                'round': w['round'],
                'dist_start_km': w['dist_start_m'] / 1000.0,
                't_fly_s': w['t_fly_s'],
                'total_t_s': w['total_t_s'],
                'dist_end_km': w['dist_end_m'] / 1000.0,
            }
            for w in windows
        ],
    }

    if n_rounds == 0:
        base.update({
            'expected_leak': float(nm),
            'intercept_rate': 0.0,
            'best': {'name': '', 'plan': []},
            'avg_survivors': [float(nm)],
            'all_candidates': [],
            'plan_rows': [],
            'final_trials': final_trials,
            'note': (
                '当前参数下无法形成有效拦截窗口：来袭导弹将在完成一次火控锁定前突破最小交战距离。'
                '建议增大发现距离、提高拦截弹速度，或缩短火控锁定时间。'
            ),
        })
        return base

    opt = optimize_plan(
        nm, ni, pk, n_rounds,
        search_trials=search_trials,
        final_trials=final_trials,
    )
    expected_leak = opt['final_res']['expected_leak']
    intercept_rate = 1.0 - expected_leak / nm
    best = opt['best']
    plan_str = ', '.join(str(x) for x in best['plan'])
    note = (
        f'结论：在 {n_rounds} 个拦截窗口、共 {ni} 枚拦截弹、单发命中概率 {pk * 100:.0f}% 的条件下，'
        f'采用「{best["name"]}」分配（各轮弹药预算 [{plan_str}]），期望突防导弹数最低，'
        f'约为 {expected_leak:.2f} 枚（拦截率 {intercept_rate * 100:.1f}%）。'
        f'搜索方法：先评估均分/前重/后重/中段集中等候选方案，再以相邻轮次间转移一枚弹药的方式做局部爬山，'
        f'直至无法进一步降低期望突防数。'
    )
    avg_survivors = opt['final_res']['avg_survivors']
    plan = list(best.get('plan') or [])
    annotated = annotate_strategy_candidates(
        opt['all_candidates'],
        expected_leak,
        str(best.get('name') or ''),
        plan,
    )
    base.update({
        'expected_leak': expected_leak,
        'intercept_rate': intercept_rate,
        'best': best,
        'avg_survivors': avg_survivors,
        'all_candidates': annotated,
        'plan_rows': build_plan_rows(plan, avg_survivors, pk),
        'final_trials': opt['final_trials'],
        'note': note,
    })
    return base


def _opt_bool(v: Any, default: bool = True) -> bool:
    """解析可选布尔参数（兼容 bool / 数字 / 字符串多种传参形式），空值用默认。"""
    if v is None or v == '':
        return default
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    s = str(v).strip().lower()
    if s in ('0', 'false', 'no', 'off', 'none'):
        return False
    if s in ('1', 'true', 'yes', 'on'):
        return True
    return default


def run_estimate_distance_from_params(params: dict[str, Any]) -> dict[str, Any]:
    """从参数字典估算交战距离（供 Web/API）。"""
    awacs_type = str(params.get('awacs_type', _EST['awacs_type']))
    has_awacs_raw = params.get('has_awacs')
    if has_awacs_raw is None or has_awacs_raw == '':
        # 未显式传 has_awacs 时，预警机体制/预设为 none 也视为「无预警机」
        implied_none = awacs_type == 'none' or str(params.get('awacs_preset', '')) == 'none'
        has_awacs = not implied_none
    else:
        has_awacs = _opt_bool(has_awacs_raw, True)

    result = estimate_engagement_distance(
        rcs=float(params.get('rcs', _EST['rcs'])),
        traj=str(params.get('traj', _EST['traj'])),
        awacs_area=float(params.get('awacs_area', _EST['awacs_area'])),
        awacs_type=awacs_type,
        standoff_km=float(params.get('standoff', _EST['standoff'])),
        ship_area=float(params.get('ship_area', _EST['ship_area'])),
        ship_type=str(params.get('ship_type', _EST['ship_type'])),
        sam_range_km=float(params.get('sam_range', _EST['sam_range'])),
        has_awacs=has_awacs,
        sam_max_alt_km=float(params.get('sam_max_alt', _EST.get('sam_max_alt', 33))),
        dive_angle_deg_val=(
            float(params['dive_angle_deg']) if params.get('dive_angle_deg') not in (None, '') else None
        ),
    )
    result['binding'] = binding_limit_label(result)
    return result


def run_estimate_pk_from_params(params: dict[str, Any]) -> dict[str, Any]:
    """从参数字典估算 Pk（供 Web/API）。"""
    return estimate_pk(
        vm_ma=float(params.get('vm', _EST['vm'])),
        vi_ma=float(params.get('vi', _EST['vi'])),
        rcs=float(params.get('rcs', _EST['rcs'])),
        traj=str(params.get('traj', _EST['traj'])),
        ship_area=float(params.get('ship_area', _EST['ship_area'])),
        ship_type=str(params.get('ship_type', _EST['ship_type'])),
        interceptor_dia_m=float(params.get('interceptor_dia', _EST['interceptor_dia'])),
        seeker_type=str(params.get('seeker_type', _EST['seeker_type'])),
        maneuver_class=str(params.get('maneuver_class', '') or '') or None,
        asm_id=str(params.get('asm_id', '') or ''),
    )


def main() -> None:
    """命令行入口：默认参数运行一次仿真并打印摘要。"""
    parser = argparse.ArgumentParser(description='饱和打击 / 反导拦截仿真')
    parser.add_argument('--nm', type=int, default=int(_UI['nm']), help='来袭导弹数量')
    parser.add_argument('--vm', type=float, default=float(_UI['vm']), help='来袭速度（马赫）')
    parser.add_argument('--D', type=float, default=float(_UI['discovery_km']), dest='discovery_km', help='发现距离（km）')
    parser.add_argument('--ni', type=int, default=int(_UI['ni']), help='拦截弹数量')
    parser.add_argument('--vi', type=float, default=float(_UI['vi']), help='拦截弹速度（马赫）')
    parser.add_argument('--pk', type=float, default=float(_UI['pk']), help='单发拦截成功概率')
    parser.add_argument('--tlock', type=float, default=float(_UI['tlock']), help='火控锁定时间（s）')
    parser.add_argument('--minr', type=float, default=float(_UI['minr']), help='最小交战距离（km）')
    parser.add_argument('--fast', action='store_true', help='减少蒙特卡洛试验次数（调试用）')
    args = parser.parse_args()

    search_trials = int(_SIM['fast_search_trials']) if args.fast else int(_SIM['search_trials'])
    final_trials = int(_SIM['fast_final_trials']) if args.fast else int(_SIM['final_trials'])
    result = run_missile_interception_strike(
        nm=args.nm,
        vm_ma=args.vm,
        discovery_km=args.discovery_km,
        ni=args.ni,
        vi_ma=args.vi,
        pk=args.pk,
        t_lock_s=args.tlock,
        min_range_km=args.minr,
        search_trials=search_trials,
        final_trials=final_trials,
    )
    print(f'拦截窗口数: {result["n_rounds"]}')
    print(f'期望突防: {result["expected_leak"]:.2f} / {result["nm"]}')
    print(f'期望拦截率: {result["intercept_rate"] * 100:.1f}%')
    if result['best']['plan']:
        print(f'最优方案: {result["best"]["name"]} → {result["best"]["plan"]}')
    print(result['note'])


if __name__ == '__main__':
    main()
