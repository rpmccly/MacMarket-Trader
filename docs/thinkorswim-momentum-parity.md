# Thinkorswim Momentum parity workflow

This document is the operator-facing companion to the Momentum
Intelligence Layer charter
([`momentum-intelligence-layer.md`](momentum-intelligence-layer.md)).
It describes the **deterministic, research-only** workflow for
capturing Thinkorswim parity evidence and validating MacMarket's
Momentum Intelligence calculations against the source Simpler Trading
studies.

The parity workflow supports two complementary modes:

- `exported_study_csv` — the operator drops a Thinkorswim study CSV
  next to the bars CSV. The validator parses the last row of the
  study CSV and compares it against the manifest's `expected_latest`
  block. **Note:** Thinkorswim support has confirmed that the
  Momentum study output cannot be exported through stock ToS. This
  mode is preserved for any operator who can capture the study rows
  through a third-party tool, but it is **not the default path**.
- `visual_observation` — the operator manually reads the rendered
  Thinkorswim chart labels (total score, label, True Momentum, EMA,
  HiLo, etc.) for a specific bar and records those values in
  `manifest.json` under `observed_latest`. Optional screenshot
  references, reviewer name, and review timestamp give the audit
  trail a non-OCR, operator-attested receipt.

Visual/manual observations are **the practical replacement** for
study-row exports given the ToS limitation. They are auditable but
not row-level CSV exports, and the validator labels them as such on
every surface.

The parity workflow is the bridge between the "Phase B6 active
trial" posture and any future Phase C activation. Until a real parity
review lands here, the operator UI surfaces
**`thinkorswim_parity_workflow_status = "missing"`** and Phase C
strategies stay disabled by default. A visual_observation pass
removes the parity blocker from the activation checklist but does
**not** auto-activate Phase C, approve trades, route orders, or
change ranking math.

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

## Why real ToS parity evidence is required

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

Without real Thinkorswim parity evidence — preferably exported bars
plus visual/manual study observations because ToS does not export
study rows — we cannot measure how close our deterministic output is
to the source studies. The repo therefore ships **no fabricated parity
values** — the fixture folder is a placeholder until an operator drops
real bars CSVs and either records visual observations from the ToS
chart labels or supplies an exported study CSV.

## Files expected

`tests/fixtures/thinkorswim_momentum/`:

| File | Required? | Purpose |
|---|:---:|---|
| `manifest.json` | yes | Validated fixture list + tolerances. |
| `<SYMBOL>_<TIMEFRAME>_bars.csv` | yes | Thinkorswim OHLCV export. |
| `<SYMBOL>_<TIMEFRAME>_study.csv` | optional | Thinkorswim study CSV (only when third-party export is available; ToS does not natively export Momentum study rows). |
| `<SYMBOL>_<HTF>_bars.csv` | optional | Higher-timeframe OHLCV. |
| `<SYMBOL>_<TIMEFRAME>_<DATE>.png` | optional | Reference screenshot for a visual observation. |
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

### Visual observation (recommended default)

```json
{
  "schema_version": "thinkorswim_momentum_parity.v1",
  "generated_at": "2026-05-13T00:00:00Z",
  "source": "thinkorswim",
  "study_names": [
    "ST_TrueMomentumScoreSTUDY",
    "ST_TrueMomentumSTUDY",
    "ST_HiLoEliteSTUDY"
  ],
  "fixtures": [
    {
      "name": "XLK_1D_visual_2026Q2",
      "symbol": "XLK",
      "timeframe": "1D",
      "parity_mode": "visual_observation",
      "bars_csv": "XLK_1D_bars.csv",
      "observed_bar_date": "2026-05-10",
      "study_timezone": "America/New_York",
      "comparison_window": 1,
      "label_must_match": false,
      "reviewer": "operator",
      "reviewed_at": "2026-05-13T13:30:00Z",
      "screenshot": "XLK_1D_2026-05-10.png",
      "screenshot_notes": "Cropped to True Momentum Score panel.",
      "notes": "Real values manually transcribed from the ToS chart label.",
      "observed_latest": {
        "total_score": 80,
        "total_label": "Bull",
        "true_momentum": 67.25,
        "true_momentum_ema": 61.40
      },
      "tolerances": {
        "total_score": 2,
        "true_momentum": 1.0,
        "true_momentum_ema": 1.0
      }
    }
  ]
}
```

