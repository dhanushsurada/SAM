"""
SAM Connect — Device Registry

(Moved here in Phase 3A.5 — originated as ecosystem/device_registry.py
during the mainline product's Phase 2. Device trust/pairing is a SAM
Connect concept per the finalized architecture, even though today it's
only wired up for the Telegram interface. ecosystem/device_registry.py now
forwards here; there is only one implementation.)

Stores which remote devices (currently: Telegram chats) are trusted to send
SAM commands, and manages the one-time pairing token lifecycle (QR code ->
scan -> /start <token> -> trusted).

Stored in ~/.sam_data/ecosystem/devices.db — separate from Founder Mode and
episodic memory, since this is device/identity metadata, not AI data. This
mirrors the "Local Data Separation" principle from the PDR: account/device
metadata and AI data (conversations, memory, Founder Mode) are always kept
apart, even though both happen to live locally right now. The on-disk
folder is still named "ecosystem" (ECOSYSTEM_DIR below) even though the
Python code now lives under connect/core/ — moving code must not move or
rename existing user data.

IMPORTANT — pairing today happens over Telegram (an internet relay), not
local WiFi. See docs/PHASE_2_TELEGRAM_BRIDGE.md for the full explanation of
that trade-off. Real same-WiFi device pairing (zero third party involved)
is still the long-term SAM Connect plan once a native Android app exists —
this registry's schema was kept generic enough (device_id, device_name,
channel) that a future WiFi-paired device can be added as a row here too,
not a separate system.
"""

import json
import logging
import secrets
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict

from connect.core.capabilities import validate_capabilities, CapabilityValidationError
from connect.core import crypto

logger = logging.getLogger("SAM.Connect.DeviceRegistry")

SAM_DATA_DIR = Path.home() / ".sam_data"
ECOSYSTEM_DIR = SAM_DATA_DIR / "ecosystem"
DEVICES_DB_PATH = ECOSYSTEM_DIR / "devices.db"

PAIRING_TOKEN_TTL_MINUTES = 10

# agent/cross-device additions below (schema stays additive — see
# _init_db's migration block. Everything above this line is unchanged
# from the pre-existing Phase 2 implementation.)

# A "direct" (LAN, same-WiFi) device is considered online if a signed
# heartbeat arrived within this many seconds; older than that and
# sweep_offline() flips it back to offline. Chosen well above the
# heartbeat interval a client is expected to use (see
# docs/architecture/CROSS_DEVICE_PROTOCOL.md) so a couple of missed
# beats from an app briefly backgrounded don't flap the state.
HEARTBEAT_STALE_SECONDS = 90

# connection_state only has real meaning for "direct" devices, which
# heartbeat; a Telegram device is authenticated per-message by Telegram
# itself and never calls record_heartbeat(). Reporting "offline" for a
# channel that was never tracking liveness in the first place would be
# actively misleading to a Devices UI, so channels other than "direct"
# always read back as "n/a" regardless of the raw column value.
CONNECTION_STATE_NOT_APPLICABLE = "n/a"
DIRECT_CHANNEL = "direct"


def connection_state_for(device: Dict) -> str:
    """Normalizes the raw connection_state column for display: only
    "direct" devices track liveness via heartbeat (see
    DeviceRegistry.record_heartbeat/sweep_offline), so any other channel
    always reads back as CONNECTION_STATE_NOT_APPLICABLE regardless of
    the column's stored value. Takes the dict shape list_devices()/
    get_device_by_external_id() return (needs "channel" and
    "connection_state" keys)."""
    if device.get("channel") != DIRECT_CHANNEL:
        return CONNECTION_STATE_NOT_APPLICABLE
    return device.get("connection_state") or "offline"


