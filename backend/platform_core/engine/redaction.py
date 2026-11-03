"""Sensitive-key guard for audit snapshots and outbox payloads.

Contract: no salary, password, secret or token values in audit ``before/after`` or in generic event
payloads (STATE_EVENT_AND_API_CONTRACT "Event catalog", DATA_TABLE OutboxEvent S1, SECURITY_BASELINE).

* Audit snapshots are **redacted**: the key is kept (so the audit shows *that* the field changed), the value
  is replaced by :data:`REDACTED`.
* Outbox payloads are **rejected** if they contain a sensitive key: events must carry identifiers only.

The key list is a technical deny-list (defence in depth), not a business classification. The full sensitive
field classification (customer PII, HR fields) is owned by later phases and step 00.7.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

REDACTED = "[REDACTED]"

# Matched as a case-insensitive substring of the key, after removing "-" and "_".
SENSITIVE_KEY_FRAGMENTS: tuple[str, ...] = (
    "password",
    "passwd",
    "secret",
    "token",
    "apikey",
    "privatekey",
    "credential",
    "salary",
    "wage",
    "payroll",
)


# Short names matched exactly (as substrings they would hit innocent keys, e.g. "otp" in "footprint").
SENSITIVE_KEY_EXACT: frozenset[str] = frozenset({"otp", "pin", "mfacode", "totp"})


def is_sensitive_key(key: str) -> bool:
    norm = key.lower().replace("_", "").replace("-", "")
    return norm in SENSITIVE_KEY_EXACT or any(fragment in norm for fragment in SENSITIVE_KEY_FRAGMENTS)


def redact(value: Any) -> Any:
    """Return a deep copy of ``value`` with values of sensitive keys replaced by :data:`REDACTED`."""
    if isinstance(value, dict):
        return {k: (REDACTED if is_sensitive_key(str(k)) else redact(v)) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [redact(v) for v in value]
    return value


def sensitive_paths(value: Any, prefix: str = "") -> Iterator[str]:
    """Yield dotted paths of sensitive keys (used to reject outbox payloads)."""
    if isinstance(value, dict):
        for k, v in value.items():
            path = f"{prefix}.{k}" if prefix else str(k)
            if is_sensitive_key(str(k)):
                yield path
            else:
                yield from sensitive_paths(v, path)
    elif isinstance(value, list | tuple):
        for i, v in enumerate(value):
            yield from sensitive_paths(v, f"{prefix}[{i}]")
