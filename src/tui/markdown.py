"""
Julius Rich Markdown renderer and typography system.

Typography rules:
- H1: Bold, normal case, 1 blank line above and below, left-aligned, emoji stripped.
- H2/H3: Bold, same text color, no numbering color, no emoji, left-aligned.
- Body: Normal weight, text color, wrapped cleanly without breaking mid-word.
- Code blocks: Raised surface, rounded border (box.ROUNDED), 1 cell padding, language label in faint.
- Inline code: Raised surface background, normal text color.
- Lists: Bullet '•' with hanging indent so wrapped lines align.
- Raw markdown leaks (###, **) are properly parsed into formatted Rich renderables.
"""

from __future__ import annotations

import re
from typing import ClassVar, Dict, Any, Optional

from rich import box
from rich.console import Console, ConsoleOptions, RenderResult
from rich.markdown import (
    CodeBlock,
    Heading,
    ListItem,
    Markdown,
    MarkdownContext,
    Paragraph,
)
from rich.panel import Panel
from rich.segment import Segment
from rich.syntax import Syntax
from rich.text import Text
from rich.theme import Theme
from markdown_it import MarkdownIt

from .theme import ThemeTokens, DARK_THEME


# Comprehensive emoji regex for stripping decorative glyphs from headings
EMOJI_REGEX = re.compile(
    r"[\U00010000-\U0010ffff\u2600-\u27bf\u2300-\u23ff\u2b50\u2b55\u200d\u2705\u274c\u2714\u2716\ufe0f]+",
    flags=re.UNICODE,
)


class JuliusHeading(Heading):
    """Clean left-aligned heading with emoji stripped and disciplined vertical rhythm."""

    LEVEL_ALIGN: ClassVar[dict[str, str]] = {
        "h1": "left",
        "h2": "left",
        "h3": "left",
        "h4": "left",
        "h5": "left",
        "h6": "left",
    }

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        raw_text = self.text.plain
        # Strip emoji from headings
        clean_text = EMOJI_REGEX.sub("", raw_text).strip()

        # Build clean bold text
        h_text = Text(clean_text, style="bold")
        h_text.justify = "left"

        if self.tag == "h1":
            # 1 blank line above and below
            yield Text("")
            yield h_text
            yield Text("")
        else:
            yield h_text


class JuliusCodeBlock(CodeBlock):
    """Rounded, padded code block sized to fit command content with faint language label."""

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        code = str(self.text).rstrip()
        lexer = self.lexer_name or "text"
        syntax = Syntax(
            code,
            lexer,
            theme="github-dark",
            line_numbers=False,
            word_wrap=True,
            padding=0,
        )
        subtitle_tag = f"[dim]{lexer}[/dim]" if self.lexer_name else None
        yield Panel(
            syntax,
            box=box.ROUNDED,
            padding=(0, 1),
            subtitle=subtitle_tag,
            subtitle_align="right",
            border_style="dim",
            expand=False,
        )


class JuliusListItem(ListItem):
    """List item with clean bullet and hanging indent."""

    def render_bullet(self, console: Console, options: ConsoleOptions) -> RenderResult:
        render_options = options.update(width=options.max_width - 2)
        lines = list(console.render_lines(self.elements, render_options, style=self.style))
        bullet = Segment(" • ")
        padding = Segment("   ")
        new_line = Segment("\n")
        for i, line in enumerate(lines):
            yield bullet if i == 0 else padding
            yield from line
            yield new_line


class JuliusParagraph(Paragraph):
    """Paragraph with clean word wrap and fold overflow to prevent word clipping with ellipses."""

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        self.text.justify = self.justify
        self.text.overflow = "fold"
        self.text.no_wrap = False
        yield self.text


