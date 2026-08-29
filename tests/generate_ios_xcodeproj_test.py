"""generate_ios_xcodeproj 单元测试。"""
from __future__ import annotations

from pathlib import Path

from scripts.generate_ios_xcodeproj import main as generate_xcodeproj
from utils.paths import ROOT


def test_generate_ios_xcodeproj_writes_pbxproj():
    """生成后的 project.pbxproj 须包含目标名与关键 Swift 源。"""
    generate_xcodeproj()
    path = ROOT / 'ios' / 'CarrierTakeOff.xcodeproj' / 'project.pbxproj'
    assert path.is_file()
    text = path.read_text(encoding='utf-8')
    assert 'CarrierTakeOff' in text
    assert 'ContentView.swift' in text
    assert 'data.json' in text
    assert 'engine.js' in text
    assert 'LocalSimulatorEngine.swift' in text
    assert 'CombatRadiusView.swift' in text
    assert 'PBXNativeTarget' in text
