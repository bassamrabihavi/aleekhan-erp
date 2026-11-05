"""Map a refusal by a database guard to a stable client error (PHASE_01 / 01.3).

The DB guards of migrations 0007-0011 name their rule in the message (``ck_*`` / ``uq_*`` / ``ex_*``
constraint
names, ``immutable_column`` / ``append_only`` / ``terminal_immutable``; docs/db/ERD.md section 6). Inside
:func:`db_rules` such an ``IntegrityError`` becomes:

* ``uq_*`` (duplicate value)                -> 400 ``VALIDATION_FAILED``, ``errors[].code`` = rule name
  (state-guarding partial uniques such as ``uq_position_one_active_head`` -> 409 like the rules below)
* every other named rule                    -> 409 ``STATE_TRANSITION_NOT_ALLOWED``, ``errors[].code`` = rule
* an unnamed integrity error                -> re-raised (programming error -> 500)

The block runs in a savepoint, so the caller's unit of work stays usable and decides what to do. The message
text itself (which may contain values) is never copied into the client error - only the rule name.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Final

from django.db import IntegrityError, transaction

from .errors import FieldError, StateTransitionNotAllowed, ValidationFailed

_RULE_RE: Final = re.compile(r"\b((?:ck|uq|ex)_[a-z0-9_]+|immutable_column|append_only|terminal_immutable)\b")


# partial unique indexes guarding a state ("one ACTIVE head", "one PENDING request"): conflicts, not input
_STATEFUL_UNIQUE: Final = re.compile(r"_(one|single|active|pending)(_|$)")


def rule_name(exc: BaseException) -> str | None:
    match = _RULE_RE.search(str(exc))
    return match.group(1) if match else None


@contextmanager
def db_rules(using: str = "default") -> Iterator[None]:
    try:
        with transaction.atomic(using=using):
            yield
    except IntegrityError as exc:
        rule = rule_name(exc)
        if rule is None:
            raise
        error = FieldError("", rule.upper())
        if rule.startswith("uq_") and not _STATEFUL_UNIQUE.search(rule):
            raise ValidationFailed(f"refused by {rule}", errors=[error]) from None
        raise StateTransitionNotAllowed(f"refused by {rule}", errors=[error]) from None
