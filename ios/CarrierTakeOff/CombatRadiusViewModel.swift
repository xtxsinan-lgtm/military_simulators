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

/// 作战半径升阻比估算状态
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

    init() {
        loadPresets()
    }

    /// 从 Bundle catalog 读取预设与默认锚点
    func loadPresets() {
        do {
            let catalog = try CatalogStore.loadBundledCatalog()
            presets = catalog.combat_radius_presets ?? []
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
            statusText = presets.isEmpty
                ? "data.json 缺少 combat_radius_presets，请运行 build_all.py"
                : "预设已加载 · \(presets.count) 型"
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
}
