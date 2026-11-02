import SwiftUI
import JuliusCore

public struct RichMarkdownView: View {
    public let content: String
    @State private var webViewHeight: CGFloat = 160

    public init(_ content: String) {
        self.content = content
    }

    public static func containsMathOrTable(_ text: String) -> Bool {
        return text.contains("$") ||
               text.contains("\\boxed") ||
               text.contains("\\[") ||
               text.contains("\\(") ||
               text.contains("\\frac") ||
               text.contains("\\sqrt") ||
               text.contains("\\rho") ||
               (text.contains("|") && text.contains("---"))
    }

    public var body: some View {
        if Self.containsMathOrTable(content) {
            KaTeXMathView(content: normalizeMathMarkdown(content), dynamicHeight: $webViewHeight)
                .frame(height: max(24, webViewHeight))
                .frame(maxWidth: .infinity, alignment: .leading)
        } else {
            VStack(alignment: .leading, spacing: 14) {
                let blocks = parseMarkdownBlocks(content)
                ForEach(0..<blocks.count, id: \.self) { idx in
                    renderBlock(blocks[idx])
                }
            }
            .textSelection(.enabled)
            .environment(\.openURL, OpenURLAction { url in
                #if os(macOS)
                NSWorkspace.shared.open(url)
                return .handled
                #elseif os(iOS)
                UIApplication.shared.open(url)
                return .handled
                #endif
            })
        }
    }

