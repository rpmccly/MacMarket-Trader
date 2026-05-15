# Thinkorswim Momentum parity workflow

This document is the operator-facing companion to the Momentum
Intelligence Layer charter
([`momentum-intelligence-layer.md`](momentum-intelligence-layer.md)).
It describes the **deterministic, research-only** workflow for
capturing Thinkorswim parity evidence and validating MacMarket's
Momentum Intelligence calculations against the source Simpler Trading
studies.

The parity workflow supports three complementary modes:

- `visual_attestation` (**recommended default**) — the operator manually
  reads BOTH the Thinkorswim rendered chart values and the MacMarket
  rendered chart values for the same bar from screenshots, records
  both observation sets in `manifest.json` under `tos_observed_latest`
  and `macmarket_observed_latest`, and the validator compares ToS vs
  MacMarket directly. **No bars CSV is required** — Thinkorswim
  cannot export Momentum study rows AND cannot export usable bars for
  this workflow, so this mode is what makes parity evidence possible
  at all. Status values: `visual_attested` / `visual_failed` /
  `visual_partial`.
- `visual_observation` — the operator reads the Thinkorswim rendered
  chart labels for a specific bar (no ToS bars export needed), drops
  a bars CSV alongside so MacMarket can compute its own side, and the
  validator compares ToS readings against MacMarket's computed
  payload. Requires `bars_csv`.
- `exported_study_csv` — the operator drops a Thinkorswim study CSV
  next to the bars CSV. The validator parses the last row of the
  study CSV and compares it against the manifest's `expected_latest`
  block. **Note:** Thinkorswim support has confirmed that the
  Momentum study output cannot be exported through stock ToS. This
  mode is preserved for any operator who can capture the study rows
  through a third-party tool, but it is **not the default path**.

Visual attestation is **the practical replacement** for both
study-row exports and bars-derived parity given the ToS limitations.
It is auditable (reviewer + ToS screenshot + MacMarket screenshot +
observed_bar_date) but is not row-level CSV exports, and the
validator labels it as such on every surface.

## Visual attestation mode — no-bars manual ToS vs MacMarket parity

The recommended workflow today is **visual attestation**:

1. Open the Thinkorswim chart for the symbol you want to attest,
   set the timeframe and history range, and confirm the active bar.
2. Open the MacMarket Momentum chart for the same symbol, same
   timeframe, and the same observed bar.
3. Save screenshots of both rendered charts using this naming
   convention so the audit trail is self-documenting:
   - `visual/<SYMBOL>_<TIMEFRAME>_ToS_<YYYY>_<M>_<D>.png` for the
     Thinkorswim screenshot.
   - `visual/<SYMBOL>_<TIMEFRAME>_MM_<YYYY>_<M>_<D>.png` for the
     MacMarket screenshot.
   Example: `visual/SPY_1D_ToS_2026_5_13.png` and
   `visual/SPY_1D_MM_2026_5_13.png`.
4. Read the rendered chart values off each screenshot — Total Score,
   Total Label, True Momentum, True Momentum EMA, and any HiLo /
   trend / momo fields you care about. Capture at least
   `total_score`, `total_label`, `true_momentum`,
   `true_momentum_ema`, plus one HiLo field on the MacMarket side.
5. Record the readings in `manifest.json` under
   `tos_observed_latest` and `macmarket_observed_latest`, with a
   `parity_mode` of `"visual_attestation"`, `observed_bar_date`,
   `reviewer`, `reviewed_at`, and screenshot paths.
6. Run the validator (see "Validator commands" below).

### Exact example manifest

