"""
Memory — Identity
Stored in ~/.sam_data/identity.json
Survives SAM reinstalls, clones, and folder deletions.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger("SAM.Identity")

SAM_DATA_DIR = Path.home() / ".sam_data"
IDENTITY_PATH = SAM_DATA_DIR / "identity.json"

DEFAULT_IDENTITY = {
    "name": "Dhanush",
    "assistant_name": "SAM",
    "about": "First-year B.Tech CSE student at NSRIT Visakhapatnam. Building SAM.",
    "projects": [
        "SAM — local AI assistant",
        "AnonCampus — NLP grievance platform",
        "NSRIT eSports Arena — tournament platform"
    ],
    "preferences": {
        "communication_style": "direct, no fluff, founder energy",
        "technical_depth": "high",
        "response_length": "concise for voice, detailed when asked"
    },
    "context": "Building SAM as both a personal tool and a future consumer product.",
    "connected_platforms": {
        "github": {
            "id": "github",
            "name": "GitHub",
            "handle": "dhanushsurada",
            "url": "https://github.com/dhanushsurada",
            "connected": True
        },
        "linkedin": {
            "id": "linkedin",
            "name": "LinkedIn",
            "handle": "dhanushsurada",
            "url": "https://www.linkedin.com/in/dhanushsurada",
            "connected": True
        },
        "twitter": {
            "id": "twitter",
            "name": "X (Twitter)",
            "handle": "dhanushsurada",
            "url": "https://x.com/dhanushsurada",
            "connected": True
        },
        "instagram": {
            "id": "instagram",
            "name": "Instagram",
            "handle": "dhanushsurada",
            "url": "https://www.instagram.com/dhanushsurada",
            "connected": True
        }
    }
}


class Identity:
    def __init__(self):
        SAM_DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not IDENTITY_PATH.exists():
            self._save(DEFAULT_IDENTITY)
            logger.info(f"Identity created at {IDENTITY_PATH}")
        else:
            logger.info(f"Identity loaded from {IDENTITY_PATH}")

    def load(self) -> dict:
        try:
            with open(IDENTITY_PATH) as f:
                data = json.load(f)
                # Ensure connected_platforms is always present
                if "connected_platforms" not in data:
                    data["connected_platforms"] = DEFAULT_IDENTITY["connected_platforms"]
                return data
        except Exception as e:
            logger.error(f"Identity load error: {e}")
            return DEFAULT_IDENTITY

    def get_platform(self, platform_id: str):
        """Return connected platform data if present and active."""
        identity = self.load()
        platforms = identity.get("connected_platforms", {})
        plat = platforms.get(platform_id.lower().strip())
        if plat and plat.get("connected", True):
            return plat
        return None

    def get_platform_url(self, platform_id: str):
        """Return the canonical URL for a connected platform."""
        plat = self.get_platform(platform_id)
        if plat and plat.get("url"):
            return plat["url"]
        return None

    def set_platform(self, platform_id: str, platform_data: dict):
        """Update or register a connected platform with canonical URL resolution."""
        identity = self.load()
        platforms = identity.setdefault("connected_platforms", {})
        pid = platform_id.lower().strip()
        handle = (platform_data.get("handle") or "").strip().lstrip("@")
        url = platform_data.get("url")
        if not url and handle:
            if pid == "github":
                url = f"https://github.com/{handle}"
            elif pid == "linkedin":
                url = f"https://www.linkedin.com/in/{handle}"
            elif pid in ("twitter", "x"):
                url = f"https://x.com/{handle}"
            elif pid == "instagram":
                url = f"https://www.instagram.com/{handle}"

        platforms[pid] = {
            "id": pid,
            "name": platform_data.get("name", pid.capitalize()),
            "handle": handle,
            "url": url,
            "connected": platform_data.get("connected", True),
        }
        self._save(identity)

    def update(self, updates: dict):
        identity = self.load()
        identity.update(updates)
        self._save(identity)
        logger.info(f"Identity updated: {list(updates.keys())}")

    def _save(self, data: dict):
        with open(IDENTITY_PATH, "w") as f:
            json.dump(data, f, indent=2)

    @staticmethod
    def path() -> Path:
        return IDENTITY_PATH
