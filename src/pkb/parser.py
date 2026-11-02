"""
Layer 2 — Language Parser & Layer 3 — Symbol Extraction.

Parses source code into structured Abstract Syntax Trees and extracts
symbols (functions, methods, classes, interfaces, structs, enums, etc.)
assigning globally unique symbol IDs. Uses tree-sitter with regex fallbacks.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple

logger = logging.getLogger(__name__)


@dataclass
class SymbolNode:
    """Represents an extracted code symbol within a repository."""
    symbol_id: str             # e.g., 'src.auth.login.authenticate_user'
    name: str                  # e.g., 'authenticate_user'
    kind: str                  # 'function' | 'method' | 'class' | 'interface' | 'struct' | 'enum' | 'variable'
    file_path: str             # Relative file path
    start_line: int            # 1-indexed
    end_line: int              # 1-indexed inclusive
    signature: Optional[str] = None
    docstring: Optional[str] = None
    parent_symbol: Optional[str] = None
    visibility: str = "public" # 'public' | 'private' | 'protected'
    parameters: List[str] = field(default_factory=list)
    return_type: Optional[str] = None
    modifiers: List[str] = field(default_factory=list)
    source_code: str = ""


@dataclass
class ParsedASTNode:
    """Represents a node in the Abstract Syntax Tree."""
    node_id: str
    parent_id: Optional[str]
    kind: str
    text: str
    start_line: int
    end_line: int
    start_col: int
    end_col: int


class LanguageParser:
    """
    Parser engine leveraging Tree-sitter when available, falling back to
    compiler-grade regex grammars for multi-language AST symbol extraction.
    """

    def __init__(self) -> None:
        self.ts_available = self._check_tree_sitter()

    def _check_tree_sitter(self) -> bool:
        try:
            import tree_sitter  # noqa: F401
            return True
        except ImportError:
            return False

    def build_symbol_id(self, file_path: str, symbol_name: str, parent: Optional[str] = None) -> str:
        """Generate a globally unique symbol identifier."""
        clean_path = file_path.replace("\\", "/").rstrip(".py").rstrip(".ts").rstrip(".js").rstrip(".rs").rstrip(".go").replace("/", ".")
        if parent:
            return f"{clean_path}.{parent}.{symbol_name}"
        return f"{clean_path}.{symbol_name}"

    def parse_file(self, rel_path: str, content: str) -> Tuple[List[SymbolNode], List[ParsedASTNode]]:
        """Parse source code content and return extracted symbols and AST nodes."""
        ext = Path(rel_path).suffix.lower()

        # Try tree-sitter parser if available for supported extensions
        if self.ts_available and ext in {".py", ".ts", ".js", ".tsx", ".jsx", ".go", ".rs", ".java", ".cpp", ".c"}:
            try:
                symbols, ast_nodes = self._parse_tree_sitter(rel_path, content, ext)
                if symbols:
                    return symbols, ast_nodes
            except Exception as e:
                logger.debug(f"Tree-sitter parse failed for {rel_path}: {e}, falling back to grammar engine.")

        # Fallback regex-grammar parser
        return self._parse_regex_grammar(rel_path, content, ext)

    def _parse_tree_sitter(self, rel_path: str, content: str, ext: str) -> Tuple[List[SymbolNode], List[ParsedASTNode]]:
        """Tree-sitter parser implementation."""
        # Using ast_parser tree-sitter bindings if available
        try:
            from src.ast_parser import list_symbols
            symbols_info = list_symbols(rel_path, content)
            symbols: List[SymbolNode] = []
            ast_nodes: List[ParsedASTNode] = []
            lines = content.splitlines()

            for i, info in enumerate(symbols_info):
                sym_id = self.build_symbol_id(rel_path, info.name, info.class_name)
                start = info.start_line
                end = info.end_line
                sym_source = "\n".join(lines[start - 1:end]) if 0 < start <= len(lines) else ""

                sym = SymbolNode(
                    symbol_id=sym_id,
                    name=info.name,
                    kind=info.kind,
                    file_path=rel_path,
                    start_line=start,
                    end_line=end,
                    signature=info.signature,
                    docstring=info.docstring,
                    parent_symbol=info.class_name,
                    source_code=sym_source,
                )
                symbols.append(sym)

                ast_nodes.append(ParsedASTNode(
                    node_id=f"{sym_id}_ast_{i}",
                    parent_id=info.class_name,
                    kind=info.kind,
                    text=info.name,
                    start_line=start,
                    end_line=end,
                    start_col=0,
                    end_col=0,
                ))

            return symbols, ast_nodes
        except Exception:
            return [], []

    def _parse_regex_grammar(self, rel_path: str, content: str, ext: str) -> Tuple[List[SymbolNode], List[ParsedASTNode]]:
        """Universal grammar extractor supporting code, config, schema, doc, and build files."""
        lines = content.splitlines()
        file_name = Path(rel_path).name.lower()

        if ext == ".py":
            return self._parse_python(rel_path, lines)
        elif ext in {".js", ".jsx", ".ts", ".tsx"}:
            return self._parse_typescript(rel_path, lines)
        elif ext == ".rs":
            return self._parse_rust(rel_path, lines)
        elif ext == ".go":
            return self._parse_go(rel_path, lines)
        elif ext in {".md", ".rst"}:
            return self._parse_markdown(rel_path, lines)
        elif ext in {".json", ".yaml", ".yml", ".toml", ".ini", ".xml"}:
            return self._parse_config(rel_path, lines)
        elif ext in {".sql", ".graphql", ".proto"}:
            return self._parse_schema(rel_path, lines)
        elif ext in {".sh", ".bash", ".zsh"} or file_name in {"dockerfile", "makefile"}:
            return self._parse_shell(rel_path, lines)
        else:
            return self._parse_generic(rel_path, lines)

    def _parse_markdown(self, rel_path: str, lines: List[str]) -> Tuple[List[SymbolNode], List[ParsedASTNode]]:
        """Extract markdown sections and headers as symbol nodes."""
        symbols: List[SymbolNode] = []
        ast_nodes: List[ParsedASTNode] = []
        header_pattern = re.compile(r"^(#{1,6})\s+(.+)$")

        for line_idx, line in enumerate(lines, start=1):
            m = header_pattern.match(line)
            if m:
                level = len(m.group(1))
                title = m.group(2).strip()
                clean_title = re.sub(r"[^\w\s-]", "", title).strip().replace(" ", "_")
                sym_id = self.build_symbol_id(rel_path, f"section_h{level}_{clean_title}")
                
                symbols.append(SymbolNode(
                    symbol_id=sym_id,
                    name=title,
                    kind=f"header_h{level}",
                    file_path=rel_path,
                    start_line=line_idx,
                    end_line=min(line_idx + 20, len(lines)),
                    signature=f"#{'#'*(level-1)} {title}",
                    source_code=line.strip(),
                ))
        return symbols, ast_nodes

    def _parse_config(self, rel_path: str, lines: List[str]) -> Tuple[List[SymbolNode], List[ParsedASTNode]]:
        """Extract config keys and sections (YAML, TOML, JSON, INI)."""
        symbols: List[SymbolNode] = []
        ast_nodes: List[ParsedASTNode] = []
        key_pattern = re.compile(r"^\s*([A-Za-z0-9_.-]+)\s*[:=]")
        section_pattern = re.compile(r"^\s*\[([A-Za-z0-9_.-]+)\]")

        for line_idx, line in enumerate(lines, start=1):
            if not line.strip() or line.strip().startswith(("#", "//", ";")):
                continue
            
            s_match = section_pattern.match(line)
            if s_match:
                section_name = s_match.group(1)
                sym_id = self.build_symbol_id(rel_path, f"section_{section_name}")
                symbols.append(SymbolNode(
                    symbol_id=sym_id,
                    name=section_name,
                    kind="config_section",
                    file_path=rel_path,
                    start_line=line_idx,
                    end_line=line_idx + 5,
                    signature=f"[{section_name}]",
                    source_code=line.strip(),
                ))
                continue

            k_match = key_pattern.match(line)
            if k_match:
                key_name = k_match.group(1)
                sym_id = self.build_symbol_id(rel_path, f"key_{key_name}")
                symbols.append(SymbolNode(
                    symbol_id=sym_id,
                    name=key_name,
                    kind="config_key",
                    file_path=rel_path,
                    start_line=line_idx,
                    end_line=line_idx,
                    signature=line.strip()[:80],
                    source_code=line.strip(),
                ))

        return symbols, ast_nodes

    def _parse_schema(self, rel_path: str, lines: List[str]) -> Tuple[List[SymbolNode], List[ParsedASTNode]]:
        """Extract SQL tables, GraphQL types, Proto messages & services."""
        symbols: List[SymbolNode] = []
        ast_nodes: List[ParsedASTNode] = []
        schema_pattern = re.compile(r"^\s*(?:CREATE\s+TABLE|type|interface|message|service|enum)\s+([A-Za-z0-9_]+)", re.IGNORECASE)

        for line_idx, line in enumerate(lines, start=1):
            m = schema_pattern.match(line)
            if m:
                name = m.group(1)
                sym_id = self.build_symbol_id(rel_path, name)
                symbols.append(SymbolNode(
                    symbol_id=sym_id,
                    name=name,
                    kind="schema_entity",
                    file_path=rel_path,
                    start_line=line_idx,
                    end_line=line_idx + 10,
                    signature=line.strip(),
                    source_code=line.strip(),
                ))

        return symbols, ast_nodes

    def _parse_shell(self, rel_path: str, lines: List[str]) -> Tuple[List[SymbolNode], List[ParsedASTNode]]:
        """Extract shell functions and build targets."""
        symbols: List[SymbolNode] = []
        ast_nodes: List[ParsedASTNode] = []
        fn_pattern = re.compile(r"^\s*(?:function\s+)?([A-Za-z0-9_.-]+)\s*\(\)\s*\{?")
        target_pattern = re.compile(r"^([A-Za-z0-9_.-]+)\s*:")

        for line_idx, line in enumerate(lines, start=1):
            m = fn_pattern.match(line) or target_pattern.match(line)
            if m:
                name = m.group(1)
                if name in {"if", "for", "while", "case"}:
                    continue
                sym_id = self.build_symbol_id(rel_path, name)
                symbols.append(SymbolNode(
                    symbol_id=sym_id,
                    name=name,
                    kind="shell_target",
                    file_path=rel_path,
                    start_line=line_idx,
                    end_line=line_idx + 5,
                    signature=line.strip(),
                    source_code=line.strip(),
                ))

        return symbols, ast_nodes

    def _parse_python(self, rel_path: str, lines: List[str]) -> Tuple[List[SymbolNode], List[ParsedASTNode]]:
        symbols: List[SymbolNode] = []
        ast_nodes: List[ParsedASTNode] = []

        class_pattern = re.compile(r"^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)(?:\((.*?)\))?:")
        def_pattern = re.compile(r"^\s*(?:async\s+)?def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\((.*?)\)(?:\s*->\s*(.*?))?:")

        current_class: Optional[str] = None
        current_class_indent = 0

        for line_idx, line in enumerate(lines, start=1):
            indent = len(line) - len(line.lstrip())

            # Reset class context if indent drops back
            if current_class and indent <= current_class_indent and line.strip() and not line.strip().startswith("#"):
                if not line.startswith(" " * (current_class_indent + 4)):
                    current_class = None

            # Class match
            c_match = class_pattern.match(line)
            if c_match:
                class_name = c_match.group(1)
                bases = c_match.group(2) or ""
                current_class = class_name
                current_class_indent = indent

                sym_id = self.build_symbol_id(rel_path, class_name)
                symbols.append(SymbolNode(
                    symbol_id=sym_id,
                    name=class_name,
                    kind="class",
                    file_path=rel_path,
                    start_line=line_idx,
                    end_line=line_idx + 10,  # approximate until end calculation
                    signature=f"class {class_name}({bases})",
                    source_code=line.strip(),
                ))
                continue

            # Function/Method match
            f_match = def_pattern.match(line)
            if f_match:
                func_name = f_match.group(1)
                params_str = f_match.group(2) or ""
                ret_type = f_match.group(3)
                kind = "method" if current_class else "function"
                visibility = "private" if func_name.startswith("_") and not func_name.startswith("__") else "public"

                params = [p.strip().split(":")[0] for p in params_str.split(",") if p.strip()]
                sym_id = self.build_symbol_id(rel_path, func_name, current_class)

                symbols.append(SymbolNode(
                    symbol_id=sym_id,
                    name=func_name,
                    kind=kind,
                    file_path=rel_path,
                    start_line=line_idx,
                    end_line=line_idx + 5,
                    signature=f"def {func_name}({params_str})",
                    parent_symbol=current_class,
                    visibility=visibility,
                    parameters=params,
                    return_type=ret_type,
                    source_code=line.strip(),
                ))

        return symbols, ast_nodes

    def _parse_typescript(self, rel_path: str, lines: List[str]) -> Tuple[List[SymbolNode], List[ParsedASTNode]]:
        symbols: List[SymbolNode] = []
        ast_nodes: List[ParsedASTNode] = []

        func_pattern = re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\((.*?)\)")
        class_pattern = re.compile(r"^\s*(?:export\s+)?class\s+([A-Za-z_][A-Za-z0-9_]*)")
        interface_pattern = re.compile(r"^\s*(?:export\s+)?interface\s+([A-Za-z_][A-Za-z0-9_]*)")

        for line_idx, line in enumerate(lines, start=1):
            f_match = func_pattern.match(line)
            if f_match:
                name = f_match.group(1)
                sym_id = self.build_symbol_id(rel_path, name)
                symbols.append(SymbolNode(
                    symbol_id=sym_id,
                    name=name,
                    kind="function",
                    file_path=rel_path,
                    start_line=line_idx,
                    end_line=line_idx + 5,
                    signature=line.strip(),
                    source_code=line.strip(),
                ))

            c_match = class_pattern.match(line)
            if c_match:
                name = c_match.group(1)
                sym_id = self.build_symbol_id(rel_path, name)
                symbols.append(SymbolNode(
                    symbol_id=sym_id,
                    name=name,
                    kind="class",
                    file_path=rel_path,
                    start_line=line_idx,
                    end_line=line_idx + 10,
                    signature=line.strip(),
                    source_code=line.strip(),
                ))

            i_match = interface_pattern.match(line)
            if i_match:
                name = i_match.group(1)
                sym_id = self.build_symbol_id(rel_path, name)
                symbols.append(SymbolNode(
                    symbol_id=sym_id,
                    name=name,
                    kind="interface",
                    file_path=rel_path,
                    start_line=line_idx,
                    end_line=line_idx + 10,
                    signature=line.strip(),
                    source_code=line.strip(),
                ))

        return symbols, ast_nodes

    def _parse_rust(self, rel_path: str, lines: List[str]) -> Tuple[List[SymbolNode], List[ParsedASTNode]]:
        symbols: List[SymbolNode] = []
        ast_nodes: List[ParsedASTNode] = []
        pattern = re.compile(r"^\s*(?:pub\s+)?(?:async\s+)?fn\s+([A-Za-z_][A-Za-z0-9_]*)\s*\((.*?)\)")

        for line_idx, line in enumerate(lines, start=1):
            m = pattern.match(line)
            if m:
                name = m.group(1)
                sym_id = self.build_symbol_id(rel_path, name)
                symbols.append(SymbolNode(
                    symbol_id=sym_id,
                    name=name,
                    kind="function",
                    file_path=rel_path,
                    start_line=line_idx,
                    end_line=line_idx + 5,
                    signature=line.strip(),
                    source_code=line.strip(),
                ))

        return symbols, ast_nodes

    def _parse_go(self, rel_path: str, lines: List[str]) -> Tuple[List[SymbolNode], List[ParsedASTNode]]:
        symbols: List[SymbolNode] = []
        ast_nodes: List[ParsedASTNode] = []
        pattern = re.compile(r"^\s*func\s+(?:\((.*?)\)\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*\((.*?)\)")

        for line_idx, line in enumerate(lines, start=1):
            m = pattern.match(line)
            if m:
                receiver = m.group(1)
                name = m.group(2)
                kind = "method" if receiver else "function"
                sym_id = self.build_symbol_id(rel_path, name, receiver)
                symbols.append(SymbolNode(
                    symbol_id=sym_id,
                    name=name,
                    kind=kind,
                    file_path=rel_path,
                    start_line=line_idx,
                    end_line=line_idx + 5,
                    signature=line.strip(),
                    source_code=line.strip(),
                ))

        return symbols, ast_nodes

    def _parse_generic(self, rel_path: str, lines: List[str]) -> Tuple[List[SymbolNode], List[ParsedASTNode]]:
        symbols: List[SymbolNode] = []
        ast_nodes: List[ParsedASTNode] = []
        pattern = re.compile(r"^\s*(?:public|private|protected|static|async|def|function|fn|func)\s+([A-Za-z_][A-Za-z0-9_]*)\b")

        for line_idx, line in enumerate(lines, start=1):
            m = pattern.match(line)
            if m:
                name = m.group(1)
                sym_id = self.build_symbol_id(rel_path, name)
                symbols.append(SymbolNode(
                    symbol_id=sym_id,
                    name=name,
                    kind="function",
                    file_path=rel_path,
                    start_line=line_idx,
                    end_line=line_idx + 5,
                    signature=line.strip(),
                    source_code=line.strip(),
                ))

        return symbols, ast_nodes
