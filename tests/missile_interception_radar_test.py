"""饱和打击雷达估算单元测试。"""
from __future__ import annotations

import math

import pytest

from utils.missile_interception.missile_interception_presets import (
    ASM_PRESETS,
    SAM_PRESETS,
    get_preset_by_id,
)
from utils.missile_interception.missile_interception_radar import (
    H_TARGET,
    TECH_MULT,
    angle_track_time_constant_s,
    binding_limit_label,
    clamp,
    default_interceptor_g,
    default_maneuver_class,
    default_target_g,
    dive_angle_deg,
    dive_entry_horizontal_km,
    endgame_miss_m,
    estimate_engagement_distance,
    estimate_pk,
    _kin,
    guidance_time_constant_s,
    homing_range_factor,
    lethal_radius_m,
    maneuver_pk_factor,
    power_range_km,
    radar_gain_factor,
    radar_horizon_km,
    target_altitude_m,
)


def test_clamp_bounds():
    """clamp 限制上下界。"""
    assert clamp(5, 1, 3) == 3
    assert clamp(-1, 0, 2) == 0
    assert clamp(1.5, 0, 2) == 1.5


def test_radar_horizon_km():
    """视距随高度平方根增长。"""
    h = radar_horizon_km(9000, 10)
    assert h == 4.12 * (math.sqrt(9000) + math.sqrt(10))


def test_tech_mult_values():
    """雷达体制增益倍率：机械扫描 / PESA / AESA / 氮化镓 AESA。"""
    assert TECH_MULT['mechanical'] == 1.0
    assert TECH_MULT['pesa'] == 1.43
    assert TECH_MULT['aesa'] == 2.10
    assert TECH_MULT['gan_aesa'] == 3.74


def test_power_range_km_scales_with_area_and_rcs():
    """探测距离随天线面积与 RCS 按雷达方程比例变化。"""
    base = power_range_km(400, 8, 8, 'aesa', 5, 5)
    bigger = power_range_km(400, 32, 8, 'aesa', 5, 5)
    assert bigger == base * 2
    assert TECH_MULT['aesa'] == 2.10


def test_radar_gain_factor_bounded():
    """增益系数落在 [0.55, 1.25]。"""
    g = radar_gain_factor(10, 'aesa', 10)
    assert 0.55 <= g <= 1.25


def test_estimate_engagement_distance_sam_limited():
    """短程拦截弹时交战距离受射程限制（默认 has_awacs=True 仍成立）。"""
    r = estimate_engagement_distance(
        rcs=0.5, traj='high', awacs_area=8, awacs_type='aesa',
        standoff_km=150, ship_area=12, ship_type='aesa', sam_range_km=40,
    )
    assert r['has_awacs'] is True
    assert r['ship_detect_km'] == r['ship_search']
    assert r['awacs_detect_km'] == r['awacs_total']
    assert r['detect_max_km'] == max(r['awacs_detect_km'], r['ship_detect_km'])
    assert r['engage_dist'] == 40
    assert binding_limit_label(r) == '拦截弹射程'


def test_estimate_engagement_distance_with_awacs_uses_max_then_sam():
    """有预警机时：交战距离 = min(max(预警机总探测, 舰载探测), 拦截弹射程)。"""
    r = estimate_engagement_distance(
        rcs=0.5, traj='high', awacs_area=8, awacs_type='aesa',
        standoff_km=150, ship_area=12, ship_type='aesa', sam_range_km=1000,
    )
    assert r['engage_dist'] == pytest.approx(
        min(max(r['awacs_total'], r['ship_search']), r['sam_range'])
    )


def test_engage_dist_uses_max_of_sensors_awacs_farther():
    """预警机总探测 > 舰载探测且二者均小于射程时：交战距离取预警机一路。"""
    r = estimate_engagement_distance(
        rcs=0.5, traj='high', awacs_area=8, awacs_type='aesa',
        standoff_km=150, ship_area=12, ship_type='aesa', sam_range_km=1000,
    )
    assert r['awacs_total'] > r['ship_search']
    assert r['engage_dist'] == pytest.approx(r['awacs_total'])
    assert binding_limit_label(r) == '预警机雷达探测距离'


