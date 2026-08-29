#!/usr/bin/env python3
"""预计算全部机型作战半径仪表盘，写入 data/combat_radius_results.json。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    """生成作战半径预计算快照。"""
    from utils.combat_radius.combat_radius_results import write_combat_radius_results

    path = write_combat_radius_results()
    print(f'Wrote {path}')


if __name__ == '__main__':
    main()
