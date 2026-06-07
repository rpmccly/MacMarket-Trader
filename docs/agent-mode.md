# Agent Mode

Agent Mode is a paper-only operator loop for the private-alpha console. It is
designed to evaluate the current equity paper book once per day, produce a
deterministic action memo, and optionally submit approved paper-only changes
through the existing paper order and paper position lifecycle.

## Agent Profiles (Phase 11)

Agent Mode is now an **Agent Profiles** cockpit: each user can create and run
multiple independent, user-scoped paper agents instead of one settings row.

Agent types:

- **Standard Strategy Agent** (`standard`) — the existing deterministic strategy
  ranking. The profile selects which strategy families it may trade (Event
  Continuation, Breakout / Prior-Day High, Pullback / Trend Continuation, Gap
  Follow-Through, Mean Reversion, HACO Context).
- **HACO Direction Agent** (`haco_direction`) — uses the existing HACO direction
  output as the primary trigger. `haco_direction_mode` is `long_only`,
  `short_only`, or `long_and_short`. HACO long opens paper longs; HACO short is
  **review-only** (no paper shorts are ever created).
- **True Momentum Agent** (`true_momentum`) — uses the existing True Momentum
  score/trend outputs. `true_momentum_trigger_mode` is `conservative`,
  `balanced`, `aggressive`, or `review_only`. New True Momentum profiles default
  to `review_only` (no auto-open). Bearish momentum is review-only.
- **Hybrid Agent** (`hybrid`) — advanced: a top-ranked Standard candidate plus an
  optional HACO long filter and/or True Momentum confirmation.

Agent-type triggers are **isolated eligibility filters** applied *after*
deterministic ranking and *before* an open is planned. They never change
recommendation scoring or HACO/Momentum indicator math; they only read existing
indicator outputs. The recommendation/sizing/risk-calendar pipeline still has
final say on every eligible-long candidate. Bearish/short/exit reads become
review-only intents (`CASH_NO_TRADE` with `status="review_only"`), counted
separately from blocked actions.

Migration: existing single-agent users are migrated into one default
**"Standard Strategy Agent"** profile (`agent_type=standard`, `is_default=true`)
that copies all prior settings and the scheduler latch. Existing run history is
backfilled to that default profile. Migration is idempotent and runs on app
startup, on every scheduler CLI invocation, and at the top of the scheduler
loop. The legacy `agent_mode_settings` table is preserved for rollback.

Each profile owns its own schedule, sizing/risk caps, notification preferences,
strategy/trigger selection, and per-profile scheduler latch. The duplicate
guard and scheduler claim are per profile + scheduled window
(`local-date|HH:MM|timezone|profile_uid`). Runs, trades, positions, and
performance can be viewed for all agents or filtered to one profile. Each run
records `agent_profile_id`, `agent_profile_name`, and `agent_type`.

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

Profiles (Phase 11):

- `GET /user/agent-mode/profiles` — list the user's profiles (overview cards)
- `POST /user/agent-mode/profiles` — create a profile from a template
- `GET /user/agent-mode/profiles/{profile_uid}` — one profile's settings
- `PUT /user/agent-mode/profiles/{profile_uid}` — update a profile
- `DELETE /user/agent-mode/profiles/{profile_uid}` — delete (not default/last)
- `POST /user/agent-mode/profiles/{profile_uid}/default` — set the default profile
- `GET /user/agent-mode/agents` — per-profile overview summary

Per-profile (default profile when `profile_id` is omitted):

- `GET /user/agent-mode/settings` (`?profile_id=`)
- `POST /user/agent-mode/settings` (body may include `profile_id`/`profile_uid`)
- `GET /user/agent-mode/status` (`?profile_id=`)
- `POST /user/agent-mode/run` (body may include `profile_id`)
- `GET /user/agent-mode/latest` (`?profile_id=`)
- `GET /user/agent-mode/runs` (`?profile_id=`; omit for all agents)
- `GET /user/agent-mode/trades` (`?profile_id=`; omit for all agents)
- `GET /user/agent-mode/performance` (`?profile_id=`; omit for all agents)
- `POST /user/agent-mode/notifications/test` (body may include `profile_id`)

All endpoints require an approved authenticated user and are user-scoped. The
run endpoint is rate-limited with other high-cost workflow routes.

## Settings

Defaults:

