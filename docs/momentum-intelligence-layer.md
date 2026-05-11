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

## Phase B2 — operator UI surfaces for the ranking contribution

Phase B2 surfaces the Phase B1 contribution in the operator console
**without** changing ranking math, recommendation approval, paper-order
behavior, options/replay/HACO behavior, or strategy families. It is
display-only.

### Operator UI surfaces

| Surface | File |
|---|---|
| Frontend types | `apps/web/lib/recommendations.ts` (`MomentumRankingContribution`, `MomentumRankingMode`; `QueueCandidate.momentum_contribution`). |
| Pure helpers | `apps/web/lib/momentum-ranking.ts` (`momentumRankingModeLabel`, `momentumRankingAppliedLabel`, `momentumContributionTone`, `summarizeMomentumContribution`, `getMomentumContributionReasonLabels`, `hasMomentumRankingWarnings`, `buildMomentumRankingBreakdown`, `momentumScoreContextRow`, `MOMENTUM_RANKING_DETERMINISTIC_NOTE`). |
| Reusable card | `apps/web/components/recommendations/momentum-ranking-card.tsx` — `<MomentumRankingCard contribution compact title />`. Also exports `<MomentumRankingInlineBadge />` for dense list rows (not used by default). |
| Recommendations integration | `apps/web/app/(console)/recommendations/page.tsx` renders the card once near the existing chart-context / momentum-summary block when a candidate is selected. The card sources the contribution from the live queue candidate first, then falls back to the stored recommendation's `ranking_provenance.momentum_contribution`. |

### Display copy (off / shadow / active)

| Mode | Mode badge | Applied badge | Header contribution badge | Final-score badge |
|---|---|---|---|---|
| `off`    | "Off — not computed" | "Not computed" | n/a | n/a |
| `shadow` | "Shadow — computed, not applied" | "Computed — final score unchanged" | "Shadow `+X.XX`" | "Final score unchanged" |
| `active` | "Active — applied to ranking" | "Bounded contribution applied to ranking" | "Applied `+X.XX`" | n/a |

When a contribution is computed but the bounded total has been suppressed
(direction unknown, parity required gate, etc.), `active` mode still shows
"Computed — bounded contribution not applied" so operators see the audit
trail rather than a silent miss.

### Component breakdown rendered

The card exposes the four Phase B1 components per row with per-row hints:

- Momentum alignment (cap `+10`, direction-aligned only)
- Trend alignment (cap `+8`)
- HiLo confirmation (cap `+5`)
- Reversal warning penalty (floor `-12`)

Plus a score-context row: total score / total label / trend / momo.

### Warnings and reason chips

The card renders the typed reason codes as readable chips:

| Reason code | Chip label |
|---|---|
| `thinkorswim_parity_pending` | "Thinkorswim parity pending" |
| `derived_higher_timeframe` | "Derived higher timeframe" |
| `direction_unknown` | "Direction unknown" |
| `momentum_no_trade_warning` | "No-trade warning" |
| `momentum_reversal_warning` | "Reversal warning" |
| `momentum_pullback_signal` | "Pullback signal" |
| `momentum_payload_unavailable` | "Momentum payload unavailable" |
| `active_blocked_parity_required` | "Active blocked — parity required" |

Reversal and no-trade flags additionally trigger a prominent **Warning**
badge wrapped in `<strong>`. Parity-pending and derived-HTF stay visible
but **not alarming** (neutral tone).

### Phase B2 guardrails

A static guard test (`apps/web/lib/momentum-integration.test.ts`) pins:

- Momentum-ranking display helpers are **not** imported into
  order/paper-position/paper-trade/options-paper-structure/replay-preview
  routes.
- Recommendation-approval / order helper files (`lib/orders-helpers.ts`,
  `lib/api-client.ts`, `lib/guided-workflow.ts`, `lib/lineage-format.ts`)
  do not import `@/lib/momentum-ranking` or the card.
- The card and helper modules do not contain `approve trade`, `auto
  approve`, `route order`, `buy now`, `sell now`, `enter now`, or
  `short now` copy.
- The Recommendations page wires the card and reads `momentum_contribution`
  off candidates.

A backend serialization test
(`tests/test_momentum_ranking_serialization.py`) pins that every
`RankedCandidate` in the queue payload carries the full contribution shape
in shadow mode, that off mode emits a stable disabled shape, and that
contribution payloads never surface `approved` / `rejected` / `side` /
`shares` / `order_id` / `route` keys.

### What Phase B2 does NOT do

- **No ranking math changes** beyond Phase B1. The Phase B1 scoring helper
  and the engine wire-up are untouched.
- **No default mode change.** Default remains `shadow`.
- **No active mode flip.** Operators must opt in via
  `MACMARKET_MOMENTUM_RANKING_MODE=active`.
- **No recommendation approval, paper-order, options, replay, HACO
  changes.**
- **No strategy families.**
- **No DB migrations.** Contribution is an in-flight ranked-candidate
  field only.

### Tests (Phase B2)

- `apps/web/lib/momentum-ranking.test.ts` — mode/applied label formatting,
  shadow vs active framing, tone selection, reason-code translation
  including dedupe and humanization, warning detection, null/off handling,
  breakdown rows, deterministic-note no-action-language guard.
- `apps/web/components/recommendations/momentum-ranking-card.test.tsx` —
  renders missing / off / shadow / active states, breakdown, score
  context, parity-pending / derived-HTF / direction-unknown chips,
  reversal+no-trade prominence, deterministic-context note, compact mode,
  inline badge variants.
- `apps/web/lib/momentum-integration.test.ts` — strengthened with the
  Phase B2 display guards.
- `tests/test_momentum_ranking_serialization.py` — backend contract pin.

## Phase B3 — operator status visibility

Phase B3 surfaces the Momentum ranking mode + parity state in the
operator UI without touching ranking math, recommendation approval,
paper-order, options/replay/HACO behavior, or strategy families. It is
**status-only**.

### Where the operator sees it

| Surface | File |
|---|---|
| Backend status schema | `src/macmarket_trader/domain/schemas.py` (`MomentumRankingStatus`) |
| Backend status builder | `src/macmarket_trader/recommendation/momentum_ranking.py::build_momentum_ranking_status` |
| Read-only API endpoint | `GET /user/momentum-ranking-status` (approved user; in `admin.py` user_router; no DB writes, no provider calls) |
| Frontend proxy route | `apps/web/app/api/user/momentum-ranking-status/route.ts` |
| Frontend client | `apps/web/lib/momentum-ranking-status.ts` (`fetchMomentumRankingStatus`, `MomentumRankingStatus` type) |
| Status card | `apps/web/components/recommendations/momentum-ranking-status-card.tsx` (`<MomentumRankingStatusCard>` + auto-fetching `<MomentumRankingStatusSection>`) |
| Operator integration | `apps/web/app/(console)/settings/page.tsx` — mounts `<MomentumRankingStatusSection>` at the bottom of Settings as operator readiness context (does **not** appear in Recommendations workflow). |

### What the status surfaces

| Field | Meaning |
|---|---|
| `mode` | Resolved `off` / `shadow` / `active` after env normalization. Invalid env values resolve to `shadow`. |
| `default_mode` | Always `shadow`. |
| `env_var` | `MACMARKET_MOMENTUM_RANKING_MODE`. |
| `raw_env_value` | The raw value as read from settings (for audit). |
| `invalid_env_value` | True when the configured value was unrecognized. |
| `enabled` | True for `shadow` / `active`. |
| `applied_by_default` | True only for `active`. |
| `parity_status` | `validated_against_thinkorswim_fixture` when the parity manifest exists, otherwise `pending_thinkorswim_fixture_validation`. |
| `parity_fixture_manifest_present` | Presence check of `tests/fixtures/thinkorswim_momentum/manifest.json`. Read-only; never parses content. |
| `parity_fixture_manifest_path` | Absolute path to the manifest when present. |
| `parity_required_for_active` | Mirrors `MomentumRankingConfig.parity_required_for_active`; informational only. |
| `real_thinkorswim_parity_pending` | True until a manifest is present. |
| `active_mode_warning` | Set when `mode=active` and parity is pending. Operator-facing message — never an approval. |
| `reason_codes` | Audit codes: `invalid_env_value_resolved_to_shadow`, `thinkorswim_parity_pending`, `active_mode_with_parity_pending`, `active_blocked_parity_required`. |
| `guardrails` | Always includes the three deterministic-context lines; appends "Real Thinkorswim parity fixtures are still pending." when applicable. |

### How `MACMARKET_MOMENTUM_RANKING_MODE` works

The endpoint reads `settings.momentum_ranking_mode`, which is bound to
`MACMARKET_MOMENTUM_RANKING_MODE` (preferred) or `MOMENTUM_RANKING_MODE`
(alias) via the same Pydantic-settings binding introduced in Phase B1.
Allowed values: `off`, `shadow`, `active` (case-insensitive). Unknown
values resolve to `shadow` and emit
`invalid_env_value_resolved_to_shadow` so operators see the fallback in
the status card rather than the application silently masking a typo.

### Default remains shadow

Phase B3 does **not** change the default. The status card pins this:
`default_mode` is always `shadow`, and the resolved `mode` for an
unconfigured environment is `shadow`.

### Active-mode warning while parity is pending

When `mode=active` and `real_thinkorswim_parity_pending=true`, the
status card renders a prominent `role="alert"` warning explaining that
the bounded contribution is applying while Thinkorswim parity fixtures
are still pending review. If `parity_required_for_active=true`, the
warning instead states that active mode is **blocked** until parity
lands and adds the `active_blocked_parity_required` reason code.

### What Phase B3 does NOT do

- **No ranking math changes.** `build_momentum_ranking_contribution`
  and the engine wire-up are untouched.
- **No default mode change.** Default remains `shadow`.
- **No active-mode enablement.** Operators must still opt in via the
  env var.
- **No `parity_required_for_active` flip.** Pinned to `False` per
  Phase B1.
- **No strategy families.**
- **No recommendation approval / paper-order / options / replay /
  HACO changes.**
- **No DB migrations.** Status is computed on read.

### Tests (Phase B3)

- `tests/test_momentum_ranking_status.py` — 15 tests pinning the pure
  status builder (default/off/active/invalid-env/manifest-present),
  the endpoint (auth required, shadow/off/active/invalid responses, no
  market provider side effects), and the no-approval/no-routing
  payload guard.
- `apps/web/lib/momentum-ranking-status.test.ts` — client delegates to
  `fetchWorkflowApi`, surfaces non-OK and auth-pending states without
  throwing.
- `apps/web/components/recommendations/momentum-ranking-status-card.test.tsx`
  — empty/loading/error/shadow/off/active branches, parity-pending +
  invalid-env warnings rendered as `<strong>`/`role="alert"`,
  parity-validated good tone, deterministic-context note, and a
  no-action-language guard.
- `apps/web/lib/momentum-integration.test.ts` — extended Phase B3
  guards keep the status helper/component out of order/approval routes
  and helper files; confirm the Settings page wires the section and
  the proxy route forwards correctly.

## Phase B4 — Momentum Shadow Impact Review

Phase B4 adds an operator-facing **review** of how Momentum Intelligence
would affect recommendation ranking under the current mode. It is
**display-only**: no ranking math, queue sorting, approval, paper-order,
options/replay/HACO behavior, or strategy-family code is touched.

### Surfaces

| Surface | File |
|---|---|
| Pure helpers | `apps/web/lib/momentum-impact.ts` (`MomentumImpactRow`, `MomentumImpactSummary`, `buildMomentumImpactRows`, `summarizeMomentumImpact`, `estimateActiveScore`, `estimateActiveRankDelta`, `momentumImpactTone`, `sortMomentumImpactRows`, `formatRankDelta`, `formatScoreUnit`, `formatUnitScore`, `MOMENTUM_IMPACT_DETERMINISTIC_NOTE`). |
| Reusable component | `apps/web/components/recommendations/momentum-impact-review.tsx` (`<MomentumImpactReview candidates compact title />`). |
| Recommendations integration | `apps/web/app/(console)/recommendations/page.tsx` renders the review at the bottom of the page using the already-loaded `queue` rows — no extra fetch, no sorting change, no approval/promote/paper-order impact. |
| Settings pointer | `apps/web/components/recommendations/momentum-ranking-status-card.tsx` now includes a one-line "Review shadow impact in Recommendations." pointer (link only — no new navigation). |

### Estimated active score logic

For each in-memory candidate the review computes:

```
shadow mode  → estimated_active = clamp01(candidate.score + shadow_contribution / 100)
active mode  → estimated_active = candidate.score        # already applied — no double count
off / missing / direction_unknown → estimated_active = candidate.score
```

- Inputs are sanitized: `NaN` / `Infinity` / non-numeric values collapse to `0`.
- The estimated score is always finite and always inside `[0, 1]`.
- The helper never mutates the candidate, never refetches, never recomputes Momentum indicator math (the contribution is consumed verbatim from the queue payload).

### Estimated rank movement

`buildMomentumImpactRows` derives a per-row `estimatedRankBefore` /
`estimatedRankAfter` / `estimatedRankDelta` by stable-sorting the
estimated active scores. Positive delta = rank would improve; negative =
rank would drop. This is **estimate-only**: the live queue's sorting
never changes.

### Mode-specific framing copy