def test_engage_dist_uses_max_of_sensors_ship_farther():
    """舰载探测 > 预警机总探测且二者均小于射程时：交战距离取舰载一路（而非二者取小）。"""
    r = estimate_engagement_distance(
        rcs=0.5, traj='high', awacs_area=0.5, awacs_type='mechanical',
        standoff_km=0, ship_area=1000, ship_type='gan_aesa', sam_range_km=5000,
    )
    assert r['ship_search'] > r['awacs_total']
    assert r['engage_dist'] == pytest.approx(r['ship_search'])
    assert binding_limit_label(r) == '舰载雷达探测距离'


def test_target_altitude_m():
    """target_altitude_m 按弹道类型返回高度估计，未知类型回退高空值。"""
    assert target_altitude_m('sea') == H_TARGET['sea'] == 10.0
    assert target_altitude_m('high') == H_TARGET['high'] == 12000.0
    assert target_altitude_m('glide') == H_TARGET['glide'] == 45000.0
    assert target_altitude_m('ballistic') == H_TARGET['ballistic'] == 80000.0
    assert target_altitude_m('unknown_traj') == H_TARGET['high']


def test_estimate_no_awacs_uses_ship_search_and_horizon():
    """无预警机时：交战距离 = min(舰载探测, 拦截弹射程)，且不使用预警机探测。"""
    r = estimate_engagement_distance(
        rcs=0.5, traj='sea', awacs_area=8, awacs_type='aesa',
        standoff_km=150, ship_area=12, ship_type='aesa', sam_range_km=200,
        has_awacs=False,
    )
    assert r['has_awacs'] is False
    assert r['ship_search'] == min(r['ship_power'], r['ship_horizon'])
    assert r['engage_dist'] == min(r['ship_search'], r['sam_range'])
    assert r['awacs_power'] == 0.0
    assert r['awacs_horizon'] == 0.0
    assert r['awacs_detect'] == 0.0
    assert r['awacs_total'] == 0.0
    assert r['awacs_detect_km'] == 0.0
    assert r['detect_max_km'] == r['ship_detect_km'] == r['ship_search']
    assert binding_limit_label(r) != '预警机雷达探测距离'


def test_estimate_no_awacs_sea_shorter_horizon_than_high():
    """同一舰载雷达下，掠海目标的地球曲率视距应短于高空目标。"""
    sea = estimate_engagement_distance(
        rcs=0.5, traj='sea', awacs_area=8, awacs_type='aesa',
        standoff_km=150, ship_area=12, ship_type='aesa', sam_range_km=500,
        has_awacs=False,
    )
    high = estimate_engagement_distance(
        rcs=0.5, traj='high', awacs_area=8, awacs_type='aesa',
        standoff_km=150, ship_area=12, ship_type='aesa', sam_range_km=500,
        has_awacs=False,
    )
    assert sea['ship_horizon'] < high['ship_horizon']


def test_dive_entry_horizontal_km_geometry():
    """俯冲角 + 最大射高几何：45°、35km 射高、45km 巡航 → 10km 水平进入距离。"""
    entry = dive_entry_horizontal_km(45000.0, 35.0, 45.0)
    assert entry == pytest.approx(10.0)
    entry80 = dive_entry_horizontal_km(80000.0, 35.0, 45.0)
    assert entry80 == pytest.approx(45.0)
    assert dive_entry_horizontal_km(30000.0, 35.0, 45.0) is None


def test_dive_angle_from_traj():
    """弹道类型对应默认俯冲角。"""
    assert dive_angle_deg('ballistic') == 45.0
    assert dive_angle_deg('glide') == 25.0


def test_high_traj_skips_dive_geometry_when_within_sam_envelope():
    """常规高空导弹巡航高度已在射高包线内：不计算俯冲进入距离。"""
    r = estimate_engagement_distance(
        rcs=0.5, traj='high', awacs_area=8, awacs_type='aesa',
        standoff_km=150, ship_area=12, ship_type='aesa', sam_range_km=1000,
        sam_max_alt_km=33.0,
    )
    assert r['h_target_m'] == 12000.0
    assert r['h_engage_m'] == 12000.0
    assert r['dive_entry_km'] is None
    assert r['dive_angle_deg'] is None
    assert r['engage_dist'] == pytest.approx(
        min(max(r['awacs_total'], r['ship_search']), r['sam_range'])
    )
    assert binding_limit_label(r) != '俯冲进入射高包线'


