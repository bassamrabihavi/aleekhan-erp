"""``auth`` + ``me`` endpoints (local login only, DEC-003; browser sessions, DEC-002).

Authentication ceremonies (``login``, ``verifyMfa``, ``stepUpMfa``, ``logout``, ``changeMyPassword``,
``startMfaEnrolment``, ``confirmMfaEnrolment``) are exempt from ``Idempotency-Key`` (CONFLICTS C-27): their
bodies carry credentials and their responses rotate session state or reveal one-time secrets, which must never
be stored in an idempotency record. Protection instead: CSRF, rate limits, lockout (DEC-051), audit.
"""

from __future__ import annotations

from typing import Any

from django.middleware.csrf import get_token, rotate_token
from rest_framework.request import Request
from rest_framework.response import Response

from platform_core.engine.context import db_now
from platform_core.engine.errors import AuthenticationRequired, NotFound
from platform_core.identity import auth, mfa, sessions
from platform_core.identity.models import Session, User
from platform_core.org.models import PositionAssignment

from ..base import AleekhanAPIView
from ..concurrency import representation_etag
from ..permissions import PublicEndpoint
from ..session_auth import (
    clear_session_cookie,
    client_ip,
    enforce_csrf,
    session_token,
    set_session_cookie,
    user_agent,
)
from ..throttling import AnonIpThrottle, LoginIpThrottle, LoginUsernameThrottle, PrincipalThrottle
from . import serializers as S
from .common import NO_STORE, SessionView, body_of, paginate, stored, write


