"""作战半径挂载图映射单元测试。"""
from __future__ import annotations

from pathlib import Path

import pytest

from utils.combat_radius.combat_radius_loadout_images import (
    build_combat_radius_loadout_images_payload,
    inject_combat_radius_loadout_images,
    loadout_image_filename,
)
from utils.paths import COMBAT_RADIUS_LOADOUT_DIR, COMBAT_RADIUS_LOADOUT_IMAGES_JSON, ROOT


def test_loadout_images_json_exists_and_maps_known_aircraft():
    """映射文件存在且覆盖用户提供的典型机型。"""
    assert COMBAT_RADIUS_LOADOUT_IMAGES_JSON.is_file()
    payload = build_combat_radius_loadout_images_payload()
    aircraft = payload['aircraft']
    for aid in ('F-15E', 'FA-18E', 'FA-18C', 'F-14', 'F-16', 'Mirage-2000', 'Typhoon', 'Tejas', 'FA-50', 'Rafale'):
        assert aid in aircraft
        assert aircraft[aid].endswith('.jpg')


def test_loadout_image_files_exist_for_mapping():
    """映射中的每个文件名在 data/combat_radius_loadout/ 下都有实体文件。"""
    payload = build_combat_radius_loadout_images_payload()
    for fname in set(payload['aircraft'].values()):
        path = COMBAT_RADIUS_LOADOUT_DIR / fname
        assert path.is_file(), f'缺少挂载图源文件 {path}'


def test_loadout_image_filename_returns_none_for_unknown():
    """未知机型不返回文件名。"""
    assert loadout_image_filename('J-20') is None
    assert loadout_image_filename('') is None


def test_inject_combat_radius_loadout_images_overrides_disk(tmp_path: Path):
    """inject 可覆盖磁盘映射（Pyodide / 测试用）。"""
    inject_combat_radius_loadout_images({'version': 9, 'aircraft': {'TEST': 'x.jpg'}})
    try:
        assert loadout_image_filename('TEST') == 'x.jpg'
        assert build_combat_radius_loadout_images_payload()['version'] == 9
    finally:
        inject_combat_radius_loadout_images(
            __import__('json').loads(COMBAT_RADIUS_LOADOUT_IMAGES_JSON.read_text(encoding='utf-8'))
        )


def test_build_combat_radius_loadout_assets_script(tmp_path: Path, monkeypatch):
    """构建脚本会把 jpg 同步到 docs / 小程序 / iOS 目录。"""
    from scripts import build_combat_radius_loadout_assets

    src = tmp_path / 'src'
    src.mkdir()
    (src / 'demo.jpg').write_bytes(b'fake')
    monkeypatch.setattr('utils.paths.COMBAT_RADIUS_LOADOUT_DIR', src)
    docs_dest = tmp_path / 'docs'
    mp_dest = tmp_path / 'mp'
    ios_dest = tmp_path / 'ios'
    monkeypatch.setattr(build_combat_radius_loadout_assets, 'DOCS_DEST', docs_dest)
    monkeypatch.setattr(build_combat_radius_loadout_assets, 'MINIPROGRAM_DEST', mp_dest)
    monkeypatch.setattr(build_combat_radius_loadout_assets, 'IOS_DEST', ios_dest)
    build_combat_radius_loadout_assets.main()
    assert (docs_dest / 'demo.jpg').is_file()
    assert (mp_dest / 'demo.jpg').is_file()
    assert (ios_dest / 'demo.jpg').is_file()
