import Foundation
import Combine

/// 作战半径单机输入（几何 + 巡航状态）
struct CombatRadiusAircraftInput {
    var name = ""
    var ar = ""
    var sweepDeg = ""
    var wingLoading = ""
    var tc = ""
    var mach = ""
    var altM = ""
    var planform = "trapezoidal"
    var layout = "conventional"
    var bwb = false
    var rough = false

    /// 填入预设几何
    mutating func apply(_ p: CombatRadiusPresetItem) {
        name = p.name
        ar = String(p.AR)
        sweepDeg = String(p.sweep_deg)
        wingLoading = String(p.wing_loading)
        tc = String(p.tc)
        mach = String(p.mach)
        altM = String(format: "%.0f", p.alt_m)
        planform = p.planform
        layout = p.layout
        bwb = p.bwb
        rough = p.rough
    }

    /// 转为 Python API 机型字典
    func asParams() -> [String: Any] {
        [
            "name": name.isEmpty ? "未命名" : name,
            "AR": Double(ar) ?? 0,
            "sweep_deg": Double(sweepDeg) ?? 0,
            "wing_loading": Double(wingLoading) ?? 0,
            "tc": Double(tc) ?? 0,
            "mach": Double(mach) ?? 0.8,
            "alt_m": Double(altM) ?? 12000,
            "planform": planform,
            "layout": layout,
            "bwb": bwb,
            "rough": rough,
        ]
    }
}

/// 作战半径估算状态（升阻比 + 军推）
@MainActor
final class CombatRadiusViewModel: ObservableObject {
    @Published var statusText = "加载预设…"
    @Published var running = false
    @Published var a1 = CombatRadiusAircraftInput()
    @Published var a2 = CombatRadiusAircraftInput()
    @Published var tgt = CombatRadiusAircraftInput()
    @Published var a1Ld = "8.8"
    @Published var a2Ld = "8.0"
    @Published var presets: [CombatRadiusPresetItem] = []
    @Published var selectedA1Id = ""
    @Published var selectedA2Id = ""
    @Published var selectedTgtId = ""
    @Published var planformOptions: [(String, String)] = [("trapezoidal", "梯形翼")]
    @Published var layoutOptions: [(String, String)] = [("conventional", "常规")]
    @Published var result: CombatRadiusResult?
    @Published var enginePresets: [CombatRadiusEnginePresetItem] = []
    @Published var selectedEngineId = ""
    @Published var engBpr = ""
    @Published var engOpr = ""
    @Published var engT4 = ""
    @Published var engTsl = ""
    @Published var engAlt = "11000"
    @Published var engMach = "1.5"
    @Published var engEta = "0.87"
    @Published var engFanPr = ""
    @Published var thrustResult: CombatRadiusResult?

    init() {
        loadPresets()
    }

    /// 从 Bundle catalog 读取预设与默认锚点
    func loadPresets() {
        do {
            let catalog = try CatalogStore.loadBundledCatalog()
            presets = catalog.combat_radius_presets ?? []
            enginePresets = catalog.combat_radius_engine_presets ?? []
            if let labels = catalog.combat_radius_config?.planform_labels, !labels.isEmpty {
                let order = ["trapezoidal", "swept", "delta", "diamond", "unswept"]
                planformOptions = orderedPairs(labels, preferred: order)
            }
            if let labels = catalog.combat_radius_config?.layout_labels, !labels.isEmpty {
                let order = ["conventional", "canard", "tailless"]
                layoutOptions = orderedPairs(labels, preferred: order)
            }
            let ui = catalog.combat_radius_config?.ui
            applyDefault(id: ui?.default_anchor1_id, slot: &a1, selected: &selectedA1Id)
            applyDefault(id: ui?.default_anchor2_id, slot: &a2, selected: &selectedA2Id)
            applyDefault(id: ui?.default_target_id, slot: &tgt, selected: &selectedTgtId)
            if let v = ui?.default_ld1 { a1Ld = String(v) }
            if let v = ui?.default_ld2 { a2Ld = String(v) }
            applyDefaultEngine(id: ui?.default_engine_id)
            if let v = ui?.default_eta_c { engEta = String(v) }
            if let v = ui?.default_thrust_alt_m { engAlt = String(format: "%.0f", v) }
            if let v = ui?.default_thrust_mach { engMach = String(v) }
            statusText = presets.isEmpty
                ? "data.json 缺少 combat_radius_presets，请运行 build_all.py"
                : "预设已加载 · \(presets.count) 型 · 发动机 \(enginePresets.count) 台"
        } catch {
            statusText = error.localizedDescription
        }
    }