| Mode | Framing line |
|---|---|
| `shadow` | "Shadow mode is enabled. Final scores are unchanged. The estimated active score shows what would happen if active mode were enabled." |
| `active` | "Active mode is enabled. The bounded contribution is already applied to the current score — these estimates do not double-count it." |
| `off`    | "Momentum contribution is disabled (off) or not computed. No estimated movement is shown." |

The component also renders summary chips for: candidates reviewed,
positive/negative/zero contribution counts, warnings count, parity-pending
count, direction-unknown count, contribution-missing count, net Δ score,
and how many candidates would move up/down.

### Warning and reason chips

The review surfaces the same reason-code labels as the Phase B2 card:
`Thinkorswim parity pending`, `Derived higher timeframe`, `Direction
unknown`, `No-trade warning`, `Reversal warning`, `Pullback signal`,
`Momentum payload unavailable`. Reversal/no-trade warnings tone as `warn`
and trigger the warning count.

A canonical operator note is rendered in every state:

> *This review estimates impact only. It does not change queue sorting,
> approval, sizing, or order routing.*

### What Phase B4 does NOT do

- **No ranking math change.** `build_momentum_ranking_contribution`,
  `DeterministicRankingEngine`, and the bounded-component caps from
  Phase B1 are byte-identical.
- **No default mode change.** Default remains `shadow`.
- **No active-mode enablement.** The review describes what active mode
  *would* look like but never flips the flag.
- **No queue sorting change.** The live queue order is preserved; the
  review's `estimatedRankAfter` is a per-row label only.
- **No recommendation approval / promote / save / paper-order / settle
  / replay / options-preview changes.**
- **No strategy families.**
- **No DB migrations.** The review reads in-memory candidates.

### Tests (Phase B4)

- `apps/web/lib/momentum-impact.test.ts` — 25 tests: shadow/active/off
  estimation, clamp to `[0, 1]`, no NaN/inf, no mutation of inputs,
  estimated rank-after derivation, summary counts (positive/negative/
  zero/warnings/parity/direction-unknown/missing), `observed_modes`,
  tone selection, sort-mode behavior, formatting helpers, deterministic
  note guard.
- `apps/web/components/recommendations/momentum-impact-review.test.tsx`
  — 8 render tests: empty, summary counts, mode framing (shadow/active/
  off), parity / direction-unknown / reversal chips, rank-up/down
  badges, deterministic-context note in every branch, no forbidden
  action language.
- `apps/web/lib/momentum-integration.test.ts` — strengthened with
  Phase B4 guards: Recommendations page imports `<MomentumImpactReview>`,
  helpers/component stay out of order/paper-position/paper-trade/options-
  paper/replay-preview routes and helper files, no forbidden language.

## Phase B4.2 — improved direction inference for bullish strategy families

Before Phase B4.2, candidates for strategies like `Breakout / Prior-Day
High` showed `direction_unknown` in the Momentum Shadow Impact Review and
received a `0.00` bounded contribution even when Momentum was Bull /
Max Bull. Phase B4.2 fixes that by **centralizing** direction inference
behind a single helper and feeding it the strategy registry's
`directional_profile` metadata. **No ranking math, contribution caps,
default mode, queue sorting, approval, paper-order, options/replay/HACO,
or strategy-family code is changed.**

### Priority cascade

`_infer_direction(context)` in
`src/macmarket_trader/recommendation/momentum_ranking.py` now follows
this explicit priority order:

1. **Explicit candidate metadata** — `direction` / `side` / `bias` on
   the contribution context wins over everything else. Reason code:
   `direction_from_candidate_metadata`.
2. **Strategy registry metadata** — when the ranking engine resolves a
   `StrategyRegistryEntry`, it passes the entry's `directional_profile`
   to the contribution context. `bullish` → `long`, `bearish` → `short`,
   anything else (`neutral`, `carry`, `volatility`) explicitly stays
   `unknown`. Reason code: `direction_from_strategy_metadata`.
3. **Strategy ID fallback** — if no registry profile was passed,
   conservative known IDs (`event_continuation`,
   `breakout_prior_day_high`, `pullback_trend_continuation`) map to
   `long`. `mean_reversion` and any ID containing `fade` stay `unknown`.
   Reason code: `bullish_strategy_direction_inferred`.
4. **Strategy label fallback** — normalized (lowercased, punctuation
   collapsed) labels are matched against:
   - `event continuation`
   - `breakout prior day high`
   - `prior day high breakout`
   - `pullback trend continuation`
   Labels containing `fade` or `mean reversion` stay `unknown`. Reason
   code: `bullish_strategy_direction_inferred`.
5. **Unknown** — anything else returns `direction_unknown` and the
   bounded contribution stays unapplied in active mode.

### Phase B4.2 rules

- Bearish/short is **only** inferred from explicit candidate metadata or
  the registry's `bearish` profile. Label fallback never infers bearish
  — Phase B4.2 stays conservative.
- A neutral / carry / volatility registry profile **overrides** the
  label fallback. The registry has the last word for those entries.
- All existing contribution caps (`max_total_contribution`,
  per-component caps, parity gate) are unchanged — Phase B4.2 only
  unlocks the bounded contribution for strategies that were
  incorrectly marked `direction_unknown` before.

### Ranking-engine wiring

`DeterministicRankingEngine.rank_candidates` now passes
`strategy_id` and `directional_profile` from the resolved
`StrategyRegistryEntry` into the contribution context:

```python
recommendation_context={
    "strategy": entry.display_name,
    "strategy_id": entry.strategy_id,
    "directional_profile": entry.directional_profile,
    "recent_trend": recent_trend,
}
```

Frontend rendering picks up the new reason codes via
`apps/web/lib/momentum-ranking.ts::REASON_CODE_LABELS`:

| Reason code | Operator-facing label |
|---|---|
| `direction_from_candidate_metadata` | Direction from candidate metadata |
| `direction_from_strategy_metadata` | Direction from strategy metadata |
| `bullish_strategy_direction_inferred` | Bullish strategy direction inferred |
| `direction_inferred_from_strategy` | Direction inferred from strategy |

The Momentum Shadow Impact Review's `direction_unknown_count` now drops
to zero for queues consisting of these strategies.

### What Phase B4.2 does NOT change

- **Ranking math / caps.** `build_momentum_ranking_contribution` body
  is unchanged beyond the inference helper. All caps and clamps from
  Phase B1 hold.
- **Default mode.** Still `shadow`.
- **Queue sorting.** Live queue ordering is preserved; the impact
  review still re-derives estimated rank-after locally without
  touching the live queue.
- **Recommendation approval, promote, save, paper-order, settle,
  replay, options preview, HACO/HACOLT behavior.** Untouched.
- **Strategy families.** No new strategy registry entries; no new
  setup-engine paths; no new `setup_type` values.

### Tests (Phase B4.2)

- `tests/test_momentum_ranking_contribution.py` — 15 new direction
  inference tests (priority cascade, label normalization, explicit
  metadata precedence, registry override, neutral registry overrides
  bullish label, off-mode short-circuit, cap preservation, shadow
  mode carries inferred reason without applying).
- `tests/test_momentum_ranking_engine_integration.py` — 4 new
  end-to-end tests through `DeterministicRankingEngine` confirming
  Breakout / Prior-Day High, Event Continuation, and Pullback /
  Trend Continuation now infer `long` via registry metadata and the
  bounded contribution applies in active mode for bullish Momentum.
- `apps/web/lib/momentum-ranking.test.ts` — Phase B4.2 reason-code
  translations.
- `apps/web/lib/momentum-impact.test.ts` — bullish-inferred rows do
  not count toward `direction_unknown_count`; rows that still carry
  `direction_unknown` continue to count.

## Phase B6 — controlled active-mode safety guard

Phase B6 lets an operator run **active** Momentum ranking in a
controlled paper / research environment **without** changing
recommendation approval, paper-order behavior, or live trading. The
guard is an explicit second env var that must be flipped **alongside**
the mode flag; production deployments that only change the mode flag
stay on shadow.

### Env vars

| Variable | Allowed values | Default | Effect |
|---|---|---|---|
| `MACMARKET_MOMENTUM_RANKING_MODE` | `off` / `shadow` / `active` (case-insensitive) | `shadow` | Operator-requested mode. |
| `MACMARKET_ALLOW_MOMENTUM_ACTIVE_RANKING` | `true` / `1` / `yes` (case-insensitive) | `false` | Safety guard; must be truthy for the **requested active** mode to take effect. |

Behavior table:

| Requested mode | Active allowed | Effective mode | Notes |
|---|---|---|---|
| `(unset)` | `false` | `shadow` | Default deployment. |
| `shadow` | `false` | `shadow` | No change. |
| `off` | `false` | `off` | Contribution not computed. |
| Invalid mode string | `false` | `shadow` | Adds `invalid_env_value_resolved_to_shadow`. |
| `active` | `false` | **`shadow`** | Adds `active_mode_blocked_by_safety_guard` + operator warning. Final scores/order unchanged. |
| `active` | `true` | `active` | Bounded contribution applies exactly as Phase B1 designed. |

### Resolution helper

`resolve_effective_momentum_ranking_mode(requested, *, active_allowed)`
in `src/macmarket_trader/recommendation/momentum_ranking.py` returns
`(effective, requested_canonical, blocked)`. The truthy parser accepts
`true` / `1` / `yes` and rejects anything else (including invalid
strings), defaulting to `false`.

### Status payload additions

`MomentumRankingStatus` (Phase B3) gained these fields:

| Field | Meaning |
|---|---|
| `requested_mode` | Operator's raw requested mode (after invalid-string normalization). |
| `effective_mode` | The mode actually applied — mirrors `mode` for backward compatibility. |
| `active_allowed` | Resolved value of the safety-guard env var. |
| `active_guard_env_var` | The literal env-var name (`MACMARKET_ALLOW_MOMENTUM_ACTIVE_RANKING`). |
| `active_mode_blocked` | True when active was requested but the guard refused. |
| `active_mode_block_reason` | Operator-facing explanation when blocked. |

The Phase B3 status card was extended to render `Effective: ...`,
`Requested: ...` (when different), an `Active allowed: Yes/No` badge,
the active-guard env-var row, and a prominent
`<strong data-testid="momentum-ranking-status-safety-guard-block">`
warning when the safety guard refused active mode. The endpoint still
has **zero** market-provider side effects.

### Operator-facing copy

The status payload's `guardrails` array now always includes:

- *"Shadow mode computes contribution but does not alter final ranking."*
- *"Active mode applies a bounded contribution only."*
- *"This does not approve, reject, size, or route trades."*
- *"Approval, sizing, and paper-order creation remain manual."*
- *"Active mode changes ranking order only; it does not approve, reject, size, or route trades."*
- *"Active Momentum ranking requires MACMARKET_ALLOW_MOMENTUM_ACTIVE_RANKING=true."*
- *"Thinkorswim parity fixtures are still pending."* (when applicable)

The Momentum Shadow Impact Review's framing line is mode-aware:

| State | Framing line |
|---|---|
| Shadow | *"Shadow mode is enabled. Final scores are unchanged. The estimated active score shows what would happen if active mode were enabled."* |
| Active (allowed) | *"Momentum contribution is currently applied to ranking. Approval and paper orders remain manual. Active mode changes ranking order only; it does not approve, reject, size, or route trades."* |
| Active (blocked) | *"Active was requested but the safety guard blocked application; review is running as shadow. Final scores are unchanged. Active Momentum ranking requires MACMARKET_ALLOW_MOMENTUM_ACTIVE_RANKING=true."* |
| Off | *"Momentum contribution is disabled (off) or not computed. No estimated movement is shown."* |

### Before / after visibility (RankedCandidate fields)

`RankedCandidate` gained four optional fields so the impact review can
show baseline vs applied score without recomputing indicators:

| Field | Meaning |
|---|---|
| `score_before_momentum` | Baseline deterministic score before any Momentum delta. |
| `score_after_momentum` | The score actually published on `score`. |
| `momentum_score_delta` | Bounded contribution that was applied (active mode only). |
| `momentum_rank_mode` | Effective mode at the time of ranking (`off` / `shadow` / `active`). |

In shadow and blocked-active modes, `score_before_momentum ==
score_after_momentum` and `momentum_score_delta` is `None`. In active
mode with the guard satisfied, `momentum_score_delta` reflects the
exact bounded delta added to the score. In `off` mode all four fields
stay `None`.

### Operator enable / disable checklist

1. **Confirm parity caveat is acceptable.** Real Thinkorswim parity
   fixtures are still pending; enabling active mode is a research /
   paper-only decision.
2. **Set both env vars** in the **controlled paper/research**
   environment only:

   ```bash
   export MACMARKET_MOMENTUM_RANKING_MODE=active
   export MACMARKET_ALLOW_MOMENTUM_ACTIVE_RANKING=true
   ```

3. **Restart the backend** so settings reload.
4. **Verify Settings → Momentum ranking status** shows:
   - `Effective: Active — applied to ranking`
   - `Active allowed: Yes`
   - **No** "Active blocked — safety guard not enabled" warning.
5. **Verify Recommendations → Momentum ranking contribution card** and
   **Momentum Shadow Impact Review** report mode `active` and that
   `score_after_momentum` differs from `score_before_momentum` for
   bullish candidates with a Bull / Max Bull Momentum payload.
