"""
SAM macOS Audio Guard & Hardware Silent Override:
Allows SAM's voice to play audibly at its user-configured in-app volume level,
even when macOS system output volume has been muted or lowered by the user.
Automatically restores the user's previous system volume and mute status when speech ends.
"""

import logging
import platform
import re
import subprocess
import threading
from typing import Dict, Any, Optional

logger = logging.getLogger("SAM.MacAudio")
IS_MAC = platform.system() == "Darwin"


class MacAudioGuard:
    _lock = threading.Lock()
    _saved_state: Optional[Dict[str, Any]] = None
    _active_sessions: int = 0

    @classmethod
    def get_volume_settings(cls) -> Dict[str, Any]:
        """Query current macOS output volume and mute status."""
        if not IS_MAC:
            return {"volume": 80, "muted": False}
        try:
            res = subprocess.run(
                ["osascript", "-e", "get volume settings"],
                capture_output=True,
                text=True,
                timeout=2
            )
            if res.returncode == 0 and res.stdout:
                out = res.stdout.strip()
                vol_m = re.search(r"output volume:(\d+)", out)
                muted_m = re.search(r"output muted:(true|false)", out)
                volume = int(vol_m.group(1)) if vol_m else 65
                muted = (muted_m.group(1).lower() == "true") if muted_m else False
                return {"volume": volume, "muted": muted}
        except Exception as e:
            logger.debug(f"Failed to query macOS volume settings: {e}")
        return {"volume": 65, "muted": False}

    @classmethod
    def ensure_audible(cls, target_volume: int = 75, override_silent: bool = True) -> Dict[str, Any]:
        """
        Temporarily unmutes macOS and raises volume to SAM's designated in-app level
        so speech is clearly audible even if the user has muted the Mac.
        """
        if not IS_MAC:
            return {"ok": True, "overridden": False}

        with cls._lock:
            current = cls.get_volume_settings()
            if cls._saved_state is None:
                cls._saved_state = current
            cls._active_sessions += 1

            if not override_silent and current["muted"]:
                return {"ok": True, "overridden": False, "muted": True}

            target_vol = max(15, min(100, int(target_volume or 75)))

            try:
                # Unmute and set output volume to SAM target volume
                cmd = f"set volume output muted false\nset volume output volume {target_vol}"
                subprocess.run(
                    ["osascript", "-e", cmd],
                    capture_output=True,
                    timeout=2
                )
                logger.debug(f"macOS audio unmuted for SAM speech: target_volume={target_vol}")
                return {
                    "ok": True,
                    "overridden": True,
                    "target_volume": target_vol,
                    "previous_state": cls._saved_state
                }
            except Exception as e:
                logger.debug(f"Failed to set macOS volume: {e}")
                return {"ok": False, "error": str(e)}

    @classmethod
    def restore_audible(cls) -> Dict[str, Any]:
        """
        Restores macOS output volume and mute status to whatever the user had
        before SAM started speaking.
        """
        if not IS_MAC:
            return {"ok": True, "restored": False}

        with cls._lock:
            cls._active_sessions = max(0, cls._active_sessions - 1)
            if cls._active_sessions > 0:
                return {"ok": True, "restored": False, "sessions_remaining": cls._active_sessions}

            saved = cls._saved_state
            cls._saved_state = None

            if not saved:
                return {"ok": True, "restored": False}

            try:
                vol = saved.get("volume", 50)
                muted_str = "true" if saved.get("muted", False) else "false"
                cmd = f"set volume output volume {vol}\nset volume output muted {muted_str}"
                subprocess.run(
                    ["osascript", "-e", cmd],
                    capture_output=True,
                    timeout=2
                )
                logger.debug(f"macOS audio restored to previous state: {saved}")
                return {"ok": True, "restored": True, "restored_state": saved}
            except Exception as e:
                logger.debug(f"Failed to restore macOS volume: {e}")
                return {"ok": False, "error": str(e)}


mac_audio_guard = MacAudioGuard
