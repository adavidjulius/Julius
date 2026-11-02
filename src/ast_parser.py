"""
AST-aware file parser for precise symbol extraction.

Uses tree-sitter to parse Python and JavaScript/TypeScript source files into
structured Abstract Syntax Trees, enabling the agent to read individual
functions and classes without loading hundreds of irrelevant lines.

Falls back gracefully to raw line reads for unsupported file types.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SymbolInfo:
    """Metadata about a discovered code symbol."""
    name: str
    kind: str          # 'function' | 'class' | 'method'
    start_line: int    # 1-indexed
    end_line: int      # 1-indexed inclusive
    docstring: Optional[str] = None


@dataclass
class ExtractedSymbol:
    """The result of extracting a specific symbol from a file."""
    name: str
    kind: str
    file: str
    start_line: int
    end_line: int
    source: str        # The raw source code of the symbol


def _try_import_tree_sitter():
    """Try to import tree-sitter and return the module, or None on failure."""
    try:
        import tree_sitter  # noqa: F401
        return tree_sitter
    except ImportError:
        return None


def _get_python_parser():
    """Build and return a tree-sitter Python parser, or None if unavailable."""
    try:
        from tree_sitter import Language, Parser
        try:
            import tree_sitter_python as tspython
            PY_LANGUAGE = Language(tspython.language())
            parser = Parser(PY_LANGUAGE)
            return parser
        except (ImportError, AttributeError):
            pass

        # Legacy tree-sitter API (< 0.22)
        try:
            import tree_sitter_python as tspython
            PY_LANGUAGE = Language(tspython.language(), 'python')
            parser = Parser()
            parser.set_language(PY_LANGUAGE)
            return parser
        except Exception:
            pass
    except ImportError:
        pass
    return None


# ── Regex-based fallback parsers ──────────────────────────────────────────────
# Used when tree-sitter is not installed or unavailable.

_PY_FUNC_RE = re.compile(r'^( {0,})(?:async\s+)?def\s+(\w+)\s*\(', re.MULTILINE)
_PY_CLASS_RE = re.compile(r'^( {0,})class\s+(\w+)\s*[:(]', re.MULTILINE)
_JS_FUNC_RE = re.compile(
    r'^(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(',
    re.MULTILINE,
)
_JS_ARROW_RE = re.compile(
    r'^(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\(',
    re.MULTILINE,
)
_JS_CLASS_RE = re.compile(r'^(?:export\s+)?class\s+(\w+)', re.MULTILINE)


def _python_symbols_regex(lines: list[str]) -> list[SymbolInfo]:
    """Extract Python symbols using regex (no tree-sitter required)."""
    text = ''.join(lines)
    symbols: list[SymbolInfo] = []

    # Collect all function/class starts with their indentation level
    entries: list[tuple[int, str, str]] = []  # (char_offset, kind, name)

    for m in _PY_FUNC_RE.finditer(text):
        indent = len(m.group(1))
        kind = 'method' if indent > 0 else 'function'
        entries.append((m.start(), kind, m.group(2)))

    for m in _PY_CLASS_RE.finditer(text):
        entries.append((m.start(), 'class', m.group(2)))

    entries.sort(key=lambda e: e[0])

    # Map char offsets → line numbers
    def char_to_line(offset: int) -> int:
        return text[:offset].count('\n') + 1

    for i, (offset, kind, name) in enumerate(entries):
        start_line = char_to_line(offset)
        if i + 1 < len(entries):
            end_line = char_to_line(entries[i + 1][0]) - 1
        else:
            end_line = len(lines)
        symbols.append(SymbolInfo(name=name, kind=kind, start_line=start_line, end_line=end_line))

    return symbols


def _js_symbols_regex(lines: list[str]) -> list[SymbolInfo]:
    """Extract JavaScript/TypeScript symbols using regex."""
    text = ''.join(lines)
    symbols: list[SymbolInfo] = []
    entries: list[tuple[int, str, str]] = []

    for m in _JS_FUNC_RE.finditer(text):
        entries.append((m.start(), 'function', m.group(1)))
    for m in _JS_ARROW_RE.finditer(text):
        entries.append((m.start(), 'function', m.group(1)))
    for m in _JS_CLASS_RE.finditer(text):
        entries.append((m.start(), 'class', m.group(1)))

    entries.sort(key=lambda e: e[0])

    def char_to_line(offset: int) -> int:
        return text[:offset].count('\n') + 1

    for i, (offset, kind, name) in enumerate(entries):
        start_line = char_to_line(offset)
        if i + 1 < len(entries):
            end_line = char_to_line(entries[i + 1][0]) - 1
        else:
            end_line = len(lines)
        symbols.append(SymbolInfo(name=name, kind=kind, start_line=start_line, end_line=end_line))

    return symbols


# ── Public API ────────────────────────────────────────────────────────────────

def list_symbols(path: str) -> list[SymbolInfo]:
    """
    Return all functions and classes found in a source file.

    Supports Python (.py), JavaScript (.js), TypeScript (.ts, .tsx).
    Returns an empty list for other file types.

    Args:
        path: Absolute or relative path to the source file.

    Returns:
        List of SymbolInfo objects sorted by start line.
    """
    file_path = Path(path)
    if not file_path.exists() or not file_path.is_file():
        return []

    suffix = file_path.suffix.lower()
    try:
        lines = file_path.read_text(errors='replace').splitlines(keepends=True)
    except Exception as exc:
        logger.warning(f'ast_parser: could not read {path}: {exc}')
        return []

    if suffix == '.py':
        parser = _get_python_parser()
        if parser:
            try:
                return _list_symbols_tree_sitter_python(parser, lines)
            except Exception as exc:
                logger.debug(f'tree-sitter parse failed, falling back to regex: {exc}')
        return _python_symbols_regex(lines)

    if suffix in {'.js', '.ts', '.jsx', '.tsx', '.mjs'}:
        return _js_symbols_regex(lines)

    return []


def extract_symbol(path: str, symbol_name: str) -> Optional[ExtractedSymbol]:
    """
    Extract the complete source code of a named function or class.

    Args:
        path: Path to the source file.
        symbol_name: The exact name of the function or class to extract.

    Returns:
        ExtractedSymbol with the source code, or None if not found.
    """
    symbols = list_symbols(path)
    match = next((s for s in symbols if s.name == symbol_name), None)
    if match is None:
        return None

    file_path = Path(path)
    lines = file_path.read_text(errors='replace').splitlines(keepends=True)

    s = match.start_line - 1  # convert to 0-indexed
    e = match.end_line         # exclusive
    source_lines = lines[s:e]

    return ExtractedSymbol(
        name=match.name,
        kind=match.kind,
        file=str(file_path.resolve()),
        start_line=match.start_line,
        end_line=match.end_line,
        source=''.join(source_lines),
    )


def _list_symbols_tree_sitter_python(parser, lines: list[str]) -> list[SymbolInfo]:
    """Extract Python symbols using the tree-sitter parser."""
    source = ''.join(lines).encode('utf-8')
    tree = parser.parse(source)
    root = tree.root_node

    symbols: list[SymbolInfo] = []

    def walk(node, depth: int = 0) -> None:
        if node.type in ('function_definition', 'async_function_definition'):
            name_node = node.child_by_field_name('name')
            if name_node:
                kind = 'method' if depth > 0 else 'function'
                start = node.start_point[0] + 1  # 0-indexed → 1-indexed
                end = node.end_point[0] + 1
                symbols.append(SymbolInfo(name=name_node.text.decode(), kind=kind, start_line=start, end_line=end))
        elif node.type == 'class_definition':
            name_node = node.child_by_field_name('name')
            if name_node:
                start = node.start_point[0] + 1
                end = node.end_point[0] + 1
                symbols.append(SymbolInfo(name=name_node.text.decode(), kind='class', start_line=start, end_line=end))
            # Walk into class body to find methods
            for child in node.children:
                walk(child, depth + 1)
            return

        for child in node.children:
            walk(child, depth)

    walk(root)
    return sorted(symbols, key=lambda s: s.start_line)
