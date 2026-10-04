#!/usr/bin/env python3
"""将作战半径挂载图从 data/ 同步到 Web、小程序与 iOS 资源目录。"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DOCS_DEST = ROOT / 'docs' / 'assets' / 'combat_radius' / 'loadout'
MINIPROGRAM_DEST = ROOT / 'miniprogram' / 'assets' / 'combat_radius' / 'loadout'
IOS_DEST = ROOT / 'ios' / 'CarrierTakeOff' / 'Resources' / 'combat_radius' / 'loadout'


def _sync_dir(src_dir: Path, dest_dir: Path) -> int:
    """复制 src_dir 下全部 jpg 到 dest_dir，返回文件数。"""
    dest_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for src in sorted(src_dir.glob('*.jpg')):
        shutil.copy2(src, dest_dir / src.name)
        count += 1
    return count


def main() -> None:
    """同步挂载图到三端静态资源目录。"""
    from utils.combat_radius.combat_radius_loadout_images import list_loadout_image_files
    from utils.paths import COMBAT_RADIUS_LOADOUT_DIR

    if not COMBAT_RADIUS_LOADOUT_DIR.is_dir():
        raise FileNotFoundError(f'缺少挂载图源目录 {COMBAT_RADIUS_LOADOUT_DIR}')

    files = list_loadout_image_files()
    if not files:
        raise FileNotFoundError(f'{COMBAT_RADIUS_LOADOUT_DIR} 下无 *.jpg 挂载图')

    n_docs = _sync_dir(COMBAT_RADIUS_LOADOUT_DIR, DOCS_DEST)
    n_mp = _sync_dir(COMBAT_RADIUS_LOADOUT_DIR, MINIPROGRAM_DEST)
    n_ios = _sync_dir(COMBAT_RADIUS_LOADOUT_DIR, IOS_DEST)
    print(f'Wrote {n_docs} loadout images -> {DOCS_DEST}')
    print(f'Wrote {n_mp} loadout images -> {MINIPROGRAM_DEST}')
    print(f'Wrote {n_ios} loadout images -> {IOS_DEST}')


if __name__ == '__main__':
    main()
