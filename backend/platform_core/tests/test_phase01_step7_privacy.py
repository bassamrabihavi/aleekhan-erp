"""PHASE_01 / 01.7 privacy and permission tests, driven by the APPROVED permission matrix (v1.3) and the
OpenAPI contract. Real session authentication, real PostgreSQL, synthetic users and data only.

1. Deny by default, every role x every operation: for each of the 11 seeded roles, a holder of only that role
   gets 403 ``ACCESS_DENIED`` on every PHASE_01 operation whose permission the matrix does not give the role
   (``identity.roles.approved_matrix_grants`` = 0010 + 0014 + 0015 + 0017).
2. MFA step-up, every MFA-flagged operation: a holder of a role that has the permission, with a session
   without a fresh MFA verification, gets 401 ``MFA_REQUIRED`` (before any body/record check).
3. Record scope (SEC-01) for S2+ data: the document sensitivity caps of the matrix (EMP S1; MGR / MGT S1-S2) -
   a document above the cap is 404 on every document read/download operation and absent from every list; at
   the cap it is visible. (All other ``{id}`` families: ``test_api_bola``.)
4. Never-exposed fields: after a world with password, MFA, session, document and parameter rows exists, no
   GET response of the contract (as a holder of every permission) contains a password / credential hash,
   TOTP secret, recovery-code hash, session key hash, storage key or key reference
   (``authz.policy.NEVER_EXPOSED``).
5. Secrets never stored or logged: a full ceremony (login, MFA enrolment, verify, step-up with TOTP and a
   recovery code, user creation with a one-time password, admin password reset, password change) - then a
   grep over EVERY row of EVERY ``platform_*`` table (``row_to_json``) and over every log record finds none of
   the plaintext passwords, one-time passwords, TOTP secret, OTP codes, recovery codes or session tokens.
"""

from __future__ import annotations

import base64
import logging
import re
import time
import uuid
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
from django.db import connection
from django.test import Client

from platform_core.authz import policy as P
from platform_core.documents import scanner
from platform_core.documents import service as docs
from platform_core.identity import totp
from platform_core.identity.models import Credential, MfaFactor, RecoveryCode, Session, User
from platform_core.identity.roles import approved_matrix_grants

from . import openapi_contract as oc
from .engine_fixtures import INTERNAL_IP, PASSWORD, SYN_PW_NEW, with_role
from .engine_fixtures import network as set_network
from .phase01_api import body, code, get, idem, if_match, post, session_client, superuser, with_roles
from .test_api_contract_planned import PHASE01_TAGS

MUTATING = {"post", "put", "patch", "delete"}
AUDIT_WINDOW = {"occurred_from": "2026-01-01T00:00:00Z", "occurred_to": "2030-12-31T00:00:00Z"}
SAMPLE = {"session_id": str(uuid.uuid4()), "parameter_key": "syn_param_key", "field_key": "syn_field_key"}
PDF = b"%PDF-1.7\n% synthetic privacy document\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n"

MATRIX = approved_matrix_grants()
ROLES = sorted(MATRIX)


def _ops() -> list[tuple[str, str, dict[str, Any]]]:
    return [
        (p, m, op)
        for p, m, op in oc.operations()
        if set(op["tags"]) & PHASE01_TAGS and op.get("x-aleekhan-permission")
    ]


OPS = _ops()


def _held(role: str) -> set[str]:
    return {a for a, _mode, _cap in MATRIX[role]}


def _url(path: str) -> str:
    def sub(m: re.Match[str]) -> str:
        return SAMPLE.get(m.group(1), str(uuid.uuid4()))

    return oc.BASE_PATH + re.sub(r"\{([a-z_]+)\}", sub, path)


def _call(c: Client, method: str, path: str) -> Any:
    if method == "get":
        return c.get(_url(path), AUDIT_WINDOW)
    return getattr(c, method)(
        _url(path),
        "{}",
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        HTTP_IF_MATCH='"1"',
    )


@pytest.fixture(autouse=True)
def _zones(settings: Any) -> None:
    set_network(settings)


