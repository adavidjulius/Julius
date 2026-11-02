import SwiftUI
import UniformTypeIdentifiers
import JuliusCore
import JuliusUI

public struct ChatThreadView: View {
    public let session: Session
    @Binding public var inputText: String
    @Binding public var attachments: [Attachment]
    public let isRecording: Bool
    public let audioPower: Float
    public let isGenerating: Bool
    public let onOpenDrawer: () -> Void
    public let onNewChat: () -> Void
    public let onMoreOptions: () -> Void
    public let onOpenAddMenu: () -> Void
    public let onOpenModelSelector: () -> Void
    public let onToggleVoiceRecording: () -> Void
    public let onOpenVoiceMode: () -> Void
    public let onStopGeneration: () -> Void
    public let onOpenThinkingSummary: () -> Void
    public let onOpenArtifact: (Artifact) -> Void
    public let onDropFile: (([NSItemProvider]) -> Bool)?
    public let onSend: () -> Void

    @State private var isDropTargeted: Bool = false

    public init(
        session: Session,
        inputText: Binding<String>,
        attachments: Binding<[Attachment]> = .constant([]),
        isRecording: Bool = false,
        audioPower: Float = 0.5,
        isGenerating: Bool = false,
        onOpenDrawer: @escaping () -> Void,
        onNewChat: @escaping () -> Void,
        onMoreOptions: @escaping () -> Void = {},
        onOpenAddMenu: @escaping () -> Void,
        onOpenModelSelector: @escaping () -> Void,
        onToggleVoiceRecording: @escaping () -> Void,
        onOpenVoiceMode: @escaping () -> Void,
        onStopGeneration: @escaping () -> Void,
        onOpenThinkingSummary: @escaping () -> Void,
        onOpenArtifact: @escaping (Artifact) -> Void,
        onDropFile: (([NSItemProvider]) -> Bool)? = nil,
        onSend: @escaping () -> Void
    ) {
        self.session = session
        self._inputText = inputText
        self._attachments = attachments
        self.isRecording = isRecording
        self.audioPower = audioPower
        self.isGenerating = isGenerating
        self.onOpenDrawer = onOpenDrawer
        self.onNewChat = onNewChat
        self.onMoreOptions = onMoreOptions
        self.onOpenAddMenu = onOpenAddMenu
        self.onOpenModelSelector = onOpenModelSelector
        self.onToggleVoiceRecording = onToggleVoiceRecording
        self.onOpenVoiceMode = onOpenVoiceMode
        self.onStopGeneration = onStopGeneration
        self.onOpenThinkingSummary = onOpenThinkingSummary
        self.onOpenArtifact = onOpenArtifact
        self.onDropFile = onDropFile
        self.onSend = onSend
    }

    public var body: some View {
        ZStack {
            JuliusTheme.bgCanvas
                .ignoresSafeArea()

            VStack(spacing: 0) {
                // Top Navigation Bar (Transparent icons)
                TopBarView(
                    isChatActive: true,
                    isCovert: session.isIncognito,
                    onOpenDrawer: onOpenDrawer,
                    onNewChat: onNewChat,
                    onMoreOptions: onMoreOptions
                )

                // Conversation Message ScrollView
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: 18) {
                            ForEach(session.messages) { msg in
                                MessageBubbleView(
                                    message: msg,
                                    onOpenThinkingSummary: onOpenThinkingSummary,
                                    onOpenArtifact: onOpenArtifact
                                )
                                .id(msg.id)
                            }
                        }
                        .padding(.top, 14)
                        .padding(.bottom, 54)
                    }
                    .onDrop(of: [UTType.fileURL], isTargeted: $isDropTargeted) { providers in
                        if let onDropFile = onDropFile {
                            return onDropFile(providers)
                        }
                        return false
                    }
                    .onChange(of: session.messages.count) {
                        if let lastId = session.messages.last?.id {
                            withAnimation(.easeOut(duration: 0.25)) {
                                proxy.scrollTo(lastId, anchor: .bottom)
                            }
                        }
                    }
                }

                // Sticky Bottom Input Bar
                InputBarView(
                    text: $inputText,
                    attachments: $attachments,
                    model: session.model,
                    effort: session.effort,
                    isRecording: isRecording,
                    audioPower: audioPower,
                    isGenerating: isGenerating,
                    onOpenAddMenu: onOpenAddMenu,
                    onOpenModelSelector: onOpenModelSelector,
                    onToggleVoiceRecording: onToggleVoiceRecording,
                    onOpenVoiceMode: onOpenVoiceMode,
                    onStopGeneration: onStopGeneration,
                    onRemoveAttachment: { att in
                        attachments.removeAll(where: { $0.id == att.id })
                    },
                    onSend: onSend
                )
                .padding(.bottom, 12)
            }
        }
    }
}
