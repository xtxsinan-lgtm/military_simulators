import SwiftUI

/// 主界面：与微信小程序 index / Web takeoff 相同的战术终端布局
struct ContentView: View {
    @StateObject private var vm = SimulatorViewModel()

    var body: some View {
        ScrollViewReader { proxy in
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                Color.clear.frame(height: 0).id("pageTop")
                header
                StatusBar(text: vm.statusText, kind: vm.statusKind)

                CardView(title: "1. 起飞模式", tag: "MODE") {
                    ModeSelector(items: vm.modeList, current: $vm.currentMode) { mode in
                        vm.applyMode(mode)
                    }
                    if vm.showStrategy {
                        Text(vm.strategyTitle.uppercased())
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundStyle(AppTheme.accent)
                            .tracking(2)
                            .padding(.top, 8)
                        ModeSelector(items: vm.strategyList, current: $vm.currentStrategy) { _ in
                            vm.updateStrategyDescription()
                        }
                        if !vm.strategyDescription.isEmpty {
                            Text(vm.strategyDescription)
                                .font(.system(size: 11, design: .monospaced))
                                .foregroundStyle(AppTheme.muted)
                                .padding(.top, 4)
                        }
                    }
                }

                CardView(title: "2. 航母", tag: "CARRIER") {
                    Text("选择航母")
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundStyle(AppTheme.muted)
                    Picker("航母", selection: Binding(
                        get: { vm.selectedCarrierId ?? "" },
                        set: { vm.onCarrierPicked($0) }
                    )) {
                        ForEach(vm.carriers) { c in
                            Text(c.displayName).tag(c.id)
                        }
                    }
                    .pickerStyle(.menu)
                    .tint(AppTheme.text)
                    .font(.system(size: 13, design: .monospaced))
                    .padding(10)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(AppTheme.surface2)
                    .overlay(Rectangle().stroke(AppTheme.border, lineWidth: 1))
                    SpecListView(items: vm.carrierSpecs, emptyText: "请选择航母")

                    if vm.showSkiJump {
                        Text("滑跃参数（修改角度或弧长后，唇口高度自动重算）：")
                            .font(.system(size: 11, design: .monospaced))
                            .foregroundStyle(AppTheme.muted)
                            .padding(.top, 8)
                        LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
                            FieldInput(label: "滑跃角 (°)", text: $vm.skiAngle) {
                                vm.updateSkiJumpFromInputs()
                                vm.markResultsStale()
                            }
                            FieldInput(label: "滑跃弧长 (m)", text: $vm.skiArcLength) {
                                vm.updateSkiJumpFromInputs()
                                vm.markResultsStale()
                            }
                            FieldInput(label: "唇口高度 (m)", text: $vm.skiHeight, readonly: true)
                        }
                        Text("滑跃水平投影：\(vm.skiHorizontal) m")
                            .font(.system(size: 11, design: .monospaced))
                            .foregroundStyle(AppTheme.muted)
                    }
                }

                CardView(title: "3. 战斗机", tag: "AIRCRAFT") {
                    Text("选择战斗机")
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundStyle(AppTheme.muted)
                    Picker("战斗机", selection: Binding(
                        get: { vm.selectedAircraftId ?? "" },
                        set: { vm.onAircraftPicked($0) }
                    )) {
                        ForEach(vm.aircraft) { a in
                            Text(a.name).tag(a.id)
                        }
                    }
                    .pickerStyle(.menu)
                    .tint(AppTheme.text)
                    .font(.system(size: 13, design: .monospaced))
                    .padding(10)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(AppTheme.surface2)
                    .overlay(Rectangle().stroke(AppTheme.border, lineWidth: 1))
                    SpecListView(items: vm.aircraftSpecs, emptyText: "请选择战斗机")
                }

                CardView(title: "4. 仿真条件", tag: "INPUT") {
                    LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
                        FieldInput(label: "甲板风 (kt)", text: $vm.windKt) { vm.markWindEdited() }
                        FieldInput(label: "环境温度 (°C)", text: $vm.tempC) { vm.markResultsStale() }
                        FieldInput(
                            label: "起飞重量 (kg)",
                            text: $vm.massKg,
                            hint: vm.massRangeHint,
                            error: vm.massError
                        ) { vm.markMassEdited() }
                    }
                    Button {
                        Task { await vm.runSimulation() }
                    } label: {
                        HStack {
                            if vm.running { ProgressView().tint(Color(hex: 0x042033)) }
                            Text(vm.running ? "▶ 计算中…" : "▶ 开始仿真")
                                .font(.system(size: 13, weight: .bold, design: .monospaced))
                                .tracking(2)
                        }
                        .foregroundStyle(Color(hex: 0x042033))
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 12)
                        .background(AppTheme.accent)
                        .opacity(vm.running ? 0.55 : 1)
                    }
                    .disabled(vm.running || !vm.engineReady)
                    .padding(.top, 4)

