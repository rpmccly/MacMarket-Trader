# Scheduled reports

MacMarket-Trader supports production-minded recurring research emails without
embedding a brittle always-on scheduler inside web requests.

## Core model

- **Watchlists** store reusable symbol lists.
- **Strategy report schedules** define frequency (`daily`, `weekdays`,
  `weekly`), run time, timezone, static symbol snapshots, report type, and
  delivery target.
- **Strategy report runs** store report payloads, status, safe failure reasons,
  and delivery audit history.

Supported `report_type` values:

- `strategy_scan`: the existing deterministic ranked strategy candidate scan.
- `momentum_heatmap`: a research-only Momentum Heatmap email generated from the
  saved static schedule symbols.
- `haco_heatmap`: a research-only HACO Direction Heatmap email generated from
  the saved static schedule symbols.

Heatmap schedules reuse the existing `/schedules` page and
`strategy_report_schedules`/`strategy_report_runs` audit tables. They do not
create recommendation queue candidates, paper orders, broker orders, approval
events, sizing decisions, or live-trading actions. Heatmap schedules force the
recipient to the signed-in account email and ignore strategy-scan-only fields
such as `market_mode`, enabled strategies, and top-N ranking.

## Local-safe execution

Run all due schedules from CLI:

```bash
python -m macmarket_trader.cli run-due-strategy-schedules
```

This command calls the same service layer as the API "run now" action and is
designed to be wired to cron, Windows Task Scheduler, or a future worker
process. It dispatches due `strategy_scan`, `momentum_heatmap`, and
`haco_heatmap` schedules.

The compatibility command below runs only due Momentum Heatmap schedules:

```bash
python -m macmarket_trader.cli run-due-momentum-heatmap-reports
```

## Email provider behavior

With `EMAIL_PROVIDER=console`, report payloads are printed to stdout. Strategy
scan emails include:

- Top trade candidates
- Watchlist-only monitor names
- No-trade rejected names
- Deterministic scoring fields and rank metadata

Heatmap emails include the generated research heatmap table, per-timeframe
summary counts, unsupported/unavailable rows, and a plain-text fallback. When a
scheduled heatmap run cannot produce usable rows, MacMarket records a failed run
and sends a branded failure email with safe diagnostics such as failed row count
and a redacted reason. Provider secrets, authorization headers, and token values
must never be included in email or stored run payloads.

No external provider is required in local/dev mode.

## Phase 2 updates (2026-04-04)

- Schedule runs now persist a full ranked queue payload plus summary counts (`top_candidate_count`, `watchlist_count`, `no_trade_count`).
- The same deterministic ranking engine is shared across Symbol Analyze, Recommendations queue generation, and scheduled reports.
- `/user/strategy-schedules` now returns config summaries and recent run summaries for operator-facing history/detail views.
- Non-equity `market_mode` schedules remain explicitly blocked as planned research preview.
