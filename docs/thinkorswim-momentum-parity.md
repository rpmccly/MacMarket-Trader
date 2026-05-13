# Thinkorswim Momentum parity workflow

This document is the operator-facing companion to the Momentum
Intelligence Layer charter
([`momentum-intelligence-layer.md`](momentum-intelligence-layer.md)).
It describes the **deterministic, research-only** workflow for
importing real Thinkorswim CSV exports and validating MacMarket's
Momentum Intelligence calculations against the source Simpler Trading
studies.

The parity workflow is the bridge between the "Phase B6 active
trial" posture and any future Phase C activation. Until a real parity
review lands here, the operator UI surfaces
**`thinkorswim_parity_workflow_status = "missing"`** and Phase C
strategies stay disabled by default.

## Purpose

Convert the vague "Thinkorswim parity pending" state into a
structured workflow status:

- `missing`  — no manifest, or manifest invalid.
- `partial`  — manifest present but some fixture CSVs are missing.
- `ready`    — manifest + fixtures staged; no parity report yet.
- `passed`   — last parity report says every fixture passed.
- `failed`   — last parity report flagged at least one failure.
- `pending`  — legacy fallback when none of the above apply.

A parity pass **does not** approve, reject, size, or route trades. It
**does not** create recommendations, paper orders, or modify the
database. It **does not** auto-activate Phase C strategy families.
It is an operator readiness signal only.

## Why real ToS fixtures are required

The deterministic ports under
`src/macmarket_trader/indicators/{true_momentum,hilo_elite,true_momentum_score}.py`
make several documented approximations to the Simpler Trading source
studies:

- **Higher-timeframe series** is derived from chart bars when no
  explicit HTF payload is supplied (1H → daily, 4H → three-session
  grouping, 1D → ISO week).
- **ATR trailing stop** is a deterministic EMA-based approximation
  (`atr_stop_mode = "deterministic_ema_trailing_stop_approximation"`).
- **StochasticFull smoothing** uses exponential smoothing matching
  `AverageType.EXPONENTIAL`.

Without real Thinkorswim CSVs we cannot measure how close our
deterministic output is to the source studies. The repo therefore
ships **no fabricated parity values** — the fixture folder is a
placeholder until an operator drops real exports.

## Files expected

`tests/fixtures/thinkorswim_momentum/`:

| File | Required? | Purpose |
|---|:---:|---|
| `manifest.json` | yes | Validated fixture list + tolerances. |
| `<SYMBOL>_<TIMEFRAME>_bars.csv` | yes | Thinkorswim OHLCV export. |
| `<SYMBOL>_<TIMEFRAME>_study.csv` | optional | Thinkorswim study CSV. |
| `<SYMBOL>_<HTF>_bars.csv` | optional | Higher-timeframe OHLCV. |
| `parity-report.json` | generated | Written by the validator. |
| `parity-report.md` | generated | Written by the validator. |
| `README.md` | optional | Operator-side notes. |

Recommended initial symbol set:

- one strong bullish symbol (e.g. `XLK`)
- one neutral symbol (e.g. `SPY`)
- one bearish / weak symbol (e.g. `XLE` or `XLP`)
- one warning / no-trade / reversal symbol if available (e.g. `XLV`)

Recommended timeframes: `1D` (always), `1W` when a separate weekly
ToS export is available. Without a separate weekly bars file,
MacMarket derives the higher timeframe from the daily bars — the
report flags this with the `derived_higher_timeframe` field and the
relevant caveat.

## Manifest schema

```json
{
  "schema_version": "thinkorswim_momentum_parity.v1",
  "generated_at": "2026-05-12T00:00:00Z",
  "source": "thinkorswim",
  "study_names": [
    "ST_TrueMomentumScoreSTUDY",
    "ST_TrueMomentumSTUDY",
    "ST_HiLoEliteSTUDY"
  ],
  "fixtures": [
    {
      "name": "XLK_1D_2026Q2",
      "symbol": "XLK",
      "timeframe": "1D",
      "bars_csv": "XLK_1D_bars.csv",
      "study_csv": "XLK_1D_study.csv",
      "higher_timeframe_bars_csv": "XLK_1W_bars.csv",
      "study_timezone": "America/New_York",
      "comparison_window": 5,
      "label_must_match": false,
      "notes": "Real export captured 2026-05-10.",
      "expected_latest": {
        "total_score": 80,
        "total_label": "Bull",
        "trend_score": 75.0,
        "momo_score": 83.33,
        "true_momentum": 67.25,
        "true_momentum_ema": 61.40,
        "hilo_thrust": 20,
        "hilo_output": 20,
        "pullback_signal": false,
        "reversal_warning": false,
        "no_trade_warning": false
      },
      "tolerances": {
        "total_score": 2,
        "trend_score": 2.5,
        "momo_score": 2.5,
        "true_momentum": 1.0,
        "true_momentum_ema": 1.0,
        "hilo_thrust": 5,
        "hilo_output": 5
      }
    }
  ]
}
```

