import SwiftUI
import JuliusCore

public struct InputBarView: View {
    @Binding public var text: String
    @Binding public var attachments: [Attachment]
    public let model: AIModel
    public let effort: EffortLevel
    public let isRecording: Bool
    public let audioPower: Float
    public let isGenerating: Bool
    public let onOpenAddMenu: () -> Void
    public let onOpenModelSelector: () -> Void
    public let onToggleVoiceRecording: () -> Void
    public let onOpenVoiceMode: () -> Void
    public let onStopGeneration: () -> Void
    public let onRemoveAttachment: ((Attachment) -> Void)?
    public let onSend: () -> Void

    @FocusState private var isInputFocused: Bool
    @State private var inputHeight: CGFloat = 28

    public init(
        text: Binding<String>,
        attachments: Binding<[Attachment]> = .constant([]),
        model: AIModel = .sonnet,
        effort: EffortLevel = .medium,
        isRecording: Bool = false,
        audioPower: Float = 0.5,
        isGenerating: Bool = false,
        onOpenAddMenu: @escaping () -> Void,
        onOpenModelSelector: @escaping () -> Void,
        onToggleVoiceRecording: @escaping () -> Void,
        onOpenVoiceMode: @escaping () -> Void,
        onStopGeneration: @escaping () -> Void,
        onRemoveAttachment: ((Attachment) -> Void)? = nil,
        onSend: @escaping () -> Void
    ) {
        self._text = text
        self._attachments = attachments
        self.model = model
        self.effort = effort
        self.isRecording = isRecording
        self.audioPower = audioPower
        self.isGenerating = isGenerating
        self.onOpenAddMenu = onOpenAddMenu
        self.onOpenModelSelector = onOpenModelSelector
        self.onToggleVoiceRecording = onToggleVoiceRecording
        self.onOpenVoiceMode = onOpenVoiceMode
        self.onStopGeneration = onStopGeneration
        self.onRemoveAttachment = onRemoveAttachment
        self.onSend = onSend
    }

