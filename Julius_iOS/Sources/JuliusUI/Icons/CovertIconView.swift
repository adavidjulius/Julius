import SwiftUI

/// Covert Mode Icon — An undercover stealth agent emblem (Fedora & Sunglasses)
public struct CovertIconView: View {
    public let size: CGFloat
    public let color: Color

    public init(size: CGFloat = 22, color: Color = JuliusTheme.brandGold) {
        self.size = size
        self.color = color
    }

    public var body: some View {
        Canvas { context, canvasSize in
            let w = canvasSize.width
            let h = canvasSize.height
            let sx = w / 32.0
            let sy = h / 32.0

            // 1. Fedora Crown & Brim (Stealth Hat)
            var hatPath = Path()
            // Crown top indent (fedora crease)
            hatPath.move(to: CGPoint(x: 10 * sx, y: 7 * sy))
            hatPath.addQuadCurve(to: CGPoint(x: 16 * sx, y: 9 * sy), control: CGPoint(x: 13 * sx, y: 7.5 * sy))
            hatPath.addQuadCurve(to: CGPoint(x: 22 * sx, y: 7 * sy), control: CGPoint(x: 19 * sx, y: 7.5 * sy))
            // Crown right side
            hatPath.addLine(to: CGPoint(x: 23 * sx, y: 14 * sy))
            // Brim right flip
            hatPath.addQuadCurve(to: CGPoint(x: 29 * sx, y: 15 * sy), control: CGPoint(x: 26 * sx, y: 14.2 * sy))
            hatPath.addQuadCurve(to: CGPoint(x: 25 * sx, y: 16.5 * sy), control: CGPoint(x: 28 * sx, y: 16 * sy))
            // Brim under crown
            hatPath.addQuadCurve(to: CGPoint(x: 7 * sx, y: 16.5 * sy), control: CGPoint(x: 16 * sx, y: 17 * sy))
            // Brim left flip
            hatPath.addQuadCurve(to: CGPoint(x: 3 * sx, y: 15 * sy), control: CGPoint(x: 4 * sx, y: 16 * sy))
            hatPath.addQuadCurve(to: CGPoint(x: 9 * sx, y: 14 * sy), control: CGPoint(x: 6 * sx, y: 14.2 * sy))
            // Crown left side
            hatPath.closeSubpath()
            context.fill(hatPath, with: .color(color))

            // 2. Dark Sunglasses Bridge
            var bridgePath = Path()
            bridgePath.move(to: CGPoint(x: 14.5 * sx, y: 20 * sy))
            bridgePath.addLine(to: CGPoint(x: 17.5 * sx, y: 20 * sy))
            context.stroke(bridgePath, with: .color(color), lineWidth: 1.8 * sx)

            // 3. Left Sunglasses Lens (G2 rounded shape)
            let leftRect = CGRect(x: 7.5 * sx, y: 19.5 * sy, width: 7 * sx, height: 6.5 * sy)
            let leftLens = Path(roundedRect: leftRect, cornerRadius: 2.2 * sx)
            context.fill(leftLens, with: .color(color))

            // 4. Right Sunglasses Lens (G2 rounded shape)
            let rightRect = CGRect(x: 17.5 * sx, y: 19.5 * sy, width: 7 * sx, height: 6.5 * sy)
            let rightLens = Path(roundedRect: rightRect, cornerRadius: 2.2 * sx)
            context.fill(rightLens, with: .color(color))
        }
        .frame(width: size, height: size)
    }
}
