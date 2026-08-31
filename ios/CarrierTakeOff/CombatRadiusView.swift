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
                    Text("选择机型后自动填充参数并加载预计算结果，无需再点按钮。修改参数后会自动重算。")
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundStyle(CombatRadiusTheme.textDim)
                    presetPicker("机型", selection: $vm.selectedTgtId) { vm.applyAircraft() }
                    aircraftEditor(ac: $vm.tgt)
                    field("空重 (kg)", text: $vm.wtEmpty)
                    field("内油 (kg)", text: $vm.wtFuel)
                    field("飞行员数", text: $vm.wtPilots)
                    field("单枚中距弹 (kg)", text: $vm.wtMissile)
                    field("挂弹数", text: $vm.wtNMissiles)
                    field("发动机台数", text: $vm.wtEngines)
                    Toggle("舰载机（降落冗余 40 min / 陆基 30 min）", isOn: $vm.wtCarrier)
                        .font(.system(size: 12, design: .monospaced))
                        .foregroundStyle(CombatRadiusTheme.text)
                        .tint(CombatRadiusTheme.green)
                        .onChange(of: vm.wtCarrier) { _, _ in vm.scheduleLiveDash() }
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
                }

                panel(title: "包线与作战半径", tag: "DASHBOARD") {
                    Text(vm.dashSource)
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundStyle(CombatRadiusTheme.textDim)
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
                            }
                        } else if let maxLd = r.max_ld {
                            HStack(spacing: 10) {
                                stat("最大 L/D", value: String(format: "%.3f", maxLd))
                                stat("高度", value: String(format: "%.1f km", (r.max_ld_alt_m ?? 0) / 1000), amber: true)
                            }
                            Text(r.fail_reason ?? "无可行巡航高度")
                                .font(.system(size: 11, design: .monospaced))
                                .foregroundStyle(CombatRadiusTheme.textDim)
                        } else {
                            Text(r.fail_reason ?? "无可行高度")
                                .font(.system(size: 11, design: .monospaced))
                                .foregroundStyle(CombatRadiusTheme.textDim)
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
        field("展弦比 AR", text: ac.ar)
        field("前缘后掠角 (°)", text: ac.sweepDeg)
        if ac.planform.wrappedValue == "double_delta" {
            field("内段前缘后掠 (°)", text: ac.sweepInnerDeg)
            field("外段前缘后掠 (°)", text: ac.sweepOuterDeg)
        }
        field("翼载荷 (t/m²)", text: ac.wingLoading)
        field("厚弦比 tc", text: ac.tc)
        field("翼面积 (m²)", text: ac.wingAreaM2)
        field("马赫角 (°)", text: ac.machAngleDeg)
        field("机身长度 (m)", text: ac.lengthM)
        field("翼展 (m)", text: ac.wingspanM)
        pickerRow("翼型", selection: ac.planform, options: vm.planformOptions)
        pickerRow("布局", selection: ac.layout, options: vm.layoutOptions)
        pickerRow("进气道", selection: ac.inlet, options: vm.inletOptions)
        Toggle("翼身融合", isOn: ac.bwb)
            .font(.system(size: 12, design: .monospaced))
            .foregroundStyle(CombatRadiusTheme.text)
            .tint(CombatRadiusTheme.green)
        Toggle("表面不平整", isOn: ac.rough)
            .font(.system(size: 12, design: .monospaced))
            .foregroundStyle(CombatRadiusTheme.text)
            .tint(CombatRadiusTheme.amber)
    }

    private func dashPanel(_ r: CombatRadiusResult) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 10) {
                stat("实用最大巡航速度", value: r.max_cruise_mach.map { String(format: "Ma %.3f", $0) } ?? "—", amber: true)
                stat("最大巡航速度", value: r.max_cruise_floor_mach.map { String(format: "Ma %.3f", $0) } ?? "—")
                let vmax = r.max_speed?.feasible == true
                    ? r.max_speed?.max_speed_kmh.map { String(format: "%.0f km/h", $0) } ?? "—"
                    : (r.max_speed?.fail_reason ?? "—")
                stat("极速", value: vmax)
            }
            ForEach(r.points ?? []) { p in
                HStack {
                    Text(cruiseSpeedLabel(p))
                        .foregroundStyle(CombatRadiusTheme.green)
                    Spacer()
                    let maxLd = p.max_ld.map { String(format: " L/Dmax %.2f", $0) } ?? ""
                    if p.feasible == true, let km = p.radius_km {
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
            Text("表尾「实用最大巡航速度」是最佳巡航高度尚未从峰值回落时的上限；「最大巡航速度」允许掉到 11 km。最佳巡航高度使升阻比×总效率最大。最大 L/D 为可飞高度（军推优先，不足则加力）中升阻比最大的点；加力可飞按全部加力，高度可到海平面。极速按阻力等于全部加力（不留巡航裕度）。混合作战半径仅超音速：去程该马赫、返程 Ma 0.8。")
                .font(.system(size: 10, design: .monospaced))
                .foregroundStyle(CombatRadiusTheme.textDim)
        }
    }

    /// 分速表第一列：固定马赫只写数字，表尾两行写中文名称加马赫。
    private func cruiseSpeedLabel(_ p: CombatRadiusCruisePoint) -> String {
        let name = p.label.isEmpty
            ? (p.mach.map { String(format: "Ma %.3f", $0) } ?? "—")
            : p.label
        if (p.id == "max_cruise" || p.id == "floor_max_cruise"), let mach = p.mach {
            return String(format: "%@ %.3f", name, mach)
        }
        if let mach = p.mach, p.id != "max_cruise", p.id != "floor_max_cruise" {
            return String(format: "%.3f", mach)
        }
        return name
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

    private func field(_ label: String, text: Binding<String>, live: Bool = true) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label)
                .font(.system(size: 11, design: .monospaced))
                .foregroundStyle(CombatRadiusTheme.textDim)
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

    private func presetPicker(_ label: String, selection: Binding<String>, onChange: @escaping () -> Void) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label)
                .font(.system(size: 11, design: .monospaced))
                .foregroundStyle(CombatRadiusTheme.textDim)
            Picker(label, selection: selection) {
                Text("— 选择战机 —").tag("")
                ForEach(vm.presets) { p in
                    Text(p.name).tag(p.id)
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
