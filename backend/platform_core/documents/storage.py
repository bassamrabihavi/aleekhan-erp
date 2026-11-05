"""Encrypted file storage (DEC-053 ST-A: folder on the encrypted server volume) - PHASE_01 / 01.3.

Bytes are stored under a random key (never the client's file name or path) below
``settings.ALEEKHAN_DOCUMENT_STORAGE_ROOT``, additionally encrypted per object with AES-256-GCM
(``identity.crypto``; the associated data binds the blob to its storage key). The database row
(``platform_stored_object``) keeps size, server-side SHA-256 and the key reference - never the key.
Files are never executed or rendered by the server; downloads are attachments only.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Final

from django.conf import settings

from platform_core.engine.errors import DependencyUnavailable, EngineContractError
from platform_core.identity import crypto

KEY_BYTES: Final = 32  # token_urlsafe(32) -> 43 characters, matches STORAGE_KEY_PATTERN


def _root() -> Path:
    root = str(getattr(settings, "ALEEKHAN_DOCUMENT_STORAGE_ROOT", "") or "")
    if not root:
        raise DependencyUnavailable("document storage is not configured")
    path = Path(root)
    if not path.is_dir():
        raise DependencyUnavailable("document storage folder is not available")
    return path


def volume_name() -> str:
    return str(getattr(settings, "ALEEKHAN_DOCUMENT_VOLUME", "documents"))


def new_storage_key() -> str:
    return secrets.token_urlsafe(KEY_BYTES)


def _path(storage_key: str) -> Path:
    if not storage_key or "/" in storage_key or "\\" in storage_key or storage_key.startswith("."):
        raise EngineContractError("invalid storage key")
    return _root() / storage_key[:2] / storage_key


def _aad(storage_key: str) -> bytes:
    return b"file:" + storage_key.encode("ascii")


def write(storage_key: str, data: bytes) -> str:
    """Encrypt and store; returns the key reference. Never overwrites an existing object."""
    target = _path(storage_key)  # refuses first when storage is not configured
    key_ref, blob = crypto.encrypt(data, aad=_aad(storage_key))
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise EngineContractError("storage key collision")
    tmp = target.with_suffix(".part")
    with open(tmp, "xb") as fh:  # exclusive create: never overwrite
        fh.write(blob)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, target)
    return key_ref


def read(storage_key: str, *, key_ref: str) -> bytes:
    try:
        blob = _path(storage_key).read_bytes()
    except FileNotFoundError:
        raise DependencyUnavailable("stored file is missing") from None
    return crypto.decrypt(blob, key_ref=key_ref, aad=_aad(storage_key))


def delete(storage_key: str) -> bool:
    """Remove the bytes (purge). Returns False if they were already gone."""
    try:
        _path(storage_key).unlink()
    except FileNotFoundError:
        return False
    return True