6. **Confirm approval and paper orders are still manual.** No
   recommendation should be auto-approved; no paper order should be
   auto-created. Phase B6 must never change those flows.
7. **To disable**, set either `MACMARKET_MOMENTUM_RANKING_MODE=shadow`
   *or* remove `MACMARKET_ALLOW_MOMENTUM_ACTIVE_RANKING=true`, then
   restart. Either change resolves the effective mode back to shadow.

### What Phase B6 does NOT do

- **No ranking math / cap changes.** Phase B1's bounded contribution
  caps still hold. `build_momentum_ranking_contribution` only learned
  to surface the new safety-guard reason code; component math is
  byte-identical.
- **No default mode change.** Default remains `shadow`.
- **No recommendation approval changes.**
  `recommendation_service.generate`, the deterministic quality gates,
  and the queue promote flow are untouched.
- **No paper-order behavior changes.** Paper open/close/settle/review
  code paths and surfaces are unchanged. The frontend guard test
  confirms the new status helpers/components are not imported into
  any order/paper-position/paper-trade/options-paper-structure/replay-
  preview route.
- **No live trading.** `LIVE_TRADING_ALLOWED` and `BROKER_PROVIDER`
  defaults remain.
- **No strategy families.** No new strategy registry entries; no
  new setup-engine paths; no new `setup_type` values.

### Tests (Phase B6)

- `tests/test_momentum_active_mode_guardrails.py` — 39 tests covering
  the resolver table, truthy parsing, contribution behavior in blocked
  vs allowed active, off-mode short-circuit, ranking-engine end-to-end
  (no score change when blocked; bounded change when allowed;
  before/after fields populated), status builder, status endpoint
  (default / blocked / allowed-active / no-provider-calls), and the
  no-approval/no-routing payload guard.
- `tests/test_momentum_ranking_status.py` — Phase B3 status tests
  updated to set the safety-guard allow flag when the test intent is
  "active mode applies".
- `apps/web/components/recommendations/momentum-ranking-status-card.test.tsx`
  — 4 new tests: blocked-active warning, allowed-active "Active
  allowed: Yes" badge, Phase B6 guardrail copy lines, env-var label.
- `apps/web/components/recommendations/momentum-impact-review.test.tsx`
  — 1 new test pinning the blocked-active framing copy plus the
  `Active blocked — safety guard not enabled` chip.
- `apps/web/lib/momentum-ranking.test.ts` — translates the new
  `active_mode_blocked_by_safety_guard` reason code.
- `apps/web/lib/momentum-integration.test.ts` — Phase B6 describe
  block pins Settings wiring, env-var references in the card +
  impact review, and forbids the safety-guard symbols from
  order/paper-order/options-paper/replay-preview routes.

## Phase B6.1 — active-mode score saturation control

Phase B6 confirmed active mode works, but operators observed too many
Max Bull / Bull candidates clamping to `score = 1.000` because Phase B1
mapped the bounded +20 score-unit contribution onto +0.20 of the
ranking-score scale. With many base scores already at 0.80–0.90, active
mode flattened high-Momentum candidates into ties at the ceiling.

**Phase B6.1 introduces a configurable scale that dampens active-mode
score application without changing the bounded raw-contribution math,
the safety guard, the parity gate, the default mode, recommendation
approval behavior, or paper-order behavior.**

### Env var

| Variable | Allowed values | Default |
|---|---|---|
| `MACMARKET_MOMENTUM_ACTIVE_DELTA_SCALE` (alias `MOMENTUM_ACTIVE_DELTA_SCALE`) | float in `[0.0, 1.0]` | `0.35` |

Invalid env values (non-numeric, infinite, out of range) fall back to
the deterministic default `0.35`. The status payload surfaces
`active_delta_scale_invalid=True` and the
`momentum_active_delta_scale_invalid` reason code so operators can see
the fallback was used without the application crashing.

### Formula

```
applied_score_delta = raw_total_contribution / 100 × active_delta_scale
score_after_momentum = clamp01(score_before_momentum + applied_score_delta)
```

The **raw** contribution remains in Phase B1's score-units cap (`±20`).
The **applied** delta lives in the ranking engine's `[0, 1]` score
space.

| `active_delta_scale` | Max applied delta | Min applied delta |
|---|---|---|
| `0.35` (default) | `+0.070` | `-0.042` |
| `0.50` | `+0.100` | `-0.060` |
| `0.70` | `+0.140` | `-0.084` |
| `1.00` (pre-B6.1 behavior) | `+0.200` | `-0.120` |

A baseline of `0.898` plus `+20` raw at default scale lands at
`0.968`, not `1.000`. Higher-scoring candidates can still clamp at
`1.0`, but only when baseline + scaled delta legitimately exceeds the
ceiling.

### Tuning guidance

- **Lower the scale (e.g., `0.20`)** when the active queue keeps
  saturating — Momentum still nudges ordering but contributes less.
- **Raise the scale (e.g., `0.70`)** when Momentum should pull rank
  movement harder during a research session.
- Keep the safety guard (`MACMARKET_ALLOW_MOMENTUM_ACTIVE_RANKING=true`)
  set explicitly — Phase B6.1 only operates after the Phase B6 guard
  permits active mode.

### Status payload additions

`MomentumRankingStatus` gained:

| Field | Meaning |
|---|---|
| `active_delta_scale` | Resolved float (clamped to `[0.0, 1.0]`). |
| `active_delta_scale_env_var` | Always `MACMARKET_MOMENTUM_ACTIVE_DELTA_SCALE`. |
| `active_delta_scale_invalid` | True when env was unparseable / out of range. |
| `active_delta_scale_warning` | Operator-facing fallback message when invalid. |

The Settings status card renders the scale value, the env-var label,
the operator helper line *"Active score delta = raw contribution ÷ 100
× active delta scale."*, and an `role="alert"` invalid-fallback warning
when applicable.

### Contribution payload additions

`MomentumRankingContribution` gained:

| Field | Meaning |
|---|---|
| `active_delta_scale` | Per-candidate copy of the resolved scale. |
| `raw_total_contribution` | Bounded raw contribution in score units (unchanged math, just published explicitly). |
| `applied_score_delta` | `0` in shadow / blocked-active / off; the actual ranking-score delta in active mode. |

Existing fields (`total_contribution`, `shadow_contribution`, the
component breakdowns) keep their Phase B1 semantics — Phase B6.1 does
**not** reduce the raw contribution calculation. Operators still see
the same `+20 / -12` audit explanation; the applied delta is shown
alongside.

### Ranking-engine behavior

- **Active + allow + valid scale.** Engine applies
  `applied_score_delta` (already scaled by the contribution payload)
  to the candidate score, clamped to `[0, 1]`. Old code that used
  `total_contribution / 100` is replaced by the
  `applied_score_delta` field so the per-row math has one source of
  truth.
- **Shadow.** Final score unchanged. The frontend impact review uses
  the contribution's `active_delta_scale` (or default `0.35` when
  absent) to estimate what active mode would produce.
- **Blocked active.** Effective shadow. The contribution still
  carries `raw_total_contribution` and `active_delta_scale`; the
  applied delta stays `0`.
- **Off.** Unchanged.

### Frontend display

- **Momentum ranking card** now shows two header badges per candidate:
  `Shadow +X.XX raw` *and* `Est. delta @ scale +Y.YY` (or `Applied
  +X.XX raw` and `Score delta +Y.YY` in active mode), plus a footer
  line `Active delta scale: 0.35 · raw ÷ 100 × scale = applied score
  delta.`.
- **Momentum Shadow Impact Review** renders a small "Active delta
  scale: 0.35" note beneath the mode framing and splits the table
  column from "Shadow / applied (score units)" into two columns: "Raw
  contribution (score units)" and "Applied delta @ scale".
- **Settings status card** renders `Active delta scale` and `Active
  delta scale env var` rows plus the helper copy line.

### What Phase B6.1 does NOT change

- **Raw contribution math / caps.** Phase B1's bounded `[-12, +20]`
  cap and per-component caps are byte-identical. The bounded scoring
  helper is untouched except to publish three new optional fields.
- **Default mode.** Default remains `shadow`. The safety guard
  (`MACMARKET_ALLOW_MOMENTUM_ACTIVE_RANKING`) still must be truthy
  before active mode applies.
- **Recommendation approval / paper-order / options / replay / HACO
  behavior.** None of those code paths was touched.
- **Indicator math.** No changes to
  `compute_true_momentum`, `compute_hilo_elite`,
  `compute_true_momentum_score`, or any other Phase A indicator
  surface.
- **Parity gate.** `parity_required_for_active` defaults unchanged;
  Thinkorswim parity fixtures remain pending and surfacing the
  `thinkorswim_parity_pending` reason code on every contribution.
- **Strategy families.** No new strategy registry entries; no new
  setup-engine paths.

### Operator checklist

1. Set the scale alongside the existing env vars (paper / research
   environment only):

   ```bash
   export MACMARKET_MOMENTUM_RANKING_MODE=active
   export MACMARKET_ALLOW_MOMENTUM_ACTIVE_RANKING=true
   export MACMARKET_MOMENTUM_ACTIVE_DELTA_SCALE=0.35   # tune as needed
   ```

2. Restart the backend so settings reload.
3. Confirm Settings → Momentum ranking status shows the chosen scale
   value (and **no** invalid-scale alert).
4. Confirm Recommendations queue no longer saturates to 1.000 for
   bullish Momentum candidates with baseline ≤ ~0.93.
5. Approval and paper-order creation remain manual — Phase B6.1
   cannot change either.
6. To revert, unset `MACMARKET_MOMENTUM_ACTIVE_DELTA_SCALE` (returns
   to the deterministic default `0.35`) or set
   `MACMARKET_MOMENTUM_ACTIVE_DELTA_SCALE=1.0` for pre-B6.1 behavior.

### Tests (Phase B6.1)

- `tests/test_momentum_active_delta_scale.py` — 35 tests covering:
  parsing every env-value shape (truthy, valid floats, out-of-range,
  garbage, NaN/inf, bools), config wiring, contribution payload
  scaling (default / explicit scale / blocked-active / shadow / no
  double counting), ranking-engine end-to-end (no saturation at
  default scale, clamp still active at scale `1.0`, shadow score
  unchanged at any scale, blocked-active unchanged, higher scale
  produces a larger applied delta), status builder + endpoint
  exposing the scale and the invalid-fallback reason code, and the
  no-approval/no-routing payload guard at every scale.
- `tests/test_momentum_ranking_status.py`, `test_momentum_ranking_engine_integration.py`,
  `test_momentum_ranking_contribution.py` — existing suites still pass
  unchanged.
- `apps/web/lib/momentum-impact.test.ts` — 4 new tests pinning the
  helper's default-scale fallback, candidate-supplied scale honored,
  no-double-count in active mode, and the impact-row carrying
  `activeDeltaScale` / `rawTotalContribution` / `appliedScoreDelta`.
- `apps/web/components/recommendations/momentum-ranking-card.test.tsx`
  — 3 new tests pinning the raw/applied dual badges, the active-mode
  applied-delta path, and the default-scale fallback when the scale
  is absent.
- `apps/web/components/recommendations/momentum-ranking-status-card.test.tsx`
  — 2 new tests for the Phase B6.1 scale row + env-var and the
  invalid-fallback `role="alert"` block.
- `apps/web/components/recommendations/momentum-impact-review.test.tsx`
  — 2 new tests for the per-row "Applied delta @ scale" column and
  the scale-helper note.

## Phase B6.2 — Active-mode score wiring fix

Phase B6.2 closes two consistency bugs observed after Phase B6.1 went
live in the deployed paper environment with
`MACMARKET_MOMENTUM_RANKING_MODE=active`,
`MACMARKET_ALLOW_MOMENTUM_ACTIVE_RANKING=true`, and
`MACMARKET_MOMENTUM_ACTIVE_DELTA_SCALE=0.35`. It is a strictly
behavior-preserving wiring fix: raw contribution caps, defaults,
parity gates, approval/order behavior, indicator math, and Phase C
remain unchanged.

### Observed deployed bugs

With a bullish active contribution (raw +20, scale 0.35, intended
applied delta +0.07):

1. **Queue scores saturated to 1.000.** Active rows in the
   Recommendations queue rendered `Score 1.000` even when the
   pre-momentum baseline was ~0.812 and the expected post-momentum
   score was ~0.882. The selected-recommendation card on the same
   page correctly displayed "Applied +20.00 raw, Score delta +0.07",
   so the contribution payload was already correct — the queue was
   using a different number.
2. **Momentum Shadow Impact Review showed `Applied delta @ scale:
   0.000`** on the same active rows. The review's per-row display
   diverged from the contribution payload and from the
   recommendation card.

### Root cause

Two separate wiring drifts, both downstream of the (correct) Phase
B6.1 contribution math:

- **Backend (queue path).** The ranking engine recomputed the
  applied delta inline from `raw_total_contribution / 100 * scale`
  before clamping. With raw `+20` and scale `1.0` (which is what
  some deployment paths defaulted to before B6.1 settings were
  reloaded), this drove every bullish row to 1.000. Even at scale
  `0.35`, the inline math diverged subtly from the published
  `applied_score_delta` field on the contribution payload because
  the two code paths could be edited independently.
