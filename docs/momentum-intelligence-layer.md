# Momentum Intelligence Layer

This document describes the **deterministic** Momentum Intelligence Layer that
landed across Phases A1, A2, and A3: backend indicator math, chart payload,
API route, frontend display surfaces, and operator hardening.

The layer **does not** change recommendation ranking, ranking influence,
strategy families, recommendation approval, sizing, paper-order behavior, or
options/replay logic.

## Purpose

The Momentum Intelligence Layer ports three Simpler Trading reference studies
into typed Python so MacMarket can produce deterministic momentum/thrust
context alongside HACO. The intent matches the repository's design principle:
**LLMs explain and extract. Rules and models decide.** The layer is purely
deterministic indicator math feeding a protected chart payload that the
operator console renders as context only.

## Source studies

The following files are stored at the repository root as **reference
artifacts**. They are licensed/proprietary studies and are not redistributed
verbatim in Python comments. Production use of the ported math assumes the
operator has the rights to use and port the source studies.

- `ST_TrueMomentumScoreSTUDY.ts`
- `ST_TrueMomentumSTUDY.ts`
- `ST_HiLoEliteSTUDY.ts`

The Python ports under `src/macmarket_trader/indicators/` re-implement the
deterministic math/state behavior — they do not paste large verbatim study
text.

---

## Phase A1 — backend deterministic math

| Area | Location |
|---|---|
| Indicator helpers (`sma`, `atr`, `crosses_above/below`, `stochastic_full`, `safe_div`, …) | `src/macmarket_trader/indicators/common.py` |
| True Momentum oscillator | `src/macmarket_trader/indicators/true_momentum.py` |
| HiLo Elite stochastic + thrust + cycle | `src/macmarket_trader/indicators/hilo_elite.py` |
| Composite True Momentum Score | `src/macmarket_trader/indicators/true_momentum_score.py` |
| Pydantic chart payload schemas | `src/macmarket_trader/domain/schemas.py` |
| Momentum chart service | `src/macmarket_trader/charts/momentum_service.py` |
| `POST /charts/momentum` API route | `src/macmarket_trader/api/routes/charts.py` |
| Backend tests + parity scaffold | `tests/test_indicators_*.py`, `tests/test_momentum_charts_api.py`, `tests/test_momentum_thinkorswim_parity_scaffold.py` |

`HACO` and `HACOLT` behavior is unchanged.

### Composite total-score reference

```
base_score = TrueMomentumScore + HiLoThrust + Bull_MA + Bear_MA + ATR_Value + MACD_bias
intraday_penalty = -5 if (intraday and has_200 and close < SMA200 and -95 <= base <= 100) else 0
total_score = base_score + intraday_penalty

trend_score = (Bull_MA + Bear_MA + ATR_Value) * 100 / 40 (- 5 if penalty)
momo_score  = (TrueMomentumScore + HiLoThrust + MACD_bias) * 100 / 60
```

State labels:

| Range | State | Label |
|---|---|---|
| `>= 100` | `max_bull` | "Max Bull" |
| `>= 75`  | `bull`     | "Bull" |
| `>= 45`  | `neutral_up` | "Neutral Up" |
| `<= -100` | `max_bear` | "Max Bear" |
| `<= -75`  | `bear`     | "Bear" |
| `<= -45`  | `neutral_down` | "Neutral Down" |
| otherwise | `neutral` | "Neutral" |

### Approximation/parity caveats

- **Higher-timeframe series** is derived deterministically from chart bars
  (1H → daily, 4H → three-session grouping, 1D → ISO week) when no explicit
  `higher_timeframe_bars` payload is supplied. The series exposes
  `higher_timeframe_source ∈ {provided_higher_timeframe_bars,
  derived_from_chart_bars, insufficient_data}` so the chart layer can surface
  this clearly without framing it as an error.
- **`parity_status`** defaults to `pending_thinkorswim_fixture_validation`.
  When Thinkorswim CSV fixtures land under
  `tests/fixtures/thinkorswim_momentum/`, the scaffold test
  (`tests/test_momentum_thinkorswim_parity_scaffold.py`) can switch to
  comparing latest `total_score` / `true_momentum` / `hilo_thrust` within
  configured tolerances.
- **ATR trailing stop** uses a **deterministic EMA-based trailing-stop
  approximation** (`atr_stop_mode =
  "deterministic_ema_trailing_stop_approximation"`) — Thinkorswim's
  `ATRTrailingStop` *modified* trail type is not reproduced exactly; the
  series labels this rather than hiding it.

