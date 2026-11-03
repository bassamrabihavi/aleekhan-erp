"""Business-rule gate: unknown or unapproved rules are blocked (handoff AGENTS / PHASE_00 Gate).

Every code path that applies a business rule depending on an owner decision (``DEC-###``) must call
:func:`require_approved_rule` first. Until the decision is APPROVED *and* its implementation is reviewed, the
call raises :class:`RuleNotApproved` (HTTP 409, ``code=RULE_NOT_APPROVED``, ``decision_id``).

The registry of approved rule decisions is deliberately an in-code constant, not a setting or a DB row: it can
only change through a reviewed commit (no environment toggle can unlock a rule). In PHASE_00 it is empty:
code/die/stock and all other business rules are locked (PHASE_00 Gate). Governance decisions approved in
``control/`` (e.g. DEC-045 about the backup drill) are not business rules and do not belong here.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from functools import wraps
from types import MappingProxyType
from typing import Final, ParamSpec, TypeVar

from .errors import DECISION_ID_RE, RuleNotApproved

# decision_id -> short note (commit / review reference). Add an entry only together with the implementation
# of that rule and its golden tests (golden test ``test_no_business_rule_approved_in_phase_00`` guards it).
# Read-only view (REV-0010): runtime code cannot insert an entry and unlock a rule; the private dict below is
# the only source and is edited in reviewed commits only.
_APPROVED_RULE_DECISIONS: Final[dict[str, str]] = {}
APPROVED_RULE_DECISIONS: Final[Mapping[str, str]] = MappingProxyType(_APPROVED_RULE_DECISIONS)

P = ParamSpec("P")
R = TypeVar("R")


def _check_id(decision_id: str) -> None:
    if not DECISION_ID_RE.fullmatch(decision_id):
        raise ValueError(f"decision_id must match DEC-###, got {decision_id!r}")


def is_rule_approved(decision_id: str) -> bool:
    _check_id(decision_id)
    return decision_id in APPROVED_RULE_DECISIONS


def require_approved_rule(decision_id: str, *, rule: str = "") -> None:
    """Raise :class:`RuleNotApproved` unless ``decision_id`` is in the approved registry."""
    if not is_rule_approved(decision_id):
        detail = f"Rule '{rule}' is blocked until {decision_id} is approved." if rule else ""
        raise RuleNotApproved(decision_id, detail)


def rule_gated(decision_id: str, *, rule: str = "") -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator form: the wrapped function never runs while the decision is not approved."""
    _check_id(decision_id)

    def deco(fn: Callable[P, R]) -> Callable[P, R]:
        @wraps(fn)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            require_approved_rule(decision_id, rule=rule or fn.__qualname__)
            return fn(*args, **kwargs)

        return wrapper

    return deco
