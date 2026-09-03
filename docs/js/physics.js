/**
 * 前端气动与滑跃几何预览 — 由 scripts/generate_frontend_physics.py 自动生成。
 * 请勿手改；修改物理请改 Python（utils/）后运行 python3 scripts/build_all.py。
 */
const SKI_JUMP_REF_RADIUS_M = 200.0;
const FLAP_DEFLECTION_DEG = 20.0;
const FLAP_EFFICIENCY = 0.5;
const WING_INCIDENCE_DEG = 2.0;
const PILOT_LOAD_KG = 100.0;
const A2A_MISSILE_COUNT = 4;
const PITCH_MAX_DEG = 20.0;
const CANARD_LIFT_INTERFERENCE = 0.5;
const CANARD_LAYOUT = 'canard';

function computeSkiJumpArc(angleDeg, lipHeightM = null, arcLengthM = null) {
  if (angleDeg <= 0) throw new Error('滑跃角必须为正');
  const angleRad = (angleDeg * Math.PI) / 180;
  let r;
  let h;
  if (arcLengthM != null && arcLengthM > 0) {
    r = arcLengthM / angleRad;
    h = r * (1 - Math.cos(angleRad));
  } else if (lipHeightM != null && lipHeightM > 0) {
    h = lipHeightM;
    r = h / (1 - Math.cos(angleRad));
  } else {
    r = SKI_JUMP_REF_RADIUS_M;
    h = r * (1 - Math.cos(angleRad));
  }
  return {
    angle_deg: angleDeg,
    radius_m: r,
    arc_length_m: r * angleRad,
    horizontal_m: r * Math.sin(angleRad),
    lip_height_m: h,
  };
}

function resolveCarrierSkiJump(carrier) {
  if (!carrier.ski_jump) return null;
  const angle = carrier.ski_jump_angle_deg || 0;
  let height = carrier.ski_jump_height_m;
  if (height == null || height === '') {
    return computeSkiJumpArc(angle);
  }
  height = Number(height);
  if (height > 0) {
    return computeSkiJumpArc(angle, height, null);
  }
  return computeSkiJumpArc(angle);
}

function calcOswaldE(aspectRatio, sweepLeDeg) {
  const sweepRad = (sweepLeDeg * Math.PI) / 180;
  return 4.61 * (1 - 0.045 * aspectRatio ** 0.68) * Math.cos(sweepRad) ** 0.15 - 3.1;
}

function calcClAlpha(aspectRatio, oswaldE, sweepLeDeg) {
  const sweepRad = (sweepLeDeg * Math.PI) / 180;
  const denom =
    2 + Math.sqrt(4 + ((aspectRatio ** 2) / oswaldE ** 2) * (1 + Math.tan(sweepRad) ** 2));
  return (2 * Math.PI * aspectRatio) / denom;
}

function calcClFromAlphaDeg(alphaDeg, clAlpha) {
  return ((alphaDeg * Math.PI) / 180) * clAlpha;
}

function calcCanardLiftFactor(layout, canardAreaM2, wingAreaM2) {
  if (layout !== CANARD_LAYOUT) return 1.0;
  const sc = Number(canardAreaM2);
  const sw = Number(wingAreaM2);
  if (!(sc > 0) || !(sw > 0)) return 1.0;
  const k = Math.min(Math.max(CANARD_LIFT_INTERFERENCE, 0.0), 1.0);
  return 1.0 + k * (sc / sw);
}

function taxiAlphaDeg() {
  return FLAP_DEFLECTION_DEG * FLAP_EFFICIENCY + WING_INCIDENCE_DEG;
}

function computeAircraftAero(ac) {
  const ar = (ac.wingspan_m ** 2) / ac.wing_area_m2;
  const eta = calcOswaldE(ar, ac.sweep_le_deg);
  const factor = calcCanardLiftFactor(ac.layout, ac.canard_htail_area_m2, ac.wing_area_m2);
  const clAlpha = calcClAlpha(ar, eta, ac.sweep_le_deg) * factor;
  const alphaTaxi = taxiAlphaDeg();
  return {
    aspect_ratio: ar,
    oswald_e: eta,
    cl_alpha_per_rad: clAlpha,
    taxi_alpha_deg: alphaTaxi,
    cl_taxi: calcClFromAlphaDeg(alphaTaxi, clAlpha),
    cl_20deg: calcClFromAlphaDeg(PITCH_MAX_DEG, clAlpha),
    cd0: ac.cd0,
  };
}

function a2aMassKg(ac) {
  const nPilots = Number(ac.n_pilots);
  const pilots = Number.isFinite(nPilots) ? nPilots : 1;
  return (
    ac.empty_kg +
    ac.internal_fuel_kg +
    A2A_MISSILE_COUNT * ac.missile_mass_kg +
    pilots * PILOT_LOAD_KG
  );
}

function maxPayloadKg(ac) {
  return Number(ac.max_payload_kg);
}

function filterCarriersForMode(mode, carriers) {
  if (mode === 'ski_jump') return carriers.filter((c) => c.ski_jump);
  if (mode === 'short_takeoff' || mode === 'tiltrotor_short_takeoff') {
    return carriers.filter((c) => c.f35b_capable && !c.ski_jump);
  }
  if (mode === 'short_ski_jump') return carriers.filter((c) => c.f35b_capable && c.ski_jump);
  return [];
}

function filterAircraftForMode(mode, aircraft) {
  if (mode === 'ski_jump') return aircraft.filter((a) => a.type_label === 'conventional');
  if (mode === 'short_takeoff' || mode === 'short_ski_jump') {
    return aircraft.filter((a) => a.type_label === 'v/stol');
  }
  if (mode === 'tiltrotor_short_takeoff') {
    return aircraft.filter((a) => a.type_label === 'tiltrotor');
  }
  return [];
}

function fmtNum(v, digits = 1) {
  if (v == null || v === '' || Number.isNaN(v)) return '—';
  return Number(v).toLocaleString('zh-CN', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function fmtInt(v) {
  if (v == null || v === '') return '—';
  return Math.round(Number(v)).toLocaleString('zh-CN');
}

function modeNeedsSkiJump(mode) {
  return mode === 'ski_jump' || mode === 'short_ski_jump';
}

function modeHasTrajectory(mode) {
  return mode === 'ski_jump' || mode === 'short_ski_jump';
}

/** 默认甲板风 = 航母最大航速 (kt) */
function defaultDeckWindKt(carrier) {
  if (!carrier || carrier.max_speed_kt == null || carrier.max_speed_kt === '') return null;
  return Number(carrier.max_speed_kt);
}

export {
  computeSkiJumpArc,
  resolveCarrierSkiJump,
  calcOswaldE,
  calcClAlpha,
  calcClFromAlphaDeg,
  taxiAlphaDeg,
  calcCanardLiftFactor,
  computeAircraftAero,
  a2aMassKg,
  maxPayloadKg,
  filterCarriersForMode,
  filterAircraftForMode,
  fmtNum,
  fmtInt,
  modeNeedsSkiJump,
  modeHasTrajectory,
  defaultDeckWindKt,
};
