# Thinkorswim Momentum parity report

- Fixture directory: `C:\Users\ryanm\OneDrive\Documents\GitHub\MacMarket-Trader\tests\fixtures\thinkorswim_momentum`
- Generated at: `2026-05-14T20:37:06.787357+00:00`
- Manifest present: `True`
- Manifest valid: `True`
- Fixtures total: 4
- Fixtures passed: 3
- Fixtures failed: 1
- Fixtures skipped: 0
- Overall status: `failed`

## Mode summary

- visual_attestation: 4 (3 passed / 1 failed / 0 partial)
- visual_observation: 0 (0 passed / 0 failed / 0 skipped)
- exported_study_csv: 0 (0 passed / 0 failed / 0 skipped)

_Visual attestation compares operator-entered ToS and MacMarket rendered chart values. It is not exported study-row parity._
_Visual observations are operator-entered from rendered Thinkorswim chart labels. They are auditable but not row-level CSV exports — Thinkorswim does not export the Momentum study output._

_This report is operator readiness context only. It does not approve, reject, size, or route trades, and a parity pass does not auto-activate Phase C strategy families._

## Fixture summary

| Fixture | Symbol | Timeframe | Mode | Bar | Status |
|---|---|---|---|---|---|
| `SPY_1D_visual_attestation_2026_05_13` | `SPY` | `1D` | `visual_attestation` | `2026-05-13` | `visual_attested` |
| `XLK_1D_visual_attestation_2026_05_13` | `XLK` | `1D` | `visual_attestation` | `2026-05-13` | `visual_attested` |
| `XLP_1D_visual_attestation_2026_05_13` | `XLP` | `1D` | `visual_attestation` | `2026-05-13` | `visual_failed` |
| `XLE_1D_visual_attestation_2026_05_13` | `XLE` | `1D` | `visual_attestation` | `2026-05-13` | `visual_attested` |

## SPY_1D_visual_attestation_2026_05_13 — `visual_attested`

- Mode: visual attestation (no bars)
- Source: operator-entered ToS and MacMarket rendered chart values
- This is manual visual attestation, not exported study-row parity and not computed bars parity.
- Symbol: `SPY`
- Timeframe: `1D`
- Rows compared: 1
- Higher timeframe source: `None`
- Parity status: `None`
- Observed bar date: `2026-05-13`
- Reviewer: Ry
- Reviewed at: `2026-05-14T00:00:00+00:00`
- Screenshot (ToS): `visual/SPY_1D_ToS_2026_5_13.png`
- Screenshot (MacMarket): `visual/SPY_1D_MM_2026_5_13.png`
- Screenshot notes: ToS and MM rendered chart visual/manual comparison. No ToS study-row CSV or bars CSV available.

| Field | ToS observed | MacMarket observed | abs_error | Tolerance | OK? |
|---|---:|---:|---:|---:|:---:|
| `total_score` | 100.0 | 100.0000 | 0.0000 | 2.0 | ok |
| `true_momentum` | 72.5563 | 73.5100 | 0.9537 | 1.5 | ok |
| `true_momentum_ema` | 59.2084 | 60.0400 | 0.8316 | 1.5 | ok |

### Composite score attribution

_MacMarket composite components were not provided; component-sum attribution skipped._

Total score reconciliation:

| Source | total_score |
|---|---:|
| ToS observed | 100.0 |
| MacMarket observed | 100.0 |

Diagnostic flags:
- `composite_score_failed`: False
- `label_mismatch`: False
- `oscillator_aligned`: True
- `oscillator_failed`: False
- `price_context_mismatch`: False
- `reference_only_hilo_scalar_present`: True

Classification: `oscillator_aligned`

Diagnostics:
- `mode`: visual_attestation
- `source`: operator-read Thinkorswim and MacMarket rendered chart labels
- `parity_basis`: manual visual attestation — both ToS and MacMarket values are operator-entered from rendered charts
- `observed_bar_date`: 2026-05-13
- `reference_only_observations`: {'tos_only': {'tos_hilo_elite_scalar': 98.1805}}
- `reference_only_note`: tos_hilo_elite_scalar present on the ToS side only — recorded for audit, not compared (MacMarket has no equivalent unless the MM side declares the same field)
- `skipped_fields`: ['hilo_score', 'hilo_slowd', 'hilo_slowd_x', 'hilo_thrust_state']
- `fields_compared`: ['total_label', 'total_score', 'true_momentum', 'true_momentum_ema']
- `diagnostic_flags`: {'oscillator_aligned': True, 'oscillator_failed': False, 'composite_score_failed': False, 'price_context_mismatch': False, 'label_mismatch': False, 'reference_only_hilo_scalar_present': True}
- `diagnostic_classification`: ['oscillator_aligned']
- `composite_score_attribution`: {'mm_components': 'not observed', 'tos_total_score': 100.0, 'mm_total_score': 100.0}

