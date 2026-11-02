import SwiftUI
import JuliusCore
import JuliusUI

public struct ArtifactExportSheet: View {
    public let artifact: Artifact
    public let onClose: () -> Void

    public init(artifact: Artifact, onClose: @escaping () -> Void) {
        self.artifact = artifact
        self.onClose = onClose
    }

    public var body: some View {
        VStack(spacing: 0) {
            // Drag Indicator Handle
            Capsule()
                .fill(ClaudeTheme.textFaint)
                .frame(width: 36, height: 4)
                .padding(.top, 10)
                .padding(.bottom, 12)

            // Header: Title & Close (X)
            HStack {
                Text(artifact.title)
                    .font(JuliusTheme.sansBold(size: 18))
                    .foregroundColor(JuliusTheme.textPrimary)
                    .lineLimit(1)
                Spacer()
                Button(action: onClose) {
                    ZStack {
                        Circle()
                            .fill(Color.clear)
                            .frame(width: 36, height: 36)
                        Circle()
                            .stroke(JuliusTheme.brandGold.opacity(0.35), lineWidth: 1)
                            .frame(width: 36, height: 36)
                        Image(systemName: "xmark")
                            .font(.system(size: 14, weight: .bold))
                            .foregroundColor(JuliusTheme.brandGold)
                    }
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 20)
            .padding(.bottom, 6)

            // Subtitle
            HStack {
                Text("Sharing isn't included in your plan, but you can export a copy.")
                    .font(JuliusTheme.sansRegular(size: 14))
                    .foregroundColor(JuliusTheme.textSecondary)
                Spacer()
            }
            .padding(.horizontal, 20)
            .padding(.bottom, 24)

            // Export Options
            VStack(spacing: 12) {
                // HTML Option
                Button(action: {
                    exportFile(ext: "html")
                }) {
                    HStack(spacing: 16) {
                        ZStack {
                            RoundedRectangle(cornerRadius: JuliusTheme.radiusMd, style: .continuous)
                                .fill(Color.white.opacity(0.04))
                                .frame(width: 44, height: 44)
                            Image(systemName: "chevron.left.forwardslash.chevron.right")
                                .font(.system(size: 16, weight: .semibold))
                                .foregroundColor(JuliusTheme.brandGold)
                        }

                        VStack(alignment: .leading, spacing: 3) {
                            Text("HTML")
                                .font(JuliusTheme.sansBold(size: 16))
                                .foregroundColor(JuliusTheme.textPrimary)
                            Text("Standalone web page")
                                .font(JuliusTheme.sansRegular(size: 13))
                                .foregroundColor(JuliusTheme.textSecondary)
                        }

                        Spacer()

                        Image(systemName: "arrow.down.to.line")
                            .font(.system(size: 17))
                            .foregroundColor(JuliusTheme.brandGold)
                    }
                    .padding(14)
                    .background(
                        RoundedRectangle(cornerRadius: JuliusTheme.radiusXl, style: .continuous)
                            .fill(Color.white.opacity(0.03))
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: JuliusTheme.radiusXl, style: .continuous)
                            .stroke(JuliusTheme.brandGold.opacity(0.22), lineWidth: 1)
                    )
                }
                .buttonStyle(.plain)

                // Markdown Option
                Button(action: {
                    exportFile(ext: "md")
                }) {
                    HStack(spacing: 16) {
                        ZStack {
                            RoundedRectangle(cornerRadius: JuliusTheme.radiusMd, style: .continuous)
                                .fill(Color.white.opacity(0.04))
                                .frame(width: 44, height: 44)
                            Image(systemName: "arrow.down.doc")
                                .font(.system(size: 17))
                                .foregroundColor(JuliusTheme.brandGold)
                        }

                        VStack(alignment: .leading, spacing: 3) {
                            Text("Markdown")
                                .font(JuliusTheme.sansBold(size: 16))
                                .foregroundColor(JuliusTheme.textPrimary)
                            Text("Plain-text .md file")
                                .font(JuliusTheme.sansRegular(size: 13))
                                .foregroundColor(JuliusTheme.textSecondary)
                        }

                        Spacer()

                        Image(systemName: "arrow.down.to.line")
                            .font(.system(size: 17))
                            .foregroundColor(JuliusTheme.brandGold)
                    }
                    .padding(14)
                    .background(
                        RoundedRectangle(cornerRadius: JuliusTheme.radiusXl, style: .continuous)
                            .fill(Color.white.opacity(0.03))
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: JuliusTheme.radiusXl, style: .continuous)
                            .stroke(JuliusTheme.brandGold.opacity(0.22), lineWidth: 1)
                    )
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 20)
            .padding(.bottom, 28)
        }
        .background(ClaudeTheme.bgCanvas)
    }

    private func exportFile(ext: String) {
        // Replicate to Julius home directory
        Task {
            await CloudStorageManager.shared.syncArtifact(artifact: artifact)
        }
        onClose()
    }
}

