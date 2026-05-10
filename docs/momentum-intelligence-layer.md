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

## Future phases

Phase A1 deliberately stops at backend deterministic math and protected
chart payload. Future phases (not implemented in this prompt):

- Phase A2: frontend display integration for Symbol Snapshot, Strategy
  Workbench, Recommendation detail, and the indicator registry.
- Phase B: ranking influence — feeding momentum scores into recommendation
  ranking with explicit guardrails and replay parity.
- Phase C: dedicated strategy families that combine momentum context with
  event/regime/sector filters.
- Thinkorswim fixture validation: replacing `parity_status =
  pending_thinkorswim_fixture_validation` with measured tolerances once CSVs
  land.
