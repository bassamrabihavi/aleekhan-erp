"""PHASE_01 / 01.4 HTTP tests: login / MFA / step-up / logout / sessions / password change / me, CSRF, login
rate limits, X-Request-ID propagation, one-time credential never stored for replay. Synthetic users only."""

from __future__ import annotations

import base64
import time
import uuid
from urllib.parse import parse_qs, urlparse

import pytest
from django.test import Client, override_settings

from platform_core.identity import totp
from platform_core.models import AuditEvent, IdempotencyRecord, OutboxEvent

from . import openapi_contract as oc
from .engine_fixtures import INTERNAL_IP, PASSWORD, SYN_PW_NEW, SYN_PW_WRONG, give_role, person
from .engine_fixtures import network as set_network
from .phase01_api import API, body, code, get, idem, post, session_client, with_roles

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.usefixtures("api_db", "clear_cache")]


@pytest.fixture(autouse=True)
def _zones(settings) -> None:
    set_network(settings)


def _login(c: Client, username: str, password: str, **headers):
    return post(c, "/auth/login", {"username": username, "password": password}, **headers)


def _enrol(c: Client) -> tuple[bytes, list[str]]:
    r = post(c, "/auth/mfa/enrolment")
    assert r.status_code == 200, r.content
    oc.validate_response("/auth/mfa/enrolment", "post", r)
    uri = body(r)["provisioning_uri"]
    secret_b32 = parse_qs(urlparse(uri).query)["secret"][0]
    secret = base64.b32decode(secret_b32 + "=" * (-len(secret_b32) % 8))
    r = post(c, "/auth/mfa/enrolment/confirm", {"code": totp.totp(secret, time.time())})
    assert r.status_code == 200, r.content
    oc.validate_response("/auth/mfa/enrolment/confirm", "post", r)
    assert body(r)["mfa_enrolled"] is True and len(body(r)["recovery_codes"]) == 10
    return secret, body(r)["recovery_codes"]


def test_login_context_sets_csrf_cookie_and_login_requires_csrf() -> None:
    u = with_roles("employee")
    c = Client(REMOTE_ADDR=INTERNAL_IP, enforce_csrf_checks=True)
    r = _login(c, u.username, PASSWORD)
    assert r.status_code == 403 and code(r) == "ACCESS_DENIED"  # login CSRF
    r = get(c, "/auth/login")
    assert r.status_code == 200 and body(r) == {"status": "ok"}
    oc.validate_response("/auth/login", "get", r)
    token = c.cookies["csrftoken"].value
    r = _login(c, u.username, PASSWORD, HTTP_X_CSRFTOKEN=token)
    assert r.status_code == 200, r.content
    oc.validate_response("/auth/login", "post", r)
    assert body(r)["state"] == "ACTIVE" and body(r)["is_current"] is True
    cookie = r.cookies["aleekhan_session"]
    assert cookie["httponly"] and cookie["samesite"] == "Lax" and cookie["path"] == "/"
    # an unsafe call of the authenticated session without the CSRF header is refused
    r = post(c, "/auth/logout")
    assert r.status_code == 403 and code(r) == "ACCESS_DENIED"
    r = post(c, "/auth/logout", HTTP_X_CSRFTOKEN=token)
    assert r.status_code == 204
    oc.validate_response("/auth/logout", "post", r)
    assert r.cookies["aleekhan_session"].value == ""
    r = get(c, "/auth/session")
    assert r.status_code == 401 and code(r) == "AUTHENTICATION_REQUIRED"


def test_wrong_password_unknown_user_same_answer() -> None:
    u = with_roles("employee")
    c = Client(REMOTE_ADDR=INTERNAL_IP)
    a = _login(c, u.username, SYN_PW_WRONG)
    b = _login(c, "syn.nobody.here", SYN_PW_WRONG)
    for r in (a, b):
        assert r.status_code == 401 and code(r) == "INVALID_CREDENTIALS"
        oc.validate_response("/auth/login", "post", r)
    assert {k: v for k, v in body(a).items() if k != "request_id"} == {
        k: v for k, v in body(b).items() if k != "request_id"
    }


def test_session_me_permissions_and_my_sessions() -> None:
    u = with_roles("employee")
    c = session_client(u)
    for path in ("/auth/session", "/me", "/me/permissions", "/auth/sessions"):
        r = get(c, path)
        assert r.status_code == 200, (path, r.content)
        oc.validate_response(path, "get", r)
    me = body(get(c, "/me"))
    assert me["user"]["user_id"] == str(u.pk) and me["roles"][0]["status"] == "ACTIVE"
    grants = body(get(c, "/me/permissions"))["grants"]
    assert {g["action"] for g in grants} >= {"platform.org.read", "platform.workflow.task.read"}
    assert "platform.identity.user.read" not in {g["action"] for g in grants}  # matrix: EMP has no user.read


