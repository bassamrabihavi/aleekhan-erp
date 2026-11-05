"""TOTP (RFC 6238 over RFC 4226 HOTP) with the standard library only (DEC-050: authenticator apps).

Parameters are the RFC / authenticator-app defaults (TECHNICAL, compatible with Google/Microsoft
Authenticator): HMAC-SHA1, 6 digits, 30-second steps, a tolerance of one step either side for clock skew.
Replay guard: a code is accepted only for a time step strictly greater than the factor's ``last_used_step``
(the DB trigger ``platform_mfa_factor_guard`` also refuses a non-increasing step).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
from typing import Final
from urllib.parse import quote, urlencode

DIGITS: Final = 6
STEP_SECONDS: Final = 30
SKEW_STEPS: Final = 1
SECRET_BYTES: Final = 20  # 160 bits, RFC 4226 recommendation for HMAC-SHA1


def new_secret() -> bytes:
    return secrets.token_bytes(SECRET_BYTES)


def hotp(secret: bytes, counter: int, *, digits: int = DIGITS, digest: str = "sha1") -> str:
    mac = hmac.new(secret, struct.pack(">Q", counter), getattr(hashlib, digest)).digest()
    offset = mac[-1] & 0x0F
    code = (struct.unpack(">I", mac[offset : offset + 4])[0] & 0x7FFFFFFF) % (10**digits)
    return str(code).zfill(digits)


def time_step(unix_time: float, *, step: int = STEP_SECONDS) -> int:
    return int(unix_time // step)


def totp(secret: bytes, unix_time: float, *, digits: int = DIGITS, digest: str = "sha1") -> str:
    return hotp(secret, time_step(unix_time), digits=digits, digest=digest)


def match_step(secret: bytes, code: str, unix_time: float, *, last_used_step: int | None) -> int | None:
    """The time step the code belongs to (within the skew window and after ``last_used_step``), else None."""
    if len(code) != DIGITS or not code.isascii() or not code.isdigit():
        return None
    now_step = time_step(unix_time)
    matched: int | None = None
    for candidate in range(now_step - SKEW_STEPS, now_step + SKEW_STEPS + 1):
        if hmac.compare_digest(hotp(secret, candidate), code):  # constant-time compare, check all candidates
            matched = candidate
    if matched is None or (last_used_step is not None and matched <= last_used_step):
        return None
    return matched


def provisioning_uri(secret: bytes, *, account: str, issuer: str = "Aleekhan") -> str:
    """``otpauth://`` URI shown once as a QR code; never logged or stored."""
    label = quote(f"{issuer}:{account}")
    query = urlencode(
        {
            "secret": base64.b32encode(secret).decode("ascii").rstrip("="),
            "issuer": issuer,
            "algorithm": "SHA1",
            "digits": DIGITS,
            "period": STEP_SECONDS,
        }
    )
    return f"otpauth://totp/{label}?{query}"
