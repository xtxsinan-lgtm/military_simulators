"""外挂位置、中央升力体与机体尺度修正单元测试。"""
from __future__ import annotations

import pytest

from utils.combat_radius.combat_radius_presets import get_preset_by_id, load_presets
from utils.combat_radius.lift_drag import (
    StoreSpec,
    aircraft_from_dict,
    geometric_wetted_area_m2,
    lifting_body_index,
    store_chord_scale,
    store_spec_front_m2,
    store_spec_wetted_m2,
)
from utils.combat_radius.loadout import (
    MOUNT_STYLE_AERO,
    resolve_loadout,
    station_aero_style,
    station_span_frac,
)


def _ac(aircraft_id: str):
    ac = aircraft_from_dict(get_preset_by_id(load_presets(), aircraft_id))
    ac.mach = 0.8
    ac.alt_m = 11000.0
    return ac


def _aam(style: str, span: float = -1.0, count: float = 1.0) -> StoreSpec:
    """中距弹级外挂，气动参数取该挂点类型默认值。"""
    a = MOUNT_STYLE_AERO[style]
    return StoreSpec(
        length_m=3.85, diameter_m=0.203, count=count, mount='pylon',
        pylon_wetted_m2=a['pylon_wetted_m2'], pylon_front_m2=a['pylon_front_m2'],
        exposed_frac=a['exposed_frac'], interf=a['interf'], front_frac=a['front_frac'],
        style=style, span_frac=span,
    )


def test_lifting_body_index_orders_airframes():
    """F-16 类圆截面机身≈0；侧卫/F-15E/F-22 类扁宽升力体接近 1。"""
    assert lifting_body_index(_ac('F-16')) < 0.05
    assert lifting_body_index(_ac('FC-1')) < 0.2
    assert 0.2 < lifting_body_index(_ac('J-10C')) < 0.6
    assert lifting_body_index(_ac('J-15')) > 0.8
    assert lifting_body_index(_ac('F-15E')) > 0.7
    assert lifting_body_index(_ac('F-22')) == pytest.approx(1.0)


def test_belly_store_drag_lower_on_lifting_body():
    """同样机腹中线挂弹：升力体机型浸润/迎风明显小于 F-16 类。"""
    spec = _aam('centerline')
    f16, j15 = _ac('F-16'), _ac('J-15')
    assert store_spec_wetted_m2(spec, j15) < 0.8 * store_spec_wetted_m2(spec)
    assert store_spec_front_m2(spec, j15) < store_spec_front_m2(spec)
    assert store_spec_wetted_m2(spec, f16) >= store_spec_wetted_m2(spec)  # 无升力体不减


def test_belly_shielded_more_than_intake_more_than_wing():
    """遮蔽程度：机腹中线 > 进气道下 > 翼下挂点。"""
    j15 = _ac('J-15')
    base = {s: store_spec_wetted_m2(_aam(s)) for s in ('centerline', 'side_rail', 'wing_pylon')}
    cut = {s: 1 - store_spec_wetted_m2(_aam(s, 0.5), j15) / base[s]
           for s in ('centerline', 'side_rail', 'wing_pylon')}
    assert cut['centerline'] > cut['side_rail'] > cut['wing_pylon']


def test_wing_pylon_inboard_cheaper_than_outboard():
    """翼下挂点：内侧受翼身交汇遮蔽，外翼更暴露。"""
    j15 = _ac('J-15')
    inner = store_spec_wetted_m2(_aam('wing_pylon', 0.0), j15)
    mid = store_spec_wetted_m2(_aam('wing_pylon', 0.5), j15)
    outer = store_spec_wetted_m2(_aam('wing_pylon', 1.0), j15)
    assert inner < mid < outer


def test_chord_scale_shrinks_with_larger_wing():
    """平均弦越长，同样外挂的干扰超额越小；并有上下限。"""
    assert store_chord_scale(_ac('J-15')) < 1.0 < store_chord_scale(_ac('F-16'))
    assert 0.8 <= store_chord_scale(_ac('J-20')) <= 1.2
    assert 0.8 <= store_chord_scale(_ac('FC-1')) <= 1.2


def test_same_store_is_smaller_wetted_fraction_on_bigger_aircraft():
    """同样 2 枚翼下中距弹，占机体浸润面积的比例随机体增大而减小。"""
    spec = _aam('wing_pylon', 0.5, count=2.0)
    ratios = []
    for aid in ('FC-1', 'J-10C', 'Rafale', 'F-15E', 'J-15'):
        ac = _ac(aid)
        ratios.append(store_spec_wetted_m2(spec, ac) / geometric_wetted_area_m2(ac))
    assert ratios == sorted(ratios, reverse=True)
    assert ratios[0] > 2.5 * ratios[-1]


def test_no_aircraft_means_no_position_correction():
    """不传 ac 时保持原几何，便于纯几何单测。"""
    spec = _aam('centerline')
    assert store_spec_wetted_m2(spec) == pytest.approx(store_spec_wetted_m2(spec, None))


def test_unstyled_specs_skip_position_but_keep_size_scale():
    """无 style 的回退件不做位置遮蔽，只受机体尺度影响。"""
    spec = StoreSpec(length_m=3.65, diameter_m=0.178, count=1, mount='pylon')
    j15 = _ac('J-15')
    assert store_spec_front_m2(spec, j15) == pytest.approx(store_spec_front_m2(spec))
    assert store_spec_wetted_m2(spec, j15) < store_spec_wetted_m2(spec)


@pytest.mark.parametrize('label, expected', [
    ('4号右翼根挂点', 0.15),
    ('3号右翼中挂点', 0.5),
    ('2号右翼外挂点', 1.0),
    ('3 左中外挂点', 0.7),
    ('4 左中内挂点', 0.35),
    ('3 左主挂点（STA-3，in/out）', -1.0),
])
def test_station_span_frac_from_label(label, expected):
    """展向位置从挂点名称关键词解析。"""
    assert station_span_frac(label) == pytest.approx(expected)


def test_station_aero_style_reclassifies_belly_wing_pylon():
    """库里标成翼下、名称在机腹/进气道的站位按进气道下处理。"""
    assert station_aero_style('wing_pylon', '机腹右侧挂点（右）') == 'side_rail'
    assert station_aero_style('wing_pylon', '2号右翼外挂点') == 'wing_pylon'
    assert station_aero_style('centerline', '6号机腹中线挂点') == 'centerline'


def test_resolve_loadout_passes_style_and_span():
    """挂载解析后 StoreSpec 带挂点类型与展向位置。"""
    summary = resolve_loadout('J-15', {'2': 'pl8@1', '6': 'pl12@1', '5': 'yj83k@1'})
    by_id = {s.station_id: s for s in summary.store_specs}
    assert by_id['2'].style == 'wing_pylon' and by_id['2'].span_frac == pytest.approx(1.0)
    assert by_id['6'].style == 'centerline' and by_id['6'].span_frac < 0
    assert by_id['5'].style == 'side_rail'