def test_revoke_my_other_session_and_never_another_users() -> None:
    u = with_roles("employee")
    c1 = session_client(u)
    c2 = session_client(u)
    sid2 = body(get(c2, "/auth/session"))["session_handle"]
    r = post(c1, f"/auth/sessions/{sid2}/revoke", {"reason": "synthetic revoke"}, **idem())
    assert r.status_code == 200, r.content
    oc.validate_response("/auth/sessions/{session_id}/revoke", "post", r)
    assert body(r)["state"] == "REVOKED"
    assert get(c2, "/auth/session").status_code == 401
    other = with_roles("employee")
    oc_ = session_client(other)
    sid_other = body(get(oc_, "/auth/session"))["session_handle"]
    r = post(c1, f"/auth/sessions/{sid_other}/revoke", {"reason": "synthetic revoke"}, **idem())
    assert r.status_code == 404 and code(r) == "NOT_FOUND"
    assert get(oc_, "/auth/session").status_code == 200


def test_mfa_enrolment_login_verify_and_step_up() -> None:
    u = with_roles("owner_admin")
    c = Client(REMOTE_ADDR=INTERNAL_IP)
    r = _login(c, u.username, PASSWORD)
    assert r.status_code == 200 and body(r)["state"] == "ACTIVE" and body(r)["mfa_enrolment_required"] is True
    secret, recovery = _enrol(c)
    assert post(c, "/auth/logout").status_code == 204
    r = _login(c, u.username, PASSWORD)
    assert r.status_code == 200 and body(r)["state"] == "MFA_PENDING"
    old_cookie = c.cookies["aleekhan_session"].value
    r = get(c, "/me")
    assert r.status_code == 401 and code(r) == "MFA_REQUIRED"
    r = post(c, "/auth/mfa/verify", {"code": totp.totp(secret, time.time() + totp.STEP_SECONDS)})
    assert r.status_code == 200, r.content
    oc.validate_response("/auth/mfa/verify", "post", r)
    assert body(r)["state"] == "ACTIVE" and body(r)["mfa_verified_at"]
    assert c.cookies["aleekhan_session"].value != old_cookie  # token rotated at MFA
    assert get(c, "/me").status_code == 200
    r = post(c, "/auth/mfa/step-up", {"code": "000000"})
    assert r.status_code == 401 and code(r) == "INVALID_CREDENTIALS"
    # the next TOTP step was consumed by verify (replay guard): step up with a one-time recovery code
    r = post(c, "/auth/mfa/step-up", {"code": recovery[0]})
    assert r.status_code == 200, r.content
    oc.validate_response("/auth/mfa/step-up", "post", r)


def test_step_up_is_enforced_on_mfa_operations() -> None:
    owner = with_roles("owner_admin")
    stale = session_client(owner, mfa=False)
    new = {
        "username": f"syn.api.{uuid.uuid4().hex[:6]}",
        "display_name": "کاربر ساختگی (محیط آزمایشی — داده ساختگی)",
        "account_kind": "PERSON",
        "network_policy": "ANY_WITH_MFA_OUTSIDE",
        "reason": "synthetic create",
    }
    r = post(stale, "/admin/users", new, **idem())
    assert r.status_code == 401 and code(r) == "MFA_REQUIRED"
    oc.validate_response("/admin/users", "post", r)
    fresh = session_client(owner, mfa=True)
    r = post(fresh, "/admin/users", new, **idem())
    assert r.status_code == 201, r.content


def test_create_user_one_time_password_shown_once_and_forced_change() -> None:
    owner = with_roles("owner_admin")
    c = session_client(owner)
    rid = "6f1d2c3b-4a5e-4f60-8a7b-9c0d1e2f3a4b"
    new = {
        "username": f"syn.api.{uuid.uuid4().hex[:6]}",
        "display_name": "کاربر ساختگی (محیط آزمایشی — داده ساختگی)",
        "account_kind": "PERSON",
        "network_policy": "ANY_WITH_MFA_OUTSIDE",
        "reason": "synthetic create",
    }
    headers = idem(HTTP_X_REQUEST_ID=rid)
    r = post(c, "/admin/users", new, **headers)
    assert r.status_code == 201, r.content
    oc.validate_response("/admin/users", "post", r)
    assert r["X-Request-ID"] == rid
    created = body(r)
    secret = created["one_time_credential"]["one_time_password"]
    assert secret != "[REDACTED]" and len(secret) >= 12
    # request id propagated into audit and outbox rows of the same transaction
    assert AuditEvent.objects.filter(request_id=rid, action="platform.identity.user.create").exists()
    assert OutboxEvent.objects.filter(request_id=rid, event_type="platform.identity.user.created").exists()
    # the idempotency record never stores the secret; a replay shows [REDACTED]
    rec = IdempotencyRecord.objects.get(key=headers["HTTP_IDEMPOTENCY_KEY"])
    assert secret not in str(rec.response_body)
    r2 = post(c, "/admin/users", new, **headers)
    assert r2.status_code == 201 and r2["Idempotent-Replayed"] == "true"
    assert body(r2)["one_time_credential"]["one_time_password"] == "[REDACTED]"
    assert body(r2)["user"]["user_id"] == created["user"]["user_id"]
    r3 = post(
        c,
        "/admin/users",
        {**new, "reason": "another body"},
        HTTP_IDEMPOTENCY_KEY=headers["HTTP_IDEMPOTENCY_KEY"],
    )
    assert r3.status_code == 422 and code(r3) == "IDEMPOTENCY_KEY_REUSED"
    # first login with the one-time password: everything but the password change is refused
    nc = Client(REMOTE_ADDR=INTERNAL_IP)
    r = _login(nc, new["username"], secret)
    assert r.status_code == 200 and body(r)["password_change_required"] is True
    r = get(nc, "/me")
    assert r.status_code == 403 and code(r) == "PASSWORD_CHANGE_REQUIRED"
    r = post(nc, "/auth/password/change", {"current_password": secret, "new_password": SYN_PW_NEW})
    assert r.status_code == 204, r.content
    oc.validate_response("/auth/password/change", "post", r)
    assert get(nc, "/me").status_code == 200