```json
{
  "schema_version": "thinkorswim_momentum_parity.v1",
  "source": "thinkorswim",
  "fixtures": [
    {
      "name": "SPY_1D_visual_attestation_2026_05_13",
      "symbol": "SPY",
      "timeframe": "1D",
      "parity_mode": "visual_attestation",
      "observed_bar_date": "2026-05-13",
      "reviewer": "operator",
      "reviewed_at": "2026-05-14T13:30:00Z",
      "tos_screenshot": "visual/SPY_1D_ToS_2026_5_13.png",
      "macmarket_screenshot": "visual/SPY_1D_MM_2026_5_13.png",
      "tos_observed_latest": {
        "total_score": 100,
        "total_label": "Max Bull",
        "true_momentum": 72.5563,
        "true_momentum_ema": 59.2084,
        "tos_hilo_elite_scalar": 98.1805
      },
      "macmarket_observed_latest": {
        "total_score": 100,
        "total_label": "Max Bull",
        "true_momentum": 73.51,
        "true_momentum_ema": 60.04,
        "hilo_slowd": 79.15,
        "hilo_slowd_x": 65.96,
        "hilo_score": 20,
        "hilo_thrust_state": "confirmed"
      },
      "tolerances": {
        "total_score": 2,
        "true_momentum": 1.5,
        "true_momentum_ema": 1.5
      }
    }
  ]
}
```

### Default visual_attestation tolerances

| Field | Default tolerance |
|---|---:|
| `total_score` | 2.0 |
| `trend_score` | 2.0 |
| `momo_score` | 2.0 |
| `true_momentum` | 1.5 |
| `true_momentum_ema` | 1.5 |
| `hilo_slowd` | 2.0 |
| `hilo_slowd_x` | 2.0 |
| `hilo_score` | 5.0 |

These are wider than the legacy CSV-derived defaults because
eye-read precision is coarser than CSV-derived precision. Operators
may override them per-fixture via the `tolerances` block.

### Interpreting visual_attested / visual_failed / visual_partial

- `visual_attested` — every field present in both observations is
  within tolerance and label rules pass.
- `visual_failed` — at least one numeric mismatch, or, when
  `label_must_match: true`, a label mismatch.
- `visual_partial` — both observation sets exist but no field is
  present in both sides (nothing comparable). Strict CLI treats
  this as non-pass.
- `skipped_missing_observation` — one or both observation maps are
  empty. The validator never claims attested status when a side is
  blank.

### ToS HiLo Elite scalar vs MacMarket HiLo fields

`tos_hilo_elite_scalar` is **ToS-only** by default. MacMarket does
not currently compute a ToS-comparable ST_HiLoElite scalar — the
MacMarket HiLo panel displays `hilo_slowd` / `hilo_slowd_x` /
`hilo_thrust_state` / `hilo_score` separately. When the operator
records `tos_hilo_elite_scalar` only on the ToS side, the validator
captures it in the report's diagnostics under
`reference_only_observations` but does not auto-compare it. If both
sides happen to populate `tos_hilo_elite_scalar`, the validator
compares them with the configured tolerance. The validator never
silently compares `tos_hilo_elite_scalar` against `hilo_slowd`.

### Price/bar context (optional, strongly recommended)

Capture an OHLC block on each side when possible:

```json
"tos_observed_price":       {"open": 84.10, "high": 84.83, "low": 83.92, "close": 84.72},
"macmarket_observed_price": {"open": 84.10, "high": 84.85, "low": 83.95, "close": 84.96}
```

Rules:

- Optional fields. Either side may omit them.
- When both sides supply `close`, the validator compares with
  tolerance `tolerances.close` (default **0.10** for ETFs/equities).
- A mismatch adds the reason code
  `visual_attestation_price_context_mismatch` and the diagnostic
  `bar_context_mismatch` to the report. By default this does **not**
  flip the result to failed — if the oscillator/composite fields
  pass, the validator prefers a warning and surfaces the price
  divergence clearly so the operator can recapture against the same
  bar.
- Set `strict_price_context: true` on the fixture to flip the result
  to `visual_failed` when the close mismatches. Use this when the
  operator's intent is to attest both numbers came from the exact
  same bar; leave it `false` (default) when the operator wants a
  warning + audit trail without failing the parity comparison.
- **If the ToS and MacMarket close differ, parity is not
  apples-to-apples.** Always check the price context before widening
  any tolerance.

### Composite score attribution (optional, helpful when total_score differs)

