# Momentum Intelligence Layer (Phase A1)

This document describes the **deterministic** Momentum Intelligence Layer that
landed under Phase A1: backend indicator math, chart payload, API route, and
tests. It does **not** change recommendation ranking, ranking influence,
strategy families, or recommendation approval behavior.

## Purpose

The Momentum Intelligence Layer ports three Simpler Trading reference studies
into typed Python so MacMarket can produce deterministic momentum/thrust
context alongside HACO. The intent matches the repository's design principle:
LLMs explain and extract; rules and models decide. The layer is purely
deterministic indicator math feeding a protected chart payload.

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

## Phase A1 scope

| Area | Status | Location |
|---|---|---|
| Indicator helpers (`sma`, `atr`, `crosses_above/below`, `stochastic_full`, …) | Added | `src/macmarket_trader/indicators/common.py` |
| True Momentum oscillator | Added | `src/macmarket_trader/indicators/true_momentum.py` |
| HiLo Elite stochastic + thrust + cycle | Added | `src/macmarket_trader/indicators/hilo_elite.py` |
| Composite True Momentum Score | Added | `src/macmarket_trader/indicators/true_momentum_score.py` |
| Pydantic chart payload schemas | Added | `src/macmarket_trader/domain/schemas.py` |
| Momentum chart service | Added | `src/macmarket_trader/charts/momentum_service.py` |
| `POST /charts/momentum` API route | Added | `src/macmarket_trader/api/routes/charts.py` |
| Backend tests + parity scaffold | Added | `tests/` |

**HACO/HACOLT behavior is unchanged.** The existing `compute_haco_states`,
`compute_hacolt_direction`, and `/charts/haco` route continue to work as
before; this phase only added new modules and helpers.

## Explicitly out of scope for Phase A1

- No ranking influence — composite scores are not consumed by recommendation
  scoring or quality gates.
- No new strategy family is added.
- No automatic trade approval changes.
- No frontend integration in this prompt.
- No database migrations — payload is request-driven and stateless.

## Approximation/parity caveats

- **Higher-timeframe series:** When `higher_timeframe_bars` is not provided,
  `compute_true_momentum` derives a labeled secondary close series from the
  chart bars (1H → daily, 4H → deterministic three-session grouping, 1D →
  ISO-week grouping). The result is **not** an exact reproduction of
  Thinkorswim's secondary `close(period=...)` aggregation. The series exposes
  `higher_timeframe_source` with values `provided_higher_timeframe_bars`,
  `derived_from_chart_bars`, or `insufficient_data` so the chart layer can
  surface this clearly.
- **`parity_status`:** Defaults to `pending_thinkorswim_fixture_validation`.
  When Thinkorswim CSV fixtures are added under
  `tests/fixtures/thinkorswim_momentum/`, the scaffold test
  (`tests/test_momentum_thinkorswim_parity_scaffold.py`) can switch to
  comparing latest `total_score` / `true_momentum` / `hilo_thrust` within
  configured tolerances. Until then, parity is explicitly *pending*.
- **ATR trailing stop:** Thinkorswim's `ATRTrailingStop` with the *modified*
  trail type is not exactly reproducible from the published behavior alone.
  The composite score uses a **deterministic EMA-based trailing-stop
  approximation** and exposes `atr_stop_mode =
  "deterministic_ema_trailing_stop_approximation"` in the output series. This
  is intentional and labeled rather than hidden.