class DeviceRegistry:
    def __init__(self):
        ECOSYSTEM_DIR.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(DEVICES_DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS devices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel TEXT NOT NULL DEFAULT 'telegram',
                    external_id TEXT NOT NULL,
                    device_name TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    pairing_token TEXT,
                    token_expires_at TEXT,
                    paired_at TEXT,
                    last_active TEXT,
                    UNIQUE(channel, external_id)
                )
            """)
            # agent/cross-device: additive columns for pre-existing Phase 2
            # databases that predate the device/capability/trust model.
            # SQLite has no ADD COLUMN IF NOT EXISTS, so inspect the schema
            # and add only missing columns. Migration errors are allowed to
            # surface rather than being mistaken for duplicate columns.
            # A device row created before this migration reads back with platform=None,
            # capabilities={}, public_key=None, connection_state='offline'
            # (i.e. CONNECTION_STATE_NOT_APPLICABLE once read through
            # connection_state_for()) until it re-pairs or sends its first
            # heartbeat — never a crash, never a silently dropped device.
            existing_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(devices)").fetchall()
            }
            for column_name, column_sql in (
                ("platform", "ALTER TABLE devices ADD COLUMN platform TEXT"),
                ("protocol_version", "ALTER TABLE devices ADD COLUMN protocol_version TEXT"),
                ("capabilities", "ALTER TABLE devices ADD COLUMN capabilities TEXT NOT NULL DEFAULT '{}'"),
                ("public_key", "ALTER TABLE devices ADD COLUMN public_key TEXT"),
                ("connection_state", "ALTER TABLE devices ADD COLUMN connection_state TEXT NOT NULL DEFAULT 'offline'"),
            ):
                if column_name not in existing_columns:
                    conn.execute(column_sql)
            conn.commit()
        logger.info(f"Device registry DB at {DEVICES_DB_PATH}")

    # ─── Pairing ─────────────────────────────────────────────────────────

    def create_pairing_token(self, channel: str = "telegram") -> str:
        """Generates a fresh one-time token for a new pairing attempt. Not
        tied to a device yet — that happens when the token is redeemed."""
        token = secrets.token_urlsafe(16)
        expires_at = (datetime.now() + timedelta(minutes=PAIRING_TOKEN_TTL_MINUTES)).isoformat()
        with sqlite3.connect(DEVICES_DB_PATH) as conn:
            conn.execute(
                "INSERT INTO devices (channel, external_id, status, pairing_token, token_expires_at) "
                "VALUES (?,?,?,?,?)",
                (channel, f"__pending_{token}", "awaiting_redemption", token, expires_at)
            )
            conn.commit()
        logger.info(f"Pairing token created, expires {expires_at}")
        return token

    def redeem_token(self, token: str, external_id: str, device_name: str = "Phone",
                      channel: str = "telegram", *, platform: Optional[str] = None,
                      public_key: Optional[str] = None, capabilities: Optional[Dict] = None,
                      protocol_version: Optional[str] = None) -> bool:
        """
        Called when someone sends /start <token> to the bot (channel=
        "telegram"), or when a direct/LAN device redeems a QR-scanned
        pairing token (channel="direct" — see
        connect/transports/lan_http.py). Validates the token (exists, not
        expired, not already used), and if valid, promotes that
        external_id (a Telegram chat_id, or a client-generated device_id
        for "direct") to a trusted device. Returns True on success, False
        on invalid/expired/reused token.

        platform/public_key/capabilities/protocol_version are agent/
        cross-device additions, all keyword-only and all optional — the
        existing Telegram call site (interfaces/telegram/telegram_bridge.py)
        never passes them and its behavior is byte-for-byte unchanged.
        When given (the "direct" channel always gives all four — see
        connect/transports/lan_http.py), they're validated up front, before
        any row is touched, so a malformed pairing payload can't leave a
        row half-written: a bad public_key raises
        connect.core.crypto.KeyFormatError, bad capabilities raises
        connect.core.capabilities.CapabilityValidationError. Both are
        ValueError subclasses; callers that only care about "did pairing
        succeed" can still catch ValueError as one thing.
        """
        if public_key is not None:
            crypto.load_public_key(public_key)  # raises KeyFormatError if malformed
        normalized_capabilities = None
        if capabilities is not None:
            normalized_capabilities = validate_capabilities(capabilities)  # raises CapabilityValidationError

        with sqlite3.connect(DEVICES_DB_PATH) as conn:
            # Claim the write lock before reading the one-time token. With
            # SQLite's default deferred transaction, concurrent callers
            # can all observe the pending row before any one of them
            # updates it, allowing the same pairing token to trust multiple
            # devices. BEGIN IMMEDIATE serializes the read/validate/consume
            # sequence so only one caller can redeem it.
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT id, token_expires_at FROM devices WHERE pairing_token = ? "
                "AND status = 'awaiting_redemption' AND channel = ?",
                (token, channel)
            ).fetchone()

            if not row:
                logger.warning("Pairing token not found or already used")
                return False

            row_id, expires_at = row
            if datetime.now() > datetime.fromisoformat(expires_at):
                logger.warning("Pairing token expired")
                conn.execute("DELETE FROM devices WHERE id = ?", (row_id,))
                conn.commit()
                return False

            # Does a row for this (channel, external_id) already exist —
            # trusted under a different row, OR previously revoked? Both
            # occupy the same UNIQUE(channel, external_id) slot the plain
            # INSERT/UPDATE below assumes is free. Originally this only
            # checked status = 'trusted', so re-pairing a *revoked* device
            # (a legitimate flow — the fresh token here is the same trust
            # bootstrap as a first-time pairing, see this method's
            # docstring) crashed with a sqlite3.IntegrityError instead of
            # ever reaching a return value. Found via the offline test
            # suite's revoke-then-re-pair case, not a hypothetical.
            existing = conn.execute(
                "SELECT id, status FROM devices WHERE channel = ? AND external_id = ?",
                (channel, external_id)
            ).fetchone()
            if existing:
                existing_id, existing_status = existing
                conn.execute("DELETE FROM devices WHERE id = ?", (row_id,))
                updates, params = [], []
                if existing_status != "trusted":
                    now = datetime.now().isoformat()
                    updates += ["status = 'trusted'", "device_name = ?", "paired_at = ?", "last_active = ?"]
                    params += [device_name, now, now]
                # Refreshes whichever of these a caller actually passed —
                # unchanged from the original already-trusted case: a bare
                # re-scan with nothing new to report (Telegram never passes
                # any of these) still touches nothing beyond the status
                # restore above, if any.
                if platform is not None:
                    updates.append("platform = ?"); params.append(platform)
                if public_key is not None:
                    updates.append("public_key = ?"); params.append(public_key)
                if normalized_capabilities is not None:
                    updates.append("capabilities = ?"); params.append(json.dumps(normalized_capabilities))
                if protocol_version is not None:
                    updates.append("protocol_version = ?"); params.append(protocol_version)
                if updates:
                    params.append(existing_id)
                    conn.execute(f"UPDATE devices SET {', '.join(updates)} WHERE id = ?", params)
                conn.commit()
                logger.info(
                    f"external_id {external_id} re-paired (was {existing_status}) — cleaned up spare token row"
                )
                return True

            now = datetime.now().isoformat()
            conn.execute(
                "UPDATE devices SET external_id = ?, device_name = ?, status = 'trusted', "
                "pairing_token = NULL, token_expires_at = NULL, paired_at = ?, last_active = ?, "
                "platform = ?, public_key = ?, capabilities = ?, protocol_version = ? "
                "WHERE id = ?",
                (external_id, device_name, now, now,
                 platform, public_key,
                 json.dumps(normalized_capabilities) if normalized_capabilities is not None else "{}",
                 protocol_version, row_id)
            )
            conn.commit()
        logger.info(f"Device paired: {channel}/{external_id} ({device_name})")
        return True

    # ─── Trust checks ───────────────────────────────────────────────────

    def is_trusted(self, external_id: str, channel: str = "telegram") -> bool:
        with sqlite3.connect(DEVICES_DB_PATH) as conn:
            row = conn.execute(
                "SELECT id FROM devices WHERE channel = ? AND external_id = ? AND status = 'trusted'",
                (channel, external_id)
            ).fetchone()
        return row is not None

    def touch_last_active(self, external_id: str, channel: str = "telegram"):
        with sqlite3.connect(DEVICES_DB_PATH) as conn:
            conn.execute(
                "UPDATE devices SET last_active = ? WHERE channel = ? AND external_id = ? AND status = 'trusted'",
                (datetime.now().isoformat(), channel, external_id)
            )
            conn.commit()

    # ─── Connection & capabilities (agent/cross-device) ───────────────────
    # Everything below is new. All of it is keyed by (channel, external_id)
    # — the same identity pair is_trusted()/touch_last_active() already
    # use above — never by the internal `id` int that revoke()/rename()
    # use below. That split is deliberate, not an inconsistency: a device
    # only ever knows its own external_id (the Telegram chat_id Telegram
    # hands it, or the UUID a direct device generated for itself), so
    # every device-facing operation (this section) has to be reachable
    # that way. A desktop management UI, by contrast, always starts from
    # list_devices() — which already has the internal id sitting right
    # there — so revoke()/rename() staying keyed by id (unchanged from
    # Phase 2) costs that UI nothing and keeps this diff off two working,
    # tested methods. See docs/architecture/CROSS_DEVICE_PROTOCOL.md for
    # the full read-through of which identifier each endpoint expects.

    def get_device_by_external_id(self, external_id: str, channel: str = DIRECT_CHANNEL) -> Optional[Dict]:
        """Full row — including capabilities parsed back to a dict, and
        connection_state normalized through connection_state_for() — for
        one trusted device. This is the lookup connect/transports/
        lan_http.py's signature verification and connect/services/
        task_handoff.py's capability checks use."""
        with sqlite3.connect(DEVICES_DB_PATH) as conn:
            row = conn.execute(
                "SELECT id, channel, external_id, device_name, status, paired_at, last_active, "
                "platform, protocol_version, capabilities, public_key, connection_state "
                "FROM devices WHERE channel = ? AND external_id = ? AND status = 'trusted'",
                (channel, external_id)
            ).fetchone()
        if not row:
            return None
        cols = ["id", "channel", "external_id", "device_name", "status", "paired_at", "last_active",
                "platform", "protocol_version", "capabilities", "public_key", "connection_state"]
        device = dict(zip(cols, row))
        device["capabilities"] = json.loads(device["capabilities"] or "{}")
        device["connection_state"] = connection_state_for(device)
        return device

    def verify_signature(self, external_id: str, message: bytes, signature: bytes,
                          channel: str = DIRECT_CHANNEL) -> bool:
        """False for: device not found, not trusted, revoked, or no
        public_key on file (e.g. a Telegram-channel row, or a
        pre-migration direct row that hasn't re-paired yet) — every one
        of those is simply "reject the request", never an exception
        connect/transports/lan_http.py has to catch specially."""
        device = self.get_device_by_external_id(external_id, channel=channel)
        if not device or not device.get("public_key"):
            return False
        try:
            public_key = crypto.load_public_key(device["public_key"])
        except crypto.KeyFormatError:
            logger.error(f"Stored public_key for {channel}/{external_id} is corrupt")
            return False
        return crypto.verify(public_key, message, signature)

    def record_heartbeat(self, external_id: str, channel: str = DIRECT_CHANNEL) -> bool:
        """Called after *every* successfully signature-verified request
        from a direct device (see connect/transports/lan_http.py's
        require_trusted_device dependency), not only a dedicated
        heartbeat endpoint — any verified request is proof of liveness.
        Returns False if the device isn't a currently-trusted row."""
        with sqlite3.connect(DEVICES_DB_PATH) as conn:
            cur = conn.execute(
                "UPDATE devices SET last_active = ?, connection_state = 'online' "
                "WHERE channel = ? AND external_id = ? AND status = 'trusted'",
                (datetime.now().isoformat(), channel, external_id)
            )
            conn.commit()
            return cur.rowcount > 0

    def sweep_offline(self, stale_after_seconds: int = HEARTBEAT_STALE_SECONDS,
                       channel: str = DIRECT_CHANNEL) -> List[Dict]:
        """Flips every trusted device on `channel` whose last_active is
        older than stale_after_seconds from connection_state='online' to
        'offline', and returns the rows that just made that transition —
        connect/core/events.py callers use that list to publish
        device.disconnected exactly once per transition, not once per
        sweep. Call this on a periodic timer (connect/transports/
        lan_http.py runs one); nothing in this class runs its own."""
        cutoff = (datetime.now() - timedelta(seconds=stale_after_seconds)).isoformat()
        with sqlite3.connect(DEVICES_DB_PATH) as conn:
            rows = conn.execute(
                "SELECT id, channel, external_id, device_name FROM devices "
                "WHERE channel = ? AND status = 'trusted' AND connection_state = 'online' "
                "AND (last_active IS NULL OR last_active < ?)",
                (channel, cutoff)
            ).fetchall()
            if rows:
                ids = [r[0] for r in rows]
                conn.execute(
                    f"UPDATE devices SET connection_state = 'offline' WHERE id IN "
                    f"({','.join('?' * len(ids))})",
                    ids
                )
                conn.commit()
        cols = ["id", "channel", "external_id", "device_name"]
        transitioned = [dict(zip(cols, r)) for r in rows]
        if transitioned:
            logger.info(f"{len(transitioned)} device(s) swept to offline (no heartbeat in {stale_after_seconds}s)")
        return transitioned

    def update_capabilities(self, external_id: str, capabilities: Dict,
                             channel: str = DIRECT_CHANNEL) -> bool:
        """Raises CapabilityValidationError on a malformed map (caller's
        job to turn that into a 422 — see connect/transports/
        lan_http.py). Returns False if the device isn't currently
        trusted, True on a successful update."""
        normalized = validate_capabilities(capabilities)
        with sqlite3.connect(DEVICES_DB_PATH) as conn:
            cur = conn.execute(
                "UPDATE devices SET capabilities = ? WHERE channel = ? AND external_id = ? AND status = 'trusted'",
                (json.dumps(normalized), channel, external_id)
            )
            conn.commit()
            return cur.rowcount > 0

    # ─── Management ─────────────────────────────────────────────────────

    def list_devices(self, include_pending: bool = False) -> List[Dict]:
        """agent/cross-device: now also returns platform, capabilities
        (parsed to a dict), and a normalized connection_state. Purely
        additive — every key this returned before Phase 3A.5 is still
        here unchanged, so interfaces/telegram/telegram_bridge.py's
        /devices command (which only reads device_name/paired_at) and any
        other existing caller keeps working without modification."""
        status_filter = "" if include_pending else "WHERE status = 'trusted'"
        with sqlite3.connect(DEVICES_DB_PATH) as conn:
            rows = conn.execute(
                f"SELECT id, channel, external_id, device_name, status, paired_at, last_active, "
                f"platform, protocol_version, capabilities, connection_state "
                f"FROM devices {status_filter} ORDER BY id DESC"
            ).fetchall()
        cols = ["id", "channel", "external_id", "device_name", "status", "paired_at", "last_active",
                "platform", "protocol_version", "capabilities", "connection_state"]
        devices = [dict(zip(cols, r)) for r in rows]
        for device in devices:
            device["capabilities"] = json.loads(device["capabilities"] or "{}")
            device["connection_state"] = connection_state_for(device)
        return devices

    def revoke(self, device_id: int) -> bool:
        with sqlite3.connect(DEVICES_DB_PATH) as conn:
            cur = conn.execute("UPDATE devices SET status = 'revoked' WHERE id = ? AND status = 'trusted'",
                                (device_id,))
            conn.commit()
            return cur.rowcount > 0

    def rename(self, device_id: int, new_name: str) -> bool:
        with sqlite3.connect(DEVICES_DB_PATH) as conn:
            cur = conn.execute("UPDATE devices SET device_name = ? WHERE id = ? AND status = 'trusted'",
                                (new_name, device_id))
            conn.commit()
            return cur.rowcount > 0

    def cleanup_expired_tokens(self):
        """Housekeeping — removes stale awaiting_redemption rows whose
        token has expired without ever being used."""
        with sqlite3.connect(DEVICES_DB_PATH) as conn:
            now = datetime.now().isoformat()
            cur = conn.execute(
                "DELETE FROM devices WHERE status = 'awaiting_redemption' AND token_expires_at < ?",
                (now,)
            )
            conn.commit()
            if cur.rowcount:
                logger.info(f"Cleaned up {cur.rowcount} expired pairing token(s)")

    @staticmethod
    def db_path() -> Path:
        return DEVICES_DB_PATH
