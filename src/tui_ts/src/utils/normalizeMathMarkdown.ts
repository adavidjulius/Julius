/**
 * Mathematical Markdown Pre-Processor and Streaming Guard
 * Standardizes delimiters and auto-closes streaming blocks
 */
export function normalizeMathMarkdown(text: string): string {
  if (!text) return "";

  let processed = text;

  // 1. Convert \[ ... \] to $$ ... $$
  processed = processed.replace(/\\\[([\s\S]*?)\\\]/g, (_, math) => `$$${math}$$`);

  // 2. Convert \( ... \) to $ ... $
  processed = processed.replace(/\\\(([\s\S]*?)\\\)/g, (_, math) => `$${math}$`);

  // 3. Catch bare \boxed{...} that are not already enclosed inside $$
  const blocks = processed.split("$$");
  if (blocks.length === 1) {
    processed = processed.replace(
      /(?<!\$)\\boxed\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}(?!\$)/g,
      "$$$$\\boxed{$1}$$$$"
    );
  } else {
    processed = blocks
      .map((seg, idx) => {
        if (idx % 2 === 0) {
          return seg.replace(
            /(?<!\$)\\boxed\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}(?!\$)/g,
            "$$$$\\boxed{$1}$$$$"
          );
        }
        return seg;
      })
      .join("$$");
  }

  // 4. Streaming Guard: Auto-close unclosed block math ($$) during token streaming
  const blockCount = (processed.match(/\$\$/g) || []).length;
  if (blockCount % 2 !== 0) {
    processed += "\n$$";
  }

  return processed;
}
