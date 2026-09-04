import Foundation
import Combine

/// 作战半径单机输入（几何）
struct CombatRadiusAircraftInput {
    var name = ""
    var ar = ""
    var sweepDeg = ""
    var sweepInnerDeg = ""
    var sweepOuterDeg = ""
    var wingLoading = ""
    var tc = ""
    var mach = "0.8"
    var altM = "12000"
    var planform = "trapezoidal"
    var layout = "conventional"
    var inlet = "dsi"
    var storeMount = "internal"
    var bwb = false
    var rough = false
    var lengthM = ""
    var wingspanM = ""
    var fuseWidthM = ""
    var fuseHeightM = ""
    var noseConeLengthM = ""
    var noseConeDiameterM = ""
    var noseLengthM = ""
    var noseRootDiameterM = ""
    var fuseBodyLengthM = ""
    var mainWingAreaM2 = ""
    var canardHtailAreaM2 = ""
    var ventralFinAreaM2 = ""
    var vtailAreaM2 = ""
    var machAngleDeg = ""
    var wingAreaM2 = ""
    var typeLabel = ""

    /// 填入预设几何
    mutating func apply(_ p: CombatRadiusPresetItem) {
        name = p.name
        ar = String(p.AR)
        sweepDeg = String(p.sweep_deg)
        sweepInnerDeg = p.sweep_inner_deg.map { String($0) } ?? ""
        sweepOuterDeg = p.sweep_outer_deg.map { String($0) } ?? ""
        wingLoading = String(p.wing_loading)
        tc = String(p.tc)
        mach = String(p.mach)
        altM = String(format: "%.0f", p.alt_m)
        planform = p.planform
        layout = p.layout
        inlet = p.inlet ?? "dsi"
        storeMount = p.store_mount ?? "internal"
        bwb = p.bwb
        rough = p.rough
        lengthM = p.length_m.map { String($0) } ?? ""
        wingspanM = p.wingspan_m.map { String($0) } ?? ""
        fuseWidthM = p.fuse_width_m.map { String($0) } ?? ""
        fuseHeightM = p.fuse_height_m.map { String($0) } ?? ""
        noseConeLengthM = p.nose_cone_length_m.map { String($0) } ?? ""
        noseConeDiameterM = p.nose_cone_diameter_m.map { String($0) } ?? ""
        noseLengthM = p.nose_length_m.map { String($0) } ?? ""
        noseRootDiameterM = p.nose_root_diameter_m.map { String($0) } ?? ""
        fuseBodyLengthM = p.fuse_body_length_m.map { String($0) } ?? ""
        mainWingAreaM2 = p.main_wing_area_m2.map { String($0) } ?? ""
        canardHtailAreaM2 = p.canard_htail_area_m2.map { String($0) } ?? ""
        ventralFinAreaM2 = p.ventral_fin_area_m2.map { String($0) } ?? ""
        vtailAreaM2 = p.vtail_area_m2.map { String($0) } ?? ""
        machAngleDeg = p.mach_angle_deg.map { String($0) } ?? ""
        wingAreaM2 = p.wing_area_m2.map { String($0) } ?? ""
        typeLabel = p.type_label ?? ""
    }

    /// 转为 Python API 机型字典
    func asParams() -> [String: Any] {
        [
            "name": name.isEmpty ? "未命名" : name,
            "AR": Double(ar) ?? 0,
            "sweep_deg": Double(sweepDeg) ?? 0,
            "sweep_inner_deg": Double(sweepInnerDeg) ?? 0,
            "sweep_outer_deg": Double(sweepOuterDeg) ?? 0,
            "wing_loading": Double(wingLoading) ?? 0,
            "tc": Double(tc) ?? 0,
            "mach": 0.8,
            "alt_m": 12000.0,
            "planform": planform,
            "layout": layout,
            "inlet": inlet,
            "store_mount": storeMount,
            "bwb": bwb,
            "rough": rough,
            "length_m": Double(lengthM) ?? 0,
            "wingspan_m": Double(wingspanM) ?? 0,
            "fuse_width_m": Double(fuseWidthM) ?? 0,
            "fuse_height_m": Double(fuseHeightM) ?? 0,
            "nose_cone_length_m": Double(noseConeLengthM) ?? 0,
            "nose_cone_diameter_m": Double(noseConeDiameterM) ?? 0,
            "nose_length_m": Double(noseLengthM) ?? 0,
            "nose_root_diameter_m": Double(noseRootDiameterM) ?? 0,
            "fuse_body_length_m": Double(fuseBodyLengthM) ?? 0,
            "main_wing_area_m2": Double(mainWingAreaM2) ?? 0,
            "canard_htail_area_m2": Double(canardHtailAreaM2) ?? 0,
            "ventral_fin_area_m2": Double(ventralFinAreaM2) ?? 0,
            "vtail_area_m2": Double(vtailAreaM2) ?? 0,
            "mach_angle_deg": Double(machAngleDeg) ?? 0,
            "wing_area_m2": Double(wingAreaM2) ?? 0,
            "type_label": typeLabel,
        ]
    }
}

