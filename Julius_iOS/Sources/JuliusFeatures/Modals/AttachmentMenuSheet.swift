import SwiftUI
import JuliusCore
import JuliusUI

public struct AttachmentMenuSheet: View {
    @State private var isMemoryEnabled: Bool = true
    @State private var dragOffset: CGFloat = 0

    public let onCameraTap: () -> Void
    public let onPhotosTap: () -> Void
    public let onFilesTap: () -> Void
    public let onClose: () -> Void

    public init(
        onCameraTap: @escaping () -> Void = {},
        onPhotosTap: @escaping () -> Void = {},
        onFilesTap: @escaping () -> Void = {},
        onClose: @escaping () -> Void
    ) {
        self.onCameraTap = onCameraTap
        self.onPhotosTap = onPhotosTap
        self.onFilesTap = onFilesTap
        self.onClose = onClose
    }

    public var body: some View {
        VStack(spacing: 0) {
            // Glide Flinger Drag Handle (Swipe/fling down to dismiss)
            Capsule()
                .fill(JuliusTheme.brandGold.opacity(0.45))
                .frame(width: 42, height: 5)
                .padding(.top, 12)
                .padding(.bottom, 14)

            // Header: Close (X) & Title
            HStack {
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
                            .foregroundColor(.white)
                    }
                }
                .buttonStyle(.plain)

                Spacer()
                Text("Add to Chat")
                    .font(JuliusTheme.sansBold(size: 17))
                    .foregroundColor(JuliusTheme.textPrimary)
                Spacer()
                Circle().fill(Color.clear).frame(width: 36, height: 36)
            }
            .padding(.horizontal, 16)
            .padding(.bottom, 18)

            VStack(spacing: 12) {
                // 3 Big Action Tiles: Camera, Photos, Files (White icons, #C8B896 borders)
                HStack(spacing: 12) {
                    AttachmentTile(icon: "camera", title: "Camera", action: onCameraTap)
                    AttachmentTile(icon: "photo", title: "Photos", action: onPhotosTap)
                    AttachmentTile(icon: "doc", title: "Files", action: onFilesTap)
                }

                // Add to project Row
                HStack {
                    Image(systemName: "archivebox")
                        .font(.system(size: 16))
                        .foregroundColor(.white)
                    Text("Add to project")
                        .font(JuliusTheme.sansBold(size: 15))
                        .foregroundColor(JuliusTheme.textPrimary)
                    Spacer()
                    Text("None")
                        .font(JuliusTheme.sansRegular(size: 15))
                        .foregroundColor(JuliusTheme.textSecondary)
                    Image(systemName: "chevron.right")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundColor(.white.opacity(0.7))
                }
                .padding(16)
                .background(
                    RoundedRectangle(cornerRadius: JuliusTheme.radiusXl, style: .continuous)
                        .fill(Color.white.opacity(0.03))
                )
                .overlay(
                    RoundedRectangle(cornerRadius: JuliusTheme.radiusXl, style: .continuous)
                        .stroke(JuliusTheme.brandGold.opacity(0.3), lineWidth: 1)
                )

                // Connectors & Memory Container
                VStack(spacing: 0) {
                    HStack {
                        Image(systemName: "square.grid.2x2")
                            .font(.system(size: 16))
                            .foregroundColor(.white)
                        Text("Connectors (MCP & Tools)")
                            .font(JuliusTheme.sansBold(size: 15))
                            .foregroundColor(JuliusTheme.textPrimary)
                        Spacer()
                        Image(systemName: "chevron.right")
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundColor(.white.opacity(0.7))
                    }
                    .padding(16)

                    Divider().background(JuliusTheme.brandGold.opacity(0.12))

                    HStack {
                        Image(systemName: "waveform.path")
                            .font(.system(size: 16))
                            .foregroundColor(.white)
                        Text("Julius Agent Memory")
                            .font(JuliusTheme.sansBold(size: 15))
                            .foregroundColor(JuliusTheme.textPrimary)
                        Spacer()
                        Toggle("", isOn: $isMemoryEnabled)
                            .labelsHidden()
                            .tint(JuliusTheme.brandGold)
                    }
                    .padding(16)
                }
                .background(
                    RoundedRectangle(cornerRadius: JuliusTheme.radiusXl, style: .continuous)
                        .fill(Color.white.opacity(0.03))
                )
                .overlay(
                    RoundedRectangle(cornerRadius: JuliusTheme.radiusXl, style: .continuous)
                        .stroke(JuliusTheme.brandGold.opacity(0.3), lineWidth: 1)
                )
            }
            .padding(.horizontal, 16)
            .padding(.bottom, 24)
        }
        .frame(maxWidth: .infinity)
        .background(JuliusTheme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 24, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 24, style: .continuous)
                .stroke(JuliusTheme.brandGold.opacity(0.3), lineWidth: 1)
        )
        .offset(y: max(0, dragOffset))
        .gesture(
            DragGesture()
                .onChanged { value in
                    if value.translation.height > 0 {
                        dragOffset = value.translation.height
                    }
                }
                .onEnded { value in
                    if value.translation.height > 80 || value.velocity.height > 400 {
                        withAnimation(.easeOut(duration: 0.2)) {
                            onClose()
                        }
                    } else {
                        withAnimation(.spring(response: 0.3, dampingFraction: 0.75)) {
                            dragOffset = 0
                        }
                    }
                }
        )
    }
}

public struct AttachmentTile: View {
    public let icon: String
    public let title: String
    public let action: () -> Void

    public init(icon: String, title: String, action: @escaping () -> Void) {
        self.icon = icon
        self.title = title
        self.action = action
    }

    public var body: some View {
        Button(action: action) {
            VStack(spacing: 12) {
                Image(systemName: icon)
                    .font(.system(size: 24))
                    .foregroundColor(.white)
                Text(title)
                    .font(JuliusTheme.sansBold(size: 14))
                    .foregroundColor(JuliusTheme.textPrimary)
            }
            .frame(maxWidth: .infinity)
            .frame(height: 94)
            .background(
                RoundedRectangle(cornerRadius: JuliusTheme.radiusXl, style: .continuous)
                    .fill(Color.white.opacity(0.03))
            )
            .overlay(
                RoundedRectangle(cornerRadius: JuliusTheme.radiusXl, style: .continuous)
                    .stroke(JuliusTheme.brandGold.opacity(0.35), lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
    }
}