---

## Phase A2 — frontend display integration

Phase A2 wired the backend payload into the operator console as
**deterministic display context only**.

| Surface | File |
|---|---|
| Frontend proxy route | `apps/web/app/api/charts/momentum/route.ts` |
| Momentum API client | `apps/web/lib/momentum-api.ts` |
| Pure helpers | `apps/web/lib/momentum-chart.ts` |
| Reusable summary panel | `apps/web/components/charts/momentum-summary-panel.tsx` |
| Workspace | `apps/web/components/charts/momentum-workspace.tsx` |
| Console page | `apps/web/app/(console)/charts/momentum/page.tsx` |
| Console nav link | `apps/web/components/console-shell.tsx` (Research → Momentum Intelligence) |
| Strategy Workbench integration | `apps/web/app/(console)/analysis/page.tsx` |
| Symbol Snapshot integration | `apps/web/app/(console)/analyze/page.tsx` |
| Recommendation detail integration | `apps/web/app/(console)/recommendations/page.tsx` |
| Indicator registry extension | `apps/web/lib/indicator-framework.ts` + `apps/web/components/charts/indicator-selector.tsx` |

New IDs under a typed `momentum_intelligence` category: `true_momentum`,
`true_momentum_ema`, `hilo_elite`, `hilo_slowd`, `hilo_slowd_x`,
`momentum_score`, `momentum_thrust`. All `defaultEnabled: false`. The generic
`WorkflowChart` lists them as **unsupported** so they never render without
the dedicated payload.

Failure modes:
- Momentum fetch failure must **never** block the parent flow on
  Workbench / Snapshot / Recommendation detail. The panel renders its own
  error/empty/loading states.
- HTTP 425 → `AUTH_NOT_READY` (matches `fetchHacoChart`).

---

## Phase A3 — visual QA / operator hardening

Phase A3 is **polish only** — no new ranking influence, no strategy families,
no recommendation approval changes.

### Surfaces reviewed and hardened

- `apps/web/components/charts/momentum-workspace.tsx`
- `apps/web/components/charts/momentum-summary-panel.tsx`
- `apps/web/lib/momentum-api.ts`
- `apps/web/lib/momentum-chart.ts`
- `apps/web/app/(console)/charts/momentum/page.tsx`
- `apps/web/app/(console)/analysis/page.tsx`
- `apps/web/app/(console)/analyze/page.tsx`
- `apps/web/app/(console)/recommendations/page.tsx`
- `apps/web/components/console-shell.tsx`
- `apps/web/components/charts/indicator-selector.tsx`
- `apps/web/lib/indicator-framework.ts`

### Hardening applied

- **Marker copy is context-only**: the backend now emits `Pullback context`,
  `Rally context`, `Reversal warning`, `Neutral → Bull`, `Neutral → Bear` —
  no action verbs (`buy`, `sell`, `enter`, `short`). A backend test
  (`test_momentum_chart_marker_indices_align_to_candles_and_use_context_only_text`)
  enforces this.
- **Marker types renamed** from `bullish_pullback_buy` /
  `bearish_rally_sell` to `bullish_pullback_context` / `bearish_rally_context`
  to keep the contract honest.
- **Sparse/empty payload safety**: the workspace `subscribeVisibleLogicalRangeChange`
  handler short-circuits on null ranges, guards reentry, and wraps each
  peer-chart `setVisibleLogicalRange` in try/catch so an empty or disposed
  peer can't crash sync.
- **Five-panel layout** uses semantic `<h4>` headings via a shared
  `PanelHeading` helper, each chart container has `role="img"` with an
  aria-label, and the controls row is a `role="group"` so AT users can
  identify the workspace controls cluster.
- **Symbol input** normalizes to uppercase on both `onChange` and `onBlur`,
  with `aria-label="Symbol"`.
- **Timeframe selector** is a labeled `<select aria-label="Timeframe">`
  bound to `1D / 4H / 1H` only.
- **Compact metadata block** on the workspace exposes `data_source`,
  `fallback_mode`, `session_policy`, `higher_timeframe_source`,
  `higher_timeframe`, and `parity_status` via shared helpers
  (`describeHigherTimeframeSource`, `describeParityStatus`) — derived HTF and
  parity-pending render as visible-but-not-alarming neutral badges.
