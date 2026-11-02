import SwiftUI
import JuliusCore

public struct MessageBubbleView: View {
    public let message: Message
    public let onOpenThinkingSummary: () -> Void
    public let onOpenArtifact: (Artifact) -> Void
    public let onActionCopy: () -> Void
    public let onActionShare: () -> Void
    public let onActionSpeak: () -> Void
    public let onActionThumbsUp: () -> Void
    public let onActionThumbsDown: () -> Void
    public let onActionRetry: () -> Void

    @State private var isStepsExpanded: Bool = false
    @State private var copied: Bool = false

    public init(
        message: Message,
        onOpenThinkingSummary: @escaping () -> Void = {},
        onOpenArtifact: @escaping (Artifact) -> Void = { _ in },
        onActionCopy: @escaping () -> Void = {},
        onActionShare: @escaping () -> Void = {},
        onActionSpeak: @escaping () -> Void = {},
        onActionThumbsUp: @escaping () -> Void = {},
        onActionThumbsDown: @escaping () -> Void = {},
        onActionRetry: @escaping () -> Void = {}
    ) {
        self.message = message
        self.onOpenThinkingSummary = onOpenThinkingSummary
        self.onOpenArtifact = onOpenArtifact
        self.onActionCopy = onActionCopy
        self.onActionShare = onActionShare
        self.onActionSpeak = onActionSpeak
        self.onActionThumbsUp = onActionThumbsUp
        self.onActionThumbsDown = onActionThumbsDown
        self.onActionRetry = onActionRetry
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if message.role == .user {
                // ── User Message (Right Aligned Pill Card with Top File Attachment) ──
                HStack {
                    Spacer(minLength: 40)
                    VStack(alignment: .trailing, spacing: 8) {
                        // 1. Attached File Boxes (Carried at top of user message)
                        if !message.attachments.isEmpty {
                            VStack(alignment: .trailing, spacing: 6) {
                                ForEach(message.attachments) { att in
                                    AttachmentCardView(attachment: att, onRemove: nil)
                                        .frame(maxWidth: 320)
                                }
                            }
                        }

                        // 2. User Message Text Bubble
                        if !message.content.isEmpty {
                            Text(message.content)
                                .font(ClaudeTheme.sansRegular(size: 16))
                                .foregroundColor(ClaudeTheme.textPrimary)
                                .padding(.horizontal, 16)
                                .padding(.vertical, 12)
                                .background(
                                    RoundedRectangle(cornerRadius: JuliusTheme.radiusXl, style: .continuous)
                                        .fill(JuliusTheme.userBubbleBg)
                                )
                        }
                    }
                }
            } else {
                // ── Assistant Message (Left Aligned Serif) ───────────────────
                VStack(alignment: .leading, spacing: 14) {
                    // 1. Single Live Agent Execution Bar ("Ran X steps · Y.Ys") — Strictly ABOVE text
                    if let tool = message.toolState ?? (message.thinkingState != nil ? ToolExecutionState(action: "Ran 2 steps · 0.4s") : nil) {
                        VStack(alignment: .leading, spacing: 8) {
                            Button(action: {
                                withAnimation(.spring(response: 0.32, dampingFraction: 0.82)) {
                                    isStepsExpanded.toggle()
                                }
                            }) {
                                HStack(spacing: 6) {
                                    Image(systemName: isStepsExpanded ? "chevron.down" : "chevron.right")
                                        .font(.system(size: 11, weight: .bold))
                                        .foregroundColor(JuliusTheme.textSecondary)

                                    Image(systemName: "doc.text")
                                        .font(.system(size: 12))
                                        .foregroundColor(JuliusTheme.textSecondary)

                                    Text(tool.action)
                                        .font(JuliusTheme.sansRegular(size: 13.5))
                                        .foregroundColor(JuliusTheme.textSecondary)
                                }
                                .contentShape(Rectangle())
                            }
                            .buttonStyle(.plain)

                            // Clean Expanded Thinking Panel: Continuous Left Accent Line (#C8B896), Clean Typography, Same Edges
                            if isStepsExpanded {
                                HStack(alignment: .top, spacing: 12) {
                                    // Vertical accent bar on the left edge (Brand Gold #C8B896)
                                    RoundedRectangle(cornerRadius: 1)
                                        .fill(JuliusTheme.brandGold.opacity(0.55))
                                        .frame(width: 2)

                                    VStack(alignment: .leading, spacing: 6) {
                                        if let thinking = message.thinkingState, !thinking.summary.isEmpty {
                                            Text(thinking.summary)
                                                .font(JuliusTheme.sansRegular(size: 13))
                                                .foregroundColor(Color.white.opacity(0.72))
                                                .lineSpacing(3.5)
                                                .textSelection(.enabled)
                                        }

                                        if let steps = message.thinkingState?.steps, !steps.isEmpty {
                                            VStack(alignment: .leading, spacing: 4) {
                                                ForEach(steps) { step in
                                                    HStack(alignment: .top, spacing: 6) {
                                                        Text("›")
                                                            .font(.system(size: 12, weight: .bold))
                                                            .foregroundColor(JuliusTheme.brandGold)
                                                        Text(step.text)
                                                            .font(JuliusTheme.sansRegular(size: 12.5))
                                                            .foregroundColor(Color.white.opacity(0.68))
                                                    }
                                                }
                                            }
                                            .padding(.top, 2)
                                        }

                                        if !tool.detail.isEmpty {
                                            Text(tool.detail)
                                                .font(.system(size: 11, design: .monospaced))
                                                .foregroundColor(JuliusTheme.textFaint)
                                                .padding(.top, 2)
                                        }
                                    }
                                }
                                .padding(.leading, 6)
                                .padding(.vertical, 4)
                                .transition(.opacity.combined(with: .move(edge: .top)))
                            }
                        }
                    }

                    // 2. Spinning/Pulsing Asterisk Loading Indicator
                    if message.isStreaming && message.content.isEmpty {
                        ClaudeAsteriskView(size: 24, isAnimating: true)
                            .padding(.vertical, 8)
                    }

                    // 3. Artifact Card (When code/artifact is generated)
                    if let artifact = message.artifact {
                        ArtifactCardView(artifact: artifact) {
                            onOpenArtifact(artifact)
                        }
                    }

                    // 4. Assistant Body Text in Rich Markdown Typography
                    if !message.content.isEmpty {
                        RichMarkdownView(message.content)
                    }

                    // 5. Action Row: ONLY Copy, Play, Regenerate in Pure White with NO outer shell
                    if !message.isStreaming && !message.content.isEmpty {
                        HStack(spacing: 14) {
                            // Copy Button (Direct icon, pure white, no outer shell)
                            Button(action: {
                                #if os(macOS)
                                NSPasteboard.general.clearContents()
                                NSPasteboard.general.setString(message.content, forType: .string)
                                #elseif os(iOS)
                                UIPasteboard.general.string = message.content
                                #endif
                                copied = true
                                onActionCopy()
                                DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
                                    copied = false
                                }
                            }) {
                                Image(systemName: copied ? "checkmark" : "doc.on.doc")
                                    .font(.system(size: 14))
                                    .foregroundColor(.white)
                                    .contentShape(Rectangle())
                            }
                            .buttonStyle(.plain)

                            // Play (Read aloud / speech) Button
                            Button(action: onActionSpeak) {
                                Image(systemName: "play.fill")
                                    .font(.system(size: 13))
                                    .foregroundColor(.white)
                                    .contentShape(Rectangle())
                            }
                            .buttonStyle(.plain)

                            // Regenerate Button
                            Button(action: onActionRetry) {
                                Image(systemName: "arrow.clockwise")
                                    .font(.system(size: 13.5))
                                    .foregroundColor(.white)
                                    .contentShape(Rectangle())
                            }
                            .buttonStyle(.plain)
                        }
                        .padding(.top, 4)

                        // 6. Subtle Disclaimer
                        Text("Julius is AI and can make mistakes.")
                            .font(JuliusTheme.sansRegular(size: 12))
                            .foregroundColor(JuliusTheme.textFaint)
                            .padding(.top, 2)
                    }
                }
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 6)
    }
}

