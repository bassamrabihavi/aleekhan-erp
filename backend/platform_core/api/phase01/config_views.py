"""``parameters`` endpoints: typed versioned parameters (page 42) and dynamic-field DRAFTS (C-33).

Parameters carry no org unit: GLOBAL-only record scope. Values: OWNER_POLICY values are proposed and published
by the owner in one step (Q-0103); TECHNICAL / BUSINESS_RULE values wait for ``publishParameterValue`` by a
config approver (BUSINESS role, MFA, proposer != publisher for BUSINESS_RULE); a BUSINESS_RULE parameter whose
decision is not APPROVED answers 409 ``RULE_NOT_APPROVED`` (engine).
"""

from __future__ import annotations

import re
import uuid
from typing import Any, Final

from rest_framework.request import Request
from rest_framework.response import Response

from platform_core.authz import policy as P
from platform_core.authz.policy import Caller, RecordScope
from platform_core.engine.context import db_now
from platform_core.engine.errors import FieldError, NotFound, ValidationFailed
from platform_core.engine.idempotency import StoredResponse
from platform_core.params import service as params
from platform_core.params.models import DynamicFieldDefinition, ParameterDefinition, ParameterValue

from . import serializers as S
from .common import (
    Phase01View,
    body_of,
    etag_response,
    if_match,
    in_scope,
    lock_checked,
    paginate,
    stored,
    write,
)

READ: Final = "platform.config.parameter.read"
DEFINE: Final = "platform.config.parameter.define"
PROPOSE: Final = "platform.config.parameter.propose"
PUBLISH: Final = "platform.config.parameter.publish"
FIELD_READ: Final = "platform.config.field.read"
FIELD_DEFINE: Final = "platform.config.field.define"
KEY_RE: Final = re.compile(r"[a-z][a-z0-9_]{2,63}")
NO_UNIT: Final = RecordScope()


def _q(caller: Caller, action: str) -> Any:
    return P.scope_q(caller, action, unit_field=None, owner_fields=())


def _definition_or_404(caller: Caller, action: str, key: str) -> ParameterDefinition:
    if not KEY_RE.fullmatch(key):
        raise NotFound()
    d = ParameterDefinition.objects.filter(key=key).first()
    if d is None:
        raise NotFound()
    in_scope(caller, action, NO_UNIT)
    return d


class ParametersView(Phase01View):
    required_action = READ
    write_action = DEFINE

    def get(self, request: Request) -> Response:
        now = db_now()
        qs = ParameterDefinition.objects.filter(_q(self.caller(), READ))
        return paginate(request, self, qs, lambda d: S.parameter(d, now), ordering="key")

    def post(self, request: Request) -> Response:
        data = body_of(request, "ParameterCreateRequest")

        def run(caller: Caller, rid: uuid.UUID) -> StoredResponse:
            in_scope(caller, DEFINE, NO_UNIT)
            d = params.define_parameter(
                caller,
                key=data["parameter_key"],
                label_fa=data["label_fa"],
                datatype=data["datatype"],
                owner_module=data["owner_module"],
                classification=data["classification"],
                decision_id=data.get("decision_id") or "",
                reason=data["reason"],
                request_id=rid,
            )
            return stored(201, S.parameter(d, db_now()), etag_version=d.row_version)

        return write(self, run)


class ParameterView(Phase01View):
    required_action = READ

    def get(self, request: Request, parameter_key: str) -> Response:
        d = _definition_or_404(self.caller(), READ, parameter_key)
        return etag_response(S.parameter(d, db_now()), d.row_version)


def _value_text(datatype: str, value: dict[str, Any]) -> str:
    if value.get("datatype") != datatype:
        raise ValidationFailed(errors=[FieldError("value.datatype", "DATATYPE_MISMATCH")])
    raw = value.get("value")
    if datatype == "BOOLEAN":
        if not isinstance(raw, bool):
            raise ValidationFailed(errors=[FieldError("value.value", "INVALID_TYPE")])
        return "true" if raw else "false"
    if not isinstance(raw, str) or not raw:
        raise ValidationFailed(errors=[FieldError("value.value", "INVALID_TYPE")])
    return raw


