"""
SAM Connect — Device Identity Cryptography

(New in agent/cross-device.)

Every SAM Connect ("direct"/LAN-paired) device authenticates itself with
an Ed25519 keypair it generates and keeps on-device — the private key
never leaves the device, never crosses the network, and SAM never asks
for it. Pairing only ever transmits the PUBLIC key (see
connect/transports/lan_http.py's redeem payload), which is only useful
for verifying that device's signatures, not for impersonating it. This
is a deliberately different trust model from the Telegram channel: a
Telegram chat_id is authenticated by Telegram itself, so
connect/core/device_registry.py never needed to store a secret for it.
A LAN HTTP request has no such built-in authentication, so it needs one.

Same library and key format (cryptography's hazmat Ed25519, PKCS8/
SubjectPublicKeyInfo PEM) as licensing/keygen.py, for two reasons: it's
already a project dependency (see requirements.txt's "Licensing (Phase
3)" section) so this adds no new dependency, and it keeps exactly one
Ed25519 code path's worth of conventions in the codebase instead of two.

This module only holds the primitives (generate / serialize / sign /
verify). The actual request-signing *scheme* — what bytes get signed,
which headers carry the signature, replay-window/nonce handling — is
connect/transports/lan_http.py's job, not this module's; keeping the
primitives here free of any HTTP-shaped assumptions means they're just as
usable for a future non-HTTP transport (connect/__init__.py already
reserves connect/transports/ for more than one).
"""

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


class KeyFormatError(ValueError):
    """A stored/received public key PEM was missing, truncated, or not
    actually an Ed25519 key. Distinct from InvalidSignature (signature
    forgery attempt / wrong key) — a caller may want to treat a
    corrupted-key row differently from a rejected signature."""


def generate_keypair():
    """Returns (private_key, public_key). Only ever called on the
    device side (see connect/transports/lan_http.py's pairing flow and
    the reference client in tests/) — SAM Core never generates a device
    keypair on a device's behalf."""
    private_key = Ed25519PrivateKey.generate()
    return private_key, private_key.public_key()


def serialize_public_key(public_key: Ed25519PublicKey) -> str:
    """PEM text, safe to store in DeviceRegistry and safe to log —
    knowing a device's public key never lets anyone impersonate it."""
    pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return pem.decode("ascii")


def load_public_key(pem_text: str) -> Ed25519PublicKey:
    try:
        key = serialization.load_pem_public_key(pem_text.encode("ascii"))
    except (ValueError, TypeError) as e:
        raise KeyFormatError(f"not a valid PEM public key: {e}") from e
    if not isinstance(key, Ed25519PublicKey):
        raise KeyFormatError("key is not Ed25519 — SAM Connect only accepts Ed25519 device keys")
    return key


def serialize_private_key(private_key: Ed25519PrivateKey) -> str:
    """Never sent over the network or given to SAM Core/server code —
    exists so a device-side client (or the offline test double in
    tests/) can persist its own key across restarts the same way
    licensing/keygen.py persists the license-signing key."""
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return pem.decode("ascii")


def load_private_key(pem_text: str) -> Ed25519PrivateKey:
    try:
        key = serialization.load_pem_private_key(pem_text.encode("ascii"), password=None)
    except (ValueError, TypeError) as e:
        raise KeyFormatError(f"not a valid PEM private key: {e}") from e
    if not isinstance(key, Ed25519PrivateKey):
        raise KeyFormatError("key is not Ed25519 — SAM Connect only accepts Ed25519 device keys")
    return key


def sign(private_key: Ed25519PrivateKey, message: bytes) -> bytes:
    return private_key.sign(message)


def verify(public_key: Ed25519PublicKey, message: bytes, signature: bytes) -> bool:
    """True/False, never raises — callers (connect/transports/lan_http.py)
    want a boolean to turn into a 401, not an exception to catch at every
    call site."""
    try:
        public_key.verify(signature, message)
        return True
    except InvalidSignature:
        return False
