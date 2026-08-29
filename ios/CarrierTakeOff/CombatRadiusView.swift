import SwiftUI

/// 作战半径估算界面（升阻比 + 军推，战术终端风格）
struct CombatRadiusView: View {
    @StateObject private var vm = CombatRadiusViewModel()

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                header
                Text(vm.statusText)
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundStyle(CombatRadiusTheme.green)

                panel(title: "1. 升阻比估算") {
                    Text("用两架已知巡航 L/D 的锚点标定 (Cf0, k_e)，再估算第三型机。ISA 11–20 km。")
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundStyle(CombatRadiusTheme.textDim)

                    sectionLabel("▸ 锚点 1", color: CombatRadiusTheme.cyan)
                    presetPicker("机型预设", selection: $vm.selectedA1Id) { vm.applyA1() }
                    field("已知巡航 L/D", text: $vm.a1Ld)
                    aircraftEditor(ac: $vm.a1)

                    sectionLabel("▸ 锚点 2", color: CombatRadiusTheme.amber)
                    presetPicker("机型预设", selection: $vm.selectedA2Id) { vm.applyA2() }
                    field("已知巡航 L/D", text: $vm.a2Ld)
                    aircraftEditor(ac: $vm.a2)

                    sectionLabel("▸ 待估机型", color: CombatRadiusTheme.green)
                    presetPicker("机型预设", selection: $vm.selectedTgtId) { vm.applyTgt() }
                    aircraftEditor(ac: $vm.tgt)

                    Button(vm.running ? "计算中…" : "▶ 估算升阻比") {
                        Task { await vm.run() }
                    }
                    .buttonStyle(CombatRadiusPrimaryButton())
                    .disabled(vm.running)
                }

                panel(title: "2. 军推估算", tag: "THRUST") {
                    Text("理想 Brayton 双涵道循环：T4 全包线保持，海平面静止军推反标定换算流量。概念设计级估算。")
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundStyle(CombatRadiusTheme.textDim)

                    enginePresetPicker("发动机预设", selection: $vm.selectedEngineId) { vm.applyEngine() }
                    field("涵道比 BPR", text: $vm.engBpr)
                    field("总压比 OPR", text: $vm.engOpr)
                    field("涡轮前温度 T4 (K)", text: $vm.engT4)
                    field("海平面军推 (kN)", text: $vm.engTsl)
                    field("高度 (m)", text: $vm.engAlt)
                    field("马赫数", text: $vm.engMach)
                    field("压气机效率 η_c", text: $vm.engEta)
                    field("风扇压比（可空）", text: $vm.engFanPr)

                    Button(vm.running ? "计算中…" : "▶ 估算可用军推") {
                        Task { await vm.runThrust() }
                    }
                    .buttonStyle(CombatRadiusPrimaryButton())
                    .disabled(vm.running)
                }

                panel(title: "3. 负载与巡航效率", tag: "TSFC") {
                    Text("空战重量 = 空重 + 一半内油 + 飞行员×0.1 t + 4 枚中距弹。D=W/(L/D)，负载=D/可用军推。巡航点用第 2 栏高度/马赫。")
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundStyle(CombatRadiusTheme.textDim)
                    field("空重 (kg)", text: $vm.wtEmpty)
                    field("内油 (kg)", text: $vm.wtFuel)
                    field("飞行员数", text: $vm.wtPilots)
                    field("单枚中距弹 (kg)", text: $vm.wtMissile)
                    field("挂弹数", text: $vm.wtNMissiles)
                    field("发动机台数", text: $vm.wtEngines)
                    field("部件效率 ε", text: $vm.effEps)
                    field("喷管效率 η_n", text: $vm.effEtan)
                    field("附件功提取比例", text: $vm.effAcc)
                    Button(vm.running ? "计算中…" : "▶ 估算负载与 TSFC") {
                        Task { await vm.runEfficiency() }
                    }
                    .buttonStyle(CombatRadiusPrimaryButton())
                    .disabled(vm.running)
                }