When MacMarket shows the composite breakdown, capture every
component on the MacMarket side:

```json
"macmarket_observed_latest": {
  "total_score": 65,
  "true_momentum_score": 15,
  "hilo_score": -5,
  "atr_bias": 5,
  "macd_bias": 5,
  "ma_bias": 25
  // ... usual fields ...
}
```

The validator reconstructs MacMarket's component sum:

```
mm_component_sum =
  true_momentum_score + hilo_score + atr_bias + macd_bias + ma_bias
```

and adds a **Composite score attribution** table to the report:

- MacMarket component sum vs reported `total_score`.
- ToS observed `total_score` vs MacMarket component sum.
- Diagnostic note when oscillator fields pass but the total_score
  differs: *"Oscillator fields passed, but total score differs.
  Review composite component weights, MA bias inclusion, or observed
  score source."*

ToS rarely exposes the full component breakdown. When ToS only
provides top-level `total_score`, the validator records it as
`tos_total_score` and does **not** assume ToS's component formula.

### Diagnostic flags + classification

Every visual_attestation result includes operator-readable
diagnostics:

| Flag | Meaning |
|---|---|
| `oscillator_aligned` | True Momentum + EMA were both compared and both within tolerance |
| `oscillator_failed` | True Momentum + EMA were compared and at least one failed |
| `composite_score_failed` | `total_score` failed |
| `price_context_mismatch` | `close` differs beyond tolerance |
| `label_mismatch` | At least one label differed |
| `reference_only_hilo_scalar_present` | ToS `tos_hilo_elite_scalar` recorded with no MM equivalent |

Both `oscillator_aligned` and `oscillator_failed` are `False` when
the oscillator fields were not on both sides at all (so the operator
does not have to read "False" as "compared but failed" vs "not
compared").

The accompanying `diagnostic_classification` bucket list combines
these into operator-friendly labels: `oscillator_aligned`,
`oscillator_mismatch`, `composite_mismatch`, `bar_context_mismatch`,
and `label_mismatch_only`.

### Surfaced into the Phase C research closeout

The Phase C research closeout
([`true-momentum-phase-c-closeout.md`](true-momentum-phase-c-closeout.md))
treats the XLP `oscillator_aligned` + `composite_mismatch` finding
as a `parity_mixed` blocker — research-only, never a reason to widen
parity tolerances. SPY / XLK / XLE remain `visual_attested`. Active
Phase C strategy generation is **not implemented**; no queue
candidates are generated; recommendation approval, paper-order
behavior, and ranking math remain unchanged.

### Surfaced into the Recommendations context (Phase C4)

The Phase C4 True Momentum Strategy Context card on the
Recommendations page consumes
`thinkorswim_parity_symbol_summaries` (newly added to the
`/user/momentum-ranking-status` payload) to surface a symbol-scoped
parity caveat. A selected XLP candidate is classified as
`composite_mismatch_review` and renders the
*"oscillator aligned but composite total score differs"* note;
unrelated symbols (SPY / XLK / XLE) stay at `research_ready` even
when global visual attestation reports `visual_failed`. The card is
research-only — it does not approve / reject / size / route trades,
does not generate queue candidates, and does not activate Phase C
strategy families. See
[`true-momentum-strategy-families.md`](true-momentum-strategy-families.md)
for the full Phase C4 contract.

### Example: XLP-style classification

XLP (2026-05-13) is the canonical "oscillator aligned, composite
mismatch" case:

- ToS reads `total_score: 35` / `Neutral`, `true_momentum: 57.1283`,
  `true_momentum_ema: 54.4013`.
- MacMarket reads `total_score: 65` / `Neutral Up`,
  `true_momentum: 58.00`, `true_momentum_ema: 54.45`.

The True Momentum oscillator + EMA fields pass within tolerance, but
the composite `total_score` and `total_label` diverge. The validator
classifies the result as `oscillator_aligned`, `composite_mismatch`
and surfaces the Composite score attribution diagnostic — the
operator's next step is to review composite weight inputs (MM
`true_momentum_score`, `hilo_score`, `atr_bias`, `macd_bias`,
`ma_bias` — pay particular attention to MA bias inclusion) or the
observed score source, **not** to widen the tolerance. **Do not
widen tolerance until price context and components are checked.**

