#!/usr/bin/env bash
# DEC-061 fidelity harness (e2e/fidelity/README.md): the E2E runner in fidelity mode (throw-away DB, real stack,
# only the @fidelity tests). Pass FIDELITY_EXTRACT=1 to re-extract the mockup specs, FIDELITY_ENFORCE=1 to gate.
set -uo pipefail
export E2E_FIDELITY=1
exec bash "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/e2e.sh"