/// 作战半径估算状态：预计算仪表盘 + 三个按需查询
@MainActor
final class CombatRadiusViewModel: ObservableObject {
    @Published var statusText = "加载预设…"
    @Published var running = false
    @Published var tgt = CombatRadiusAircraftInput()
    @Published var presets: [CombatRadiusPresetItem] = []
    @Published var selectedTgtId = ""
    @Published var planformOptions: [(String, String)] = [("trapezoidal", "梯形翼")]
    @Published var layoutOptions: [(String, String)] = [("conventional", "常规")]
    @Published var inletOptions: [(String, String)] = [("dsi", "DSI"), ("caret", "加莱特")]
    @Published var storeMountOptions: [(String, String)] = [
        ("internal", "内埋弹舱"), ("semi_recessed", "半埋"), ("pylon", "挂架"),
    ]
    @Published var enginePresets: [CombatRadiusEnginePresetItem] = []
    @Published var selectedEngineId = ""
    @Published var engBpr = ""
    @Published var engOpr = ""
    @Published var engT4 = ""
    @Published var engTsl = ""
    @Published var engMaxTsl = ""
    @Published var engEta = "0.87"
    @Published var wtEmpty = ""
    @Published var wtFuel = ""
    @Published var wtPilots = "1"
    @Published var wtMissile = ""
    @Published var wtNMissiles = "4"
    @Published var wtEngines = "1"
    @Published var wtCarrier = false
    @Published var dashboard: CombatRadiusResult?
    @Published var dashSource = "STANDBY"
    @Published var q1Mach = "0.9"
    @Published var q1Result: CombatRadiusResult?
    @Published var q2Mach = "0.8"
    @Published var q2Alt = "12000"
    @Published var q2Result: CombatRadiusResult?
    @Published var q3Mach = "0.8"
    @Published var q3Alt = "12000"
    @Published var q3Load = "0.45"
    @Published var q3Result: CombatRadiusResult?
    private var resultsMap: [String: CombatRadiusResult] = [:]
    private var liveTask: Task<Void, Never>?
    private var applying = false
    private var dryToMaxRatio = 0.7
    /// 计算进行中又改了参数时，结束后再跑一轮
    private var dashPending = false

    init() {
        loadPresets()
    }

