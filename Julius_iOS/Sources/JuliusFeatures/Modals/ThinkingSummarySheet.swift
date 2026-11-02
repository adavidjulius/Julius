import SwiftUI
import JuliusCore
import JuliusUI

public struct ThinkingSummarySheet: View {
    public let thinkingState: ThinkingState?
    public let onClose: () -> Void

    @State private var dragOffset: CGFloat = 0

    public init(thinkingState: ThinkingState?, onClose: @escaping () -> Void) {
        self.thinkingState = thinkingState
        self.onClose = onClose
    }

    public var body: some View {
        VStack(spacing: 0) {
            // Drag Indicator Handle
            Capsule()
                .fill(JuliusTheme.textFaint)
                .frame(width: 36, height: 4)
                .padding(.top, 10)
                .padding(.bottom, 12)

            // Header: Close (X) & Title
            HStack {
                Button(action: onClose) {
                    ZStack {
                        Circle()
                            .fill(JuliusTheme.surfaceRaised)
                            .frame(width: 36, height: 36)
                        Image(systemName: "xmark")
                            .font(.system(size: 14, weight: .bold))
                            .foregroundColor(JuliusTheme.brandGold)
                    }
                }
                Spacer()
                Text("Autonomous Reasoning")
                    .font(JuliusTheme.sansBold(size: 17))
                    .foregroundColor(JuliusTheme.textPrimary)
                Spacer()
                Circle().fill(Color.clear).frame(width: 36, height: 36)
            }
            .padding(.horizontal, 16)
            .padding(.bottom, 24)

            // Vertical Connected Timeline
            VStack(alignment: .leading, spacing: 0) {
                let steps = thinkingState?.steps ?? [
                    ThinkingStep(text: "Analyzing AST symbol call graph across Julius workspace", isCompleted: true),
                    ThinkingStep(text: "Validating HMAC audit chain checkpoint & sandbox permissions", isCompleted: true),
                    ThinkingStep(text: "Synthesizing modular Swift architecture and token sync", isCompleted: true)
                ]

                ForEach(Array(steps.enumerated()), id: \.element.id) { index, step in
                    HStack(alignment: .top, spacing: 18) {
                        // Dot & Connector Line
                        VStack(spacing: 0) {
                            Circle()
                                .fill(step.isCompleted ? JuliusTheme.electricGreen : JuliusTheme.textFaint)
                                .frame(width: 9, height: 9)
                                .padding(.top, 5)

                            if index < steps.count - 1 {
                                Rectangle()
                                    .fill(JuliusTheme.borderIdle)
                                    .frame(width: 2, height: 36)
                            }
                        }

                        // Text content
                        Text(step.text)
                            .font(JuliusTheme.sansRegular(size: 15))
                            .foregroundColor(step.isCompleted ? JuliusTheme.textPrimary : JuliusTheme.textFaint)
                            .lineSpacing(4)
                            .padding(.bottom, 18)

                        Spacer()
                    }
                }
            }
            .padding(.horizontal, 24)
            .padding(.bottom, 32)
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