Also check the price context: a ToS close around 84.72 versus a
MacMarket close around 84.96 is a `bar_context_mismatch` candidate
that may itself explain the score divergence. Capture
`tos_observed_price.close` + `macmarket_observed_price.close` on the
fixture and rerun before adjusting anything else.

### Strict mode

`--strict` requires every declared `visual_attestation` fixture to
pass outright:

- exit 0 when all attestation fixtures are `visual_attested`.
- non-zero when any fixture is `visual_failed` or `visual_partial`.
- non-zero when the manifest is missing or invalid.
- never makes provider, database, recommendation, or order calls.

## HiLo field discipline — SlowD vs ToS HiLo Elite

Operator visual-parity comparisons on SPY / XLK / XLP / XLE surfaced
a meaningful label mismatch: MacMarket's HiLo panel was previously
labelled "HiLo Elite", but the underlying value was the rendered
**stochastic SlowD line** from `compute_hilo_elite` (range 0..100),
not the ToS-comparable ST_HiLoElite scalar an operator reads off
Thinkorswim. Concretely:

| Symbol | ToS ST_HiLoElite (read) | MM previously labelled "HiLo Elite" |
|---|---:|---:|
| SPY | ~98.18 | ~78.91 (SlowD)                       |
| XLK | ~97.10 | ~78.26 (SlowD)                       |
| XLP | closer match | (also SlowD)                    |
| XLE | closer match | (also SlowD)                    |

To keep parity honest, MacMarket now distinguishes four HiLo surface
fields explicitly:

- **`hilo_slowd`** — rendered stochastic SlowD value (range 0..100).
  This is what MacMarket already computes and now labels honestly as
  "HiLo SlowD" on the chart panel.
- **`hilo_slowd_x`** — rendered stochastic SlowD_X value. Surfaced
  as "HiLo SlowD_X".
- **`tos_hilo_elite_scalar`** — the actual ToS ST_HiLoElite scalar
  an operator reads from Thinkorswim. **MacMarket does not currently
  compute this** so the field is always `null` and listed in
  `unavailable_fields`. The UI never renders a "HiLo Elite" badge
  unless a real value is present.
- **`hilo_thrust_state`** — categorical thrust state
  (Confirmed / Deconfirmed / Neutral). Kept separate.
- **`hilo_score`** — the composite -30 / 0 / +30 HiLo thrust
  contribution that feeds the total score. Kept separate.

Operators capturing visual parity can record `tos_hilo_elite_scalar`
in `observed_latest` so the audit trail preserves the rendered ToS
reading. The validator treats that field as **reference-only**: it
appears in the parity report's diagnostics but is never asserted
against a MacMarket equivalent (because MacMarket does not compute
one). Recording the operator's reading remains valuable evidence;
auto-comparing it would force a fabricated MacMarket number, which
the parity charter forbids.

The `hilo_slowd` and `hilo_slowd_x` fields **are** auto-compared
against MacMarket's existing SlowD / SlowD_X series, so an operator
who reads those values off the rendered chart (or a tooltip) can
score genuine SlowD parity.

### Example SPY visual_observation manifest