    @ViewBuilder
    private func renderBlock(_ block: MarkdownBlock) -> some View {
        switch block {
        case .heading(let level, let text):
            if level == 1 {
                Text(formatInlineMarkdown(text))
                    .font(JuliusTheme.serifTitle(size: 23))
                    .foregroundColor(.white)
                    .padding(.top, 10)
                    .padding(.bottom, 2)
            } else if level == 2 {
                Text(formatInlineMarkdown(text))
                    .font(JuliusTheme.sansBold(size: 19))
                    .foregroundColor(.white)
                    .padding(.top, 10)
                    .padding(.bottom, 2)
            } else {
                Text(formatInlineMarkdown(text))
                    .font(JuliusTheme.sansBold(size: 16.5))
                    .foregroundColor(.white)
                    .padding(.top, 6)
                    .padding(.bottom, 1)
            }

        case .divider:
            Rectangle()
                .fill(Color.white.opacity(0.12))
                .frame(height: 1)
                .padding(.vertical, 6)

        case .bullet(let text):
            HStack(alignment: .top, spacing: 10) {
                Circle()
                    .fill(JuliusTheme.brandGold)
                    .frame(width: 5, height: 5)
                    .padding(.top, 8)

                Text(formatInlineMarkdown(text))
                    .font(ClaudeTheme.serifBody(size: 16))
                    .foregroundColor(ClaudeTheme.textPrimary)
                    .lineSpacing(4)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(.leading, 4)
            .padding(.vertical, 1)

        case .numbered(let num, let text):
            HStack(alignment: .top, spacing: 8) {
                Text("\(num).")
                    .font(JuliusTheme.sansBold(size: 14))
                    .foregroundColor(JuliusTheme.brandGold)
                    .frame(minWidth: 20, alignment: .trailing)
                    .padding(.top, 1)

                Text(formatInlineMarkdown(text))
                    .font(ClaudeTheme.serifBody(size: 16))
                    .foregroundColor(ClaudeTheme.textPrimary)
                    .lineSpacing(4)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(.leading, 2)
            .padding(.vertical, 1)

        case .blockquote(let text):
            HStack(alignment: .top, spacing: 12) {
                RoundedRectangle(cornerRadius: 1)
                    .fill(JuliusTheme.brandGold.opacity(0.75))
                    .frame(width: 3)

                Text(formatInlineMarkdown(text))
                    .font(ClaudeTheme.serifBody(size: 15.5))
                    .foregroundColor(Color.white.opacity(0.88))
                    .lineSpacing(4)
            }
            .padding(.leading, 4)
            .padding(.vertical, 4)

        case .table(let headers, let rows):
            MarkdownTableView(headers: headers, rows: rows)

        case .callout(let title, let body):
            HStack(alignment: .top, spacing: 12) {
                RoundedRectangle(cornerRadius: 1.5)
                    .fill(JuliusTheme.brandGold)
                    .frame(width: 3)

                VStack(alignment: .leading, spacing: 4) {
                    Text(title.uppercased())
                        .font(JuliusTheme.sansBold(size: 12))
                        .foregroundColor(JuliusTheme.brandGold)
                        .tracking(0.6)

                    Text(formatInlineMarkdown(body))
                        .font(ClaudeTheme.serifBody(size: 15.5))
                        .foregroundColor(Color.white.opacity(0.92))
                        .lineSpacing(3.5)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.white.opacity(0.03))
            .overlay(
                RoundedRectangle(cornerRadius: JuliusTheme.radiusMd, style: .continuous)
                    .stroke(JuliusTheme.brandGold.opacity(0.25), lineWidth: 1)
            )
            .clipShape(RoundedRectangle(cornerRadius: JuliusTheme.radiusMd, style: .continuous))
            .padding(.vertical, 4)

        case .codeBlock(let lang, let code):
            VStack(alignment: .leading, spacing: 0) {
                // Header Bar
                HStack {
                    Text(lang.isEmpty ? "CODE" : lang.uppercased())
                        .font(.system(size: 11, weight: .bold, design: .monospaced))
                        .foregroundColor(JuliusTheme.textSecondary)

                    Spacer()

                    Button(action: {
                        #if os(macOS)
                        NSPasteboard.general.clearContents()
                        NSPasteboard.general.setString(code, forType: .string)
                        #elseif os(iOS)
                        UIPasteboard.general.string = code
                        #endif
                    }) {
                        HStack(spacing: 4) {
                            Image(systemName: "doc.on.doc")
                                .font(.system(size: 11))
                            Text("Copy")
                                .font(.system(size: 11, weight: .medium))
                        }
                        .foregroundColor(JuliusTheme.textSecondary)
                    }
                    .buttonStyle(.plain)
                }
                .padding(.horizontal, 14)
                .padding(.vertical, 8)
                .background(Color.white.opacity(0.04))

                // Code body
                ScrollView(.horizontal, showsIndicators: false) {
                    Text(code)
                        .font(.system(size: 13, design: .monospaced))
                        .foregroundColor(.white.opacity(0.92))
                        .padding(14)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
            .background(Color.white.opacity(0.025))
            .overlay(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .stroke(Color.white.opacity(0.08), lineWidth: 1)
            )
            .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
            .padding(.vertical, 4)

        case .paragraph(let text):
            Text(formatInlineMarkdown(text))
                .font(ClaudeTheme.serifBody(size: 16.5))
                .foregroundColor(ClaudeTheme.textPrimary)
                .lineSpacing(4.5)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}

// ── Horizontal Responsive Markdown Table View ─────────────────────────────────

private struct MarkdownTableView: View {
    let headers: [String]
    let rows: [[String]]

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            ScrollView(.horizontal, showsIndicators: false) {
                VStack(alignment: .leading, spacing: 0) {
                    // 1. Table Header
                    HStack(alignment: .top, spacing: 0) {
                        ForEach(0..<headers.count, id: \.self) { colIdx in
                            Text(formatInlineMarkdown(cleanMathLaTeX(headers[colIdx])))
                                .font(JuliusTheme.sansBold(size: 13.5))
                                .foregroundColor(.white)
                                .frame(minWidth: columnWidth(colIdx), alignment: .leading)
                                .padding(.horizontal, 14)
                                .padding(.vertical, 10)
                                .fixedSize(horizontal: false, vertical: true)

                            if colIdx < headers.count - 1 {
                                Rectangle()
                                    .fill(Color.white.opacity(0.10))
                                    .frame(width: 1)
                            }
                        }
                    }
                    .background(Color.white.opacity(0.06))

                    // Header separator line (Brand Gold)
                    Rectangle()
                        .fill(JuliusTheme.brandGold.opacity(0.40))
                        .frame(height: 1.5)

                    // 2. Table Data Rows
                    ForEach(0..<rows.count, id: \.self) { rowIdx in
                        let row = rows[rowIdx]
                        HStack(alignment: .top, spacing: 0) {
                            ForEach(0..<headers.count, id: \.self) { colIdx in
                                let cellText = colIdx < row.count ? row[colIdx] : ""
                                Text(formatInlineMarkdown(cleanMathLaTeX(cellText)))
                                    .font(JuliusTheme.sansRegular(size: 13))
                                    .foregroundColor(ClaudeTheme.textPrimary)
                                    .lineSpacing(2)
                                    .frame(minWidth: columnWidth(colIdx), alignment: .leading)
                                    .padding(.horizontal, 14)
                                    .padding(.vertical, 9)
                                    .fixedSize(horizontal: false, vertical: true)

                                if colIdx < headers.count - 1 {
                                    Rectangle()
                                        .fill(Color.white.opacity(0.06))
                                        .frame(width: 1)
                                }
                            }
                        }
                        .background(rowIdx % 2 == 1 ? Color.white.opacity(0.025) : Color.clear)

                        if rowIdx < rows.count - 1 {
                            Rectangle()
                                .fill(Color.white.opacity(0.06))
                                .frame(height: 1)
                        }
                    }
                }
                .background(JuliusTheme.surface)
                .overlay(
                    RoundedRectangle(cornerRadius: JuliusTheme.radiusMd, style: .continuous)
                        .stroke(JuliusTheme.brandGold.opacity(0.35), lineWidth: 1)
                )
                .clipShape(RoundedRectangle(cornerRadius: JuliusTheme.radiusMd, style: .continuous))
                .padding(.vertical, 4)
            }

            // Scroll indicator hint if table has 3+ columns
            if headers.count >= 3 {
                HStack(spacing: 5) {
                    Image(systemName: "arrow.left.and.right")
                        .font(.system(size: 9))
                        .foregroundColor(JuliusTheme.brandGold)
                    Text("Scroll horizontally for full table")
                        .font(JuliusTheme.sansRegular(size: 11))
                        .foregroundColor(JuliusTheme.textSecondary)
                }
                .padding(.leading, 4)
                .padding(.bottom, 2)
            }
        }
    }

    private func columnWidth(_ colIdx: Int) -> CGFloat {
        var maxLen = headers.indices.contains(colIdx) ? headers[colIdx].count : 8
        for r in rows {
            if colIdx < r.count {
                maxLen = max(maxLen, r[colIdx].count)
            }
        }
        let computed = CGFloat(max(90, min(300, maxLen * 7 + 28)))
        return computed
    }
}

// ── Math & LaTeX Symbol Transliteration ────────────────────────────────────────

internal func cleanMathLaTeX(_ text: String) -> String {
    var s = text

    // 1. Strip display and inline math delimiters: $$, $, \(, \), \[, \]
    s = s.replacingOccurrences(of: #"\$\$(.*?)\$\$"#, with: "$1", options: .regularExpression)
    s = s.replacingOccurrences(of: #"\$([^\$]+)\$"#, with: "$1", options: .regularExpression)
    s = s.replacingOccurrences(of: #"\\\((.*?)\\\)"#, with: "$1", options: .regularExpression)
    s = s.replacingOccurrences(of: #"\\\[(.*?)\\\]"#, with: "$1", options: .regularExpression)

    // 2. Fractions and formatting wrappers
    s = s.replacingOccurrences(of: #"\\frac\{([^}]+)\}\{([^}]+)\}"#, with: "$1 / $2", options: .regularExpression)
    s = s.replacingOccurrences(of: #"\\text\{([^}]+)\}"#, with: "$1", options: .regularExpression)
    s = s.replacingOccurrences(of: #"\\mathrm\{([^}]+)\}"#, with: "$1", options: .regularExpression)
    s = s.replacingOccurrences(of: #"\\mathbf\{([^}]+)\}"#, with: "**$1**", options: .regularExpression)
    s = s.replacingOccurrences(of: #"\\mathit\{([^}]+)\}"#, with: "*$1*", options: .regularExpression)
    s = s.replacingOccurrences(of: #"_\{([a-zA-Z0-9]+)\}"#, with: "_$1", options: .regularExpression)
    s = s.replacingOccurrences(of: #"\^\{?\\circ\}?"#, with: "°", options: .regularExpression)

    // 3. Greek, geometry, and mathematical symbols
    let mathSymbols: [(String, String)] = [
        // Geometry / Engineering Projections
        (#"\\perp\b"#, "⊥"),
        (#"\\parallel\b"#, "∥"),
        (#"\\angle\b"#, "∠"),
        (#"\\triangle\b"#, "△"),
        (#"\\degree\b"#, "°"),
        (#"\\circ\b"#, "°"),

        // Greek Lowercase
        (#"\\alpha\b"#, "α"),
        (#"\\beta\b"#, "β"),
        (#"\\gamma\b"#, "γ"),
        (#"\\delta\b"#, "δ"),
        (#"\\epsilon\b"#, "ε"),
        (#"\\zeta\b"#, "ζ"),
        (#"\\eta\b"#, "η"),
        (#"\\theta\b"#, "θ"),
        (#"\\iota\b"#, "ι"),
        (#"\\kappa\b"#, "κ"),
        (#"\\lambda\b"#, "λ"),
        (#"\\mu\b"#, "μ"),
        (#"\\nu\b"#, "ν"),
        (#"\\xi\b"#, "ξ"),
        (#"\\pi\b"#, "π"),
        (#"\\rho\b"#, "ρ"),
        (#"\\sigma\b"#, "σ"),
        (#"\\tau\b"#, "τ"),
        (#"\\upsilon\b"#, "υ"),
        (#"\\phi\b"#, "φ"),
        (#"\\chi\b"#, "χ"),
        (#"\\psi\b"#, "ψ"),
        (#"\\omega\b"#, "ω"),

        // Greek Uppercase
        (#"\\Gamma\b"#, "Γ"),
        (#"\\Delta\b"#, "Δ"),
        (#"\\Theta\b"#, "Θ"),
        (#"\\Lambda\b"#, "Λ"),
        (#"\\Xi\b"#, "Ξ"),
        (#"\\Pi\b"#, "Π"),
        (#"\\Sigma\b"#, "Σ"),
        (#"\\Upsilon\b"#, "Υ"),
        (#"\\Phi\b"#, "Φ"),
        (#"\\Psi\b"#, "Ψ"),
        (#"\\Omega\b"#, "Ω"),

        // Relations & Operators
        (#"\\le\b"#, "≤"),
        (#"\\leq\b"#, "≤"),
        (#"\\ge\b"#, "≥"),
        (#"\\geq\b"#, "≥"),
        (#"\\neq\b"#, "≠"),
        (#"\\approx\b"#, "≈"),
        (#"\\equiv\b"#, "≡"),
        (#"\\sim\b"#, "∼"),
        (#"\\times\b"#, "×"),
        (#"\\div\b"#, "÷"),
        (#"\\pm\b"#, "±"),
        (#"\\mp\b"#, "∓"),
        (#"\\cdot\b"#, "·"),
        (#"\\sqrt\b"#, "√"),
        (#"\\in\b"#, "∈"),
        (#"\\notin\b"#, "∉"),
        (#"\\subset\b"#, "⊂"),
        (#"\\subseteq\b"#, "⊆"),
        (#"\\cap\b"#, "∩"),
        (#"\\cup\b"#, "∪"),
        (#"\\infty\b"#, "∞"),
        (#"\\partial\b"#, "∂"),
        (#"\\nabla\b"#, "∇"),
        (#"\\sum\b"#, "∑"),
        (#"\\prod\b"#, "∏"),
        (#"\\int\b"#, "∫"),

        // Arrows
        (#"\\to\b"#, "→"),
        (#"\\rightarrow\b"#, "→"),
        (#"\\leftarrow\b"#, "←"),
        (#"\\leftrightarrow\b"#, "↔"),
        (#"\\Rightarrow\b"#, "⇒"),
        (#"\\Leftarrow\b"#, "⇐"),
        (#"\\Leftrightarrow\b"#, "⇔")
    ]
    for (pattern, replacement) in mathSymbols {
        s = s.replacingOccurrences(of: pattern, with: replacement, options: .regularExpression)
    }
    return s
}

// ── Markdown Table Squashed Row Normalizer ─────────────────────────────────────

internal func normalizeMarkdownTables(_ raw: String) -> String {
    let lines = raw.components(separatedBy: "\n")
    var result: [String] = []

    for line in lines {
        let trimmed = line.trimmingCharacters(in: .whitespaces)
        let hasPipes = trimmed.contains("|")
        let hasSquashedDelim = trimmed.range(of: #"\|\s*\|"#, options: .regularExpression) != nil

        if hasPipes && hasSquashedDelim {
            let expanded = trimmed.replacingOccurrences(
                of: #"\|\s*\|\s*"#,
                with: "|\n| ",
                options: .regularExpression
            )
            result.append(expanded)
        } else {
            result.append(line)
        }
    }

    return result.joined(separator: "\n")
}

// ── Inline Markdown Formatter with AttributedString ───────────────────────────

private func formatInlineMarkdown(_ text: String) -> AttributedString {
    var cleaned = cleanMathLaTeX(text)

    // Auto-link raw URLs that are not already part of markdown [text](url)
    let urlPattern = #"(?<!\()https?:\/\/[^\s\)\>\]]+"#
    if let regex = try? NSRegularExpression(pattern: urlPattern, options: []) {
        let ns = cleaned as NSString
        let matches = regex.matches(in: cleaned, options: [], range: NSRange(location: 0, length: ns.length))
        for match in matches.reversed() {
            let start = match.range.location
            if start > 0 && ns.substring(with: NSRange(location: start - 1, length: 1)) == "(" {
                continue
            }
            let urlStr = ns.substring(with: match.range)
            let replacement = "[\(urlStr)](\(urlStr))"
            cleaned = (cleaned as NSString).replacingCharacters(in: match.range, with: replacement)
        }
    }

    if var attr = try? AttributedString(markdown: cleaned, options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace)) {
        for run in attr.runs {
            if let intent = run.inlinePresentationIntent, intent.contains(.stronglyEmphasized) {
                attr[run.range].foregroundColor = .white
            }
            if run.link != nil {
                attr[run.range].foregroundColor = JuliusTheme.brandGold
                attr[run.range].underlineStyle = .single
            }
        }
        return attr
    }
    return AttributedString(cleaned)
}

// ── Markdown Block Model & Parser ─────────────────────────────────────────────

private enum MarkdownBlock {
    case heading(level: Int, text: String)
    case divider
    case bullet(text: String)
    case numbered(num: String, text: String)
    case blockquote(text: String)
    case callout(title: String, body: String)
    case table(headers: [String], rows: [[String]])
    case codeBlock(lang: String, code: String)
    case paragraph(text: String)
}

private func parseMarkdownBlocks(_ raw: String) -> [MarkdownBlock] {
    var blocks: [MarkdownBlock] = []
    let normalized = normalizeMarkdownTables(raw.replacingOccurrences(of: "\r\n", with: "\n"))
    let lines = normalized.components(separatedBy: "\n")
    var i = 0

    while i < lines.count {
        let line = lines[i]
        let trimmed = line.trimmingCharacters(in: .whitespaces)

        if trimmed.isEmpty {
            i += 1
            continue
        }

        // Fenced Code Blocks (```lang ... ```)
        if trimmed.hasPrefix("```") {
            let lang = String(trimmed.dropFirst(3)).trimmingCharacters(in: .whitespaces)
            var codeLines: [String] = []
            i += 1
            while i < lines.count {
                if lines[i].trimmingCharacters(in: .whitespaces).hasPrefix("```") {
                    i += 1
                    break
                }
                codeLines.append(lines[i])
                i += 1
            }
            blocks.append(.codeBlock(lang: lang, code: codeLines.joined(separator: "\n")))
            continue
        }

        // Headings (#, ##, ###, ####)
        if trimmed.hasPrefix("#### ") {
            blocks.append(.heading(level: 4, text: String(trimmed.dropFirst(5))))
            i += 1
            continue
        } else if trimmed.hasPrefix("### ") {
            blocks.append(.heading(level: 3, text: String(trimmed.dropFirst(4))))
            i += 1
            continue
        } else if trimmed.hasPrefix("## ") {
            blocks.append(.heading(level: 2, text: String(trimmed.dropFirst(3))))
            i += 1
            continue
        } else if trimmed.hasPrefix("# ") {
            blocks.append(.heading(level: 1, text: String(trimmed.dropFirst(2))))
            i += 1
            continue
        }

        // Horizontal Dividers (---, ***, ___)
        if trimmed == "---" || trimmed == "***" || trimmed == "___" {
            blocks.append(.divider)
            i += 1
            continue
        }

        // Blockquotes (> text)
        if trimmed.hasPrefix("> ") {
            let bqText = String(trimmed.dropFirst(2)).trimmingCharacters(in: .whitespaces)
            // Check if blockquote is actually a callout like "> Key Rule: ..."
            let calloutPrefixes = ["Key Rule:", "Rule:", "Note:", "Important:", "Warning:", "Tip:"]
            if let p = calloutPrefixes.first(where: { bqText.hasPrefix($0) }) {
                let body = String(bqText.dropFirst(p.count)).trimmingCharacters(in: .whitespaces)
                blocks.append(.callout(title: String(p.dropLast()), body: body))
            } else {
                blocks.append(.blockquote(text: bqText))
            }
            i += 1
            continue
        }

        // Callouts (Key Rule:, Rule:, Note:, Important:, Warning:, Tip:)
        let calloutPrefixes = ["Key Rule:", "Rule:", "Note:", "Important:", "Warning:", "Tip:"]
        if let prefix = calloutPrefixes.first(where: { trimmed.hasPrefix($0) }) {
            let body = String(trimmed.dropFirst(prefix.count)).trimmingCharacters(in: .whitespaces)
            blocks.append(.callout(title: String(prefix.dropLast()), body: body))
            i += 1
            continue
        }

        // Bullet Lists (* item, - item, • item)
        if trimmed.hasPrefix("* ") || trimmed.hasPrefix("- ") || trimmed.hasPrefix("• ") {
            blocks.append(.bullet(text: String(trimmed.dropFirst(2))))
            i += 1
            continue
        }

        // Markdown Tables (| Col 1 | Col 2 | ... followed by | :--- | :--- |)
        if trimmed.hasPrefix("|") && i + 1 < lines.count && isTableSeparator(lines[i + 1]) {
            let headers = parseTableRow(trimmed)
            i += 2 // skip header and separator
            var rows: [[String]] = []
            while i < lines.count {
                let rLine = lines[i].trimmingCharacters(in: .whitespaces)
                if rLine.hasPrefix("|") {
                    rows.append(parseTableRow(rLine))
                    i += 1
                } else {
                    break
                }
            }
            blocks.append(.table(headers: headers, rows: rows))
            continue
        }

        // Numbered Lists & Major Numbered Section Headings (e.g. "2. Types of Planes & Their Positions")
        if let match = trimmed.range(of: #"^\d+\.\s+"#, options: .regularExpression) {
            let num = String(trimmed[match]).trimmingCharacters(in: .whitespaces).replacingOccurrences(of: ".", with: "")
            let itemText = String(trimmed[match.upperBound...]).trimmingCharacters(in: .whitespaces)

            let hasNoTrailingPeriod = !itemText.hasSuffix(".")
            let isShortTitle = itemText.count < 85
            let nextLineIsTableOrBlank = i + 1 < lines.count && (
                lines[i+1].trimmingCharacters(in: .whitespaces).isEmpty ||
                lines[i+1].trimmingCharacters(in: .whitespaces).hasPrefix("|")
            )

            if hasNoTrailingPeriod && (isShortTitle || nextLineIsTableOrBlank) {
                blocks.append(.heading(level: 2, text: "\(num). \(itemText)"))
            } else {
                blocks.append(.numbered(num: num, text: itemText))
            }
            i += 1
            continue
        }

        // Paragraph: Gather continuous text lines until blank line or special block
        var paraLines: [String] = [trimmed]
        i += 1
        while i < lines.count {
            let nextTrimmed = lines[i].trimmingCharacters(in: .whitespaces)
            if nextTrimmed.isEmpty ||
               nextTrimmed.hasPrefix("#") ||
               nextTrimmed.hasPrefix("```") ||
               nextTrimmed.hasPrefix("* ") ||
               nextTrimmed.hasPrefix("- ") ||
               nextTrimmed.hasPrefix("• ") ||
               nextTrimmed.hasPrefix("> ") ||
               nextTrimmed.hasPrefix("|") ||
               calloutPrefixes.contains(where: { nextTrimmed.hasPrefix($0) }) ||
               nextTrimmed == "---" ||
               nextTrimmed == "***" ||
               nextTrimmed == "___" ||
               nextTrimmed.range(of: #"^\d+\.\s+"#, options: .regularExpression) != nil {
                break
            }
            paraLines.append(nextTrimmed)
            i += 1
        }
        blocks.append(.paragraph(text: paraLines.joined(separator: " ")))
    }

    return blocks
}

private func isTableSeparator(_ line: String) -> Bool {
    let trimmed = line.trimmingCharacters(in: .whitespaces)
    guard trimmed.hasPrefix("|") || trimmed.contains("|") else { return false }
    let cleaned = trimmed.trimmingCharacters(in: CharacterSet(charactersIn: "|"))
    let parts = cleaned.components(separatedBy: "|")
    guard !parts.isEmpty else { return false }
    return parts.allSatisfy { part in
        let p = part.trimmingCharacters(in: .whitespaces)
        return p.contains("-") && p.allSatisfy { $0 == "-" || $0 == ":" }
    }
}

private func parseTableRow(_ line: String) -> [String] {
    var trimmed = line.trimmingCharacters(in: .whitespaces)
    if trimmed.hasPrefix("|") { trimmed = String(trimmed.dropFirst()) }
    if trimmed.hasSuffix("|") { trimmed = String(trimmed.dropLast()) }
    return trimmed.components(separatedBy: "|").map { $0.trimmingCharacters(in: .whitespaces) }
}