- **Frontend (impact review path).** The `QueueCandidate` TypeScript
  type was missing the Phase B6 fields the backend already emits
  (`score_before_momentum`, `score_after_momentum`,
  `momentum_score_delta`, `momentum_rank_mode`). `buildMomentumImpactRows`
  therefore had nothing to read in active mode and fell through to
  `contribution.applied_score_delta`, which on older cached payloads
  was either `null` or `0`, rendering `0.000`.

### Fix — single source of truth on the backend

`src/macmarket_trader/recommendation/momentum_ranking.py` now exports
`apply_momentum_score_delta(base_score, contribution) -> tuple[float, float]`.
Every caller that needs to know "given this base score and this
contribution, what is the final score and applied delta?" routes
through this helper:

- Off, shadow, or blocked-active → returns `(clamp01(base), 0.0)`.
- Active + applied with a payload-supplied `applied_score_delta`
  → returns `(clamp01(base + delta), delta)`. The published delta is
  the **intended** scaled value, not the clamp-truncated one, so the
  operator-visible "Score delta +0.07" always matches the contribution
  payload even when the clamp triggers at the 0.0 / 1.0 boundary.
- Active + applied with a missing `applied_score_delta` (backward
  compatibility for pre-B6.1 payloads in replays) → falls back to
  `raw_total_contribution / 100 * active_delta_scale`, then validates
  scale ∈ [0, 1] and is finite, falling back to
  `DEFAULT_ACTIVE_DELTA_SCALE` otherwise.

`ranking_engine.py` now calls `apply_momentum_score_delta` instead
of doing the math inline, so the engine, the contribution payload,
and the operator card cannot drift apart again. `RankedCandidate`
continues to expose `score_before_momentum`, `score_after_momentum`,
`momentum_score_delta`, and `momentum_rank_mode` — the change is the
math underneath them, not the field surface.

### Fix — frontend type completion and fallback chain

`apps/web/lib/recommendations.ts` extends `QueueCandidate` with the
Phase B6 fields the backend already emits (all optional + nullable
so older replay payloads still parse). `apps/web/lib/momentum-impact.ts`
gains a `baselineScore` on every impact row and implements an explicit
three-step fallback chain for the applied delta in active mode:

1. `candidate.momentum_score_delta` (preferred — set by the engine
   via `apply_momentum_score_delta`).
2. `contribution.applied_score_delta` (correct for current backend
   payloads, kept for resilience).
3. `raw_total_contribution / 100 * active_delta_scale` (final
   fallback for legacy replay payloads).

The baseline value is whichever of `candidate.score_before_momentum`
or `currentScore - appliedScoreDelta` is finite, so even a payload
without the new field still renders a sensible baseline column.

`apps/web/components/recommendations/momentum-impact-review.tsx`
gains a `Baseline` table column and active-mode framing copy that
explains "Current score already includes the applied Momentum delta;
the Baseline column shows the pre-Momentum score. Applied delta
shows the scaled Momentum score impact." Shadow rows continue to
show `Baseline == currentScore` because shadow mode does not apply
a delta.

### What did not change

- **Raw contribution caps** remain ±20 with the same Phase B1 inputs
  and weights.
- **Default mode** is still `off` everywhere except deployments that
  explicitly set `MACMARKET_MOMENTUM_RANKING_MODE=active` and
  `MACMARKET_ALLOW_MOMENTUM_ACTIVE_RANKING=true`.
- **Approval and order behavior** remain manual. Phase B6.2 changes
  no approval gate, no broker routing, no `BROKER_PROVIDER`/
  `LIVE_TRADING_ALLOWED` semantics.
- **Indicator math, parity gates, Thinkorswim fixtures** are
  untouched. `parity_required_for_active` defaults stay as they were,
  and the `thinkorswim_parity_pending` reason code still surfaces.
- **Strategy registry** is unchanged. No Phase C work landed.
- **Active delta scale env var, parsing, and defaults** are
  Phase B6.1's responsibility and were not modified.

### Tests (Phase B6.2)

- `tests/test_momentum_b62_score_wiring.py` — 20 new pytest tests:
  parametrized end-to-end engine integration at realistic baselines
  (0.812 / 0.898 / 0.970 / 0.0 / 1.0) with the `_score_symbol`
  patched to fix the baseline; helper-level unit tests for shadow,
  blocked-active, missing `applied_score_delta` (backward-compat
  fallback to `raw / 100 * default_scale`), NaN/inf sanitization,
  and the explicit `momentum_score_delta = applied_score_delta`
  invariant even when the final score clamps; regression pin that
  the queue never applies unscaled raw to a queue score; pin that
  Phase B6 before/after fields surface on every active row; and
  guard that the queue payload still contains no approval, order, or
  routing fields.
- `apps/web/lib/momentum-impact.test.ts` — 8 new tests in a "Phase
  B6.2 applied-delta fallback chain" block: candidate
  `momentum_score_delta` preferred, contribution
  `applied_score_delta` fallback, raw/100*scale fallback, never-zero
  regression for active rows that are actually applied, baseline from
  candidate `score_before_momentum`, baseline computed locally when
  the field is absent, baseline equal to current score in shadow
  mode, and NaN/inf sanitization on every fallback path.
- `apps/web/components/recommendations/momentum-impact-review.test.tsx`
  — 2 new render tests pinning the new `Baseline` column header, the
  baseline value next to the active score (e.g., `0.812` next to
  `0.882`), the rendered scaled delta (`0.070`, never `0.000`), the
  active-mode framing copy explaining current vs. baseline, and the
  fallback chain at the component level when
  `candidate.momentum_score_delta` is absent.

### Operator checklist (Phase B6.2)

1. After deploying Phase B6.2, confirm the Recommendations queue no
   longer saturates to 1.000 for bullish Momentum candidates with
   baseline ≲ 0.93. A `+20` raw at scale `0.35` should produce
   approximately `baseline + 0.07`, clamped at 1.0 when needed.
2. Open the Momentum Shadow Impact Review and verify that active
   rows show a non-zero `Applied delta @ scale`, the new `Baseline`
   column, and framing copy that matches the queue score.
3. Approval and paper-order creation remain manual.
4. To revert behavior, disable active mode via env (
   `MACMARKET_MOMENTUM_RANKING_MODE=shadow` or `off`).

## Phase B6.3 — Single source of truth for the active queue score

Phase B6.3 closes the deployed-but-incompletely-fixed regression: even
after Phase B6.2 routed the engine through `apply_momentum_score_delta`,
the deployed `/user/recommendations/queue` payload still reported
queue rows with the **legacy un-scaled** delta (`raw / 100 = +0.20`)
while the selected-recommendation card showed the correct **scaled**
delta (`raw / 100 × 0.35 = +0.07`). Reproduced shapes:

```
SPY  baseline 0.812 → queue score 1.000  (expected 0.882)
MSFT baseline 0.792 → queue score 0.992  (implies +0.200 delta)
NVDA baseline 0.779 → queue score 0.979  (implies +0.200 delta)
```

The Phase B6.3 fix is **defensive hardening plus diagnostics**. Even
if a stale deploy or a future regression reintroduces a different
score-modification path, the engine output is now provably equal to
the Phase B6.1 scaled formula on every active queue row.

### Single-source-of-truth output guard

`enforce_score_consistency(...)` (new in
`src/macmarket_trader/recommendation/momentum_ranking.py`) is called on
every active-mode candidate inside
`DeterministicRankingEngine.rank_candidates`. It:

1. Recomputes `expected = clamp01(score_before + contribution.applied_score_delta)`.
2. Compares `observed_score` (what the loop had just produced) to
   `expected`. If the absolute difference exceeds `1e-6`, the guard
   appends `momentum_score_consistency_corrected` to the contribution
   reason codes so the operator UI can flag it.
3. Sets `score`, `score_after_momentum`, and `momentum_score_delta`
   from the guard's output so every field is consistent with the
   Phase B6.1 scaled formula.
4. Returns `realized_score_delta = expected - score_before`, which
   equals the intended delta unless the `[0, 1]` clamp truncates.

The guard is **deterministic, never raises, and never changes
approval, sizing, or routing**. It exists strictly to ensure that
`candidate.score`, `candidate.score_after_momentum`,
`contribution.applied_score_delta`, and the operator-visible
"Score delta" pill cannot disagree.

### Intended vs realized delta

Phase B6.3 makes the operator-visible distinction explicit on
every active row:

- **Intended applied delta** (`momentum_score_delta`,
  `contribution.applied_score_delta`,
  "Applied delta @ scale" column) — the scaled Phase B6.1 value
  `raw / 100 × active_delta_scale`. Always the operator-visible
  audit number on the recommendation card.
- **Realized score delta** (`momentum_realized_score_delta`,
  "Realized delta" column) — `score_after - score_before` after the
  `[0, 1]` clamp. Equal to the intended value unless the clamp
  truncates (e.g. baseline 0.97 + intended +0.07 → score 1.000,
  realized +0.03).

The frontend `MomentumImpactReview` now renders a `Realized delta`
column alongside `Applied delta @ scale` for active rows so operators
can see at a glance when the clamp engaged. The active-mode framing
copy is updated to "Applied delta @ scale is the intended scaled
Momentum score impact; Realized delta is what actually changed on the
score after the [0, 1] clamp."

### Runtime diagnostics on the status payload

`MomentumRankingStatus` exposes two read-only diagnostic fields so a
stale deploy is visible without git log forensics:

- `active_delta_formula_version`: `"scaled_v1"`. Bumped whenever the
  active-score wiring changes. Operators confirming a fresh deploy
  can read this directly from the Settings card.
- `ranking_score_consistency_guard`: `true`. Reports that the engine
  output is enforced through Phase B6.3's single-source-of-truth
  guard. Stays `true` for as long as the guard is wired in.

These fields are pure status; they never gate approval, sizing, or
order routing.

### Frontend display invariants

`apps/web/lib/momentum-impact.ts` and the impact-review component
now adhere to these rules on every render:

- `currentScore` prefers `candidate.score_after_momentum` when present
  so even a stale wire payload (where `candidate.score` drifted) lines
  up with the backend guard.
- `appliedScoreDelta` always reads `candidate.momentum_score_delta`
  (intended), then `contribution.applied_score_delta`, then the
  legacy `raw / 100 × scale` fallback. It is **never** derived from
  `currentScore - baselineScore`.
- `realizedScoreDelta` reads `candidate.momentum_realized_score_delta`
  when present, otherwise `currentScore - baselineScore`. Shadow rows
  always report `0`.
- `consistencyCorrected` is `true` when the contribution carries the
  `momentum_score_consistency_corrected` reason code, and the row
  surfaces "Score consistency corrected" near the applied-delta cell.

### What did not change

- **Raw contribution caps** remain ±20 with the Phase B1 inputs.
- **Default Momentum mode** is still `off` in every deployment that
  does not explicitly set `MACMARKET_MOMENTUM_RANKING_MODE=active` +
  `MACMARKET_ALLOW_MOMENTUM_ACTIVE_RANKING=true`.
- **Approval and paper-order behavior** remain manual. Phase B6.3
  changes no approval gate, no broker routing, no
  `BROKER_PROVIDER`/`LIVE_TRADING_ALLOWED` semantics.
- **Indicator math, parity gates, Thinkorswim fixtures** are
  untouched. `parity_required_for_active` defaults stay as they were,
  and the `thinkorswim_parity_pending` reason code still surfaces.
- **Strategy registry** is unchanged. No Phase C work landed.
- **Active delta scale env var, parsing, and defaults** are Phase
  B6.1's responsibility and were not modified.
- **`apply_momentum_score_delta`** (Phase B6.2) is unchanged; the
  Phase B6.3 guard delegates to it for the intended-delta value.

### Tests (Phase B6.3)

- `tests/test_momentum_b63_queue_consistency.py` — 21 new pytest tests
  covering: pure-helper `enforce_score_consistency` behavior across
  pass-through / legacy-bug correction / clamp-truncated realized
  delta / shadow + blocked-active + off-mode pass-through / NaN-inf
  sanitization; engine end-to-end at baselines `0.812 / 0.898 / 0.970 /
  0.500 / 1.000` with the realized-delta field present; the
  contribution payload's `applied_score_delta` equals
  `candidate.momentum_score_delta`; **real `/user/recommendations/queue`
  endpoint** integration tests via `fastapi.testclient.TestClient`
  that assert the response payload publishes the scaled `+0.07`
  intended delta and **never** the legacy `+0.20`; shadow / blocked-
  active queue rows leave the baseline score untouched; the API never
  leaks approval, sizing, or routing fields onto a queue row; and the
  `MomentumRankingStatus` payload exposes
  `active_delta_formula_version = "scaled_v1"` plus
  `ranking_score_consistency_guard = True`.
- `apps/web/lib/momentum-impact.test.ts` — 9 new tests in a
  "Phase B6.3 realized-delta + consistency-corrected wiring" block:
  realized-delta preferred from candidate field; realized tracks the
  clamp-truncated value; realized fallback to `current - baseline`;
  realized = 0 in shadow mode; `consistencyCorrected` mirrors the
  reason code; `currentScore` prefers `score_after_momentum`; the
  legacy-bug shape still surfaces intended `+0.07`; NaN/inf
  sanitization on every new field.
