import SwiftUI
import JuliusCore
import JuliusUI

public struct CovertChatView: View {
    public var session: Session?
    @Binding public var inputText: String
    @Binding public var attachments: [Attachment]
    public let model: AIModel
    public let effort: EffortLevel
    public let isRecording: Bool
    public let audioPower: Float
    public let isGenerating: Bool
    public let onOpenDrawer: () -> Void
    public let onCloseCovert: () -> Void
    public let onOpenAddMenu: () -> Void
    public let onOpenModelSelector: () -> Void
    public let onToggleVoiceRecording: () -> Void
    public let onOpenVoiceMode: () -> Void
    public let onStopGeneration: () -> Void
    public let onSend: () -> Void

    public init(
        session: Session? = nil,
        inputText: Binding<String>,
        attachments: Binding<[Attachment]> = .constant([]),
        model: AIModel = .sonnet,
        effort: EffortLevel = .medium,
        isRecording: Bool = false,
        audioPower: Float = 0.5,
        isGenerating: Bool = false,
        onOpenDrawer: @escaping () -> Void,
        onCloseCovert: @escaping () -> Void,
        onOpenAddMenu: @escaping () -> Void,
        onOpenModelSelector: @escaping () -> Void,
        onToggleVoiceRecording: @escaping () -> Void = {},
        onOpenVoiceMode: @escaping () -> Void = {},
        onStopGeneration: @escaping () -> Void = {},
        onSend: @escaping () -> Void
    ) {
        self.session = session
        self._inputText = inputText
        self._attachments = attachments
        self.model = model
        self.effort = effort
        self.isRecording = isRecording
        self.audioPower = audioPower
        self.isGenerating = isGenerating
        self.onOpenDrawer = onOpenDrawer
        self.onCloseCovert = onCloseCovert
        self.onOpenAddMenu = onOpenAddMenu
        self.onOpenModelSelector = onOpenModelSelector
        self.onToggleVoiceRecording = onToggleVoiceRecording
        self.onOpenVoiceMode = onOpenVoiceMode
        self.onStopGeneration = onStopGeneration
        self.onSend = onSend
    }

    public var body: some View {
        ZStack {
            JuliusTheme.bgCanvas
                .ignoresSafeArea()

            VStack(spacing: 0) {
                // Top Navigation Bar (With Title "Covert chat" and Close X)
                TopBarView(
                    title: "Covert chat",
                    isChatActive: session != nil && !(session?.messages.isEmpty ?? true),
                    isCovert: true,
                    onOpenDrawer: onOpenDrawer,
                    onOpenCovert: onCloseCovert,
                    onNewChat: onCloseCovert
                )

                if let currentSession = session, !currentSession.messages.isEmpty {
                    // Active Covert Chat Thread
                    ScrollViewReader { proxy in
                        ScrollView {
                            LazyVStack(alignment: .leading, spacing: 18) {
                                ForEach(currentSession.messages) { msg in
                                    MessageBubbleView(
                                        message: msg,
                                        onOpenThinkingSummary: {},
                                        onOpenArtifact: { _ in }
                                    )
                                    .id(msg.id)
                                }
                            }
                            .padding(.top, 14)
                            .padding(.bottom, 54)
                        }
                        .onChange(of: currentSession.messages.count) {
                            if let lastId = currentSession.messages.last?.id {
                                withAnimation(.easeOut(duration: 0.25)) {
                                    proxy.scrollTo(lastId, anchor: .bottom)
                                }
                            }
                        }
                    }
                } else {
                    // Center Covert Stealth Emblem (White) & Privacy Notice
                    Spacer()

                    VStack(spacing: 18) {
                        CovertIconView(size: 52, color: .white)

                        (Text("Covert chats operate in zero-retention mode. They aren't saved to history, persistent agent memory, or synced to the cloud workspace. ")
                        + Text("Learn more").underline().foregroundColor(JuliusTheme.brandGold)
                        + Text(" about Julius privacy isolation."))
                            .font(JuliusTheme.sansRegular(size: 15))
                            .foregroundColor(JuliusTheme.textPrimary)
                            .multilineTextAlignment(.center)
                    }
                    .padding(.horizontal, 32)

                    Spacer()
                }

                // Input Bar Container (Transparent & Responsive)
                InputBarView(
                    text: $inputText,
                    attachments: $attachments,
                    model: model,
                    effort: effort,
                    isRecording: isRecording,
                    audioPower: audioPower,
                    isGenerating: isGenerating,
                    onOpenAddMenu: onOpenAddMenu,
                    onOpenModelSelector: onOpenModelSelector,
                    onToggleVoiceRecording: onToggleVoiceRecording,
                    onOpenVoiceMode: onOpenVoiceMode,
                    onStopGeneration: onStopGeneration,
                    onSend: onSend
                )
                .padding(.bottom, 12)
            }
        }
    }
}

public typealias IncognitoChatView = CovertChatView