### Exported study CSV (when available)

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
      "parity_mode": "exported_study_csv",
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
- `fixtures[].parity_mode` — `"exported_study_csv"` or
  `"visual_observation"`. When absent, inferred from manifest shape:
  `observed_latest` → `visual_observation`, otherwise
  `exported_study_csv`. Use `visual_observation` for the practical
  default since Thinkorswim does not export the Momentum study rows.
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
- `fixtures[].observed_latest` (visual_observation) — the operator's
  manual reading of the rendered ToS chart label values. Accepts any
  subset of: `total_score`, `total_label`, `trend_score`,
  `momo_score`, `true_momentum`, `true_momentum_ema`, `hilo_thrust`,
  `hilo_output`, `pullback_signal`, `reversal_warning`,
  `no_trade_warning`. **At least one numeric score field or label
  must be present** for the observation to be considered ready;
  `total_score`, `total_label`, `true_momentum`, and
  `true_momentum_ema` are strongly recommended. Aliased as
  `expected_latest` for backward compatibility — pick one.
- `fixtures[].observed_bar_date` (visual_observation) — ISO date of
  the bar the operator read from ToS. The validator compares against
  the last bar in `bars_csv`; a mismatch is recorded as a diagnostic
  so the operator can re-slice the bars. Accepts `bar_date` as alias.
- `fixtures[].screenshot` / `screenshot_notes` (visual_observation) —
  optional reference filename + free-text notes. Surfaced in the
  report but never opened by the validator (no OCR).
- `fixtures[].reviewer` / `reviewed_at` (visual_observation) —
  optional reviewer attestation surfaced in the report.

## Capture path A — visual / manual ToS observation (default)

Use this path when ToS will not export the Momentum study CSV. The
operator reads the rendered chart labels and writes them into the
manifest as `observed_latest` values.

1. Open the ToS chart for the symbol you want to validate.
2. Set the symbol and timeframe (`Daily` for 1D, `Weekly` for 1W).
3. Add the three Simpler Trading studies so their labels render on
   the chart:
   - `ST_TrueMomentumScoreSTUDY`
   - `ST_TrueMomentumSTUDY`
   - `ST_HiLoEliteSTUDY`
4. Match the MacMarket chart date/range to the same observed bar
   (the bar you intend to record).
5. Read the rendered label values for the observed bar. Capture any
   subset of: total score, total label, True Momentum, True Momentum
   EMA, HiLo Thrust, HiLo output (HLP), Trend score, Momo score,
   and the pullback / reversal / no-trade flags. Capture at minimum
   `total_score`, `total_label`, `true_momentum`, and
   `true_momentum_ema` — the validator surfaces reason codes when
   recommended fields are missing.
6. (Optional but recommended) Take a cropped screenshot of the
   labels and save it next to the manifest as
   `<SYMBOL>_<TF>_<DATE>.png`. The validator does **not** run OCR on
   the screenshot — it only records the path for audit.
7. Export the OHLCV bars: `File → Export → CSV` (or right-click
   chart → `Export Data`). Save as `<SYMBOL>_<TF>_bars.csv` and
   slice/clip it so the last bar matches the observed bar date.
8. Edit `tests/fixtures/thinkorswim_momentum/manifest.json` (copy
   from `manifest.example.json` on the first run). Add a fixture
   entry with `parity_mode: "visual_observation"`, the bars CSV
   path, `observed_bar_date`, and the operator-transcribed
   `observed_latest` block plus your starting `tolerances`. Add
   `reviewer`, `reviewed_at`, `screenshot`, and `screenshot_notes`
   when available.
9. Run the validator (see below). The report will explicitly state
   that the parity basis is operator-read visual/manual observation,
   not exported study-row parity.

## Capture path B — exported study CSV (when available)

Thinkorswim itself does not export the Momentum study output, but a
third-party export tool may still produce one. When that path is
open to the operator, the manifest can declare
`parity_mode: "exported_study_csv"` and add a study CSV alongside the
bars CSV.

1. Follow steps 1–4 above so the chart matches the MacMarket bar.
2. Export OHLCV: `File → Export → CSV`. Save as
   `<SYMBOL>_<TF>_bars.csv`.
3. Capture the study output (third-party tool) as a CSV with at
   least the latest bar's `Date`, `totalScore`, `Trend`, `Momo`,
   `TrueMomentum`, `EMA`, `HiLoThrust`, `HLP_Output`. Headers are
   case- and underscore-insensitive — `Total Score`, `total_score`,
   `totalScore` are all accepted.
4. Save the study CSV as `<SYMBOL>_<TF>_study.csv`.
5. (Optional) Repeat steps 1 + 2 with the weekly timeframe and save
   the bars as `<SYMBOL>_<HTF>_bars.csv`.
6. Edit `manifest.json`. Add a fixture entry with
   `parity_mode: "exported_study_csv"`, the operator-supplied
   `expected_latest` values from the **last bar** in `bars_csv`, and
   your starting `tolerances`.
