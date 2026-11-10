"""Encrypted file storage (DEC-053 ST-A: folder on the encrypted server volume) - PHASE_01 / 01.3.

Bytes are stored under a random key (never the client's file name or path) below
``settings.ALEEKHAN_DOCUMENT_STORAGE_ROOT``, additionally encrypted per object with AES-256-GCM
(``identity.crypto``; the associated data binds the blob to its storage key). The database row
(``platform_stored_object``) keeps size, server-side SHA-256 and the key reference - never the key.
Files are never executed or rendered by the server; downloads are attachments only.
"""

from __future__ import annotations

import os
import re
import secrets
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from django.conf import settings

from platform_core.engine.errors import DependencyUnavailable, EngineContractError
from platform_core.identity import crypto

KEY_BYTES: Final = 32  # token_urlsafe(32) -> 43 characters, matches STORAGE_KEY_PATTERN
PARTIAL_SUFFIX: Final = ".part"
_KEY_RE: Final = re.compile(r"[A-Za-z0-9_-]{43}")


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


def is_configured() -> bool:
    return bool(str(getattr(settings, "ALEEKHAN_DOCUMENT_STORAGE_ROOT", "") or ""))


@dataclass(frozen=True)
class StoredFile:
    """One file found below the storage root (orphan cleanup, 01.7). ``partial`` = a ``.part`` left-over."""

    storage_key: str
    partial: bool
    mtime: float
    size: int


def scan_files() -> Iterator[StoredFile]:
    """Every object file of the two-level layout (``<root>/<key[:2]>/<key>`` or ``<key>.part``).

    Files with any other name or place are never reported (so never deleted): the cleanup only ever touches
    names this module could have written. Symlinks are skipped.
    """
    root = _root()
    for sub in sorted(root.iterdir()):
        if not sub.is_dir() or sub.is_symlink() or len(sub.name) != 2:
            continue
        for f in sorted(sub.iterdir()):
            if f.is_symlink() or not f.is_file():
                continue
            name, partial = f.name, f.name.endswith(PARTIAL_SUFFIX)
            key = name[: -len(PARTIAL_SUFFIX)] if partial else name
            if not _KEY_RE.fullmatch(key) or key[:2] != sub.name:
                continue
            st = f.stat()
            yield StoredFile(storage_key=key, partial=partial, mtime=st.st_mtime, size=st.st_size)


def delete_file(item: StoredFile) -> bool:
    """Remove one file reported by :func:`scan_files` (idempotent: False if it is already gone)."""
    target = _path(item.storage_key)
    if item.partial:
        target = target.with_suffix(PARTIAL_SUFFIX)
    try:
        target.unlink()
    except FileNotFoundError:
        return False
    return True