- `apps/web/components/recommendations/momentum-impact-review.test.tsx`
  — 5 new render tests pinning the new `Realized delta` column header,
  the realized value next to the intended applied delta for the
  clamp-truncated case (intended `0.070`, realized `0.030`), the
  consistency-corrected diagnostic note, the legacy-bug shape (intended
  stays `0.070` even when `currentScore=1.000`), the `—` placeholder
  for shadow rows, and the "no NaN/Infinity, no action language"
  regression.

### Operator checklist (Phase B6.3)

1. After deploying Phase B6.3, open Settings → Momentum ranking
   status and confirm `Active delta formula: scaled_v1` plus
   `Ranking score consistency guard: on`. This is the fastest way
   to verify the new build is actually running.
2. Open the Recommendations queue and confirm bullish active rows
   with baseline ≲ 0.93 no longer saturate to `1.000`. SPY at
   baseline `0.812` should land at `0.882`.
3. Open the Momentum Shadow Impact Review and verify each active
   row shows both the **intended** applied delta (e.g. `0.070`) and
   the **realized** delta in the new column. High-baseline rows
   (≥ 0.93) should show a smaller realized than intended because
   the clamp truncated.
4. Approval and paper-order creation remain manual. Phase B6.3 did
   not change either.
5. To revert, disable active mode via env (
   `MACMARKET_MOMENTUM_RANKING_MODE=shadow` or `off`). The guard
   itself has no environment surface — it is always-on in active
   mode and a pass-through everywhere else.

## Phase B6.4 — Last-boundary queue-response consistency

Phase B6.4 closes the deployed-but-still-broken edge: even after the
Phase B6.3 engine-level guard, the deployed `/user/recommendations/queue`
JSON still showed the legacy un-scaled delta on the wire. The selected
recommendation card and the contribution payload showed the correct
scaled `+0.07`, but the queue rows reported the legacy `+0.20`
behavior:

```
SPY  Event Continuation 0.812 → current 1.000  (applied delta 0.188)
SPY  Breakout           0.792 → current 0.992  (implies +0.200)
DIA  Breakout           0.791 → current 0.991  (implies +0.200)
XLC  Breakout           0.785 → current 0.985  (implies +0.200)
```

Phase B6.4 fixes this defensively at the **response serialization
boundary**: regardless of which engine code path produced the queue
items, the queue route now re-stamps every active-applied row from the
single source of truth (`contribution.applied_score_delta`) before
returning JSON. Any drift between the engine output and the contribution
payload is caught here, tagged on the row, and surfaced to the operator
UI.

### Backend last-boundary guard

`apply_queue_response_consistency(queue_items)` is a new helper in
`src/macmarket_trader/recommendation/momentum_ranking.py`. The queue
route in `src/macmarket_trader/api/routes/admin.py` calls it after the
engine has produced its dicts but before the route returns. For each
row whose `momentum_contribution` is active + applied, the helper:

1. Recomputes `expected_score = clamp01(score_before + contribution.applied_score_delta)`.
2. Overwrites `score`, `score_after_momentum`, `momentum_score_delta`
   (intended), `momentum_realized_score_delta` (clamp-aware), and
   `momentum_rank_mode` from the canonical Phase B6.1 math.
3. Sets a new diagnostic field `score_consistency_status`:
   - `"ok"` — the observed score equaled `expected_score`. No
     correction was needed, but the canonical fields are still
     re-stamped (so a partially-stale payload still ends up
     internally consistent).
   - `"corrected"` — the observed score differed by more than the
     Phase B6.3 tolerance. The row picks up the
     `momentum_score_consistency_corrected` reason code on the
     contribution as well.
4. Pass-through behavior for shadow / blocked-active / off / disabled
   contributions: no score modification; rows with a contribution
   payload still get `score_consistency_status="ok"` for diagnostic
   completeness.

The guard also aligns the engine's separate `top_candidates`,
`watchlist_only`, and `no_trade` dict buckets so a frontend that reads
any of them sees the same corrected score.

### Frontend display invariants (tightened)

`apps/web/lib/momentum-impact.ts` swaps the Phase B6.2/B6.3 fallback
order so that `contribution.applied_score_delta` is now the **first
choice** for the intended applied delta on every active row:

1. `contribution.applied_score_delta` (canonical Phase B6.1 scaled value)
2. `candidate.momentum_score_delta` (may carry legacy unscaled value on
   stale payloads)
3. `raw / 100 × active_delta_scale` (last-resort recomputation)

The impact-review component renders the new
`score_consistency_status="corrected"` tag the same way as the Phase
B6.3 reason code — either signal surfaces the
"Score consistency corrected" diagnostic next to the Applied delta
cell. This guarantees that even if a legacy-shaped wire payload
arrives (`current=1.000`, `momentum_score_delta=0.188` while
`contribution.applied_score_delta=0.07`), the row still renders the
correct intended `0.070` and visibly flags the inconsistency.

### Status diagnostic

`MomentumRankingStatus` gains a third Phase B6 diagnostic:

- `queue_response_consistency_guard`: `true`. Reports that the queue
  API route is running its output through
  `apply_queue_response_consistency` before returning. Combined with
  `active_delta_formula_version: "scaled_v1"` (B6.3) and
  `ranking_score_consistency_guard: true` (B6.3), operators can verify
  the full Phase B6 stack from the Settings card alone.

### What did not change

- **Raw contribution caps** remain ±20 with the Phase B1 inputs.
- **Default Momentum mode** is still `off` everywhere except deployments
  that explicitly set `MACMARKET_MOMENTUM_RANKING_MODE=active` +
  `MACMARKET_ALLOW_MOMENTUM_ACTIVE_RANKING=true`.
- **Approval and paper-order behavior** remain manual.
- **Indicator math, parity gates, Thinkorswim fixtures** are untouched.
- **Strategy registry** is unchanged. No Phase C work landed.
- **`apply_momentum_score_delta`** (B6.2) and `enforce_score_consistency`
  (B6.3) are unchanged; the Phase B6.4 helper composes
  `enforce_score_consistency` rather than reimplementing the math.

### Tests (Phase B6.4)

- `tests/test_momentum_b64_queue_response_guard.py` — 17 new pytest
  tests covering: pure-helper `apply_queue_response_consistency`
  behavior (legacy-bug correction, already-ok pass-through,
  shadow/blocked/off pass-through, clamp-truncated realized delta,
  empty queue, missing contribution, malformed contribution); **real
  `/user/recommendations/queue` API** integration tests via
  `fastapi.testclient.TestClient` with the ranking engine stubbed to
  return the deployed-bug payload shape directly (so the test fails on
  the exact deployed wire shape), at baselines 0.812 / 0.792 / 0.898 /
  0.970; negative raw contribution scaled correctly via the guard; the
  payload never leaks approval / order / routing fields; the
  `top_candidates` bucket stays aligned with the `queue` bucket after
  correction; the multi-row deployed scenario (SPY EV Continuation +
  SPY Breakout + DIA Breakout + XLC Breakout) all corrected; the status
  payload exposes `queue_response_consistency_guard=True` alongside the
  Phase B6.3 diagnostics.
- `apps/web/lib/momentum-impact.test.ts` — 5 new tests in a
  "Phase B6.4 legacy-payload regression + score_consistency_status"
  block: contribution-delta preference over candidate field;
  `consistencyCorrected` fires from `score_consistency_status` alone;
  `consistencyCorrected` fires from reason code alone;
  `consistencyCorrected` stays false when status is `"ok"`; the
  intended-delta cell never derives from `current_score - baseline`
  when the contribution payload is present. The Phase B6.2 preference
  test was updated to assert the new B6.4 preference order.
- `apps/web/components/recommendations/momentum-impact-review.test.tsx`
  — 3 new render tests: the legacy-bug payload (current 1.000 + legacy
  0.188 on candidate) still renders the Applied delta cell as `0.070`;
  the `score_consistency_status="corrected"` tag alone surfaces the
  diagnostic note; the `"ok"` status leaves the note hidden.

### Operator checklist (Phase B6.4)

1. After deploying Phase B6.4, open Settings → Momentum ranking
   status and confirm `Queue response consistency guard: on`
   alongside the Phase B6.3 `Ranking score consistency guard: on`
   and `Active delta formula: scaled_v1`.
2. Open the Recommendations queue and confirm SPY @ 0.812 baseline
   now lands at score `0.882`, not `1.000`. Other rows that showed
   the legacy `+0.20` shape (`0.792 → 0.992`, `0.791 → 0.991`,
   `0.785 → 0.985`) should all now reflect `+0.07` instead.
3. Active rows that the route corrected display
   "Score consistency corrected" under their Applied delta cell.
   That diagnostic should disappear within one or two queue refresh
   cycles as the upstream engine catches up.
4. Approval and paper-order creation remain manual. Phase B6.4 did
   not change either.
5. To revert, disable active mode via env. The guard itself has no
   environment surface — it is always-on in active mode and a
   pass-through everywhere else.

## Phase B7 — Active Momentum Trial Journal / Comparison Report

Phase B7 adds an operator-only **evidence capture** layer on top of the
Recommendations queue. It is the first surface that lets an operator
freeze the current Momentum ranking picture — modes, deltas, warnings,
parity status, score-consistency corrections — into a deterministic
snapshot that can be saved locally, exported as Markdown or JSON, and
compared later against paper or research outcomes.

It is **display- and export-only**: no backend persistence, no DB
migration, no LLM, no ranking math change, no queue-sorting change, and
no approval, promote, save, paper-order, settle, replay, or options-
preview behavior change.

### Purpose

Operators need a way to write down what Momentum Intelligence was
showing them when they made a decision, so a later comparison can
distinguish "the ranking layer caused the outcome" from "discretionary
sizing or external news caused the outcome". Phase B7 is that capture
layer. It is not a trade-approval tool, not a sizing tool, not an order-
routing tool, and not a backtester — the deterministic guardrail copy is
rendered on every surface that emits a snapshot.

### Data source

| Source | What is read |
|---|---|
| In-memory `queue` rows already loaded by `app/(console)/recommendations/page.tsx` | rank, symbol, strategy, score, expected_rr, confidence, `score_before_momentum`, `score_after_momentum`, `momentum_score_delta`, `momentum_realized_score_delta`, `score_consistency_status`, `momentum_contribution`, `risk_calendar` |
| `apps/web/lib/momentum-impact.ts` | `buildMomentumImpactRows` and `summarizeMomentumImpact` are reused verbatim — the journal does **not** recompute Momentum math |
| `apps/web/lib/momentum-ranking.ts` | `getMomentumContributionReasonLabels`, `normalizeMomentumRankingMode`, `momentumRankingModeLabel` for label rendering only |

No new endpoint is called. No extra fetch happens. No payload field is
recomputed. If the queue is empty, the journal renders an empty state
with the capture button disabled.

### Surfaces

| Surface | File |
|---|---|
| Pure helpers | `apps/web/lib/momentum-trial-journal.ts` (`buildMomentumTrialSnapshot`, `summarizeMomentumTrialSnapshot`, `topMomentumTrialMovers`, `topMomentumTrialWarnings`, `rankMovementBuckets`, `classifyMomentumTrialCandidate`, `momentumTrialWarnings`, `sanitizeMomentumTrialNote`, `formatMomentumTrialTimestamp`, `validateMomentumTrialSnapshot`, `buildMomentumTrialJson`, `buildMomentumTrialMarkdown`, `MOMENTUM_TRIAL_JOURNAL_VERSION`, `MOMENTUM_TRIAL_JOURNAL_DETERMINISTIC_NOTE`). |
| Reusable component | `apps/web/components/recommendations/momentum-trial-journal.tsx` (`<MomentumTrialJournal candidates universeSymbols title compact initialSnapshot persistLatest />` plus the presentational `<MomentumTrialJournalView snapshot … />`). |
| Recommendations integration | `apps/web/app/(console)/recommendations/page.tsx` renders `<MomentumTrialJournal candidates={queue} />` directly below `<MomentumImpactReview>`. No new fetch, no change to queue ordering, no change to approval/promote/paper-order/replay behavior. |
| Settings pointer | `apps/web/components/recommendations/momentum-ranking-status-card.tsx` adds a one-line "Capture trial evidence in Recommendations." pointer — link only, no new navigation. |

### Snapshot shape

`MomentumTrialSnapshot` is the canonical export envelope. Each captured
candidate carries:

- `rank`, `symbol`, `strategy`, `mode`
- `classification` (`active_positive` / `active_negative` / `active_zero` /
  `shadow_positive` / `shadow_negative` / `shadow_zero` / `off` /
  `blocked_active` / `contribution_missing`)
- `current_score`, `baseline_score`, `active_score` (all clamped to `[0, 1]`)
- `raw_contribution` (raw ±20 ranking-score units)
- `applied_delta` (intended, in `[0, 1]` units), `realized_delta`
  (post-clamp realized, `0` when not active)
- `total_score`, `total_label`, `trend_score`, `momo_score`
- `reason_codes`, `reason_labels`, `warning_flags`
- `score_consistency_status`, `risk_calendar_decision`,
  `risk_calendar_level`, `expected_rr`, `confidence`

`MomentumTrialSummary` aggregates: candidate / active / shadow / off /
parity-pending / direction-unknown / warning / positive / negative /
zero contribution / consistency-corrected / contribution-missing /
blocked-active counts; `net_estimated_score_delta`; `reason_code_counts`;
the requested + effective + observed ranking modes; and the
`active_delta_scale` actually observed in the queue payload.

