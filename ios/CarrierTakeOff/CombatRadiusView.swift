import SwiftUI

/// 作战半径估算界面：选机加载预计算仪表盘，下方三个按需查询
struct CombatRadiusView: View {
    @StateObject private var vm = CombatRadiusViewModel()

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                header
                Text(vm.statusText)
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundStyle(CombatRadiusTheme.green)

                panel(title: "选择战机", tag: "INPUT") {
                    Text("选择机型后自动填充参数并加载预计算结果。修改任意机型或发动机参数后，点「计算作战半径」按当前参数重算各速度下的整张表（也会在停止输入后自动重算）。")
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundStyle(CombatRadiusTheme.textDim)
                    presetPicker("机型", selection: $vm.selectedTgtId) { vm.applyAircraft() }
                    if let url = vm.loadoutImageUrl {
                        sectionLabel("▸ 外挂挂载示意", color: CombatRadiusTheme.cyan)
                        AsyncImage(url: url) { phase in
                            switch phase {
                            case .success(let image):
                                image
                                    .resizable()
                                    .scaledToFit()
                                    .frame(maxWidth: .infinity)
                                    .background(CombatRadiusTheme.panel2)
                                    .overlay(
                                        RoundedRectangle(cornerRadius: 2)
                                            .stroke(CombatRadiusTheme.line, lineWidth: 1)
                                    )
                            case .failure:
                                Text("挂载图加载失败")
                                    .font(.system(size: 10, design: .monospaced))
                                    .foregroundStyle(CombatRadiusTheme.textDim)
                            default:
                                ProgressView()
                            }
                        }
                    }
                    aircraftEditor(ac: $vm.tgt)
                    field("空重 (kg)", text: $vm.wtEmpty)
                    field("内油 (kg)", text: $vm.wtFuel)
                    field("飞行员数", text: $vm.wtPilots)
                    field("发动机台数", text: $vm.wtEngines)
                    if !vm.showLoadout {
                        field("单枚中距弹 (kg)", text: $vm.wtMissile)
                        field("挂弹数", text: $vm.wtNMissiles)
                    }
                    Toggle("舰载弹射 45 min；垂起与陆基 30 min", isOn: $vm.wtCarrier)
                        .font(.system(size: 12, design: .monospaced))
                        .foregroundStyle(CombatRadiusTheme.text)
                        .tint(CombatRadiusTheme.green)
                        .onChange(of: vm.wtCarrier) { _, _ in vm.scheduleLiveDash() }
                    sectionLabel("▸ 任务剖面", color: CombatRadiusTheme.cyan)
                    HStack(spacing: 8) {
                        ForEach(vm.flightProfileOptions) { opt in
                            Button(opt.label) { vm.setFlightProfile(opt.id) }
                                .buttonStyle(CombatRadiusSegButton(on: vm.flightProfileId == opt.id))
                        }
                    }
                    Text(vm.flightProfileNote)
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundStyle(CombatRadiusTheme.textDim)
                    Toggle(
                        "扣除目标区空战 \(vm.combatToggleMin.formatted()) min 全加力油耗",
                        isOn: Binding(get: { vm.combatAllowanceOn }, set: { vm.setCombatAllowance($0) })
                    )
                        .font(.system(size: 12, design: .monospaced))
                        .foregroundStyle(CombatRadiusTheme.text)
                        .tint(CombatRadiusTheme.green)
                    sectionLabel("▸ 发动机", color: CombatRadiusTheme.amber)
                    enginePresetPicker("发动机预设", selection: $vm.selectedEngineId) {
                        vm.applyEngine()
                        vm.scheduleLiveDash()
                    }
                    field("涵道比 BPR", text: $vm.engBpr)
                    field("总压比 OPR", text: $vm.engOpr)
                    field("涡轮前温度 T4 (K)", text: $vm.engT4)
                    field("海平面军推 (kN)", text: $vm.engTsl)
                    field("海平面加力 (kN)", text: $vm.engMaxTsl)
                    if vm.showF135TsfcToggle {
                        sectionLabel("▸ F135 油耗惩罚", color: CombatRadiusTheme.amber)
                        HStack(spacing: 8) {
                            Button(vm.f135TsfcPublishedLabel) { vm.setF135TsfcMode("published") }
                                .buttonStyle(CombatRadiusSegButton(on: vm.f135TsfcMode == "published"))
                            Button(vm.f135TsfcLpcLabel) { vm.setF135TsfcMode("lpc_only") }
                                .buttonStyle(CombatRadiusSegButton(on: vm.f135TsfcMode == "lpc_only"))
                        }
                        Text(vm.f135TsfcNote)
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundStyle(CombatRadiusTheme.textDim)
                    }
                    Button(vm.running ? "计算中…" : "▶ 计算作战半径") {
                        Task { await vm.requestLiveDash() }
                    }
                    .buttonStyle(CombatRadiusPrimaryButton())
                    .disabled(vm.running)
                }