def test_sea_traj_skips_dive_geometry():
    """掠海导弹同样在射高包线内，不涉及俯冲几何。"""
    r = estimate_engagement_distance(
        rcs=0.5, traj='sea', awacs_area=8, awacs_type='aesa',
        standoff_km=0, ship_area=12, ship_type='aesa', sam_range_km=500,
        has_awacs=False, sam_max_alt_km=33.0,
    )
    assert r['dive_entry_km'] is None
    assert r['dive_angle_deg'] is None


def test_glide_ballistic_engage_limited_by_dive_entry():
    """滑翔体 / 弹道导弹有效交战距离受俯冲进入射高包线限制。"""
    common = dict(
        rcs=0.5, awacs_area=8, awacs_type='aesa', standoff_km=150,
        ship_area=12, ship_type='aesa', sam_range_km=1000, has_awacs=True,
        sam_max_alt_km=33.0,
    )
    high = estimate_engagement_distance(traj='high', **common)
    glide = estimate_engagement_distance(traj='glide', **common)
    ballistic = estimate_engagement_distance(traj='ballistic', **common)
    assert glide['dive_entry_km'] is not None
    assert ballistic['dive_entry_km'] is not None
    assert ballistic['dive_entry_km'] > glide['dive_entry_km']
    assert glide['engage_dist'] < high['engage_dist']
    assert ballistic['engage_dist'] > glide['engage_dist']
    assert binding_limit_label(ballistic) == '俯冲进入射高包线'
    assert glide['h_engage_m'] == 33000.0
    assert glide['h_target_m'] == 45000.0


def test_maneuver_pk_factor_ordering():
    """机动性修正：滑翔体更难拦截，超燃冲压更易拦截，双锥体介于巡航与滑翔体之间。"""
    cruise = maneuver_pk_factor('cruise')
    scramjet = maneuver_pk_factor('scramjet')
    glide = maneuver_pk_factor('glide')
    dual = maneuver_pk_factor('dual_cone')
    assert glide < dual < cruise < scramjet


def test_default_maneuver_class():
    """型号 / 弹道推断机动性类别。"""
    assert default_maneuver_class('glide') == 'glide'
    assert default_maneuver_class('ballistic') == 'dual_cone'
    assert default_maneuver_class('high', 'yj12') == 'scramjet'
    assert default_maneuver_class('high', 'yj18') == 'cruise'


def test_kin_reads_nav_ratio():
    """运动学配置能读到比例导引导航比。"""
    assert _kin()['nav_ratio'] == pytest.approx(4.0)


def test_default_target_g_by_class_and_speed():
    """未填过载时：亚音速巡航低于超音速，高超声速冲压低于中低马赫冲压，双锥最高。"""
    assert default_target_g('cruise', 0.9) == 5.0
    assert default_target_g('cruise', 3.0) == 8.0
    assert default_target_g('scramjet', 3.0) > default_target_g('scramjet', 8.0)
    assert default_target_g('glide', 8.0) == 8.0
    assert default_target_g('dual_cone', 10.0) == 15.0


def test_default_interceptor_g_smaller_missile_more_agile():
    """未填拦截弹过载时，小弹径按点防御高机动，大弹径更低。"""
    assert default_interceptor_g(0.16) > default_interceptor_g(0.25) > default_interceptor_g(0.5)


def test_homing_range_factor_shrinks_only_above_knee():
    """末制导距离系数在膝点马赫以下为 1，更快则缩短且不低于下限。"""
    assert homing_range_factor(0.9) == 1.0
    assert homing_range_factor(2.5) == 1.0
    fast = homing_range_factor(8.0)
    faster = homing_range_factor(12.0)
    assert 0.35 <= faster <= fast < 1.0


