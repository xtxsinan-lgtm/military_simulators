import SwiftUI

/// 饱和打击仿真界面（战术终端风格）
struct MissileInterceptionStrikeView: View {
    @StateObject private var vm = MissileInterceptionViewModel()

    var body: some View {
        ScrollViewReader { proxy in
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                Color.clear.frame(height: 0).id("pageTop")
                header
                Text(vm.statusText)
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundStyle(MissileInterceptionTheme.green)

                panel(title: "参数输入") {
                    field("来袭数量 (枚)", text: $vm.nm, hintKey: "nm")
                    field("拦截弹数量", text: $vm.ni, hintKey: "ni")

                    sectionLabel("▸ 打击方", color: MissileInterceptionTheme.red)
                    nationPicker("反舰导弹国别", selection: $vm.selectedAsmNation, nations: vm.asmNations) {
                        vm.resetAsmModel()
                    }
                    presetPicker("反舰导弹型号", selection: $vm.selectedAsmId, items: vm.asmModels) {
                        vm.applyAsmPreset()
                    }
                    field("速度 (Ma)", text: $vm.vm, hintKey: "vm")
                    field("RCS (m²)", text: $vm.rcs, hintKey: "rcs")
                    pickerRow("弹道", selection: $vm.traj, options: vm.trajOptions, hintKey: "traj")

                    sectionLabel("▸ 预警机", color: MissileInterceptionTheme.cyan)
                    presetPicker("预警机预设", selection: $vm.selectedAewId, items: vm.aewPresets) {
                        vm.applyAewPreset()
                    }
                    field("天线面积 (m²)", text: $vm.awacsArea, hintKey: "awacsArea")
                    pickerRow("雷达体制", selection: $vm.awacsType, options: vm.radarOptions, hintKey: "awacsType")
                    field("前出距离 (km)", text: $vm.standoff)

                    sectionLabel("▸ 舰载雷达 & 拦截弹", color: MissileInterceptionTheme.green)
                    nationPicker("防御方国别", selection: $vm.selectedDefenderNation, nations: vm.defenderNations) {
                        vm.resetDefenderModels()
                    }
                    presetPicker("驱护舰艇型号", selection: $vm.selectedShipId, items: vm.shipModels) {
                        vm.applyShipPreset()
                    }
                    presetPicker("防空导弹型号", selection: $vm.selectedSamId, items: vm.samModels) {
                        vm.applySamPreset()
                    }
                    field("舰载天线 (m²)", text: $vm.shipArea, hintKey: "shipArea")
                    pickerRow("舰载体制", selection: $vm.shipType, options: vm.radarOptions, hintKey: "shipType")
                    field("拦截弹射程 (km)", text: $vm.samRange, hintKey: "samRange")
                    field("拦截弹最大射高 (km)", text: $vm.samMaxAlt, hintKey: "samMaxAlt")
                    field("拦截弹速度 (Ma)", text: $vm.vi, hintKey: "vi")
                    field("拦截弹直径 (m)", text: $vm.interceptorDia, hintKey: "interceptorDia")
                    pickerRow("制导头", selection: $vm.seekerType, options: vm.seekerOptions, hintKey: "seekerType")
                    field("火控锁定时间 (s)", text: $vm.tlock, hintKey: "tlock")
                    field("最小交战距离 (km)", text: $vm.minr, hintKey: "minr")

                    Button("◈ 估算交战距离与拦截率") {
                        Task { await vm.estimateDistanceAndPk() }
                    }
                    .buttonStyle(SatSecondaryButton())
                    if !vm.distNote.isEmpty {
                        Text(vm.distNote).font(.system(size: 10, design: .monospaced)).foregroundStyle(MissileInterceptionTheme.textDim)
                    }
                    if !vm.pkNote.isEmpty {
                        Text(vm.pkNote).font(.system(size: 10, design: .monospaced)).foregroundStyle(MissileInterceptionTheme.textDim)
                    }
                    Text("交战距离 = min( max(预警机, 舰载), 拦截弹射程 [, 俯冲进入距离] )。仅当巡航高度高于拦截弹最大射高时才计入俯冲几何；常规高空/掠海导弹已在射高包线内，不涉及俯冲角。")
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundStyle(MissileInterceptionTheme.textDim)

                    readonlyField("预警机雷达探测距离 (km)", text: vm.awacsDetectKm)
                    readonlyField("舰载雷达探测距离 (km)", text: vm.shipDetectKm)
                    readonlyField("进入有效射高距离", text: vm.diveEntryDisplay)
                    field("交战距离 (km)", text: $vm.discoveryKm)
                    field("单发拦截成功概率", text: $vm.pk, hintKey: "pk")

                    Button(vm.running ? "计算中…" : "▶ 运行仿真") {
                        Task { await vm.run() }
                    }
                    .buttonStyle(SatPrimaryButton())
                    .disabled(vm.running)
                }

                if vm.hasResult, let r = vm.result {
                    resultsPanel(r)
                }
            }
            .padding(14)
        }
        .overlay(alignment: .bottomTrailing) {
            Button("↑ 顶部") {
                withAnimation { proxy.scrollTo("pageTop", anchor: .top) }
            }
            .font(.system(size: 12, design: .monospaced))
            .padding(8)
            .background(MissileInterceptionTheme.panel)
            .overlay(Rectangle().stroke(MissileInterceptionTheme.cyan, lineWidth: 1))
            .foregroundStyle(MissileInterceptionTheme.cyan)
            .padding(16)
        }
        .background(MissileInterceptionTheme.bg.ignoresSafeArea())
        .task { await vm.estimateDistanceAndPk() }
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("饱和打击 / 反导拦截仿真终端")
                .font(.system(size: 14, weight: .bold, design: .monospaced))
                .foregroundStyle(MissileInterceptionTheme.amber)
            Text("SHIPBORNE MISSILE INTERCEPTION")
                .font(.system(size: 10, design: .monospaced))
                .foregroundStyle(MissileInterceptionTheme.textDim)
            Text(vm.statusTag)
                .font(.system(size: 10, design: .monospaced))
                .foregroundStyle(MissileInterceptionTheme.amber)
        }
    }

    private func resultsPanel(_ r: MissileInterceptionResult) -> some View {
        panel(title: "仿真结果 · \(vm.statusTag)") {
            if vm.resultStale {
                Text("参数已更改，以下结果与当前输入不一致，请重新仿真。")
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundStyle(MissileInterceptionTheme.amber)
            }
            HStack(spacing: 10) {
                stat("窗口数", "\(r.n_rounds ?? 0)", nil)
                stat("期望突防", String(format: "%.2f", r.expected_leak ?? 0), MissileInterceptionTheme.red)
                stat("拦截率", String(format: "%.1f%%", (r.intercept_rate ?? 0) * 100), MissileInterceptionTheme.green)
            }
            sectionLabel("▸ 拦截窗口", color: MissileInterceptionTheme.textDim)
            ForEach(r.windows ?? []) { w in
                Text("#\(w.round)  \(String(format: "%.1f", w.dist_start_km))→\(String(format: "%.1f", w.dist_end_km)) km  t=\(String(format: "%.1f", w.total_t_s))s")
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundStyle(MissileInterceptionTheme.text)
            }
            if let best = r.best {
                sectionLabel("▸ 最优方案 \(best.name)", color: MissileInterceptionTheme.textDim)
                Text("[\(best.plan.map(String.init).joined(separator: ", "))]")
                    .font(.system(size: 12, design: .monospaced))
                    .foregroundStyle(MissileInterceptionTheme.green)
            }
            if let rows = r.plan_rows, !rows.isEmpty {
                sectionLabel("▸ 最优弹药分配", color: MissileInterceptionTheme.textDim)
                ForEach(rows) { row in
                    Text("#\(row.round)  \(row.budget)枚  存活\(String(format: "%.2f", row.survivors))  ≈\(String(format: "%.2f", row.per_target))/目标  杀伤 \(String(format: "%.1f%%", row.kill_prob * 100))")
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundStyle(MissileInterceptionTheme.text)
                }
            }
            sectionLabel("▸ 策略对比", color: MissileInterceptionTheme.textDim)
            ForEach(r.all_candidates ?? []) { c in
                Text("\(c.name)  [\(c.plan.map(String.init).joined(separator: ", "))]  突防 \(String(format: "%.2f", c.expected_leak))  \(c.relative_label ?? (c.is_best == true ? "最优" : ""))")
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(c.is_best == true ? MissileInterceptionTheme.green : MissileInterceptionTheme.textDim)
            }
            if let note = r.note {
                Text(note)
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(MissileInterceptionTheme.textDim)
                    .padding(.top, 8)
            }
        }
    }

    private func panel<Content: View>(title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title)
                .font(.system(size: 10, design: .monospaced))
                .foregroundStyle(MissileInterceptionTheme.textDim)
            content()
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(MissileInterceptionTheme.panel)
        .overlay(Rectangle().stroke(MissileInterceptionTheme.line, lineWidth: 1))
    }

    private func sectionLabel(_ text: String, color: Color) -> some View {
        Text(text)
            .font(.system(size: 10, design: .monospaced))
            .foregroundStyle(color)
            .padding(.top, 6)
    }

    private func field(_ label: String, text: Binding<String>, hintKey: String? = nil) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(label)
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundStyle(MissileInterceptionTheme.textDim)
                if let hintKey, !vm.hint(for: hintKey).isEmpty {
                    Text("?")
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundStyle(MissileInterceptionTheme.cyan)
                        .help(vm.hint(for: hintKey))
                }
            }
            TextField("", text: text)
                .textFieldStyle(.plain)
                .padding(8)
                .background(MissileInterceptionTheme.panel2)
                .overlay(Rectangle().stroke(MissileInterceptionTheme.line, lineWidth: 1))
                .foregroundStyle(MissileInterceptionTheme.text)
                .font(.system(size: 13, design: .monospaced))
                .onChange(of: text.wrappedValue) { _, _ in vm.markResultsStale() }
        }
    }

    /// 只读展示字段（估算结果，如预警机/舰载雷达探测距离），不可编辑。
    private func readonlyField(_ label: String, text: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label)
                .font(.system(size: 11, design: .monospaced))
                .foregroundStyle(MissileInterceptionTheme.textDim)
            Text(text)
                .font(.system(size: 13, design: .monospaced))
                .foregroundStyle(MissileInterceptionTheme.cyan)
                .padding(8)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(MissileInterceptionTheme.panel2)
                .overlay(Rectangle().stroke(MissileInterceptionTheme.line, lineWidth: 1))
        }
    }

    private func pickerRow(_ label: String, selection: Binding<String>, options: [(String, String)], hintKey: String? = nil) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(label)
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundStyle(MissileInterceptionTheme.textDim)
                if let hintKey, !vm.hint(for: hintKey).isEmpty {
                    Text("?")
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundStyle(MissileInterceptionTheme.cyan)
                        .help(vm.hint(for: hintKey))
                }
            }
            Picker(label, selection: selection) {
                ForEach(options, id: \.0) { opt in
                    Text(opt.1).tag(opt.0)
                }
            }
            .pickerStyle(.menu)
            .tint(MissileInterceptionTheme.cyan)
            .onChange(of: selection.wrappedValue) { _, _ in vm.markResultsStale() }
        }
    }

    /// 两级选择的第一级：国别；切换后由 onChange 复位型号
    private func nationPicker(
        _ label: String,
        selection: Binding<String>,
        nations: [String],
        onChange: @escaping () -> Void
    ) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label)
                .font(.system(size: 11, design: .monospaced))
                .foregroundStyle(MissileInterceptionTheme.textDim)
            Picker(label, selection: selection) {
                Text("— 全部国别 —").tag("")
                ForEach(nations, id: \.self) { nation in
                    Text(nation).tag(nation)
                }
            }
            .pickerStyle(.menu)
            .tint(MissileInterceptionTheme.cyan)
            .onChange(of: selection.wrappedValue) { _, _ in onChange() }
        }
    }

    private func presetPicker(
        _ label: String,
        selection: Binding<String>,
        items: [MissileInterceptionPresetItem],
        onChange: @escaping () -> Void
    ) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label)
                .font(.system(size: 11, design: .monospaced))
                .foregroundStyle(MissileInterceptionTheme.textDim)
            Picker(label, selection: selection) {
                Text("— 自定义 —").tag("")
                ForEach(items) { item in
                    Text(item.name).tag(item.id)
                }
            }
            .pickerStyle(.menu)
            .tint(MissileInterceptionTheme.amber)
            .onChange(of: selection.wrappedValue) { _, _ in onChange() }
        }
    }

    private func stat(_ k: String, _ v: String, _ color: Color?) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(k)
                .font(.system(size: 9, design: .monospaced))
                .foregroundStyle(MissileInterceptionTheme.textDim)
            Text(v)
                .font(.system(size: 20, design: .monospaced))
                .foregroundStyle(color ?? MissileInterceptionTheme.amber)
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(MissileInterceptionTheme.panel2)
        .overlay(Rectangle().stroke(MissileInterceptionTheme.line, lineWidth: 1))
    }
}

private struct SatPrimaryButton: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 13, weight: .bold, design: .monospaced))
            .frame(maxWidth: .infinity)
            .padding(12)
            .background(MissileInterceptionTheme.amber)
            .foregroundStyle(Color(hex: 0x1A1300))
            .opacity(configuration.isPressed ? 0.85 : 1)
    }
}

private struct SatSecondaryButton: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 12, weight: .bold, design: .monospaced))
            .frame(maxWidth: .infinity)
            .padding(10)
            .background(MissileInterceptionTheme.cyan)
            .foregroundStyle(Color(hex: 0x04262B))
            .opacity(configuration.isPressed ? 0.85 : 1)
    }
}
