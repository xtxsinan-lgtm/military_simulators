import Foundation
import SwiftUI

/// 饱和打击参数与结果状态
@MainActor
final class MissileInterceptionViewModel: ObservableObject {
    @Published var statusText = "加载预设…"
    @Published var statusTag = "STANDBY"
    @Published var running = false

    @Published var nm = "24"
    @Published var vm = "2.6"
    @Published var rcs = "0.5"
    @Published var traj = "high"
    @Published var awacsArea = "8"
    @Published var awacsType = "aesa"
    @Published var standoff = "150"
    @Published var shipArea = "12"
    @Published var shipType = "aesa"
    @Published var samRange = "40"
    @Published var samMaxAlt = "33"
    @Published var discoveryKm = "120"
    @Published var ni = "16"
    @Published var vi = "3.8"
    @Published var interceptorDia = "0.35"
    @Published var seekerType = "active_aesa"
    @Published var pk = "0.7"
    @Published var tlock = "6"
    @Published var minr = "3"
    private var resultFresh = false

    var fieldHints: [String: String] {
        (try? CatalogStore.loadBundledCatalog().missile_interception_config?.field_hints) ?? [:]
    }

    var fieldRanges: [String: MissileInterceptionFieldRange] {
        (try? CatalogStore.loadBundledCatalog().missile_interception_config?.field_ranges) ?? [:]
    }

    @Published var asmPresets: [MissileInterceptionPresetItem] = []
    @Published var aewPresets: [MissileInterceptionPresetItem] = []
    @Published var shipPresets: [MissileInterceptionPresetItem] = []
    @Published var samPresets: [MissileInterceptionPresetItem] = []
    @Published var selectedAsmId = ""
    @Published var selectedAewId = ""
    @Published var selectedShipId = ""
    @Published var selectedSamId = ""
    // 反舰为两级选择；驱护+防空共用防御方国别，空串表示不限国别
    @Published var selectedAsmNation = ""
    @Published var selectedDefenderNation = ""

    @Published var distNote = ""
    @Published var pkNote = ""
    @Published var awacsDetectKm = "待估算"
    @Published var shipDetectKm = "待估算"
    @Published var diveEntryDisplay = "—"
    @Published var hasResult = false
    @Published var resultStale = false
    @Published var result: MissileInterceptionResult?

    @Published var trajOptions: [(String, String)] = [
        ("high", "高空 / 常规弹道"),
        ("sea", "掠海 / 海面杂波环境"),
        ("glide", "滑翔体弹道（鹰击-17 等）"),
        ("ballistic", "弹道导弹弹道（鹰击-20/21 等）"),
    ]
    let radarOptions = [
        ("mechanical", "机械扫描"), ("pesa", "PESA"),
        ("aesa", "AESA"), ("gan_aesa", "GaN AESA"),
    ]
    let seekerOptions = [
        ("active_aesa", "主动 AESA"),
        ("active_mech", "主动机械"),
        ("semi_active", "半主动"),
    ]

    init() {
        loadPresets()
        applyUiDefaultsFromCatalog()
    }

    private func applyUiDefaultsFromCatalog() {
        guard let ui = try? CatalogStore.loadBundledCatalog().missile_interception_config?.ui else { return }
        if let v = ui.nm { nm = String(v) }
        if let v = ui.ni { ni = String(v) }
        if let v = ui.vm { vm = String(v) }
        if let v = ui.rcs { rcs = String(v) }
        if let v = ui.traj { traj = v }
        if let v = ui.awacs_area { awacsArea = String(v) }
        if let v = ui.awacs_type { awacsType = v }
        if let v = ui.standoff { standoff = String(v) }
        if let v = ui.ship_area { shipArea = String(v) }
        if let v = ui.ship_type { shipType = v }
        if let v = ui.sam_range { samRange = String(v) }
        if let v = ui.sam_max_alt { samMaxAlt = String(v) }
        if let v = ui.vi { vi = String(v) }
        if let v = ui.interceptor_dia { interceptorDia = String(v) }
        if let v = ui.seeker_type { seekerType = v }
        if let v = ui.tlock { tlock = String(v) }
        if let v = ui.minr { minr = String(v) }
        if let v = ui.discovery_km { discoveryKm = String(v) }
        if let v = ui.pk { pk = String(v) }
        if let v = ui.has_awacs {
            selectedAewId = v ? "" : Self.noAewId
        }
    }

    /// 「无预警机」合成预设项的固定 id
    static let noAewId = "__none__"

    /// 从 Bundle catalog 读取预设；预警机列表最前插入「无预警机」合成项
    func loadPresets() {
        do {
            let catalog = try CatalogStore.loadBundledCatalog()
            let p = catalog.missile_interception_presets
            asmPresets = p?.asm ?? []
            aewPresets = [MissileInterceptionPresetItem(id: Self.noAewId, name: "无预警机")] + (p?.aew ?? [])
            shipPresets = p?.ship ?? []
            samPresets = p?.sam ?? []
            if let types = catalog.missile_interception_config?.traj_types, !types.isEmpty {
                trajOptions = types.map { ($0.key, $0.value) }
            }
            statusText = "预设已加载"
            statusTag = "READY"
        } catch {
            statusText = error.localizedDescription
            statusTag = "ERROR"
        }
    }