def _session_body(session_id: Any, *, current: Any, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    s = Session.objects.get(pk=session_id)
    body = S.session_info(s, current=current)
    body.update(extra or {})
    return body


class LoginView(AleekhanAPIView):
    """GET ``getLoginContext`` (sets the CSRF cookie) / POST ``login``. Public (C-26)."""

    authentication_classes: list[Any] = []  # an old cookie is ignored: login always opens a new session
    permission_classes = [PublicEndpoint]
    throttle_classes = [AnonIpThrottle, PrincipalThrottle, LoginIpThrottle, LoginUsernameThrottle]

    def get(self, request: Request) -> Response:
        get_token(request._request)  # CsrfViewMiddleware sets the csrftoken cookie on the response
        return Response({"status": "ok"}, headers=NO_STORE)

    def post(self, request: Request) -> Response:
        enforce_csrf(request)  # login CSRF
        data = body_of(request, "LoginRequest")
        result = auth.login(
            data["username"],
            data["password"],
            client_ip=client_ip(request),
            user_agent=user_agent(request),
            request_id=self._rid(request),
        )
        body = _session_body(
            result.session_id,
            current=result.session_id,
            extra={
                "password_change_required": result.must_change_password,
                "mfa_enrolment_required": result.mfa_enrolment_required,
            },
        )
        response = Response(body, headers=NO_STORE)
        set_session_cookie(response, result.token)
        rotate_token(request._request)  # REV-0123: new CSRF token once the session exists (no token fixation)
        return response

    @staticmethod
    def _rid(request: Request) -> Any:
        from ..request_id import request_id_of

        return request_id_of(request)


class VerifyMfaView(SessionView):
    """POST ``verifyMfa``: MFA_PENDING -> ACTIVE, token rotated (new cookie)."""

    idempotent = False  # authentication ceremony (C-27)

    allow_mfa_pending = True
    allow_password_change = True

    def post(self, request: Request) -> Response:
        self.caller()
        data = body_of(request, "MfaVerifyRequest")
        token = session_token(request)
        if token is None:  # pragma: no cover - the authentication needed the cookie
            raise AuthenticationRequired()
        result = auth.verify_mfa(token, data["code"], client_ip=client_ip(request), request_id=self.rid())
        response = Response(
            _session_body(
                result.session_id,
                current=result.session_id,
                extra={"password_change_required": result.must_change_password},
            ),
            headers=NO_STORE,
        )
        set_session_cookie(response, result.token)
        rotate_token(request._request)  # REV-0123: rotate the CSRF token with the session token
        return response


class StepUpMfaView(SessionView):
    """POST ``stepUpMfa`` (01.4): fresh MFA verification of an ACTIVE session (step-up window, DEC-051)."""

    idempotent = False  # authentication ceremony (C-27)

    def post(self, request: Request) -> Response:
        caller = self.caller()
        data = body_of(request, "MfaVerifyRequest")
        auth.step_up(caller, data["code"], client_ip=client_ip(request), request_id=self.rid())
        return Response(_session_body(caller.session_id, current=caller.session_id), headers=NO_STORE)


class LogoutView(SessionView):
    idempotent = False  # authentication ceremony (C-27)
    allow_mfa_pending = True
    allow_password_change = True

    def post(self, request: Request) -> Response:
        sessions.logout(self.caller(), request_id=self.rid())
        response = Response(status=204)
        clear_session_cookie(response)
        return response


class CurrentSessionView(SessionView):
    allow_password_change = True

    def get(self, request: Request) -> Response:
        caller = self.caller()
        return Response(_session_body(caller.session_id, current=caller.session_id), headers=NO_STORE)


class MySessionsView(SessionView):
    def get(self, request: Request) -> Response:
        caller = self.caller()
        qs = Session.objects.filter(user_id=caller.user_id, state__in=sessions.LIVE)
        return paginate(request, self, qs, lambda s: S.session_info(s, current=caller.session_id))


class RevokeMySessionView(SessionView):
    def post(self, request: Request, session_id: str) -> Response:
        from .common import UUID_RE

        body_of(request, "ReasonRequest")

        def run(caller: Any, rid: Any) -> Any:
            import uuid

            if not UUID_RE.fullmatch(session_id):
                raise NotFound()
            sid = uuid.UUID(session_id)
            sessions.revoke_my_session(caller, sid, request_id=rid)
            return stored(200, _session_body(sid, current=caller.session_id))

        return write(self, run)


class ChangePasswordView(SessionView):
    idempotent = False  # authentication ceremony (C-27)
    allow_password_change = True

    def post(self, request: Request) -> Response:
        data = body_of(request, "PasswordChangeRequest")
        auth.change_my_password(
            self.caller(), data["current_password"], data["new_password"], request_id=self.rid()
        )
        return Response(status=204)


class MfaEnrolmentView(SessionView):
    idempotent = False  # authentication ceremony (C-27)

    def post(self, request: Request) -> Response:
        enrolment = mfa.start_enrolment(self.caller(), request_id=self.rid())
        return Response({"method": "TOTP", "provisioning_uri": enrolment.provisioning_uri}, headers=NO_STORE)


class MfaEnrolmentConfirmView(SessionView):
    idempotent = False  # authentication ceremony (C-27)

    def post(self, request: Request) -> Response:
        data = body_of(request, "MfaVerifyRequest")
        codes = mfa.confirm_enrolment(self.caller(), data["code"], request_id=self.rid())
        return Response({"mfa_enrolled": True, "recovery_codes": codes}, headers=NO_STORE)


class MeView(SessionView):
    def get(self, request: Request) -> Response:
        caller = self.caller()
        user = User.objects.get(pk=caller.user_id)
        now = db_now()
        positions = (
            PositionAssignment.objects.filter(user_id=user.pk, valid_from__lte=now)
            .exclude(valid_to__lte=now)
            .order_by("valid_from", "id")[:20]
        )
        body = {
            "user": S.user(user),
            "roles": [S.assignment(a) for a in S.live_assignments(user.pk)],
            "positions": [S.position_assignment(p) for p in positions],
        }
        return Response(body, headers={"ETag": representation_etag(body), **NO_STORE})


class MyPermissionsView(SessionView):
    def get(self, request: Request) -> Response:
        caller = self.caller()
        body = S.effective_permissions(caller.user_id, db_now())
        etag = representation_etag({k: v for k, v in body.items() if k != "computed_at"})
        return Response(body, headers={"ETag": etag, **NO_STORE})
