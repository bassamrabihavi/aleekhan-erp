"""Sensitive-key guard for audit snapshots, outbox payloads and staged import rows.

Contract: no salary, password, secret or token values in audit ``before/after`` or in generic event
payloads (STATE_EVENT_AND_API_CONTRACT "Event catalog", DATA_TABLE OutboxEvent S1, SECURITY_BASELINE).

* Audit snapshots are **redacted**: the key is kept (so the audit shows *that* the field changed), the value
  is replaced by :data:`REDACTED`.
* Outbox payloads are **rejected** if they contain a sensitive key: events must carry identifiers only.
* Staged import rows (``integration.imports.stage_rows``) are **refused** with ``SENSITIVE_FIELD``.

The key list is a technical deny-list (defence in depth), not a business classification. The full sensitive
field classification (customer PII, HR fields) is owner decision DEC-028 and the PHASE_01 field matrix.

REV-0602 (00.7): factory workbooks have Persian headers, so keys are normalised before matching
(:func:`normalize_key`): Unicode NFKC, case-fold, Arabic yeh/kaf/alef-maksura -> Persian ``ی``/``ک``, teh
marbuta/heh-with-yeh -> ``ه``, and removal of ZWNJ/ZWJ, bidi marks, tatweel, harakat, whitespace, ``_``,
``-`` and ``.``. Persian fragments are chosen so that common innocent factory words do not match (e.g.
``قرمز`` "red" contains ``رمز``; ``کارتن`` "carton" contains ``کارت``; ``شبانه`` "nightly" contains
``شبا``): short ambiguous words are matched only as the *whole* key (:data:`SENSITIVE_KEY_EXACT`).
Known deliberate over-match: ``حقوق`` also hits ``حقوقی`` ("legal", e.g. ``شخص حقوقی``); refusing such a
column is the safe direction until DEC-028 classifies fields (documented in docs/security).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator
from typing import Any

REDACTED = "[REDACTED]"

# Characters folded to their Persian form before matching (after NFKC).
_CHAR_MAP = str.maketrans(
    {
        "\u064a": "\u06cc",  # ARABIC LETTER YEH -> PERSIAN YEH
        "\u0649": "\u06cc",  # ARABIC LETTER ALEF MAKSURA -> PERSIAN YEH
        "\u0643": "\u06a9",  # ARABIC LETTER KAF -> PERSIAN KEHEH
        "\u0629": "\u0647",  # TEH MARBUTA -> HEH
        "\u06c0": "\u0647",  # HEH WITH YEH ABOVE -> HEH
    }
)
# ZWNJ/ZWJ/ZWSP, bidi marks and isolates, BOM, tatweel, Arabic harakat, whitespace and separators.
_STRIP_RE = re.compile(
    "[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff\u0640\u064b-\u065f\u0670"
    r"\s_\-.]+"
)

# Matched as a substring of the normalised key.
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
    "iban",
    "nationalid",
    "nationalcode",
    "cardnumber",
    "cardno",
    "bankaccount",
    # Persian (normalised form: no spaces/ZWNJ, Persian yeh/kaf)
    "حقوق",  # salary (also matches فیش حقوقی)
    "دستمزد",  # wage
    "رمزعبور",  # password
    "رمزورود",  # login password
    "رمزدوم",  # second password
    "رمزپویا",  # one-time password
    "کلمهعبور",  # password
    "کلمهرمز",  # password
    "گذرواژه",  # password
    "پسورد",  # password (loanword)
    "پسوورد",
    "توکن",  # token
    "کلیدخصوصی",  # private key
    "شمارهکارت",  # card number
    "کارتبانکی",  # bank card
    "شمارهشبا",  # IBAN
    "کدشبا",
    "حساببانکی",  # bank account
    "کدملی",  # national id
    "شمارهملی",  # national id
)

# Short names matched only as the whole normalised key (as substrings they would hit innocent keys, e.g.
# "otp" in "footprint", "رمز" in "قرمز", "شبا" in "شبانه", "مزد" in "مزدا").
SENSITIVE_KEY_EXACT: frozenset[str] = frozenset({"otp", "pin", "mfacode", "totp", "رمز", "مزد", "شبا"})


def normalize_key(key: str) -> str:
    """Normalised form of a key used for deny-list matching (see module docstring)."""
    folded = unicodedata.normalize("NFKC", key).casefold().translate(_CHAR_MAP)
    return _STRIP_RE.sub("", folded)


def is_sensitive_key(key: str) -> bool:
    norm = normalize_key(key)
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
