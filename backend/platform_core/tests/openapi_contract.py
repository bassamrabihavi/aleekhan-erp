"""Validate real HTTP responses against ``docs/api/openapi-draft.yaml`` (OpenAPI 3.1, JSON Schema 2020-12).

Checks per response: the status code is declared for the operation (or, for framework-level failures that
every endpoint can produce, the body is a valid ``Problem``), the content type is declared, the body validates
against the declared schema, and declared headers that are present validate against their schemas
(``X-Request-ID`` is required on every response by the conventions).
"""

from __future__ import annotations

import functools
import json
from pathlib import Path
from typing import Any

import yaml
from openapi_schema_validator import OAS31Validator, oas31_format_checker

OPENAPI_PATH = Path(__file__).resolve().parents[3] / "docs" / "api" / "openapi-draft.yaml"
BASE_PATH = "/api/v1"
HTTP_METHODS = ("get", "put", "post", "patch", "delete", "head", "options")
# Statuses any endpoint may produce via the framework (unknown method, payload, rate limit, crash).
GENERIC_PROBLEM_STATUSES = frozenset({400, 404, 405, 413, 429, 500})


@functools.cache
def spec() -> dict[str, Any]:
    with OPENAPI_PATH.open(encoding="utf-8") as fh:
        doc: dict[str, Any] = yaml.safe_load(fh)
    return doc


def _resolve(node: dict[str, Any]) -> dict[str, Any]:
    while "$ref" in node:
        ref = node["$ref"]
        assert ref.startswith("#/"), ref
        target: Any = spec()
        for part in ref[2:].split("/"):
            target = target[part]
        node = target
    return node


def validator(schema: dict[str, Any]) -> OAS31Validator:
    # format checking on (uuid, date-time, uri): a malformed X-Request-ID or timestamp fails the contract
    return OAS31Validator({**schema, "components": spec()["components"]}, format_checker=oas31_format_checker)


# 0.5.0-draft (01.1): path items marked ``x-aleekhan-status: planned`` are contract drafts for a later step
# and are NOT served yet. Route parity uses ``implemented_paths()``; ``test_api_contract_planned``
# pins the rules.
PLANNED_MARKER = "x-aleekhan-status"
PLANNED_VALUE = "planned"


def is_planned(path: str) -> bool:
    return bool(spec()["paths"][path].get(PLANNED_MARKER) == PLANNED_VALUE)


def implemented_paths() -> set[str]:
    return {p for p in spec()["paths"] if not is_planned(p)}


def planned_paths() -> set[str]:
    return {p for p in spec()["paths"] if is_planned(p)}


def operations(*, planned: bool | None = None) -> list[tuple[str, str, dict[str, Any]]]:
    """All operations; ``planned=False`` only implemented ones, ``planned=True`` only planned ones."""
    out = []
    for path, item in spec()["paths"].items():
        if planned is not None and is_planned(path) is not planned:
            continue
        for method in HTTP_METHODS:
            if method in item:
                out.append((path, method, item[method]))
    return out


def operation(path: str, method: str) -> dict[str, Any]:
    op: dict[str, Any] = spec()["paths"][path][method.lower()]
    return op


def validate_response(path: str, method: str, response: Any) -> None:
    """``response`` is a Django test-client response for ``BASE_PATH + path``."""
    op = operation(path, method)
    status = str(response.status_code)
    content_type = response["Content-Type"].split(";")[0].strip()
    body = json.loads(response.content.decode("utf-8")) if response.content else None

    # conventions: every response carries a UUID X-Request-ID
    validator({"type": "string", "format": "uuid"}).validate(response.get("X-Request-ID"))
    assert response.get("X-Request-ID"), "X-Request-ID missing"

    declared = op["responses"].get(status)
    if declared is None:
        assert response.status_code in GENERIC_PROBLEM_STATUSES, f"{method} {path}: undeclared {status}"
        assert content_type == "application/problem+json", content_type
        validator({"$ref": "#/components/schemas/Problem"}).validate(body)
        return
    declared = _resolve(declared)
    content = declared.get("content", {})
    assert content_type in content, f"{method} {path} {status}: {content_type} not in {list(content)}"
    validator(content[content_type]["schema"]).validate(body)
    for name, header in declared.get("headers", {}).items():
        value = response.get(name)
        if value is None:
            continue
        schema = dict(_resolve(header)["schema"])
        if schema.get("type") == "integer":
            assert value.isdigit(), (name, value)
            validator(schema).validate(int(value))
        else:
            validator(schema).validate(value)
    if content_type == "application/problem+json":
        assert body is not None
        assert body["request_id"] == response["X-Request-ID"] or response.get("Idempotent-Replayed")
