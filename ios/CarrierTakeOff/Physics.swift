import Foundation

/**
 * 前端气动与滑跃几何预览 — 由 scripts/generate_frontend_physics.py 自动生成。
 * 请勿手改；修改物理请改 Python（utils/）后运行 python3 scripts/build_all.py。
 */
enum Physics {
    static let skiJumpRefRadiusM: Double = 200.0
    static let flapDeflectionDeg: Double = 20.0
    static let flapEfficiency: Double = 0.5
    static let wingIncidenceDeg: Double = 2.0
    static let pilotLoadKg: Double = 100.0
    static let a2aMissileCount: Int = 4
    static let pitchMaxDeg: Double = 20.0

    struct SkiJumpGeom {
        var angleDeg: Double
        var radiusM: Double
        var arcLengthM: Double
        var horizontalM: Double
        var lipHeightM: Double
    }

    struct AeroPreview {
        var aspectRatio: Double
        var oswaldE: Double
        var clAlphaPerRad: Double
        var taxiAlphaDeg: Double
        var clTaxi: Double
        var cl20deg: Double
        var cd0: Double
    }

    static func computeSkiJumpArc(
        angleDeg: Double,
        lipHeightM: Double? = nil,
        arcLengthM: Double? = nil
    ) throws -> SkiJumpGeom {
        guard angleDeg > 0 else {
            throw NSError(
                domain: "Physics",
                code: 1,
                userInfo: [NSLocalizedDescriptionKey: "滑跃角必须为正"]
            )
        }
        let angleRad = angleDeg * .pi / 180
        let r: Double
        let h: Double
        if let arc = arcLengthM, arc > 0 {
            r = arc / angleRad
            h = r * (1 - cos(angleRad))
        } else if let lip = lipHeightM, lip > 0 {
            h = lip
            r = h / (1 - cos(angleRad))
        } else {
            r = skiJumpRefRadiusM
            h = r * (1 - cos(angleRad))
        }
        return SkiJumpGeom(
            angleDeg: angleDeg,
            radiusM: r,
            arcLengthM: r * angleRad,
            horizontalM: r * sin(angleRad),
            lipHeightM: h
        )
    }

    static func resolveCarrierSkiJump(_ carrier: Carrier) -> SkiJumpGeom? {
        guard carrier.ski_jump else { return nil }
        let angle = carrier.ski_jump_angle_deg ?? 0
        if let height = carrier.ski_jump_height_m, height > 0 {
            return try? computeSkiJumpArc(angleDeg: angle, lipHeightM: height, arcLengthM: nil)
        }
        return try? computeSkiJumpArc(angleDeg: angle)
    }

    static func calcOswaldE(aspectRatio: Double, sweepLeDeg: Double) -> Double {
        let sweepRad = sweepLeDeg * .pi / 180
        return 4.61 * (1 - 0.045 * pow(aspectRatio, 0.68)) * pow(cos(sweepRad), 0.15) - 3.1
    }

    static func calcClAlpha(aspectRatio: Double, oswaldE: Double, sweepLeDeg: Double) -> Double {
        let sweepRad = sweepLeDeg * .pi / 180
        let denom =
            2 + sqrt(4 + ((pow(aspectRatio, 2) / pow(oswaldE, 2)) * (1 + pow(tan(sweepRad), 2))))
        return (2 * .pi * aspectRatio) / denom
    }

    static func calcClFromAlphaDeg(alphaDeg: Double, clAlpha: Double) -> Double {
        (alphaDeg * .pi / 180) * clAlpha
    }

    static func taxiAlphaDeg() -> Double {
        flapDeflectionDeg * flapEfficiency + wingIncidenceDeg
    }

    static func computeAircraftAero(_ ac: Aircraft) -> AeroPreview {
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
    }

    static func a2aMassKg(_ ac: Aircraft) -> Double {
        let nPilots = Double(ac.n_pilots ?? 1)
        return ac.empty_kg + ac.internal_fuel_kg + Double(a2aMissileCount) * ac.missile_mass_kg + nPilots * pilotLoadKg
    }

    static func maxPayloadKg(_ ac: Aircraft) -> Double {
        ac.max_payload_kg
    }

    static func filterCarriersForMode(_ mode: String, _ carriers: [Carrier]) -> [Carrier] {
        switch mode {
        case "ski_jump":
            return carriers.filter(\.ski_jump)
        case "short_takeoff", "tiltrotor_short_takeoff":
            return carriers.filter { $0.f35b_capable && !$0.ski_jump }
        case "short_ski_jump":
            return carriers.filter { $0.f35b_capable && $0.ski_jump }
        default:
            return []
        }
    }

    static func filterAircraftForMode(_ mode: String, _ aircraft: [Aircraft]) -> [Aircraft] {
        switch mode {
        case "ski_jump":
            return aircraft.filter { $0.type_label == "conventional" }
        case "short_takeoff", "short_ski_jump":
            return aircraft.filter { $0.type_label == "v/stol" }
        case "tiltrotor_short_takeoff":
            return aircraft.filter { $0.type_label == "tiltrotor" }
        default:
            return []
        }
    }

    static func fmtNum(_ v: Double?, digits: Int = 1) -> String {
        guard let v, !v.isNaN else { return "—" }
        let f = NumberFormatter()
        f.locale = Locale(identifier: "zh_CN")
        f.minimumFractionDigits = digits
        f.maximumFractionDigits = digits
        f.numberStyle = .decimal
        return f.string(from: NSNumber(value: v)) ?? String(format: "%.\(digits)f", v)
    }

    static func fmtInt(_ v: Double?) -> String {
        guard let v else { return "—" }
        let f = NumberFormatter()
        f.locale = Locale(identifier: "zh_CN")
        f.numberStyle = .decimal
        f.maximumFractionDigits = 0
        return f.string(from: NSNumber(value: round(v))) ?? "\(Int(round(v)))"
    }

    static func modeNeedsSkiJump(_ mode: String) -> Bool {
        mode == "ski_jump" || mode == "short_ski_jump"
    }

    static func modeHasTrajectory(_ mode: String) -> Bool {
        mode == "ski_jump" || mode == "short_ski_jump"
    }

    /// 默认甲板风 = 航母最大航速 (kt)
    static func defaultDeckWindKt(_ carrier: Carrier?) -> Double? {
        guard let carrier, let wind = carrier.max_speed_kt else { return nil }
        return wind
    }
}
