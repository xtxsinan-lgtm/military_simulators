import SwiftUI

/// 导弹射程估算界面：选预设看样本表，改参数后本地重算
struct MissileRangeView: View {
    @StateObject private var vm = MissileRangeViewModel()

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                Text("导弹射程估算终端")
                    .font(.system(size: 16, weight: .semibold, design: .monospaced))
                    .foregroundStyle(MissileRangeTheme.green)
                Text("RANGE · HGV / RAM / CRUISE / BALLISTIC")
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(MissileRangeTheme.textDim)
                Text(vm.statusText)
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundStyle(MissileRangeTheme.green)

                panel(title: "弹体与发射条件", tag: "INPUT") {
                    Text(vm.classBlurb)
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundStyle(MissileRangeTheme.textDim)
                    Picker("弹种", selection: $vm.missileClass) {
                        ForEach(vm.classOptions) { item in
                            Text(item.label).tag(item.id)
                        }
                    }
                    .onChange(of: vm.missileClass) { _, newId in
                        vm.setClass(newId)
                    }
                    Picker("预设样本", selection: $vm.selectedId) {
                        ForEach(vm.cases) { item in
                            Text(item.name).tag(item.id)
                        }
                    }
                    .onChange(of: vm.selectedId) { _, newId in
                        if let row = vm.cases.first(where: { $0.id == newId }) {
                            vm.applyCase(row)
                        }
                    }
                    field("弹长 (m)", text: $vm.lengthM)
                    field("弹径 (m)", text: $vm.diameterM)
                    field("战斗部 (kg)", text: $vm.warheadKg)
                    if vm.missileClass == "hgv" {
                        Picker("构型", selection: Binding(
                            get: { vm.typeIndex },
                            set: { vm.setTypeIndex($0) }
                        )) {
                            ForEach(vm.typeIds.indices, id: \.self) { index in
                                Text(vm.typeLabels[index]).tag(index)
                            }
                        }
                    }
                    field("发射马赫数", text: $vm.vMach)
                    field("发射高度 (km)", text: $vm.hKm)
                    field("比冲 (s)", text: $vm.ispS)
                    field("推进剂密度 (kg/m³)", text: $vm.density)
                    Button {
                        Task { await vm.estimate() }
                    } label: {
                        Text(vm.running ? "计算中…" : "▶ 估算射程")
                            .font(.system(size: 13, weight: .bold, design: .monospaced))
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 10)
                            .background(MissileRangeTheme.green)
                            .foregroundStyle(Color(hex: 0x042014))
                    }
                    .buttonStyle(.plain)
                    .disabled(vm.running)
                }

                panel(title: "估算结果", tag: "OUTPUT") {
                    if let result = vm.result {
                        if let high = result.range_high_km, let sea = result.range_sea_km {
                            statRow([
                                ("全高空 km", high, 1, false),
                                ("全掠海 km", sea, 1, true),
                            ])
                        } else {
                            statRow([
                                ("估算射程 km", result.range_km, 1, false),
                                (vm.missileClass == "ballistic" || vm.missileClass == "hgv" ? "关机马赫" : "巡航马赫", result.v_burnout_mach, 2, true),
                            ])
                        }
                        if let dash = result.range_terminal_km {
                            statRow([
                                ("末端冲刺 km", dash, 1, false),
                                ("巡航马赫", result.v_burnout_mach, 2, true),
                            ])
                        }
                        statRow([
                            ("升阻比", result.ld_ratio, 2, false),
                            ("起飞质量 t", result.m_0_t, 2, true),
                        ])
                        statRow([
                            ("弹头 m", result.l_head_m, 2, false),
                            ("助推 m", result.l_booster_m, 2, false),
                            ("推进剂 kg", result.m_p_total_kg, 1, false),
                        ])
                        if let note = result.note, !note.isEmpty {
                            Text(note)
                                .font(.system(size: 10, design: .monospaced))
                                .foregroundStyle(MissileRangeTheme.textDim)
                        }
                    } else {
                        Text("选择预设后显示样本射程。")
                            .font(.system(size: 12, design: .monospaced))
                            .foregroundStyle(MissileRangeTheme.textDim)
                    }
                }

                panel(title: "预设样本表", tag: "TABLE") {
                    ScrollView(.horizontal) {
                        VStack(alignment: .leading, spacing: 0) {
                            tableHeader
                            ForEach(vm.rows) { row in
                                Button {
                                    vm.applyCase(row)
                                } label: {
                                    tableRow(row, on: row.id == vm.activeId)
                                }
                                .buttonStyle(.plain)
                            }
                        }
                    }
                }
            }
            .padding(16)
        }
        .background(MissileRangeTheme.bg.ignoresSafeArea())
        .navigationTitle("导弹射程")
        .navigationBarTitleDisplayMode(.inline)
        .onAppear { vm.load() }
    }

    private var tableHeader: some View {
        HStack(spacing: 8) {
            cell("ID", width: 36, dim: true)
            cell("尺寸", width: 110, dim: true)
            cell("弹头", width: 56, dim: true)
            cell("弹种", width: 88, dim: true)
            cell("射程km", width: 72, dim: true)
            cell("掠海km", width: 72, dim: true)
        }
        .padding(.vertical, 4)
    }

    private func tableRow(_ row: MissileRangeCase, on: Bool) -> some View {
        HStack(spacing: 8) {
            cell(String(row.id), width: 36, dim: false, highlight: on)
            cell(row.size_m ?? "", width: 110, dim: false, highlight: on)
            cell(fmt(row.warhead_kg, 0), width: 56, dim: false, highlight: on)
            cell(kind(row), width: 88, dim: false, highlight: on)
            cell(fmt(row.range_km, 1), width: 72, dim: false, highlight: on)
            cell(row.range_sea_km == nil ? "—" : fmt(row.range_sea_km, 1), width: 72, dim: false, highlight: on)
        }
        .padding(.vertical, 6)
    }

    private func kind(_ row: MissileRangeCase) -> String {
        if (row.missile_class ?? "hgv") == "hgv" {
            return row.type_label ?? row.hgv_type
        }
        return row.class_label ?? row.missile_class ?? ""
    }

    private func cell(_ text: String, width: CGFloat, dim: Bool, highlight: Bool = false) -> some View {
        Text(text)
            .font(.system(size: 11, design: .monospaced))
            .foregroundStyle(highlight ? MissileRangeTheme.amber : (dim ? MissileRangeTheme.textDim : MissileRangeTheme.text))
            .frame(width: width, alignment: .leading)
    }

    private func statRow(_ items: [(String, Double?, Int, Bool)]) -> some View {
        HStack(spacing: 8) {
            ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                VStack(alignment: .leading, spacing: 4) {
                    Text(item.0)
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundStyle(MissileRangeTheme.textDim)
                    Text(fmt(item.1, item.2))
                        .font(.system(size: 18, design: .monospaced))
                        .foregroundStyle(item.3 ? MissileRangeTheme.amber : MissileRangeTheme.green)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(8)
                .background(MissileRangeTheme.panel2)
                .overlay(Rectangle().stroke(MissileRangeTheme.line, lineWidth: 1))
            }
        }
    }

    private func fmt(_ value: Double?, _ digits: Int) -> String {
        guard let value else { return "—" }
        return String(format: "%.\(digits)f", value)
    }

    private func field(_ label: String, text: Binding<String>) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label)
                .font(.system(size: 11, design: .monospaced))
                .foregroundStyle(MissileRangeTheme.textDim)
            TextField(label, text: text)
                .font(.system(size: 13, design: .monospaced))
                .foregroundStyle(MissileRangeTheme.text)
                .padding(8)
                .background(MissileRangeTheme.panel2)
                .overlay(Rectangle().stroke(MissileRangeTheme.line, lineWidth: 1))
                .keyboardType(.decimalPad)
        }
    }

    @ViewBuilder
    private func panel<Content: View>(title: String, tag: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text(title.uppercased())
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(MissileRangeTheme.textDim)
                Spacer()
                Text(tag)
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(MissileRangeTheme.green)
            }
            content()
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(MissileRangeTheme.panel)
        .overlay(Rectangle().stroke(MissileRangeTheme.line, lineWidth: 1))
    }
}