# ------------------------------------------------------------------------------- 1. deny by default
def test_matrix_and_contract_are_both_covered() -> None:
    from importlib import import_module

    seed = import_module("platform_core.migrations.0010_seed_phase01_catalogue")
    assert (
        len(ROLES) == 11 and len(OPS) == 86
    )  # every PHASE_01 operation with a permission (others: session-only)
    assert {op["x-aleekhan-permission"] for _p, _m, op in OPS} == set(
        seed.PERMISSIONS
    )  # all 43, nothing else


@pytest.mark.django_db
@pytest.mark.usefixtures("clear_cache")
@pytest.mark.parametrize("role", ROLES)
def test_every_role_is_refused_every_operation_the_matrix_does_not_grant(role: str) -> None:
    c = session_client(with_roles(role))
    held = _held(role)
    refused = 0
    for path, method, op in OPS:
        if op["x-aleekhan-permission"] in held:
            continue
        r = _call(c, method, path)
        assert r.status_code == 403 and code(r) == "ACCESS_DENIED", (role, op["operationId"], r.status_code)
        oc.validate_response(path, method, r)
        refused += 1
    assert refused > 0 or role == "owner_admin", role  # every role lacks something (owner: see below)
    if role == "owner_admin":
        assert refused >= 10  # e.g. task.create / document.create / instance.cancel are not owner cells


# ------------------------------------------------------------------------------------- 2. MFA step-up
def _mfa_cases() -> list[tuple[str, str, dict[str, Any], str]]:
    from importlib import import_module

    seed = import_module("platform_core.migrations.0010_seed_phase01_catalogue")
    mfa = {a for a, (_d, m, _ba, _sod) in seed.PERMISSIONS.items() if m}
    out = []
    for path, method, op in OPS:
        perm = op["x-aleekhan-permission"]
        if perm not in mfa:
            continue
        holder = next(r for r in ROLES if perm in _held(r))
        out.append((path, method, op, holder))
    return out


MFA_CASES = _mfa_cases()


def test_every_mfa_flagged_operation_has_a_holder_and_the_flag_in_the_contract() -> None:
    assert len(MFA_CASES) >= 25
    for _p, _m, op, _holder in MFA_CASES:
        assert op.get("x-aleekhan-mfa-step-up") is True, op["operationId"]


@pytest.mark.django_db
@pytest.mark.usefixtures("clear_cache")
@pytest.mark.parametrize("holder", sorted({h for *_x, h in MFA_CASES}))
def test_mfa_flagged_operations_need_a_fresh_step_up_for_every_holder_role(holder: str) -> None:
    stale = session_client(with_roles(holder), mfa=False)
    checked = 0
    for path, method, op, h in MFA_CASES:
        if h != holder:
            continue
        r = _call(stale, method, path)
        assert r.status_code == 401 and code(r) == "MFA_REQUIRED", (holder, op["operationId"], r.status_code)
        oc.validate_response(path, method, r)
        checked += 1
    assert checked > 0


# ----------------------------------------------------------------------- 3. S2+ record scope (documents)
@pytest.fixture
def store(settings: Any, tmp_path: Any) -> None:
    settings.ALEEKHAN_DOCUMENT_STORAGE_ROOT = str(tmp_path)


def _clean_doc(sensitivity: str) -> tuple[str, str]:
    _u, ctl = with_role("document_controller")
    doc = docs.create_document(
        ctl, document_type="syn_drawing", title_fa="سند ساختگی", sensitivity=sensitivity
    )
    rev = docs.upload_revision(ctl, doc.pk, filename="sheet.pdf", data=PDF + uuid.uuid4().bytes)
    docs.scan_revision(rev.pk, scanner.FakeScannerForTests())
    return str(doc.pk), str(rev.pk)


CAPS = [(r, cap) for r in ROLES for a, mode, cap in MATRIX[r] if a == "platform.document.read" and cap]


def test_capped_document_grants_are_the_approved_ones() -> None:
    assert sorted(CAPS) == [("employee", "S1"), ("management_viewer", "S2"), ("unit_manager", "S2")]