- **Summary panel** uses a `<dl>`/`<dt>`/`<dd>` semantic structure for
  components with `wordBreak: break-word` so long labels wrap cleanly. Each
  component badge carries an aria-label such as `"Total Score +90"`.
- **Reversal / no-trade / pullback warnings** are wrapped in `<strong>` for
  visual prominence and addressable via `data-testid=...` for tests.
- **Neutral state** renders with `tone="neutral"` badges and never with
  `tone="good"` or `tone="bad"`. A summary-panel test pins this behavior.
- **Deterministic-context note** is the canonical phrase
  *"Momentum Intelligence is deterministic context only in Phase A. It does
  not approve, reject, size, or rank trades."* — exported as
  `MOMENTUM_DETERMINISTIC_NOTE` and rendered on every panel state (empty,
  loading, error, populated) so operators always see the context framing.
- **Fail-soft integration**: each consumer page wraps `fetchMomentumChart`
  in its own try/catch. Workbench analysis, Symbol Snapshot triage, and
  Recommendation detail all proceed without the momentum panel when the
  fetch fails.
- **Indicator selector** exposes the new `momentum_intelligence` bucket with
  a hint that explicitly frames the IDs as deterministic context only —
  never trade approval.

### Tests run

- `tests/test_momentum_charts_api.py`, `tests/test_charts_api.py` — backend smoke.
- `apps/web/lib/momentum-chart.test.ts` — score tone, formatting,
  summary, warning detection, latest-snapshot extraction, HTF / parity
  helpers, deterministic-note guard.
- `apps/web/lib/momentum-api.test.ts` — JSON POST shape, credentials/cache,
  425 → `AUTH_NOT_READY`, non-OK error.
- `apps/web/components/charts/momentum-summary-panel.test.tsx` — empty,
  loading, error, full bull mode, compact mode, reversal/pullback prominence,
  bear bad-tone variant, neutral-tone guard.
- `apps/web/lib/indicator-framework.test.ts` — registry coverage and
  default-state pin.
- `apps/web/lib/workflow-chart.test.ts` — momentum-intelligence IDs surface
  as **unsupported** on the generic workflow chart.
- `apps/web/lib/momentum-integration.test.ts` — Workbench / Snapshot /
  Recommendation static imports + console-nav link + ranking-touch guard
  ensuring no momentum types are imported into ranking/approval modules.
- `apps/web/tests/e2e/momentum-workspace-smoke.spec.ts` — Playwright smoke
  for `/charts/momentum`: workspace mounts, deterministic note visible,
  symbol input + timeframe selector + load button present, console nav
  link points back to `/charts/momentum`.

### Confirmation

- Phase B (ranking influence): **not implemented**. Composite scores still do
  not feed recommendation ranking, scoring, or quality gates. The
  `momentum-integration` guard test enforces this.
- Phase C (strategy families): **not implemented**.
- Recommendation approval, sizing, paper-order, options preview, replay, and
  HACO/HACOLT behaviors are unchanged.
- `parity_status` continues to default to
  `pending_thinkorswim_fixture_validation` until Thinkorswim fixture CSVs
  land. Derived higher-timeframe behavior remains explicitly labeled.

---

## Thinkorswim parity fixtures

Operator-supplied Thinkorswim CSV exports are the only authoritative way to
validate that MacMarket's deterministic ports of `ST_TrueMomentumScoreSTUDY`,
`ST_TrueMomentumSTUDY`, and `ST_HiLoEliteSTUDY` actually agree with the source
studies. The repo ships the **infrastructure** for this validation but not the
data itself — no fabricated parity values are committed.

### Layout

```
tests/fixtures/thinkorswim_momentum/
  README.md                    -- operator workflow + supported CSV columns
  manifest.example.json        -- template for manifest.json
  manifest.json                -- (gitignored / not committed) operator-added entries
  <SYMBOL>_<TF>_bars.csv       -- (operator-supplied) Thinkorswim OHLCV export
  <SYMBOL>_<TF>_study.csv      -- (operator-supplied) Thinkorswim study export
  <SYMBOL>_<HTF>_bars.csv      -- (optional) higher-timeframe OHLCV export

tests/helpers/momentum_parity.py   -- forgiving CSV parser + manifest loader
tests/test_momentum_thinkorswim_parity_scaffold.py   -- the parity test
tests/test_momentum_parity_helper.py                 -- helper-level unit tests
```

### Required / optional CSVs per fixture

Each entry in `manifest.json` lists:

| Field | Required | Notes |
|---|---|---|
| `name` | yes | unique label; appears in test failures |
| `symbol` | yes | normalized to upper-case |
| `timeframe` | yes | one of `1D`, `4H`, `1H` |
| `bars_csv` | yes | OHLCV CSV path relative to the fixture directory |
| `study_csv` | optional | per-bar Thinkorswim study export; cross-checked when present |
| `higher_timeframe_bars_csv` | optional | when present, the test asserts `higher_timeframe_source == "provided_higher_timeframe_bars"` |
| `expected_latest` | yes | operator-supplied values for the latest bar; only known study fields are accepted |
| `tolerances` | yes (mapping; entries optional) | per-field absolute tolerances; default `1.0` if a field is missing |

Known study fields: `total_score`, `true_momentum`, `true_momentum_ema`,
`hilo_thrust`, `hilo_output`, `trend_score`, `momo_score`. Any field that is
not in `expected_latest` is **skipped** by the comparison, so partial fixture
coverage is fine — operators only need to assert what they have actually
exported from Thinkorswim.

### Supported CSV columns

The parser is **case- and underscore-insensitive**.

Bars CSV: `Date` / `Datetime` / `Time` / `Timestamp`, `Open` (or `O`), `High`
(or `H`), `Low` (or `L`), `Close` (or `C` / `Last`), `Volume` (or `Vol` / `V`).

Study CSV: `totalScore` / `TotalScore` / `total_score`; `TrueMomentum` /
`true_momentum`; `TrueMomentumEMA` / `true_momentum_ema` / `EMA`; `HiLoThrust`
/ `hilo_thrust`; `HLP_Output` / `hilo_output` / `HLPOutput`; `Trend` /
`trend_score`; `Momo` / `momo_score`. Date/timestamp columns are accepted via
the same parser used for bars CSVs.

### How to run

```
python -m pytest tests/test_momentum_thinkorswim_parity_scaffold.py -q --tb=short
```

- With **no** `manifest.json`: the test is a no-op pass and surfaces no
  parity assertions. Helper unit tests
  (`tests/test_momentum_parity_helper.py`) still exercise the CSV parser and
  manifest validator independent of fixture availability.
- With `manifest.json` present: the test parametrizes over each fixture,
  builds the deterministic momentum payload via `MomentumChartService`,
  compares the latest payload snapshot against `expected_latest` using the
  per-field absolute `tolerances`, cross-checks the operator's study CSV
  values when present, and asserts that `higher_timeframe_source` is
  `"provided_higher_timeframe_bars"` whenever a fixture supplies an HTF
  bars CSV. Missing fixture files or unknown study fields fail clearly with
  the offending path/key.

### Phase B gating

**Phase B (ranking influence) is bounded and gated by mode** — see the
Phase B1 section below. Until Thinkorswim parity fixtures land and have
been reviewed, Phase B1 stays in the safe-by-default `shadow` mode and
flipping to `active` requires explicit operator authorization. A future
config flag (`parity_required_for_active`) will additionally block
`active` mode while parity is still pending.

## Phase B1 — bounded ranking influence (mode-aware)

Phase B1 introduces a **bounded, audited, mode-aware** Momentum
Intelligence ranking contribution. It does **not** change recommendation
approval, paper-order, or live-trading behavior. It does **not** create a
strategy family. It only attaches an explanation/contribution to the
ranking-engine output that downstream surfaces can render or apply.

### Mode

The mode is read from `Settings.momentum_ranking_mode` (env var
`MACMARKET_MOMENTUM_RANKING_MODE` or `MOMENTUM_RANKING_MODE`). Allowed
values: `off`, `shadow`, `active`. **Default: `shadow`**.

| Mode | Computes contribution? | Applies to score? | Use when |
|---|---|---|---|
| `off`    | No  | No  | Disable Phase B1 entirely (e.g., regression hunts). |
| `shadow` | Yes | No  | **Default.** Surface explanation; final scores/order unchanged. |
| `active` | Yes | Yes (within cap) | Operator has authorized momentum to influence ranking. |

The default stays `shadow` while Thinkorswim parity fixtures remain pending
so live/paper behavior never silently shifts.

### Bounded components

`MomentumRankingConfig` exposes per-component absolute caps. Defaults:

