import Foundation
import SwiftUI

/// 主页面状态机：对齐小程序 pages/index/index.js
@MainActor
final class SimulatorViewModel: ObservableObject {
    @Published var modeList: [ModeItem] = []
    @Published var strategyList: [ModeItem] = []
    @Published var currentMode: String = "ski_jump"
    @Published var currentStrategy: String = "A"
    @Published var showStrategy: Bool = false
    @Published var strategyTitle: String = "喷口策略"
    @Published var strategyDescription: String = ""

    @Published var carriers: [Carrier] = []
    @Published var aircraft: [Aircraft] = []
    @Published var selectedCarrierId: String?
    @Published var selectedAircraftId: String?

    @Published var carrierSpecs: [SpecItem] = []
    @Published var aircraftSpecs: [SpecItem] = []

    @Published var showSkiJump: Bool = false
    @Published var skiAngle: String = ""
    @Published var skiArcLength: String = ""
    @Published var skiHeight: String = ""
    @Published var skiHorizontal: String = "—"

    @Published var windKt: String = ""
    @Published var tempC: String = "30"
    @Published var massKg: String = ""

    @Published var statusText: String = ""
    @Published var statusKind: StatusKind = .idle
    @Published var outputText: String = "选择参数后点击「开始仿真」，结果将显示在此处。"
    @Published var outputEmpty: Bool = true
    @Published var outputSummary: String = ""
    @Published var highlights: [ResultHighlight] = []
    @Published var resultStale: Bool = false
    @Published var outputDetailsOpen: Bool = true
    @Published var massRangeHint: String = ""
    @Published var massError: String = ""
    @Published var running: Bool = false
    @Published var showTrajectory: Bool = false
    @Published var chartResult: SimulationResult?
    @Published var engineReady: Bool = false

    private var catalog: CatalogPayload?
    private var stovlStrategies: [String: String] = [:]
    private var tiltrotorStrategies: [String: String] = [:]
    private var windUserEdited = false
    private var massUserEdited = false
    private var resultFresh = false

    var selectedCarrier: Carrier? {
        carriers.first { $0.id == selectedCarrierId }
    }

    var selectedAircraft: Aircraft? {
        aircraft.first { $0.id == selectedAircraftId }
    }

    func bootstrap() async {
        setStatus("正在加载本地数据与仿真引擎…", .loading)
        do {
            let resolved = try CatalogStore.loadBundledCatalog()
            catalog = resolved
            stovlStrategies = resolved.stovl_strategies ?? [
                "A": "策略 A — 延迟偏转喷口",
                "B": "策略 B — 全程固定喷口",
                "C": "策略 C — 尾流约束最优偏转",
            ]
            tiltrotorStrategies = resolved.tiltrotor_strategies ?? [
                "A": "策略 A — 延迟倾转短舱",
                "B": "策略 B — 全程固定短舱角",
            ]
            modeList = modesToList(resolved.modes)
            strategyList = modesToList(stovlStrategies)
            let ui = resolved.takeoff_config?.ui
            tempC = ui?.default_temp_c.map { String(format: "%.0f", $0) } ?? "30"
            applyMode(ui?.default_mode ?? "ski_jump")
            if let strategy = ui?.default_strategy {
                currentStrategy = strategy
            }
            setStatus("目录已加载，正在初始化本地 Python 引擎（首次可能较慢）…", .loading)
            try await LocalSimulatorEngine.shared.prepare()
            engineReady = true
            setStatus("本地仿真引擎已就绪（数据与计算均在本机）", .ok)
        } catch {
            engineReady = false
            setStatus(error.localizedDescription, .error)
        }
    }

    func setStatus(_ text: String, _ kind: StatusKind) {
        statusText = text
        statusKind = kind
    }

    func applyMode(_ mode: String) {
        guard let data = catalog else { return }
        carriers = Physics.filterCarriersForMode(mode, data.carriers)
        aircraft = Physics.filterAircraftForMode(mode, data.aircraft)
        showStrategy =
            mode == "short_takeoff"
            || mode == "short_ski_jump"
            || mode == "tiltrotor_short_takeoff"
        let isTilt = mode == "tiltrotor_short_takeoff"
        let strategyMap = isTilt ? tiltrotorStrategies : stovlStrategies
        if isTilt, currentStrategy == "C" { currentStrategy = "A" }
        windUserEdited = false
        massUserEdited = false
        currentMode = mode
        strategyTitle = isTilt ? "短舱倾转策略" : "喷口策略"
        strategyList = modesToList(strategyMap)
        updateStrategyDescription()
        selectedCarrierId = carriers.first?.id
        selectedAircraftId = aircraft.first?.id
        showTrajectory = false
        chartResult = nil
        refreshSelections()
        markResultsStale()
    }

