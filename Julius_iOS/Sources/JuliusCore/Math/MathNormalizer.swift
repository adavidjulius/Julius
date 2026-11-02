import Foundation

/// Mathematical Markdown Pre-Processor and Normalization Engine
/// Follows the three-stage math rendering pipeline:
/// 1. Converts alternate delimiters (\[...\], \(...\)) to standard KaTeX delimiters ($$, $)
/// 2. Wraps bare \boxed{...} macros that lack outer math delimiters
/// 3. Streaming Guard: Auto-closes unclosed $$ block delimiters during token streaming
public func normalizeMathMarkdown(_ text: String) -> String {
    guard !text.isEmpty else { return "" }
    var processed = text

    // 1. Convert \[ ... \] to $$ ... $$
    processed = processed.replacingOccurrences(
        of: #"\\\[([\s\S]*?)\\\]"#,
        with: #"$$$1$$"#,
        options: .regularExpression
    )

    // 2. Convert \( ... \) to $ ... $
    processed = processed.replacingOccurrences(
        of: #"\\\(([\s\S]*?)\\\)"#,
        with: #"$$1$"#,
        options: .regularExpression
    )

    // 3. Catch bare \boxed{...} that are not already enclosed inside $$
    let blocks = processed.components(separatedBy: "$$")
    if blocks.count == 1 {
        processed = processed.replacingOccurrences(
            of: #"(?<!\$)\\boxed\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}(?!\$)"#,
            with: #"$$\\boxed{$1}$$"#,
            options: .regularExpression
        )
    } else {
        var normalizedBlocks: [String] = []
        for (idx, seg) in blocks.enumerated() {
            if idx % 2 == 0 {
                let wrapped = seg.replacingOccurrences(
                    of: #"(?<!\$)\\boxed\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}(?!\$)"#,
                    with: #"$$\\boxed{$1}$$"#,
                    options: .regularExpression
                )
                normalizedBlocks.append(wrapped)
            } else {
                normalizedBlocks.append(seg)
            }
        }
        processed = normalizedBlocks.joined(separator: "$$")
    }

    // 4. Streaming Guard: Auto-close unclosed block math ($$) during token streaming
    let blockMatches = processed.components(separatedBy: "$$").count - 1
    if blockMatches % 2 != 0 {
        processed += "\n$$"
    }

    return processed
}
