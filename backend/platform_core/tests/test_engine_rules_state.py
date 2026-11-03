"""Rule gate (RULE_NOT_APPROVED), generic state machine, outbox machine golden, redaction properties."""

from __future__ import annotations

import json
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from platform_core.engine import rules
from platform_core.engine.errors import RuleNotApproved, StateTransitionNotAllowed
from platform_core.engine.outbox import OUTBOX_DELIVERY_MACHINE
from platform_core.engine.redaction import REDACTED, is_sensitive_key, redact, sensitive_paths
from platform_core.engine.state import StateMachine

GOLDEN_DIR = Path(__file__).parent / "golden"


# ------------------------------------------------------------------------------------------- rule gate
def test_no_business_rule_approved_in_phase_00() -> None:
    """PHASE_00 Gate: code/die/stock and every other business rule stay locked."""
    assert dict(rules.APPROVED_RULE_DECISIONS) == {}


def test_approved_rule_registry_is_immutable_at_runtime() -> None:
    """REV-0010: runtime code cannot insert an approval and unlock a rule."""
    registry: Any = rules.APPROVED_RULE_DECISIONS
    with pytest.raises(TypeError):
        registry["DEC-005"] = "sneaky"
    with pytest.raises((TypeError, AttributeError)):
        registry.update({"DEC-005": "sneaky"})
    with pytest.raises((TypeError, AttributeError)):
        registry.setdefault("DEC-005", "sneaky")
    assert not rules.is_rule_approved("DEC-005")


@pytest.mark.parametrize("decision_id", ["DEC-005", "DEC-006", "DEC-008", "DEC-015", "DEC-999"])
def test_require_approved_rule_blocks_unapproved(decision_id: str) -> None:
    with pytest.raises(RuleNotApproved) as exc:
        rules.require_approved_rule(decision_id, rule="synthetic.rule")
    assert exc.value.decision_id == decision_id
    assert exc.value.http_status == 409
    assert decision_id in exc.value.detail


@pytest.mark.parametrize("bad", ["", "DEC-5", "dec-005", "DEC-0005", "X"])
def test_malformed_decision_id_is_a_programming_error(bad: str) -> None:
    with pytest.raises(ValueError):
        rules.require_approved_rule(bad)
    with pytest.raises(ValueError):
        rules.rule_gated(bad)


def test_rule_gated_decorator_never_runs_body_until_approved(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    @rules.rule_gated("DEC-005")
    def issue_code(n: int) -> int:
        calls.append(n)
        return n

    with pytest.raises(RuleNotApproved):
        issue_code(1)
    assert calls == []
    # Simulates a future reviewed approval (test-only patch; there is no runtime toggle).
    monkeypatch.setattr(rules, "APPROVED_RULE_DECISIONS", MappingProxyType({"DEC-005": "synthetic approval"}))
    assert issue_code(2) == 2
    assert calls == [2]


# ------------------------------------------------------------------------------------------- state machine
SYNTH = StateMachine(
    name="synthetic.machine",
    states=frozenset({"A", "B", "C", "D"}),
    transitions={"A": frozenset({"B"}), "B": frozenset({"C", "D"}), "C": frozenset(), "D": frozenset({"A"})},
    rule_gates={("B", "D"): "DEC-012"},
)


@given(src=st.sampled_from(sorted(SYNTH.states)), dst=st.sampled_from(sorted(SYNTH.states)))
def test_state_machine_allows_exactly_listed_transitions(src: str, dst: str) -> None:
    listed = dst in SYNTH.transitions.get(src, frozenset())
    assert SYNTH.can(src, dst) is listed
    if not listed:
        with pytest.raises(StateTransitionNotAllowed):
            SYNTH.assert_transition(src, dst)
    elif (src, dst) in SYNTH.rule_gates:
        with pytest.raises(RuleNotApproved):
            SYNTH.assert_transition(src, dst)
    else:
        SYNTH.assert_transition(src, dst)


def test_state_machine_rejects_unknown_states_and_gates_on_undefined_edges() -> None:
    with pytest.raises(ValueError):
        StateMachine("x", frozenset({"A"}), {"A": frozenset({"Z"})})
    with pytest.raises(ValueError):
        StateMachine("x", frozenset({"A", "B"}), {"A": frozenset({"B"})}, rule_gates={("B", "A"): "DEC-001"})
    assert SYNTH.terminal_states == frozenset({"C"})


def test_outbox_machine_golden() -> None:
    golden = json.loads((GOLDEN_DIR / "outbox_delivery_machine.golden.json").read_text(encoding="utf-8"))
    actual = {
        "name": OUTBOX_DELIVERY_MACHINE.name,
        "transitions": {
            s: sorted(OUTBOX_DELIVERY_MACHINE.transitions[s]) for s in sorted(OUTBOX_DELIVERY_MACHINE.states)
        },
        "terminal_states": sorted(OUTBOX_DELIVERY_MACHINE.terminal_states),
    }
    golden.pop("_note")
    assert actual == golden


# ------------------------------------------------------------------------------------------- redaction
json_scalars = st.none() | st.booleans() | st.integers() | st.text(max_size=10)
json_keys = st.sampled_from(
    ["id", "name", "password", "Salary", "api_key", "footprint", "qty", "pin", "token_x"]
)
json_values = st.recursive(
    json_scalars,
    lambda inner: st.lists(inner, max_size=4) | st.dictionaries(json_keys, inner, max_size=4),
    max_leaves=20,
)


def _leaks(value: Any) -> bool:
    return any(True for _ in sensitive_paths(value))


@given(value=json_values)
def test_redact_removes_every_sensitive_value_and_is_idempotent(value: Any) -> None:
    out = redact(value)
    assert redact(out) == out

    # every sensitive key survives but holds only the marker
    def check(v: Any) -> None:
        if isinstance(v, dict):
            for k, sub in v.items():
                if is_sensitive_key(k):
                    assert sub == REDACTED
                else:
                    check(sub)
        elif isinstance(v, list):
            for sub in v:
                check(sub)

    check(out)


def test_sensitive_key_matching() -> None:
    for key in (
        "password",
        "new_password",
        "Salary",
        "API-Key",
        "refresh_token",
        "otp",
        "PIN",
        "payroll_ref",
    ):
        assert is_sensitive_key(key), key
    for key in ("footprint", "pinned_at", "id", "quantity", "pinion", "spine"):
        assert not is_sensitive_key(key), key
    assert list(sensitive_paths({"a": [{"b": {"password": 1}}]})) == ["a[0].b.password"]
    assert not _leaks({"aggregate_id": "x", "qty": 1})
