"""
SAM Apple Continuity & Ecosystem Synchronization

Interfaces with macOS AppleScript / osascript to support:
- Querying & writing to Apple Notes
- Fetching & appending to Apple Reminders
- Safari active tab inspection & URL handoff
- macOS notification push
"""

import logging
import platform
import subprocess
from typing import Dict, List, Optional, Any

logger = logging.getLogger("SAM.Connect.AppleContinuity")

IS_MAC = platform.system() == "Darwin"


def _run_applescript(script: str) -> Optional[str]:
    if not IS_MAC:
        return None
    try:
        res = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=5
        )
        if res.returncode == 0:
            return res.stdout.strip()
        else:
            logger.debug(f"AppleScript error: {res.stderr.strip()}")
            return None
    except Exception as e:
        logger.debug(f"Failed to execute AppleScript: {e}")
        return None


class AppleContinuityManager:
    """
    Manages Continuity integration between macOS and connected iOS devices.
    """

    def is_available(self) -> bool:
        return IS_MAC

    def get_safari_active_tab(self) -> Optional[Dict[str, str]]:
        """Returns the current URL and title open in Safari on macOS."""
        script = """
        tell application "Safari"
            if (count of windows) > 0 then
                set currentURL to URL of current tab of front window
                set currentTitle to name of current tab of front window
                return currentTitle & "||" & currentURL
            end if
        end tell
        """
        output = _run_applescript(script)
        if output and "||" in output:
            title, url = output.split("||", 1)
            return {"title": title, "url": url}
        return None

    def open_url_in_safari(self, url: str) -> bool:
        """Opens a handoff URL in Safari."""
        script = f"""
        tell application "Safari"
            activate
            open location "{url}"
        end tell
        """
        return _run_applescript(script) is not None

    def add_apple_note(self, title: str, body: str, folder: str = "Notes") -> bool:
        """Creates a note in Apple Notes, which syncs via iCloud to iPhone."""
        safe_title = title.replace('"', '\\"')
        safe_body = body.replace('"', '\\"')
        script = f"""
        tell application "Notes"
            tell account 1
                make new note at folder "{folder}" with properties {{name:"{safe_title}", body:"<h1>{safe_title}</h1><br/>{safe_body}"}}
            end tell
        end tell
        """
        return _run_applescript(script) is not None

    def add_apple_reminder(self, title: str, list_name: str = "Reminders", due_date: Optional[str] = None) -> bool:
        """Adds a reminder to Apple Reminders."""
        safe_title = title.replace('"', '\\"')
        script = f"""
        tell application "Reminders"
            tell list "{list_name}"
                make new reminder with properties {{name:"{safe_title}"}}
            end tell
        end tell
        """
        return _run_applescript(script) is not None

    def status(self) -> Dict[str, Any]:
        return {
            "platform": "macOS",
            "available": self.is_available(),
            "continuity_services": ["safari_handoff", "apple_notes_sync", "apple_reminders_sync"]
        }
