import SwiftUI

/// 启动页：从 Bundle data.json.simulators 列出可选模拟器
struct HubView: View {
    @State private var simulators: [SimulatorEntry] = []
    @State private var status = "加载中…"
    @State private var loadError = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text("CARRIER COMBAT SIMULATOR")
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundStyle(Color(hex: 0x5FD8E8))
                Text("舰载作战仿真终端")
                    .font(.system(size: 28, weight: .semibold))
                    .foregroundStyle(Color(hex: 0xE8EEF0))

                ForEach(simulators) { sim in
                    NavigationLink {
                        destination(for: sim)
                    } label: {
                        VStack(alignment: .leading, spacing: 8) {
                            Text(sim.eyebrow ?? sim.id.uppercased())
                                .font(.system(size: 10, design: .monospaced))
                                .foregroundStyle(Color(hex: 0x8AA0A8))
                            Text(sim.name)
                                .font(.system(size: 18, weight: .semibold))
                                .foregroundStyle(Color(hex: 0xE8EEF0))
                            Text(sim.subtitle ?? "")
                                .font(.system(size: 13))
                                .foregroundStyle(Color(hex: 0x8AA0A8))
                            Text("进入仿真 →")
                                .font(.system(size: 12, design: .monospaced))
                                .foregroundStyle(Color(hex: 0xFFB020))
                                .padding(.top, 4)
                        }
                        .padding(16)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(Color(hex: 0x0D1820))
                        .overlay(
                            Rectangle()
                                .stroke(Color(hex: 0x243540), lineWidth: 1)
                        )
                        .overlay(alignment: .top) {
                            Rectangle()
                                .fill(hubAccent(for: sim.id))
                                .frame(height: 3)
                        }
                    }
                    .buttonStyle(.plain)
                }

                Text(status)
                    .font(.system(size: 12, design: .monospaced))
                    .foregroundStyle(loadError ? Color(hex: 0xF87171) : Color(hex: 0x8AA0A8))
                    .padding(.top, 8)
            }
            .padding(20)
        }
        .background(Color(hex: 0x071018).ignoresSafeArea())
        .navigationBarTitleDisplayMode(.inline)
        .onAppear(perform: load)
    }

    @ViewBuilder
    private func destination(for sim: SimulatorEntry) -> some View {
        switch sim.ios_route ?? sim.id {
        case "missile_interception":
            MissileInterceptionStrikeView()
        case "combat_radius":
            CombatRadiusView()
        default:
            ContentView()
        }
    }

    private func hubAccent(for id: String) -> Color {
        switch id {
        case "missile_interception":
            return Color(hex: 0xFFB020)
        case "combat_radius":
            return Color(hex: 0x3DDC84)
        default:
            return Color(hex: 0x38BDF8)
        }
    }

    private func load() {
        do {
            let catalog = try CatalogStore.loadBundledCatalog()
            let sims = catalog.simulators ?? []
            simulators = sims
            let ac = catalog.aircraft.count
            let cr = catalog.carriers.count
            let sat = catalog.missile_interception_presets
            let satCount = (sat?.asm?.count ?? 0) + (sat?.sam?.count ?? 0)
            status = sims.isEmpty
                ? "data.json 缺少 simulators，请运行 build_all.py"
                : "已同步 \(ac) 种舰载机 · \(cr) 艘航母 · 饱和装备 \(satCount)+ 项"
            loadError = sims.isEmpty
        } catch {
            status = error.localizedDescription
            loadError = true
        }
    }
}