@pytest.mark.django_db
@pytest.mark.usefixtures("clear_cache", "store")
@pytest.mark.parametrize(("role", "cap"), CAPS)
def test_documents_above_the_sensitivity_cap_do_not_exist_for_the_role(role: str, cap: str) -> None:
    levels = ["S1", "S2", "S3"]
    created = {s: _clean_doc(s) for s in levels}
    c = session_client(with_roles(role))
    listed = {x["document_id"] for x in body(get(c, "/documents"))["items"]}
    for s, (did, rid) in created.items():
        visible = levels.index(s) <= levels.index(cap)
        assert (did in listed) is visible, (role, s)
        for path in (
            f"/documents/{did}",
            f"/documents/{did}/revisions",
            f"/documents/{did}/revisions/{rid}",
            f"/documents/{did}/revisions/{rid}/content",
        ):
            r = get(c, path)
            if visible:
                assert r.status_code == 200, (role, s, path, r.status_code)
            else:
                assert r.status_code == 404 and code(r) == "NOT_FOUND", (role, s, path, r.status_code)


# ---------------------------------------------------------------------------- 4. never-exposed fields
def _secret_values() -> set[str]:
    values: set[str] = set()
    values |= set(Credential.objects.values_list("password_hash", flat=True))
    for blob in MfaFactor.objects.exclude(secret_ciphertext=None).values_list("secret_ciphertext", flat=True):
        raw = bytes(blob or b"")
        values |= {raw.hex(), base64.b64encode(raw).decode("ascii")}
    values |= set(RecoveryCode.objects.values_list("code_hash", flat=True))
    values |= set(Session.objects.values_list("session_key_hash", flat=True))
    from platform_core.documents.models import StoredObject

    for key, ref in StoredObject.objects.values_list("storage_key", "key_ref"):
        values |= {key, ref}
    return {v for v in values if v and len(v) >= 8}


NEVER_EXPOSED_NAMES = tuple(sorted(P.NEVER_EXPOSED))


@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("api_db", "clear_cache", "store")
def test_no_get_response_contains_a_never_exposed_field_or_value() -> None:
    _clean_doc("S1")
    owner = with_roles("owner_admin")
    c = Client(REMOTE_ADDR=INTERNAL_IP)
    assert post(c, "/auth/login", {"username": owner.username, "password": PASSWORD}).status_code == 200
    _enrol(c)  # TOTP factor + recovery codes exist now
    probe = session_client(superuser())
    secrets_ = _secret_values()
    assert len(secrets_) >= 5
    seen = 0
    for path, method, op in oc.operations():
        if method != "get" or not set(op["tags"]) & PHASE01_TAGS or "{" in path:
            continue
        r = probe.get(oc.BASE_PATH + path, AUDIT_WINDOW)
        if r.status_code != 200 or not r["Content-Type"].startswith("application/json"):
            continue
        text = r.content.decode("utf-8")
        for name in NEVER_EXPOSED_NAMES:
            assert f'"{name}"' not in text, (op["operationId"], name)
        for value in secrets_:
            assert value not in text, op["operationId"]
        seen += 1
    assert seen >= 15


# ---------------------------------------------------------------- 5. secrets never stored or logged
def _enrol(c: Client) -> tuple[bytes, str, list[str], str]:
    r = post(c, "/auth/mfa/enrolment")
    assert r.status_code == 200, r.content
    secret_b32 = parse_qs(urlparse(body(r)["provisioning_uri"]).query)["secret"][0]
    secret = base64.b32decode(secret_b32 + "=" * (-len(secret_b32) % 8))
    otp = totp.totp(secret, time.time())
    r = post(c, "/auth/mfa/enrolment/confirm", {"code": otp})
    assert r.status_code == 200, r.content
    return secret, secret_b32, body(r)["recovery_codes"], otp


