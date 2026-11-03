"""Reusable 14-digit code type (Rahkaran-style product/die codes).

Contract (ADR-001, DATA_TABLE.md conventions): a 14-digit code is a *string* of exactly 14 ASCII digits,
leading zeros preserved, stored as ``varchar(14)`` with a named CHECK constraint ``~ '^[0-9]{14}$'``.
It is never numeric. Each code column must also carry its namespace (``product_code`` vs ``die_code``);
the namespace is modelled by the owning table in later phases, not here.

This module validates *format only*. Issuing new codes is BLOCKED until DEC-005 / DEC-008.
No normalisation is applied (Persian/Arabic-Indic digits, spaces, dashes are rejected, not converted):
converting such input is an unapproved rule.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import CheckConstraint, Q
from django.utils.deconstruct import deconstructible

CODE14_LENGTH = 14
# PostgreSQL ARE pattern used in CHECK constraints (no newline-sensitive mode, so ``$`` = end of string).
CODE14_DB_PATTERN = r"^[0-9]{14}$"
# Python pattern: ASCII digits only (``\d`` would accept Persian digits); fullmatch, so a trailing
# newline is rejected (``$`` in Python would accept "…\n").
_CODE14_RE = re.compile(r"[0-9]{14}")

CODE14_ERROR_CODE = "invalid_code14"


def is_code14(value: object) -> bool:
    return isinstance(value, str) and _CODE14_RE.fullmatch(value) is not None


@deconstructible
class Code14Validator:
    message = "Code must be exactly 14 ASCII digits (string, leading zeros kept)."
    code = CODE14_ERROR_CODE

    def __call__(self, value: Any) -> None:
        if not is_code14(value):
            raise ValidationError(self.message, code=self.code, params={"value": value})

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Code14Validator)

    def __hash__(self) -> int:
        return hash(self.code)


validate_code14 = Code14Validator()


if TYPE_CHECKING:
    _CharFieldBase = models.CharField[str, str]
else:
    _CharFieldBase = models.CharField


class Code14Field(_CharFieldBase):
    """``varchar(14)`` holding a 14-digit code. Pair it with :func:`code14_check_constraint`."""

    description = "14-digit code (string)"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs["max_length"] = CODE14_LENGTH
        super().__init__(*args, **kwargs)
        if validate_code14 not in self.validators:
            self.validators.append(validate_code14)

    def deconstruct(self) -> Any:
        name, path, args, kwargs = super().deconstruct()
        kwargs.pop("max_length", None)
        return name, path, args, kwargs

    def to_python(self, value: Any) -> Any:
        # Never coerce ints: 00000000000123 as int would lose its leading zeros.
        if value is not None and not isinstance(value, str):
            raise ValidationError(Code14Validator.message, code=CODE14_ERROR_CODE)
        return value


def code14_check_constraint(field_name: str, name: str) -> CheckConstraint:
    """Named DB CHECK enforcing the 14-digit format on ``field_name`` (NULL allowed if the column is)."""
    return CheckConstraint(condition=Q(**{f"{field_name}__regex": CODE14_DB_PATTERN}), name=name)
