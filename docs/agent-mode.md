# Agent Mode

Agent Mode is a paper-only operator loop for the private-alpha console. It is
designed to evaluate the current equity paper book once per day, produce a
deterministic action memo, and optionally submit approved paper-only changes
through the existing paper order and paper position lifecycle.

## Guardrails

- Paper only. Agent Mode rejects non-paper execution modes.
- No live broker routing, no live trading, and no real-money orders.
- Deterministic MacMarket engines own ranking, side, action, entry,
  stop/invalidation, targets, sizing, risk-calendar gates, and cash/no-trade
  outcomes.
- LLM/AI text is not used to approve, size, route, open, close, replace, scale,
  or reduce paper positions.
- The max target book is fixed at five paper positions for the MVP.
- Agent Mode never forces five trades; failed or missing gates become
  `CASH_NO_TRADE`.
- Already-open symbols are not duplicated as new paper-open candidates.

## Endpoints

- `GET /user/agent-mode/settings`
- `POST /user/agent-mode/settings`
- `POST /user/agent-mode/run`
- `GET /user/agent-mode/latest`
- `GET /user/agent-mode/runs`
- `GET /user/agent-mode/trades`
- `GET /user/agent-mode/performance`

All endpoints require an approved authenticated user. The run endpoint is
rate-limited with other high-cost workflow routes.

## Settings

Defaults:

- `enabled=false`
- `daily_run_time=15:45`
- `universe_source=manual`
- `manual_symbols=["SPY","QQQ","MTUM"]`
- `max_positions=5`
- `scan_depth=12`
- `allow_opens=true`
- `allow_closes=true`
- `allow_scale_resize=false`
- `paused=false`
- `kill_switch_enabled=false`

When disabled, paused, or kill-switched, `POST /user/agent-mode/run` records a
dry-run result even if a caller requests `dry_run=false`. When enabled and not
paused/kill-switched, `dry_run=false` may create paper-only orders and
paper-only closes through the existing repositories and paper broker adapter.
Scale/resize remains review-only in the MVP even when the setting is enabled;
Agent Mode will not execute scale-in, reduce, or replace intents until those
paper lifecycle paths are explicitly implemented.

## Daily Runner

The CLI command below runs enabled, due Agent Mode settings once per local day
per user:

```powershell
python -m macmarket_trader.cli run-due-agent-mode
```

The command uses each setting's `daily_run_time` and `timezone`, skips users who
already have a run for that local date, and reports per-user skipped/error/run
status. It skips users who are no longer locally approved before any paper
order lifecycle path can run. It does not enable live routing.

## Diagnostic Layers

Agent Mode records every run with:

- settings snapshot
- resolved universe
- current paper book
- position reviews
- proposed/executed intents
- candidate queue
- decision memo
- provider/fallback/missing-data labels

The UI page at `/agent-mode` shows loading, empty, error, dry-run, scheduled,
and completed states. Operator language uses paper-safe terms such as paper
open, paper close, hold, replace paper position, and cash/no trade. If Agent
Mode actually executes an enabled close, the result is labeled as executed by
the Agent Mode paper lifecycle; dry-run and review-only paths are not labeled
as executed.

## Performance Cockpit

The `/agent-mode` page is organized as a paper-only cockpit:

- Overview: agent status, schedule, latest run state, current paper book count,
  realized/unrealized/total paper P&L, win rate, max drawdown, and latest run
  open/close/blocked counts.
- Runs: user-scoped run history with dry-run/enabled/error filters and separate
  counts for paper opens, paper closes, holds, blocked actions, cash/no trade,
  and total executed actions.
- Trades: closed Agent Mode paper trades with symbol, side, quantity, entry,
  exit, realized P&L, return, holding days, reasons, and linked run ID where
  the run audit provides one.
- Positions: current open paper positions with entry, mark, unrealized P&L,
  return, days held, and current Agent Mode review/action context.
- Performance: cumulative realized P&L, unrealized P&L, total paper P&L,
  win/loss count, win rate, average win/loss, profit factor when computable,
  and max drawdown when closed-trade history is available.
- Settings: enable/pause/kill switch controls plus run buttons. Dry-run is the
  safe primary action. Enabled paper mode uses a destructive control and
  requires explicit confirmation because it may create paper orders or close
  paper positions through the existing paper lifecycle.

The candidate queue groups duplicate strategy rows by symbol. The main row
shows the best ranked strategy/score for each symbol and supporting strategies
can be expanded for review.

## Daily Target Book Contrast

`/daily-target-book` is the read-only manual-review counterpart to Agent Mode.
It reuses deterministic ranking, risk, market-data labels, and paper-position
review diagnostics to build a five-slot target book, but it never creates paper
orders, changes paper positions, runs schedules, or calls broker execution.
Use Agent Mode for the autonomous paper lifecycle; use Daily Target Book to
review the current paper book versus today's deterministic scan before taking
operator-controlled action elsewhere.
