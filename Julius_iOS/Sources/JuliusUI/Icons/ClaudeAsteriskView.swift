import SwiftUI

/// Legacy compatibility wrapper forwarding to JuliusMasterMarkView
public struct ClaudeAsteriskView: View {
    public let size: CGFloat
    public let isAnimating: Bool
    public let color: Color

    public init(size: CGFloat = 36, isAnimating: Bool = false, color: Color = JuliusTheme.electricGreen) {
        self.size = size
        self.isAnimating = isAnimating
        self.color = color
    }

    public var body: some View {
        JuliusMasterMarkView(size: size, color: color, isAnimating: isAnimating)
    }
}