    private func applyDefault(
        id: String?,
        slot: inout CombatRadiusAircraftInput,
        selected: inout String
    ) {
        guard let p = (id.flatMap { targetId in presets.first(where: { $0.id == targetId }) }) ?? presets.first else { return }
        selected = p.id
        slot.apply(p)
    }

    private func orderedPairs(_ labels: [String: String], preferred: [String]) -> [(String, String)] {
        // 按给定顺序输出标签对，其余键按字母序追加
        let head = preferred.compactMap { key -> (String, String)? in
            guard let name = labels[key] else { return nil }
            return (key, name)
        }
        let tail = labels.keys.filter { !preferred.contains($0) }.sorted().compactMap { key -> (String, String)? in
            guard let name = labels[key] else { return nil }
            return (key, name)
        }
        return head + tail
    }

    func applyA1() {
        guard let p = presets.first(where: { $0.id == selectedA1Id }) else { return }
        a1.apply(p)
        if let known = p.ld_known { a1Ld = String(known) }
    }

    func applyA2() {
        guard let p = presets.first(where: { $0.id == selectedA2Id }) else { return }
        a2.apply(p)
        if let known = p.ld_known { a2Ld = String(known) }
    }

    func applyTgt() {
        guard let p = presets.first(where: { $0.id == selectedTgtId }) else { return }
        tgt.apply(p)
    }

    /// 填入所选发动机的 BPR/OPR/T4；有海平面军推时一并写入
    func applyEngine() {
        guard let p = enginePresets.first(where: { $0.id == selectedEngineId }) else { return }
        engBpr = String(p.bpr)
        engOpr = String(p.opr)
        engT4 = String(format: "%.0f", p.t4_K)
        if let tsl = p.tsl_kN {
            engTsl = String(tsl)
        }
    }

    private func applyDefaultEngine(id: String?) {
        let chosen = id.flatMap { targetId in enginePresets.first(where: { $0.id == targetId }) }
            ?? enginePresets.first(where: { $0.tsl_kN != nil })
            ?? enginePresets.first
        guard let p = chosen else { return }
        selectedEngineId = p.id
        applyEngine()
    }

    func run() async {
        running = true
        statusText = "计算中…"
        defer { running = false }
        do {
            let payload: [String: Any] = [
                "action": "predict_ld",
                "params": [
                    "anchor1": a1.asParams(),
                    "ld1_target": Double(a1Ld) ?? 8.8,
                    "anchor2": a2.asParams(),
                    "ld2_target": Double(a2Ld) ?? 8.0,
                    "target": tgt.asParams(),
                ],
            ]
            let r = try await LocalSimulatorEngine.shared.runCombatRadius(payload: payload)
            guard r.success else {
                throw NSError(
                    domain: "CombatRadius",
                    code: 1,
                    userInfo: [NSLocalizedDescriptionKey: r.error ?? "估算失败"]
                )
            }
            result = r
            if let ld = r.target?.ld {
                statusText = String(format: "L/D = %.4f", ld)
            } else {
                statusText = "READY"
            }
        } catch {
            result = nil
            statusText = error.localizedDescription
        }
    }

    /// 估算给定高度/马赫数下的可用军推
    func runThrust() async {
        running = true
        statusText = "军推计算中…"
        defer { running = false }
        do {
            var params: [String: Any] = [
                "name": enginePresets.first(where: { $0.id == selectedEngineId })?.name ?? "",
                "bpr": Double(engBpr) ?? 0,
                "opr": Double(engOpr) ?? 0,
                "t4_K": Double(engT4) ?? 0,
                "tsl_kN": Double(engTsl) ?? 0,
                "alt_m": Double(engAlt) ?? 11000,
                "mach": Double(engMach) ?? 1.5,
                "eta_c": Double(engEta) ?? 0.87,
            ]
            if let fan = Double(engFanPr), fan > 1 {
                params["fan_pr_override"] = fan
            }
            let payload: [String: Any] = [
                "action": "estimate_thrust",
                "params": params,
            ]
            let r = try await LocalSimulatorEngine.shared.runCombatRadius(payload: payload)
            guard r.success else {
                throw NSError(
                    domain: "CombatRadius",
                    code: 1,
                    userInfo: [NSLocalizedDescriptionKey: r.error ?? "估算失败"]
                )
            }
            thrustResult = r
            if let kn = r.thrust_kN {
                statusText = String(format: "军推 = %.1f kN", kn)
            } else {
                statusText = "READY"
            }
        } catch {
            thrustResult = nil
            statusText = error.localizedDescription
        }
    }
}