7. Run the validator (see below).

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

`parity-report.md` lists a top-level mode summary, a fixture table,
and per-fixture sections. The fixture table makes the mode explicit:

```
| Fixture                  | Symbol | Timeframe | Mode                | Bar        | Status |
|--------------------------|--------|-----------|---------------------|------------|--------|
| `XLK_1D_visual_2026Q2`   | `XLK`  | `1D`      | `visual_observation` | 2026-05-10 | passed |
| `XLK_1D_2026Q2`          | `XLK`  | `1D`      | `exported_study_csv` | —          | passed |
```

Per-fixture delta tables use `Observed` for `visual_observation`
mode and `Expected` for `exported_study_csv` mode:

```
| Field            | Observed | MacMarket | abs_error | Tolerance | OK?  |
|------------------|---------:|----------:|----------:|----------:|:----:|
| `total_score`    |       80 | 79.5      | 0.5       | 2.0       | ok   |
| `true_momentum`  |    67.25 | 67.10     | 0.15      | 1.0       | ok   |
```

`parity-report.json` carries the same data plus `parity_mode`,
`derived_higher_timeframe`, `parity_status`, `parity_mode_counts`,
`visual_observation_count`, `exported_study_csv_count`, the visual
review metadata (`observed_bar_date`, `screenshot`, `reviewer`,
`reviewed_at`), and `diagnostics` for each fixture.

### Interpreting `visual_passed` / `visual_failed`

The workflow status remains the narrow enum (`missing` / `partial` /
`ready` / `passed` / `failed`), but reason codes and counts
distinguish visual-mode outcomes:

- A pass with a non-zero `visual_observation_count` carries the
  `thinkorswim_visual_parity_passed` reason code; the Settings card
  surfaces it as "Visual parity passed" and notes the parity basis
  is visual / manual.
- A failure with a non-zero `visual_observation_failed_count`
  carries `thinkorswim_visual_parity_failed`.
- When the only fixtures are visual observations, the report and
  Settings card also surface `thinkorswim_exported_study_csv_unavailable`.

### Difference between visual parity and exported CSV parity

- **Visual parity** confirms the operator's eye-read of the ToS
  rendered chart label matches MacMarket's deterministic value
  within tolerance. It is auditable (reviewer + screenshot + bar
  date) but is one operator-attested data point per bar, not a
  row-level CSV comparison.
- **Exported CSV parity** compares the last row of a Thinkorswim
  study CSV (when an export path exists) against MacMarket's
  deterministic value. It is a stricter, machine-checkable parity
  basis and remains the preferred mode when available.

Visual parity is enough for operator research validation. It is
**not** enough on its own to auto-activate Phase C, and it never
approves, rejects, sizes, or routes trades.

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

1. Real Thinkorswim parity evidence landing here — preferably
   exported bars plus visual/manual study observations because ToS
   does not export the Momentum study rows — and
   `thinkorswim_parity_workflow_status == "passed"` for a
   representative sector / regime mix.
2. The accumulated Phase B8 outcome evidence corpus.
3. Explicit operator authorization.

A parity `passed` status (visual or exported) **does not**
auto-activate Phase C. It only removes the parity blocker from the
activation checklist. If a future Phase C gate wants stricter
exported-study-row parity, the activation checklist should state
that visual / manual parity is the accepted operator-reviewed
substitute today and an exported-row corpus remains an explicit
prerequisite for that future gate.

## Settings card surface

The `/settings` page renders the
`MomentumRankingStatusCard` with a "Thinkorswim parity workflow"
section. It shows:

- The resolved workflow status (`Missing` / `Partial` /
  `Report available — pending` / `Passed` / `Failed`).
- Fixture readiness (`Fixtures: <ready>/<total>`).
- Mode counts (visual observations vs exported study CSVs).
- Visual review state ("Visual parity observations available",
  "Visual parity passed").
- "Exported study CSV parity unavailable / not provided" when the
  fixture set is visual-only.
- Last report timestamp + path (when present).
- Reason codes (`thinkorswim_manifest_missing`,
  `thinkorswim_fixture_files_missing`, `thinkorswim_parity_passed`,
  `thinkorswim_parity_failed`, `thinkorswim_visual_parity_passed`,
  `thinkorswim_visual_parity_failed`,
  `thinkorswim_visual_parity_observations_available`,
  `thinkorswim_exported_study_csv_unavailable`).
- A short operator hint pointing at the CLI.

The card never carries approval / order / route / size language and
always carries the deterministic note that a parity pass — visual or
exported — does not activate any trading behavior.

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
