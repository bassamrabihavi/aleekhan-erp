"""Per-source freshness (PHASE_00 / 00.6): fresh / stale / never.

``last_success_at`` is set when a batch of the source is VALIDATED with at least one structurally valid row
(``imports.validate_batch``). A duplicate import of the same file does not refresh it (it brings no new
evidence, WH-01). Classification against the source's ``staleness_threshold``:

* ``never``  no successful import yet;
* ``fresh``  ``now - last_success_at <= threshold`` (a timestamp in the future counts as age 0);
* ``stale``  older than the threshold.

The thresholds seeded in migration 0006 are TECHNICAL DEFAULTS (``threshold_basis = TECHNICAL_DEFAULT``): the
real validity of a Rahkaran snapshot and the re-import policy are owner decision DEC-016 (OPEN). The API
returns the basis and the governing decision so the UI can say so; stale data is never presented as real time
(SOURCE_MAPPING section 7).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from .models import IntegrationSource


class Freshness(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    NEVER = "never"


def classify(last_success_at: datetime | None, threshold: timedelta, now: datetime) -> Freshness:
    if threshold <= timedelta(0):
        raise ValueError("threshold must be positive")
    if last_success_at is None:
        return Freshness.NEVER
    return Freshness.STALE if now - last_success_at > threshold else Freshness.FRESH


def age_seconds(last_success_at: datetime | None, now: datetime) -> int | None:
    if last_success_at is None:
        return None
    return max(0, int((now - last_success_at).total_seconds()))


@dataclass(frozen=True)
class SourceFreshness:
    source: IntegrationSource
    freshness: Freshness
    age_seconds: int | None


def freshness_of(source: IntegrationSource, now: datetime) -> SourceFreshness:
    return SourceFreshness(
        source=source,
        freshness=classify(source.last_success_at, source.staleness_threshold, now),
        age_seconds=age_seconds(source.last_success_at, now),
    )