    public var body: some View {
        VStack(spacing: 8) {
            // Main Input Container Card (Transparent & G2 Continuous Squircle)
            VStack(alignment: .leading, spacing: 10) {
                // ── Uploaded Attachments Preview (Rendered above text input) ──
                if !attachments.isEmpty {
                    VStack(spacing: 6) {
                        ForEach(attachments) { attachment in
                            AttachmentCardView(attachment: attachment) {
                                if let onRemove = onRemoveAttachment {
                                    onRemove(attachment)
                                } else {
                                    attachments.removeAll(where: { $0.id == attachment.id })
                                }
                            }
                        }
                    }
                    .padding(.horizontal, 12)
                    .padding(.top, 12)
                }

                // Text Input Area or Live Transcribing Preview
                if isRecording {
                    HStack {
                        Text(text.isEmpty ? "Listening to voice..." : text)
                            .font(JuliusTheme.sansRegular(size: 15))
                            .foregroundColor(JuliusTheme.brandGold.opacity(0.85))
                            .lineLimit(2)
                            .padding(.horizontal, 16)
                            .padding(.top, attachments.isEmpty ? 14 : 4)
                            .padding(.bottom, 4)
                        Spacer()
                    }
                } else {
                    ZStack(alignment: .leading) {
                        if text.isEmpty {
                            Text("Ask Julius...")
                                .font(JuliusTheme.sansRegular(size: 15.5))
                                .foregroundColor(Color.white.opacity(0.38))
                                .padding(.horizontal, 14)
                                .padding(.top, attachments.isEmpty ? 6 : 2)
                                .allowsHitTesting(false)
                        }

                        ScrollableTextInputView(
                            text: $text,
                            dynamicHeight: $inputHeight,
                            placeholder: "Ask Julius...",
                            minHeight: 28,
                            maxHeight: 135,
                            onSend: {
                                if !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || !attachments.isEmpty {
                                    onSend()
                                }
                            }
                        )
                        .frame(height: inputHeight)
                        .padding(.horizontal, 10)
                        .padding(.top, attachments.isEmpty ? 6 : 2)
                        .padding(.bottom, 2)
                    }
                    .animation(.spring(response: 0.25, dampingFraction: 0.85), value: inputHeight)
                }

                // Bottom Control Bar
                if isRecording {
                    // ── Active Voice Recording State ──────────────────────────────
                    HStack(spacing: 12) {
                        // Cancel (X)
                        Button(action: onToggleVoiceRecording) {
                            ZStack {
                                Circle()
                                    .fill(Color.clear)
                                    .frame(width: 38, height: 38)
                                Circle()
                                    .stroke(JuliusTheme.brandGold.opacity(0.35), lineWidth: 1)
                                    .frame(width: 38, height: 38)
                                Image(systemName: "xmark")
                                    .font(.system(size: 15, weight: .semibold))
                                    .foregroundColor(.white)
                            }
                        }
                        .buttonStyle(.plain)

                        // Live Dynamic Audio Waveform Bars (#C8B896 Brand Gold)
                        DynamicWaveformView(power: audioPower, barCount: 24, maxHeight: 24, color: JuliusTheme.brandGold)
                            .frame(maxWidth: .infinity)

                        // Stop Button (■)
                        Button(action: onToggleVoiceRecording) {
                            ZStack {
                                Circle()
                                    .fill(Color.clear)
                                    .frame(width: 38, height: 38)
                                Circle()
                                    .stroke(JuliusTheme.brandGold.opacity(0.35), lineWidth: 1)
                                    .frame(width: 38, height: 38)
                                RoundedRectangle(cornerRadius: 3)
                                    .fill(Color.white)
                                    .frame(width: 14, height: 14)
                            }
                        }
                        .buttonStyle(.plain)

                        // Send Voice Button (↑)
                        Button(action: onSend) {
                            ZStack {
                                Circle()
                                    .fill(JuliusTheme.brandGold)
                                    .frame(width: 38, height: 38)
                                Image(systemName: "arrow.up")
                                    .font(.system(size: 17, weight: .bold))
                                    .foregroundColor(JuliusTheme.bgDeep)
                            }
                        }
                        .buttonStyle(.plain)
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 8)
                } else {
                    // ── Standard Input State: Attachment [+] on left; Model Type Pill & Action on right ──
                    HStack(spacing: 8) {
                        // Attachment Button (+) with White icon and #C8B896 border
                        Button(action: onOpenAddMenu) {
                            ZStack {
                                Circle()
                                    .fill(Color.clear)
                                    .frame(width: 34, height: 34)
                                Circle()
                                    .stroke(JuliusTheme.brandGold.opacity(0.35), lineWidth: 1)
                                    .frame(width: 34, height: 34)
                                Image(systemName: "plus")
                                    .font(.system(size: 15, weight: .medium))
                                    .foregroundColor(.white)
                            }
                        }
                        .buttonStyle(.plain)

                        Spacer()

                        // Model Type Pill — Fixed permanent size (154x32) with auto-scaling text
                        Button(action: onOpenModelSelector) {
                            HStack(spacing: 4) {
                                (
                                    Text("\(model.name) ")
                                        .font(JuliusTheme.sansBold(size: 11.5))
                                        .foregroundColor(.white)
                                    + Text(effort.rawValue)
                                        .font(JuliusTheme.sansRegular(size: 10.5))
                                        .foregroundColor(JuliusTheme.textSecondary)
                                )
                                .lineLimit(1)
                                .minimumScaleFactor(0.70)

                                Image(systemName: "chevron.down")
                                    .font(.system(size: 8.5, weight: .semibold))
                                    .foregroundColor(.white)
                            }
                            .padding(.horizontal, 10)
                            .frame(width: 154, height: 32)
                            .background(Color.clear)
                            .overlay(
                                Capsule()
                                    .stroke(JuliusTheme.brandGold.opacity(0.35), lineWidth: 1)
                            )
                            .clipShape(Capsule())
                        }
                        .buttonStyle(.plain)

                        // Action Controls on the FAR RIGHT
                        if isGenerating {
                            // Stop Generation Button (■)
                            Button(action: onStopGeneration) {
                                ZStack {
                                    Circle()
                                        .fill(Color.clear)
                                        .frame(width: 34, height: 34)
                                    Circle()
                                        .stroke(JuliusTheme.brandGold.opacity(0.35), lineWidth: 1)
                                        .frame(width: 34, height: 34)
                                    RoundedRectangle(cornerRadius: 3)
                                        .fill(Color.white)
                                        .frame(width: 12, height: 12)
                                }
                                .frame(width: 34, height: 34)
                            }
                            .buttonStyle(.plain)
                        } else if text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && attachments.isEmpty {
                            // Dictation Microphone Button on the FAR RIGHT
                            Button(action: onToggleVoiceRecording) {
                                ZStack {
                                    Circle()
                                        .fill(Color.clear)
                                        .frame(width: 34, height: 34)
                                    Circle()
                                        .stroke(JuliusTheme.brandGold.opacity(0.35), lineWidth: 1)
                                        .frame(width: 34, height: 34)
                                    Image(systemName: "mic.fill")
                                        .font(.system(size: 15))
                                        .foregroundColor(.white)
                                }
                            }
                            .buttonStyle(.plain)
                        } else {
                            // Active Send Button on the FAR RIGHT
                            Button(action: onSend) {
                                ZStack {
                                    Circle()
                                        .fill(JuliusTheme.brandGold)
                                        .frame(width: 34, height: 34)
                                        .shadow(color: JuliusTheme.brandGold.opacity(0.35), radius: 6, x: 0, y: 2)
                                    Image(systemName: "arrow.up")
                                        .font(.system(size: 15, weight: .bold))
                                        .foregroundColor(JuliusTheme.bgDeep)
                                }
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .padding(.horizontal, 8)
                    .padding(.bottom, 8)
                }
            }
            .background(
                RoundedRectangle(cornerRadius: JuliusTheme.radiusXl, style: .continuous)
                    .fill(Color.white.opacity(0.03))
            )
            .overlay(
                RoundedRectangle(cornerRadius: JuliusTheme.radiusXl, style: .continuous)
                    .stroke(JuliusTheme.brandGold.opacity(0.22), lineWidth: 1)
            )
            .padding(.horizontal, 16)
        }
    }
}
