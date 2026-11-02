import SwiftUI
import JuliusCore

public struct AttachmentCardView: View {
    public let attachment: Attachment
    public var onRemove: (() -> Void)? = nil

    public init(attachment: Attachment, onRemove: (() -> Void)? = nil) {
        self.attachment = attachment
        self.onRemove = onRemove
    }

    private var isPDF: Bool {
        attachment.type.contains("pdf") || attachment.name.lowercased().hasSuffix(".pdf")
    }

    private var isImage: Bool {
        attachment.type.contains("image") || ["png", "jpg", "jpeg", "webp"].contains(attachment.name.split(separator: ".").last?.lowercased() ?? "")
    }

    public var body: some View {
        HStack(spacing: 12) {
            // Document Type Badge
            if isPDF {
                ZStack {
                    RoundedRectangle(cornerRadius: 6, style: .continuous)
                        .fill(Color(red: 0.86, green: 0.22, blue: 0.22)) // Authentic Red PDF badge
                        .frame(width: 36, height: 36)
                    VStack(spacing: 1) {
                        Image(systemName: "doc.fill")
                            .font(.system(size: 12, weight: .bold))
                            .foregroundColor(.white)
                        Text("PDF")
                            .font(.system(size: 8, weight: .black, design: .rounded))
                            .foregroundColor(.white)
                    }
                }
            } else if isImage {
                ZStack {
                    RoundedRectangle(cornerRadius: 6, style: .continuous)
                        .fill(JuliusTheme.brandGold.opacity(0.18))
                        .frame(width: 36, height: 36)
                    Image(systemName: "photo.fill")
                        .font(.system(size: 16))
                        .foregroundColor(JuliusTheme.brandGold)
                }
            } else {
                ZStack {
                    RoundedRectangle(cornerRadius: 6, style: .continuous)
                        .fill(Color.white.opacity(0.08))
                        .frame(width: 36, height: 36)
                    Image(systemName: "doc.text.fill")
                        .font(.system(size: 16))
                        .foregroundColor(JuliusTheme.brandGold)
                }
            }

            // File Name & Workspace Status
            VStack(alignment: .leading, spacing: 3) {
                Text(attachment.name)
                    .font(JuliusTheme.sansBold(size: 13.5))
                    .foregroundColor(JuliusTheme.textPrimary)
                    .lineLimit(1)

                HStack(spacing: 4) {
                    Image(systemName: "checkmark.icloud.fill")
                        .font(.system(size: 10))
                        .foregroundColor(JuliusTheme.electricGreen)
                    Text("Workspace synced")
                        .font(JuliusTheme.sansRegular(size: 11))
                        .foregroundColor(JuliusTheme.textSecondary)
                }
            }

            Spacer()

            // Optional Dismiss / Remove (x) Button
            if let onRemove = onRemove {
                Button(action: onRemove) {
                    Image(systemName: "xmark.circle.fill")
                        .font(.system(size: 18))
                        .foregroundColor(Color.white.opacity(0.55))
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 9)
        .background(
            RoundedRectangle(cornerRadius: JuliusTheme.radiusMd, style: .continuous)
                .fill(Color.white.opacity(0.04))
        )
        .overlay(
            RoundedRectangle(cornerRadius: JuliusTheme.radiusMd, style: .continuous)
                .stroke(JuliusTheme.brandGold.opacity(0.35), lineWidth: 1)
        )
    }
}