`schema_version` is pinned to `phase_b7.v1` and emitted in both the
snapshot and the export payload so future versions can co-exist without
silently shifting field meanings.

### Operator note safety

`sanitizeMomentumTrialNote` strips and `[redacted]`s a forbidden phrase
list (`buy now`, `sell now`, `enter now`, `short now`, `auto approve`,
`auto-approve`, `route order`, `place order`, `submit order`), collapses
whitespace, and length-caps at 1200 characters. The journal can never
publish trade-direction action language even through an operator note.

### Local / export-only behavior

- The component persists the latest snapshot to `localStorage` under
  `macmarket.momentumTrial.latest` (controllable via `persistLatest`).
  Tests pass `persistLatest={false}` so they never depend on a browser.
- Snapshots are user-driven: nothing is captured automatically — the
  operator must click **Capture Momentum Trial Snapshot**.
- The component exposes **Copy Markdown**, **Download Markdown**,
  **Download JSON**, and **Clear snapshot** actions. Downloads use a
  client-side `Blob` + temporary `<a download>`; there is no upload, no
  backend write, and no DB row.
- `validateMomentumTrialSnapshot` rejects unknown schema versions when
  re-hydrating from `localStorage`.

### Deterministic guardrail copy

Every snapshot, every Markdown export, and every JSON export carries
the canonical operator note:

> *This trial journal records Momentum ranking evidence only. It does
> not approve, reject, size, or route trades.*

A `momentum-integration` guard test confirms the string appears in the
helper and that no forbidden action language appears in either the
helper module or the component module.

### Suggested operator workflow

1. Open `/recommendations` and generate or refresh the active queue so
   the rows on screen are the picture you want to record.
2. Scroll to **Active Momentum Trial Journal** and press
   **Capture Momentum Trial Snapshot**. The summary cards, top-candidate
   table, and warnings table populate from the rows already loaded.
3. Add a short **Operator note** (optional). Action language is
   redacted and a warning hint appears if the sanitizer had to rewrite
   anything.
4. Export with **Download Markdown** or **Download JSON** for archival;
   use **Copy Markdown** to paste into another tool.
5. Later, compare the snapshot side-by-side against the paper-order
   result, the replay run, or external research notes. The snapshot's
   `schema_version`, `generated_at`, mode summary, and reason-code
   counts make it possible to align after the fact without retrofitting
   the live queue.

### What Phase B7 does NOT do

- **No ranking math change.** `build_momentum_ranking_contribution`,
  `DeterministicRankingEngine`, Phase B1 bounded caps, Phase B6 safety
  guard, Phase B6.1–B6.4 wiring, and the active-delta formula are
  byte-identical.
- **No queue sorting change.** Live queue ordering is preserved; the
  snapshot's "top candidates" view is a per-snapshot label only.
- **No approval, promote, save, paper-order, settle, replay, or
  options-preview behavior change.**
- **No backend mutation.** No new HTTP endpoint, no DB row, no migration.
- **No LLM call.** The helpers are deterministic and side-effect-free.
- **No strategy families.** Phase C remains gated and separate.
- **No live routing or expiration-settlement work.** Out of scope for
  the Momentum Intelligence layer.

### Tests (Phase B7)

- `apps/web/lib/momentum-trial-journal.test.ts` — pure-helper suite
  covering snapshot construction from active/shadow/off/missing
  candidates, parity / direction-unknown / consistency-corrected /
  blocked-active counts, NaN/Infinity sanitization, operator-note
  sanitization, top-mover and top-warning ordering, movement-bucket
  classification, JSON/Markdown export round-trips, schema validation,
  and a forbidden-language guard on Markdown + JSON output.
- `apps/web/components/recommendations/momentum-trial-journal.test.tsx`
  — render suite covering empty state, capture-disabled state with no
  candidates, captured-summary rendering via `initialSnapshot`,
  copy / download / clear button surface, warning-table presence and
  compact-mode hiding, operator-note display, deterministic-guardrail
  copy in every branch, and a no-action-language guard on rendered
  HTML.
- `apps/web/lib/momentum-integration.test.ts` — strengthened with
  Phase B7 guards: Recommendations page imports
  `<MomentumTrialJournal>` and passes the existing `queue`, the helper
  + component stay out of order / paper-position / paper-trade /
  options-paper / replay-preview routes and out of the order /
  recommendation helper files, the helper carries the deterministic
  operator-evidence guardrail copy, and neither surface emits
  forbidden trade-approval / order-routing language.

### Still pending

- **Thinkorswim fixture parity.** Phase B7 surfaces parity-pending and
  consistency-corrected counts in the snapshot summary, but the
  `parity_required_for_active` flag still depends on dropping
  measured fixtures into `tests/fixtures/thinkorswim_momentum/` per
  the parity-fixtures plan above.
- **Phase C strategy families.** Dedicated momentum-aware strategy
  families remain a separate, explicitly-gated phase. Phase B7 does
  not introduce, implement, or schedule any strategy-family code.

## Phase B7.1 — trial journal polish

Phase B7.1 is a **frontend-only polish** of the Phase B7 trial journal.
It does not change Momentum ranking math, queue sorting, recommendation
approval, paper-order behavior, or backend scoring. It does not add any
backend route, DB column, migration, LLM call, or strategy family. The
helper / component / tests / docs are the entire surface.

### What changed

1. **Deterministic guardrail note renders exactly once.** Previously the
   sentence "_This trial journal records Momentum ranking evidence only.
   It does not approve, reject, size, or route trades._" was rendered
   twice — once at the bottom of `MomentumTrialJournalView` and again at
   the bottom of the outer `MomentumTrialJournal` container. The view
   no longer renders the note; the container is the canonical render
   site. Container-level tests assert exactly one occurrence in the
   empty state and exactly one occurrence with a captured snapshot.
2. **Trade warnings vs operational caveats are separated.** Phase B7
   surfaced a single "Warnings" count and table that mixed real
   trade-direction signals (no-trade, reversal, bearish total-label
   contradiction) with operational data-quality flags (parity pending,
   derived higher timeframe, score-consistency corrected, blocked
   active). Phase B7.1 splits them:
   - `MomentumTrialTradeWarningFlag` = `"no_trade_warning" |
     "reversal_warning" | "bear_total_label_contradiction"`.
   - `MomentumTrialOperationalCaveatFlag` = `"score_consistency_corrected" |
     "parity_pending" | "derived_higher_timeframe" | "direction_unknown" |
     "active_mode_blocked_by_safety_guard"`.
   - The union enum `MomentumTrialWarningFlag` is preserved for
     back-compat.
   - `partitionWarningFlags`, `isTradeWarningFlag`,
     `isOperationalCaveatFlag` are exported helpers.
3. **Snapshot summary exposes the new counts.** `trade_warning_count`,
   `operational_caveat_count`, and `derived_higher_timeframe_count` join
   the existing `parity_pending_count`, `direction_unknown_count`, and
   `score_consistency_corrected_count`. The legacy `warning_count` is
   re-aimed at the trade-warning count only and is also exposed via the
   clearer `trade_warning_count` alias.
4. **Snapshot carries partitioned candidate lists.**
   `trade_warning_candidates` returns rows with at least one
   trade-warning flag; `operational_caveat_candidates` returns rows with
   at least one operational caveat. The union `warning_candidates` is
   preserved for back-compat.
5. **Top-candidates table now has separate "Trade warnings" and
   "Operational caveats / reasons" cells.** Trade warnings render with
   the `bad` tone; operational caveats render with the `warn` tone;
   reason labels render neutrally.
6. **The single "Warnings" section is replaced by two sections.**
   Both sections always emit, so operators see the snapshot explicitly
   answered each question:
   - **Trade warnings** — empty state reads "No trade warnings
     captured." in both Markdown and the UI.
   - **Operational caveats** — empty state reads "No operational caveats
     captured." Above the table, an explainer renders: "Operational
     caveats describe data-quality, parity, and guardrail context. They
     are not trade-direction warnings."
7. **Universe/captured-symbol labeling is honest.** The snapshot now
   carries `universe_kind: "evaluated" | "captured"`:
   - `"evaluated"` when the caller passes `universeSymbols` (e.g. the
     Recommendations page passes its parsed manual-symbol input). The
     UI heading and Markdown bullet read **"Evaluated universe: …"**.
   - `"captured"` when no universe is passed and the snapshot only
     knows the symbols it captured from the candidate rows. The UI
     heading and Markdown bullet read **"Captured symbols: …"**.
   The helper `momentumTrialUniverseLabel(kind)` returns the right
   label for both UI and exports.
8. **Recommendations page passes the evaluated universe.**
   `apps/web/app/(console)/recommendations/page.tsx` now mounts the
   journal as `<MomentumTrialJournal candidates={queue}
   universeSymbols={parsedSymbols.symbols} />`. No new fetch and no
   change to queue submission, approval, promotion, paper-order, or
   options flow.
9. **Schema version bumped.** `MOMENTUM_TRIAL_JOURNAL_VERSION` moves
   from `"phase_b7.v1"` to `"phase_b7_1.v1"`. Any operator's cached
   localStorage snapshot from Phase B7 is invalidated and the operator
   simply re-captures — there is no migration path because the
   journal is local/export-only.

### Severity ordering

`compareByWarningSeverity` keeps trade warnings strictly above
operational caveats: `no_trade > reversal > bear-contradiction >
score-consistency-corrected > blocked-active > derived-HTF >
parity-pending > direction-unknown`. This drives both
`topMomentumTrialTradeWarnings` and `topMomentumTrialOperationalCaveats`.

### Markdown export sections (Phase B7.1)

Always emitted, in order:

1. `## Summary` — counts include `Trade warnings`, `Operational
   caveats`, `Parity pending`, `Derived higher timeframe`, `Direction
   unknown`, `Score consistency corrected`, `Contribution missing`,
   `Blocked active (safety guard)`, and `Net estimated score delta`.
2. `## Top candidates` — split "Trade warnings" + "Operational
   caveats / reasons" columns.
3. `## Trade warnings` — table of rows with trade-warning flags, or
   `_No trade warnings captured._`.
4. `## Operational caveats` — explainer + table of rows with caveat
   flags, or `_No operational caveats captured._`.
5. `## Operator note` — only when an operator note is present.
6. Trailing line: the deterministic guardrail copy.

### JSON export (Phase B7.1)

The exported `MomentumTrialExportPayload.snapshot` now carries
`universe_kind`, `trade_warning_candidates`,
`operational_caveat_candidates`, and the new summary counts
(`trade_warning_count`, `operational_caveat_count`,
`derived_higher_timeframe_count`). Existing fields are unchanged.

### What Phase B7.1 does NOT do

- **No ranking math change.** `build_momentum_ranking_contribution`,
  `DeterministicRankingEngine`, Phase B1 / B6 / B6.x wiring, and the
  active-delta formula are byte-identical.
- **No queue sorting change.**
- **No approval, promote, save, paper-order, settle, replay, or
  options-preview behavior change.**
- **No backend mutation.** No new endpoint, no DB row, no migration.
- **No LLM call.**
- **No strategy families.** Phase C remains gated and separate.
- **No active-mode env behavior change.**

### Tests (Phase B7.1)

- `apps/web/lib/momentum-trial-journal.test.ts` — adds the
  "Phase B7.1 — trade warnings vs operational caveats" suite. Coverage:
  parity-pending alone does not increment `trade_warning_count` but
  does increment `operational_caveat_count` + `parity_pending_count`;
  derived higher timeframe increments `operational_caveat_count` +
  `derived_higher_timeframe_count`; no-trade and reversal warnings
  increment `trade_warning_count`; bearish total-label contradiction
  increments `trade_warning_count`; score-consistency-corrected and
  active-mode safety-guard blocks increment operational caveat counts
  only; `universe_kind` reads `"evaluated"` when `universeSymbols` is
  passed and `"captured"` otherwise; `partitionWarningFlags`,
  `isTradeWarningFlag`, and `isOperationalCaveatFlag` classify the full
  union; `topMomentumTrialTradeWarnings` excludes parity-only rows while
  `topMomentumTrialOperationalCaveats` returns them; the
  `momentumTrialTradeWarnings` / `momentumTrialOperationalCaveats`
  accessors mirror the partition; the JSON export carries the new
  counts and `universe_kind`. The Markdown suite also asserts: the
  "Trade warnings" + "Operational caveats" sections always emit; the
  empty-state copy is correct; reversal-only rows are routed to the
  Trade warnings section; parity-only rows are routed to the
  Operational caveats section; the universe-kind heading switches
  correctly; the new summary counts appear in the body; and the
  deterministic guardrail copy appears exactly once.
- `apps/web/components/recommendations/momentum-trial-journal.test.tsx`
  — adds "Phase B7.1 deterministic-note + universe" suite asserting the
  guardrail copy appears exactly once in both empty and captured
  states, and that `universeSymbols` flows end-to-end. View-level tests
  now assert: new summary card labels render (`Trade warnings`,
  `Operational caveats`, `Positive / negative / zero contribution`);
  Trade warnings + Operational caveats tables render with the right
  testids; the "No trade warnings captured." message shows when only
  parity caveats exist; the "No operational caveats captured." message
  shows when only trade warnings exist; compact mode hides both tables;
  the universe block toggles between `Captured symbols` and
  `Evaluated universe` based on `universe_kind`; and the view does NOT
  render the deterministic note (the container owns that copy).
