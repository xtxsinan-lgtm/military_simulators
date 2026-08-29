"""预计算脚本入口单元测试。"""
from __future__ import annotations

from scripts.build_combat_radius_results import main


def test_build_combat_radius_results_script_main(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(
        'utils.combat_radius.combat_radius_results.write_combat_radius_results',
        lambda: tmp_path / 'combat_radius_results.json',
    )
    main()
    assert 'combat_radius_results.json' in capsys.readouterr().out
