"""PHASE_01 / 01.8 (REV-0132): direct unit tests of the per-request permission memo
``platform_core.authz.policy.request_cache``.

The memo exists only inside the ``with request_cache():`` block of ONE read request. These tests pin the four
safety properties the 01.7 review asked for:

(a) nothing is cached outside the block (every call reads the DB again);
(b) the memo is gone after the block - also after an exception inside it;
(c) two users inside one block each get their own grants (the key contains the user id);
(d) a grant revoked between two requests is seen by the second request.

Synthetic users and roles only (engine_fixtures).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from platform_core.authz import policy as P
from platform_core.identity.models import RoleAssignment

from .engine_fixtures import caller, give_role, person

ACTION = "platform.ops.job.read"  # matrix: owner_admin, it_ops (TECHNICAL, not a business approval)


def _queries(fn: Callable[[], Any]) -> int:
    with CaptureQueriesContext(connection) as ctx:
        fn()
    return len(ctx.captured_queries)


def _revoke(user_id: uuid.UUID) -> None:
    RoleAssignment.objects.filter(user_id=user_id).update(
        status="REVOKED", revoked_at=datetime.now(UTC), revoke_reason="لغو ساختگی (آزمون)"
    )


@pytest.mark.django_db
def test_a_nothing_is_cached_outside_the_block() -> None:
    u = person()
    give_role(u, "it_ops")
    assert P._REQUEST_CACHE.get() is None
    assert P.effective_grants(u.pk, ACTION)
    assert P._REQUEST_CACHE.get() is None  # a call outside the block creates no memo
    # every call outside the block reads the DB again ...
    assert _queries(lambda: P.effective_grants(u.pk, ACTION)) > 0
    assert _queries(lambda: P.effective_grants(u.pk, ACTION)) > 0
    # ... so a revocation is visible at once
    _revoke(u.pk)
    assert P.effective_grants(u.pk, ACTION) == []
    assert not P.can(caller(u), ACTION)


@pytest.mark.django_db
def test_inside_the_block_the_grants_are_read_once() -> None:
    u = person()
    give_role(u, "it_ops")
    with P.request_cache():
        assert P._REQUEST_CACHE.get() == {}
        assert _queries(lambda: P.effective_grants(u.pk, ACTION)) > 0
        assert _queries(lambda: P.effective_grants(u.pk, ACTION)) == 0  # memo hit
        # the memo hands out copies: a caller mutating its list cannot poison the next check
        P.effective_grants(u.pk, ACTION).clear()
        assert P.effective_grants(u.pk, ACTION)


@pytest.mark.django_db
def test_b_the_memo_is_gone_after_the_block() -> None:
    u = person()
    give_role(u, "it_ops")
    with P.request_cache():
        P.effective_grants(u.pk, ACTION)
        assert P._REQUEST_CACHE.get()
    assert P._REQUEST_CACHE.get() is None
    assert _queries(lambda: P.effective_grants(u.pk, ACTION)) > 0


@pytest.mark.django_db
def test_b_the_memo_is_gone_after_an_exception_in_the_block() -> None:
    u = person()
    give_role(u, "it_ops")

    class Boom(Exception):
        pass

    with pytest.raises(Boom), P.request_cache():
        P.effective_grants(u.pk, ACTION)
        assert P._REQUEST_CACHE.get()
        raise Boom()
    assert P._REQUEST_CACHE.get() is None
    _revoke(u.pk)
    assert P.effective_grants(u.pk, ACTION) == []  # no stale grant survives the failed request


@pytest.mark.django_db
def test_b_nested_blocks_restore_the_outer_memo() -> None:
    with P.request_cache():
        outer = P._REQUEST_CACHE.get()
        with P.request_cache():
            assert P._REQUEST_CACHE.get() is not outer
        assert P._REQUEST_CACHE.get() is outer
    assert P._REQUEST_CACHE.get() is None


@pytest.mark.django_db
def test_c_two_users_in_one_block_get_their_own_grants() -> None:
    holder = person()
    give_role(holder, "it_ops")
    other = person()  # no role at all
    owner = person()
    give_role(owner, "owner_admin")
    with P.request_cache():
        g_holder = P.effective_grants(holder.pk, ACTION)
        g_other = P.effective_grants(other.pk, ACTION)
        g_owner = P.effective_grants(owner.pk, ACTION)
        assert [g.role_code for g in g_holder] == ["it_ops"]
        assert g_other == []
        assert [g.role_code for g in g_owner] == ["owner_admin"]
        # the order of the calls does not leak one user's memo into another's decision
        assert P.can(caller(holder), ACTION)
        assert not P.can(caller(other), ACTION)
        assert P.can(caller(owner), ACTION)
        assert P.effective_grants(other.pk, ACTION) == []
        assert {g.assignment_id for g in g_holder}.isdisjoint({g.assignment_id for g in g_owner})


@pytest.mark.django_db
def test_d_a_grant_revoked_between_two_requests_is_seen_by_the_second() -> None:
    u = person()
    give_role(u, "it_ops")
    with P.request_cache():  # request 1
        assert P.can(caller(u), ACTION)
    _revoke(u.pk)
    with P.request_cache():  # request 2
        assert P.effective_grants(u.pk, ACTION) == []
        assert not P.can(caller(u), ACTION)


@pytest.mark.django_db
def test_d_a_grant_given_between_two_requests_is_seen_by_the_second() -> None:
    u = person()
    with P.request_cache():
        assert not P.can(caller(u), ACTION)
    give_role(u, "it_ops")
    with P.request_cache():
        assert P.can(caller(u), ACTION)