    func refreshSelections() {
        updateCarrierInfo()
        updateAircraftInfo()
    }

    func updateStrategyDescription() {
        guard showStrategy else {
            strategyDescription = ""
            return
        }
        let cfg = catalog?.takeoff_config
        let descs =
            currentMode == "tiltrotor_short_takeoff"
            ? cfg?.tiltrotor_strategy_descriptions
            : cfg?.stovl_strategy_descriptions
        strategyDescription = descs?[currentStrategy] ?? ""
        markResultsStale()
    }

    func updateSkiJumpFromInputs() {
        guard let carrier = selectedCarrier, carrier.ski_jump else { return }
        guard let angle = Double(skiAngle), angle > 0 else { return }
        let arcLen = Double(skiArcLength)
        do {
            let geom = try Physics.computeSkiJumpArc(
                angleDeg: angle,
                lipHeightM: nil,
                arcLengthM: (arcLen != nil && (arcLen ?? 0) > 0) ? arcLen : nil
            )
            skiHeight = String(format: "%.2f", geom.lipHeightM)
            skiHorizontal = Physics.fmtNum(geom.horizontalM, digits: 1)
        } catch {
            // 输入无效时保持原值
        }
    }

    func updateCarrierInfo() {
        guard let c = selectedCarrier else {
            carrierSpecs = []
            showSkiJump = false
            return
        }
        if c.ski_jump, let base = Physics.resolveCarrierSkiJump(c) {
            skiAngle = String(base.angleDeg)
            skiArcLength = String(format: "%.1f", base.arcLengthM)
        }
        carrierSpecs = [
            SpecItem(label: "最大航速", value: "\(Physics.fmtInt(c.max_speed_kt)) kt"),
            SpecItem(label: "甲板总长度", value: "\(Physics.fmtNum(c.total_deck_length_m, digits: 1)) m"),
            SpecItem(
                label: "滑跃甲板",
                value: c.ski_jump ? "是（参数可编辑）" : "否（平直甲板）"
            ),
        ]
        showSkiJump = Physics.modeNeedsSkiJump(currentMode) && c.ski_jump
        if !windUserEdited, let wind = Physics.defaultDeckWindKt(c) {
            windKt = String(Int(wind))
        }
        if c.ski_jump {
            updateSkiJumpFromInputs()
        }
    }

