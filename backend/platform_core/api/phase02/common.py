"""Shared machinery of the PHASE_02 endpoints (02.4): the PHASE_01 view, body, write and pagination helpers
plus the PHASE_02 record scope and the Persian search normalisation.

* Record scope (DEC-057 answer 3): PHASE_02 records carry no org unit; every grant covers all customers, so a
  record is visible only through a GLOBAL-scope assignment of the action (``authz.policy`` with an empty
  :class:`RecordScope`). An object outside it is 404 (SEC-01); a list outside it is empty (list == object
  check).
* Search (``q``): ``ي``/``ی``, ``ك``/``ک`` and the half-space are normalised on both sides; a search never
  merges or suggests a merge (C-71).
"""

from __future__ import annotations

import uuid
from typing import Any, Final

from django.db import models
from django.db.models import F, Func, Q, Value
from django.db.models.functions import Lower
from rest_framework.request import Request

from platform_core.authz import policy as P
from platform_core.authz.policy import Caller, RecordScope
from platform_core.engine.errors import FieldError, NotFound, ValidationFailed

from ..phase01.common import Phase01View
from . import bodies as _bodies  # noqa: F401 - registers the PHASE_02 body specs

GLOBAL: Final = RecordScope()
_FROM: Final = "يك‌"
_TO: Final = "یک "


class Phase02View(Phase01View):
    """PHASE_02 endpoint: session + action permission (+ MFA step-up) + GLOBAL record scope."""

    def in_scope(self) -> Caller:
        caller = self.caller()
        P.require_record(caller, self.required_action, GLOBAL)  # 404 without a GLOBAL grant
        return caller


def scoped[M: models.Model](view: Phase02View, qs: models.QuerySet[M]) -> models.QuerySet[M]:
    caller = view.caller()
    return qs if P.can(caller, view.required_action, GLOBAL) else qs.none()


def object_or_404[M: models.Model](view: Phase02View, qs: models.QuerySet[M], pk: Any) -> M:
    view.in_scope()
    obj = qs.filter(pk=pk).first()
    if obj is None:
        raise NotFound()
    return obj


def normalise(text: str) -> str:
    return text.translate(str.maketrans(_FROM, _TO)).lower()


def search_q(request: Request, *fields: str) -> tuple[dict[str, Any], Q] | None:
    """``q`` (1..100 characters) as an annotation + filter over ``fields`` (normalised contains)."""
    raw = request.query_params.get("q")
    if raw is None:
        return None
    if not 1 <= len(raw) <= 100:
        raise ValidationFailed(errors=[FieldError("q", "PATTERN_MISMATCH")])
    needle = normalise(raw.strip())
    annotations: dict[str, Any] = {}
    cond = Q(pk__in=[])
    for i, field in enumerate(fields):
        name = f"_q{i}"
        annotations[name] = Func(Lower(F(field)), Value(_FROM), Value(_TO), function="translate")
        cond |= Q(**{f"{name}__contains": needle})
    return annotations, cond


def apply_search[M: models.Model](
    request: Request, qs: models.QuerySet[M], *fields: str
) -> models.QuerySet[M]:
    found = search_q(request, *fields)
    if found is None:
        return qs
    annotations, cond = found
    out: models.QuerySet[M] = qs.annotate(**annotations).filter(cond)
    return out


def query_date(request: Request, name: str) -> Any:
    from ..phase01.common import DATE_RE

    raw = request.query_params.get(name)
    if raw is None:
        return None
    from datetime import date

    try:
        if not DATE_RE.fullmatch(raw):
            raise ValueError
        return date.fromisoformat(raw)
    except ValueError:
        raise ValidationFailed(errors=[FieldError(name, "INVALID_DATE")]) from None


def uuid_param(raw: Any) -> uuid.UUID:
    return raw if isinstance(raw, uuid.UUID) else uuid.UUID(str(raw))
