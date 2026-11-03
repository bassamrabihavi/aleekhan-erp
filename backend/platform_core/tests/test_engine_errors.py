"""Error-code catalogue: golden snapshot, OpenAPI consistency, Problem schema, exception hierarchy."""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

import pytest
import yaml
from hypothesis import given
from hypothesis import strategies as st
from openapi_schema_validator import OAS31Validator

from platform_core.engine import errors as E

GOLDEN = Path(__file__).parent / "golden" / "error_codes.golden.json"
OPENAPI = Path(__file__).resolve().parents[3] / "docs" / "api" / "openapi-draft.yaml"
PERSIAN_LETTER = re.compile(r"[؀-ۿ]")


def _openapi() -> dict[str, Any]:
    with OPENAPI.open(encoding="utf-8") as fh:
        doc: dict[str, Any] = yaml.safe_load(fh)
    return doc


def test_error_catalogue_golden() -> None:
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))["error_codes"]
    actual = [
        {
            "code": c.value,
            "http_status": E.ERROR_CATALOGUE[c].http_status,
            "exception": E.EXCEPTION_FOR_CODE[c].__name__,
        }
        for c in E.ErrorCode
    ]
    assert actual == golden


def test_catalogue_matches_openapi_enum_and_status_mapping() -> None:
    doc = _openapi()
    enum = doc["components"]["schemas"]["ErrorCode"]["enum"]
    mapping = doc["x-aleekhan-conventions"]["error_codes"]
    assert sorted(enum) == sorted(c.value for c in E.ErrorCode)
    assert mapping == {c.value: E.ERROR_CATALOGUE[c].http_status for c in E.ErrorCode}


def test_every_code_has_spec_exception_and_persian_message() -> None:
    assert set(E.ERROR_CATALOGUE) == set(E.ErrorCode)
    assert set(E.EXCEPTION_FOR_CODE) == set(E.ErrorCode)
    for code, spec in E.ERROR_CATALOGUE.items():
        assert spec.code is code
        assert 400 <= spec.http_status <= 599
        assert spec.title.strip()
        assert PERSIAN_LETTER.search(spec.message_fa), code
        exc_cls = E.EXCEPTION_FOR_CODE[code]
        assert issubclass(exc_cls, E.ClientError if spec.http_status < 500 else E.ServerError)


def test_openapi_examples_use_catalogue_messages() -> None:
    responses = _openapi()["components"]["responses"]
    for resp in responses.values():
        example = resp.get("content", {}).get("application/problem+json", {}).get("example")
        if example:
            spec = E.ERROR_CATALOGUE[E.ErrorCode(example["code"])]
            assert example["status"] == spec.http_status
            assert example["message_fa"] == spec.message_fa


def _problem_validator() -> OAS31Validator:
    doc = _openapi()
    schema = {"$ref": "#/components/schemas/Problem", "components": doc["components"]}
    return OAS31Validator(schema)


def _instance(code: E.ErrorCode) -> E.AleekhanError:
    cls = E.EXCEPTION_FOR_CODE[code]
    if cls is E.RuleNotApproved:
        return E.RuleNotApproved("DEC-005", "synthetic")
    return cls("synthetic detail", errors=[E.FieldError("field_a", "REQUIRED", "الزامی است")])


@pytest.mark.parametrize("code", list(E.ErrorCode))
def test_to_problem_matches_openapi_problem_schema(code: E.ErrorCode) -> None:
    rid = uuid.uuid4()
    exc = _instance(code)
    body = exc.to_problem(rid)
    _problem_validator().validate(body)
    assert body["code"] == code.value
    assert body["status"] == exc.http_status
    assert body["request_id"] == str(rid)
    assert body["type"].endswith("/" + code.value)


def test_rule_not_approved_requires_valid_decision_id() -> None:
    exc = E.RuleNotApproved("DEC-008")
    assert exc.to_problem(uuid.uuid4())["decision_id"] == "DEC-008"
    for bad in ("", "DEC-8", "dec-008", "DEC-0080", "DEC-008\n"):
        with pytest.raises(ValueError):
            E.RuleNotApproved(bad)


def test_field_errors_are_capped_at_schema_max() -> None:
    exc = E.ValidationFailed(errors=[E.FieldError(f"f{i}", "X") for i in range(150)])
    assert len(exc.to_problem(uuid.uuid4())["errors"]) == E.MAX_FIELD_ERRORS


@given(
    detail=st.text(max_size=200), code=st.sampled_from([c for c in E.ErrorCode if c != "RULE_NOT_APPROVED"])
)
def test_problem_shape_property(detail: str, code: E.ErrorCode) -> None:
    body = E.EXCEPTION_FOR_CODE[code](detail).to_problem(uuid.UUID(int=1))
    required = {"type", "title", "status", "code", "request_id", "message_fa"}
    assert required <= body.keys()
    assert ("detail" in body) == bool(detail)
    assert "decision_id" not in body
    assert body["status"] == E.ERROR_CATALOGUE[code].http_status
