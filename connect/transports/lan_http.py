"""
SAM Connect — LAN HTTP Transport

(New in agent/cross-device. This is the "transport boundary" the Agent 3
execution prompt's section 1 lists as owned scope, and the first thing
ever placed in connect/transports/ — see that package's docstring.)

=== What this is ===
Same-WiFi HTTP, the transport connect/bridges/vivo_iqoo/README.md
already documents as how phone connectivity works today ("today's phone
connectivity is same-WiFi HTTP, not an Office Kit integration"). This
module turns that from an unauthenticated convention into an
authenticated one, by defining exactly what a "direct" (paired,
non-Telegram) device must send on every request to prove who it is.

=== Why signatures instead of a bearer secret ===
connect/core/device_registry.py's Telegram rows never needed a SAM-issued
secret because Telegram itself authenticates the chat_id. A LAN HTTP
request has no such built-in guarantee, so it needs its own. The
straightforward alternative — SAM hands the device a shared secret at
pairing time, device sends it back on every request — works, but means a
leaked/logged request (or a compromised task_store.db-style backup) also
leaks something an attacker could use to *impersonate* the device.
Ed25519 avoids that: the device generates its own keypair
(connect.core.crypto.generate_keypair), pairing only ever transmits the
PUBLIC half, and SAM never possesses anything capable of forging that
device's signature. This is the same reasoning licensing/keygen.py's
docstring gives for keeping the license-signing private key off the
server — applied to devices instead of licenses.

=== Request signing scheme ===
A direct device signs every authenticated request with four headers:

    X-SAM-Device-Id:  <device_id>          (the external_id it paired with)
    X-SAM-Timestamp:  <unix seconds, int>
    X-SAM-Nonce:      <>=16 random url-safe chars, unique per request>
    X-SAM-Signature:  <base64 Ed25519 signature>

...over the canonical message built by canonical_message():

    "{METHOD}\\n{PATH}\\n{TIMESTAMP}\\n{NONCE}\\n{SHA256_HEX(BODY)}"

PATH is the request path only (no scheme/host/query string — SAM Connect
has no query-string-bearing endpoints today; if one is added later, it
must be folded into the signed message, not left out). BODY is the exact
raw request body bytes (empty bytes for a GET/no-body request — sha256 of
b"" is still a real, fixed hash, not skipped).

=== Replay protection ===
verify_request() rejects a timestamp more than TIMESTAMP_WINDOW_SECONDS
away from server time (covers both a stale replayed request and a
clock badly out of sync), and separately rejects a (device_id, nonce)
pair it's already seen within that same window (covers a byte-for-byte
replay inside the timestamp window, which a timestamp check alone
wouldn't catch). The nonce cache is in-memory and per-process — see
NonceCache's docstring for what that does and doesn't protect against.

=== Pairing payload ===
The desktop-side QR code (build_pairing_qr_payload) encodes where to
connect, not who to trust — trust is established by the one-time token
inside it plus the device's public key, submitted together in the
redemption request. See docs/architecture/CROSS_DEVICE_PROTOCOL.md for
the full wire format and a worked pairing example.
"""

import base64
import hashlib
import logging
import socket
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, Optional

from connect.core.device_registry import DeviceRegistry, DIRECT_CHANNEL, PAIRING_TOKEN_TTL_MINUTES
from connect.core import crypto

logger = logging.getLogger("SAM.Connect.Transports.LanHttp")

PROTOCOL_VERSION = "1.0"

# How far a request's X-SAM-Timestamp may drift from server time, in
# either direction, before it's rejected. Generous enough to absorb a
# phone with a few seconds of clock skew and normal LAN latency, tight
# enough that a captured request is useless well before anyone could
# realistically replay it by hand.
TIMESTAMP_WINDOW_SECONDS = 120


class DeviceAuthError(Exception):
    """Base class for every reason verify_request() can reject a
    request. interfaces/api/device_auth.py catches this one type and
    maps it to an HTTP 401 — subclasses exist for logging/testing
    granularity, not because callers need to handle them differently."""


class MissingCredentialsError(DeviceAuthError):
    pass


class TimestampOutOfRangeError(DeviceAuthError):
    pass


class ReplayedRequestError(DeviceAuthError):
    pass


class DeviceNotTrustedError(DeviceAuthError):
    pass


class InvalidSignatureError(DeviceAuthError):
    pass


def canonical_message(method: str, path: str, timestamp: str, nonce: str, body: bytes) -> bytes:
    body_hash = hashlib.sha256(body or b"").hexdigest()
    return f"{method.upper()}\n{path}\n{timestamp}\n{nonce}\n{body_hash}".encode("utf-8")