    /// 从 Bundle catalog 读取预设与预计算仪表盘
    func loadPresets() {
        do {
            let catalog = try CatalogStore.loadBundledCatalog()
            presets = CombatRadiusPresetItem.sortedByNationThenName(
                catalog.combat_radius_presets ?? []
            )
            enginePresets = catalog.combat_radius_engine_presets ?? []
            resultsMap = catalog.combat_radius_results?.aircraft ?? [:]
            if let labels = catalog.combat_radius_config?.planform_labels, !labels.isEmpty {
                let order = ["trapezoidal", "swept", "delta", "double_delta", "diamond", "lambda", "unswept"]
                planformOptions = orderedPairs(labels, preferred: order)
            }
            if let labels = catalog.combat_radius_config?.layout_labels, !labels.isEmpty {
                let order = ["conventional", "canard", "tailless"]
                layoutOptions = orderedPairs(labels, preferred: order)
            }
            if let labels = catalog.combat_radius_config?.inlet_labels, !labels.isEmpty {
                let order = ["dsi", "caret"]
                inletOptions = orderedPairs(labels, preferred: order)
            }
            if let labels = catalog.combat_radius_config?.store_mount_labels, !labels.isEmpty {
                let order = ["internal", "semi_recessed", "pylon"]
                storeMountOptions = orderedPairs(labels, preferred: order)
            }
            let ui = catalog.combat_radius_config?.ui
            if let v = ui?.default_eta_c { engEta = String(v) }
            if let r = catalog.combat_radius_config?.engine?.dry_to_max_thrust_ratio, r > 0, r <= 1 {
                dryToMaxRatio = r
            }
            let defaultId = ui?.default_target_id
            applying = true
            if let p = (defaultId.flatMap { id in presets.first(where: { $0.id == id }) }) ?? presets.first {
                selectedTgtId = p.id
                tgt.apply(p)
                applyWeight(from: p)
                if let engId = p.engine_id, enginePresets.contains(where: { $0.id == engId }) {
                    selectedEngineId = engId
                    applyEngine()
                }
                showSnapshot()
            }
            DispatchQueue.main.async { [weak self] in
                self?.applying = false
            }
            statusText = presets.isEmpty
                ? "data.json 缺少 combat_radius_presets，请运行 build_all.py"
                : "预设已加载 · \(presets.count) 型"
        } catch {
            statusText = error.localizedDescription
        }
    }

