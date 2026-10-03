"""导弹射程仿真入口：按弹种估算单发，并按同一推进剂假设刷新样本表。"""
from __future__ import annotations

from typing import Any

from utils.missile_range.classes import estimate_by_class, glide_shape
from utils.missile_range.dataset import (
    all_missile_cases,
    build_missile_range_catalog_payload,
    evaluate_dataset,
)
from utils.missile_range.estimate import (
    DEFAULT_ISP_S,
    DEFAULT_PROPELLANT_DENSITY,
    optimize_hgv_geometry,
)


def opt_float(value: Any, default: float) -> float:
    """解析可选浮点；空值使用默认。"""
    if value is None or value == '':
        return default
    return float(value)


def opt_optional_float(value: Any) -> float | None:
    """空值表示不覆盖；有值则转成浮点。"""
    if value is None or value == '':
        return None
    return float(value)


def opt_bool(value: Any, default: bool) -> bool:
    """解析可选布尔。字符串按常见开关词处理。"""
    if value is None or value == '':
        return default
    if isinstance(value, str):
        return value.strip().lower() not in {'', '0', 'false', 'no', 'off'}
    return bool(value)


def resolve_ballistic_single_stage(params: dict[str, Any]) -> bool:
    """普通弹道是否锁定单级。

    ballistic_single_stage 优先。旧字段 ballistic_two_stage 为假时同样锁定单级。
    """
    if 'ballistic_single_stage' in params and params.get('ballistic_single_stage') not in (None, ''):
        return opt_bool(params.get('ballistic_single_stage'), False)
    if 'ballistic_two_stage' in params and params.get('ballistic_two_stage') not in (None, ''):
        return not opt_bool(params.get('ballistic_two_stage'), True)
    return False


def _required_float(params: dict[str, Any], key: str) -> float:
    if key not in params or params[key] is None or params[key] == '':
        raise ValueError(f'缺少参数 {key}')
    return float(params[key])


def include_dataset_rows(params: dict[str, Any]) -> bool:
    """单发估算是否附带重算整张样本表。

    缺省仍返回样本表，供小程序和已有调用方使用。
    网页在固体比冲和密度都没变时传 include_rows=false，只算当前这一发。
    """
    return opt_bool(params.get('include_rows'), True)


def run_estimate_from_params(params: dict[str, Any] | None) -> dict[str, Any]:
    """按表单参数估算一发。固体比冲重算预设表；吸气比冲只作用于当前这一发。"""
    params = params or {}
    try:
        isp = opt_float(params.get('isp_s'), DEFAULT_ISP_S)
        density = opt_float(params.get('propellant_density'), DEFAULT_PROPELLANT_DENSITY)
        ballistic_single_stage = resolve_ballistic_single_stage(params)
        opt_geom_raw = params.get('optimize_geometry', True)
        if isinstance(opt_geom_raw, str):
            optimize_geometry = opt_geom_raw.strip().lower() in {'1', 'true', 'yes', 'on'}
        else:
            optimize_geometry = bool(opt_geom_raw)
        result = estimate_by_class(
            missile_class=str(params.get('missile_class') or 'hgv_biconic'),
            length_m=_required_float(params, 'length_m'),
            diameter_m=_required_float(params, 'diameter_m'),
            warhead_mass_kg=_required_float(params, 'warhead_kg'),
            v_launch_mach=opt_float(params.get('v_launch_mach'), 0.85),
            h_launch_km=opt_float(params.get('h_launch_km'), 13.0),
            isp_s=isp,
            propellant_density=density,
            isp_air_s=opt_optional_float(params.get('isp_air_s')),
            ballistic_single_stage=ballistic_single_stage,
            optimize_geometry=optimize_geometry,
            l_head_m=opt_optional_float(params.get('l_head_m')),
            d_head_m=opt_optional_float(params.get('d_head_m')),
        )
        payload: dict[str, Any] = {'success': True, 'result': result}
        if include_dataset_rows(params):
            payload['rows'] = evaluate_dataset(isp_s=isp, propellant_density=density)
        return payload
    except (TypeError, ValueError) as exc:
        return {'success': False, 'error': str(exc)}


def run_optimize_geometry_from_params(params: dict[str, Any] | None) -> dict[str, Any]:
    """搜索包含战斗部与制控组件的滑翔体最优长度与直径（使总射程最大）。"""
    params = params or {}
    try:
        missile_class = str(params.get('missile_class') or 'hgv_biconic')
        shape = glide_shape(missile_class)
        if shape is None:
            raise ValueError(f'弹种 {missile_class} 不是助推滑翔弹，无法进行滑翔体几何寻优')
        length_m = _required_float(params, 'length_m')
        diameter_m = _required_float(params, 'diameter_m')
        warhead_kg = _required_float(params, 'warhead_kg')
        v_mach = opt_float(params.get('v_launch_mach'), 0.85)
        h_km = opt_float(params.get('h_launch_km'), 13.0)
        isp = opt_float(params.get('isp_s'), DEFAULT_ISP_S)
        density = opt_float(params.get('propellant_density'), DEFAULT_PROPELLANT_DENSITY)
        min_fineness = opt_optional_float(params.get('min_fineness'))
        min_d_head = opt_optional_float(params.get('min_d_head_m'))
        max_d_head = opt_optional_float(params.get('max_d_head_m'))
        opt = optimize_hgv_geometry(
            length_m=length_m,
            diameter_m=diameter_m,
            warhead_mass_kg=warhead_kg,
            hgv_type=shape,
            v_launch_mach=v_mach,
            h_launch_km=h_km,
            isp_s=isp,
            propellant_density=density,
            min_fineness=min_fineness,
            min_d_head_m=min_d_head,
            max_d_head_m=max_d_head,
        )
        return {'success': True, 'optimization': opt, 'result': opt['result']}
    except (TypeError, ValueError) as exc:
        return {'success': False, 'error': str(exc)}


def run_dataset_from_params(params: dict[str, Any] | None) -> dict[str, Any]:
    """只重算预设样本表。"""
    params = params or {}
    try:
        rows = evaluate_dataset(
            isp_s=opt_float(params.get('isp_s'), DEFAULT_ISP_S),
            propellant_density=opt_float(params.get('propellant_density'), DEFAULT_PROPELLANT_DENSITY),
        )
    except (TypeError, ValueError) as exc:
        return {'success': False, 'error': str(exc)}
    return {'success': True, 'rows': rows, 'count': len(all_missile_cases())}


def run_presets_from_params(params: dict[str, Any] | None = None) -> dict[str, Any]:
    """返回目录中的弹种、默认值和默认推进剂下的样本表。"""
    del params
    payload = build_missile_range_catalog_payload()
    return {'success': True, **payload}
