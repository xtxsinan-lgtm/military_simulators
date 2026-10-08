"""雷达视距公式单元测试。"""
from __future__ import annotations

import math

from utils.radar_horizon import radar_horizon_km


def test_radar_horizon_km_formula():
    """与饱和打击雷达模块共用同一系数 4.12。"""
    h1, h2 = 9000.0, 10.0
    expect = 4.12 * (math.sqrt(h1) + math.sqrt(h2))
    assert radar_horizon_km(h1, h2) == expect