| Component | Cap | Behavior |
|---|---|---|
| `momentum_alignment_score`  | `+0..+10` | Direction-aligned bull/bear state (Max Bull → +10 long, Max Bear → +10 short). Opposed direction → 0 (never positive). |
| `trend_alignment_score`     | `+0..+8`  | Magnitude of `trend_score` when its sign agrees with the inferred direction. |
| `hilo_confirmation_bonus`   | `+0..+5`  | HiLo composite (`hilo_score` from `HLP_Output`) magnitude when it agrees with the inferred direction. |
| `reversal_warning_penalty`  | `-0..-12` | Full cap fires on an explicit reversal warning. |
| **`total_contribution`**    | `[-12, +20]` | Final clamp on the sum of components. |

`no_trade_warning` is a **warning only** — it suppresses the positive
components (and adds the `momentum_no_trade_warning` reason code) but does
**not** hard-reject the candidate. Reversal warnings emit
`momentum_reversal_warning`. Pullback signals emit
`momentum_pullback_signal`.

### Active-mode behavior

In `active` mode the bounded `total_contribution` (in score units of the
±20 cap) is converted into the ranking engine's `[0, 1]` score scale via
`ranking_score_scale = 100.0` and added to the candidate's score. The final
score is then re-clamped to `[0, 1]`. Re-ranking happens after the active
adjustment.

### Shadow-mode behavior

In `shadow` mode the contribution is computed and attached to each
`RankedCandidate.momentum_contribution`, but `applied=False` and
`total_contribution=0.0`. Scores and ordering are byte-identical to `off`
mode for the same inputs. Tests pin this invariant
(`tests/test_momentum_ranking_engine_integration.py`).

### Direction inference

The contribution function takes a `recommendation_context` with optional
`direction` / `side`. When neither is provided, the ranking engine passes a
`recent_trend` hint (5-bar net close change) and the strategy name; the
helper infers `long`/`short` only for momentum-aligned strategies
(`continuation`, `pullback`). Fade and mean-reversion strategies stay
`direction = "unknown"` and the active-mode contribution is **not applied**
in that case (reason code `direction_unknown`).

### Parity-pending caveat

While Thinkorswim parity fixtures remain pending the contribution still
emits the `thinkorswim_parity_pending` reason code. A future flag,
`parity_required_for_active`, can be set to `True` to refuse active-mode
application until a fixture has been validated; the current default is
`False` so operators can opt in to active mode before parity lands. The
unit test
`tests/test_momentum_ranking_contribution.py::test_parity_required_for_active_blocks_when_pending`
pins the gate.

### What Phase B1 does NOT do

- **No strategy families**: no new strategy registry entries. No new setup
  engine paths.
- **No recommendation-approval changes**: `recommendation_service.generate`,
  the quality gates, and the queue-promote flow are unchanged.
- **No paper-order changes**: paper open/close/lifecycle endpoints, sizing,
  commissions, and review surfaces are unchanged.
- **No live-trading**: `LIVE_TRADING_ALLOWED` and `BROKER_PROVIDER` defaults
  remain. The contribution function refuses to surface
  `approve`/`reject`/`side`/`shares`/`order_id`/`route` keys (test
  `test_contribution_payload_does_not_include_approval_or_routing_fields`).
- **No DB migrations**: `momentum_contribution` is an in-flight payload
  field on the ranking-engine output only. Persisted recommendation rows
  are unchanged.

### How to switch modes

```bash
# Default — safest. Computes context but does not apply.
unset MACMARKET_MOMENTUM_RANKING_MODE  # or set to "shadow"

# Disable entirely (regression hunts, comparison runs).
export MACMARKET_MOMENTUM_RANKING_MODE=off

# Apply bounded contribution to ranking. Requires explicit operator decision.
export MACMARKET_MOMENTUM_RANKING_MODE=active
```

### Tests

- `tests/test_momentum_ranking_contribution.py` — 22 tests pinning bounded
  components, sanitation, reason codes, parity gate, dict-shape acceptance,
  and the no-approval/no-routing payload guardrails.
- `tests/test_momentum_ranking_engine_integration.py` — 6 tests pinning
  off / shadow / active ranking-engine behavior, score-scale clamping,
  and backward-compatible call signature.

## Future phases

- **Thinkorswim fixture validation**: drop CSVs into
  `tests/fixtures/thinkorswim_momentum/` per the parity-fixtures section
  above and update `manifest.json`. Once a fixture passes, flip
  `parity_required_for_active` to `True` so active mode requires measured
  parity rather than relying on operator discretion alone.
- **Phase C (gated, separate authorization)**: dedicated strategy families
  combining momentum with event/regime/sector filters. Same gate as Phase B.