```json
{
  "schema_version": "thinkorswim_momentum_parity.v1",
  "source": "thinkorswim",
  "fixtures": [
    {
      "name": "SPY_1D_2026-05-14",
      "symbol": "SPY",
      "timeframe": "1D",
      "parity_mode": "visual_observation",
      "bars_csv": "SPY_1D_bars.csv",
      "observed_bar_date": "2026-05-13",
      "study_timezone": "America/New_York",
      "comparison_window": 1,
      "label_must_match": false,
      "reviewer": "operator",
      "reviewed_at": "2026-05-14T13:30:00Z",
      "screenshot": "SPY_1D_2026-05-13_tos.png",
      "macmarket_screenshot": "SPY_1D_2026-05-13_mm.png",
      "screenshot_notes": "ToS Score panel + MM Momentum workspace cropped to the same bar.",
      "notes": "Operator visual parity capture; SlowD reading from ToS tooltip.",
      "observed_latest": {
        "total_score": 100,
        "total_label": "Max Bull",
        "true_momentum": 72.5563,
        "true_momentum_ema": 59.2084,
        "hilo_slowd": 98.1805,
        "tos_hilo_elite_scalar": 98.1805
      },
      "tolerances": {
        "total_score": 2,
        "true_momentum": 1.0,
        "true_momentum_ema": 1.0,
        "hilo_slowd": 5.0
      }
    }
  ]
}
```

Note: `tos_hilo_elite_scalar` is recorded for the audit trail. The
validator will not assert it against MacMarket because MacMarket
does not currently compute a ToS-comparable scalar.

### Screenshot naming convention

To make the audit trail self-documenting, follow:

```
<SYMBOL>_<TIMEFRAME>_<YYYY-MM-DD>_tos.png      # rendered ToS chart
<SYMBOL>_<TIMEFRAME>_<YYYY-MM-DD>_mm.png       # rendered MM chart
```

Place them next to `manifest.json` and reference them as `screenshot`
(ToS) and `macmarket_screenshot` (MM) on the fixture entry. The
validator never opens the images — naming is operator discipline
only.

## Visual parity chart polish

To accelerate the manual observation step, the MM Momentum chart now
renders a ToS-comparable visual parity surface that mirrors the
rendered Thinkorswim chart label fields (Total Score, Total Label,
True Momentum, True Momentum EMA, HiLo Elite value, HiLo thrust
state, HiLo score, Pullback / Reversal / No-trade flags, and a
reserved IV% slot). Polish summary:

- A normalized `visual_parity_snapshot` ships in every
  `MomentumChartPayload`. A per-bar `visual_parity_series` lets the
  frontend look up status by hovered bar (latest-bar status is the
  fallback when no hover is active).
- Compact top-left status badge rows render above the candle pane,
  the True Momentum panel, and the HiLo panel. IV% is shown as
  "IV% —" with `unavailable=true` until a deterministic IV /
  IV-percentile source exists; the schema field is reserved so it
  can populate cleanly later.
- True Momentum and EMA segments are colored green when True
  Momentum is above its EMA (constructive) and red when below
  (weakening) so direction is visually obvious. The raw numeric
  values are preserved; only the visual segmentation is recomputed.
- Deterministic arrows mark True Momentum / EMA crosses
  (`bullish_cross`, `bearish_cross`) and HiLo thrust state changes
  (`hilo_confirmed`, `hilo_deconfirmed`, `hilo_state_transition`).
  Arrows describe context only — they are never buy/sell signals.
- A collapsible "Chart annotation glossary" component documents
  Rally context, Pullback context, Reversal warning, Neutral → Bull,
  Neutral → Bear, No-trade warning, and the new cross/transition
  markers in deterministic, non-actionable copy.
- Thinkorswim B/S labels and shaded swing zones are **deferred** in
  this pass because no deterministic MM equivalent exists. They
  will be revisited only if/when an equivalent deterministic signal
  is defined.

The polish does **not** change ranking math, queue sorting,
recommendation approval, paper-order behavior, replay behavior,
options behavior, backend scoring, or the underlying Momentum
indicator math. Visual parity remains operator-reviewed manual
observation evidence — the chart polish just makes that review
faster.

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

Without real Thinkorswim visual/manual parity evidence — the
recommended path is `parity_mode: "visual_attestation"`, which
records operator-entered ToS and MacMarket rendered chart values
from screenshots and requires no bars or study CSV — we cannot
measure how close our deterministic output is to the source studies.
The repo therefore ships **no fabricated parity values** — the
fixture folder is a placeholder until an operator drops real
screenshots and records the corresponding readings (or, when those
are available, real bars CSVs and visual observations / exported
study CSVs).

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