class NonceCache:
    """
    In-memory (device_id, nonce) -> expiry. Prevents a byte-for-byte
    replayed request from re-verifying a second time inside the window a
    timestamp check alone would still accept.

    Deliberately in-memory and per-process, matching every other piece
    of runtime (non-SQLite) state in this codebase (interfaces/api/
    events.py's history, interfaces/api/task_store.py's _cancel_events).
    Consequence, stated plainly rather than left implicit: a server
    restart forgets recently-used nonces (a replay of a request whose
    timestamp is still in-window can succeed once after a restart — the
    timestamp window bounds how long that stays possible), and if SAM's
    API server is ever run as more than one process, nonces aren't
    shared between them. Today's runtime (interfaces/api/server.py's
    single `uvicorn.run(app, ...)`) is single-process, so this is a
    documented forward-looking limitation, not a live one — flagged here
    for whoever changes that.

    TTL is 2x TIMESTAMP_WINDOW_SECONDS, not 1x (hardening pass — it was
    1x originally, which left a real replay gap): verify_request accepts a
    timestamp anywhere in [now - W, now + W], so a request from a device
    whose clock runs ahead is accepted at t0 carrying ts up to t0 + W, and
    its timestamp then stays acceptable until ts + W = t0 + 2W. A cache
    that forgets the nonce after only W seconds lets that request be
    replayed during (t0 + W, t0 + 2W]. Found by a regression test failing
    against the 1x TTL (tests/test_connect_offline.py's
    test_nonce_cache_and_replay_window), not by reasoning alone.

    Pruning: expired entries are dropped in bulk only when the dict grows
    past 4096 entries; below that an expired entry lingers in memory but
    is ignored on lookup (an expired key is treated as fresh). Only
    requests that pass signature verification are ever recorded (see
    verify_request), so growth is bounded by what *authenticated* devices
    send within one TTL. Worst case, a sustained burst past ~17 requests
    per second (4096 entries / 240s) keeps the live set above the
    threshold and makes each check rebuild the dict under the lock:
    wasteful, not incorrect.
    """

    def __init__(self, ttl_seconds: float = 2 * TIMESTAMP_WINDOW_SECONDS):
        self._ttl = ttl_seconds
        self._seen: Dict[tuple, float] = {}
        self._lock = threading.Lock()

    def check_and_record(self, device_id: str, nonce: str) -> bool:
        """True if (device_id, nonce) is fresh and has now been recorded;
        False if it was already seen and still within its TTL."""
        now = time.time()
        key = (device_id, nonce)
        with self._lock:
            if len(self._seen) > 4096:  # cheap bound; real pruning happens below either way
                self._seen = {k: v for k, v in self._seen.items() if v > now}
            expiry = self._seen.get(key)
            if expiry is not None and expiry > now:
                return False
            self._seen[key] = now + self._ttl
            return True


def verify_request(registry: DeviceRegistry, nonce_cache: NonceCache, *, method: str, path: str,
                    body: bytes, device_id: str, timestamp: str, nonce: str,
                    signature_b64: str) -> Dict:
    """
    Framework-agnostic verification: raises a DeviceAuthError subclass on
    any failure, returns the verified device dict (as
    DeviceRegistry.get_device_by_external_id returns it) on success, and
    records a heartbeat as a side effect of success (see
    DeviceRegistry.record_heartbeat's docstring for why that's correct
    here and not just in a dedicated heartbeat endpoint).
    interfaces/api/device_auth.py is the only intended caller — it's a
    thin FastAPI dependency that pulls these same values out of the
    request/headers and turns any DeviceAuthError into a 401.
    """
    if not (device_id and timestamp and nonce and signature_b64):
        raise MissingCredentialsError(
            "X-SAM-Device-Id, X-SAM-Timestamp, X-SAM-Nonce and X-SAM-Signature are all required"
        )

    try:
        ts = float(timestamp)
    except ValueError:
        raise TimestampOutOfRangeError("X-SAM-Timestamp must be a unix timestamp")
    if abs(time.time() - ts) > TIMESTAMP_WINDOW_SECONDS:
        raise TimestampOutOfRangeError(
            f"timestamp outside the {TIMESTAMP_WINDOW_SECONDS}s window — check device clock"
        )

    # NOTE: the nonce is deliberately NOT recorded here. It used to be —
    # before signature verification — which let anyone on the LAN grow the
    # cache with garbage requests and, worse, "burn" a legitimate
    # request's nonce by submitting a forged copy of it first (the forged
    # copy fails verification but had already consumed the nonce, so the
    # genuine request then read as a replay). Unauthenticated input must
    # not mutate replay state; see the check_and_record call below.
    try:
        signature = base64.b64decode(signature_b64, validate=True)
    except Exception as e:
        raise InvalidSignatureError(f"X-SAM-Signature is not valid base64: {e}") from e

    # Looked up (rather than delegated whole to
    # DeviceRegistry.verify_signature) specifically so "you were never
    # paired, or you were revoked" and "you're paired, but this
    # signature doesn't match your registered key" can be told apart.
    # On a single-user, same-WiFi system the realistic failure a device
    # owner hits is the second one — e.g. they reinstalled the app and it
    # generated a new keypair without re-pairing — and a flat "auth
    # failed" would send them debugging the wrong thing.
    device = registry.get_device_by_external_id(device_id, channel=DIRECT_CHANNEL)
    if not device or not device.get("public_key"):
        raise DeviceNotTrustedError("this device is not currently paired — pair it again")

    try:
        public_key = crypto.load_public_key(device["public_key"])
    except crypto.KeyFormatError:
        logger.error(f"Stored public_key for direct/{device_id} is corrupt")
        raise DeviceNotTrustedError("this device's stored key is corrupt — pair it again")

    message = canonical_message(method, path, timestamp, nonce, body)
    if not crypto.verify(public_key, message, signature):
        raise InvalidSignatureError(
            "signature does not match this device's registered key — if you reinstalled "
            "or reset the app, pair it again"
        )

    # Only now, with the signature verified, is it safe to record the nonce.
    # check_and_record is atomic under the cache's lock, so two concurrent
    # copies of the same *valid* request still yield exactly one success.
    if not nonce_cache.check_and_record(device_id, nonce):
        raise ReplayedRequestError("this (device, nonce) pair was already used")

    registry.record_heartbeat(device_id, channel=DIRECT_CHANNEL)
    device["connection_state"] = "online"  # reflect the heartbeat we just recorded without a second DB read
    return device