- **Stochastic smoothing:** `stochastic_full` uses exponential smoothing
  (matching the studies' `AverageType.EXPONENTIAL`) and the documented
  `over_bought` / `over_sold` scaling. EMA seeding uses the first value as
  seed (consistent with the existing repository convention).

## Composite score component reference

The composite total score per `compute_true_momentum_score` is:

```
base_score = TrueMomentumScore + HiLoThrust + Bull_MA + Bear_MA + ATR_Value + MACD_bias
intraday_penalty = -5 if (intraday and has_200 and close < SMA200 and -95 <= base <= 100) else 0
total_score = base_score + intraday_penalty

trend_score = (Bull_MA + Bear_MA + ATR_Value) * 100 / 40 (- 5 if penalty)
momo_score  = (TrueMomentumScore + HiLoThrust + MACD_bias) * 100 / 60
```

Score-state labels:

| Range | State | Label |
|---|---|---|
| `>= 100` | `max_bull` | "Max Bull" |
| `>= 75`  | `bull`     | "Bull" |
| `>= 45`  | `neutral_up` | "Neutral Up" |
| `<= -100` | `max_bear` | "Max Bear" |
| `<= -75`  | `bear`     | "Bear" |
| `<= -45`  | `neutral_down` | "Neutral Down" |
| otherwise | `neutral` | "Neutral" |

Pullback and reversal flags (`MaxBullPullback`, `BullPullback`, …,
`FromMaxBullToWeak`, `NeutralUpToBull`, …) are exposed on each
`MomentumScorePoint` and surfaced as markers in the chart payload.

## API

`POST /charts/momentum` is a protected route requiring an approved user
(`require_approved_user`), mirroring the auth and bar-resolution policy of
`POST /charts/haco`.

Request shape: `MomentumChartRequest` (`symbol`, `timeframe ∈ {1D, 4H, 1H}`,
`bars`, optional `higher_timeframe_bars`, `include_markers`).

Response shape: `MomentumChartPayload` — candles, four indicator lines
(true-momentum, true-momentum EMA, HiLo SlowD, HiLo SlowD_X), HiLo thrust
strip, score strip, signal markers, latest snapshot, explanation, and
provider/session metadata including `data_source`, `fallback_mode`,
`higher_timeframe_source`, `higher_timeframe`, `parity_status`, and
`calculation_notes`.

## Phase A2 — frontend display integration

Phase A2 wires the Phase A1 backend payload into the operator console as
**deterministic display context only**. It deliberately does **not**
introduce ranking influence, strategy-family creation, or any change to
recommendation approval, sizing, or paper-order behavior.

| Surface | File | Notes |
|---|---|---|
| Frontend proxy route | `apps/web/app/api/charts/momentum/route.ts` | POST proxy via `proxyWorkflowRequest` to `/charts/momentum`; auth-pending → 425. |
| Momentum API client | `apps/web/lib/momentum-api.ts` | `fetchMomentumChart`, types matching the backend payload; 425 maps to `AUTH_NOT_READY`. |
| Pure helpers | `apps/web/lib/momentum-chart.ts` | `momentumScoreTone`, `formatMomentumScore`, `formatMomentumValue`, `summarizeMomentumSnapshot`, `hasMomentumWarning`, `getLatestMomentumSnapshot`, `buildMomentumLegendValues`, `normalizeMomentumTimeKey`. |
| Reusable summary panel | `apps/web/components/charts/momentum-summary-panel.tsx` | Renders score / state / trend / momo / components / parity / HTF source / data source / explicit deterministic-context note. |
| Workspace | `apps/web/components/charts/momentum-workspace.tsx` | Symbol input, timeframe selector (1D / 4H / 1H), price candles + synced TM/EMA, SlowD/SlowD_X, score histogram, thrust strip, and markers. |
| Console page | `apps/web/app/(console)/charts/momentum/page.tsx` | Mounts the workspace under **Research → Momentum Intelligence** in the console nav. |
| Strategy Workbench | `apps/web/app/(console)/analysis/page.tsx` | Adds `momentumPayload` / loading / error state; fetches alongside the existing `fetchHacoChart` call; renders `MomentumSummaryPanel` near the Workbench chart. Failure does not block the workbench. |
| Symbol Snapshot | `apps/web/app/(console)/analyze/page.tsx` | Adds compact panel for the entered symbol on timeframe `1D`; failure does not block triage. |
| Recommendation detail | `apps/web/app/(console)/recommendations/page.tsx` | Adds `selectedMomentumPayload` for the selected queue/recommendation symbol; renders compact panel as context only. |
| Indicator registry | `apps/web/lib/indicator-framework.ts` + `apps/web/components/charts/indicator-selector.tsx` | New IDs: `true_momentum`, `true_momentum_ema`, `hilo_elite`, `hilo_slowd`, `hilo_slowd_x`, `momentum_score`, `momentum_thrust` under a typed `momentum_intelligence` category. All `defaultEnabled: false`. The generic `WorkflowChart` lists them as **unsupported** rather than rendering them, since they require the dedicated momentum payload. |

### Tests

- `apps/web/lib/momentum-chart.test.ts` — score tone mapping, null/undefined formatting, snapshot summary (bull / bear / neutral), warning detection, latest-snapshot extraction, legend rows.
- `apps/web/lib/momentum-api.test.ts` — `fetchMomentumChart` posts JSON to `/api/charts/momentum`, uses `credentials: include` and `cache: no-store`, maps 425 to `AUTH_NOT_READY`, throws clear error on non-OK responses.
- `apps/web/components/charts/momentum-summary-panel.test.tsx` — renders empty / loading / error states, score / label / trend / momo / components, parity-pending and HTF-source badges, deterministic-context note, reversal/no-trade warning state, bear-tone variant.
- `apps/web/lib/indicator-framework.test.ts` — registry contains new IDs; existing defaults unchanged; momentum-intelligence IDs round-trip through `normalizeSelection`.
- `apps/web/lib/workflow-chart.test.ts` — momentum-intelligence IDs are surfaced as **unsupported** (not selected) on the generic workflow chart.
- `apps/web/lib/momentum-integration.test.ts` — Strategy Workbench, Symbol Snapshot, Recommendation detail import the panel + client; momentum proxy route delegates to `proxyWorkflowRequest`; `/charts/momentum` page mounts `MomentumWorkspace`.

### Explicitly out of scope

- No ranking influence — composite scores still do not feed recommendation ranking, scoring, or quality gates.
- No strategy families.
- No recommendation approval, sizing, or paper-order behavior changes.
- No HACO/HACOLT removal; HACO context remains intact.
- `parity_status` continues to default to `pending_thinkorswim_fixture_validation` until Thinkorswim fixture CSVs land under `tests/fixtures/thinkorswim_momentum/`.

## Future phases

- Phase A3: visual QA / operator hardening — mobile/responsive polish, accessibility audit, dark/light theme review, hover/legend/animation polish, and signal-marker copy review across surfaces.
- Phase B (later, gated): ranking influence — only after Phase A3 completes and explicit operator approval is in place.
- Phase C (later, gated): dedicated strategy families that combine momentum context with event/regime/sector filters.
- Thinkorswim fixture validation: replacing `parity_status =
  pending_thinkorswim_fixture_validation` with measured tolerances once CSVs
  land.