- `apps/web/lib/momentum-integration.test.ts` — strengthens the B7
  guards: the Recommendations page now passes both `candidates={queue}`
  and `universeSymbols={parsedSymbols.symbols}`; both surfaces carry
  the trade-warning vs operational-caveat exports and copy; the view
  no longer renders the standalone deterministic-note testid; the
  helper/component remain isolated from order, paper-position,
  paper-trade, options-paper, and replay-preview routes; and no
  forbidden trade-direction / order-routing literals appear in either
  source file.

### Still pending (carried forward from Phase B7)

- **Thinkorswim fixture parity.** The summary now reports
  `parity_pending_count`, `derived_higher_timeframe_count`, and
  `score_consistency_corrected_count` separately, but flipping
  `parity_required_for_active` to `True` still depends on dropping
  measured fixtures into `tests/fixtures/thinkorswim_momentum/`.
- **Phase C strategy families.** Dedicated momentum-aware strategy
  families remain a separate, explicitly-gated phase. Phase B7.1 does
  not introduce, implement, or schedule any strategy-family code.

## Phase C2.1 — link B7/B8 trial evidence into the C2 bundle

Phase C2.1 wires the existing Phase B7 trial-journal snapshot and the
Phase B8 outcome review into the Phase C2 preview-evidence bundle.
The C2 panel can now show whether the captured B8 evidence belongs to
the current queue, the exported Markdown / JSON carry the linked B8
metadata, and the previously-visible duplicate guardrail copy under
the C1 panel is cleaned up.

Still frontend-only and research-only. No backend write, no DB row,
no migration, no LLM call. No Phase C activation. No ranking, queue
sorting, approval, paper-order, replay, or options-preview behavior
change.

### Linkage model

- `computeMomentumQueueSignature(rows)` (exported from
  `apps/web/lib/true-momentum-preview-evidence.ts`) builds a stable
  `rank::symbol::strategy` signature, sorted, from any iterable of
  rows with those fields. Works for both live `QueueCandidate[]` and
  for `MomentumTrialSnapshot.candidates`.
- The C2 evidence panel rehydrates the latest B7 snapshot and B8
  outcome review from `localStorage` (read-only) using the canonical
  storage keys `macmarket.momentumTrial.latest` and
  `macmarket.momentumTrial.outcome.latest`.
- The C2 builder then computes:
  - `b8_snapshot_link_status` — `linked` when the snapshot's
    signature matches the live queue, `mismatch` when it differs, and
    `missing` when no snapshot is available.
  - `b8_outcome_review_link_status` — same matching plus a `partial`
    status when the outcome review signature matches but every
    candidate is still tagged `unclear`.
  - `b8_snapshot_generated_at`, `b8_outcome_generated_at`,
    `b8_snapshot_candidate_count`, `b8_outcome_reviewed_count`,
    `b8_outcome_summary` (compact per-tag counts),
    `linked_b8_snapshot_schema_version`,
    `linked_b8_outcome_schema_version`, and a human-readable
    `b8_link_warning`.

### UI changes

- B8 snapshot + outcome-review badges now show the resolved status
  string (`linked` / `missing` / `mismatch` / `partial`) and tone the
  badge accordingly.
- A short, operator-readable copy line summarizes the snapshot +
  outcome state directly under the summary cards
  ("Linked to current Momentum Trial Journal snapshot…",
  "A B8 snapshot exists, but it belongs to a different queue.", etc.).
- When linked, the snapshot timestamp + compact outcome counts
  (worked / missed / too aggressive / good warning / false warning /
  needs ToS parity / unclear) are surfaced inline.
- The C1 preview panel suppresses its trailing deterministic note +
  "Still pending" caveat whenever the C2 evidence panel is mounted
  (i.e. when previews exist). The C2 panel is the canonical owner of
  both lines while it is visible; this removes the previously-visible
  duplicate guardrail copy.
- Capture / export / clear buttons stay enabled regardless of B8
  state.

### Markdown / JSON export

The Markdown export adds a "## Linked B8 Trial Evidence" section
between the header bullets and the existing "## Summary" section,
listing snapshot + outcome status, timestamps, candidate / reviewed
counts, per-tag outcome counts, and any `b8_link_warning`. When no B8
evidence is linked the section explicitly states "missing".

The JSON export carries every new bundle field
(`b8_snapshot_link_status`, `b8_outcome_review_link_status`,
timestamps, counts, compact outcome summary, schema versions,
`b8_link_warning`).

### Still pending

- Accumulated B8 outcome evidence corpus.
- Real Thinkorswim fixture parity.
- Operator authorization before any active Phase C.

## Phase C2 — True Momentum research-preview evidence bundle

Phase C2 wraps the Phase C1 classification into a deterministic
operator evidence bundle. The bundle is built from the already-loaded
Recommendations queue and the existing C1 preview result; operators
overlay a global research conclusion, per-family notes, and per-row
tags / notes (`research_candidate`, `watchlist_only`,
`needs_tos_parity_check`, `needs_b8_outcome_evidence`, `too_noisy`,
`defer`) and export the result as Markdown / JSON for review against
Phase B8 outcome evidence.

It is **frontend-only and local/export-only**. No backend write, no DB
row, no migration, no LLM call. No active Phase C activation. No
ranking math change, no queue sorting change, no approval / promote /
save / paper-order / settle / replay / options-preview behavior
change.

### Surfaces

- Pure helpers: `apps/web/lib/true-momentum-preview-evidence.ts`.
- Reusable component:
  `apps/web/components/recommendations/true-momentum-preview-evidence-panel.tsx`.
- Mounted automatically by the Phase C1 preview panel whenever
  Phase C1 produced at least one preview row. The Recommendations page
  passes `universeSymbols={parsedSymbols.symbols}` so the bundle can
  label "Evaluated universe" rather than "Captured symbols".
- LocalStorage: `macmarket.trueMomentumPreviewEvidence.latest`, keyed
  by the queue signature so stale caches are discarded.

### Bundle shape (`phase_c2.v1`)

- `schema_version` / `generated_at` / `preview_phase` ("C2") /
  `implementation_status` ("research_preview_evidence")
- `ranking_mode` / `active_delta_scale`
- `evaluated_universe` + `universe_kind` ("evaluated" / "captured")
- `candidate_count` / `preview_count`
- `family_counts` + flat `continuation_count` / `pullback_count` /
  `reversal_watch_count`
- `parity_pending_count` / `derived_higher_timeframe_count` /
  `trade_warning_count` / `operational_caveat_count` /
  `score_consistency_corrected_count`
- `b8_snapshot_present` / `b8_outcome_review_present` (presence flags
  only — no shared mutable state)
- `family_summaries` (per-family per-strength counts + candidate
  arrays)
- `preview_candidates` (every matched Phase C1 row re-framed for
  archival)
- `operator_review` (`global_conclusion`, `family_notes`,
  `candidate_notes`, `review_tags`, `authored_at`)
- `deterministic_note` (research-only guardrail copy)

### Recommended workflow

1. Run the active Momentum queue.
2. Review the Phase C1 family preview panel.
3. Capture a Phase C2 preview evidence bundle.
4. Capture a Phase B7 / B8 trial snapshot + outcome review for the
   same session.
5. Compare exported Phase C2 evidence + Phase B8 outcomes before any
   Phase C3 / active Phase C authorization.

### Tests

- `apps/web/lib/true-momentum-preview-evidence.test.ts` — pure-helper
  suite (bundle build, family/strength/caveat counts, universe-kind
  labeling, B8 presence flags, sanitization, partition, top-evidence
  ordering, Markdown/JSON export, validation, no-action-language
  guard).
- `apps/web/components/recommendations/true-momentum-preview-evidence-panel.test.tsx`
  — render suite (empty state, family sections, summary cards,
  capture / export / clear buttons, global conclusion textarea, per-
  family notes, review-tag buttons, deterministic note + still-pending
  caveat copy, no forbidden trade-action / queue-generation /
  approval / order-routing language).
- `apps/web/lib/momentum-integration.test.ts` — Phase C2 isolation
  guard suite (lib + panel exist; C1 panel mounts the evidence panel
  only inside the Recommendations preview flow; surfaces stay out of
  order / paper / replay / options-paper routes and order /
  recommendation helpers; no forbidden trade-action / queue-generation
  / approval / order-routing language).

### Still pending

- Accumulated B8 outcome evidence corpus.
- Real Thinkorswim fixture parity.
- Operator authorization before any active Phase C.

## Phase C1 — True Momentum strategy-family research preview

Phase C1 is a **read-only research-preview classifier** that labels
the already-loaded Recommendations queue into the three planned True
Momentum families (continuation, pullback, reversal / weakening watch)
documented in [`true-momentum-strategy-families.md`](true-momentum-strategy-families.md).

It does not generate new queue candidates, does not change ranking
math, queue sorting, approval, promote, save, paper-order, settle,
replay, or options-preview behavior, does not auto-approve / size /
route trades, does not call an LLM, and does not require any database
migration. Phase C0 scaffolding remains in place; C1 just adds a
classifier on top.

### Enabling Phase C1

```env
MACMARKET_TRUE_MOMENTUM_STRATEGY_MODE=research_preview
MACMARKET_ALLOW_TRUE_MOMENTUM_STRATEGY_FAMILIES=true
```

Both env vars are required. With the defaults (mode `disabled` and
guard `false`) the Phase C1 panel renders a clear "disabled" empty
state with the env-var instructions and no preview rows.
`MACMARKET_TRUE_MOMENTUM_STRATEGY_MODE=active` is still **reserved**:
even with the guard truthy, active degrades to `research_preview` with
the `true_momentum_strategy_active_mode_not_implemented` reason code.

### Classification

Precedence is **reversal_watch > pullback > continuation** — exactly
one preview row per candidate. Each row carries
`non_actionable: true`, the `match_strength` tag
(`strong` / `moderate` / `watch` / `blocked`), the source candidate's
Momentum totals + flags, and any operational caveats
(`thinkorswim_parity_pending`, `derived_higher_timeframe`,
`direction_unknown`, `active_mode_blocked_by_safety_guard`,
`score_consistency_corrected`). No preview row ever includes entry,
stop, target, size, approval, or order fields.

### Surfaces

- Backend: `evaluate_true_momentum_strategy_preview(settings, *,
  candidates)` in
  `src/macmarket_trader/recommendation/true_momentum_strategy_families.py`.
- Read-only endpoint: `POST /user/true-momentum-strategy-families/preview`
  (approved-user auth; no DB writes, no provider / market-data /
  LLM calls).
- Pydantic payloads:
  `TrueMomentumStrategyPreviewCandidatePayload`,
  `TrueMomentumStrategyPreviewSummaryPayload`,
  `TrueMomentumStrategyPreviewResultPayload`,
  `TrueMomentumStrategyPreviewRequest`.
- Frontend helper: `apps/web/lib/true-momentum-strategy-preview.ts`.
- Frontend panel:
  `apps/web/components/recommendations/true-momentum-strategy-preview-panel.tsx`,
  mounted on the Recommendations page directly after the Momentum
  Trial Journal.

### Still pending

- Accumulated B8 outcome evidence corpus.
- Real Thinkorswim fixture parity.
- Operator authorization before any active Phase C.

## Phase B8 — Active Momentum Trial Outcome Review

Phase B8 is the **operator-side evidence loop** for the Phase B7 trial
journal. After a session, the operator opens a captured snapshot and
tags each candidate with the observed outcome — did Momentum actually
help, did it over-weight a name, did it miss something, did its warning
turn out to be useful or false, does this still need a Thinkorswim
parity spot-check. The review is then exported to Markdown / JSON and
stored locally so a later cohort can compare the tagged outcomes
against paper or research results.

It is **local/export-only**: no backend persistence, no DB row, no DB
migration, no LLM call, no ranking math change, no queue-sorting
change, and no approval / promote / save / paper-order / settle /
replay / options-preview behavior change. Phase C True Momentum
strategy families remain inactive.

### Purpose

Phase B7 captures a deterministic snapshot of what Momentum showed at
the moment of the decision. Phase B8 lets the operator overlay the
later-observed outcome on that same snapshot, producing an archivable
record that pairs *prior context* with *measured result*. Aggregating
these outcome reviews across an active-trial cohort is what Phase C1
will use to decide whether True Momentum strategy families should be
activated, and on which sectors.

### Outcome tags

| Tag | Meaning |
|---|---|
| `worked` | Momentum elevated this name and the move played out cleanly. |
| `missed` | Momentum did not flag this name but the move clearly belonged in the queue. |
| `too_aggressive` | Momentum lifted this name too far / too early — operator over-relied. |
| `good_warning` | A no-trade / reversal / contradiction warning correctly held us out. |
| `false_warning` | A warning fired but the name actually behaved fine. |
| `watchlist_only` | Right context, wrong timing — keep on the watchlist. |
| `needs_tos_parity_check` | Score / scoring differed from the Thinkorswim view; flag for parity review. |
| `ignored` | Operator chose not to act on this candidate at all. |
| `unclear` | Default; outcome was not visible enough to tag yet. |

### Surfaces

