import Foundation

/// 导弹射程：从目录加载预设，改参数后走本地 Pyodide 重算
@MainActor
final class MissileRangeViewModel: ObservableObject {
    @Published var cases: [MissileRangeCase] = []
    @Published var rows: [MissileRangeCase] = []
    @Published var selectedId: Int = 1
    @Published var lengthM = "10.5"
    @Published var diameterM = "1"
    @Published var warheadKg = "200"
    @Published var missileClass = "hgv_biconic"
    @Published var classOptions: [MissileClassInfo] = []
    @Published var classBlurb = "选择弹种后估算射程。固体比冲用于火箭级，吸气巡航用更高的比冲。"
    @Published var vMach = "0.85"
    @Published var hKm = "13"
    @Published var ispS = "264"
    @Published var ispAir = ""
    @Published var showAirIsp = false
    @Published var ballisticTwoStage = true
    @Published var optimizeGeometry = true
    @Published var density = "1760"
    @Published var activeId: Int?
    @Published var result: MissileRangeEstimate?
    @Published var statusText = "加载中…"
    @Published var running = false
    @Published var failOnly = false

    var displayedRows: [MissileRangeCase] {
        failOnly ? rows.filter { $0.reached_takeover == false } : rows
    }

    var failCount: Int {
        rows.filter { $0.reached_takeover == false }.count
    }

    var okCount: Int {
        rows.filter { $0.reached_takeover == true }.count
    }

    func load() {
        do {
            let catalog = try CatalogStore.loadBundledCatalog()
            let loaded = catalog.missile_range?.cases ?? []
            guard !loaded.isEmpty else {
                statusText = "data.json 缺少 missile_range，请运行 build_all.py"
                return
            }
            cases = loaded
            rows = loaded
            classOptions = catalog.missile_range?.classes ?? []
            if let defaults = catalog.missile_range?.defaults {
                if let isp = defaults.isp_s { ispS = text(isp) }
                if let rho = defaults.propellant_density { density = text(rho) }
                if let twoStage = defaults.ballistic_two_stage { ballisticTwoStage = twoStage }
            }
            applyCase(loaded[0])
        } catch {
            statusText = error.localizedDescription
        }
    }

    func applyCase(_ row: MissileRangeCase) {
        selectedId = row.id
        missileClass = row.missile_class ?? "hgv_biconic"
        lengthM = text(row.length_m)
        diameterM = text(row.diameter_m)
        warheadKg = text(row.warhead_kg)
        vMach = text(row.v_mach)
        hKm = text(row.h_km)
        ballisticTwoStage = row.missile_class == "ballistic"
        activeId = row.id
        if let info = classOptions.first(where: { $0.id == missileClass }) {
            classBlurb = info.blurb ?? classBlurb
            if let cruise = info.isp_cruise_s {
                ispAir = text(cruise)
                showAirIsp = true
            } else {
                showAirIsp = false
            }
        }
        result = MissileRangeEstimate(
            missile_class: row.missile_class,
            class_label: row.class_label,
            m_0_t: row.m_0_t,
            l_head_m: row.l_head_m,
            d_head_m: row.d_head_m,
            fineness: row.fineness,
            range_gain_km: row.range_gain_km,
            l_booster_m: row.l_booster_m,
            m_p_total_kg: row.m_p_total_kg,
            v_burnout_mach: row.v_burnout_mach,
            ld_ratio: row.ld_ratio,
            range_km: row.range_km,
            range_high_km: row.range_high_km,
            range_sea_km: row.range_sea_km,
            range_mixed_km: row.range_mixed_km,
            range_terminal_km: row.range_terminal_km,
            note: row.note,
            isp_boost_s: row.isp_boost_s,
            isp_cruise_s: row.isp_cruise_s,
            isp_rocket_s: row.isp_rocket_s,
            reached_takeover: row.reached_takeover,
            mach_takeover: row.mach_takeover,
            mach_boost: row.mach_boost,
            m_booster_kg: row.m_booster_kg,
            m_fuel_kg: row.m_fuel_kg,
            takeover_progress: row.takeover_progress
        )
        statusText = row.reached_takeover == false ? "⚠️ 未达工作速度" : "PRESET"
    }

    func setFailOnly(_ on: Bool) {
        failOnly = on
        if on, result?.reached_takeover != false, let first = displayedRows.first {
            applyCase(first)
        }
    }

    func setClass(_ id: String) {
        missileClass = id
        if let info = classOptions.first(where: { $0.id == id }) {
            classBlurb = info.blurb ?? classBlurb
            if let cruise = info.isp_cruise_s {
                ispAir = text(cruise)
                showAirIsp = true
            } else {
                showAirIsp = false
            }
        }
        ballisticTwoStage = id == "ballistic"
    }

    func estimate() async {
        if running { return }
        running = true
        statusText = "RUNNING"
        var params: [String: Any] = [
            "length_m": number(lengthM, 0),
            "diameter_m": number(diameterM, 0),
            "warhead_kg": number(warheadKg, 0),
            "missile_class": missileClass,
            "v_launch_mach": number(vMach, 0.85),
            "h_launch_km": number(hKm, 13),
            "isp_s": number(ispS, 264),
            "propellant_density": number(density, 1760),
            "ballistic_two_stage": ballisticTwoStage,
            "optimize_geometry": optimizeGeometry,
        ]
        if showAirIsp {
            params["isp_air_s"] = number(ispAir, 0)
        }
        let payload: [String: Any] = [
            "action": "estimate",
            "params": params,
        ]
        do {
            let res = try await LocalSimulatorEngine.shared.runMissileRange(payload: payload)
            if !res.success {
                statusText = res.error ?? "估算失败"
            } else {
                result = res.result
                if let next = res.rows, !next.isEmpty {
                    rows = next
                }
                activeId = nil
                statusText = res.result?.reached_takeover == false ? "⚠️ 未达工作速度" : "DONE"
            }
        } catch {
            statusText = error.localizedDescription
        }
        running = false
    }

    private func number(_ raw: String, _ fallback: Double) -> Double {
        Double(raw) ?? fallback
    }

    private func text(_ value: Double) -> String {
        String(value)
    }
}
