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

                    Text("第 3–4 部分（燃油、任务剖面、作战半径积分）将在后续接入同一终端。")
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundStyle(CombatRadiusTheme.textDim)
                }

                if let r = vm.result, r.success {
                    resultsPanel(r)
                }
                if let r = vm.thrustResult, r.success {
                    thrustResultsPanel(r)
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
            Text("COMBAT RADIUS · L/D + MILITARY THRUST")
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
