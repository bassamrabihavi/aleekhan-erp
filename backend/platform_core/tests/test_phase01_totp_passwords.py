"""TOTP (RFC 6238 golden vectors, replay guard, skew) and the DEC-051 password policy (unit + property)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from platform_core.engine.errors import PasswordPolicyViolation
from platform_core.identity import totp
from platform_core.identity.passwords import (
    PasswordPolicy,
    policy_failures,
    validate_new_password,
    write_credential,
)

from .engine_fixtures import SYN_PW_ZERO, person

GOLDEN = json.loads(
    (Path(__file__).parent / "golden" / "totp_rfc6238.golden.json").read_text(encoding="utf-8")
)
POLICY = PasswordPolicy(
    min_length=8, require_upper=True, require_digit=True, require_symbol=True, reuse_depth=5
)


@pytest.mark.parametrize("vector", GOLDEN["vectors"], ids=lambda v: str(v["time"]))
@pytest.mark.parametrize("digest", ["sha1", "sha256", "sha512"])
def test_rfc6238_vectors(vector: dict[str, Any], digest: str) -> None:
    seed = GOLDEN["seeds"][digest].encode("ascii")
    assert totp.time_step(int(vector["time"])) == vector["step"]
    assert totp.totp(seed, int(vector["time"]), digits=8, digest=digest) == vector[digest]


def test_match_step_skew_and_replay_guard() -> None:
    secret = totp.new_secret()
    t = 1_800_000_000.0
    code = totp.totp(secret, t)
    step = totp.time_step(t)
    assert totp.match_step(secret, code, t, last_used_step=None) == step
    assert totp.match_step(secret, code, t + 30, last_used_step=None) == step  # one step of skew
    assert totp.match_step(secret, code, t + 90, last_used_step=None) is None  # too old
    assert totp.match_step(secret, code, t, last_used_step=step) is None  # replay
    assert totp.match_step(secret, "12345", t, last_used_step=None) is None
    assert totp.match_step(secret, "abcdef", t, last_used_step=None) is None


def test_provisioning_uri_has_no_plain_secret_bytes() -> None:
    uri = totp.provisioning_uri(b"\x00" * 20, account="syn.user")
    assert uri.startswith("otpauth://totp/Aleekhan%3Asyn.user?")
    assert "digits=6" in uri and "period=30" in uri and "algorithm=SHA1" in uri


# ------------------------------------------------------------------------------------------ passwords
@pytest.mark.parametrize(
    ("password", "codes"),
    [
        ("Short1!", ["MIN_LENGTH"]),
        ("alllower1!", ["UPPERCASE_REQUIRED"]),
        ("NoDigits!!", ["DIGIT_REQUIRED"]),
        ("NoSymbol12", ["SYMBOL_REQUIRED"]),
        ("Valid-Pass-1", []),
        ("Pass-۱۲۳-Word", []),  # Persian digits count as digits
    ],
)
def test_policy_failures(password: str, codes: list[str]) -> None:
    assert policy_failures(password, POLICY) == codes


@given(
    core=st.text(alphabet=st.characters(min_codepoint=97, max_codepoint=122), min_size=5, max_size=30),
    upper=st.sampled_from("ABCXYZ"),
    digit=st.sampled_from("0123456789"),
    symbol=st.sampled_from("!@#-_.*"),
)
def test_compliant_passwords_always_pass(core: str, upper: str, digit: str, symbol: str) -> None:
    assert policy_failures(core + upper + digit + symbol, POLICY) == []


@given(pw=st.text(min_size=0, max_size=7))
def test_short_passwords_always_fail(pw: str) -> None:
    assert "MIN_LENGTH" in policy_failures(pw, POLICY)


@pytest.mark.django_db
def test_last_five_passwords_are_refused_and_the_sixth_is_allowed() -> None:
    """Q-0105: the last 5 passwords (current one included) are refused."""
    from platform_core.engine.context import db_now

    u = person(password=SYN_PW_ZERO)
    for i in range(1, 6):
        write_credential(u, f"Syn-Pass-{i}!", now=db_now(), one_time=False, set_by_id=u.pk)
    # current = 5; history newest first = 4, 3, 2, 1, 0
    for i in (5, 4, 3, 2, 1):
        with pytest.raises(PasswordPolicyViolation) as exc:
            validate_new_password(u, f"Syn-Pass-{i}!")
        assert [e.code for e in exc.value.errors] == ["RECENTLY_USED"]
    validate_new_password(u, "Syn-Pass-0!")  # sixth most recent: allowed again


@pytest.mark.django_db
def test_policy_violation_never_echoes_the_password() -> None:
    with pytest.raises(PasswordPolicyViolation) as exc:
        validate_new_password(None, "weakpw")
    body = json.dumps(exc.value.to_problem(__import__("uuid").uuid4()))
    assert "weakpw" not in body
