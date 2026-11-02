import SwiftUI
import JuliusCore
import JuliusUI

public struct CreateProjectSheet: View {
    public let onClose: () -> Void
    public let onCreate: (ProjectItem) -> Void

    @State private var projectName: String = ""
    @State private var projectDescription: String = ""
    @FocusState private var isNameFocused: Bool

    public init(onClose: @escaping () -> Void, onCreate: @escaping (ProjectItem) -> Void) {
        self.onClose = onClose
        self.onCreate = onCreate
    }

    private var isValid: Bool {
        !projectName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    public var body: some View {
        ZStack {
            JuliusTheme.bgCanvas
                .ignoresSafeArea()

            VStack(alignment: .leading, spacing: 22) {
                // ── Header (Close X, Title "Create a project", Checkmark) ──
                HStack {
                    // Left: Transparent close button with X ("wrong symbol transparent")
                    Button(action: onClose) {
                        Image(systemName: "xmark")
                            .font(.system(size: 16, weight: .semibold))
                            .foregroundColor(.white)
                            .frame(width: 40, height: 40)
                            .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)

                    Spacer()

                    // Center: "Create a project"
                    Text("Create a project")
                        .font(JuliusTheme.sansBold(size: 17.5))
                        .foregroundColor(.white)

                    Spacer()

                    // Right: Circular button with Checkmark (Gold when valid)
                    Button(action: {
                        if isValid {
                            let p = ProjectItem(name: projectName, description: projectDescription)
                            onCreate(p)
                        }
                    }) {
                        ZStack {
                            Circle()
                                .fill(isValid ? JuliusTheme.brandGold : Color.white.opacity(0.10))
                                .frame(width: 40, height: 40)
                            Image(systemName: "checkmark")
                                .font(.system(size: 14, weight: .bold))
                                .foregroundColor(isValid ? .black : Color.white.opacity(0.35))
                        }
                    }
                    .buttonStyle(.plain)
                    .disabled(!isValid)
                }
                .padding(.top, 16)
                .padding(.bottom, 6)

                // ── Field 1: "What are you working on?" ──
                VStack(alignment: .leading, spacing: 10) {
                    Text("What are you working on?")
                        .font(JuliusTheme.sansBold(size: 15))
                        .foregroundColor(.white)

                    ZStack(alignment: .leading) {
                        if projectName.isEmpty {
                            Text("Name your project")
                                .font(JuliusTheme.sansRegular(size: 16))
                                .foregroundColor(Color(white: 0.40))
                                .padding(.horizontal, 16)
                                .allowsHitTesting(false)
                        }

                        TextField("", text: $projectName)
                            .focused($isNameFocused)
                            .textFieldStyle(.plain)
                            .font(JuliusTheme.sansRegular(size: 16))
                            .foregroundColor(.white)
                            .padding(.horizontal, 16)
                    }
                    .frame(height: 52)
                    .background(Color(white: 0.11))
                    .overlay(
                        RoundedRectangle(cornerRadius: 16, style: .continuous)
                            .stroke(Color(white: 0.20), lineWidth: 1)
                    )
                    .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
                }

                // ── Field 2: "What are you trying to achieve?" ──
                VStack(alignment: .leading, spacing: 10) {
                    Text("What are you trying to achieve?")
                        .font(JuliusTheme.sansBold(size: 15))
                        .foregroundColor(.white)

                    ZStack(alignment: .topLeading) {
                        if projectDescription.isEmpty {
                            Text("Describe your project, goals, subject, etc...")
                                .font(JuliusTheme.sansRegular(size: 15))
                                .foregroundColor(Color(white: 0.40))
                                .padding(.horizontal, 16)
                                .padding(.vertical, 14)
                                .allowsHitTesting(false)
                        }

                        TextEditor(text: $projectDescription)
                            .scrollContentBackground(.hidden)
                            .font(JuliusTheme.sansRegular(size: 15))
                            .foregroundColor(.white)
                            .padding(.horizontal, 12)
                            .padding(.vertical, 10)
                            .frame(height: 150)
                    }
                    .background(Color(white: 0.11))
                    .overlay(
                        RoundedRectangle(cornerRadius: 16, style: .continuous)
                            .stroke(Color(white: 0.20), lineWidth: 1)
                    )
                    .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
                }

                Spacer()
            }
            .padding(.horizontal, 18)
        }
        .frame(minWidth: 320, maxWidth: .infinity, minHeight: 460, maxHeight: .infinity)
        .onAppear {
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) {
                isNameFocused = true
            }
        }
    }
}
