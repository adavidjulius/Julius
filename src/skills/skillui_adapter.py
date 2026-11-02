"""
SkillUI Python Adapter for Julius.

Interactions with Julius's embedded `npxskillui` engine to extract design systems
from URLs, local directories, or git repositories, and register them as native Julius skills.
"""

from __future__ import annotations

import os
import sys
import logging
import asyncio
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

from .agentskills_importer import AgentSkillsImporter

logger = logging.getLogger(__name__)


class SkillUIAdapter:
    """Adapter for running native SkillUI design system extraction in Julius."""

    def __init__(self, workspace_root: str = ".") -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.skillui_dir = self.workspace_root / "src" / "native_ts" / "npxskillui"
        self.cli_dist = self.skillui_dir / "dist" / "cli.js"
        self.cli_src = self.skillui_dir / "src" / "cli.ts"
        self.importer = AgentSkillsImporter(workspace_root=str(self.workspace_root))

    def _get_runner_cmd(self) -> list[str]:
        """Determine whether to run via compiled dist/cli.js or via npx ts-node / jiti."""
        if self.cli_dist.exists():
            return ["node", str(self.cli_dist)]
        return ["npx", "-y", "ts-node", str(self.cli_src)]

    def run_extraction(
        self,
        url: Optional[str] = None,
        dir_path: Optional[str] = None,
        repo_url: Optional[str] = None,
        out_dir: Optional[str] = None,
        mode: str = "default",
        screens: int = 5,
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute SkillUI design system extraction synchronously.
        """
        cmd = self._get_runner_cmd()

        if url:
            cmd.extend(["--url", url])
        elif dir_path:
            cmd.extend(["--dir", dir_path])
        elif repo_url:
            cmd.extend(["--repo", repo_url])
        else:
            raise ValueError("Must specify one of: --url, --dir, or --repo")

        output_path = Path(out_dir).resolve() if out_dir else self.workspace_root
        cmd.extend(["--out", str(output_path)])

        if mode == "ultra":
            cmd.extend(["--mode", "ultra", "--screens", str(screens)])

        if name:
            cmd.extend(["--name", name])

        logger.info(f"Launching SkillUI command: {' '.join(cmd)}")
        
        env = os.environ.copy()
        env["NODE_PATH"] = str(self.skillui_dir / "node_modules")

        proc = subprocess.run(
            cmd,
            cwd=str(self.skillui_dir),
            env=env,
            capture_output=True,
            text=True
        )

        if proc.returncode != 0:
            logger.error(f"SkillUI extraction failed:\nStdout: {proc.stdout}\nStderr: {proc.stderr}")
            return {
                "success": False,
                "error": proc.stderr or proc.stdout,
                "command": " ".join(cmd),
            }

        logger.info(f"SkillUI extraction succeeded.\n{proc.stdout}")
        return {
            "success": True,
            "stdout": proc.stdout,
            "output_dir": str(output_path),
        }

    async def run_extraction_async(
        self,
        url: Optional[str] = None,
        dir_path: Optional[str] = None,
        repo_url: Optional[str] = None,
        out_dir: Optional[str] = None,
        mode: str = "default",
        screens: int = 5,
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute SkillUI design system extraction asynchronously.
        """
        return await asyncio.to_thread(
            self.run_extraction,
            url=url,
            dir_path=dir_path,
            repo_url=repo_url,
            out_dir=out_dir,
            mode=mode,
            screens=screens,
            name=name,
        )
