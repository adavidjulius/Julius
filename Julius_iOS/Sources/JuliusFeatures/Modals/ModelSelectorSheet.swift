import SwiftUI
import JuliusCore
import JuliusUI

public struct ModelSelectorSheet: View {
    @Binding public var selectedModel: AIModel
    @Binding public var selectedEffort: EffortLevel
    public let onClose: () -> Void

    @State private var dragOffset: CGFloat = 0

    public init(
        selectedModel: Binding<AIModel>,
        selectedEffort: Binding<EffortLevel>,
        onClose: @escaping () -> Void
    ) {
        self._selectedModel = selectedModel
        self._selectedEffort = selectedEffort
        self.onClose = onClose
    }

    public var body: some View {
        VStack(spacing: 0) {
            // Drag Indicator Handle
            Capsule()
                .fill(JuliusTheme.brandGold.opacity(0.3))
                .frame(width: 36, height: 4)
                .padding(.top, 10)
                .padding(.bottom, 12)

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

                Text("Select model")
                    .font(JuliusTheme.sansBold(size: 17))
                    .foregroundColor(JuliusTheme.textPrimary)

                Spacer()

                Circle().fill(Color.clear).frame(width: 36, height: 36)
            }
            .padding(.horizontal, 16)
            .padding(.bottom, 18)

            ScrollView(showsIndicators: false) {
                VStack(spacing: 14) {
                    // Models Card Container (100% Transparent with G2 continuous squircle edges)
                    VStack(spacing: 0) {
                        ForEach(AIModel.allModels) { model in
                            Button(action: {
                                selectedModel = model
                            }) {
                                HStack(alignment: .top, spacing: 14) {
                                    VStack(alignment: .leading, spacing: 4) {
                                        HStack(spacing: 8) {
                                            Text(model.name)
                                                .font(JuliusTheme.sansBold(size: 16))
                                                .foregroundColor(JuliusTheme.textPrimary)
                                            if let badge = model.badge {
                                                Text(badge)
                                                    .font(JuliusTheme.sansBold(size: 11))
                                                    .foregroundColor(JuliusTheme.textPrimary)
                                                    .padding(.horizontal, 6)
                                                    .padding(.vertical, 2)
                                                    .background(
                                                        RoundedRectangle(cornerRadius: JuliusTheme.radiusSm, style: .continuous)
                                                            .fill(JuliusTheme.brandGold.opacity(0.18))
                                                    )
                                            }
                                        }
                                        Text(model.subtitle)
                                            .font(JuliusTheme.sansRegular(size: 13))
                                            .foregroundColor(JuliusTheme.textSecondary)
                                    }
                                    Spacer()
                                    if selectedModel.id == model.id {
                                        Image(systemName: "checkmark")
                                            .font(.system(size: 15, weight: .bold))
                                            .foregroundColor(.white)
                                    }
                                }
                                .padding(.horizontal, 16)
                                .padding(.vertical, 14)
                                .background(selectedModel.id == model.id ? JuliusTheme.brandGoldFaint : Color.clear)
                            }
                            .buttonStyle(.plain)

                            if model.id != AIModel.allModels.last?.id {
                                Divider().background(JuliusTheme.brandGold.opacity(0.12))
                            }
                        }
                    }
                    .background(
                        RoundedRectangle(cornerRadius: JuliusTheme.radiusXl, style: .continuous)
                            .fill(Color.white.opacity(0.03))
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: JuliusTheme.radiusXl, style: .continuous)
                            .stroke(JuliusTheme.brandGold.opacity(0.25), lineWidth: 1)
                    )

                    // Plan Info Note
                    (Text("Julius 550B Ultra is included with Julius Pro & Ultra plans, powered by local and cloud clusters. ")
                    + Text("Learn more")
                        .foregroundColor(JuliusTheme.textPrimary).underline())
                        .font(JuliusTheme.sansRegular(size: 13))
                        .foregroundColor(JuliusTheme.textSecondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.horizontal, 4)

                    // Effort Selector Row (100% Transparent with G2 continuous squircle edges)
                    HStack {
                        Text("Effort")
                            .font(JuliusTheme.sansBold(size: 16))
                            .foregroundColor(JuliusTheme.textPrimary)
                        Spacer()
                        Menu {
                            ForEach(EffortLevel.allCases, id: \.self) { level in
                                Button(level.rawValue) {
                                    selectedEffort = level
                                }
                            }
                        } label: {
                            HStack(spacing: 6) {
                                Text(selectedEffort.rawValue)
                                    .font(JuliusTheme.sansBold(size: 15))
                                    .foregroundColor(JuliusTheme.textPrimary)
                                Image(systemName: "chevron.up.chevron.down")
                                    .font(.system(size: 12))
                                    .foregroundColor(.white)
                            }
                            .padding(.horizontal, 14)
                            .padding(.vertical, 8)
                            .background(
                                RoundedRectangle(cornerRadius: JuliusTheme.radiusMd, style: .continuous)
                                    .fill(Color.clear)
                            )
                            .overlay(
                                RoundedRectangle(cornerRadius: JuliusTheme.radiusMd, style: .continuous)
                                    .stroke(JuliusTheme.brandGold.opacity(0.35), lineWidth: 1)
                            )
                        }
                        .buttonStyle(.plain)
                    }
                    .padding(.horizontal, 16)
                    .padding(.vertical, 14)
                    .background(
                        RoundedRectangle(cornerRadius: JuliusTheme.radiusXl, style: .continuous)
                            .fill(Color.white.opacity(0.03))
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: JuliusTheme.radiusXl, style: .continuous)
                            .stroke(JuliusTheme.brandGold.opacity(0.25), lineWidth: 1)
                    )

                    Text("Control how much effort Julius spends reasoning before answering.")
                        .font(JuliusTheme.sansRegular(size: 13))
                        .foregroundColor(JuliusTheme.textSecondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.horizontal, 4)
                }
                .padding(.horizontal, 16)
                .padding(.bottom, 24)
            }
        }
        .frame(maxWidth: .infinity)
        .frame(maxHeight: 580)
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