    /// 当前是否选择了预警机（未选择「无预警机」即视为有预警机，含自定义/空选项）
    var hasAwacs: Bool { selectedAewId != Self.noAewId }

    /// 从预设列表提取去重国别（按首次出现顺序，与 Python nations_sorted 一致）
    static func nationsSorted(_ items: [MissileInterceptionPresetItem]) -> [String] {
        var seen: [String] = []
        for item in items {
            let nation = (item.nation ?? "").trimmingCharacters(in: .whitespaces)
            if !nation.isEmpty, !seen.contains(nation) { seen.append(nation) }
        }
        return seen
    }

    /// 合并多组预设国别（与 Python nations_union 一致）
    static func nationsUnion(_ lists: [MissileInterceptionPresetItem]...) -> [String] {
        var seen: [String] = []
        for items in lists {
            for nation in Self.nationsSorted(items) where !seen.contains(nation) {
                seen.append(nation)
            }
        }
        return seen
    }

    /// 按国别过滤预设；国别为空时返回全部
    static func filterPresets(_ items: [MissileInterceptionPresetItem], nation: String) -> [MissileInterceptionPresetItem] {
        let key = nation.trimmingCharacters(in: .whitespaces)
        if key.isEmpty { return items }
        return items.filter { ($0.nation ?? "").trimmingCharacters(in: .whitespaces) == key }
    }

    var asmNations: [String] { Self.nationsSorted(asmPresets) }
    /// 驱护舰艇 + 防空导弹国别并集，供共用选择器
    var defenderNations: [String] { Self.nationsUnion(shipPresets, samPresets) }

    var asmModels: [MissileInterceptionPresetItem] { Self.filterPresets(asmPresets, nation: selectedAsmNation) }
    var shipModels: [MissileInterceptionPresetItem] { Self.filterPresets(shipPresets, nation: selectedDefenderNation) }
    var samModels: [MissileInterceptionPresetItem] { Self.filterPresets(samPresets, nation: selectedDefenderNation) }

    /// 切换国别后型号需复位为「— 自定义 —」，避免残留其他国别的选中项
    func resetAsmModel() { selectedAsmId = "" }
    /// 切换防御方国别后同时复位舰艇与防空弹型号
    func resetDefenderModels() {
        selectedShipId = ""
        selectedSamId = ""
    }

    func applyAsmPreset() {
        guard let p = asmPresets.first(where: { $0.id == selectedAsmId }) else { return }
        if let v = p.vm { vm = String(v) }
        if let v = p.rcs { rcs = String(v) }
        if let v = p.traj { traj = v }
        markResultsStale()
    }

    func applyAewPreset() {
        guard let p = aewPresets.first(where: { $0.id == selectedAewId }) else { return }
        if let v = p.area { awacsArea = String(v) }
        if let v = p.type { awacsType = v }
        if let v = p.standoff { standoff = String(v) }
        markResultsStale()
    }

    func applyShipPreset() {
        guard let p = shipPresets.first(where: { $0.id == selectedShipId }) else { return }
        if let v = p.area { shipArea = String(v) }
        if let v = p.type { shipType = v }
        markResultsStale()
    }

    func applySamPreset() {
        guard let p = samPresets.first(where: { $0.id == selectedSamId }) else { return }
        if let v = p.vi { vi = String(v) }
        if let v = p.dia { interceptorDia = String(v) }
        if let v = p.guidance { seekerType = v }
        if let v = p.range { samRange = String(v) }
        if let v = p.max_alt { samMaxAlt = String(v) }
        markResultsStale()
    }

    private func estimateParams() -> [String: Any] {
        [
            "rcs": Double(rcs) ?? 0.5,
            "traj": traj,
            "awacs_area": Double(awacsArea) ?? 8,
            "awacs_type": awacsType,
            "standoff": Double(standoff) ?? 150,
            "ship_area": Double(shipArea) ?? 12,
            "ship_type": shipType,
            "sam_range": Double(samRange) ?? 40,
            "sam_max_alt": Double(samMaxAlt) ?? 33,
            "vm": Double(vm) ?? 2.6,
            "vi": Double(vi) ?? 3.8,
            "interceptor_dia": Double(interceptorDia) ?? 0.35,
            "seeker_type": seekerType,
            "has_awacs": hasAwacs,
            "asm_id": selectedAsmId,
            "maneuver_class": asmPresets.first(where: { $0.id == selectedAsmId })?.maneuver_class ?? "",
        ]
    }

    private func formatDiveEntryDisplay(_ dist: MissileInterceptionResult) -> String {
        if let entry = dist.dive_entry_km, entry > 0 {
            return String(format: "%.1f km（俯冲 %.0f°）", entry, dist.dive_angle_deg ?? 0)
        }
        let h = String(format: "%.0f", dist.h_target_m ?? 0)
        let alt = String(format: "%.0f", dist.sam_max_alt_km ?? 0)
        return "全程在有效射高包线内（巡航 \(h)m ≤ 最大射高 \(alt)km）"
    }