class ParameterValuesView(Phase01View):
    required_action = READ
    write_action = PROPOSE

    def get(self, request: Request, parameter_key: str) -> Response:
        d = _definition_or_404(self.caller(), READ, parameter_key)
        qs = ParameterValue.objects.select_related("definition").filter(definition=d)
        return paginate(request, self, qs, S.parameter_value, ordering="-proposed_at")

    def post(self, request: Request, parameter_key: str) -> Response:
        data = body_of(request, "ParameterValueProposal")

        def run(caller: Caller, rid: uuid.UUID) -> StoredResponse:
            d = _definition_or_404(caller, PROPOSE, parameter_key)
            pv = params.propose(
                caller,
                key=d.key,
                value=_value_text(d.datatype, data["value"]),
                reason=data["reason"],
                effective_from=data["effective_from"],
                request_id=rid,
            )
            pv = ParameterValue.objects.select_related("definition").get(pk=pv.pk)
            return stored(201, S.parameter_value(pv), etag_version=pv.row_version)

        return write(self, run)


class PublishValueView(Phase01View):
    required_action = PUBLISH

    def post(self, request: Request, parameter_key: str, value_revision_id: uuid.UUID) -> Response:
        expected = if_match(self)
        body_of(request, "OptionalNoteRequest")

        def run(caller: Caller, rid: uuid.UUID) -> StoredResponse:
            def scope(pv: ParameterValue) -> None:
                if pv.definition_id != parameter_key:
                    raise NotFound()  # a value of another parameter
                in_scope(caller, PUBLISH, NO_UNIT)

            lock_checked(ParameterValue, value_revision_id, scope=scope, expected=expected)
            pv = params.publish(caller, value_revision_id, request_id=rid)
            pv = ParameterValue.objects.select_related("definition").get(pk=pv.pk)
            return stored(200, S.parameter_value(pv), etag_version=pv.row_version)

        return write(self, run)


# ------------------------------------------------------------------------------------- dynamic fields
def _field_or_404(caller: Caller, action: str, key: str) -> DynamicFieldDefinition:
    if not KEY_RE.fullmatch(key):
        raise NotFound()
    f = DynamicFieldDefinition.objects.filter(field_key=key).first()
    if f is None:
        raise NotFound()
    in_scope(caller, action, NO_UNIT)
    return f


class DynamicFieldsView(Phase01View):
    required_action = FIELD_READ
    write_action = FIELD_DEFINE

    def get(self, request: Request) -> Response:
        qs = DynamicFieldDefinition.objects.filter(_q(self.caller(), FIELD_READ))
        return paginate(request, self, qs, S.dynamic_field, ordering="field_key")

    def post(self, request: Request) -> Response:
        data = body_of(request, "DynamicFieldCreateRequest")

        def run(caller: Caller, rid: uuid.UUID) -> StoredResponse:
            in_scope(caller, FIELD_DEFINE, NO_UNIT)
            f = params.create_dynamic_field(
                caller,
                field_key=data["field_key"],
                entity_scope=data["entity_scope"],
                label_fa=data["label_fa"],
                datatype=data["datatype"],
                security_class=data["security_class"],
                help_fa=data.get("help_fa") or "",
                request_id=rid,
            )
            return stored(201, S.dynamic_field(f), etag_version=f.row_version)

        return write(self, run)


class DynamicFieldView(Phase01View):
    required_action = FIELD_READ
    write_action = FIELD_DEFINE

    def get(self, request: Request, field_key: str) -> Response:
        f = _field_or_404(self.caller(), FIELD_READ, field_key)
        return etag_response(S.dynamic_field(f), f.row_version)

    def patch(self, request: Request, field_key: str) -> Response:
        expected = if_match(self)
        data = body_of(request, "DynamicFieldUpdateRequest")

        def run(caller: Caller, rid: uuid.UUID) -> StoredResponse:
            f = _field_or_404(caller, FIELD_DEFINE, field_key)
            f = params.update_dynamic_field(
                caller,
                f.field_key,
                expected_version=expected,
                label_fa=data.get("label_fa"),
                help_fa=("" if data.get("help_fa") is None else data["help_fa"])
                if "help_fa" in data
                else None,
                request_id=rid,
            )
            return stored(200, S.dynamic_field(f), etag_version=f.row_version)

        return write(self, run)