def test_guidance_time_constant_s_tvc_faster_than_aero():
    """高过载时间常数更短；半主动在此基础上更慢。"""
    aero = guidance_time_constant_s(25, 'active_mech')
    tvc = guidance_time_constant_s(60, 'active_mech')
    semi = guidance_time_constant_s(25, 'semi_active')
    assert tvc < aero < semi


def test_angle_track_time_constant_s_not_only_autopilot():
    """航向通道不会因舵回路极快而变成零，仍保留跟踪滤波分量。"""
    assert angle_track_time_constant_s(0.15) > 0.15
    assert angle_track_time_constant_s(0.5) >= 0.5


def test_lethal_radius_m_grows_with_diameter_and_is_bounded():
    """杀伤半径随弹径增大，并落在上下限内。"""
    small = lethal_radius_m(0.12)
    mid = lethal_radius_m(0.34)
    large = lethal_radius_m(0.7)
    assert 8.0 <= small < mid <= large <= 22.0


def test_endgame_miss_m_grows_when_interceptor_g_is_short():
    """拦截弹过载低于需用值时脱靶更大，且分解项齐全。"""
    easy = endgame_miss_m(0.9, 3.5, 4, 50, 'active_mech')
    hard = endgame_miss_m(0.9, 3.5, 20, 15, 'active_mech')
    assert hard['miss_m'] > easy['miss_m']
    assert hard['miss_saturation_m'] > 0
    assert easy['g_required'] == pytest.approx(8.0)
    assert hard['t_go_s'] > 0


def test_estimate_pk_range():
    """Pk 估算落在配置上下限内，并给出脱靶与过载分解。"""
    r = estimate_pk(
        vm_ma=2.6, vi_ma=3.8, rcs=0.5, traj='high',
        ship_area=12, ship_type='aesa', interceptor_dia_m=0.35,
        seeker_type='active_aesa',
    )
    assert 0.03 <= r['pk'] <= 0.95
    assert r['miss_m'] > 0
    assert r['target_g'] > 0 and r['interceptor_g'] > 0
    assert 'ecm_factor' not in r


def test_estimate_pk_higher_target_g_lowers_pk():
    """同一速度下，来袭过载越高越难拦截；拦截弹过载越高越容易。"""
    common = dict(
        vm_ma=3.0, vi_ma=3.5, rcs=0.3, traj='high',
        ship_area=12, ship_type='aesa', interceptor_dia_m=0.34,
        seeker_type='active_mech', interceptor_g=30,
    )
    low = estimate_pk(**common, target_g=4)
    high = estimate_pk(**common, target_g=15)
    assert high['pk'] < low['pk']
    common_ig = {k: v for k, v in common.items() if k != 'interceptor_g'}
    weak = estimate_pk(**common_ig, target_g=12, interceptor_g=18)
    strong = estimate_pk(**common_ig, target_g=12, interceptor_g=60)
    assert weak['pk'] < strong['pk']


def test_estimate_pk_faster_target_lowers_pk_at_same_g():
    """过载相同时空速越高，末制导时间越短，Pk 越低。"""
    slow = estimate_pk(
        0.9, 3.5, 0.3, 'high', 12, 'aesa', 0.34, 'active_mech',
        target_g=8, interceptor_g=30,
    )
    fast = estimate_pk(
        8.0, 3.5, 0.3, 'high', 12, 'aesa', 0.34, 'active_mech',
        target_g=8, interceptor_g=30,
    )
    assert fast['t_go_s'] < slow['t_go_s']
    assert fast['pk'] < slow['pk']


def test_estimate_pk_explicit_g_overrides_class_default():
    """显式过载优先于机动类别默认值。"""
    common = dict(
        vm_ma=3.0, vi_ma=3.5, rcs=0.3, traj='high',
        ship_area=12, ship_type='aesa', interceptor_dia_m=0.34,
        seeker_type='active_mech',
    )
    by_class = estimate_pk(**common, maneuver_class='dual_cone')
    explicit = estimate_pk(**common, maneuver_class='dual_cone', target_g=4)
    assert by_class['target_g'] == 15.0
    assert explicit['target_g'] == 4.0
    assert explicit['pk'] > by_class['pk']