                if vm.showLoadout {
                    panel(title: "挂载配置", tag: "LOADOUT") {
                        Text("按挂点选择副油箱/弹药；质量与阻力按公开尺寸估算，副油箱燃油并入任务总油。改动后自动按当前挂载重算下方作战半径。")
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundStyle(CombatRadiusTheme.textDim)
                        ForEach(vm.loadoutRows) { row in
                            loadoutPicker(row)
                        }
                        field("挂载干重 (kg)", text: .constant(vm.loadoutPayload.isEmpty ? "—" : vm.loadoutPayload), live: false, readonly: true)
                        field("外挂燃油 (kg)", text: .constant(vm.loadoutExtFuel.isEmpty ? "—" : vm.loadoutExtFuel), live: false, readonly: true)
                    }
                }

                panel(title: "包线与作战半径", tag: "DASHBOARD") {
                    Text(vm.dashSource)
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundStyle(CombatRadiusTheme.textDim)
                    if let lo = vm.dashLoadout {
                        dashLoadoutView(lo)
                    }
                    if let r = vm.dashboard, r.success {
                        dashPanel(r)
                    } else if let r = vm.dashboard, let err = r.error {
                        Text(err)
                            .font(.system(size: 11, design: .monospaced))
                            .foregroundStyle(CombatRadiusTheme.textDim)
                    }
                }

                panel(title: "给定速度 · 搜索最佳升阻比与巡航高度", tag: "SEARCH") {
                    field("马赫数", text: $vm.q1Mach, live: false)
                    Button(vm.running ? "搜索中…" : "▶ 搜索最佳升阻比和巡航高度") {
                        Task { await vm.runSearchCruise() }
                    }
                    .buttonStyle(CombatRadiusPrimaryButton())
                    .disabled(vm.running)
                    if let r = vm.q1Result {
                        if r.feasible == true {
                            HStack(spacing: 10) {
                                stat("最佳 L/D", value: String(format: "%.3f", r.ld ?? 0))
                                stat("最大 L/D", value: String(format: "%.3f", r.max_ld ?? r.ld ?? 0))
                                stat("高度", value: String(format: "%.1f km", (r.alt_m ?? 0) / 1000), amber: true)
                            }
                            HStack(spacing: 10) {
                                stat("最大可用推力", value: String(format: "%.1f kN", r.thrust_avail_kN ?? 0))
                                stat("负载", value: String(format: "%.1f%%", (r.load ?? 0) * 100))
                            }
                            HStack(spacing: 10) {
                                stat("热效率", value: String(format: "%.1f%%", (r.eta_th ?? 0) * 100))
                                stat("推进效率", value: String(format: "%.1f%%", (r.eta_p ?? 0) * 100))
                                stat("总效率", value: String(format: "%.1f%%", (r.eta_o ?? 0) * 100))
                            }
                            altitudeScanTable(r.altitude_scan)
                        } else if let maxLd = r.max_ld {
                            HStack(spacing: 10) {
                                stat("最大 L/D", value: String(format: "%.3f", maxLd))
                                stat("高度", value: String(format: "%.1f km", (r.max_ld_alt_m ?? 0) / 1000), amber: true)
                            }
                            Text(r.fail_reason ?? "无可行巡航高度")
                                .font(.system(size: 11, design: .monospaced))
                                .foregroundStyle(CombatRadiusTheme.textDim)
                            altitudeScanTable(r.altitude_scan)
                        } else {
                            Text(r.fail_reason ?? "无可行高度")
                                .font(.system(size: 11, design: .monospaced))
                                .foregroundStyle(CombatRadiusTheme.textDim)
                            altitudeScanTable(r.altitude_scan)
                        }
                    }
                }

