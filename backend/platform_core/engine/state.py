"""Generic, declarative state machine (server-side transition guard).

A machine lists its states and allowed transitions. :meth:`StateMachine.assert_transition` raises
``STATE_TRANSITION_NOT_ALLOWED`` for anything not listed, and ``RULE_NOT_APPROVED`` for a listed transition
whose guard depends on an unapproved decision (``rule_gates``). Business machines are defined in their own
phases from approved contracts; PHASE_00 only defines the platform outbox machine (``outbox.py``).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from .errors import StateTransitionNotAllowed
from .rules import require_approved_rule


@dataclass(frozen=True)
class StateMachine:
    name: str
    states: frozenset[str]
    transitions: Mapping[str, frozenset[str]]
    # (from, to) -> DEC-### whose approval is required before the transition may run.
    rule_gates: Mapping[tuple[str, str], str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for src, dsts in self.transitions.items():
            unknown = ({src} | set(dsts)) - self.states
            if unknown:
                raise ValueError(f"{self.name}: unknown states in transitions: {sorted(unknown)}")
        for (src, dst), _dec in self.rule_gates.items():
            if dst not in self.transitions.get(src, frozenset()):
                raise ValueError(f"{self.name}: rule gate on an undefined transition {src}->{dst}")

    def can(self, src: str, dst: str) -> bool:
        return dst in self.transitions.get(src, frozenset())

    def assert_transition(self, src: str, dst: str) -> None:
        if not self.can(src, dst):
            raise StateTransitionNotAllowed(f"{self.name}: {src} -> {dst} is not allowed")
        decision_id = self.rule_gates.get((src, dst))
        if decision_id is not None:
            require_approved_rule(decision_id, rule=f"{self.name}: {src} -> {dst}")

    @property
    def terminal_states(self) -> frozenset[str]:
        return frozenset(s for s in self.states if not self.transitions.get(s))
