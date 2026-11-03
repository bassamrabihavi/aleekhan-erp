"""Code14 field/validator: format only (14 ASCII digits as a string). Issuing codes is out of scope."""

from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, models, transaction
from django.test.utils import isolate_apps

from platform_core.code14 import (
    CODE14_DB_PATTERN,
    Code14Field,
    code14_check_constraint,
    is_code14,
    validate_code14,
)

VALID = ["00000000000000", "00000000000123", "12345678901234", "99999999999999"]
INVALID: list[object] = [
    "",
    "0000000000012",  # 13 digits
    "000000000001234",  # 15 digits
    "0000000000012a",
    " 0000000000123",
    "0000000000123 ",
    "00000000000123\n",  # Python '$' would accept this; fullmatch must not
    "0000-000000-123",
    "۰۰۰۰۰۰۰۰۰۰۰۱۲۳",  # Persian digits are not normalised (unapproved rule)
    "١٢٣٤٥٦٧٨٩٠١٢٣٤",  # Arabic-Indic digits
    123,
    12345678901234,  # int: would lose leading zeros, never accepted
    None,
]


@pytest.mark.parametrize("value", VALID)
def test_valid_codes(value: str) -> None:
    assert is_code14(value)
    validate_code14(value)


@pytest.mark.parametrize("value", INVALID)
def test_invalid_codes(value: object) -> None:
    assert not is_code14(value)
    with pytest.raises(ValidationError) as exc:
        validate_code14(value)
    assert exc.value.code == "invalid_code14"


def test_field_is_varchar14_with_validator() -> None:
    f = Code14Field()
    assert f.max_length == 14
    assert validate_code14 in f.validators
    # max_length cannot be overridden
    assert Code14Field(max_length=20).max_length == 14
    _name, path, _args, kwargs = f.deconstruct()
    assert path == "platform_core.code14.Code14Field"
    assert "max_length" not in kwargs
    assert f.clean("00000000000123", None) == "00000000000123"
    with pytest.raises(ValidationError):
        f.clean(123, None)
    with pytest.raises(ValidationError):
        f.clean("123", None)


def test_db_pattern_matches_python_contract() -> None:
    assert CODE14_DB_PATTERN == "^[0-9]{14}$"
    c = code14_check_constraint("product_code", "ck_x_product_code_fmt")
    assert c.name == "ck_x_product_code_fmt"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("00000000000123", True),
        ("0000000000123", False),
        ("00000000000123\n", False),
        ("۰۰۰۰۰۰۰۰۰۰۰۱۲۳", False),
    ],
)
def test_postgres_regex_semantics(value: str, expected: bool) -> None:
    with connection.cursor() as cur:
        cur.execute("SELECT %s ~ %s", [value, CODE14_DB_PATTERN])
        assert cur.fetchone() == (expected,)


@pytest.mark.django_db
@isolate_apps("platform_core")
def test_check_constraint_on_a_temporary_table() -> None:
    """Create a throw-away table (rolled back with the test transaction) using Code14Field + CHECK."""

    class TmpCoded(models.Model):
        code = Code14Field()

        class Meta:
            app_label = "platform_core"
            db_table = "tmp_code14_probe"
            constraints = [code14_check_constraint("code", "ck_tmp_code14_probe_code_fmt")]

        def __str__(self) -> str:
            return str(self.code)

    with connection.schema_editor() as editor:
        editor.create_model(TmpCoded)
    with connection.cursor() as cur:
        cur.execute(
            "SELECT data_type, character_maximum_length FROM information_schema.columns "
            "WHERE table_name = 'tmp_code14_probe' AND column_name = 'code'"
        )
        assert cur.fetchone() == ("character varying", 14)
    TmpCoded._default_manager.create(code="00000000000001")
    assert TmpCoded._default_manager.get().code == "00000000000001"  # leading zeros preserved
    for bad in ["0000000000001", "0000000000000a"]:
        with pytest.raises(IntegrityError) as exc, transaction.atomic():
            TmpCoded._default_manager.create(code=bad)
        assert "ck_tmp_code14_probe_code_fmt" in str(exc.value)