    private func orderedPairs(_ labels: [String: String], preferred: [String]) -> [(String, String)] {
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

    /// 选择战机后填充参数并加载预计算
    func applyAircraft() {
        guard let p = presets.first(where: { $0.id == selectedTgtId }) else { return }
        applying = true
        tgt.apply(p)
        applyWeight(from: p)
        if let engId = p.engine_id, enginePresets.contains(where: { $0.id == engId }) {
            selectedEngineId = engId
            applyEngine()
        }
        showSnapshot()
        DispatchQueue.main.async { [weak self] in
            self?.applying = false
        }
    }

    /// 从机型预设填入空战重量与发动机台数
    func applyWeight(from p: CombatRadiusPresetItem?) {
        guard let p else { return }
        if let v = p.empty_kg { wtEmpty = String(format: "%.0f", v) }
        if let v = p.internal_fuel_kg { wtFuel = String(format: "%.0f", v) }
        if let v = p.n_pilots { wtPilots = String(v) }
        if let v = p.missile_mass_kg { wtMissile = String(format: "%.0f", v) }
        wtNMissiles = "4"
        if let v = p.n_engines { wtEngines = String(v) }
        wtCarrier = p.carrier ?? false
    }

    /// 填入所选发动机的 BPR/OPR/T4；有海平面军推时一并写入
    func applyEngine() {
        guard let p = enginePresets.first(where: { $0.id == selectedEngineId }) else { return }
        engBpr = String(p.bpr)
        engOpr = String(p.opr)
        engT4 = String(format: "%.0f", p.t4_K)
        if let tsl = p.tsl_kN, tsl > 0 {
            engTsl = String(tsl)
        } else if let maxTsl = p.max_tsl_kN, maxTsl > 0 {
            engTsl = String(format: "%.1f", maxTsl * dryToMaxRatio)
        } else {
            engTsl = ""
        }
        engMaxTsl = p.max_tsl_kN.map { String($0) } ?? ""
    }

    func showSnapshot() {
        if let snap = resultsMap[selectedTgtId], snap.success {
            dashboard = snap
            dashSource = "预计算快照"
        } else {
            dashboard = resultsMap[selectedTgtId]
            dashSource = resultsMap[selectedTgtId]?.error ?? "无预计算快照。填写军推后点「计算作战半径」。"
        }
    }

    /// 参数改动后延迟现场重算仪表盘
    func scheduleLiveDash() {
        if applying { return }
        liveTask?.cancel()
        liveTask = Task { [weak self] in
            try? await Task.sleep(nanoseconds: 600_000_000)
            guard let self, !Task.isCancelled else { return }
            await self.runDashboard()
        }
    }

    func dashboardParams() -> [String: Any] {
        var params: [String: Any] = [
            "name": tgt.name,
            "target": tgt.asParams(),
            "empty_kg": Double(wtEmpty) ?? 0,
            "internal_fuel_kg": Double(wtFuel) ?? 0,
            "n_pilots": Double(wtPilots) ?? 1,
            "missile_mass_kg": Double(wtMissile) ?? 0,
            "n_missiles": Double(wtNMissiles) ?? 4,
            "n_engines": Int(wtEngines) ?? 1,
            "carrier": wtCarrier,
            "bpr": Double(engBpr) ?? 0,
            "opr": Double(engOpr) ?? 0,
            "t4_K": Double(engT4) ?? 0,
            "eta_c": Double(engEta) ?? 0.87,
        ]
        if let tsl = Double(engTsl), tsl > 0 {
            params["tsl_kN"] = tsl
        }
        if let maxTsl = Double(engMaxTsl), maxTsl > 0 {
            params["max_tsl_kN"] = maxTsl
        }
        return params
    }

    /// 立即按当前机型/发动机参数重算各速度仪表盘（对应「计算作战半径」）。
    func requestLiveDash() async {
        liveTask?.cancel()
        await runDashboard()
    }

    func runDashboard() async {
        if running {
            dashPending = true
            return
        }
        dashPending = false
        running = true
        dashSource = "重算中…"
        defer {
            running = false
            if dashPending {
                dashPending = false
                Task { await self.runDashboard() }
            }
        }
        do {
            let r = try await LocalSimulatorEngine.shared.runCombatRadius(payload: [
                "action": "aircraft_dashboard",
                "params": dashboardParams(),
            ])
            guard r.success else {
                throw NSError(domain: "CombatRadius", code: 1, userInfo: [NSLocalizedDescriptionKey: r.error ?? "仪表盘失败"])
            }
            dashboard = r
            dashSource = "现场重算"
            statusText = "READY"
        } catch {
            dashboard = nil
            dashSource = error.localizedDescription
            statusText = error.localizedDescription
        }
    }

    /// 给定马赫搜索最佳升阻比与巡航高度
    func runSearchCruise() async {
        running = true
        statusText = "搜索中…"
        defer { running = false }
        do {
            var params = dashboardParams()
            params["mach"] = Double(q1Mach) ?? 0.9
            let r = try await LocalSimulatorEngine.shared.runCombatRadius(payload: [
                "action": "search_best_cruise",
                "params": params,
            ])
            guard r.success else {
                throw NSError(domain: "CombatRadius", code: 1, userInfo: [NSLocalizedDescriptionKey: r.error ?? "搜索失败"])
            }
            q1Result = r
            statusText = r.feasible == true ? "READY" : (r.fail_reason ?? "READY")
        } catch {
            q1Result = nil
            statusText = error.localizedDescription
        }
    }

    /// 给定速度与高度计算升阻比与效率
    func runPoint() async {
        running = true
        statusText = "计算中…"
        defer { running = false }
        do {
            var params = dashboardParams()
            params["mach"] = Double(q2Mach) ?? 0.8
            params["alt_m"] = Double(q2Alt) ?? 12000
            let r = try await LocalSimulatorEngine.shared.runCombatRadius(payload: [
                "action": "estimate_efficiency",
                "params": params,
            ])
            guard r.success else {
                throw NSError(domain: "CombatRadius", code: 1, userInfo: [NSLocalizedDescriptionKey: r.error ?? "计算失败"])
            }
            q2Result = r
            statusText = "READY"
        } catch {
            q2Result = nil
            statusText = error.localizedDescription
        }
    }

    /// 给定速度、高度、负载计算发动机效率
    func runEngineCycle() async {
        running = true
        statusText = "计算中…"
        defer { running = false }
        do {
            let params: [String: Any] = [
                "bpr": Double(engBpr) ?? 0,
                "opr": Double(engOpr) ?? 0,
                "t4_K": Double(engT4) ?? 0,
                "mach": Double(q3Mach) ?? 0.8,
                "alt_m": Double(q3Alt) ?? 12000,
                "load": Double(q3Load) ?? 0.45,
            ]
            let r = try await LocalSimulatorEngine.shared.runCombatRadius(payload: [
                "action": "estimate_engine_cycle",
                "params": params,
            ])
            guard r.success else {
                throw NSError(domain: "CombatRadius", code: 1, userInfo: [NSLocalizedDescriptionKey: r.error ?? "计算失败"])
            }
            q3Result = r
            statusText = "READY"
        } catch {
            q3Result = nil
            statusText = error.localizedDescription
        }
    }
}