def test_ceremonies_need_no_idempotency_key_but_writes_do() -> None:
    u = with_roles("employee")
    c = session_client(u)
    r = post(c, "/auth/sessions/" + str(uuid.uuid4()) + "/revoke", {"reason": "synthetic"})
    assert r.status_code == 428 and code(r) == "IDEMPOTENCY_KEY_REQUIRED"
    r = post(
        c, "/auth/sessions/" + str(uuid.uuid4()) + "/revoke", {"reason": "x"}, HTTP_IDEMPOTENCY_KEY="nope"
    )
    assert r.status_code == 400 and code(r) == "VALIDATION_FAILED"
    r = post(c, "/auth/password/change", {"current_password": SYN_PW_WRONG, "new_password": SYN_PW_NEW})
    assert r.status_code == 401 and code(r) == "INVALID_CREDENTIALS"  # no 428: ceremony (C-27)


@override_settings(
    ALEEKHAN_THROTTLE_RATES={
        "anon": "1000/min",
        "principal": "1000/min",
        "health": "1000/min",
        "login_ip": "1000/min",
        "login_user": "2/min",
    }
)
def test_login_rate_limit_per_username() -> None:
    u = person()
    for i in range(2):
        r = _login(Client(REMOTE_ADDR=f"10.20.3.{i + 1}"), u.username, SYN_PW_WRONG)
        assert r.status_code == 401
    r = _login(Client(REMOTE_ADDR="10.20.3.9"), u.username.upper(), SYN_PW_WRONG)
    assert r.status_code == 429 and code(r) == "RATE_LIMITED" and int(r["Retry-After"]) >= 1
    oc.validate_response("/auth/login", "post", r)
    r = _login(Client(REMOTE_ADDR="10.20.3.9"), "syn.other.user", SYN_PW_WRONG)
    assert r.status_code == 401  # another username has its own bucket


@override_settings(
    ALEEKHAN_THROTTLE_RATES={
        "anon": "1000/min",
        "principal": "1000/min",
        "health": "1000/min",
        "login_ip": "3/min",
        "login_user": "1000/min",
    }
)
def test_login_rate_limit_per_ip_and_get_is_not_counted() -> None:
    c = Client(REMOTE_ADDR="10.20.4.4")
    for _ in range(5):
        assert get(c, "/auth/login").status_code == 200
    for i in range(3):
        assert _login(c, f"syn.nobody.{i}", SYN_PW_WRONG).status_code == 401
    r = _login(c, "syn.nobody.x", SYN_PW_WRONG)
    assert r.status_code == 429 and code(r) == "RATE_LIMITED"


@override_settings(
    ALEEKHAN_THROTTLE_RATES={
        "anon": "1000/min",
        "principal": "2/min",
        "health": "1000/min",
        "login_ip": "1000/min",
        "login_user": "1000/min",
    }
)
def test_principal_rate_limit_applies_to_authenticated_calls() -> None:
    u = with_roles("employee")
    c = session_client(u)
    assert get(c, "/auth/session").status_code == 200
    assert get(c, "/me").status_code == 200
    r = get(c, "/me")
    assert r.status_code == 429 and code(r) == "RATE_LIMITED"


def test_request_id_echo_and_replacement() -> None:
    u = with_roles("employee")
    c = session_client(u)
    good = str(uuid.uuid4())
    assert get(c, "/me", HTTP_X_REQUEST_ID=good)["X-Request-ID"] == good
    r = get(c, "/me", HTTP_X_REQUEST_ID="not-a-uuid\r\nX: y")
    assert r["X-Request-ID"] != "not-a-uuid\r\nX: y" and uuid.UUID(r["X-Request-ID"])


def test_operator_outside_network_refused_and_vpn_is_outside() -> None:
    op = person(account_kind="OPERATOR", network_policy="INTERNAL_ONLY")
    give_role(op, "operator_terminal")
    r = _login(Client(REMOTE_ADDR="10.20.99.5"), op.username, PASSWORD)  # VPN range = outside (DEC-052)
    assert r.status_code == 403 and code(r) == "NETWORK_POLICY_DENIED"
    oc.validate_response("/auth/login", "post", r)
    r = _login(Client(REMOTE_ADDR=INTERNAL_IP), op.username, PASSWORD)
    assert r.status_code == 200


def test_api_base_path_constant() -> None:
    assert API == oc.BASE_PATH