Field summary:

- `schema_version` — reserved for future migrations.
- `source` — must be `"thinkorswim"` for this workflow.
- `study_names` — recommended Simpler Trading study IDs. Documentation
  only; the validator does not parse them.
- `fixtures[].timeframe` — one of `1D`, `1W`, `4H`, `1H`.
- `fixtures[].study_timezone` — operator note; the validator does not
  re-timezone the values.
- `fixtures[].comparison_window` — currently the latest bar drives the
  primary comparison; future revisions of the parity engine compare
  the last *N* rows.
- `fixtures[].label_must_match` — when `true`, label / flag
  mismatches (`total_label`, `pullback_signal`, etc.) flip the result
  to `failed`. When `false` (default), mismatches are reported as
  diagnostics but do not change the status.
- `fixtures[].tolerances` — per-field absolute tolerance. Defaults
  (when a field is omitted): `total_score 2.0`, `trend_score 2.5`,
  `momo_score 2.5`, `true_momentum 1.0`, `true_momentum_ema 1.0`,
  `hilo_thrust 5.0`, `hilo_output 5.0`. Start conservative and
  tighten over time.

## Step-by-step Thinkorswim export

1. Open the chart for the symbol you want to validate.
2. Add the three Simpler Trading studies:
   - `ST_TrueMomentumScoreSTUDY` — emits `totalScore`, `Trend`,
     `Momo`, and the rounded total label.
   - `ST_TrueMomentumSTUDY` — emits `TrueMomentum` and the
     `EMA` (True Momentum EMA) plot.
   - `ST_HiLoEliteSTUDY` — emits `SlowD`, `SlowD_X`, the HiLo Thrust,
     and the HLP composite output.
3. Set the timeframe (`Daily` for 1D, `Weekly` for 1W).
4. Export OHLCV: `File → Export → CSV` (or right-click chart →
   `Export Data`). Save as `<SYMBOL>_<TF>_bars.csv` under
   `tests/fixtures/thinkorswim_momentum/`.
5. Export the study output: copy the visible study values into a CSV
   with at least the latest bar's `Date`, `totalScore`, `Trend`,
   `Momo`, `TrueMomentum`, `EMA`, `HiLoThrust`, `HLP_Output`. Headers
   are case- and underscore-insensitive — `Total Score`,
   `total_score`, `totalScore` are all accepted.
6. Save the study CSV as `<SYMBOL>_<TF>_study.csv`.
7. (Optional) Repeat steps 3 + 4 with the weekly timeframe and save
   the bars as `<SYMBOL>_<HTF>_bars.csv`.
8. Edit `tests/fixtures/thinkorswim_momentum/manifest.json` (copy
   from `manifest.example.json` on the first run). Add a fixture
   entry with the operator-supplied `expected_latest` values from
   the **last bar** in `bars_csv` plus your starting `tolerances`.
9. Run the validator (see below).

## Validator commands

```powershell
# Read-only: prints status, exits 0 (or non-zero in strict mode).
python scripts/validate_thinkorswim_momentum_parity.py \
    --fixture-dir tests/fixtures/thinkorswim_momentum

# Writes parity-report.json + parity-report.md next to the manifest.
python scripts/validate_thinkorswim_momentum_parity.py \
    --fixture-dir tests/fixtures/thinkorswim_momentum --write-report

# Strict mode: exits non-zero on missing manifest, invalid manifest,
# missing fixture files, or any parity comparison failure.
python scripts/validate_thinkorswim_momentum_parity.py \
    --fixture-dir tests/fixtures/thinkorswim_momentum --strict

# JSON output (machine-readable):
python scripts/validate_thinkorswim_momentum_parity.py \
    --fixture-dir tests/fixtures/thinkorswim_momentum --write-report --json
```

