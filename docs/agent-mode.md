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
status. It does not enable live routing.

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
open, paper close, hold, replace paper position, and cash/no trade.
