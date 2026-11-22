"""
SAM Notes Vault — Personal Knowledge & Real-Life Memory.

"My own notes are the memory."
Connects directly to the user's local notes vault (Obsidian, Apple Notes markdown exports,
or local documents) to answer "what's on my plate from my real life" and extract active tasks.

Leap-Ahead Feature:
- "Bidirectional Note Auto-Log":
  Automatically appends actions, decisions, and agent execution results into the
  user's Daily Note under `# SAM Activity Log`, keeping real-life notes in sync.
"""

from __future__ import annotations

import datetime
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("SAM.NotesVault")

DEFAULT_NOTES_DIR = Path.home() / ".sam_data" / "notes"


class NotesVaultRetriever:
    """
    Manages access, task extraction, semantic search, and auto-logging
    across user's local notes and markdown vaults.
    """

    def __init__(self, notes_dir: Optional[Path] = None):
        self.notes_dir = Path(notes_dir) if notes_dir else DEFAULT_NOTES_DIR
        self._ensure_dir()

    def _ensure_dir(self):
        try:
            self.notes_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning(f"Could not create notes directory: {e}")

    def get_today_note_path(self) -> Path:
        """Returns the file path for today's daily note (YYYY-MM-DD.md)."""
        today_str = datetime.date.today().isoformat()
        return self.notes_dir / f"{today_str}.md"

    def get_active_plate(self) -> str:
        """
        Scans today's daily note and all markdown files in the vault
        for open tasks (- [ ]), active goals, and immediate priorities.
        Returns a concise natural language summary of 'what's on my plate'.
        """
        open_tasks = []
        priorities = []
        projects = []

        if not self.notes_dir.exists():
            return "No notes vault directory found."

        # Scan today's note first
        today_file = self.get_today_note_path()
        files_to_scan = [today_file] if today_file.exists() else []

        # Add other markdown files
        for p in sorted(self.notes_dir.glob("*.md"), reverse=True):
            if p not in files_to_scan and not p.name.startswith("."):
                files_to_scan.append(p)
            if len(files_to_scan) >= 15:
                break

        for note_file in files_to_scan:
            try:
                content = note_file.read_text(encoding="utf-8", errors="ignore")
                for line in content.splitlines():
                    trimmed = line.strip()
                    # Check for uncompleted markdown checkboxes
                    if re.match(r"^-\s*\[\s*\]\s+", trimmed):
                        task_text = re.sub(r"^-\s*\[\s*\]\s+", "", trimmed)
                        if task_text not in open_tasks:
                            open_tasks.append(task_text)
                    elif trimmed.lower().startswith("priority:") or trimmed.lower().startswith("- priority:"):
                        priorities.append(trimmed)
                    elif trimmed.lower().startswith("project:") or trimmed.lower().startswith("- project:"):
                        projects.append(trimmed)
            except Exception as e:
                logger.debug(f"Error reading note file {note_file}: {e}")

        if not open_tasks and not priorities and not projects:
            return "Your notes vault is clear — no pending tasks or active plate items found for today."

        lines = ["Here is what's on your plate from your real life:"]
        if open_tasks:
            lines.append("\nTasks:")
            for t in open_tasks[:8]:
                lines.append(f"  • {t}")
        if priorities:
            lines.append("\nKey Priorities:")
            for p in priorities[:4]:
                lines.append(f"  • {p}")
        if projects:
            lines.append("\nActive Projects:")
            for pr in projects[:4]:
                lines.append(f"  • {pr}")

        return "\n".join(lines)

    def search_notes(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Searches all markdown notes for matching lines or keywords."""
        if not self.notes_dir.exists() or not query.strip():
            return []

        results = []
        tokens = query.lower().split()

        for note_path in self.notes_dir.glob("**/*.md"):
            if note_path.name.startswith("."):
                continue
            try:
                content = note_path.read_text(encoding="utf-8", errors="ignore")
                score = 0
                matching_lines = []
                for line in content.splitlines():
                    line_lower = line.lower()
                    if any(t in line_lower for t in tokens):
                        score += 1
                        if len(matching_lines) < 3 and line.strip():
                            matching_lines.append(line.strip())
                if score > 0:
                    results.append({
                        "file": note_path.name,
                        "path": str(note_path),
                        "score": score,
                        "snippets": matching_lines
                    })
            except Exception as e:
                logger.debug(f"Search error on {note_path}: {e}")

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    def append_daily_log(self, entry: str, category: str = "SAM Action") -> bool:
        """
        Leap-Ahead Feature: Bidirectional Note Auto-Log.
        Appends an action/outcome to today's daily note under `# SAM Activity Log`.
        """
        today_file = self.get_today_note_path()
        now_str = datetime.datetime.now().strftime("%H:%M:%S")
        log_line = f"- [{now_str}] **{category}**: {entry.strip()}"

        try:
            if not today_file.exists():
                today_header = f"# Daily Note — {datetime.date.today().isoformat()}\n\n## Tasks\n- [ ] Review daily priorities\n\n## SAM Activity Log\n"
                today_file.write_text(today_header + log_line + "\n", encoding="utf-8")
                return True

            content = today_file.read_text(encoding="utf-8")
            if "## SAM Activity Log" in content:
                content = content.replace("## SAM Activity Log", f"## SAM Activity Log\n{log_line}")
            else:
                content += f"\n\n## SAM Activity Log\n{log_line}\n"

            today_file.write_text(content, encoding="utf-8")
            return True
        except Exception as e:
            logger.error(f"Failed to append to daily note: {e}")
            return False