    /// 一次估算交战距离与单发拦截成功概率，填入预警机/舰载雷达探测距离与交战距离等字段。
    func estimateDistanceAndPk() async {
        statusTag = "COMPUTING"
        do {
            let params = estimateParams()
            let distR = try await LocalSimulatorEngine.shared.runMissileInterception(payload: [
                "action": "estimate_distance",
                "params": params,
            ])
            guard distR.success, let dist = distR.engage_dist, let shipDetect = distR.ship_detect_km else {
                throw NSError(domain: "MissileInterception", code: 1, userInfo: [
                    NSLocalizedDescriptionKey: distR.error ?? "交战距离估算失败",
                ])
            }
            let pkR = try await LocalSimulatorEngine.shared.runMissileInterception(payload: [
                "action": "estimate_pk",
                "params": params,
            ])
            guard pkR.success, let value = pkR.pk else {
                throw NSError(domain: "MissileInterception", code: 1, userInfo: [
                    NSLocalizedDescriptionKey: pkR.error ?? "拦截率估算失败",
                ])
            }
            let hasAwacsResult = distR.has_awacs ?? true
            let awacsDetect = hasAwacsResult ? (distR.awacs_detect_km ?? 0) : 0
            awacsDetectKm = String(format: "%.1f", awacsDetect)
            shipDetectKm = String(format: "%.1f", shipDetect)
            diveEntryDisplay = formatDiveEntryDisplay(distR)
            discoveryKm = String(format: "%.1f", dist)
            if hasAwacsResult {
                let diveSuffix: String
                if let entry = distR.dive_entry_km, entry > 0 {
                    diveSuffix = "，俯冲进入(\(String(format: "%.0f", distR.dive_angle_deg ?? 0))°/射高\(String(format: "%.0f", distR.sam_max_alt_km ?? 0))km)≈\(String(format: "%.1f", entry))km"
                } else {
                    diveSuffix = ""
                }
                distNote = "预警机探测 \(String(format: "%.0f", awacsDetect))km ｜ 舰载探测 \(String(format: "%.0f", shipDetect))km → 交战距离=\(String(format: "%.1f", dist)) km\(diveSuffix)（受限于：\(distR.binding ?? "")）"
            } else {
                let hTarget = String(format: "%.0f", distR.h_target_m ?? 0)
                let hEngage = String(format: "%.0f", distR.h_engage_m ?? 0)
                distNote = "无预警机：巡航 \(hTarget)m / 射高 \(hEngage)m，舰载探测=\(String(format: "%.0f", shipDetect))km，交战距离 \(String(format: "%.1f", dist)) km（受限于：\(distR.binding ?? "")）"
            }
            pk = String(format: "%.2f", value)
            pkNote = "估算拦截率（单发）= \(String(format: "%.2f", value))（机动性×\(String(format: "%.2f", pkR.maneuver_factor ?? 1))[\(pkR.maneuver_class ?? "cruise")]）"
            statusTag = "READY"
        } catch {
            distNote = error.localizedDescription
            pkNote = ""
            statusTag = "ERROR"
        }
    }

    func run() async {
        running = true
        statusTag = "COMPUTING"
        statusText = "计算中…"
        defer { running = false }
        do {
            let params: [String: Any] = [
                "nm": Int(Double(nm) ?? 24),
                "vm": Double(vm) ?? 2.6,
                "D": Double(discoveryKm) ?? 120,
                "ni": Int(Double(ni) ?? 16),
                "vi": Double(vi) ?? 3.8,
                "pk": Double(pk) ?? 0.7,
                "tlock": Double(tlock) ?? 6,
                "minr": Double(minr) ?? 3,
            ]
            let r = try await LocalSimulatorEngine.shared.runMissileInterception(payload: [
                "action": "simulate",
                "params": params,
            ])
            guard r.success else {
                throw NSError(domain: "MissileInterception", code: 1, userInfo: [
                    NSLocalizedDescriptionKey: r.error ?? "仿真失败",
                ])
            }
            result = r
            hasResult = true
            resultStale = false
            resultFresh = true
            statusTag = "DONE"
            statusText = "MC N=\(r.final_trials ?? 0)"
        } catch {
            statusTag = "ERROR"
            statusText = error.localizedDescription
            hasResult = false
        }
    }

    func markResultsStale() {
        guard resultFresh else { return }
        resultFresh = false
        resultStale = true
        statusTag = "STALE"
    }

    func hint(for key: String) -> String {
        fieldHints[key] ?? ""
    }

    /// 与 Web field-range 文案对齐的取值范围提示
    func rangeHint(for key: String) -> String {
        guard let spec = fieldRanges[key], let lo = spec.min, let hi = spec.max else { return "" }
        let unit = spec.unit ?? ""
        let unitPart = unit.isEmpty ? "" : " \(unit)"
        return "范围 \(fmtRange(lo))–\(fmtRange(hi))\(unitPart)"
    }

    private func fmtRange(_ value: Double) -> String {
        if value == value.rounded() { return String(Int(value.rounded())) }
        return String(format: "%g", value)
    }
}
