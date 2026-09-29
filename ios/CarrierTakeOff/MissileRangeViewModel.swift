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
    @Published var hgvType = "biconic"
    @Published var vMach = "0.85"
    @Published var hKm = "13"
    @Published var ispS = "264"
    @Published var density = "1760"
    @Published var activeId: Int?
    @Published var result: MissileRangeEstimate?
    @Published var statusText = "加载中…"
    @Published var running = false

    let typeIds = ["biconic", "waverider"]
    let typeLabels = ["双锥体", "乘波体"]

    var typeIndex: Int {
        typeIds.firstIndex(of: hgvType) ?? 0
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
            if let defaults = catalog.missile_range?.defaults {
                if let isp = defaults.isp_s { ispS = text(isp) }
                if let rho = defaults.propellant_density { density = text(rho) }
            }
            applyCase(loaded[0])
        } catch {
            statusText = error.localizedDescription
        }
    }

    func applyCase(_ row: MissileRangeCase) {
        selectedId = row.id
        lengthM = text(row.length_m)
        diameterM = text(row.diameter_m)
        warheadKg = text(row.warhead_kg)
        hgvType = row.hgv_type
        vMach = text(row.v_mach)
        hKm = text(row.h_km)
        activeId = row.id
        result = MissileRangeEstimate(
            m_0_t: row.m_0_t,
            l_head_m: row.l_head_m,
            l_booster_m: row.l_booster_m,
            m_p_total_kg: row.m_p_total_kg,
            v_burnout_mach: row.v_burnout_mach,
            ld_ratio: row.ld_ratio,
            range_km: row.range_km
        )
        statusText = "PRESET"
    }

    func setTypeIndex(_ index: Int) {
        guard typeIds.indices.contains(index) else { return }
        hgvType = typeIds[index]
    }

    func estimate() async {
        if running { return }
        running = true
        statusText = "RUNNING"
        let payload: [String: Any] = [
            "action": "estimate",
            "params": [
                "length_m": number(lengthM, 0),
                "diameter_m": number(diameterM, 0),
                "warhead_kg": number(warheadKg, 0),
                "hgv_type": hgvType,
                "v_launch_mach": number(vMach, 0.85),
                "h_launch_km": number(hKm, 13),
                "isp_s": number(ispS, 264),
                "propellant_density": number(density, 1760),
            ],
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
                statusText = "DONE"
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
