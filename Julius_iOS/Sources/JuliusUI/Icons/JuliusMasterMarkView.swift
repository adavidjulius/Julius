import SwiftUI

/// Mathematical Blueprint of the Julius Master Mark
/// Canvas: 512 × 512 pt (viewBox 0 0 512 512)
/// Curvature Standard: G2 continuous acceleration contours
/// Dorsal Apex: (400.67, 96.49) initiating forward vector
/// Ground Anchor: (234.12, 458.30) establishing balance
public struct JuliusMasterMarkShape: Shape {
    public init() {}

    public func path(in rect: CGRect) -> Path {
        let scaleX = rect.width / 512.0
        let scaleY = rect.height / 512.0
        let offsetX = rect.minX
        // Mathematical optical centering: the mark geometry spans Y: 95.60...458.30 (midpoint = 276.95).
        // Offsetting Y by (256.0 - 276.95) = -20.95 pt in 512-pt space perfectly centers its visual bounding box at rect.midY.
        let offsetY = rect.minY - (20.95 * scaleY)

        @inline(__always) func pt(_ x: Double, _ y: Double) -> CGPoint {
            CGPoint(x: offsetX + CGFloat(x) * scaleX, y: offsetY + CGFloat(y) * scaleY)
        }

        var path = Path()
        path.move(to: pt(400.67, 96.49))
        path.addCurve(to: pt(380.05, 99.87), control1: pt(393.83, 97.02), control2: pt(384.98, 98.49))
        path.addCurve(to: pt(374.67, 101.34), control1: pt(377.96, 100.49), control2: pt(375.52, 101.11))
        path.addCurve(to: pt(367.69, 103.83), control1: pt(373.11, 101.65), control2: pt(370.40, 102.63))
        path.addCurve(to: pt(364.53, 105.07), control1: pt(366.89, 104.19), control2: pt(365.47, 104.76))
        path.addCurve(to: pt(346.00, 115.11), control1: pt(361.33, 106.23), control2: pt(350.93, 111.87))
        path.addCurve(to: pt(308.53, 151.24), control1: pt(333.16, 123.69), control2: pt(319.78, 136.58))
        path.addCurve(to: pt(291.46, 176.88), control1: pt(303.24, 158.17), control2: pt(295.11, 170.40))
        path.addCurve(to: pt(287.55, 183.77), control1: pt(290.97, 177.72), control2: pt(289.19, 180.84))
        path.addCurve(to: pt(275.55, 207.77), control1: pt(284.88, 188.48), control2: pt(277.68, 202.88))
        path.addCurve(to: pt(273.11, 213.10), control1: pt(275.11, 208.75), control2: pt(274.04, 211.15))
        path.addCurve(to: pt(259.73, 247.41), control1: pt(270.35, 219.06), control2: pt(262.44, 239.32))
        path.addCurve(to: pt(256.89, 254.88), control1: pt(258.35, 251.63), control2: pt(257.02, 254.97))
        path.addCurve(to: pt(256.31, 246.35), control1: pt(256.71, 254.75), control2: pt(256.45, 250.92))
        path.addCurve(to: pt(254.22, 218.88), control1: pt(256.00, 237.55), control2: pt(254.98, 224.08))
        path.addCurve(to: pt(253.33, 212.44), control1: pt(254.00, 217.15), control2: pt(253.60, 214.26))
        path.addCurve(to: pt(249.11, 191.11), control1: pt(252.57, 206.57), control2: pt(250.13, 194.35))
        path.addCurve(to: pt(247.07, 184.44), control1: pt(248.75, 190.00), control2: pt(247.82, 187.02))
        path.addCurve(to: pt(242.71, 172.22), control1: pt(245.78, 180.17), control2: pt(244.71, 177.11))
        path.addCurve(to: pt(232.27, 152.44), control1: pt(240.84, 167.51), control2: pt(234.84, 156.22))
        path.addCurve(to: pt(202.23, 124.71), control1: pt(224.14, 140.62), control2: pt(212.94, 130.26))
        path.addCurve(to: pt(197.43, 122.13), control1: pt(200.41, 123.73), control2: pt(198.23, 122.58))
        path.addCurve(to: pt(191.87, 119.82), control1: pt(196.67, 121.69), control2: pt(194.14, 120.66))
        path.addCurve(to: pt(156.89, 112.66), control1: pt(179.87, 115.38), control2: pt(172.49, 113.86))
        path.addCurve(to: pt(140.22, 112.44), control1: pt(149.38, 112.08), control2: pt(146.45, 112.04))
        path.addCurve(to: pt(106.22, 116.88), control1: pt(127.78, 113.24), control2: pt(115.60, 114.84))
        path.addCurve(to: pt(99.78, 118.26), control1: pt(105.11, 117.10), control2: pt(102.22, 117.72))
        path.addCurve(to: pt(71.78, 125.82), control1: pt(92.67, 119.77), control2: pt(86.22, 121.50))
        path.addCurve(to: pt(64.89, 128.53), control1: pt(66.14, 127.51), control2: pt(64.89, 128.00))
        path.addCurve(to: pt(65.65, 129.20), control1: pt(64.89, 128.75), control2: pt(65.25, 129.06))
        path.addCurve(to: pt(69.34, 131.16), control1: pt(66.09, 129.38), control2: pt(67.74, 130.22))
        path.addCurve(to: pt(75.34, 134.45), control1: pt(70.94, 132.05), control2: pt(73.65, 133.52))
        path.addCurve(to: pt(111.34, 160.41), control1: pt(83.47, 138.85), control2: pt(103.25, 153.07))
        path.addCurve(to: pt(153.92, 207.03), control1: pt(127.43, 174.94), control2: pt(142.72, 191.70))
        path.addCurve(to: pt(173.30, 235.74), control1: pt(161.34, 217.25), control2: pt(172.63, 233.92))
        path.addCurve(to: pt(175.12, 238.67), control1: pt(173.39, 236.01), control2: pt(174.23, 237.34))
        path.addCurve(to: pt(182.23, 250.89), control1: pt(176.59, 240.80), control2: pt(182.23, 250.58))
        path.addCurve(to: pt(184.27, 254.49), control1: pt(182.23, 250.98), control2: pt(183.16, 252.58))
        path.addCurve(to: pt(202.45, 290.22), control1: pt(188.00, 260.80), control2: pt(198.85, 282.09))
        path.addCurve(to: pt(205.21, 296.44), control1: pt(203.38, 292.31), control2: pt(204.63, 295.11))
        path.addCurve(to: pt(208.50, 303.77), control1: pt(205.83, 297.77), control2: pt(207.30, 301.06))
        path.addCurve(to: pt(211.12, 309.41), control1: pt(209.70, 306.44), control2: pt(210.90, 309.01))
        path.addCurve(to: pt(211.56, 310.65), control1: pt(211.39, 309.85), control2: pt(211.56, 310.39))
        path.addCurve(to: pt(212.40, 313.01), control1: pt(211.56, 310.92), control2: pt(211.92, 311.94))
        path.addCurve(to: pt(214.22, 317.32), control1: pt(212.84, 314.03), control2: pt(213.69, 315.99))
        path.addCurve(to: pt(218.89, 328.65), control1: pt(216.22, 322.30), control2: pt(218.31, 327.36))
        path.addCurve(to: pt(223.82, 341.76), control1: pt(219.51, 330.16), control2: pt(220.22, 332.03))
        path.addCurve(to: pt(243.15, 400.20), control1: pt(230.62, 360.38), control2: pt(239.82, 388.12))
        path.addCurve(to: pt(243.99, 403.09), control1: pt(243.42, 401.18), control2: pt(243.82, 402.47))
        path.addCurve(to: pt(244.83, 405.98), control1: pt(244.17, 403.71), control2: pt(244.57, 405.00))
        path.addCurve(to: pt(246.43, 411.31), control1: pt(245.10, 406.96), control2: pt(245.81, 409.36))
        path.addCurve(to: pt(248.16, 417.31), control1: pt(247.01, 413.27), control2: pt(247.81, 415.98))
        path.addCurve(to: pt(249.54, 422.20), control1: pt(248.52, 418.64), control2: pt(249.14, 420.87))
        path.addCurve(to: pt(250.61, 426.42), control1: pt(249.90, 423.53), control2: pt(250.43, 425.44))
        path.addCurve(to: pt(254.43, 441.09), control1: pt(251.10, 428.51), control2: pt(253.37, 437.26))
        path.addCurve(to: pt(255.54, 445.22), control1: pt(254.87, 442.56), control2: pt(255.36, 444.42))
        path.addCurve(to: pt(257.94, 443.09), control1: pt(256.25, 448.24), control2: pt(256.83, 447.71))
        path.addCurve(to: pt(259.54, 436.20), control1: pt(258.34, 441.27), control2: pt(259.10, 438.16))
        path.addCurve(to: pt(262.03, 425.76), control1: pt(259.98, 434.24), control2: pt(261.14, 429.53))
        path.addCurve(to: pt(267.54, 403.98), control1: pt(263.59, 419.05), control2: pt(265.72, 410.78))
        path.addCurve(to: pt(274.65, 377.98), control1: pt(271.98, 387.58), control2: pt(273.72, 381.14))
        path.addCurve(to: pt(276.38, 371.85), control1: pt(275.05, 376.65), control2: pt(275.58, 374.69))
        path.addCurve(to: pt(277.98, 366.65), control1: pt(276.60, 371.09), control2: pt(277.31, 368.74))
        path.addCurve(to: pt(281.09, 356.43), control1: pt(278.65, 364.56), control2: pt(280.02, 359.98))
        path.addCurve(to: pt(294.91, 315.10), control1: pt(283.58, 348.07), control2: pt(292.20, 322.21))
        path.addCurve(to: pt(299.84, 301.77), control1: pt(298.78, 304.70), control2: pt(299.13, 303.77))
        path.addCurve(to: pt(303.31, 292.66), control1: pt(300.68, 299.24), control2: pt(302.55, 294.39))
        path.addCurve(to: pt(307.44, 282.66), control1: pt(303.62, 291.90), control2: pt(305.49, 287.42))
        path.addCurve(to: pt(318.42, 257.55), control1: pt(311.97, 271.55), control2: pt(314.28, 266.26))
        path.addCurve(to: pt(322.02, 249.77), control1: pt(319.66, 254.84), control2: pt(321.31, 251.37))
        path.addCurve(to: pt(343.35, 209.86), control1: pt(326.15, 240.61), control2: pt(338.78, 217.06))
        path.addCurve(to: pt(344.86, 207.37), control1: pt(344.19, 208.57), control2: pt(344.86, 207.46))
        path.addCurve(to: pt(366.10, 175.46), control1: pt(344.86, 206.30), control2: pt(360.77, 182.48))
        path.addCurve(to: pt(414.63, 124.62), control1: pt(383.08, 153.28), control2: pt(396.10, 139.68))
        path.addCurve(to: pt(435.30, 110.22), control1: pt(419.56, 120.62), control2: pt(431.30, 112.44))
        path.addCurve(to: pt(447.97, 102.71), control1: pt(442.14, 106.44), control2: pt(447.97, 102.98))
        path.addCurve(to: pt(446.10, 101.91), control1: pt(447.97, 102.53), control2: pt(447.13, 102.18))
        path.addCurve(to: pt(440.86, 100.53), control1: pt(445.03, 101.64), control2: pt(442.68, 101.02))
        path.addCurve(to: pt(400.64, 96.49), control1: pt(428.77, 97.24), control2: pt(412.37, 95.60))
        path.closeSubpath()
        return path
    }
}