Exit codes (strict mode):

| Code | Meaning |
|---:|---|
| 0  | `passed` or `ready` |
| 10 | manifest missing |
| 11 | fixture files missing (`partial`) |
| 12 | parity comparison `failed` |
| 13 | manifest invalid |

Non-strict mode always exits 0 — useful for the deploy pipeline as a
diagnostic banner without breaking on a still-pending fixture set.

The optional env var `MACMARKET_REQUIRE_THINKORSWIM_PARITY=true` is
the seam for future CI integration: when set, the test in
`tests/test_thinkorswim_momentum_parity_workflow.py` confirms the CLI
fails loudly under `--strict`.

## How to interpret the report

`parity-report.md` lists each fixture, its status (`passed` /
`failed` / `skipped_*`), and a per-field delta table:

```
| Field            | Expected | Actual  | abs_error | Tolerance | OK?  |
|------------------|---------:|--------:|----------:|----------:|:----:|
| `total_score`    |       80 | 79.5    | 0.5       | 2.0       | ok   |
| `trend_score`    |     75.0 | 74.1    | 0.9       | 2.5       | ok   |
| `true_momentum`  |    67.25 | 67.10   | 0.15      | 1.0       | ok   |
```

`parity-report.json` carries the same data plus
`derived_higher_timeframe`, `parity_status`, and `diagnostics` for
each fixture.

Caveats surfaced by the report:

- **HTF derived from daily bars.** When a fixture omits
  `higher_timeframe_bars_csv` and the timeframe is `1W`, the report
  notes that the higher-timeframe series was derived from daily bars
  rather than from a separate weekly Thinkorswim export.
- **Rounded label thresholds.** `total_label` is the rounded total
  score; small numeric differences can flip the label without
  flipping the numeric tolerance. Use `label_must_match: false`
  unless an exact label match is required for that fixture.
- **Column casing / aliases.** Headers are normalized via
  `normalize_thinkorswim_columns`; mismatches surface a clear
  diagnostic, never an obscure `KeyError`.
- **Study timezone alignment.** The validator does not re-timezone
  CSV rows; align the `Date` column at export time.

## How this gates Phase C

Phase C0 / C1 / C2 / C2.1 / C2.2 / C3 are all research-only today
(see `docs/momentum-phase-closeout.md`). Active Phase C strategy
generation is reserved and waits on:

1. Real Thinkorswim parity fixtures landing here and
   `thinkorswim_parity_workflow_status == "passed"` for a
   representative sector / regime mix.
2. The accumulated Phase B8 outcome evidence corpus.
3. Explicit operator authorization.

A parity `passed` status **does not** auto-activate Phase C. It only
removes the parity blocker from the activation checklist.

## Settings card surface

The `/settings` page renders the
`MomentumRankingStatusCard` with a new "Thinkorswim parity workflow"
section. It shows:

- The resolved workflow status (`Missing` / `Partial` /
  `Report available — pending` / `Passed` / `Failed`).
- Fixture readiness (`Fixtures: <ready>/<total>`).
- Last report timestamp + path (when present).
- Reason codes (`thinkorswim_manifest_missing`,
  `thinkorswim_fixture_files_missing`, `thinkorswim_parity_passed`,
  `thinkorswim_parity_failed`).
- A short operator hint pointing at the CLI.

The card never carries approval / order / route / size language and
always carries the deterministic note that a parity pass does not
activate any trading behavior.

## Acceptance check

After dropping fixtures and running the validator:

```powershell
python -m pytest tests/test_thinkorswim_momentum_parity_workflow.py \
    tests/test_momentum_thinkorswim_parity_scaffold.py \
    tests/test_momentum_parity_helper.py -q --tb=short
```

When real fixtures land, also run the strict validator from CI:

```powershell
python scripts/validate_thinkorswim_momentum_parity.py \
    --fixture-dir tests/fixtures/thinkorswim_momentum --strict --write-report
```

If strict exits non-zero, the parity-report.md will name the failing
fixture and the per-field deltas that exceeded tolerance. Investigate
deterministically — do **not** silently widen tolerances to make the
status flip to `passed`.
