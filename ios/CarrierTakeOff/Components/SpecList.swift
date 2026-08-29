import SwiftUI

/// 参数键值列表（对齐 spec-list）
struct SpecListView: View {
    let items: [SpecItem]
    var emptyText: String = "暂无数据"

    var body: some View {
        if items.isEmpty {
            Text(emptyText)
                .font(.system(size: 12, design: .monospaced))
                .foregroundStyle(AppTheme.muted)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.top, 8)
        } else {
            VStack(spacing: 0) {
                ForEach(items) { item in
                    HStack(alignment: .top) {
                        Text(item.label)
                            .font(.system(size: 11, design: .monospaced))
                            .foregroundStyle(AppTheme.muted)
                            .frame(maxWidth: .infinity, alignment: .leading)
                        Text(item.value)
                            .font(.system(size: 12, design: .monospaced))
                            .foregroundStyle(AppTheme.text)
                            .multilineTextAlignment(.trailing)
                    }
                    .padding(.vertical, 7)
                    Rectangle()
                        .fill(AppTheme.border)
                        .frame(height: 1)
                }
            }
            .padding(.top, 4)
        }
    }
}

/// 面板容器（战术终端直角边框）
struct CardView<Content: View>: View {
    let title: String
    var tag: String = "PANEL"
    var trailingSummary: String? = nil
    @ViewBuilder var content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .firstTextBaseline, spacing: 10) {
                Text(title.uppercased())
                    .font(.system(size: 10, weight: .regular, design: .monospaced))
                    .foregroundStyle(AppTheme.muted)
                    .tracking(2)
                Text(tag)
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(AppTheme.accent)
                    .tracking(1)
                Spacer(minLength: 8)
                if let trailingSummary, !trailingSummary.isEmpty {
                    Text(trailingSummary)
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundStyle(AppTheme.accent)
                        .multilineTextAlignment(.trailing)
                }
            }
            content
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(AppTheme.surface)
        .overlay(Rectangle().stroke(AppTheme.border, lineWidth: 1))
    }
}

/// 状态条
struct StatusBar: View {
    let text: String
    let kind: StatusKind

    var body: some View {
        if !text.isEmpty {
            Text(text)
                .font(.system(size: 11, design: .monospaced))
                .foregroundStyle(fg)
                .tracking(0.5)
                .padding(.horizontal, 12)
                .padding(.vertical, 10)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(AppTheme.surface2)
                .overlay(Rectangle().stroke(border, lineWidth: 1))
        }
    }

    private var fg: Color {
        switch kind {
        case .ok: return AppTheme.success
        case .error: return AppTheme.danger
        case .loading: return AppTheme.accent
        case .idle: return AppTheme.muted
        case .stale: return Color(hex: 0xFBBF24)
        }
    }

    private var border: Color {
        switch kind {
        case .ok: return AppTheme.success.opacity(0.35)
        case .error: return AppTheme.danger.opacity(0.35)
        case .loading: return AppTheme.accent.opacity(0.35)
        case .idle: return AppTheme.border
        case .stale: return Color(hex: 0xFBBF24).opacity(0.45)
        }
    }
}

/// 深色表单输入
struct FieldInput: View {
    let label: String
    @Binding var text: String
    var readonly: Bool = false
    var hint: String? = nil
    var error: String? = nil
    var onEdit: (() -> Void)?

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label)
                .font(.system(size: 11, design: .monospaced))
                .foregroundStyle(AppTheme.muted)
            TextField("", text: $text)
                .font(.system(size: 13, design: .monospaced))
                .keyboardType(.decimalPad)
                .disabled(readonly)
                .padding(.horizontal, 10)
                .padding(.vertical, 9)
                .foregroundStyle(readonly ? AppTheme.muted : AppTheme.text)
                .background(AppTheme.surface2)
                .overlay(Rectangle().stroke((error?.isEmpty == false) ? AppTheme.danger : AppTheme.border, lineWidth: 1))
                .onChange(of: text) { _, _ in
                    if !readonly { onEdit?() }
                }
            if let hint, !hint.isEmpty {
                Text(hint)
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(AppTheme.muted)
            }
            if let error, !error.isEmpty {
                Text(error)
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundStyle(AppTheme.danger)
            }
        }
    }
}
