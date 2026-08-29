#!/usr/bin/env python3
"""一键构建全部前端产物：physics.js/Swift + Web data.json + 小程序 + iOS。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    """按依赖顺序构建：物理 → 作战半径预计算 → GitHub Pages → 小程序 → iOS。"""
    from scripts.generate_frontend_physics import write_physics_files
    from scripts import build_combat_radius_results, build_docs, build_miniprogram, build_ios

    print('=== 1/5 生成前端 physics（JS + iOS Swift，常量来自 Python）===')
    write_physics_files()

    print('=== 2/5 预计算作战半径仪表盘 ===')
    build_combat_radius_results.main()

    print('=== 3/5 构建 Web（docs/data.json + docs/py）===')
    build_docs.main()

    print('=== 4/5 构建小程序（miniprogram/data/data.json）===')
    build_miniprogram.main()

    print('=== 5/5 构建 iOS（ios/CarrierTakeOff/Resources/data.json）===')
    build_ios.main()

    from scripts.generate_ios_xcodeproj import main as generate_xcodeproj

    print('=== 附：生成 CarrierTakeOff.xcodeproj ===')
    generate_xcodeproj()

    print('全部构建完成。')


if __name__ == '__main__':
    main()