    func updateAircraftInfo() {
        guard let ac = selectedAircraft else {
            aircraftSpecs = []
            return
        }
        let aero = Physics.computeAircraftAero(ac)
        let isVtol = ac.type_label == "v/stol"
        let isTilt = ac.type_label == "tiltrotor"
        var specs: [SpecItem] = [
            SpecItem(label: "最大起飞重量 (MTOW)", value: "\(Physics.fmtInt(ac.mtow_kg)) kg"),
            SpecItem(label: "空重", value: "\(Physics.fmtInt(ac.empty_kg)) kg"),
            SpecItem(label: "最大内油", value: "\(Physics.fmtInt(ac.internal_fuel_kg)) kg"),
            SpecItem(label: "中距弹型号", value: ac.bvr_missile),
            SpecItem(label: "中距弹重量", value: "\(Physics.fmtNum(ac.missile_mass_kg, digits: 1)) kg/枚"),
            SpecItem(label: "最大载弹量", value: "\(Physics.fmtInt(Physics.maxPayloadKg(ac))) kg"),
            SpecItem(
                label: isTilt ? "默认起飞重量（空重+内油+机组）" : "4枚中距弹满内油空战起飞重量",
                value: "\(Physics.fmtInt(Physics.a2aMassKg(ac))) kg"
            ),
            SpecItem(label: "翼展", value: "\(Physics.fmtNum(ac.wingspan_m, digits: 2)) m"),
            SpecItem(label: "翼面积", value: "\(Physics.fmtNum(ac.wing_area_m2, digits: 2)) m²"),
        ]
        if isVtol {
            specs.append(contentsOf: [
                SpecItem(label: "主喷管推力 (15°C SL)", value: "\(Physics.fmtNum((ac.t_main_stovl_sl_n ?? 0) / 1000, digits: 1)) kN"),
                SpecItem(label: "升力风扇推力", value: "\(Physics.fmtNum((ac.t_liftfan_sl_n ?? 0) / 1000, digits: 1)) kN"),
                SpecItem(label: "滚转喷管推力", value: "\(Physics.fmtNum((ac.t_rollposts_sl_n ?? 0) / 1000, digits: 1)) kN"),
            ])
        } else if isTilt {
            let block = (ac.nacelle_blockage_frac ?? 0.1) * 100
            specs.append(contentsOf: [
                SpecItem(label: "总轴功率 (15°C SL)", value: "\(Physics.fmtNum((ac.shaft_power_sl_w ?? 0) / 1e6, digits: 2)) MW"),
                SpecItem(label: "桨盘直径", value: "\(Physics.fmtNum(ac.prop_diameter_m ?? 0, digits: 2)) m"),
                SpecItem(label: "短舱遮挡比", value: "\(Physics.fmtNum(block, digits: 0)) %"),
            ])
        } else {
            specs.append(
                SpecItem(label: "最大加力推力 (15°C SL)", value: "\(Physics.fmtNum((ac.t_max_sl_n ?? 0) / 1000, digits: 1)) kN")
            )
        }
        specs.append(contentsOf: [
            SpecItem(label: "前缘后掠角", value: "\(Physics.fmtNum(ac.sweep_le_deg, digits: 1))°"),
            SpecItem(label: "展弦比", value: Physics.fmtNum(aero.aspectRatio, digits: 3)),
            SpecItem(label: "升力线斜率 C_Lα", value: "\(Physics.fmtNum(aero.clAlphaPerRad, digits: 4)) /rad"),
            SpecItem(
                label: "滑行升力系数 Cl_taxi",
                value: "\(Physics.fmtNum(aero.clTaxi, digits: 4))（迎角 \(Physics.fmtNum(aero.taxiAlphaDeg, digits: 1))°）"
            ),
            SpecItem(label: "20° 攻角升力系数", value: Physics.fmtNum(aero.cl20deg, digits: 4)),
            SpecItem(label: "零升阻力系数 Cd0", value: Physics.fmtNum(aero.cd0, digits: 4)),
        ])
        aircraftSpecs = specs
        if !massUserEdited {
            massKg = String(Int(round(Physics.a2aMassKg(ac))))
        }
        refreshMassHint()
    }

    func onCarrierPicked(_ id: String) {
        windUserEdited = false
        selectedCarrierId = id
        updateCarrierInfo()
        markResultsStale()
    }

    func onAircraftPicked(_ id: String) {
        massUserEdited = false
        selectedAircraftId = id
        updateAircraftInfo()
        markResultsStale()
    }

    func markWindEdited() {
        windUserEdited = true
        markResultsStale()
    }

    func markMassEdited() {
        massUserEdited = true
        refreshMassHint()
        markResultsStale()
    }

    func markResultsStale() {
        guard resultFresh else { return }
        resultFresh = false
        resultStale = true
        setStatus("参数已更改 — 结果已过期，请重新仿真", .stale)
    }

    /// 与 Python validate_takeoff_mass 对齐
    func validateTakeoffMass(_ mass: Double, mtow: Double, empty: Double) -> String {
        if mass <= 0 { return "起飞重量必须为正数" }
        if mass > mtow + 1e-6 {
            return "起飞重量 \(Int(mass.rounded())) kg 超出最大起飞重量 \(Int(mtow.rounded())) kg"
        }
        if mass + 1e-6 < empty {
            return "起飞重量 \(Int(mass.rounded())) kg 低于空重 \(Int(empty.rounded())) kg"
        }
        return ""
    }

    func refreshMassHint() {
        guard let ac = selectedAircraft else {
            massRangeHint = ""
            massError = ""
            return
        }
        massRangeHint = "范围：空重 \(Int(ac.empty_kg.rounded())) – MTOW \(Int(ac.mtow_kg.rounded())) kg"
        if let mass = Double(massKg) {
            massError = validateTakeoffMass(mass, mtow: ac.mtow_kg, empty: ac.empty_kg)
        } else if massKg.isEmpty {
            massError = ""
        } else {
            massError = "请填写有效的起飞重量"
        }
    }

