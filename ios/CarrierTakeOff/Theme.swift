import SwiftUI

/// 起飞仿真主题：保留蓝青配色，布局观感对齐饱和打击战术终端
enum AppTheme {
    static let bg = Color(hex: 0x0F1419)
    static let surface = Color(hex: 0x1A2332)
    static let surface2 = Color(hex: 0x243044)
    static let border = Color(hex: 0x334155)
    static let text = Color(hex: 0xE2E8F0)
    static let muted = Color(hex: 0x94A3B8)
    static let accent = Color(hex: 0x38BDF8)
    static let accentDim = Color(hex: 0x0EA5E9)
    static let success = Color(hex: 0x4ADE80)
    static let danger = Color(hex: 0xF87171)
    static let warning = Color(hex: 0xFBBF24)
    /// 战术终端风格：近直角
    static let radius: CGFloat = 2
    static let mono = Font.system(size: 13, design: .monospaced)
}

extension Color {
    /// 从 0xRRGGBB 构造 Color
    init(hex: UInt32, opacity: Double = 1) {
        let r = Double((hex >> 16) & 0xFF) / 255
        let g = Double((hex >> 8) & 0xFF) / 255
        let b = Double(hex & 0xFF) / 255
        self.init(.sRGB, red: r, green: g, blue: b, opacity: opacity)
    }
}
