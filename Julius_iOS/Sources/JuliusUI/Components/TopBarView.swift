import SwiftUI
import JuliusCore

public struct TopBarView: View {
    public let title: String?
    public let isChatActive: Bool
    public let isCovert: Bool
    public let onOpenDrawer: () -> Void
    public let onOpenCovert: () -> Void
    public let onNewChat: () -> Void
    public let onMoreOptions: () -> Void

    public init(
        title: String? = nil,
        isChatActive: Bool = false,
        isCovert: Bool = false,
        onOpenDrawer: @escaping () -> Void,
        onOpenCovert: @escaping () -> Void = {},
        onNewChat: @escaping () -> Void = {},
        onMoreOptions: @escaping () -> Void = {}
    ) {
        self.title = title
        self.isChatActive = isChatActive
        self.isCovert = isCovert
        self.onOpenDrawer = onOpenDrawer
        self.onOpenCovert = onOpenCovert
        self.onNewChat = onNewChat
        self.onMoreOptions = onMoreOptions
    }

    // Compatibility initializer for previous callers
    public init(
        title: String? = nil,
        isChatActive: Bool = false,
        isIncognito: Bool,
        onOpenDrawer: @escaping () -> Void,
        onOpenIncognito: @escaping () -> Void = {},
        onNewChat: @escaping () -> Void = {},
        onMoreOptions: @escaping () -> Void = {}
    ) {
        self.init(
            title: title,
            isChatActive: isChatActive,
            isCovert: isIncognito,
            onOpenDrawer: onOpenDrawer,
            onOpenCovert: onOpenIncognito,
            onNewChat: onNewChat,
            onMoreOptions: onMoreOptions
        )
    }

    public var body: some View {
        HStack {
            // Left: Transparent Hamburger Menu Icon (Main Colour #C8B896)
            Button(action: onOpenDrawer) {
                VStack(spacing: 4.5) {
                    RoundedRectangle(cornerRadius: 1)
                        .fill(JuliusTheme.brandGold)
                        .frame(width: 20, height: 2)
                    RoundedRectangle(cornerRadius: 1)
                        .fill(JuliusTheme.brandGold)
                        .frame(width: 20, height: 2)
                    RoundedRectangle(cornerRadius: 1)
                        .fill(JuliusTheme.brandGold)
                        .frame(width: 20, height: 2)
                }
                .frame(width: 44, height: 44)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)

            Spacer()

            if let title = title, !title.isEmpty {
                Text(title)
                    .font(JuliusTheme.sansBold(size: 16))
                    .foregroundColor(JuliusTheme.textPrimary)
                    .lineLimit(1)
            }

            Spacer()

            // Right Action Button (Transparent, Main Colour #C8B896)
            if isCovert {
                // Close Covert Button (Transparent & White xmark)
                Button(action: onNewChat) {
                    Image(systemName: "xmark")
                        .font(.system(size: 16, weight: .bold))
                        .foregroundColor(.white)
                        .frame(width: 44, height: 44)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
            } else if isChatActive {
                // Transfluid Capsule with New Chat bubble + More Options (•••) in Pure White
                HStack(spacing: 12) {
                    Button(action: onNewChat) {
                        Image(systemName: "plus.bubble.fill")
                            .font(.system(size: 16))
                            .foregroundColor(.white)
                    }
                    .buttonStyle(.plain)

                    Button(action: onMoreOptions) {
                        Image(systemName: "ellipsis")
                            .font(.system(size: 16, weight: .bold))
                            .foregroundColor(.white)
                    }
                    .buttonStyle(.plain)
                }
                .padding(.horizontal, 13)
                .padding(.vertical, 7)
                .background(Color.white.opacity(0.06))
                .overlay(
                    Capsule().stroke(Color.white.opacity(0.18), lineWidth: 1)
                )
                .clipShape(Capsule())
            } else {
                // Transparent Covert Icon Button for Covert Chat (White icon per user specification)
                Button(action: onOpenCovert) {
                    CovertIconView(size: 24, color: .white)
                        .frame(width: 44, height: 44)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 6)
        .background(Color.clear)
    }
}
