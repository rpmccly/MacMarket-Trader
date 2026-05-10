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

## Future phases

- **Thinkorswim fixture validation**: drop CSVs into
  `tests/fixtures/thinkorswim_momentum/` per the parity-fixtures section
  above and update `manifest.json`. Once a fixture passes, flip
  `parity_required_for_active` to `True` so active mode requires measured
  parity rather than relying on operator discretion alone.
- **Phase C (gated, separate authorization)**: dedicated strategy families
  combining momentum with event/regime/sector filters. Same gate as Phase B.