                    if !vm.engineReady {
                        Text("本地 Python 仿真引擎加载中（与 Web 版同一套物理模型，无需后端）。")
                            .font(.system(size: 11, design: .monospaced))
                            .foregroundStyle(AppTheme.muted)
                    }
                }

                CardView(title: "5. 仿真输出", tag: "OUTPUT", trailingSummary: vm.outputSummary) {
                    if vm.resultStale {
                        Text("参数已更改，以下结果与当前输入不一致，请重新仿真。")
                            .font(.system(size: 11, design: .monospaced))
                            .foregroundStyle(Color(hex: 0xFBBF24))
                    }
                    if !vm.highlights.isEmpty {
                        HStack(spacing: 10) {
                            ForEach(vm.highlights) { card in
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(card.label.uppercased())
                                        .font(.system(size: 9, design: .monospaced))
                                        .foregroundStyle(AppTheme.muted)
                                    Text(card.value)
                                        .font(.system(size: 18, weight: .bold, design: .monospaced))
                                        .foregroundStyle(highlightTone(card.tone))
                                }
                                .padding(10)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .background(AppTheme.surface2)
                                .overlay(Rectangle().stroke(AppTheme.border, lineWidth: 1))
                            }
                        }
                    }
                    Button(vm.outputDetailsOpen ? "▾ 收起计算详情" : "▸ 计算详情") {
                        vm.outputDetailsOpen.toggle()
                    }
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundStyle(AppTheme.muted)
                    if vm.outputDetailsOpen {
                        ScrollView {
                            Text(vm.outputText)
                                .font(.system(size: 11, design: .monospaced))
                                .foregroundStyle(vm.outputEmpty ? AppTheme.muted : AppTheme.text)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .textSelection(.enabled)
                        }
                        .frame(maxHeight: 240)
                        .padding(8)
                        .background(Color(hex: 0x0D1117))
                        .overlay(Rectangle().stroke(AppTheme.border, lineWidth: 1))
                    }
                }

                if vm.showTrajectory {
                    CardView(title: "6. 起飞轨迹", tag: "TRAJECTORY") {
                        TrajectoryChart(result: vm.chartResult)
                    }
                }
            }
            .padding(.horizontal, 14)
            .padding(.top, 8)
            .padding(.bottom, 24)
        }
        .overlay(alignment: .bottomTrailing) {
            Button("↑ 顶部") {
                withAnimation { proxy.scrollTo("pageTop", anchor: .top) }
            }
            .font(.system(size: 12, design: .monospaced))
            .padding(8)
            .background(AppTheme.surface)
            .overlay(Rectangle().stroke(AppTheme.accent, lineWidth: 1))
            .foregroundStyle(AppTheme.accent)
            .padding(16)
        }
        }
        .background(
            ZStack {
                AppTheme.bg
                // 网格底纹（对齐 Web/小程序）
                Canvas { context, size in
                    let step: CGFloat = 28
                    var path = Path()
                    var x: CGFloat = 0
                    while x <= size.width {
                        path.move(to: CGPoint(x: x, y: 0))
                        path.addLine(to: CGPoint(x: x, y: size.height))
                        x += step
                    }
                    var y: CGFloat = 0
                    while y <= size.height {
                        path.move(to: CGPoint(x: 0, y: y))
                        path.addLine(to: CGPoint(x: size.width, y: y))
                        y += step
                    }
                    context.stroke(path, with: .color(AppTheme.accent.opacity(0.06)), lineWidth: 1)
                }
                .allowsHitTesting(false)
            }
            .ignoresSafeArea()
        )
        .preferredColorScheme(.dark)
        .task { await vm.bootstrap() }
    }

    private func highlightTone(_ tone: String?) -> Color {
        switch tone {
        case "ok": return AppTheme.success
        case "danger": return AppTheme.danger
        default: return AppTheme.accent
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("航母舰载机起飞距离仿真终端")
                .font(.system(size: 14, weight: .bold, design: .monospaced))
                .foregroundStyle(AppTheme.accent)
                .tracking(2)
            Text("CARRIER TAKEOFF")
                .font(.system(size: 10, design: .monospaced))
                .foregroundStyle(AppTheme.muted)
                .tracking(1)
        }
        .padding(.horizontal, 2)
        .padding(.bottom, 6)
        .frame(maxWidth: .infinity, alignment: .leading)
        .overlay(alignment: .bottom) {
            Rectangle().fill(AppTheme.border).frame(height: 1)
        }
    }
}

#Preview {
    ContentView()
}
