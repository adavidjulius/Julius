import SwiftUI
import JuliusCore

public struct ArtifactCardView: View {
    public let artifact: Artifact
    public let onTap: () -> Void

    public init(artifact: Artifact, onTap: @escaping () -> Void) {
        self.artifact = artifact
        self.onTap = onTap
    }

    public var body: some View {
        Button(action: onTap) {
            HStack(spacing: 14) {
                // Purple Icon Container
                ZStack {
                    RoundedRectangle(cornerRadius: JuliusTheme.radiusMd, style: .continuous)
                        .fill(JuliusTheme.artifactPurple)
                        .frame(width: 46, height: 46)
                    Image(systemName: "puzzlepiece.extension.fill")
                        .font(.system(size: 20))
                        .foregroundColor(JuliusTheme.brandGold)
                }

                // Title and Subtitle
                VStack(alignment: .leading, spacing: 3) {
                    Text(artifact.title)
                        .font(JuliusTheme.sansBold(size: 15))
                        .foregroundColor(JuliusTheme.textPrimary)
                        .lineLimit(1)
                    Text(artifact.subtitle)
                        .font(JuliusTheme.sansRegular(size: 13))
                        .foregroundColor(JuliusTheme.textSecondary)
                }

                Spacer()
            }
            .padding(12)
            .background(
                RoundedRectangle(cornerRadius: JuliusTheme.radiusXl, style: .continuous)
                    .fill(Color.white.opacity(0.04))
            )
            .overlay(
                RoundedRectangle(cornerRadius: JuliusTheme.radiusXl, style: .continuous)
                    .stroke(JuliusTheme.brandGold.opacity(0.25), lineWidth: 1)
            )
        }
    }
}

