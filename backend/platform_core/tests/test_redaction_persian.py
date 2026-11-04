"""REV-0602 (00.7): Persian sensitive keys are detected (normalised) for audit redaction, outbox rejection and
staging refusal. Values are SYNTHETIC markers and must never be echoed.
"""

from __future__ import annotations

import uuid

import pytest

from platform_core.engine.context import Actor, RequestContext
from platform_core.engine.errors import EngineContractError, ValidationFailed
from platform_core.engine.redaction import REDACTED, is_sensitive_key, normalize_key, redact
from platform_core.engine.uow import unit_of_work
from platform_core.integration import imports as im
from platform_core.integration.models import BatchStatus, StagingRow
from platform_core.models import AuditEvent

from . import factories

MARKER = "<synthetic-not-a-secret>"
ZWNJ = "‌"
AR_YEH = "ي"
AR_KAF = "ك"

SENSITIVE_FA = [
    "حقوق",
    "حقوق پایه",
    "فیش حقوقی",
    "فیش" + ZWNJ + "حقوقی",
    "دستمزد",
    "دست مزد",
    "مزد",
    "رمز",
    "رمز عبور",
    "رمز" + ZWNJ + "عبور",
    "رمز_عبور",
    "رمز ورود",
    "گذرواژه",
    "گذر" + ZWNJ + "واژه",
    "کلمه عبور",
    "کلمه" + ZWNJ + "عبور",
    "پسورد",
    "توکن",
    "کلید خصوصی",
    "شماره کارت",
    "شماره" + ZWNJ + "کارت",
    "کارت بانکی",
    "شبا",
    "شماره شبا",
    "کد ملی",
    "کد" + ZWNJ + "ملی",
    "شماره ملی",
    "حساب بانکی",
    # Arabic yeh / kaf variants (as typed on Arabic keyboards or exported by some tools)
    "کد مل" + AR_YEH,
    AR_KAF + "د ملی",
    AR_KAF + "لمه عبور",
    "حقوق" + AR_YEH,
    # tatweel, bidi mark, surrounding spaces
    "حقـوق",
    "‏" + "رمز عبور" + " ",
    "  دستمزد  ",
    # English variants
    "IBAN",
    "national_id",
    "Card-Number",
]

# Common factory words that contain a sensitive fragment but are NOT sensitive (no over-blocking).
INNOCENT_FA = [
    "قرمز",  # "red" contains رمز
    "رنگ قرمز",
    "کارتن",  # "carton" contains کارت
    "کارت تولید",  # production card
    "شبانه",  # "nightly" contains شبا
    "شیفت شبانه",
    "شماره حساب",  # ledger account code (Rahkaran), not a bank account
    "کد کالا",
    "تعداد",
    "مقدار",
    "تاریخ",
    "نام مشتری",
]


@pytest.mark.parametrize("key", SENSITIVE_FA)
def test_persian_sensitive_keys_are_detected(key: str) -> None:
    assert is_sensitive_key(key), normalize_key(key)


@pytest.mark.parametrize("key", INNOCENT_FA)
def test_innocent_persian_keys_are_not_flagged(key: str) -> None:
    assert not is_sensitive_key(key), normalize_key(key)


def test_normalisation_folds_arabic_letters_and_invisibles() -> None:
    assert normalize_key(AR_KAF + "د" + ZWNJ + "مل" + AR_YEH) == normalize_key("کد ملی") == "کدملی"
    assert normalize_key("Pass_Word") == "password"


@pytest.mark.parametrize("key", SENSITIVE_FA)
def test_redact_hides_persian_sensitive_values(key: str) -> None:
    out = redact({"نام": "x", "nested": [{key: MARKER}]})
    assert out == {"نام": "x", "nested": [{key: REDACTED}]}
    assert MARKER not in repr(out)


def _ctx() -> RequestContext:
    return RequestContext(Actor.system(), request_id=uuid.uuid4())


@pytest.mark.django_db
@pytest.mark.parametrize("key", ["حقوق", "رمز" + ZWNJ + "عبور", "کد مل" + AR_YEH])
def test_audit_redacts_and_outbox_rejects_persian_keys(key: str) -> None:
    with unit_of_work(_ctx(), require_event=False) as uow:
        a = uow.audit(
            action="platform.synthetic.update", resource_type="platform.synthetic", after={key: MARKER}
        )
    assert AuditEvent.objects.get(pk=a.pk).after == {key: REDACTED}
    with pytest.raises(EngineContractError, match="sensitive") as exc, unit_of_work(_ctx()) as uow:
        uow.audit(action="platform.synthetic.update", resource_type="platform.synthetic")
        uow.emit(
            event_type="platform.synthetic.updated",
            aggregate_type="platform.synthetic",
            aggregate_id="1",
            aggregate_version=1,
            payload={"items": [{key: MARKER}]},
        )
    assert MARKER not in str(exc.value)


@pytest.mark.django_db
@pytest.mark.parametrize("key", ["حقوق", "دستمزد", "گذر" + ZWNJ + "واژه", "شماره کارت", AR_KAF + "لمه عبور"])
def test_staging_refuses_persian_sensitive_columns(key: str) -> None:
    src = factories.integration_source()
    batch = im.receive_file(
        _ctx(), source_code=src.code, content=b"SYNTHETIC fa-key test bytes", original_name="x"
    ).batch
    with pytest.raises(ValidationFailed) as exc:
        im.stage_rows(_ctx(), batch.id, [im.StagingInput(1, {"کد کالا": "00000000000001", key: MARKER})])
    err = exc.value.errors[0]
    assert (err.field, err.code) == (f"rows[0].payload.{key}", "SENSITIVE_FIELD")
    assert MARKER not in str(exc.value.to_problem(uuid.uuid4()))
    batch.refresh_from_db()
    assert batch.status == BatchStatus.RECEIVED
    assert not StagingRow.objects.filter(batch=batch).exists()
