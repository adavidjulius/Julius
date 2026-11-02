import SwiftUI
import JuliusCore
import JuliusUI

public enum LiveTalkState {
    case listening
    case thinking
    case speaking
}

public struct VoiceModeView: View {
    @ObservedObject private var transcriber = DeviceSpeechTranscriber.shared
    @State private var isMuted: Bool = false
    @State private var liveState: LiveTalkState = .listening
    @State private var pulseScale: CGFloat = 1.0
    @State private var secondaryPulse: CGFloat = 1.0

    public let model: AIModel
    public let onClose: () -> Void

    private var audioLevels: [CGFloat] {
        if isMuted || !transcriber.isRecording {
            return Array(repeating: 0.08, count: 28)
        }
        let power = CGFloat(transcriber.audioPower)
        return (0..<28).map { i in
            let normalized = Double(i) / 27.0
            let bell = sin(normalized * .pi)
            let flutter = sin(Double(i) * 1.8 + Double(power) * 12.0) * 0.15 + 0.85
            return max(0.08, min(1.0, power * CGFloat(bell * flutter * 1.4)))
        }
    }

    public init(model: AIModel = .sonnet, onClose: @escaping () -> Void) {
        self.model = model
        self.onClose = onClose
    }

    public var body: some View {
        ZStack {
            // Base Obsidian Canvas
            JuliusTheme.bgDeep
                .ignoresSafeArea()

            // Ambient Radiant Halo Gradient at Bottom (#C8B896 Main Brand Color)
            VStack {
                Spacer()
                RadialGradient(
                    gradient: Gradient(colors: [
                        (isMuted ? Color.red : JuliusTheme.brandGold).opacity(0.24),
                        (isMuted ? Color.red : JuliusTheme.brandGold).opacity(0.06),
                        Color.clear
                    ]),
                    center: .bottom,
                    startRadius: 20,
                    endRadius: 420
                )
                .frame(height: 420)
            }
            .ignoresSafeArea()

            VStack(spacing: 0) {
                // Top Header: Transparent Hamburger, Live Pill, and Gear
                HStack {
                    Button(action: {}) {
                        VStack(spacing: 4.5) {
                            RoundedRectangle(cornerRadius: 1).fill(JuliusTheme.brandGold).frame(width: 20, height: 2)
                            RoundedRectangle(cornerRadius: 1).fill(JuliusTheme.brandGold).frame(width: 20, height: 2)
                            RoundedRectangle(cornerRadius: 1).fill(JuliusTheme.brandGold).frame(width: 20, height: 2)
                        }
                        .frame(width: 44, height: 44)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)

                    Spacer()

                    // Live Status Pill in Center Header (#C8B896 Main Accent)
                    HStack(spacing: 6) {
                        Circle()
                            .fill(isMuted ? Color.red : JuliusTheme.brandGold)
                            .frame(width: 7, height: 7)
                        Text(isMuted ? "MUTED" : (liveState == .listening ? "LIVE SPEECH" : (liveState == .thinking ? "THINKING" : "SPEAKING")))
                            .font(JuliusTheme.sansBold(size: 11))
                            .tracking(1.2)
                            .foregroundColor(isMuted ? Color.red : JuliusTheme.brandGold)
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 6)
                    .background(Color.clear)
                    .overlay(
                        RoundedRectangle(cornerRadius: JuliusTheme.radiusPill, style: .continuous)
                            .stroke((isMuted ? Color.red : JuliusTheme.brandGold).opacity(0.35), lineWidth: 1)
                    )

                    Spacer()

                    Button(action: {}) {
                        Image(systemName: "gearshape")
                            .font(.system(size: 18))
                            .foregroundColor(JuliusTheme.brandGold)
                            .frame(width: 44, height: 44)
                            .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                }
                .padding(.horizontal, 16)
                .padding(.top, 10)

                Spacer()

                // Center Identity: Pure Green Logo inside #C8B896 Golden Radiant Orbital Ripples
                VStack(spacing: 24) {
                    ZStack {
                        // Orbital Pulse Rings in #C8B896
                        if !isMuted {
                            Circle()
                                .stroke(JuliusTheme.brandGold.opacity(0.18), lineWidth: 1.5)
                                .frame(width: 136 * secondaryPulse, height: 136 * secondaryPulse)

                            Circle()
                                .stroke(JuliusTheme.brandGold.opacity(0.35), lineWidth: 1.5)
                                .frame(width: 106 * pulseScale, height: 106 * pulseScale)
                        }

                        // Logo is ONLY in GREEN (#7ED321)
                        Button(action: toggleInteractionState) {
                            JuliusMasterMarkView(
                                size: 68,
                                color: JuliusTheme.electricGreen, // ONLY GREEN!
                                isAnimating: !isMuted,
                                withBadge: false
                            )
                        }
                        .buttonStyle(.plain)
                    }
                    .frame(height: 140)

                    // Title & Real-Time Dynamic Voice Transcript
                    VStack(spacing: 10) {
                        Text(isMuted ? "Microphone Muted" : (transcriber.isRecording ? "Listening to your voice..." : "Voice Ready"))
                            .font(JuliusTheme.serifTitle(size: 28))
                            .foregroundColor(JuliusTheme.textPrimary)

                        Text(isMuted ? "Muted. Tap microphone to resume live talk." : (transcriber.liveTranscript.isEmpty ? "Speak naturally to chat with Julius" : transcriber.liveTranscript))
                            .font(JuliusTheme.sansRegular(size: 15))
                            .foregroundColor(isMuted ? JuliusTheme.textFaint : JuliusTheme.brandGold)
                            .multilineTextAlignment(.center)
                            .padding(.horizontal, 32)
                            .animation(.easeInOut(duration: 0.25), value: transcriber.liveTranscript)
                    }
                }

                Spacer()

                // Interactive Real Audio Spectrum Waveform Bars (#C8B896)
                HStack(spacing: 4) {
                    ForEach(0..<audioLevels.count, id: \.self) { i in
                        RoundedRectangle(cornerRadius: JuliusTheme.radiusSm, style: .continuous)
                            .fill(isMuted ? JuliusTheme.borderIdle : JuliusTheme.brandGold)
                            .frame(width: 3.5, height: isMuted ? 4 : max(4, audioLevels[i] * 42))
                            .animation(.spring(response: 0.15, dampingFraction: 0.5), value: audioLevels[i])
                    }
                }
                .frame(height: 48)
                .padding(.bottom, 28)

                // Large Interactive Microphone Touch Target (#C8B896)
                ZStack {
                    Circle()
                        .stroke((isMuted ? Color.red : JuliusTheme.brandGold).opacity(0.38), lineWidth: 2)
                        .frame(width: 86 * pulseScale, height: 86 * pulseScale)

                    Button(action: {
                        isMuted.toggle()
                        if isMuted {
                            transcriber.stopTranscribing()
                        } else {
                            transcriber.startTranscribing(onPartial: { _ in }, onComplete: { _ in })
                        }
                    }) {
                        ZStack {
                            Circle()
                                .fill(Color.white.opacity(0.04))
                                .frame(width: 72, height: 72)
                            Circle()
                                .stroke((isMuted ? Color.red : JuliusTheme.brandGold).opacity(0.3), lineWidth: 1)
                                .frame(width: 72, height: 72)
                            Image(systemName: isMuted ? "mic.slash.fill" : "mic.fill")
                                .font(.system(size: 26))
                                .foregroundColor(isMuted ? Color.red : JuliusTheme.brandGold)
                        }
                    }
                    .buttonStyle(.plain)
                }
                .padding(.bottom, 36)

                // Bottom Controls (#C8B896 Accents, G2 Squircles)
                HStack(spacing: 14) {
                    // + Add Attachment Button
                    Button(action: {}) {
                        ZStack {
                            Circle()
                                .fill(Color.clear)
                                .frame(width: 44, height: 44)
                            Circle()
                                .stroke(JuliusTheme.brandGold.opacity(0.3), lineWidth: 1)
                                .frame(width: 44, height: 44)
                            Image(systemName: "plus")
                                .font(.system(size: 18, weight: .semibold))
                                .foregroundColor(JuliusTheme.brandGold)
                        }
                    }
                    .buttonStyle(.plain)

                    // Model Name Pill Dropdown
                    HStack(spacing: 6) {
                        Text(model.name)
                            .font(JuliusTheme.sansBold(size: 15))
                            .foregroundColor(JuliusTheme.textPrimary)
                        Image(systemName: "chevron.down")
                            .font(.system(size: 11, weight: .bold))
                            .foregroundColor(JuliusTheme.brandGold)
                    }
                    .padding(.horizontal, 16)
                    .padding(.vertical, 12)
                    .background(Color.clear)
                    .overlay(
                        RoundedRectangle(cornerRadius: JuliusTheme.radiusPill, style: .continuous)
                            .stroke(JuliusTheme.brandGold.opacity(0.32), lineWidth: 1)
                    )

                    // Audio Mode Switch
                    Button(action: toggleInteractionState) {
                        ZStack {
                            Circle()
                                .fill(Color.clear)
                                .frame(width: 44, height: 44)
                            Circle()
                                .stroke(JuliusTheme.brandGold.opacity(0.3), lineWidth: 1)
                                .frame(width: 44, height: 44)
                            Image(systemName: liveState == .speaking ? "pause.fill" : "waveform")
                                .font(.system(size: 16))
                                .foregroundColor(JuliusTheme.brandGold)
                        }
                    }
                    .buttonStyle(.plain)

                    // Close (X) Pill Button
                    Button(action: onClose) {
                        ZStack {
                            Circle()
                                .fill(JuliusTheme.brandGold)
                                .frame(width: 44, height: 44)
                            Image(systemName: "xmark")
                                .font(.system(size: 16, weight: .bold))
                                .foregroundColor(JuliusTheme.bgDeep)
                        }
                    }
                    .buttonStyle(.plain)
                    .keyboardShortcut(.cancelAction)
                }
                .padding(.bottom, 36)
            }
        }
        .onAppear {
            withAnimation(.easeInOut(duration: 1.2).repeatForever(autoreverses: true)) {
                pulseScale = 1.2
            }
            withAnimation(.easeInOut(duration: 1.8).repeatForever(autoreverses: true)) {
                secondaryPulse = 1.35
            }
            transcriber.startTranscribing(
                onPartial: { _ in },
                onComplete: { _ in }
            )
        }
        .onDisappear {
            transcriber.stopTranscribing()
        }
    }

    private func toggleInteractionState() {
        guard !isMuted else { return }
        switch liveState {
        case .listening:
            liveState = .thinking
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.2) {
                if !isMuted {
                    liveState = .speaking
                }
            }
        case .thinking:
            liveState = .speaking
        case .speaking:
            liveState = .listening
        }
    }
}