## XLK_1D_visual_attestation_2026_05_13 — `visual_attested`

- Mode: visual attestation (no bars)
- Source: operator-entered ToS and MacMarket rendered chart values
- This is manual visual attestation, not exported study-row parity and not computed bars parity.
- Symbol: `XLK`
- Timeframe: `1D`
- Rows compared: 1
- Higher timeframe source: `None`
- Parity status: `None`
- Observed bar date: `2026-05-13`
- Reviewer: Ry
- Reviewed at: `2026-05-14T00:00:00+00:00`
- Screenshot (ToS): `visual/XLK_1D_ToS_2026_5_13.png`
- Screenshot (MacMarket): `visual/XLK_1D_MM_2026_5_13.png`
- Screenshot notes: ToS and MM rendered chart visual/manual comparison. No ToS study-row CSV or bars CSV available.

| Field | ToS observed | MacMarket observed | abs_error | Tolerance | OK? |
|---|---:|---:|---:|---:|:---:|
| `total_score` | 100.0 | 100.0000 | 0.0000 | 2.0 | ok |
| `true_momentum` | 81.2468 | 82.1200 | 0.8732 | 1.5 | ok |
| `true_momentum_ema` | 60.3955 | 61.1300 | 0.7345 | 1.5 | ok |

### Composite score attribution

_MacMarket composite components were not provided; component-sum attribution skipped._

Total score reconciliation:

| Source | total_score |
|---|---:|
| ToS observed | 100.0 |
| MacMarket observed | 100.0 |

Diagnostic flags:
- `composite_score_failed`: False
- `label_mismatch`: False
- `oscillator_aligned`: True
- `oscillator_failed`: False
- `price_context_mismatch`: False
- `reference_only_hilo_scalar_present`: True

Classification: `oscillator_aligned`

Diagnostics:
- `mode`: visual_attestation
- `source`: operator-read Thinkorswim and MacMarket rendered chart labels
- `parity_basis`: manual visual attestation — both ToS and MacMarket values are operator-entered from rendered charts
- `observed_bar_date`: 2026-05-13
- `reference_only_observations`: {'tos_only': {'tos_hilo_elite_scalar': 97.0972}}
- `reference_only_note`: tos_hilo_elite_scalar present on the ToS side only — recorded for audit, not compared (MacMarket has no equivalent unless the MM side declares the same field)
- `skipped_fields`: ['hilo_score', 'hilo_slowd', 'hilo_slowd_x', 'hilo_thrust_state']
- `fields_compared`: ['total_label', 'total_score', 'true_momentum', 'true_momentum_ema']
- `diagnostic_flags`: {'oscillator_aligned': True, 'oscillator_failed': False, 'composite_score_failed': False, 'price_context_mismatch': False, 'label_mismatch': False, 'reference_only_hilo_scalar_present': True}
- `diagnostic_classification`: ['oscillator_aligned']
- `composite_score_attribution`: {'mm_components': 'not observed', 'tos_total_score': 100.0, 'mm_total_score': 100.0}

## XLP_1D_visual_attestation_2026_05_13 — `visual_failed`

- Mode: visual attestation (no bars)
- Source: operator-entered ToS and MacMarket rendered chart values
- This is manual visual attestation, not exported study-row parity and not computed bars parity.
- Symbol: `XLP`
- Timeframe: `1D`
- Rows compared: 1
- Higher timeframe source: `None`
- Parity status: `None`
- Observed bar date: `2026-05-13`
- Reviewer: Ry
- Reviewed at: `2026-05-14T00:00:00+00:00`
- Screenshot (ToS): `visual/XLP_1D_ToS_2026_5_13.png`
- Screenshot (MacMarket): `visual/XLP_1D_MM_2026_5_13.png`
- Screenshot notes: ToS and MM rendered chart visual/manual comparison. No ToS study-row CSV or bars CSV available.

| Field | ToS observed | MacMarket observed | abs_error | Tolerance | OK? |
|---|---:|---:|---:|---:|:---:|
| `total_score` | 35.0 | 65.0000 | 30.0000 | 2.0 | MISS |
| `true_momentum` | 57.1283 | 58.0000 | 0.8717 | 1.5 | ok |
| `true_momentum_ema` | 54.4013 | 54.4500 | 0.0487 | 1.5 | ok |

Label / flag mismatches:
- XLP_1D_visual_attestation_2026_05_13 attestation: total_label ToS 'Neutral' vs MM 'Neutral Up'

Numeric mismatches:
- XLP_1D_visual_attestation_2026_05_13 attestation: total_score ToS 35.0 vs MM 65.0000 differ by 30.0000 (tol 2.0)

### Composite score attribution

_MacMarket composite components were not provided; component-sum attribution skipped._

Total score reconciliation:

| Source | total_score |
|---|---:|
| ToS observed | 35.0 |
| MacMarket observed | 65.0 |

Diagnostic flags:
- `composite_score_failed`: True
- `label_mismatch`: True
- `oscillator_aligned`: True
- `oscillator_failed`: False
- `price_context_mismatch`: False
- `reference_only_hilo_scalar_present`: True

Classification: `oscillator_aligned`, `composite_mismatch`

Diagnostics:
- `mode`: visual_attestation
- `source`: operator-read Thinkorswim and MacMarket rendered chart labels
- `parity_basis`: manual visual attestation — both ToS and MacMarket values are operator-entered from rendered charts
- `observed_bar_date`: 2026-05-13
- `reference_only_observations`: {'tos_only': {'tos_hilo_elite_scalar': 56.383}}
- `reference_only_note`: tos_hilo_elite_scalar present on the ToS side only — recorded for audit, not compared (MacMarket has no equivalent unless the MM side declares the same field)
- `skipped_fields`: ['hilo_score', 'hilo_slowd', 'hilo_slowd_x', 'hilo_thrust_state', 'momo_score', 'trend_score']
- `fields_compared`: ['total_label', 'total_score', 'true_momentum', 'true_momentum_ema']
- `diagnostic_flags`: {'oscillator_aligned': True, 'oscillator_failed': False, 'composite_score_failed': True, 'price_context_mismatch': False, 'label_mismatch': True, 'reference_only_hilo_scalar_present': True}
- `diagnostic_classification`: ['oscillator_aligned', 'composite_mismatch']
- `composite_score_attribution`: {'mm_components': 'not observed', 'tos_total_score': 35.0, 'mm_total_score': 65.0}
- `composite_mismatch_note`: Oscillator fields passed, but total score differs. Review composite component weights, MA bias inclusion, or observed score source.

## XLE_1D_visual_attestation_2026_05_13 — `visual_attested`

- Mode: visual attestation (no bars)
- Source: operator-entered ToS and MacMarket rendered chart values
- This is manual visual attestation, not exported study-row parity and not computed bars parity.
- Symbol: `XLE`
- Timeframe: `1D`
- Rows compared: 1
- Higher timeframe source: `None`
- Parity status: `None`
- Observed bar date: `2026-05-13`
- Reviewer: Ry
- Reviewed at: `2026-05-14T00:00:00+00:00`
- Screenshot (ToS): `visual/XLE_1D_ToS_2026_5_13.png`
- Screenshot (MacMarket): `visual/XLE_1D_MM_2026_5_13.png`
- Screenshot notes: ToS and MM rendered chart visual/manual comparison. No ToS study-row CSV or bars CSV available.

| Field | ToS observed | MacMarket observed | abs_error | Tolerance | OK? |
|---|---:|---:|---:|---:|:---:|
| `total_score` | -30.0 | -30.0000 | 0.0000 | 2.0 | ok |
| `true_momentum` | 58.6418 | 59.2400 | 0.5982 | 1.5 | ok |
| `true_momentum_ema` | 66.4516 | 67.2100 | 0.7584 | 1.5 | ok |

### Composite score attribution

_MacMarket composite components were not provided; component-sum attribution skipped._

Total score reconciliation:

| Source | total_score |
|---|---:|
| ToS observed | -30.0 |
| MacMarket observed | -30.0 |

Diagnostic flags:
- `composite_score_failed`: False
- `label_mismatch`: False
- `oscillator_aligned`: True
- `oscillator_failed`: False
- `price_context_mismatch`: False
- `reference_only_hilo_scalar_present`: True

Classification: `oscillator_aligned`

Diagnostics:
- `mode`: visual_attestation
- `source`: operator-read Thinkorswim and MacMarket rendered chart labels
- `parity_basis`: manual visual attestation — both ToS and MacMarket values are operator-entered from rendered charts
- `observed_bar_date`: 2026-05-13
- `reference_only_observations`: {'tos_only': {'tos_hilo_elite_scalar': 68.1149}}
- `reference_only_note`: tos_hilo_elite_scalar present on the ToS side only — recorded for audit, not compared (MacMarket has no equivalent unless the MM side declares the same field)
- `skipped_fields`: ['hilo_score', 'hilo_slowd', 'hilo_slowd_x', 'hilo_thrust_state', 'momo_score', 'trend_score']
- `fields_compared`: ['total_label', 'total_score', 'true_momentum', 'true_momentum_ema']
- `diagnostic_flags`: {'oscillator_aligned': True, 'oscillator_failed': False, 'composite_score_failed': False, 'price_context_mismatch': False, 'label_mismatch': False, 'reference_only_hilo_scalar_present': True}
- `diagnostic_classification`: ['oscillator_aligned']
- `composite_score_attribution`: {'mm_components': 'not observed', 'tos_total_score': -30.0, 'mm_total_score': -30.0}