                panel(title: "给定速度与高度", tag: "POINT") {
                    field("马赫数", text: $vm.q2Mach, live: false)
                    field("高度 (m)", text: $vm.q2Alt, live: false)
                    Button(vm.running ? "计算中…" : "▶ 计算该点升阻比与效率") {
                        Task { await vm.runPoint() }
                    }
                    .buttonStyle(CombatRadiusPrimaryButton())
                    .disabled(vm.running)
                    if let r = vm.q2Result, r.success {
                        HStack(spacing: 10) {
                            stat("升阻比", value: String(format: "%.3f", r.ld ?? 0))
                            stat("最大可用推力", value: String(format: "%.1f kN", r.thrust_avail_kN ?? 0), amber: true)
                        }
                        HStack(spacing: 10) {
                            stat("负载", value: String(format: "%.1f%%", (r.load ?? 0) * 100))
                            stat("总效率", value: String(format: "%.1f%%", (r.eta_o ?? 0) * 100))
                        }
                        HStack(spacing: 10) {
                            stat("热效率", value: String(format: "%.1f%%", (r.eta_th ?? 0) * 100))
                            stat("推进效率", value: String(format: "%.1f%%", (r.eta_p ?? 0) * 100))
                        }
                    }
                }

                panel(title: "给定速度、高度、负载 · 发动机效率", tag: "ENGINE") {
                    field("马赫数", text: $vm.q3Mach, live: false)
                    field("高度 (m)", text: $vm.q3Alt, live: false)
                    field("负载", text: $vm.q3Load, live: false)
                    Button(vm.running ? "计算中…" : "▶ 计算发动机热/推进/总效率") {
                        Task { await vm.runEngineCycle() }
                    }
                    .buttonStyle(CombatRadiusPrimaryButton())
                    .disabled(vm.running)
                    if let r = vm.q3Result, r.success {
                        HStack(spacing: 10) {
                            stat("热效率", value: String(format: "%.1f%%", (r.eta_th ?? 0) * 100))
                            stat("推进效率", value: String(format: "%.1f%%", (r.eta_p ?? 0) * 100), amber: true)
                            stat("总效率", value: String(format: "%.1f%%", (r.eta_o ?? 0) * 100))
                        }
                    }
                }
            }
            .padding(14)
        }
        .background(CombatRadiusTheme.bg.ignoresSafeArea())
        .navigationBarTitleDisplayMode(.inline)
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("飞机作战半径估算终端")
                .font(.system(size: 14, weight: .bold, design: .monospaced))
                .foregroundStyle(CombatRadiusTheme.green)
            Text("COMBAT RADIUS · PRECOMPUTED DASHBOARD")
                .font(.system(size: 10, design: .monospaced))
                .foregroundStyle(CombatRadiusTheme.textDim)
        }
    }

    @ViewBuilder
    private func aircraftEditor(ac: Binding<CombatRadiusAircraftInput>) -> some View {
        field("展弦比 AR（计算）", text: ac.ar, readonly: true)
        field("前缘后掠角 (°)", text: ac.sweepDeg)
        if ac.planform.wrappedValue == "double_delta" {
            field("内段前缘后掠 (°)", text: ac.sweepInnerDeg)
            field("外段前缘后掠 (°)", text: ac.sweepOuterDeg)
        }
        field("翼载荷 (t/m² · 计算)", text: ac.wingLoading, readonly: true)
        field("厚弦比 tc", text: ac.tc)
        field("翼面积 (m²)", text: ac.wingAreaM2)
        field("马赫角 (°)", text: ac.machAngleDeg)
        field("机身长度 (m)", text: ac.lengthM)
        field("翼展 (m)", text: ac.wingspanM)
        field("机身宽 (m)", text: ac.fuseWidthM)
        field("机身高 (m)", text: ac.fuseHeightM)
        field("机头锥长度 (m)", text: ac.noseConeLengthM)
        field("机头锥直径 (m)", text: ac.noseConeDiameterM)
        field("机头长度 (m)", text: ac.noseLengthM)
        field("机头根部直径 (m)", text: ac.noseRootDiameterM)
        field("机身盒段长度 (m)", text: ac.fuseBodyLengthM)
        field("主翼面积（单面）(m²)", text: ac.mainWingAreaM2)
        field("平尾/鸭翼面积（单面）(m²)", text: ac.canardHtailAreaM2)
        field("垂尾面积（单面）(m²)", text: ac.vtailAreaM2)
        field("腹鳍面积（单面）(m²)", text: ac.ventralFinAreaM2)
        pickerRow("翼型", selection: ac.planform, options: vm.planformOptions)
        pickerRow("布局", selection: ac.layout, options: vm.layoutOptions)
        pickerRow("进气道", selection: ac.inlet, options: vm.inletOptions)
        if !vm.showLoadout {
            pickerRow("挂装方式", selection: ac.storeMount, options: vm.storeMountOptions)
        }
        Toggle("表面不平整（摩擦+形状阻力）", isOn: ac.rough)
            .font(.system(size: 12, design: .monospaced))
            .foregroundStyle(CombatRadiusTheme.text)
            .tint(CombatRadiusTheme.amber)
    }

    /// 包线与作战半径：当前挂载与总挂载重量
    private func dashLoadoutView(_ lo: CombatRadiusViewModel.DashLoadoutState) -> some View {
        let items = lo.items.isEmpty
            ? "空挂（无外挂）"
            : lo.items.map { it in
                let unit = it.unitKg.map { String(format: "（单件 %.0f kg）", $0) } ?? ""
                return String(format: "%@ ×%.0f%@", it.name, it.count, unit)
            }.joined(separator: " · ")
        let split = lo.fuelKg > 0
            ? String(format: "挂载干重 %.0f kg + 外挂燃油 %.0f kg", lo.dryKg, lo.fuelKg)
            : String(format: "挂载干重 %.0f kg · 无外挂燃油", lo.dryKg)
        return VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .firstTextBaseline) {
                Text("当前挂载 · 总挂载重量")
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(CombatRadiusTheme.textDim)
                Spacer()
                Text(String(format: "%.0f kg", lo.totalKg))
                    .font(.system(size: 18, design: .monospaced))
                    .foregroundStyle(CombatRadiusTheme.amber)
            }
            Text(split)
                .font(.system(size: 11, design: .monospaced))
                .foregroundStyle(CombatRadiusTheme.textDim)
            Text(items)
                .font(.system(size: 11, design: .monospaced))
                .foregroundStyle(CombatRadiusTheme.cyan)
            if !lo.note.isEmpty {
                Text(lo.note)
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(CombatRadiusTheme.textDim)
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(CombatRadiusTheme.panel2)
        .overlay(
            RoundedRectangle(cornerRadius: 2)
                .stroke(CombatRadiusTheme.line, lineWidth: 1)
        )
    }

    private func dashPanel(_ r: CombatRadiusResult) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 10) {
                stat("实用最大巡航速度", value: r.max_cruise_mach.map { String(format: "Ma %.3f", $0) } ?? "—", amber: true)
                stat("最大巡航速度", value: r.max_possible_cruise_mach.map { String(format: "Ma %.3f", $0) } ?? "—")
                let vmax = r.max_speed?.feasible == true
                    ? r.max_speed?.max_speed_kmh.map { String(format: "%.0f km/h", $0) } ?? "—"
                    : (r.max_speed?.fail_reason ?? "—")
                stat("极速", value: vmax)
            }
            if let en = r.endurance, en.feasible == true {
                let rows: [(String, CombatRadiusEnduranceSummary, Bool)] = {
                    if let v = en.variants {
                        var out: [(String, CombatRadiusEnduranceSummary, Bool)] = []
                        if let c = v["carrier"], c.feasible == true {
                            out.append(("舰载待战续航（45 min 余油）", c, en.scenario == "carrier"))
                        }
                        if let l = v["land"], l.feasible == true {
                            out.append(("陆基待战续航（30 min·MTOW 满油）", l, en.scenario == "land"))
                        }
                        return out
                    }
                    return [("待战续航（最小流量速度）", en, true)]
                }()
                ForEach(Array(rows.enumerated()), id: \.offset) { _, item in
                    let block = item.1
                    if let hours = block.endurance_h {
                        let mach = block.mach.map { String(format: "Ma %.3f", $0) } ?? "—"
                        let alt = block.alt_m.map { String(format: "%.1f km", $0 / 1000) } ?? "—"
                        let spd = block.speed_kmh.map { String(format: "%.0f km/h", $0) } ?? "—"
                        let flow = block.fuel_flow_kg_h.map { String(format: "%.0f kg/h", $0) } ?? "—"
                        let fuel = block.internal_fuel_kg.map { String(format: "油 %.0f kg", $0) } ?? ""
                        stat(
                            item.0,
                            value: String(format: "%.1f h", hours),
                            sub: [mach, alt, spd, flow, fuel].filter { !$0.isEmpty }.joined(separator: " · "),
                            amber: item.2
                        )
                    }
                }
            }
            ForEach(r.points ?? []) { p in
                HStack {
                    Text(cruiseSpeedLabel(p))
                        .foregroundStyle(CombatRadiusTheme.green)
                    Spacer()
                    let maxLd = p.max_ld.map { String(format: " L/Dmax %.2f", $0) } ?? ""
                    if p.endurance_h != nil, p.radius_km == nil, let hours = p.endurance_h {
                        Text(String(format: "%.1f h 待战%@", hours, maxLd))
                            .foregroundStyle(CombatRadiusTheme.amber)
                    } else if p.feasible == true, let km = p.radius_km {
                        let mixed: String = {
                            if let m = p.mach, m > 1, let mix = p.mixed_radius_km {
                                return String(format: " 混合 %.0f km", mix)
                            }
                            if let m = p.mach, m > 1 {
                                return " 混合 —"
                            }
                            return " 混合不适用"
                        }()
                        Text(String(format: "%.0f km%@%@", km, mixed, maxLd))
                            .foregroundStyle(CombatRadiusTheme.text)
                    } else {
                        Text((p.fail_reason ?? "无 92% 裕度高度") + maxLd)
                            .foregroundStyle(CombatRadiusTheme.textDim)
                    }
                }
                .font(.system(size: 11, design: .monospaced))
            }
            Text("表尾「实用最大巡航速度」在 Ma 1.2 以上取最佳巡航高度达到最大值时的速度；「最大巡航速度」允许掉到 11 km。若与 Ma 1.2 以上作战半径最大的马赫不同，再插一行「最大半径超音速巡航速度」。最佳巡航高度使升阻比×总效率最大。最大 L/D 为可飞高度（军推优先，不足则加力）中升阻比最大的点；加力可飞按全部加力，高度可到海平面。极速按阻力等于全部加力（不留巡航裕度）；超过超巡带后附加体积波阻，避免光滑隐身机靠降高把极速估高。混合作战半径仅超音速：去程该马赫、返程 Ma 0.8。")
                .font(.system(size: 10, design: .monospaced))
                .foregroundStyle(CombatRadiusTheme.textDim)
            if let abRows = r.afterburner_best_altitude, !abRows.isEmpty {
                Text("最大加力推力下各速度最佳高度与作战半径")
                    .font(.system(size: 12, weight: .bold, design: .monospaced))
                    .foregroundStyle(CombatRadiusTheme.amber)
                ForEach(abRows) { p in
                    HStack {
                        Text(p.mach.map { String(format: "Ma %.3f", $0) } ?? "—")
                            .foregroundStyle(CombatRadiusTheme.green)
                        Spacer()
                        if p.feasible == true, let km = p.radius_km {
                            let alt = (p.alt_m ?? 0) / 1000
                            let mode = p.reheat == true ? "加力" : "军推"
                            Text(String(format: "%@ %.1f km · %.0f km", mode, alt, km))
                                .foregroundStyle(CombatRadiusTheme.text)
                        } else {
                            Text("不可飞")
                                .foregroundStyle(CombatRadiusTheme.textDim)
                        }
                    }
                    .font(.system(size: 11, design: .monospaced))
                }
                Text("高度与极速同一包线，可到海平面。阻力不超过军推时不开加力；超过军推才按加力燃油（全加力 TSFC 约为军推最大点的 2.2 倍）。")
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(CombatRadiusTheme.textDim)
            }
        }
    }

    /// 分速表第一列：固定马赫只写数字，表尾命名行写中文名称加马赫。
    private func cruiseSpeedLabel(_ p: CombatRadiusCruisePoint) -> String {
        let name = p.label.isEmpty
            ? (p.mach.map { String(format: "Ma %.3f", $0) } ?? "—")
            : p.label
        let named = p.id == "max_cruise" || p.id == "max_possible_cruise" || p.id == "max_radius_cruise"
        if named, let mach = p.mach {
            return String(format: "%@ %.3f", name, mach)
        }
        if let mach = p.mach, !named {
            return String(format: "%.3f", mach)
        }
        return name
    }

    /// 给定速度搜索：各高度升阻比、推力、负载与效率表。
    @ViewBuilder
    private func altitudeScanTable(_ scan: [CombatRadiusAltitudeScanPoint]?) -> some View {
        if let scan, !scan.isEmpty {
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 6) {
                    Text("高度km").frame(maxWidth: .infinity, alignment: .leading)
                    Text("升阻比").frame(maxWidth: .infinity, alignment: .trailing)
                    Text("推力kN").frame(maxWidth: .infinity, alignment: .trailing)
                    Text("负载").frame(maxWidth: .infinity, alignment: .trailing)
                    Text("热效率").frame(maxWidth: .infinity, alignment: .trailing)
                    Text("推进效率").frame(maxWidth: .infinity, alignment: .trailing)
                    Text("总效率").frame(maxWidth: .infinity, alignment: .trailing)
                }
                .font(.system(size: 9, design: .monospaced))
                .foregroundStyle(CombatRadiusTheme.textDim)
                ForEach(scan) { p in
                    let best = p.selected == true
                    let dim = p.feasible != true
                    HStack(spacing: 6) {
                        Text(String(format: "%.1f", p.alt_m / 1000))
                            .frame(maxWidth: .infinity, alignment: .leading)
                        Text(String(format: "%.2f", p.ld ?? 0))
                            .frame(maxWidth: .infinity, alignment: .trailing)
                        Text(String(format: "%.1f", p.thrust_avail_kN ?? 0))
                            .frame(maxWidth: .infinity, alignment: .trailing)
                        Text(String(format: "%.1f%%", (p.load ?? 0) * 100))
                            .frame(maxWidth: .infinity, alignment: .trailing)
                        Text(String(format: "%.1f%%", (p.eta_th ?? 0) * 100))
                            .frame(maxWidth: .infinity, alignment: .trailing)
                        Text(String(format: "%.1f%%", (p.eta_p ?? 0) * 100))
                            .frame(maxWidth: .infinity, alignment: .trailing)
                        Text(String(format: "%.1f%%", (p.eta_o ?? 0) * 100))
                            .frame(maxWidth: .infinity, alignment: .trailing)
                    }
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(best ? CombatRadiusTheme.green : (dim ? CombatRadiusTheme.textDim : CombatRadiusTheme.text))
                }
                Text("绿行是该速度下升阻比×总效率最大的高度；灰行不满足 92% 军推裕度。")
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(CombatRadiusTheme.textDim)
            }
            .padding(.top, 6)
        }
    }

    private func stat(_ k: String, value: String, sub: String = "", amber: Bool = false) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(k)
                .font(.system(size: 9, design: .monospaced))
                .foregroundStyle(CombatRadiusTheme.textDim)
            Text(value)
                .font(.system(size: 18, design: .monospaced))
                .foregroundStyle(amber ? CombatRadiusTheme.amber : CombatRadiusTheme.green)
            if !sub.isEmpty {
                Text(sub)
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(CombatRadiusTheme.textDim)
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(CombatRadiusTheme.panel2)
        .overlay(Rectangle().stroke(CombatRadiusTheme.line, lineWidth: 1))
    }

    private func panel<Content: View>(title: String, tag: String = "L/D", @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text(title.uppercased())
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(CombatRadiusTheme.textDim)
                Spacer()
                Text(tag)
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(CombatRadiusTheme.green)
            }
            content()
        }
        .padding(14)
        .background(CombatRadiusTheme.panel)
        .overlay(Rectangle().stroke(CombatRadiusTheme.line, lineWidth: 1))
    }

    private func sectionLabel(_ text: String, color: Color) -> some View {
        Text(text)
            .font(.system(size: 10, design: .monospaced))
            .foregroundStyle(color)
            .padding(.top, 6)
    }

    private func field(_ label: String, text: Binding<String>, live: Bool = true, readonly: Bool = false) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label)
                .font(.system(size: 11, design: .monospaced))
                .foregroundStyle(CombatRadiusTheme.textDim)
            if readonly {
                Text(text.wrappedValue.isEmpty ? "—" : text.wrappedValue)
                    .font(.system(size: 13, design: .monospaced))
                    .foregroundStyle(CombatRadiusTheme.cyan)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(8)
                    .background(CombatRadiusTheme.panel)
                    .overlay(Rectangle().stroke(CombatRadiusTheme.line, lineWidth: 1))
            } else {
                TextField("", text: text)
                    .textFieldStyle(.plain)
                    .font(.system(size: 13, design: .monospaced))
                    .foregroundStyle(CombatRadiusTheme.text)
                    .padding(8)
                    .background(CombatRadiusTheme.panel2)
                    .overlay(Rectangle().stroke(CombatRadiusTheme.line, lineWidth: 1))
                    .onChange(of: text.wrappedValue) { _, _ in
                        if live { vm.scheduleLiveDash() }
                    }
            }
        }
    }

    private func presetPicker(_ label: String, selection: Binding<String>, onChange: @escaping () -> Void) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label)
                .font(.system(size: 11, design: .monospaced))
                .foregroundStyle(CombatRadiusTheme.textDim)
            Picker(label, selection: selection) {
                Text("— 选择战机 —").tag("")
                ForEach(vm.presets) { p in
                    Text(p.selectLabel).tag(p.id)
                }
            }
            .pickerStyle(.menu)
            .tint(CombatRadiusTheme.cyan)
            .onChange(of: selection.wrappedValue) { _, _ in onChange() }
        }
    }

    private func enginePresetPicker(_ label: String, selection: Binding<String>, onChange: @escaping () -> Void) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label)
                .font(.system(size: 11, design: .monospaced))
                .foregroundStyle(CombatRadiusTheme.textDim)
            Picker(label, selection: selection) {
                Text("— 自定义 —").tag("")
                ForEach(vm.enginePresets) { p in
                    Text(p.name).tag(p.id)
                }
            }
            .pickerStyle(.menu)
            .tint(CombatRadiusTheme.cyan)
            .onChange(of: selection.wrappedValue) { _, _ in onChange() }
        }
    }

    private func pickerRow(_ label: String, selection: Binding<String>, options: [(String, String)]) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label)
                .font(.system(size: 11, design: .monospaced))
                .foregroundStyle(CombatRadiusTheme.textDim)
            Picker(label, selection: selection) {
                ForEach(options, id: \.0) { id, name in
                    Text(name).tag(id)
                }
            }
            .pickerStyle(.menu)
            .tint(CombatRadiusTheme.cyan)
            .onChange(of: selection.wrappedValue) { _, _ in vm.scheduleLiveDash() }
        }
    }

    private func loadoutPicker(_ row: CombatRadiusViewModel.LoadoutStationRow) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(row.label)
                .font(.system(size: 11, design: .monospaced))
                .foregroundStyle(CombatRadiusTheme.textDim)
            Picker(row.label, selection: Binding(
                get: { vm.loadoutSelection[row.id] ?? "" },
                set: { vm.setLoadout(stationId: row.id, key: $0) }
            )) {
                ForEach(row.options, id: \.key) { opt in
                    Text(opt.label ?? opt.key).tag(opt.key)
                }
            }
            .pickerStyle(.menu)
            .tint(CombatRadiusTheme.cyan)
        }
    }
}

private struct CombatRadiusSegButton: ButtonStyle {
    var on: Bool
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 12, design: .monospaced))
            .frame(maxWidth: .infinity)
            .padding(8)
            .background(on ? Color(hex: 0x1A1408) : CombatRadiusTheme.panel2)
            .foregroundStyle(on ? CombatRadiusTheme.amber : CombatRadiusTheme.textDim)
            .overlay(Rectangle().stroke(on ? CombatRadiusTheme.amber : CombatRadiusTheme.line, lineWidth: 1))
            .opacity(configuration.isPressed ? 0.85 : 1)
    }
}

private struct CombatRadiusPrimaryButton: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 13, weight: .bold, design: .monospaced))
            .frame(maxWidth: .infinity)
            .padding(11)
            .background(CombatRadiusTheme.green)
            .foregroundStyle(Color(hex: 0x042014))
            .opacity(configuration.isPressed ? 0.85 : 1)
    }
}