                panel(title: "4. 作战半径", tag: "RANGE") {
                    Text("搜索 L/D×η_o 最大且阻力 ≤ 军推 92% 的高度，布雷盖平飞估算。自动给出 Ma 0.8 / 1.5 / 1.76 与最大巡航马赫。马赫角优先用预设度数。不计爬升下降余油。")
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundStyle(CombatRadiusTheme.textDim)
                    Button(vm.running ? "计算中…" : "▶ 估算作战半径") {
                        Task { await vm.runRadius() }
                    }
                    .buttonStyle(CombatRadiusPrimaryButton())
                    .disabled(vm.running)
                }

                if let r = vm.result, r.success {
                    resultsPanel(r)
                }
                if let r = vm.thrustResult, r.success {
                    thrustResultsPanel(r)
                }
                if let r = vm.efficiencyResult, r.success {
                    efficiencyResultsPanel(r)
                }
                if let r = vm.radiusResult, r.success {
                    radiusResultsPanel(r)
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
            Text("COMBAT RADIUS · L/D + THRUST + TSFC + BREGUET")
                .font(.system(size: 10, design: .monospaced))
                .foregroundStyle(CombatRadiusTheme.textDim)
        }
    }

    @ViewBuilder
    private func aircraftEditor(ac: Binding<CombatRadiusAircraftInput>) -> some View {
        field("展弦比 AR", text: ac.ar)
        field("前缘后掠角 (°)", text: ac.sweepDeg)
        field("翼载荷 (t/m²)", text: ac.wingLoading)
        field("厚弦比 tc", text: ac.tc)
        field("翼面积 (m²)", text: ac.wingAreaM2)
        field("马赫角 (°)", text: ac.machAngleDeg)
        field("机身长度 (m)", text: ac.lengthM)
        field("翼展 (m)", text: ac.wingspanM)
        field("马赫数", text: ac.mach)
        field("高度 (m)", text: ac.altM)
        pickerRow("翼型", selection: ac.planform, options: vm.planformOptions)
        pickerRow("布局", selection: ac.layout, options: vm.layoutOptions)
        Toggle("翼身融合", isOn: ac.bwb)
            .font(.system(size: 12, design: .monospaced))
            .foregroundStyle(CombatRadiusTheme.text)
            .tint(CombatRadiusTheme.green)
        Toggle("表面不平整", isOn: ac.rough)
            .font(.system(size: 12, design: .monospaced))
            .foregroundStyle(CombatRadiusTheme.text)
            .tint(CombatRadiusTheme.amber)
    }

    private func resultsPanel(_ r: CombatRadiusResult) -> some View {
        panel(title: "升阻比输出", tag: "OUTPUT") {
            HStack(spacing: 10) {
                stat("待估 L/D", value: String(format: "%.4f", r.target?.ld ?? 0), sub: r.target?.name ?? "")
                stat("Cf0", value: String(format: "%.6f", r.Cf0 ?? 0), amber: true)
                stat("k_e", value: String(format: "%.6f", r.k_e ?? 0), amber: true)
            }
            let rows = (r.anchors ?? []) + (r.target.map { [$0] } ?? [])
            ForEach(Array(rows.enumerated()), id: \.offset) { idx, row in
                HStack {
                    Text(row.name)
                        .foregroundStyle(idx == rows.count - 1 ? CombatRadiusTheme.green : CombatRadiusTheme.text)
                    Spacer()
                    Text(String(format: "L/D %.4f", row.ld))
                        .foregroundStyle(idx == rows.count - 1 ? CombatRadiusTheme.green : CombatRadiusTheme.text)
                }
                .font(.system(size: 11, design: .monospaced))
            }
        }
    }

    private func thrustResultsPanel(_ r: CombatRadiusResult) -> some View {
        panel(title: "军推输出", tag: "THRUST") {
            HStack(spacing: 10) {
                stat("可用军推", value: String(format: "%.1f kN", r.thrust_kN ?? 0), sub: String(format: "%.2f 吨力", r.thrust_tf ?? 0))
                stat("推力衰减 α", value: String(format: "%.3f", r.alpha ?? 0), amber: true)
            }
            HStack(spacing: 10) {
                stat("质量流比", value: String(format: "%.3f", r.mdot_ratio ?? 0))
                stat("风扇压比", value: String(format: "%.2f", r.fan_pr ?? 0))
            }
            Text(String(format: "来流总温比 τr=%.3f · 大气 %.1f K / %.1f kPa。α = T_flight / T_SL。", r.tau_r ?? 0, r.T0 ?? 0, (r.P0 ?? 0) / 1000))
                .font(.system(size: 10, design: .monospaced))
                .foregroundStyle(CombatRadiusTheme.textDim)
        }
    }

    private func efficiencyResultsPanel(_ r: CombatRadiusResult) -> some View {
        panel(title: "效率 / TSFC 输出", tag: "TSFC") {
            HStack(spacing: 10) {
                stat("负载比", value: String(format: "%.1f%%", (r.load ?? 0) * 100), sub: String(format: "原始 %.1f%%", (r.load_raw ?? 0) * 100), amber: true)
                stat("总效率 η_o", value: String(format: "%.1f%%", (r.eta_o ?? 0) * 100), sub: String(format: "热 %.1f%% · 推进 %.1f%%", (r.eta_th ?? 0) * 100, (r.eta_p ?? 0) * 100))
            }
            HStack(spacing: 10) {
                stat("TSFC", value: r.tsfc_mg_n_s.map { String(format: "%.2f mg/(N·s)", $0) } ?? "—", sub: r.tsfc_lb_lbf_h.map { String(format: "%.3f lb/(lbf·h)", $0) } ?? "")
                stat("反解 T4", value: String(format: "%.0f K", r.T4_solved ?? 0))
            }
            Text(String(format: "空战重量 %.0f kg · 阻力 %.2f kN · 可用军推 %.1f kN（%d 发）· L/D %.3f。", r.mass_kg ?? 0, r.drag_kN ?? 0, r.thrust_avail_kN ?? 0, r.n_engines ?? 1, r.ld ?? 0))
                .font(.system(size: 10, design: .monospaced))
                .foregroundStyle(CombatRadiusTheme.textDim)
            if let w = r.warning, !w.isEmpty {
                Text("告警：\(w)")
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(CombatRadiusTheme.amber)
            }
        }
    }

    private func radiusResultsPanel(_ r: CombatRadiusResult) -> some View {
        panel(title: "作战半径输出", tag: "RANGE") {
            HStack(spacing: 10) {
                let angle = r.mach_angle_deg.map { String(format: "%.1f°", $0) } ?? "—"
                let cone = r.mach_cone_limit.map { String(format: "锥限 Ma %.2f", $0) } ?? ""
                stat("马赫角", value: angle, sub: cone)
                stat("最大巡航 Ma", value: r.max_cruise_mach.map { String(format: "%.3f", $0) } ?? "—", amber: true)
            }
            ForEach(r.points ?? []) { p in
                HStack {
                    Text(p.label)
                        .foregroundStyle(CombatRadiusTheme.green)
                    Spacer()
                    if p.feasible == true, let km = p.radius_km {
                        Text(String(format: "Ma %.3f  %.0f km", p.mach ?? 0, km))
                            .foregroundStyle(CombatRadiusTheme.text)
                    } else {
                        Text("无 92% 裕度高度")
                            .foregroundStyle(CombatRadiusTheme.textDim)
                    }
                }
                .font(.system(size: 11, design: .monospaced))
            }
            if let note = r.note, !note.isEmpty {
                Text(note)
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(CombatRadiusTheme.textDim)
            }
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

    private func field(_ label: String, text: Binding<String>) -> some View {
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
        }
    }

    private func presetPicker(_ label: String, selection: Binding<String>, onChange: @escaping () -> Void) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label)
                .font(.system(size: 11, design: .monospaced))
                .foregroundStyle(CombatRadiusTheme.textDim)
            Picker(label, selection: selection) {
                Text("— 自定义 —").tag("")
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
