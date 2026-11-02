import SwiftUI
import JuliusCore
import JuliusUI

public struct MainHomeView: View {
    @Binding public var inputText: String
    @Binding public var attachments: [Attachment]
    public let model: AIModel
    public let effort: EffortLevel
    public let isRecording: Bool
    public let audioPower: Float
    public let onOpenDrawer: () -> Void
    public let onOpenCovert: () -> Void
    public let onOpenAddMenu: () -> Void
    public let onOpenModelSelector: () -> Void
    public let onToggleVoiceRecording: () -> Void
    public let onOpenVoiceMode: () -> Void
    public let onSend: () -> Void

    public init(
        inputText: Binding<String>,
        attachments: Binding<[Attachment]> = .constant([]),
        model: AIModel = .sonnet,
        effort: EffortLevel = .medium,
        isRecording: Bool = false,
        audioPower: Float = 0.5,
        onOpenDrawer: @escaping () -> Void,
        onOpenCovert: @escaping () -> Void,
        onOpenAddMenu: @escaping () -> Void,
        onOpenModelSelector: @escaping () -> Void,
        onToggleVoiceRecording: @escaping () -> Void,
        onOpenVoiceMode: @escaping () -> Void,
        onSend: @escaping () -> Void
    ) {
        self._inputText = inputText
        self._attachments = attachments
        self.model = model
        self.effort = effort
        self.isRecording = isRecording
        self.audioPower = audioPower
        self.onOpenDrawer = onOpenDrawer
        self.onOpenCovert = onOpenCovert
        self.onOpenAddMenu = onOpenAddMenu
        self.onOpenModelSelector = onOpenModelSelector
        self.onToggleVoiceRecording = onToggleVoiceRecording
        self.onOpenVoiceMode = onOpenVoiceMode
        self.onSend = onSend
    }

    public var body: some View {
        ZStack {
            JuliusTheme.bgCanvas
                .ignoresSafeArea()

            VStack(spacing: 0) {
                // Top Navigation Bar (with transparent icons & Covert icon)
                TopBarView(
                    isChatActive: false,
                    isCovert: false,
                    onOpenDrawer: onOpenDrawer,
                    onOpenCovert: onOpenCovert
                )

                Spacer()

                // Center Identity: Pure Transparent Julius Green Mark + Inspiring Title
                VStack(spacing: 20) {
                    JuliusMasterMarkView(
                        size: 54,
                        color: JuliusTheme.electricGreen,
                        withBadge: false
                    )

                    Text("What shall we build today?")
                        .font(JuliusTheme.serifTitle(size: 27))
                        .foregroundColor(JuliusTheme.textPrimary)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, 28)
                }

                Spacer()

                // Input Bar Container (Transparent, G2 continuous squircle edges, left typing)
                InputBarView(
                    text: $inputText,
                    attachments: $attachments,
                    model: model,
                    effort: effort,
                    isRecording: isRecording,
                    audioPower: audioPower,
                    onOpenAddMenu: onOpenAddMenu,
                    onOpenModelSelector: onOpenModelSelector,
                    onToggleVoiceRecording: onToggleVoiceRecording,
                    onOpenVoiceMode: onOpenVoiceMode,
                    onStopGeneration: {},
                    onSend: onSend
                )
                .padding(.bottom, 16)
            }
        }
    }
}
