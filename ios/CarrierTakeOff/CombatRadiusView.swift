import SwiftUI

/// 作战半径升阻比估算界面（战术终端风格）
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

                    Text("第 2–4 部分（燃油、任务剖面、作战半径积分）将在后续接入同一终端。")
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundStyle(CombatRadiusTheme.textDim)
                }

                if let r = vm.result, r.success {
                    resultsPanel(r)
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
            Text("COMBAT RADIUS · L/D CALIBRATION")
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
        panel(title: "输出") {
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

    private func panel<Content: View>(title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text(title.uppercased())
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(CombatRadiusTheme.textDim)
                Spacer()
                Text("L/D")
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