class JuliusMarkdown(Markdown):
    """Custom Markdown renderer adhering strictly to Julius terminal typography and brand palette."""

    elements = dict(Markdown.elements)
    elements["heading_open"] = JuliusHeading
    elements["fence"] = JuliusCodeBlock
    elements["item_open"] = JuliusListItem
    elements["paragraph_open"] = JuliusParagraph

    def __init__(self, markup: str, *args, theme: Optional[ThemeTokens] = None, **kwargs) -> None:
        super().__init__(markup, *args, **kwargs)
        # Enable strikethrough, table, and file:// hyperlink support
        parser = MarkdownIt().enable("strikethrough").enable("table")
        parser.validateLink = lambda url: True if url.strip().lower().startswith("file:") else MarkdownIt.validateLink(parser, url)
        self.parsed = parser.parse(markup)
        self.theme_tokens = theme or DARK_THEME

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        accent = self.theme_tokens.accent if self.theme_tokens and not self.theme_tokens.is_no_color else "#c8b896"
        is_no_color = self.theme_tokens.is_no_color if self.theme_tokens else False

        brand_styles = {
            "markdown.code": "bold" if is_no_color else f"bold {accent} on #1c1c1e",
            "markdown.code_block": "none" if is_no_color else f"{accent} on #1c1c1e",
            "markdown.link": "bold underline" if is_no_color else f"bold {accent}",
            "markdown.link_url": "underline" if is_no_color else f"underline {accent}",
            "markdown.list": "none" if is_no_color else accent,
            "markdown.item.number": "bold" if is_no_color else f"bold {accent}",
            "markdown.table.border": "dim" if is_no_color else f"dim {accent}",
            "markdown.table.header": "bold" if is_no_color else f"bold {accent}",
        }
        brand_theme = Theme(brand_styles)
        console.push_theme(brand_theme)
        try:
            yield from super().__rich_console__(console, options)
        finally:
            console.pop_theme()


def render_julius_markdown(text: str, theme: Optional[ThemeTokens] = None) -> JuliusMarkdown:
    """Convenience helper to construct a JuliusMarkdown instance with sanitized text."""
    # Strip any trailing JSON wrappers if model accidentally emitted them
    # Strip any trailing JSON wrappers if model accidentally emitted them
    clean = text.strip()
    if clean.startswith("```json") and clean.endswith("```"):
        import json
        try:
            parsed = json.loads(clean[7:-3].strip())
            if isinstance(parsed, dict) and "summary" in parsed:
                clean = parsed["summary"]
            elif isinstance(parsed, dict) and "message" in parsed:
                clean = parsed["message"]
        except Exception:
            pass

    # Suppress raw internal result prefixes
    if clean.startswith("Task completed:"):
        clean = clean[len("Task completed:"):].strip()
    elif clean.startswith("Conversation recorded:"):
        clean = clean[len("Conversation recorded:"):].strip()

    t = theme or DARK_THEME
    code_theme = "github-dark" if t.is_dark else "github-light"

    # Auto-link bare URLs and standalone recognizable files (e.g. julius.dwg, report.pdf)
    url_pat = re.compile(r'(?<![\[\(])(https?://[^\s)\]]+)(?![\]\)])')
    file_pat = re.compile(
        r'(?<![`/a-zA-Z0-9_\-\[<\(\\])\b([a-zA-Z0-9_\-]+\.(?:dwg|pdf))\b(?![`\]>\)])',
        re.IGNORECASE,
    )

    # Protect code blocks and inline backticks so code/commands are never mangled
    token_pat = re.compile(r'(```[\s\S]*?```|`[^`\n]+`)')
    tokens = token_pat.split(clean)
    processed_tokens = []
    for tok in tokens:
        if tok.startswith("`"):
            processed_tokens.append(tok)
        else:
            tok = url_pat.sub(r'[\1](\1)', tok)
            tok = file_pat.sub(r'[\1](file://\1)', tok)
            processed_tokens.append(tok)
    clean = "".join(processed_tokens)

    return JuliusMarkdown(
        clean,
        code_theme=code_theme,
        justify="left",
        hyperlinks=True,
        theme=t,
    )


# Backward compatibility aliases
AppleHeading = JuliusHeading
AppleCodeBlock = JuliusCodeBlock
AppleListItem = JuliusListItem
AppleMarkdown = JuliusMarkdown
render_apple_markdown = render_julius_markdown

