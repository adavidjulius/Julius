import SwiftUI
import JuliusCore
import JuliusUI

public struct LibraryView: View {
    public let artifacts: [Artifact]
    public let onOpenDrawer: () -> Void
    public let onSelectArtifact: (Artifact) -> Void

    @State private var searchText: String = ""

    public init(
        artifacts: [Artifact] = [],
        onOpenDrawer: @escaping () -> Void,
        onSelectArtifact: @escaping (Artifact) -> Void
    ) {
        self.artifacts = artifacts
        self.onOpenDrawer = onOpenDrawer
        self.onSelectArtifact = onSelectArtifact
    }

    private var filteredArtifacts: [Artifact] {
        if searchText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return artifacts
        }
        let q = searchText.lowercased()
        return artifacts.filter {
            $0.title.lowercased().contains(q) ||
            $0.subtitle.lowercased().contains(q) ||
            $0.language.lowercased().contains(q) ||
            $0.content.lowercased().contains(q)
        }
    }

    public var body: some View {
        ZStack {
            JuliusTheme.bgCanvas
                .ignoresSafeArea()

            VStack(spacing: 0) {
                // ── Top Bar (Hamburger on Left, "Library" Title, Sliders on Right) ──
                HStack {
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

                    Text("Library")
                        .font(JuliusTheme.sansBold(size: 18))
                        .foregroundColor(.white)

                    Spacer()

                    Button(action: {}) {
                        ZStack {
                            Circle()
                                .fill(Color(white: 0.13))
                                .frame(width: 44, height: 44)
                            HStack(spacing: 3.5) {
                                ZStack(alignment: .top) {
                                    Rectangle().fill(Color.white.opacity(0.85)).frame(width: 1.5, height: 16)
                                    Circle().fill(Color.white).frame(width: 5, height: 5).padding(.top, 2)
                                }
                                ZStack(alignment: .bottom) {
                                    Rectangle().fill(Color.white.opacity(0.85)).frame(width: 1.5, height: 16)
                                    Circle().fill(Color.white).frame(width: 5, height: 5).padding(.bottom, 2)
                                }
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

                // ── Content Area: Empty State or Dynamic Cards ──
                if filteredArtifacts.isEmpty {
                    Spacer()

                    VStack(spacing: 16) {
                        ZStack {
                            Circle()
                                .fill(Color(white: 0.13))
                                .frame(width: 64, height: 64)
                            Image(systemName: "books.vertical")
                                .font(.system(size: 26))
                                .foregroundColor(JuliusTheme.brandGold)
                        }

                        Text("No Saved Files or Artifacts")
                            .font(JuliusTheme.sansBold(size: 18))
                            .foregroundColor(.white)

                        Text("Code files, documents, and artifacts generated during your conversations will automatically be cataloged here.")
                            .font(JuliusTheme.sansRegular(size: 14))
                            .foregroundColor(Color(white: 0.6))
                            .multilineTextAlignment(.center)
                            .lineSpacing(4)
                            .padding(.horizontal, 40)
                    }

                    Spacer()
                } else {
                    ScrollView(showsIndicators: false) {
                        LazyVStack(spacing: 14) {
                            ForEach(filteredArtifacts) { art in
                                Button(action: { onSelectArtifact(art) }) {
                                    VStack(alignment: .leading, spacing: 10) {
                                        HStack {
                                            Text(art.title)
                                                .font(JuliusTheme.sansBold(size: 16))
                                                .foregroundColor(.white)
                                                .lineLimit(1)
                                            Spacer()
                                            Text(art.language.uppercased())
                                                .font(JuliusTheme.sansBold(size: 10))
                                                .foregroundColor(JuliusTheme.brandGold)
                                                .padding(.horizontal, 6)
                                                .padding(.vertical, 2)
                                                .background(
                                                    RoundedRectangle(cornerRadius: JuliusTheme.radiusSm, style: .continuous)
                                                        .fill(JuliusTheme.brandGold.opacity(0.15))
                                                )
                                        }

                                        Text(art.content.prefix(120).replacingOccurrences(of: "\n", with: " "))
                                            .font(.system(size: 13, design: .monospaced))
                                            .foregroundColor(Color.white.opacity(0.65))
                                            .lineLimit(2)

                                        HStack(spacing: 6) {
                                            Image(systemName: "clock")
                                                .font(.system(size: 10))
                                                .foregroundColor(JuliusTheme.textSecondary)
                                            Text("Active Session Artifact")
                                                .font(JuliusTheme.sansRegular(size: 11))
                                                .foregroundColor(JuliusTheme.textSecondary)
                                        }
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
                        .padding(.horizontal, 16)
                        .padding(.top, 10)
                        .padding(.bottom, 80)
                    }
                }

                // ── Bottom Search Bar (Translucent with Brand Gold Border) ──
                HStack(spacing: 10) {
                    Image(systemName: "magnifyingglass")
                        .font(.system(size: 15))
                        .foregroundColor(JuliusTheme.textSecondary)

                    TextField("", text: $searchText, prompt: Text("Search artifacts").foregroundColor(JuliusTheme.textSecondary))
                        .textFieldStyle(.plain)
                        .font(JuliusTheme.sansRegular(size: 15))
                        .foregroundColor(.white)

                    if !searchText.isEmpty {
                        Button(action: { searchText = "" }) {
                            Image(systemName: "xmark.circle.fill")
                                .font(.system(size: 14))
                                .foregroundColor(JuliusTheme.textSecondary)
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 12)
                .background(Color.white.opacity(0.06))
                .overlay(
                    Capsule().stroke(JuliusTheme.brandGold.opacity(0.35), lineWidth: 1)
                )
                .clipShape(Capsule())
                .padding(.horizontal, 16)
                .padding(.bottom, 24)
            }
        }
    }
}
