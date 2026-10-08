"""地球曲率雷达视距（公里）。"""
from __future__ import annotations

import math


def radar_horizon_km(h1: float, h2: float) -> float:
    """雷达视距；h1/h2 为天线与目标高度（米）。"""
    return 4.12 * (math.sqrt(h1) + math.sqrt(h2))
