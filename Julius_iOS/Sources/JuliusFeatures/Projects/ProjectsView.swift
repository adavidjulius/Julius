import SwiftUI
import JuliusCore
import JuliusUI

public struct ProjectItem: Identifiable, Codable, Sendable, Equatable {
    public let id: UUID
    public var name: String
    public var description: String
    public var createdAt: Date

    public init(id: UUID = UUID(), name: String, description: String = "", createdAt: Date = Date()) {
        self.id = id
        self.name = name
        self.description = description
        self.createdAt = createdAt
    }
}

public struct ProjectsView: View {
    @Binding public var projects: [ProjectItem]
    public let onOpenDrawer: () -> Void
    public let onSelectProject: (ProjectItem) -> Void
    @State private var isCreateProjectOpen: Bool = false

    public init(
        projects: Binding<[ProjectItem]>,
        onOpenDrawer: @escaping () -> Void,
        onSelectProject: @escaping (ProjectItem) -> Void = { _ in }
    ) {
        self._projects = projects
        self.onOpenDrawer = onOpenDrawer
        self.onSelectProject = onSelectProject
    }

    public var body: some View {
        ZStack {
            JuliusTheme.bgCanvas
                .ignoresSafeArea()

            VStack(spacing: 0) {
                // ── Top Bar (Hamburger on Left, Centered Title, Vertical Sliders on Right) ──
                HStack {
                    // Left: Circular dark button with asymmetrical 3-line Hamburger
                    Button(action: onOpenDrawer) {
                        ZStack {
                            Circle()
                                .fill(Color(white: 0.13))
                                .frame(width: 44, height: 44)
                            VStack(alignment: .leading, spacing: 4) {
                                RoundedRectangle(cornerRadius: 1)
                                    .fill(Color.white)
                                    .frame(width: 18, height: 2)
                                RoundedRectangle(cornerRadius: 1)
                                    .fill(Color.white)
                                    .frame(width: 18, height: 2)
                                RoundedRectangle(cornerRadius: 1)
                                    .fill(Color.white)
                                    .frame(width: 12, height: 2)
                            }
                        }
                    }
                    .buttonStyle(.plain)

                    Spacer()

                    // Center: "Projects" Title
                    Text("Projects")
                        .font(JuliusTheme.sansBold(size: 18))
                        .foregroundColor(.white)

                    Spacer()

                    // Right: Circular dark button with Vertical Sliders Filter
                    Button(action: {}) {
                        ZStack {
                            Circle()
                                .fill(Color(white: 0.13))
                                .frame(width: 44, height: 44)
                            HStack(spacing: 3.5) {
                                // Slider 1 (Knob Top)
                                ZStack(alignment: .top) {
                                    Rectangle().fill(Color.white.opacity(0.85)).frame(width: 1.5, height: 16)
                                    Circle().fill(Color.white).frame(width: 5, height: 5).padding(.top, 2)
                                }
                                // Slider 2 (Knob Bottom)
                                ZStack(alignment: .bottom) {
                                    Rectangle().fill(Color.white.opacity(0.85)).frame(width: 1.5, height: 16)
                                    Circle().fill(Color.white).frame(width: 5, height: 5).padding(.bottom, 2)
                                }
                                // Slider 3 (Knob Center)
                                ZStack(alignment: .center) {
                                    Rectangle().fill(Color.white.opacity(0.85)).frame(width: 1.5, height: 16)
                                    Circle().fill(Color.white).frame(width: 5, height: 5)
                                }
                            }
                        }
                    }
                    .buttonStyle(.plain)
                }
                .padding(.horizontal, 18)
                .padding(.top, 10)
                .padding(.bottom, 12)

                if projects.isEmpty {
                    // ── Empty State (Matching Reference Screenshot 1 Exactly) ──
                    Spacer()

                    VStack(spacing: 16) {
                        // Circular dark container with filing tray/box
                        ZStack {
                            Circle()
                                .fill(Color(white: 0.13))
                                .frame(width: 58, height: 58)
                            Image(systemName: "archivebox")
                                .font(.system(size: 22))
                                .foregroundColor(Color(white: 0.6))
                        }

                        Text("No projects yet")
                            .font(JuliusTheme.sansBold(size: 18.5))
                            .foregroundColor(.white)

                        Text("Create one to organize chats around a topic or\nset of documents.")
                            .font(JuliusTheme.sansRegular(size: 14))
                            .foregroundColor(Color(white: 0.6))
                            .multilineTextAlignment(.center)
                            .lineSpacing(4)
                            .padding(.horizontal, 48)
                    }

                    Spacer()
                } else {
                    // ── Active Projects List ──
                    ScrollView {
                        LazyVStack(spacing: 14) {
                            ForEach(projects) { project in
                                Button(action: { onSelectProject(project) }) {
                                    VStack(alignment: .leading, spacing: 8) {
                                        HStack {
                                            Text(project.name)
                                                .font(JuliusTheme.sansBold(size: 16.5))
                                                .foregroundColor(.white)
                                            Spacer()
                                            Image(systemName: "chevron.right")
                                                .font(.system(size: 12))
                                                .foregroundColor(JuliusTheme.textFaint)
                                        }

                                        if !project.description.isEmpty {
                                            Text(project.description)
                                                .font(JuliusTheme.sansRegular(size: 13.5))
                                                .foregroundColor(JuliusTheme.textSecondary)
                                                .lineLimit(2)
                                        }

                                        HStack(spacing: 6) {
                                            Image(systemName: "clock")
                                                .font(.system(size: 10))
                                                .foregroundColor(JuliusTheme.brandGold.opacity(0.8))
                                            Text("Active Project")
                                                .font(JuliusTheme.sansRegular(size: 11))
                                                .foregroundColor(JuliusTheme.brandGold.opacity(0.8))
                                        }
                                        .padding(.top, 2)
                                    }
                                    .padding(16)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                    .background(Color.white.opacity(0.03))
                                    .overlay(
                                        RoundedRectangle(cornerRadius: 16, style: .continuous)
                                            .stroke(JuliusTheme.brandGold.opacity(0.28), lineWidth: 1)
                                    )
                                    .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
                                }
                                .buttonStyle(.plain)
                            }
                        }
                        .padding(16)
                    }
                }

                // ── Floating "+ New project" Button (Pinned Bottom Right) ──
                HStack {
                    Spacer()
                    Button(action: { isCreateProjectOpen = true }) {
                        HStack(spacing: 6) {
                            Image(systemName: "plus")
                                .font(.system(size: 14, weight: .bold))
                            Text("New project")
                                .font(JuliusTheme.sansBold(size: 14.5))
                        }
                        .foregroundColor(.black)
                        .padding(.horizontal, 18)
                        .padding(.vertical, 12)
                        .background(Capsule().fill(Color.white))
                        .shadow(color: Color.black.opacity(0.35), radius: 10, x: 0, y: 5)
                    }
                    .buttonStyle(.plain)
                    .padding(.trailing, 20)
                    .padding(.bottom, 28)
                }
            }
        }
        .background(
            Button("") { isCreateProjectOpen = true }
                .keyboardShortcut("n", modifiers: .command)
                .opacity(0)
        )
        .sheet(isPresented: $isCreateProjectOpen) {
            CreateProjectSheet(onClose: { isCreateProjectOpen = false }) { newProject in
                projects.append(newProject)
                isCreateProjectOpen = false
            }
        }
    }
}
