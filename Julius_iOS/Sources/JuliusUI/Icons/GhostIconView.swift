import SwiftUI

/// Legacy compatibility wrapper forwarding to CovertIconView
public struct GhostIconView: View {
    public let size: CGFloat
    public let color: Color

    public init(size: CGFloat = 36, color: Color = JuliusTheme.brandGold) {
        self.size = size
        self.color = color
    }

    public var body: some View {
        CovertIconView(size: size, color: color)
    }
}