def test_estimate_pk_sea_skimming_harder():
    """掠海弹道 traj_factor 更低；在未顶满上限时 Pk 亦更低。"""
    high = estimate_pk(
        3.0, 3.0, 0.05, 'high', 6, 'mechanical', 0.2, 'active_mech',
        target_g=8, interceptor_g=30,
    )
    sea = estimate_pk(
        3.0, 3.0, 0.05, 'sea', 6, 'mechanical', 0.2, 'active_mech',
        target_g=8, interceptor_g=30,
    )
    assert sea['traj_factor'] < high['traj_factor']
    assert sea['pk'] < high['pk']


def test_estimate_pk_glide_and_ballistic_harder_than_high():
    """滑翔体 / 弹道导弹比常规高空更难：弹道系数更低，且弹道默认过载更高、更快。"""
    high = estimate_pk(8.0, 4.0, 0.1, 'high', 12, 'aesa', 0.35, 'active_aesa')
    glide = estimate_pk(8.0, 4.0, 0.1, 'glide', 12, 'aesa', 0.35, 'active_aesa')
    ballistic = estimate_pk(10.0, 4.0, 0.1, 'ballistic', 12, 'aesa', 0.35, 'active_aesa')
    assert glide['traj_factor'] < high['traj_factor']
    assert ballistic['traj_factor'] < glide['traj_factor']
    assert ballistic['target_g'] > glide['target_g']
    assert ballistic['pk'] <= glide['pk'] <= high['pk']


def _preset_pk(asm_id: str, sam_id: str) -> dict:
    """用导弹库速度与过载估算一对单发 Pk（舰载雷达取中等 AESA）。"""
    asm = get_preset_by_id(ASM_PRESETS, asm_id)
    sam = get_preset_by_id(SAM_PRESETS, sam_id)
    assert asm is not None and sam is not None
    return estimate_pk(
        vm_ma=asm['vm'],
        vi_ma=sam['vi'],
        rcs=asm['rcs'],
        traj=asm['traj'],
        ship_area=12,
        ship_type='aesa',
        interceptor_dia_m=sam['dia'],
        seeker_type=sam['guidance'],
        maneuver_class=asm.get('maneuver_class'),
        asm_id=asm_id,
        target_g=asm['max_g'],
        interceptor_g=sam['max_g'],
    )


def test_preset_pk_ordering_is_plausible():
    """典型弹对的单发 Pk 应落在可解释的区间：亚音速易拦截，高超声速末制导很难。"""
    harpoon_sm6 = _preset_pk('harpoon', 'sm6')['pk']
    harpoon_aster = _preset_pk('harpoon', 'aster30')['pk']
    brahmos_essm = _preset_pk('brahmos', 'essm')['pk']
    brahmos_sm6 = _preset_pk('brahmos', 'sm6')['pk']
    brahmos_sm2 = _preset_pk('brahmos', 'sm2')['pk']
    zircon_sm6 = _preset_pk('zircon', 'sm6')['pk']
    zircon_hq10 = _preset_pk('zircon', 'hq10')['pk']
    yj21_sm6 = _preset_pk('yj21', 'sm6')['pk']
    yj21_aster = _preset_pk('yj21', 'aster30')['pk']
    yj17_sm6 = _preset_pk('yj17', 'sm6')['pk']

    assert 0.65 <= harpoon_sm6 <= 0.90
    assert harpoon_aster >= harpoon_sm6 - 0.05
    assert brahmos_essm > brahmos_sm6 > brahmos_sm2
    assert 0.45 <= brahmos_sm6 <= 0.70
    assert zircon_sm6 < harpoon_sm6
    assert 0.25 <= zircon_sm6 <= 0.60
    assert zircon_hq10 < zircon_sm6
    assert yj21_sm6 < zircon_sm6
    assert yj21_sm6 < 0.20
    assert yj21_aster >= yj21_sm6
    assert yj17_sm6 < harpoon_sm6
    for value in (
        harpoon_sm6, brahmos_essm, brahmos_sm2, zircon_sm6, zircon_hq10, yj21_sm6, yj17_sm6,
    ):
        assert 0.03 <= value <= 0.95
