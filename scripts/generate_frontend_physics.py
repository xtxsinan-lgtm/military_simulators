#!/usr/bin/env python3
"""从 Python 物理常量生成前端 physics.js（Web ESM + 小程序 CommonJS）与 iOS Physics.swift。

算法与 utils/takeoff/takeoff_physics.py、utils/takeoff/ski_jump_geometry.py、utils/specs.py 对齐；
常量在生成时注入。请勿手改 docs/js/physics.js、miniprogram/utils/physics.js 或
ios/CarrierTakeOff/Physics.swift。
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS_PHYSICS = ROOT / 'docs' / 'js' / 'physics.js'
MINI_PHYSICS = ROOT / 'miniprogram' / 'utils' / 'physics.js'
IOS_PHYSICS = ROOT / 'ios' / 'CarrierTakeOff' / 'Physics.swift'

# 导出符号列表（ESM / CJS 共用）
_EXPORT_NAMES = (
    'computeSkiJumpArc',
    'resolveCarrierSkiJump',
    'calcOswaldE',
    'calcClAlpha',
    'calcClFromAlphaDeg',
    'taxiAlphaDeg',
    'computeAircraftAero',
    'a2aMassKg',
    'maxPayloadKg',
    'filterCarriersForMode',
    'filterAircraftForMode',
    'fmtNum',
    'fmtInt',
    'modeNeedsSkiJump',
    'modeHasTrajectory',
    'defaultDeckWindKt',
)


def _load_constants() -> dict:
    """从 data/takeoff_config.json 读取前端预览所需常量。"""
    from utils.takeoff.takeoff_config import physics_config
    phys = physics_config()
    return {
        'SKI_JUMP_REF_RADIUS_M': float(phys['ski_jump_ref_radius_m']),
        'FLAP_DEFLECTION_DEG': float(phys['flap_deflection_deg']),
        'FLAP_EFFICIENCY': float(phys['flap_efficiency']),
        'WING_INCIDENCE_DEG': float(phys['wing_incidence_deg']),
        'PILOT_LOAD_KG': float(phys['pilot_load_kg']),
        'A2A_MISSILE_COUNT': int(phys['a2a_missile_count']),
        'PITCH_MAX_DEG': float(phys['pitch_max_deg']),
    }


def render_physics_body(constants: dict | None = None) -> str:
    """生成 physics 函数体（无 export / module.exports）。"""
    c = constants or _load_constants()
    return f'''/**
 * 前端气动与滑跃几何预览 — 由 scripts/generate_frontend_physics.py 自动生成。
 * 请勿手改；修改物理请改 Python（utils/）后运行 python3 scripts/build_all.py。
 */
const SKI_JUMP_REF_RADIUS_M = {c['SKI_JUMP_REF_RADIUS_M']};
const FLAP_DEFLECTION_DEG = {c['FLAP_DEFLECTION_DEG']};
const FLAP_EFFICIENCY = {c['FLAP_EFFICIENCY']};
const WING_INCIDENCE_DEG = {c['WING_INCIDENCE_DEG']};
const PILOT_LOAD_KG = {c['PILOT_LOAD_KG']};
const A2A_MISSILE_COUNT = {c['A2A_MISSILE_COUNT']};
const PITCH_MAX_DEG = {c['PITCH_MAX_DEG']};

function computeSkiJumpArc(angleDeg, lipHeightM = null, arcLengthM = null) {{
  if (angleDeg <= 0) throw new Error('滑跃角必须为正');
  const angleRad = (angleDeg * Math.PI) / 180;
  let r;
  let h;
  if (arcLengthM != null && arcLengthM > 0) {{
    r = arcLengthM / angleRad;
    h = r * (1 - Math.cos(angleRad));
  }} else if (lipHeightM != null && lipHeightM > 0) {{
    h = lipHeightM;
    r = h / (1 - Math.cos(angleRad));
  }} else {{
    r = SKI_JUMP_REF_RADIUS_M;
    h = r * (1 - Math.cos(angleRad));
  }}
  return {{
    angle_deg: angleDeg,
    radius_m: r,
    arc_length_m: r * angleRad,
    horizontal_m: r * Math.sin(angleRad),
    lip_height_m: h,
  }};
}}

function resolveCarrierSkiJump(carrier) {{
  if (!carrier.ski_jump) return null;
  const angle = carrier.ski_jump_angle_deg || 0;
  let height = carrier.ski_jump_height_m;
  if (height == null || height === '') {{
    return computeSkiJumpArc(angle);
  }}
  height = Number(height);
  if (height > 0) {{
    return computeSkiJumpArc(angle, height, null);
  }}
  return computeSkiJumpArc(angle);
}}

function calcOswaldE(aspectRatio, sweepLeDeg) {{
  const sweepRad = (sweepLeDeg * Math.PI) / 180;
  return 4.61 * (1 - 0.045 * aspectRatio ** 0.68) * Math.cos(sweepRad) ** 0.15 - 3.1;
}}

function calcClAlpha(aspectRatio, oswaldE, sweepLeDeg) {{
  const sweepRad = (sweepLeDeg * Math.PI) / 180;
  const denom =
    2 + Math.sqrt(4 + ((aspectRatio ** 2) / oswaldE ** 2) * (1 + Math.tan(sweepRad) ** 2));
  return (2 * Math.PI * aspectRatio) / denom;
}}

function calcClFromAlphaDeg(alphaDeg, clAlpha) {{
  return ((alphaDeg * Math.PI) / 180) * clAlpha;
}}

function taxiAlphaDeg() {{
  return FLAP_DEFLECTION_DEG * FLAP_EFFICIENCY + WING_INCIDENCE_DEG;
}}

function computeAircraftAero(ac) {{
  const ar = (ac.wingspan_m ** 2) / ac.wing_area_m2;
  const eta = calcOswaldE(ar, ac.sweep_le_deg);
  const clAlpha = calcClAlpha(ar, eta, ac.sweep_le_deg);
  const alphaTaxi = taxiAlphaDeg();
  return {{
    aspect_ratio: ar,
    oswald_e: eta,
    cl_alpha_per_rad: clAlpha,
    taxi_alpha_deg: alphaTaxi,
    cl_taxi: calcClFromAlphaDeg(alphaTaxi, clAlpha),
    cl_20deg: calcClFromAlphaDeg(PITCH_MAX_DEG, clAlpha),
    cd0: ac.cd0,
  }};
}}

function a2aMassKg(ac) {{
  const nPilots = Number(ac.n_pilots);
  const pilots = Number.isFinite(nPilots) ? nPilots : 1;
  return (
    ac.empty_kg +
    ac.internal_fuel_kg +
    A2A_MISSILE_COUNT * ac.missile_mass_kg +
    pilots * PILOT_LOAD_KG
  );
}}

function maxPayloadKg(ac) {{
  return Number(ac.max_payload_kg);
}}

function filterCarriersForMode(mode, carriers) {{
  if (mode === 'ski_jump') return carriers.filter((c) => c.ski_jump);
  if (mode === 'short_takeoff' || mode === 'tiltrotor_short_takeoff') {{
    return carriers.filter((c) => c.f35b_capable && !c.ski_jump);
  }}
  if (mode === 'short_ski_jump') return carriers.filter((c) => c.f35b_capable && c.ski_jump);
  return [];
}}

function filterAircraftForMode(mode, aircraft) {{
  if (mode === 'ski_jump') return aircraft.filter((a) => a.type_label === 'conventional');
  if (mode === 'short_takeoff' || mode === 'short_ski_jump') {{
    return aircraft.filter((a) => a.type_label === 'v/stol');
  }}
  if (mode === 'tiltrotor_short_takeoff') {{
    return aircraft.filter((a) => a.type_label === 'tiltrotor');
  }}
  return [];
}}

function fmtNum(v, digits = 1) {{
  if (v == null || v === '' || Number.isNaN(v)) return '—';
  return Number(v).toLocaleString('zh-CN', {{
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }});
}}

function fmtInt(v) {{
  if (v == null || v === '') return '—';
  return Math.round(Number(v)).toLocaleString('zh-CN');
}}

function modeNeedsSkiJump(mode) {{
  return mode === 'ski_jump' || mode === 'short_ski_jump';
}}

function modeHasTrajectory(mode) {{
  return mode === 'ski_jump' || mode === 'short_ski_jump';
}}

/** 默认甲板风 = 航母最大航速 (kt) */
function defaultDeckWindKt(carrier) {{
  if (!carrier || carrier.max_speed_kt == null || carrier.max_speed_kt === '') return null;
  return Number(carrier.max_speed_kt);
}}
'''


def render_esm(constants: dict | None = None) -> str:
    """生成 Web 用 ESM physics.js 全文。"""
    body = render_physics_body(constants)
    names = ',\n  '.join(_EXPORT_NAMES)
    return body + f'\nexport {{\n  {names},\n}};\n'


def render_cjs(constants: dict | None = None) -> str:
    """生成小程序用 CommonJS physics.js 全文。"""
    body = render_physics_body(constants)
    lines = ',\n  '.join(_EXPORT_NAMES)
    return body + f'\nmodule.exports = {{\n  {lines},\n}};\n'


def render_swift(constants: dict | None = None) -> str:
    """生成 iOS SwiftUI 用 Physics.swift（常量来自 Python，算法与 JS 同源）。"""
    c = constants or _load_constants()
    return f'''import Foundation

/**
 * 前端气动与滑跃几何预览 — 由 scripts/generate_frontend_physics.py 自动生成。
 * 请勿手改；修改物理请改 Python（utils/）后运行 python3 scripts/build_all.py。
 */
enum Physics {{
    static let skiJumpRefRadiusM: Double = {c['SKI_JUMP_REF_RADIUS_M']}
    static let flapDeflectionDeg: Double = {c['FLAP_DEFLECTION_DEG']}
    static let flapEfficiency: Double = {c['FLAP_EFFICIENCY']}
    static let wingIncidenceDeg: Double = {c['WING_INCIDENCE_DEG']}
    static let pilotLoadKg: Double = {c['PILOT_LOAD_KG']}
    static let a2aMissileCount: Int = {c['A2A_MISSILE_COUNT']}
    static let pitchMaxDeg: Double = {c['PITCH_MAX_DEG']}

    struct SkiJumpGeom {{
        var angleDeg: Double
        var radiusM: Double
        var arcLengthM: Double
        var horizontalM: Double
        var lipHeightM: Double
    }}

    struct AeroPreview {{
        var aspectRatio: Double
        var oswaldE: Double
        var clAlphaPerRad: Double
        var taxiAlphaDeg: Double
        var clTaxi: Double
        var cl20deg: Double
        var cd0: Double
    }}

    static func computeSkiJumpArc(
        angleDeg: Double,
        lipHeightM: Double? = nil,
        arcLengthM: Double? = nil
    ) throws -> SkiJumpGeom {{
        guard angleDeg > 0 else {{
            throw NSError(
                domain: "Physics",
                code: 1,
                userInfo: [NSLocalizedDescriptionKey: "滑跃角必须为正"]
            )
        }}
        let angleRad = angleDeg * .pi / 180
        let r: Double
        let h: Double
        if let arc = arcLengthM, arc > 0 {{
            r = arc / angleRad
            h = r * (1 - cos(angleRad))
        }} else if let lip = lipHeightM, lip > 0 {{
            h = lip
            r = h / (1 - cos(angleRad))
        }} else {{
            r = skiJumpRefRadiusM
            h = r * (1 - cos(angleRad))
        }}
        return SkiJumpGeom(
            angleDeg: angleDeg,
            radiusM: r,
            arcLengthM: r * angleRad,
            horizontalM: r * sin(angleRad),
            lipHeightM: h
        )
    }}

    static func resolveCarrierSkiJump(_ carrier: Carrier) -> SkiJumpGeom? {{
        guard carrier.ski_jump else {{ return nil }}
        let angle = carrier.ski_jump_angle_deg ?? 0
        if let height = carrier.ski_jump_height_m, height > 0 {{
            return try? computeSkiJumpArc(angleDeg: angle, lipHeightM: height, arcLengthM: nil)
        }}
        return try? computeSkiJumpArc(angleDeg: angle)
    }}

    static func calcOswaldE(aspectRatio: Double, sweepLeDeg: Double) -> Double {{
        let sweepRad = sweepLeDeg * .pi / 180
        return 4.61 * (1 - 0.045 * pow(aspectRatio, 0.68)) * pow(cos(sweepRad), 0.15) - 3.1
    }}

    static func calcClAlpha(aspectRatio: Double, oswaldE: Double, sweepLeDeg: Double) -> Double {{
        let sweepRad = sweepLeDeg * .pi / 180
        let denom =
            2 + sqrt(4 + ((pow(aspectRatio, 2) / pow(oswaldE, 2)) * (1 + pow(tan(sweepRad), 2))))
        return (2 * .pi * aspectRatio) / denom
    }}

    static func calcClFromAlphaDeg(alphaDeg: Double, clAlpha: Double) -> Double {{
        (alphaDeg * .pi / 180) * clAlpha
    }}

    static func taxiAlphaDeg() -> Double {{
        flapDeflectionDeg * flapEfficiency + wingIncidenceDeg
    }}

    static func computeAircraftAero(_ ac: Aircraft) -> AeroPreview {{
        let ar = pow(ac.wingspan_m, 2) / ac.wing_area_m2
        let eta = calcOswaldE(aspectRatio: ar, sweepLeDeg: ac.sweep_le_deg)
        let clAlpha = calcClAlpha(aspectRatio: ar, oswaldE: eta, sweepLeDeg: ac.sweep_le_deg)
        let alphaTaxi = taxiAlphaDeg()
        return AeroPreview(
            aspectRatio: ar,
            oswaldE: eta,
            clAlphaPerRad: clAlpha,
            taxiAlphaDeg: alphaTaxi,
            clTaxi: calcClFromAlphaDeg(alphaDeg: alphaTaxi, clAlpha: clAlpha),
            cl20deg: calcClFromAlphaDeg(alphaDeg: pitchMaxDeg, clAlpha: clAlpha),
            cd0: ac.cd0
        )
    }}

    static func a2aMassKg(_ ac: Aircraft) -> Double {{
        let nPilots = Double(ac.n_pilots ?? 1)
        return ac.empty_kg + ac.internal_fuel_kg + Double(a2aMissileCount) * ac.missile_mass_kg + nPilots * pilotLoadKg
    }}

    static func maxPayloadKg(_ ac: Aircraft) -> Double {{
        ac.max_payload_kg
    }}

    static func filterCarriersForMode(_ mode: String, _ carriers: [Carrier]) -> [Carrier] {{
        switch mode {{
        case "ski_jump":
            return carriers.filter(\\.ski_jump)
        case "short_takeoff", "tiltrotor_short_takeoff":
            return carriers.filter {{ $0.f35b_capable && !$0.ski_jump }}
        case "short_ski_jump":
            return carriers.filter {{ $0.f35b_capable && $0.ski_jump }}
        default:
            return []
        }}
    }}

    static func filterAircraftForMode(_ mode: String, _ aircraft: [Aircraft]) -> [Aircraft] {{
        switch mode {{
        case "ski_jump":
            return aircraft.filter {{ $0.type_label == "conventional" }}
        case "short_takeoff", "short_ski_jump":
            return aircraft.filter {{ $0.type_label == "v/stol" }}
        case "tiltrotor_short_takeoff":
            return aircraft.filter {{ $0.type_label == "tiltrotor" }}
        default:
            return []
        }}
    }}

    static func fmtNum(_ v: Double?, digits: Int = 1) -> String {{
        guard let v, !v.isNaN else {{ return "—" }}
        let f = NumberFormatter()
        f.locale = Locale(identifier: "zh_CN")
        f.minimumFractionDigits = digits
        f.maximumFractionDigits = digits
        f.numberStyle = .decimal
        return f.string(from: NSNumber(value: v)) ?? String(format: "%.\\(digits)f", v)
    }}

    static func fmtInt(_ v: Double?) -> String {{
        guard let v else {{ return "—" }}
        let f = NumberFormatter()
        f.locale = Locale(identifier: "zh_CN")
        f.numberStyle = .decimal
        f.maximumFractionDigits = 0
        return f.string(from: NSNumber(value: round(v))) ?? "\\(Int(round(v)))"
    }}

    static func modeNeedsSkiJump(_ mode: String) -> Bool {{
        mode == "ski_jump" || mode == "short_ski_jump"
    }}

    static func modeHasTrajectory(_ mode: String) -> Bool {{
        mode == "ski_jump" || mode == "short_ski_jump"
    }}

    /// 默认甲板风 = 航母最大航速 (kt)
    static func defaultDeckWindKt(_ carrier: Carrier?) -> Double? {{
        guard let carrier, let wind = carrier.max_speed_kt else {{ return nil }}
        return wind
    }}
}}
'''


def write_physics_files(constants: dict | None = None) -> tuple[Path, Path, Path]:
    """写入 docs / 小程序 physics.js 与 iOS Physics.swift。"""
    c = constants or _load_constants()
    DOCS_PHYSICS.parent.mkdir(parents=True, exist_ok=True)
    MINI_PHYSICS.parent.mkdir(parents=True, exist_ok=True)
    IOS_PHYSICS.parent.mkdir(parents=True, exist_ok=True)
    DOCS_PHYSICS.write_text(render_esm(c), encoding='utf-8')
    MINI_PHYSICS.write_text(render_cjs(c), encoding='utf-8')
    IOS_PHYSICS.write_text(render_swift(c), encoding='utf-8')
    return DOCS_PHYSICS, MINI_PHYSICS, IOS_PHYSICS


def main() -> None:
    docs_path, mini_path, ios_path = write_physics_files()
    print(f'Wrote {docs_path}')
    print(f'Wrote {mini_path}')
    print(f'Wrote {ios_path}')


if __name__ == '__main__':
    main()
