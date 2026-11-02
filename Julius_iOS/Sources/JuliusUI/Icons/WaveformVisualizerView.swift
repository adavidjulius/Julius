import SwiftUI

public struct WaveformIconView: View {
    public let barCount: Int
    public let height: CGFloat
    public let color: Color
    public let isAnimated: Bool

    public init(barCount: Int = 4, height: CGFloat = 16, color: Color = JuliusTheme.brandGold, isAnimated: Bool = false) {
        self.barCount = barCount
        self.height = height
        self.color = color
        self.isAnimated = isAnimated
    }

    public var body: some View {
        HStack(spacing: 2.5) {
            ForEach(0..<barCount, id: \.self) { i in
                WaveformBar(index: i, maxHeight: height, color: color, isAnimated: isAnimated)
            }
        }
    }
}

public struct WaveformBar: View {
    let index: Int
    let maxHeight: CGFloat
    let color: Color
    let isAnimated: Bool

    @State private var currentHeight: CGFloat = 8

    public init(index: Int, maxHeight: CGFloat, color: Color = JuliusTheme.brandGold, isAnimated: Bool = false) {
        self.index = index
        self.maxHeight = maxHeight
        self.color = color
        self.isAnimated = isAnimated
    }

    public var body: some View {
        RoundedRectangle(cornerRadius: 1.5)
            .fill(color)
            .frame(width: 2.5, height: currentHeight)
            .onAppear {
                let heights: [CGFloat] = [maxHeight * 0.35, maxHeight * 0.85, maxHeight * 0.55, maxHeight * 0.75, maxHeight * 0.45]
                currentHeight = heights[index % heights.count]
                if isAnimated {
                    withAnimation(
                        .easeInOut(duration: 0.45)
                        .repeatForever(autoreverses: true)
                        .delay(Double(index) * 0.08)
                    ) {
                        currentHeight = heights[(index + 2) % heights.count]
                    }
                }
            }
    }
}

public struct DynamicWaveformView: View {
    public let power: Float
    public let barCount: Int
    public let maxHeight: CGFloat
    public let color: Color

    public init(power: Float, barCount: Int = 24, maxHeight: CGFloat = 26, color: Color = JuliusTheme.brandGold) {
        self.power = power
        self.barCount = barCount
        self.maxHeight = maxHeight
        self.color = color
    }

    public var body: some View {
        HStack(spacing: 2.5) {
            ForEach(0..<barCount, id: \.self) { i in
                // Calculate symmetric curve factor (higher in middle, lower on ends)
                let normalized = Double(i) / Double(max(1, barCount - 1))
                let curve = sin(normalized * .pi)
                // Modulate by dynamic power + slight individual flutter
                let flutter = sin(Double(i) * 1.5 + Double(power) * 10) * 0.15 + 0.85
                let calculatedHeight = max(4.0, maxHeight * CGFloat(power) * CGFloat(curve * flutter))

                RoundedRectangle(cornerRadius: 1.5)
                    .fill(color)
                    .frame(width: 2.5, height: calculatedHeight)
                    .animation(.spring(response: 0.18, dampingFraction: 0.75), value: power)
            }
        }
    }
}
