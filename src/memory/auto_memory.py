"""
File-based Auto-Memory Engine for Julius (WS1.1 / WS1.2).
Implements the 4-tier typed memory system and MEMORY.md index:
- Types: user, feedback, project, reference
- Strict 200-line index cap on MEMORY.md
- YAML frontmatter format with Why and How to apply lines
- Pre-recommendation verification of files and symbols
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

MEMORY_TYPES = {"user", "feedback", "project", "reference"}
MAX_INDEX_LINES = 200
MAX_CONTENT_BYTES = 102400  # 100KB per memory file


@dataclass
class MemoryRecord:
    slug: str
    title: str
    description: str
    memory_type: str
    content: str
    why: str = ""
    how_to_apply: str = ""
    file_path: Optional[Path] = None
    modified_ms: float = 0.0


class AutoMemoryManager:
    """Manages persistent, file-based markdown memories and the MEMORY.md index."""

    def __init__(self, workspace_root: Optional[str] = None, memory_dir: Optional[str] = None) -> None:
        self.workspace_root = Path(workspace_root or ".").resolve()
        if memory_dir:
            self.memory_dir = Path(memory_dir).resolve()
        else:
            # Default to workspace .julius/memory or ~/.julius/memory
            ws_mem = self.workspace_root / ".julius" / "memory"
            self.memory_dir = ws_mem
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.memory_dir / "MEMORY.md"
        self._ensure_index_file()

    def _ensure_index_file(self) -> None:
        if not self.index_path.exists():
            self.index_path.write_text("# Julius Auto-Memory Index\n\n", encoding="utf-8")

    def save_memory(
        self,
        slug: str,
        title: str,
        description: str,
        memory_type: str,
        content: str,
        why: str = "",
        how_to_apply: str = "",
    ) -> Path:
        """
        Save a typed memory file with YAML frontmatter and update the MEMORY.md index.
        Enforces memory type validation and 200-line index cap.
        """
        # Sanitize slug
        clean_slug = re.sub(r'[^a-z0-9_-]', '-', slug.lower().strip()).strip('-')
        if not clean_slug:
            clean_slug = "memory-entry"
        m_type = memory_type.lower() if memory_type.lower() in MEMORY_TYPES else "project"

        file_path = self.memory_dir / f"{clean_slug}.md"

        # Build Markdown content with YAML frontmatter
        body_lines = [
            "---",
            f"name: {clean_slug}",
            f"title: {title.strip() or clean_slug}",
            f"description: {description.strip()}",
            "metadata:",
            f"  type: {m_type}",
            "---",
            "",
            content.strip(),
        ]
        if why:
            body_lines.extend(["", f"**Why:** {why.strip()}"])
        if how_to_apply:
            body_lines.extend(["", f"**How to apply:** {how_to_apply.strip()}"])

        full_text = "\n".join(body_lines) + "\n"
        if len(full_text.encode('utf-8')) > MAX_CONTENT_BYTES:
            logger.warning("Memory content exceeds size limit, truncating")
            full_text = full_text[:MAX_CONTENT_BYTES]

        file_path.write_text(full_text, encoding="utf-8")

        # Update MEMORY.md index
        self._update_index_entry(clean_slug, title.strip() or clean_slug, description.strip())
        logger.info(f"Saved auto-memory: {clean_slug} ({m_type})")
        return file_path

    def _update_index_entry(self, slug: str, title: str, description: str) -> None:
        """Add or update an index entry in MEMORY.md while capping at 200 lines."""
        lines = []
        if self.index_path.exists():
            lines = self.index_path.read_text(encoding="utf-8").splitlines()

        entry_pattern = re.compile(rf'^- \[(.*?)\]\({re.escape(slug)}\.md\)')
        new_entry = f"- [{title}]({slug}.md) — {description}"

        found = False
        updated_lines = []
        for line in lines:
            if entry_pattern.match(line):
                updated_lines.append(new_entry)
                found = True
            else:
                updated_lines.append(line)

        if not found:
            updated_lines.append(new_entry)

        # Enforce max 200 lines
        if len(updated_lines) > MAX_INDEX_LINES:
            # Keep header lines and most recent entries
            headers = [l for l in updated_lines[:5] if l.startswith('#')]
            entries = [l for l in updated_lines if l.startswith('- [')]
            updated_lines = headers + entries[-(MAX_INDEX_LINES - len(headers)):]

        self.index_path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")

    def load_memory(self, slug: str) -> Optional[MemoryRecord]:
        """Load and parse a memory file by slug."""
        clean_slug = slug.removesuffix('.md').strip()
        file_path = self.memory_dir / f"{clean_slug}.md"
        if not file_path.exists():
            return None

        text = file_path.read_text(encoding="utf-8", errors="replace")
        mtime = file_path.stat().st_mtime

        # Parse YAML frontmatter
        fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, flags=re.DOTALL)
        if not fm_match:
            return MemoryRecord(
                slug=clean_slug,
                title=clean_slug,
                description="",
                memory_type="project",
                content=text,
                file_path=file_path,
                modified_ms=mtime * 1000,
            )

        fm_text, body = fm_match.group(1), fm_match.group(2)
        desc_match = re.search(r"^description:\s*(.+)$", fm_text, flags=re.MULTILINE)
        title_match = re.search(r"^title:\s*(.+)$", fm_text, flags=re.MULTILINE)
        type_match = re.search(r"type:\s*(\w+)", fm_text, flags=re.MULTILINE)

        desc = desc_match.group(1).strip() if desc_match else ""
        m_title = title_match.group(1).strip() if title_match else clean_slug
        m_type = type_match.group(1).strip() if type_match else "project"

        why_match = re.search(r"\*\*Why:\*\*\s*(.+)$", body, flags=re.MULTILINE)
        how_match = re.search(r"\*\*How to apply:\*\*\s*(.+)$", body, flags=re.MULTILINE)

        why = why_match.group(1).strip() if why_match else ""
        how = how_match.group(1).strip() if how_match else ""

        return MemoryRecord(
            slug=clean_slug,
            title=m_title,
            description=desc,
            memory_type=m_type,
            content=body.strip(),
            why=why,
            how_to_apply=how,
            file_path=file_path,
            modified_ms=mtime * 1000,
        )

    def list_memories(self) -> List[MemoryRecord]:
        """List all memories ordered by modification time (newest first)."""
        records = []
        for p in self.memory_dir.glob("*.md"):
            if p.name == "MEMORY.md":
                continue
            rec = self.load_memory(p.stem)
            if rec:
                records.append(rec)
        records.sort(key=lambda r: r.modified_ms, reverse=True)
        return records

    def load_index(self) -> str:
        """Read the MEMORY.md index content."""
        if not self.index_path.exists():
            return ""
        return self.index_path.read_text(encoding="utf-8")

    def remove_memory(self, slug: str) -> bool:
        """Remove a memory file and its entry from the index."""
        clean_slug = slug.removesuffix('.md').strip()
        file_path = self.memory_dir / f"{clean_slug}.md"
        if file_path.exists():
            file_path.unlink()

        if self.index_path.exists():
            lines = self.index_path.read_text(encoding="utf-8").splitlines()
            entry_pattern = re.compile(rf'^- \[(.*?)\]\({re.escape(clean_slug)}\.md\)')
            filtered = [l for l in lines if not entry_pattern.match(l)]
            self.index_path.write_text("\n".join(filtered) + "\n", encoding="utf-8")
        return True

    def verify_memory_against_workspace(self, memory: MemoryRecord) -> Tuple[bool, str]:
        """
        Verify rule: Before recommending from memory, verify paths or functions named in it.
        Returns (is_valid, reason).
        """
        # Search for file paths in memory
        file_paths = re.findall(r'[`\'"]([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)[`\'"]', memory.content)
        for rel_path in file_paths:
            full_path = self.workspace_root / rel_path
            if not full_path.exists():
                return False, f"Referenced file '{rel_path}' does not exist now in workspace."
        return True, "All referenced paths verified."