| Surface | File |
|---|---|
| Pure helpers | `apps/web/lib/momentum-trial-outcomes.ts` (`buildMomentumTrialOutcomeReview`, `candidateOutcomeDefaults`, `summarizeMomentumTrialOutcomes`, `outcomeReasonCounts`, `sanitizeMomentumOutcomeNote`, `validateMomentumTrialOutcomeReview`, `buildMomentumOutcomeMarkdown`, `buildMomentumOutcomeJson`, `outcomeTagLabel`, `outcomeTagTone`, `momentumCandidateOutcomeKey`, `MOMENTUM_TRIAL_OUTCOME_REVIEW_VERSION`, `MOMENTUM_TRIAL_OUTCOME_DETERMINISTIC_NOTE`, `MOMENTUM_TRIAL_OUTCOME_STORAGE_KEY`, `MOMENTUM_TRIAL_OUTCOME_TAGS`). |
| Reusable component | `apps/web/components/recommendations/momentum-trial-outcome-review.tsx` (`<MomentumTrialOutcomeReviewPanel snapshot persistLatest initialOutcomes initialGlobalConclusion />`). |
| Trial-journal integration | `apps/web/components/recommendations/momentum-trial-journal.tsx` mounts `<MomentumTrialOutcomeReviewPanel snapshot={snapshot} persistLatest={persistLatest} />` directly after `MomentumTrialJournalView` whenever a snapshot is captured. The panel is hidden in the empty state. |
| LocalStorage | `macmarket.momentumTrial.outcome.latest` — keyed by the source snapshot's `generated_at`. A cached payload is re-hydrated only when it matches the current snapshot timestamp; mismatched payloads are discarded silently. |

### Review shape

`MomentumTrialOutcomeReview` is the canonical export envelope. It bundles:

- `schema_version` pinned to `phase_b8.v1`,
- `generated_at` (review timestamp, distinct from the snapshot's),
- the full source `snapshot` (so the export stands alone),
- the optional operator `global_conclusion` text + authored timestamp,
- per-candidate `candidate_outcomes` (rank, symbol, strategy, tag,
  note, reason codes, trade-warning flags, operational-caveat flags),
- a per-tag `summary` plus an aggregated `reason_code_counts`.

### Markdown export sections

Always emitted, in order:

1. Snapshot timestamp / review timestamp / schema version.
2. Requested + effective mode.
3. Active delta scale.
4. `Evaluated universe` or `Captured symbols` (mirrors the Phase B7.1
   universe-kind labeling).
5. Snapshot operator note (only when present).
6. `## Global outcome conclusion` — operator's session-level recap or
   `_No global conclusion recorded._`.
7. `## Outcome summary` — counts per tag.
8. `## Candidate outcomes` — rank / symbol / strategy / baseline /
   active-or-current / raw / applied Δ / total / outcome tag /
   operator note / reasons + caveats.
9. `## Remaining caveats` — explicit Thinkorswim-parity-pending
   reminder, derived-higher-timeframe row count, and the explicit
   "Phase C True Momentum strategy families are not active." line.
10. Trailing line: the deterministic outcome guardrail copy.

### Deterministic guardrail copy

Every review carries:

> *Outcome tags are operator research notes only. They do not change
> ranking, approval, sizing, or order routing.*

Notes are passed through `sanitizeMomentumOutcomeNote` which trims and
length-caps and `[redacted]`s the same forbidden phrase list as the
Phase B7 note sanitizer (constructed from token pairs so trade-action
literals never appear in the helper source). The integration guards
assert no forbidden trade-direction / order-routing language appears in
either the helper module or the component module.

### What Phase B8 does NOT do

- **No ranking math change.** `build_momentum_ranking_contribution`,
  `DeterministicRankingEngine`, Phase B1 / B6 / B6.x wiring are
  byte-identical.
- **No queue sorting change.**
- **No approval, promote, save, paper-order, settle, replay, or
  options-preview behavior change.**
- **No backend mutation.** No new endpoint, no DB row, no migration.
- **No LLM call.**
- **No Phase C activation.** True Momentum strategy families remain
  scaffold-only. The Phase B8 outcome corpus is one of the explicit
  prerequisites before any Phase C1 activation can be authorized.

### How B8 informs C1

A Phase C1 authorization decision needs three sources of evidence:

1. Real Thinkorswim parity fixtures (Phase A outstanding item).
2. An active-trial outcome corpus — exactly what Phase B8 captures.
3. Explicit operator authorization per planned family.

When a meaningful number of Phase B8 reviews have been exported and
reviewed across a representative sector / regime mix, the operator can
audit which planned True Momentum families would have produced clean,
neutral, or counter-productive outcomes against the captured snapshots.
That review — not the Phase B8 helper itself — is the input to a
Phase C1 go/no-go.

### Tests (Phase B8)

- `apps/web/lib/momentum-trial-outcomes.test.ts` — 28 pure-helper
  tests covering: outcome tag labels / tones / membership predicate;
  note sanitization (trimming, redaction, length cap); candidate
  defaults from snapshot (top + warning + caveat candidates, deduped,
  default `unclear` tag, reason flag copy); review construction with
  and without existing outcomes; stale-row rejection;
  global-conclusion sanitization; null-snapshot graceful degradation;
  per-tag summary counts; reason-code count aggregation; validation
  acceptance + rejection; Markdown export sections (headers, global
  conclusion empty state, universe-kind heading); JSON round-trip;
  forbidden trade-action language guard on both Markdown and JSON.
- `apps/web/components/recommendations/momentum-trial-outcome-review.test.tsx`
  — 8 render tests covering empty state, table per default outcome,
  summary cards with new labels, export + clear buttons, global
  conclusion textarea, `initialOutcomes` / `initialGlobalConclusion`
  honored, deterministic-note rendered, no forbidden action language.
- `apps/web/lib/momentum-integration.test.ts` — Phase B8 isolation
  guard suite: helper and component carry the deterministic outcome
  copy; trial-journal container mounts the outcome panel; outcome
  surfaces stay out of order / paper / replay / options-paper routes
  and out of order / recommendation helper files; no forbidden
  trade-action language; Recommendations page still mounts the trial
  journal only (no direct outcome-panel mount).

### Still pending (carried forward)

- **Thinkorswim fixture parity.** Phase B8 surfaces a
  `needs_tos_parity_check` tag the operator can apply per-row, plus a
  "Remaining caveats" Markdown section that reminds the reader parity
  is still pending — but landing real fixtures in
  `tests/fixtures/thinkorswim_momentum/` and flipping
  `parity_required_for_active = True` is still future work.
- **Phase C strategy families.** Phase C0 scaffolding remains
  disabled-by-default. Activation is gated on the Phase B8 outcome
  corpus + Thinkorswim parity + operator authorization.

## Phase A/B Closeout

This section closes out the completed Momentum Intelligence Phase A and
Phase B work. It is intentionally stable — it records what shipped, the
active-mode operator knobs, the current safety posture, and what
remains outstanding before any Phase C activation can be considered.

### Phase A completed (research surface)

- Backend Momentum indicator + score engine wired through the
  recommendation pipeline.
- `/charts/momentum` payload exposes the candles, indicator lines,
  HiLo thrust strip, score strip, signal markers, latest snapshot,
  and chart explanation in one deterministic blob.
- Momentum workspace surfaces the chart + summary + markers in a
  read-only operator surface.
- Symbol Snapshot, Strategy Workbench, and Recommendation Detail
  surfaces consume the same Momentum snapshot for context.
- Thinkorswim parity fixture infrastructure exists at
  `tests/fixtures/thinkorswim_momentum/` with a `manifest.json`
  pointer; real fixtures remain pending.

### Phase B completed (bounded ranking influence)

- B1 — bounded contribution capped at ±20 score units, mode-aware
  (`off`/`shadow`/`active`) with the safety-guard scaffolding.
- B2 — operator UI for the ranking contribution per candidate.
- B3 — operator status visibility through the
  `/user/momentum-ranking-status` endpoint and the Settings
  Momentum-ranking status card.
- B4 — Momentum Shadow Impact Review on Recommendations.
- B4.2 — improved direction inference for bullish strategy families.
- B6 — controlled active-mode safety guard
  (`MACMARKET_ALLOW_MOMENTUM_ACTIVE_RANKING`).
- B6.1 — active-mode score saturation control via
  `MACMARKET_MOMENTUM_ACTIVE_DELTA_SCALE`.
- B6.2 — active-mode score wiring fix; baseline score before Momentum
  was applied is surfaced on each candidate.
- B6.3 — single source of truth for the active queue score plus the
  always-on ranking-score consistency guard.
- B6.4 — last-boundary queue-response consistency guard re-stamping
  active-applied rows in the queue route.
- B7 — Active Momentum Trial Journal / Comparison Report (operator
  evidence capture, local/export-only, no backend write).
- B7.1 — trial-journal polish: trade warnings vs operational caveats
  separated, evaluated universe vs captured symbols labeling, single
  deterministic guardrail note.
- Deploy temp handling was hardened so pytest temp directories no
  longer collide with the deployed working tree under
  `C:\Dashboard\MacMarket-Trader`.

### Active-mode env vars (current operator knobs)

| Env var | Purpose | Default |
|---|---|---|
| `MACMARKET_MOMENTUM_RANKING_MODE` | `off` / `shadow` / `active` | `shadow` |
| `MACMARKET_ALLOW_MOMENTUM_ACTIVE_RANKING` | Phase B6 safety guard for active mode | `false` |
| `MACMARKET_MOMENTUM_ACTIVE_DELTA_SCALE` | Phase B6.1 scale applied to the bounded raw contribution | `0.35` |

### Current recommended active-trial values

```env
MACMARKET_MOMENTUM_RANKING_MODE=active
MACMARKET_ALLOW_MOMENTUM_ACTIVE_RANKING=true
MACMARKET_MOMENTUM_ACTIVE_DELTA_SCALE=0.35
```

Under these values:

- Raw `+20.00` contribution maps to applied `+0.070` on the
  `[0, 1]` ranking score.
- Active queue no longer broadly saturates to `1.000`.
- Operator can still flip `MACMARKET_MOMENTUM_RANKING_MODE=shadow`
  or toggle the safety guard back to `false` to revert to the
  display-only Phase B baseline at any time.

### Safety posture

- **Ranking only.** Phase B influences candidate ordering only.
- **No approval behavior change.** Promote / save / approve flows are
  byte-identical to pre-Phase-B behavior.
- **No paper-order behavior change.** Paper-order creation remains
  manual and operator-initiated.
- **No auto-ordering.** Active mode never routes, opens, closes, or
  settles a position.
- **Parity pending visible.** Every Momentum status surface (Settings
  card, Recommendations impact review, Trial Journal snapshot, status
  endpoint) surfaces `parity_pending` and the
  `thinkorswim_parity_pending` reason code while real fixtures
  remain absent.

### Outstanding items

- **Real Thinkorswim parity fixtures.** Drop CSVs into
  `tests/fixtures/thinkorswim_momentum/` per the parity-fixtures plan
  and update `manifest.json`. Once a fixture passes, flip
  `parity_required_for_active` to `True` so active mode requires
  measured parity rather than operator discretion alone.
- **Accumulated B8 outcome evidence corpus.** The Phase B8 Active
  Momentum Trial Outcome Review feature is implemented — operators can
  tag captured Phase B7 snapshots per-candidate (worked, missed, too
  aggressive, good warning, false warning, watchlist only, needs ToS
  parity check, ignored, unclear) and export the review as
  Markdown / JSON. What still remains pending is the *accumulated
  corpus* of exported B8 reviews across a representative sector /
  regime mix — that corpus is one of the prerequisites for any future
  Phase C1 activation.
- **Phase C strategy-family implementation.** Phase C0 (scaffolding)
  is documented in
  [`docs/true-momentum-strategy-families.md`](true-momentum-strategy-families.md);
  no Phase C strategy currently generates queue candidates.
- **Possible Thinkorswim review for XLY / XLE / XLV differences.**
  Operator-flagged sectors where the deployed Momentum scoring differed
  noticeably from the Thinkorswim view during the active trial; this is
  a precondition before any Phase C activation.

### Phase C posture (explicit)

- **Phase C is not active.**
- **Phase C strategies are not generating queue candidates.**
- **Phase C does not approve, reject, size, or route trades.**

The Phase C0 scaffold module is read-only: it exposes specs and a
resolved status, gated behind both
`MACMARKET_TRUE_MOMENTUM_STRATEGY_MODE` and the explicit
`MACMARKET_ALLOW_TRUE_MOMENTUM_STRATEGY_FAMILIES` guard. With the
default settings, the effective mode is `disabled` and no preview rows
or queue candidates are produced. See
[`docs/momentum-phase-closeout.md`](momentum-phase-closeout.md) for the
operator-friendly checklist and
[`docs/true-momentum-strategy-families.md`](true-momentum-strategy-families.md)
for the full Phase C0 specification.

## Future phases

- **Thinkorswim fixture validation**: drop CSVs into
  `tests/fixtures/thinkorswim_momentum/` per the parity-fixtures section
  above and update `manifest.json`. Once a fixture passes, flip
  `parity_required_for_active` to `True` so active mode requires measured
  parity rather than relying on operator discretion alone.
- **Phase C (gated, separate authorization)**: dedicated strategy families
  combining momentum with event/regime/sector filters. Same gate as Phase B.
