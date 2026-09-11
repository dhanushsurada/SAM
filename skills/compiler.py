"""
SKILLS — Compiler
Detects repeated task patterns and compiles them into fast executables.
Compiled skills bypass LLM thinking — drastically reduce latency.
Hermes-inspired approach.

Storage location (fixed — see PROGRESS.md / audit notes): this used to
write to <repo>/skills/skills.db and <repo>/skills/compiled/, the only
persistent-data subsystem in SAM that didn't live under SAM_DATA_DIR
(~/.sam_data). sam_cli.py's `cmd_skills` and `cmd_sync_status` always
read from SAM_DATA_DIR, so a real developer who had ever compiled a
skill would see it "disappear" from the CLI's point of view — not
actually lost, just written somewhere the CLI never looked. Storage now
lives under SAM_DATA_DIR like everything else; `_migrate_legacy_skills_data`
below copies any pre-existing data at the old location forward once,
non-destructively (old files are left in place, never deleted or moved),
so nothing is lost either way.
"""

import json
import logging
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List

from config.settings import SAM_DATA_DIR

logger = logging.getLogger("SAM.Skills")

SKILLS_DB_PATH = SAM_DATA_DIR / "skills" / "skills.db"
COMPILED_PATH = SAM_DATA_DIR / "skills" / "compiled"

# Where this data lived before the fix above — kept only as a migration
# source, never written to again.
_LEGACY_SKILLS_DB_PATH = Path(__file__).parent / "skills.db"
_LEGACY_COMPILED_PATH = Path(__file__).parent / "compiled"


def _migrate_legacy_skills_data(old_db: Path, old_compiled: Path, new_db: Path, new_compiled: Path) -> None:
    """One-time, idempotent, copy-only migration of any pre-existing
    skills data from the old repo-relative location to the canonical
    SAM_DATA_DIR location. Never deletes or moves the old files — safe
    to call on every startup, and a no-op once the new location already
    has the data (or the old location never had any)."""
    try:
        if old_db.exists() and not new_db.exists():
            new_db.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(old_db, new_db)
            logger.info(f"Migrated legacy skills database {old_db} -> {new_db} (old file left in place)")
    except OSError as e:
        logger.warning(f"Could not migrate legacy skills database {old_db} -> {new_db}: {e}")

    try:
        if old_compiled.is_dir():
            new_compiled.mkdir(parents=True, exist_ok=True)
            for src in old_compiled.glob("*.json"):
                dest = new_compiled / src.name
                if not dest.exists():
                    shutil.copy2(src, dest)
                    logger.info(f"Migrated legacy compiled skill {src} -> {dest} (old file left in place)")
    except OSError as e:
        logger.warning(f"Could not migrate legacy compiled skills {old_compiled} -> {new_compiled}: {e}")


class SkillCompiler:
    def __init__(self, settings):
        self.settings = settings
        _migrate_legacy_skills_data(_LEGACY_SKILLS_DB_PATH, _LEGACY_COMPILED_PATH, SKILLS_DB_PATH, COMPILED_PATH)
        COMPILED_PATH.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(SKILLS_DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS skill_candidates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_pattern TEXT NOT NULL,
                    action_sequence TEXT NOT NULL,
                    success_count INTEGER DEFAULT 1,
                    last_used TEXT,
                    compiled INTEGER DEFAULT 0,
                    skill_name TEXT
                )
            """)
            conn.commit()

    def record_successful_task(self, task: str, action_sequence: List[Dict]):
        """
        Record a successful task completion.
        If this pattern has been seen before, increment count.
        At threshold, compile into a skill.
        """
        pattern = self._extract_pattern(task)
        existing = self._find_existing(pattern)

        if existing:
            new_count = existing["success_count"] + 1
            with sqlite3.connect(SKILLS_DB_PATH) as conn:
                conn.execute(
                    "UPDATE skill_candidates SET success_count=?, last_used=? WHERE id=?",
                    (new_count, datetime.now().isoformat(), existing["id"])
                )
                conn.commit()

            # Compile at 3 successful runs
            if new_count >= 3 and not existing["compiled"]:
                self._compile_skill(existing["id"], pattern, action_sequence)
        else:
            with sqlite3.connect(SKILLS_DB_PATH) as conn:
                conn.execute(
                    "INSERT INTO skill_candidates (task_pattern, action_sequence, last_used) VALUES (?,?,?)",
                    (pattern, json.dumps(action_sequence), datetime.now().isoformat())
                )
                conn.commit()

    def find_compiled_skill(self, task: str) -> Optional[Dict]:
        """
        Check if a compiled skill exists for this task.
        Returns the skill dict or None.
        """
        pattern = self._extract_pattern(task)
        with sqlite3.connect(SKILLS_DB_PATH) as conn:
            row = conn.execute(
                "SELECT skill_name, action_sequence FROM skill_candidates WHERE compiled=1 AND task_pattern=?",
                (pattern,)
            ).fetchone()

        if row:
            skill_path = COMPILED_PATH / f"{row[0]}.json"
            if skill_path.exists():
                with open(skill_path) as f:
                    return json.load(f)
        return None

    def _compile_skill(self, skill_id: int, pattern: str, action_sequence: List[Dict]):
        """Compile a skill into a reusable JSON procedure."""
        skill_name = f"skill_{pattern[:30].replace(' ', '_')}_{skill_id}"

        skill_data = {
            "name": skill_name,
            "pattern": pattern,
            "compiled_at": datetime.now().isoformat(),
            "actions": action_sequence,
            "version": 1
        }

        skill_path = COMPILED_PATH / f"{skill_name}.json"
        with open(skill_path, "w") as f:
            json.dump(skill_data, f, indent=2)

        with sqlite3.connect(SKILLS_DB_PATH) as conn:
            conn.execute(
                "UPDATE skill_candidates SET compiled=1, skill_name=? WHERE id=?",
                (skill_name, skill_id)
            )
            conn.commit()

        logger.info(f"Compiled skill: {skill_name}")

    def _extract_pattern(self, task: str) -> str:
        """Extract the core pattern from a task description."""
        # Simple approach: lowercase, remove specific values, keep structure
        import re
        pattern = task.lower().strip()
        # Remove specific URLs, numbers, names
        pattern = re.sub(r'https?://\S+', 'URL', pattern)
        pattern = re.sub(r'\d+', 'N', pattern)
        return pattern[:100]

    def _find_existing(self, pattern: str) -> Optional[Dict]:
        with sqlite3.connect(SKILLS_DB_PATH) as conn:
            row = conn.execute(
                "SELECT id, success_count, compiled FROM skill_candidates WHERE task_pattern=?",
                (pattern,)
            ).fetchone()
        if row:
            return {"id": row[0], "success_count": row[1], "compiled": row[2]}
        return None

    def list_skills(self) -> List[Dict]:
        """List all compiled skills."""
        with sqlite3.connect(SKILLS_DB_PATH) as conn:
            rows = conn.execute(
                "SELECT skill_name, task_pattern, success_count FROM skill_candidates WHERE compiled=1"
            ).fetchall()
        return [{"name": r[0], "pattern": r[1], "uses": r[2]} for r in rows]
