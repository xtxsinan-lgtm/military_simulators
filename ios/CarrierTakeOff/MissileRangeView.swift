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
                    field("发射马赫数", text: $vm.vMach)
                    field("发射高度 (km)", text: $vm.hKm)
                    field("固体比冲 (s)", text: $vm.ispS)
                    if vm.showAirIsp {
                        field("吸气比冲 (s)", text: $vm.ispAir)
                    }
                    if vm.missileClass == "ballistic" {
                        Toggle("仅单级", isOn: $vm.ballisticSingleStage)
                            .font(.system(size: 13, design: .monospaced))
                            .foregroundStyle(MissileRangeTheme.text)
                    }
                    if vm.missileClass.hasPrefix("hgv") {
                        Toggle("寻优滑翔体尺寸", isOn: $vm.optimizeGeometry)
                            .font(.system(size: 13, design: .monospaced))
                            .foregroundStyle(MissileRangeTheme.text)
                    }
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
                        if result.reached_takeover == false {
                            VStack(alignment: .leading, spacing: 4) {
                                Text("⚠️ 未达工作速度 (TAKEOVER FAILED)")
                                    .font(.system(size: 11, weight: .bold, design: .monospaced))
                                    .foregroundStyle(Color.red)
                                Text("助推级实际加速至 Ma \(fmt(result.mach_boost ?? result.v_burnout_mach, 2))，未达冲压设计接力速度 Ma \(fmt(result.mach_takeover, 2))。冲压未启动，巡航段有效射程为 0 km，当前射程仅计助推关机后的惯性弹道滑行弧。")
                                    .font(.system(size: 10, design: .monospaced))
                                    .foregroundStyle(MissileRangeTheme.text)
                            }
                            .padding(10)
                            .background(Color.red.opacity(0.12))
                            .overlay(
                                RoundedRectangle(cornerRadius: 2)
                                    .stroke(Color.red.opacity(0.6), lineWidth: 1)
                            )
                        }
                        if let takeover = result.mach_takeover {
                            let boost = result.mach_boost ?? result.v_burnout_mach ?? 0
                            let frac = result.takeover_progress ?? min(1.0, boost / takeover)
                            VStack(alignment: .leading, spacing: 4) {
                                HStack {
                                    Text("助推接力进度")
                                    Spacer()
                                    Text(String(format: "Ma %.2f / %.2f", boost, takeover))
                                }
                                .font(.system(size: 10, design: .monospaced))
                                .foregroundStyle(MissileRangeTheme.textDim)
                                ProgressView(value: max(0, min(1, frac)))
                                    .tint(result.reached_takeover == false ? Color.red : MissileRangeTheme.green)
                                Text(result.reached_takeover == false ? "未达接力速度，冲压未启动" : "已接入冲压巡航")
                                    .font(.system(size: 10, design: .monospaced))
                                    .foregroundStyle(result.reached_takeover == false ? Color.red : MissileRangeTheme.textDim)
                            }
                            .padding(.vertical, 4)
                        }
                        if let takeover = result.mach_takeover {
                            statRow([
                                ("接力目标", takeover, 2, false),
                                ("助推实际", result.mach_boost ?? result.v_burnout_mach, 2, true),
                            ])
                        }
                        if let profile = profileCaption(result.profile_text, high: result.range_high_km, mixed: result.range_mixed_km, sea: result.range_sea_km) {
                            Text("高空/混合/掠海  \(profile) km")
                                .font(.system(size: 16, design: .monospaced))
                                .foregroundStyle(MissileRangeTheme.green)
                        } else {
                            statRow([
                                (result.reached_takeover == false ? "弹道滑行 km" : "估算射程 km", result.range_km, 1, false),
                                (vm.missileClass == "ballistic" || vm.missileClass.hasPrefix("hgv") ? "关机马赫" : (result.reached_takeover == false ? "助推马赫" : "巡航马赫"), result.v_burnout_mach, 2, true),
                            ])
                        }
                        if let alt = result.alt_range_text, !alt.isEmpty {
                            Text("各机射程  \(alt) km")
                                .font(.system(size: 13, design: .monospaced))
                                .foregroundStyle(MissileRangeTheme.amber)
                        }
                        if let wing = result.m_wing_kg, let dead = result.m_dead_kg {
                            statRow([
                                ("折叠弹翼 kg", wing, 0, false),
                                ("死重 kg", dead, 0, true),
                            ])
                        }
                        statRow([
                            ("升阻比", result.ld_ratio, 2, false),
                            ("起飞质量 t", result.m_0_t, 2, true),
                        ])
                        if let dHead = result.d_head_m {
                            statRow([
                                ("弹头 m", result.l_head_m, 2, false),
                                ("滑翔径 m", dHead, 3, false),
                                ("助推 m", result.l_booster_m, 2, false),
                            ])
                            if result.fineness != nil || (result.range_gain_km ?? 0) > 0 {
                                statRow([
                                    ("长细比", result.fineness, 2, false),
                                    ("几何增程 km", result.range_gain_km, 1, true),
                                ])
                            }
                        } else {
                            statRow([
                                ("弹头 m", result.l_head_m, 2, false),
                                ("助推 m", result.l_booster_m, 2, false),
                                ("推进剂 kg", result.m_p_total_kg, 1, false),
                            ])
                        }
                        ispStatRow(result)
                        if let stages = result.n_stages {
                            Text(stageCaption(stages, split: result.stage_split, locked: result.stage_locked))
                                .font(.system(size: 12, weight: .semibold, design: .monospaced))
                                .foregroundStyle(MissileRangeTheme.green)
                        }
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
                    Toggle("只看未达工作速度", isOn: Binding(
                        get: { vm.failOnly },
                        set: { vm.setFailOnly($0) }
                    ))
                    .font(.system(size: 12, design: .monospaced))
                    .foregroundStyle(Color.red)
                    Text("冲压接力：已接入 \(vm.okCount) 发 · 未达工作速度 \(vm.failCount) 发。")
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundStyle(MissileRangeTheme.textDim)
                    ScrollView(.horizontal) {
                        VStack(alignment: .leading, spacing: 0) {
                            tableHeader
                            ForEach(vm.displayedRows) { row in
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
            cell("载机", width: 132, dim: true)
            cell("尺寸", width: 110, dim: true)
            cell("战斗部重量", width: 96, dim: true)
            cell("弹种", width: 120, dim: true)
            cell("射程km", width: 168, dim: true)
            cell("分级", width: 108, dim: true)
            cell("各机射程", width: 460, dim: true)
        }
        .padding(.vertical, 4)
    }

    private func tableRow(_ row: MissileRangeCase, on: Bool) -> some View {
        HStack(spacing: 8) {
            cell(String(row.id), width: 36, dim: false, highlight: on)
            cell(row.bay ?? "—", width: 132, dim: false, highlight: on)
            cell(row.size_m ?? "", width: 110, dim: false, highlight: on)
            cell(fmt(row.warhead_kg, 0), width: 96, dim: false, highlight: on)
            cell(kind(row), width: 120, dim: false, highlight: on)
            cell(profileCaption(row.profile_text, high: row.range_high_km, mixed: row.range_mixed_km, sea: row.range_sea_km) ?? fmt(row.range_km, 1), width: 168, dim: false, highlight: on)
            cell(stageCaption(row.n_stages, split: row.stage_split, locked: row.stage_locked), width: 108, dim: false, highlight: on)
            cell(row.alt_range_text ?? "—", width: 460, dim: false, highlight: on)
        }
        .padding(.vertical, 6)
    }

    private func stageCaption(_ stages: Int?, split: String?, locked: Bool?) -> String {
        guard let stages else { return "—" }
        let name: String
        switch stages {
        case 1: name = "单级"
        case 2: name = "两级"
        case 3: name = "三级"
        default: name = "\(stages)级"
        }
        if stages == 1 { return locked == true ? "\(name)·锁定" : name }
        let ratio = split ?? ""
        return ratio.isEmpty ? name : "\(name) \(ratio)"
    }

    private func kind(_ row: MissileRangeCase) -> String {
        let label = row.class_label ?? row.missile_class ?? ""
        if row.reached_takeover == false {
            return "\(label) [未达速]"
        }
        return label
    }

    @ViewBuilder
    private func ispStatRow(_ result: MissileRangeEstimate) -> some View {
        let items = ispStatItems(result)
        if !items.isEmpty {
            statRow(items)
        }
    }

    private func profileCaption(_ preset: String?, high: Double?, mixed: Double?, sea: Double?) -> String? {
        if let preset, !preset.isEmpty { return preset }
        guard let high, let sea else { return nil }
        let mid = mixed.map { fmt($0, 1) } ?? "—"
        return "\(fmt(high, 1))/\(mid)/\(fmt(sea, 1))"
    }

    private func ispStatItems(_ result: MissileRangeEstimate) -> [(String, Double?, Int, Bool)] {
        var items: [(String, Double?, Int, Bool)] = []
        if let boost = result.isp_boost_s {
            items.append(("助推比冲 s", boost, 0, false))
        }
        if let cruise = result.isp_cruise_s {
            items.append(("吸气比冲 s", cruise, 0, true))
        }
        if let rocket = result.isp_rocket_s {
            items.append(("固体比冲 s", rocket, 0, false))
        }
        return items
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