- `enabled=false`
- `daily_run_time=15:45`
- `universe_source=manual`
- `manual_symbols=["SPY","QQQ","MTUM"]`
- `default_watchlist_id=null`
- `max_positions=5`
- `max_open_agent_positions=5`
- `max_new_trades_per_run=5`
- `max_new_trades_per_day=5`
- `max_dollars_per_trade=null`
- `max_percent_of_paper_account_per_trade=null`
- `max_exposure_per_symbol=null`
- `min_cash_reserve=0`
- `scan_depth=12`
- `allow_opens=true`
- `allow_closes=true`
- `allow_scale_resize=false`
- `allow_scale_ins=false`
- `allow_new_trade_when_symbol_already_open=false`
- `require_confirmation_for_restricted=true`
- `notification_preference=none`
- `paused=false`
- `kill_switch_enabled=false`

When disabled, paused, or kill-switched, `POST /user/agent-mode/run` records a
dry-run result even if a caller requests `dry_run=false`. When enabled and not
paused/kill-switched, `dry_run=false` may create paper-only orders and
paper-only closes through the existing repositories and paper broker adapter.
Scale/resize remains review-only in the MVP even when the setting is enabled;
Agent Mode will not execute scale-in, reduce, or replace intents until those
paper lifecycle paths are explicitly implemented.

Agent Mode stores its own user-scoped settings. Existing account defaults can
seed the first row, but later runs snapshot the Agent Mode settings used for
that run so sizing and skip decisions are auditable. When Agent Mode creates a
paper order, it applies the most conservative available cap across existing
paper sizing, max dollars per trade, max percent of paper account basis, max
exposure per symbol, minimum cash reserve, max trades per run/day, and max open
Agent positions. If sizing cannot be computed or a cap leaves zero shares, the
trade is skipped or blocked with a deterministic reason instead of routing an
order.

When `universe_source=watchlist`, scheduled runs and manual runs use the
selected/default watchlist as the primary symbol source. Manual symbols are
only used when the source is explicit manual override or watchlist-plus-manual.
Each run records `watchlist_id`, `watchlist_name`, and the resolved symbol
snapshot used for audit. Missing, deleted, or empty watchlists produce a clear
skip/block reason instead of silently falling back to the manual text box.

## Schedule Status

`GET /user/agent-mode/status` is the backend-owned schedule observability
contract. It returns the Agent enablement state, configured timezone and daily
run time, current server time in UTC, next scheduled run timestamp, seconds
until the next run, last started/completed timestamps, last run status,
skip/error summaries, trade/review/block counts, scheduler health, last
scheduler check, due-now state, selected watchlist, resolved symbol count, and
a paper-only scheduler source marker. The frontend may animate a countdown
from these values, but it does not calculate schedule truth independently.

Scheduler health is `unknown` until the external CLI loop has checked in. It
becomes `ok` after a recent check, `stale` when the last check is older than
the expected loop interval tolerance, and `degraded` after an error check.

If the browser timezone differs from the Agent Mode timezone, the UI warns the
operator that Agent runs use the configured Agent timezone.

## Notifications

Agent Mode notification preferences are user-scoped and support `none`,
`email`, `sms`, and `both`. User-facing run notifications are digested per run:
at most one branded email summary and one short SMS summary are sent for a
single Agent run. The digest includes status, watchlist/source, reviewed
candidate/position counts, opened/closed/held/blocked counts, notable symbols,
and an Agent Mode link. It does not send one user-facing message per symbol.

Email continues to use the existing backend email provider boundary and the
MacMarket branded email style. Notification attempt records remain available
for audit with safe payloads and redacted recipients.

SMS uses a backend provider abstraction with Twilio as the first provider:

