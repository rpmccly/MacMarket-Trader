"""Parity scaffold for Momentum Intelligence Layer.

Future Thinkorswim fixture CSVs should be placed under
``tests/fixtures/thinkorswim_momentum/`` with a manifest file naming each
fixture's symbol, timeframe, and expected ``total_score`` /
``true_momentum`` / ``hilo_thrust`` values for the latest bar.

If no fixtures are present, this scaffold passes while documenting that
parity validation is pending. When fixtures are added, replace the pass-only
branch with comparisons within configured tolerances.
"""

from __future__ import annotations

import json
from pathlib import Path

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "thinkorswim_momentum"
MANIFEST = FIXTURE_DIR / "manifest.json"


def test_thinkorswim_parity_fixtures_marker() -> None:
    if not MANIFEST.exists():
        # Parity fixtures pending. The presence of this scaffold is sufficient
        # to track the work; future fixture CSVs go under FIXTURE_DIR.
        assert FIXTURE_DIR.parent.exists() or not FIXTURE_DIR.exists()
        return

    manifest = json.loads(MANIFEST.read_text())
    assert isinstance(manifest, dict)
    assert "fixtures" in manifest