# ─── Discovery / pairing payload ───────────────────────────────────────────

def detect_lan_ip() -> str:
    """Best-effort local IPv4 address on the same LAN the phone would be
    on. Uses the standard no-packets-sent UDP-connect trick (asks the OS
    routing table which interface WOULD be used, doesn't actually
    require 8.8.8.8 to be reachable). Falls back to 127.0.0.1 — which
    will not work for a real phone, but keeps this function total rather
    than raising, since a caller building a pairing payload for local
    manual testing (e.g. from the offline test suite, or a machine with
    no network interface at all) shouldn't hard-fail here."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        logger.warning("Could not determine a LAN IP; pairing QR will encode 127.0.0.1")
        return "127.0.0.1"
    finally:
        s.close()


def build_pairing_qr_payload(registry: DeviceRegistry, port: int, host: Optional[str] = None) -> Dict:
    """Generates a fresh pairing token and returns the dict a desktop
    caller (e.g. a future `python -m connect.transports.lan_http` CLI,
    mirroring interfaces/telegram/pair_new_device.py) QR-encodes as JSON.
    Contains where to connect and a one-time proof the scan came from the
    trusted screen — never a long-lived credential."""
    token = registry.create_pairing_token(channel=DIRECT_CHANNEL)
    expires_at = (datetime.now() + timedelta(minutes=PAIRING_TOKEN_TTL_MINUTES)).isoformat()
    return {
        "v": PROTOCOL_VERSION,
        "token": token,
        "host": host or detect_lan_ip(),
        "port": port,
        "expires_at": expires_at,
    }


def redeem_pairing(registry: DeviceRegistry, payload: Dict) -> Dict:
    """
    Server side of pairing redemption — what
    interfaces/api/connect_routes.py's POST /api/connect/pairing/redeem
    calls after FastAPI/pydantic has already validated the payload shape.
    `payload` is the device's submission:

        {
          "token": "...",                 # from the scanned QR
          "device_id": "<client UUID>",   # the device picks this itself
          "device_name": "Dhanush's iQOO 13",
          "platform": "android",
          "public_key": "-----BEGIN PUBLIC KEY-----...",
          "capabilities": {...},          # connect.core.capabilities shape
          "protocol_version": "1.0"
        }

    Returns {"device_id": ..., "status": "trusted"} on success. Raises
    ValueError (covers both connect.core.crypto.KeyFormatError and
    connect.core.capabilities.CapabilityValidationError, both ValueError
    subclasses — see redeem_token's docstring) if public_key or
    capabilities are malformed, and DeviceNotTrustedError if the token
    itself is missing/expired/already used — the two failure kinds a
    caller genuinely needs to tell apart, to return 422 vs 401.
    """
    required = ("token", "device_id", "device_name", "platform", "public_key")
    missing = [k for k in required if not payload.get(k)]
    if missing:
        raise ValueError(f"pairing payload missing required field(s): {missing}")

    ok = registry.redeem_token(
        payload["token"], payload["device_id"], device_name=payload["device_name"],
        channel=DIRECT_CHANNEL, platform=payload["platform"], public_key=payload["public_key"],
        capabilities=payload.get("capabilities") or {}, protocol_version=payload.get("protocol_version"),
    )
    if not ok:
        raise DeviceNotTrustedError("pairing token is invalid, expired, or already used")
    return {"device_id": payload["device_id"], "status": "trusted"}