    func runSimulation() async {
        guard let carrier = selectedCarrier, let aircraft = selectedAircraft else {
            setStatus("请选择航母和战斗机", .error)
            return
        }
        guard let mass = Double(massKg), let temp = Double(tempC), let wind = Double(windKt) else {
            setStatus("请填写有效的重量、温度和甲板风", .error)
            return
        }
        refreshMassHint()
        if !massError.isEmpty {
            setStatus(massError, .error)
            return
        }

        running = true
        outputEmpty = false
        outputText = "计算中…"
        outputSummary = ""
        highlights = []
        resultStale = false
        outputDetailsOpen = true
        showTrajectory = false
        chartResult = nil
        setStatus("仿真计算中（可能需要数秒至数十秒）…", .loading)

        do {
            var payload: [String: Any] = [
                "mode": currentMode,
                "aircraft": try aircraft.asJSONDictionary(),
                "carrier": try carrier.asJSONDictionary(),
                "mass_kg": mass,
                "temp_c": temp,
                "wind_kt": wind,
                "total_deck_length_m": carrier.total_deck_length_m,
            ]
            if showStrategy {
                payload["strategy"] = currentStrategy
            }
            if Physics.modeNeedsSkiJump(currentMode), carrier.ski_jump {
                updateSkiJumpFromInputs()
                if let a = Double(skiAngle) { payload["ski_jump_angle_deg"] = a }
                if let arc = Double(skiArcLength) { payload["ski_jump_arc_length_m"] = arc }
                if let h = Double(skiHeight) { payload["ski_jump_height_m"] = h }
            }

            let result = try await LocalSimulatorEngine.shared.run(payload: payload)
            let traj = result.trajectory
            let deck = result.deck_profile
            let showTraj =
                Physics.modeHasTrajectory(currentMode)
                && result.success
                && (traj?.isEmpty == false)
                && (deck?.points.isEmpty == false)

            outputText = result.output ?? "(无输出)"
            chartResult = showTraj ? result : nil
            showTrajectory = showTraj

            if result.success {
                outputSummary = Self.formatOutputSummary(result)
                highlights = result.highlights ?? []
                resultStale = false
                resultFresh = true
                outputDetailsOpen = false
                let trajNote = showTraj ? " · 轨迹 \(traj?.count ?? 0) 点" : ""
                let missing =
                    Physics.modeHasTrajectory(currentMode) && !showTraj ? " · 未返回轨迹数据" : ""
                if result.deck_launch_ok == true {
                    setStatus("仿真完成 — 甲板可用\(trajNote)\(missing)", .ok)
                } else {
                    setStatus("仿真完成 — 甲板不足\(trajNote)\(missing)", .error)
                }
            } else {
                outputSummary = ""
                highlights = []
                resultFresh = false
                outputDetailsOpen = true
                setStatus(result.error ?? "仿真失败", .error)
            }
        } catch {
            outputText = error.localizedDescription
            outputSummary = ""
            showTrajectory = false
            chartResult = nil
            setStatus("仿真出错: \(error.localizedDescription)", .error)
        }
        running = false
    }

    /// 仿真输出卡片标题右侧摘要：优先 API 字段，否则本地拼装
    private static func formatOutputSummary(_ result: SimulationResult) -> String {
        if let summary = result.output_summary, !summary.isEmpty {
            return summary
        }
        guard let distance = result.distance_m else { return "" }
        let dist = "起飞 \(Physics.fmtNum(distance, digits: 1)) m"
        guard let margin = result.deck_margin_m else { return dist }
        let deck = margin >= 0
            ? "余量 \(Physics.fmtNum(margin, digits: 1)) m"
            : "超出 \(Physics.fmtNum(-margin, digits: 1)) m"
        return "\(dist) · \(deck)"
    }

    private func modesToList(_ modes: [String: String]) -> [ModeItem] {
        // 保持 catalog 插入序：modes 在 JSON 中顺序固定
        let preferred = ["ski_jump", "short_takeoff", "short_ski_jump", "tiltrotor_short_takeoff", "A", "B", "C"]
        var items: [ModeItem] = []
        var seen = Set<String>()
        for key in preferred where modes[key] != nil {
            items.append(ModeItem(id: key, label: modes[key]!))
            seen.insert(key)
        }
        for (id, label) in modes where !seen.contains(id) {
            items.append(ModeItem(id: id, label: label))
        }
        return items
    }
}