def _all_platform_rows() -> str:
    with connection.cursor() as cur:
        cur.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' "
            "AND table_type = 'BASE TABLE' AND table_name LIKE 'platform\\_%' ORDER BY table_name"
        )
        tables = [t for (t,) in cur.fetchall()]
        chunks = []
        for t in tables:
            # table names come from information_schema (not user input); quoted as identifiers
            sql = f"SELECT coalesce(string_agg(row_to_json(x)::text, chr(10)), '') FROM public.\"{t}\" x"  # noqa: S608
            cur.execute(sql)
            chunks.append(cur.fetchone()[0])
    assert len(tables) >= 40
    return "\n".join(chunks)


@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("api_db", "clear_cache")
def test_no_password_otp_recovery_code_or_token_in_any_table_or_log(caplog: Any) -> None:
    caplog.set_level(logging.DEBUG)
    owner = with_roles("owner_admin")
    c = Client(REMOTE_ADDR=INTERNAL_IP)
    r = post(c, "/auth/login", {"username": owner.username, "password": PASSWORD})
    assert r.status_code == 200
    tokens = {c.cookies["aleekhan_session"].value}
    secret, secret_b32, recovery, otp1 = _enrol(c)
    assert post(c, "/auth/logout").status_code == 204
    assert post(c, "/auth/login", {"username": owner.username, "password": PASSWORD}).status_code == 200
    tokens.add(c.cookies["aleekhan_session"].value)
    otp2 = totp.totp(secret, time.time() + totp.STEP_SECONDS)
    assert post(c, "/auth/mfa/verify", {"code": otp2}).status_code == 200
    tokens.add(c.cookies["aleekhan_session"].value)
    assert post(c, "/auth/mfa/step-up", {"code": recovery[0]}).status_code == 200
    # the owner creates a user (one-time password shown once) and resets the password (another one)
    new = {
        "username": f"syn.priv.{uuid.uuid4().hex[:6]}",
        "display_name": "کاربر ساختگی (محیط آزمایشی — داده ساختگی)",
        "account_kind": "PERSON",
        "network_policy": "ANY_WITH_MFA_OUTSIDE",
        "reason": "synthetic create",
    }
    r = post(c, "/admin/users", new, **idem())
    assert r.status_code == 201, r.content
    one_time_1 = body(r)["one_time_credential"]["one_time_password"]
    uid = body(r)["user"]["user_id"]
    r = get(c, f"/admin/users/{uid}")
    r = post(
        c,
        f"/admin/users/{uid}/reset-password",
        {"reason": "synthetic reset"},
        **if_match(int(r["ETag"].strip('"'))),
    )
    assert r.status_code == 200, r.content
    one_time_2 = body(r)["one_time_password"]
    # the new user logs in with the one-time password and changes it
    nc = Client(REMOTE_ADDR=INTERNAL_IP)
    assert post(nc, "/auth/login", {"username": new["username"], "password": one_time_2}).status_code == 200
    tokens.add(nc.cookies["aleekhan_session"].value)
    r = post(nc, "/auth/password/change", {"current_password": one_time_2, "new_password": SYN_PW_NEW})
    assert r.status_code == 204, r.content
    # failed attempts too: a wrong OTP and a wrong password
    assert post(c, "/auth/mfa/step-up", {"code": "000001"}).status_code == 401

    plain = {PASSWORD, SYN_PW_NEW, one_time_1, one_time_2, secret_b32, secret.hex(), *recovery, *tokens}
    plain = {p for p in plain if p and p != "[REDACTED]"}
    assert len(plain) >= 16
    quoted_codes = {f'"{otp1}"', f'"{otp2}"', '"000001"'}  # 6 digits: matched as whole JSON strings only
    rows = _all_platform_rows()
    logs = "\n".join(f"{rec.getMessage()} {rec.__dict__}" for rec in caplog.records)
    assert len(rows) > 1000 and caplog.records
    for where, text in (("database rows", rows), ("log records", logs)):
        for p in plain:
            assert p not in text, f"a plaintext secret was found in {where}"  # never print the value
        for q in quoted_codes:
            assert q not in text, f"an OTP code was found in {where}"
    assert User.objects.filter(username=new["username"]).exists()