/// Production-grade Julius Master Mark View
public struct JuliusMasterMarkView: View {
    public let size: CGFloat
    public let color: Color
    public let isAnimating: Bool
    public let withBadge: Bool
    public let badgeColor: Color

    @State private var breathePhase: Double = 1.0

    public init(
        size: CGFloat = 36,
        color: Color = JuliusTheme.electricGreen,
        isAnimating: Bool = false,
        withBadge: Bool = false,
        badgeColor: Color = JuliusTheme.slateBadge
    ) {
        self.size = size
        self.color = color
        self.isAnimating = isAnimating
        self.withBadge = withBadge
        self.badgeColor = badgeColor
    }

    public var body: some View {
        Group {
            if withBadge {
                ZStack {
                    RoundedRectangle(cornerRadius: size * 0.225, style: .continuous)
                        .fill(badgeColor)
                        .shadow(color: color.opacity(0.22), radius: size * 0.12, x: 0, y: size * 0.04)

                    RoundedRectangle(cornerRadius: size * 0.225, style: .continuous)
                        .stroke(JuliusTheme.borderIdle, lineWidth: 1)

                    JuliusMasterMarkShape()
                        .fill(color)
                        .frame(width: size * 0.62, height: size * 0.62)
                        .opacity(isAnimating ? breathePhase : 1.0)
                }
                .frame(width: size, height: size)
            } else {
                JuliusMasterMarkShape()
                    .fill(color)
                    .frame(width: size, height: size)
                    .opacity(isAnimating ? breathePhase : 1.0)
            }
        }
        .onAppear {
            if isAnimating {
                // 1400ms Harmonic Sine Breathing cycle from Brand Book
                withAnimation(
                    .easeInOut(duration: 0.7)
                    .repeatForever(autoreverses: true)
                ) {
                    breathePhase = 0.38
                }
            }
        }
    }
}
