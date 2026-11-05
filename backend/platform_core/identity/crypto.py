"""Authenticated encryption of secrets at rest (PHASE_01 / 01.3): TOTP seeds and stored document bytes.

Library: ``cryptography`` (pyca, AES-256-GCM via OpenSSL). Python's standard library has no block cipher, and
hand-written cryptography is not acceptable; ``cryptography`` is the de-facto audited implementation (pinned
in backend/requirements.txt under the >= 14-day rule, docs/ops/CI.md).

Format (version 1): ``b"AKE1" || nonce(12) || ciphertext || tag(16)``. The associated data binds a ciphertext
to its purpose and owner (e.g. ``b"mfa:" + user id``), so a ciphertext copied to another row does not decrypt.
Keys: ``settings.ALEEKHAN_DATA_KEYS`` (from the secret store / environment, never the DB or Git); the DB
stores
only ``key_ref``. No configured key -> ``DEPENDENCY_UNAVAILABLE`` (the feature is refused, never stored
unencrypted).
"""

from __future__ import annotations

import os
from typing import Final

from django.conf import settings

from platform_core.engine.errors import DependencyUnavailable, EngineContractError

MAGIC: Final = b"AKE1"
NONCE_BYTES: Final = 12


def _keys() -> dict[str, bytes]:
    keys: dict[str, bytes] = dict(getattr(settings, "ALEEKHAN_DATA_KEYS", {}) or {})
    return keys


def current_key_ref() -> str:
    ref = str(getattr(settings, "ALEEKHAN_DATA_KEY_CURRENT", "") or "")
    if not ref or ref not in _keys():
        raise DependencyUnavailable("no data encryption key is configured")
    return ref


def encrypt(plaintext: bytes, *, aad: bytes) -> tuple[str, bytes]:
    """Encrypt with the current key. Returns ``(key_ref, blob)``."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    ref = current_key_ref()
    nonce = os.urandom(NONCE_BYTES)
    return ref, MAGIC + nonce + AESGCM(_keys()[ref]).encrypt(nonce, plaintext, aad)


def decrypt(blob: bytes, *, key_ref: str, aad: bytes) -> bytes:
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key = _keys().get(key_ref)
    if key is None:
        raise DependencyUnavailable("the data key of this ciphertext is not configured")
    if len(blob) < len(MAGIC) + NONCE_BYTES + 16 or not blob.startswith(MAGIC):
        raise EngineContractError("not an Aleekhan ciphertext")
    nonce = blob[len(MAGIC) : len(MAGIC) + NONCE_BYTES]
    try:
        return AESGCM(key).decrypt(nonce, blob[len(MAGIC) + NONCE_BYTES :], aad)
    except InvalidTag:
        raise EngineContractError("ciphertext authentication failed (tampered or wrong key)") from None