- `SMS_PROVIDER=twilio`
- `SMS_NOTIFICATIONS_ENABLED`
- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_FROM_NUMBER`
- `TWILIO_MESSAGING_SERVICE_SID`
- `TWILIO_REQUEST_TIMEOUT_SECONDS`
- `SMS_MAX_MESSAGES_PER_USER_PER_DAY`
- `SMS_MAX_MESSAGES_PER_RUN`

Twilio SID/auth token values are server-only and must not use `NEXT_PUBLIC`
names. If SMS is disabled or Twilio config is incomplete, SMS preferences can
still be saved, but send attempts are recorded as `disabled` or `skipped` with
safe diagnostic codes. Phone numbers are redacted in persisted attempt records
and UI responses. SMS requires both a phone number and confirmed consent.

## Daily Runner

The CLI command below runs enabled, due Agent Mode settings for each configured
local daily window:

```powershell
python -m macmarket_trader.cli run-due-agent-mode
```

The Windows deployment/restart scripts start
`scripts/run-agent-mode-scheduler.ps1`, which loops every five minutes and
calls:

```powershell
python -m macmarket_trader.cli agent-scheduler-check
```

The scheduler uses the same deployed working directory, `.env`, virtualenv, and
database as the backend. It records the last check result on the user-scoped
Agent settings row and records actual runs in `agent_mode_runs` with source
metadata:

- `scheduled_agent` for real scheduled paper-only runs
- `manual_agent` for manual UI/API runs
- `scheduler_diagnostic` for safe diagnostic dry-runs

Duplicate prevention is based on a scheduler-window claim plus the scheduled
window key `local-date|HH:MM|timezone`, not on arbitrary manual runs. Manual
dry-runs do not suppress a due scheduled run. The scheduler skips users who
are no longer locally approved before any paper order lifecycle path can run.
It does not enable live routing.

Operator diagnostics:

```powershell
.\scripts\run-agent-mode-scheduler.ps1 -Once -NoNotifications -DryRun
.\scripts\run-agent-mode-scheduler.ps1 -Loop -NoNotifications -DryRun
python -m macmarket_trader.cli agent-scheduler-diagnostics
python -m macmarket_trader.cli agent-scheduler-check --dry-run --no-notifications
```

The `-Once -DryRun -NoNotifications` foreground mode creates no paper orders,
suppresses email/SMS digests, prints safe diagnostics in the current console,
and exits. The `-Loop -DryRun -NoNotifications` mode stays alive and writes
heartbeat/check logs without creating paper orders or sending notifications.
Production deploy/restart starts `-Loop` without dry-run so enabled scheduled
Agent Mode runs can use the existing paper-only lifecycle. The scheduler log
is `logs\agent_scheduler.log`; the launcher boot log is
`logs\agent_scheduler_boot.log`.

## Diagnostic Layers

Agent Mode records every run with:

- settings snapshot
- resolved universe
- selected watchlist id/name and resolved symbol snapshot when applicable
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
  exit, realized P&L, return, holding days, created/submitted/filled/closed
  timestamps, reasons, status, and linked run ID where the run audit provides
  one.
- Positions: current open paper positions with entry, cost basis/invested
  amount, mark, current market value when available, unrealized P&L, return,
  days held, and current Agent Mode review/action context.
- Performance: cumulative realized P&L, unrealized P&L, total paper P&L,
  win/loss count, win rate, average win/loss, profit factor when computable,
  max drawdown when closed-trade history is available, and timeframe-filtered
  run/trade/position/risk-block metrics for today, yesterday, last 7 days, last
  30 days, month to date, previous month, and all time.
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

## Phase 11 deployment: backup, rollback, and smoke checks

Before deploying the Agent Profiles schema change, back up the deployed SQLite
database. The schema upgrade is additive (a new `agent_profiles` table plus
nullable `agent_mode_runs.agent_profile_id/agent_profile_name/agent_type`
columns) and applied automatically by `apply_schema_updates()` on app/scheduler
startup, but a timestamped backup is required first.

Backup (run on the deploy host, services stopped):

```powershell
.\scripts\backup_deployed_db.ps1 -StopServices
```

This copies `C:\Dashboard\MacMarket-Trader\macmarket_trader.db` (and WAL/SHM
sidecars) into `C:\Dashboard\MacMarket-Trader\backups\db\<timestamp>\` with a
SHA-256 manifest and a `README.txt` restore note.

Rollback: stop the backend/frontend/scheduler, copy the backed-up `.db` (and
sidecars) from the timestamped backup folder back over the deployed DB path, then
restart. The legacy `agent_mode_settings` table is preserved, so a rollback to
the prior single-agent build still reads its original settings. Verify a backup
with:

```powershell
.\scripts\verify_sqlite_restore.ps1
```

Post-deploy smoke checks:

1. Existing users show one migrated **"Standard Strategy Agent"** default profile
   with their prior schedule/sizing/notifications intact, and prior run history
   attached.
2. Create a HACO Direction profile and a True Momentum profile; the True
   Momentum profile defaults to `review_only`.
3. `python -m macmarket_trader.cli agent-scheduler-diagnostics` lists every
   profile with per-profile due state and `counts.profiles`.
4. Run `python -m macmarket_trader.cli agent-scheduler-check --dry-run
   --no-notifications`; each enabled profile records a per-profile scheduled
   diagnostic run (no paper orders, no notifications).
5. In the cockpit, the All-agents/single-profile filter scopes Runs, Trades, and
   Performance; HACO-red and bearish-momentum candidates appear as review-only
   (no paper opens, no paper shorts).
6. Notifications: each profile run produces exactly one digest per enabled
   channel; multiple profiles scheduled separately produce multiple digests, and
   no per-symbol messages are sent. (SMS remains capped per user per day across
   all of a user's agents.)
