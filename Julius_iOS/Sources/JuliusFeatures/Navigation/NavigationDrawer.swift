import SwiftUI
import JuliusCore
import JuliusUI

#if os(iOS)
import UIKit
#endif

public struct NavigationDrawer: View {
    public let sessions: [Session]
    public let selectedSessionId: UUID?
    public let activeTab: String
    public let onSelectSession: (Session) -> Void
    public let onSelectTab: (String) -> Void
    public let onNewChat: () -> Void
    public let onClose: () -> Void

    public init(
        sessions: [Session],
        selectedSessionId: UUID?,
        activeTab: String = "Chats",
        onSelectSession: @escaping (Session) -> Void,
        onSelectTab: @escaping (String) -> Void = { _ in },
        onNewChat: @escaping () -> Void,
        onClose: @escaping () -> Void
    ) {
        self.sessions = sessions
        self.selectedSessionId = selectedSessionId
        self.activeTab = activeTab
        self.onSelectSession = onSelectSession
        self.onSelectTab = onSelectTab
        self.onNewChat = onNewChat
        self.onClose = onClose
    }

    public var body: some View {
        ZStack(alignment: .leading) {
            // Backdrop Scrim
            Color.black.opacity(0.65)
                .ignoresSafeArea()
                .onTapGesture {
                    onClose()
                }

            // Left Slide Drawer Container
            VStack(alignment: .leading, spacing: 0) {
                // Header: Julius Master Mark (Green) + Name (Straight Alignment & Centered)
                HStack(alignment: .center, spacing: 10) {
                    Spacer()
                    JuliusMasterMarkView(size: 24, color: JuliusTheme.electricGreen, withBadge: false)
                        .alignmentGuide(VerticalAlignment.center) { d in d[VerticalAlignment.center] }
                    Text("Julius")
                        .font(JuliusTheme.serifTitle(size: 26))
                        .foregroundColor(JuliusTheme.textPrimary)
                        .alignmentGuide(VerticalAlignment.center) { d in d[VerticalAlignment.center] }
                    Spacer()
                }
                .padding(.top, 54)
                .padding(.bottom, 20)

                // Recents Section Header with "+ New Chat" Button
                HStack {
                    Text("Recents")
                        .font(JuliusTheme.sansRegular(size: 14))
                        .foregroundColor(JuliusTheme.textSecondary)
                    Spacer()
                    Button(action: {
                        onNewChat()
                        onClose()
                    }) {
                        HStack(spacing: 4) {
                            Image(systemName: "plus")
                                .font(.system(size: 11, weight: .bold))
                            Text("New")
                                .font(JuliusTheme.sansBold(size: 12))
                        }
                        .foregroundColor(JuliusTheme.brandGold)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(JuliusTheme.brandGold.opacity(0.12))
                        .clipShape(Capsule())
                    }
                    .buttonStyle(.plain)
                }
                .padding(.horizontal, 24)
                .padding(.bottom, 10)

                // Scrollable Recents List (100% Transparent rows, G2 continuous squircle edges)
                ScrollView(showsIndicators: false) {
                    if sessions.isEmpty {
                        VStack(spacing: 8) {
                            Text("No recent conversations")
                                .font(JuliusTheme.sansRegular(size: 13))
                                .foregroundColor(JuliusTheme.textFaint)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.horizontal, 24)
                        .padding(.vertical, 12)
                    } else {
                        VStack(alignment: .leading, spacing: 4) {
                            ForEach(sessions) { session in
                                Button(action: {
                                    onSelectSession(session)
                                    onClose()
                                }) {
                                    HStack(spacing: 14) {
                                        Image(systemName: "bubble.left")
                                            .font(.system(size: 15))
                                            .foregroundColor(.white.opacity(0.85)) // Icons in white
                                        Text(session.title)
                                            .font(JuliusTheme.sansRegular(size: 15))
                                            .foregroundColor(selectedSessionId == session.id ? JuliusTheme.textPrimary : JuliusTheme.textSecondary)
                                            .lineLimit(1)
                                        Spacer()
                                    }
                                    .padding(.horizontal, 16)
                                    .padding(.vertical, 10)
                                    .background(
                                        RoundedRectangle(cornerRadius: JuliusTheme.radiusMd, style: .continuous)
                                            .fill(selectedSessionId == session.id ? Color.white.opacity(0.04) : Color.clear)
                                    )
                                    .overlay(
                                        RoundedRectangle(cornerRadius: JuliusTheme.radiusMd, style: .continuous)
                                            .stroke(selectedSessionId == session.id ? JuliusTheme.brandGold.opacity(0.4) : Color.clear, lineWidth: 1)
                                    )
                                }
                                .buttonStyle(.plain)
                                .padding(.horizontal, 12)
                            }
                        }
                    }
                }

                Spacer()

                // Primary Menu Items at Bottom: Chats, Code, Projects, Library (Centered per user specification)
                VStack(alignment: .center, spacing: 10) {
                    Button(action: { onSelectTab("Chats"); onClose() }) {
                        NavigationRow(icon: "bubble.left", label: "Chats", isSelected: activeTab == "Chats")
                    }
                    .buttonStyle(.plain)

                    Button(action: { onSelectTab("Code"); onClose() }) {
                        NavigationRow(icon: "chevron.left.forwardslash.chevron.right", label: "Code", isSelected: activeTab == "Code")
                    }
                    .buttonStyle(.plain)

                    Button(action: { onSelectTab("Projects"); onClose() }) {
                        NavigationRow(icon: "archivebox", label: "Projects", isSelected: activeTab == "Projects")
                    }
                    .buttonStyle(.plain)

                    Button(action: { onSelectTab("Library"); onClose() }) {
                        NavigationRow(icon: "books.vertical", label: "Library", isSelected: activeTab == "Library")
                    }
                    .buttonStyle(.plain)
                }
                .frame(maxWidth: .infinity, alignment: .center)
                .padding(.horizontal, 20)
                .padding(.bottom, 24)

                // Bottom Footer: User Avatar Profile (Centered vertically with profile, no sub-label)
                HStack(spacing: 14) {
                    // Circular DJ Profile
                    ZStack {
                        Circle()
                            .fill(Color.white.opacity(0.06))
                            .frame(width: 42, height: 42)
                        Circle()
                            .stroke(JuliusTheme.brandGold.opacity(0.4), lineWidth: 1)
                            .frame(width: 42, height: 42)
                        Text("DJ")
                            .font(JuliusTheme.sansBold(size: 15))
                            .foregroundColor(.white)
                    }

                    Text("David Julius")
                        .font(JuliusTheme.sansBold(size: 16))
                        .foregroundColor(JuliusTheme.textPrimary)

                    Spacer()
                }
                .padding(.horizontal, 20)
                .padding(.bottom, 28)
            }
            #if os(iOS)
            .frame(width: min(320, UIScreen.main.bounds.width * 0.82))
            #else
            .frame(width: 310)
            #endif
            .background(JuliusTheme.surface)
            .ignoresSafeArea()
        }
    }
}

private struct NavigationRow: View {
    let icon: String
    let label: String
    var isSelected: Bool = false

    var body: some View {
        HStack(spacing: 12) {
            Spacer()
            Image(systemName: icon)
                .font(.system(size: 16))
                .foregroundColor(.white) // Icons in white
            Text(label)
                .font(JuliusTheme.sansRegular(size: 16))
                .foregroundColor(isSelected ? JuliusTheme.textPrimary : JuliusTheme.textSecondary)
            Spacer()
        }
        .padding(.vertical, 8)
        .background(
            RoundedRectangle(cornerRadius: JuliusTheme.radiusMd, style: .continuous)
                .fill(isSelected ? Color.white.opacity(0.06) : Color.clear)
        )
        .overlay(
            RoundedRectangle(cornerRadius: JuliusTheme.radiusMd, style: .continuous)
                .stroke(isSelected ? JuliusTheme.brandGold.opacity(0.35) : Color.clear, lineWidth: 1)
        )
    }
}
