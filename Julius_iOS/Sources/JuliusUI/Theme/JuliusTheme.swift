import SwiftUI
#if canImport(CoreText)
import CoreText
#endif

/// Canonical Julius Design System Tokens (The Master Brand Book · LumenAgent)
public struct JuliusTheme {
    // ── The Brand Main Realm (Antique Parchment & Imperial Gold) ─────────────
    public static let brandMain = Color(hex: "#C8B896")              // Master Brand Main Color (#C8B896)
    public static let brandGold = Color(hex: "#C8B896")              // Double Border Gold / Antique Parchment
    public static let brandGoldGlow = Color(hex: "#C8B896").opacity(0.22)
    public static let brandGoldFaint = Color(hex: "#C8B896").opacity(0.12)

    // ── The Kinetic Electric Logo Realm (Exclusively for Master Mark) ─────────
    public static let electricGreen = Color(hex: "#7ED321")          // Logo Only Energy (Stimulated Phosphor)
    public static let electricGreenGlow = Color(hex: "#7ED321").opacity(0.18)
    public static let deepAccentGreen = Color(hex: "#006A25")
    public static let slateBadge = Color(hex: "#0F172A")             // Master App & OS Icon Badge Canvas

    // ── The Obsidian TUI Realm ────────────────────────────────────────────────
    public static let bgDeep = Color(hex: "#121214")                // Base Canvas
    public static let bgCanvas = Color(hex: "#121214")              // Base Canvas
    public static let surface = Color(hex: "#1C1C1E")               // +4% Lightness
    public static let surfaceRaised = Color(hex: "#2C2C2E")         // +8% Lightness
    public static let surfaceHighlight = Color(hex: "#3A3A3E")      // Interactive Active / Focus State

    // ── The Imperial Heritage Realm ───────────────────────────────────────────
    public static let borderGold = Color(hex: "#C8B896")            // Double Border Gold / Antique Parchment
    public static let imperialCrimson = Color(hex: "#731A1A")       // Roman Crimson
    public static let bodyObsidian = Color(hex: "#1A1A1A")          // Formal Archival Obsidian

    // ── Semantic & Accent Tokens ──────────────────────────────────────────────
    public static let terracotta = Color(hex: "#C8B896")            // Mapped to Brand Main Color
    public static let terracottaFaint = Color(hex: "#C8B896").opacity(0.15)
    public static let artifactPurple = Color(hex: "#1A2234")         // Artifact card container
    public static let artifactPurpleIcon = Color(hex: "#C8B896")     // Main brand accent
    public static let accentBlue = Color(hex: "#C8B896")            // Checkmarks, badges use Brand Main
    public static let accentBlueBadge = Color(hex: "#C8B896").opacity(0.18)

    // ── Text & Typography Contrast Tokens ─────────────────────────────────────
    public static let textPrimary = Color(hex: "#F5F5F7")           // High Contrast 15.6:1
    public static let textSecondary = Color(hex: "#86868B")         // Subtle 4.9:1
    public static let textFaint = Color(hex: "#48484A")             // Hints & Separators
    public static let userBubbleBg = Color(hex: "#2C2C2E")

    // ── Borders & Dividers ────────────────────────────────────────────────────
    public static let borderIdle = Color(hex: "#3E3E42")            // Idle Outline
    public static let borderFaint = Color(hex: "#232326")
    public static let borderActive = Color(hex: "#C8B896")          // Active Outline (#C8B896)

    // ── Continuous Squircles (G2 Tokens from Brand Book) ──────────────────────
    public static let radiusSm: CGFloat = 6                         // --radius-sm: 6px
    public static let radiusMd: CGFloat = 8                         // --radius-md: 8px
    public static let radiusLg: CGFloat = 10                        // --radius-lg: 10px
    public static let radiusXl: CGFloat = 16                        // --radius-xl: 16px
    public static let radiusPill: CGFloat = 9999                    // --radius-pill: 9999px

    // ── Motion Presets & Breathing Physics ─────────────────────────────────────
    public static let enterDuration: Double = 0.220                 // 220 ms
    public static let settleDuration: Double = 0.160                // 160 ms
    public static let fadeDuration: Double = 0.120                  // 120 ms
    public static let breatheCycleDuration: Double = 1.400          // 1400 ms Harmonic Sine Opacity (0.35 -> 1.0)

    // ── Typography ────────────────────────────────────────────────────────────
    public static func registerCustomFonts() {
        // Native Apple system serif (New York) is pre-installed and globally available
    }

    public static func serifTitle(size: CGFloat = 26) -> Font {
        return Font.system(size: size, weight: .bold, design: .serif)
    }

    public static func serifBody(size: CGFloat = 17) -> Font {
        return Font.system(size: size, weight: .regular, design: .serif)
    }

    public static func sansBold(size: CGFloat = 16) -> Font {
        return Font.system(size: size, weight: .semibold, design: .default)
    }

    public static func sansRegular(size: CGFloat = 15) -> Font {
        return Font.system(size: size, weight: .regular, design: .default)
    }

    public static func monospaced(size: CGFloat = 13) -> Font {
        return Font.system(size: size, weight: .regular, design: .monospaced)
    }
}

public typealias ClaudeTheme = JuliusTheme
