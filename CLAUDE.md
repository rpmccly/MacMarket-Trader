# MacMarket-Trader — Claude Code Session Context

This file is read automatically by Claude Code at session start to orient each conversation.
Do not condense or rewrite the architecture or setup sections. Only update the **Current Phase Status** and **Open Items** sections as work progresses.

---

## What this repo is

MacMarket-Trader is a **research-first, event-driven trading intelligence console** for U.S. large-cap equities and liquid sector ETFs.

Design principle: **LLMs explain and extract. Rules and models decide and size.**

The system ingests market/macro/company events → normalizes them → classifies regime → produces deterministic, auditable trade recommendations → routes to paper execution → measures outcome, attribution, and replay/live parity over time.

Full architecture charter: `README.md` (canonical — do not summarize or replace it).

---

## Stack

| Layer | Tech | Location |
|---|---|---|
| Backend API | Python + FastAPI + SQLite (SQLAlchemy/Alembic) | `src/macmarket_trader/` |
| Frontend | Next.js (TypeScript, App Router) | `apps/web/` |
| Auth | Clerk (identity) + local `app_users` DB (role/approval truth) | Both layers |
| DB migrations | Alembic | `alembic/` |
| Backend tests | pytest | `tests/` |
| Frontend tests | Vitest + Playwright e2e | `apps/web/` |

**Dev path:** `C:\Users\ryanm\OneDrive\Documents\GitHub\MacMarket-Trader`
**Deployed path:** `C:\Dashboard\MacMarket-Trader`
**Deploy bridge:** `.\deploy-macmarket-trader.bat` (copies dev → deployed + starts servers)

---

## Key paths

```
src/macmarket_trader/
  api/routes/admin.py                    — protected user + admin route handlers
  api/routes/analysis.py                 — strategy workbench backend
  replay/engine.py                       — deterministic replay runner
  recommendation/service.py              — recommendation generation
  indicators/                            — HACO/HACOLT indicator math
  execution/                             — broker scaffolds (mock + AlpacaBrokerProvider)
apps/web/
  app/(console)/                         — operator console pages
    analysis/page.tsx                    — Strategy Workbench
    recommendations/page.tsx             — Recommendations workspace
    replay-runs/page.tsx                 — Replay workspace
    orders/page.tsx                      — Paper Orders workspace
    settings/page.tsx                    — user settings
    welcome/page.tsx                     — alpha welcome guide
  components/
    workflow-banner.tsx                  — guided flow context chip bar
    guided-step-rail.tsx                 — step 1–4 rail navigation
    active-trade-banner.tsx              — sticky trade context (guided mode)
    brand-header.tsx                     — pre-auth brand header
  lib/
    guided-workflow.ts                   — guided state parse/build helpers
    recommendations.ts                   — queue/provenance helpers
    lineage-format.ts                    — display_id formatting
    orders-helpers.ts                    — PnL + duration helpers
docs/alpha-user-welcome.md               — canonical welcome doc (rendered at /welcome)
docs/roadmap-status.md                   — full phase history
docs/private-alpha-operator-runbook.md   — deployment runbook
scripts/run-due-schedules.ps1            — scheduler wrapper
scripts/backup-db.ps1                    — daily DB backup
tests/                                   — backend pytest suite
apps/web/tests/e2e/                      — Playwright e2e suite
```

---

## Dev setup

```bash
# Backend
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
python -m uvicorn macmarket_trader.api.main:app --reload --port 9510

# Frontend
cd apps/web
npm install
npm run dev        # port 9500 (or 3000 in dev)
```

**Minimum `.env` for local dev (no real providers):**
```
ENVIRONMENT=local
AUTH_PROVIDER=mock
EMAIL_PROVIDER=console
WORKFLOW_DEMO_FALLBACK=true
POLYGON_ENABLED=false
MARKET_DATA_PROVIDER=fallback
MARKET_DATA_ENABLED=false
```

**Minimum `apps/web/.env.local`:**
```
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=
CLERK_SECRET_KEY=
BACKEND_API_ORIGIN=http://127.0.0.1:9510
```

---

## Test and build commands

```bash
# Backend tests
pytest -q

# Frontend type check
cd apps/web && npx tsc --noEmit

# Frontend unit tests
cd apps/web && npm test

# Frontend build (full type + bundle check)
cd apps/web && npm run build

# Seed demo data
python -m macmarket_trader.cli seed-demo-data

# Run due scheduled reports (also wired to MacMarket-StrategyScheduler task)
python -m macmarket_trader.cli run-due-strategy-schedules

# Poll Alpaca paper fills (future execution phase — not yet active)
python -m macmarket_trader.cli poll-alpaca-fills
```

---

## Auth and approval source-of-truth rules

- **Clerk** = identity boundary only (session verification).
- **Local `app_users` DB** = source of truth for `approval_status`, `app_role`, approval history.
- First login creates a local pending user (`approval_status=pending`, `app_role=user`).
- Subsequent logins only sync identity fields; they never overwrite local role/approval state.
- `/api/user/me` must always reflect local DB role.

---

## Guided workflow

Primary operator path: **Analyze → Recommendation → Replay → Paper Order → Position → Close**.

Context threads through URL query params: `guided=1`, `symbol`, `strategy`, `market_mode`, `source`, `recommendation` (UID), `replay_run` (ID), `order` (ID).

`WorkflowBanner` (`components/workflow-banner.tsx`) renders the active lineage as chips and prefers `display_id` over the canonical `rec_<hex>`.
`ActiveTradeBanner` (`components/active-trade-banner.tsx`) is a sticky top strip in guided mode showing SYMBOL · strategy · `display_id` · status.
`GuidedStepRail` renders the 1–4 step rail.
`parseGuidedFlowState` / `buildGuidedQuery` in `lib/guided-workflow.ts` are the canonical helpers.

In guided mode: "Make active" auto-advances to `/replay-runs`, "Run replay now" auto-advances to `/orders` (skipped if `has_stageable_candidate=false`). "Stage paper order now" is the terminal step. Cancel staged order is allowed pre-fill; reopen closed position is allowed within a 5-minute window.

---

## Important implementation constraints

- `user_is_approved=True` must be passed to `recommendation_service.generate()` during replay so quality-gate overrides apply and `has_stageable_candidate` is computed correctly.
- Order `side` field uses `Direction` enum: `"long"` (not `"buy"`) and `"short"` (not `"sell"`). Check `order.side.value == "long"` for buy-side position creation.
- Promote endpoint (`/user/recommendations/queue/promote`) accepts `action` field (`make_active` / `save_alternative`) — stored in `ranking_provenance` and returned in response.
- `display_id` format: `{SYMBOL}-{STRATEGY_ABBREV}-{YYYYMMDD}-{HHMM}`. Generated at recommendation creation. Falls back to `display_id_or_fallback()` for legacy rows (returns `Rec #shortid`). Canonical `recommendation_id` (`rec_<hex>`) stays the unique key — `display_id` is a label only, never used as FK.
- `console_url` in `config.py` is a `@property` that mirrors `app_base_url`. Do not add a separate `CONSOLE_URL` env var.
- `apply_schema_updates()` handles all new columns automatically on startup. No manual Alembic migrations needed for nullable columns.
- Identity reconciliation: `upsert_from_auth` matches by Clerk sub, then by email, then by `invited::email` prefix. Preserves `approval_status` and `app_role` through merge.
- `BROKER_PROVIDER=mock` is the current production setting. Do not change to `alpaca` without a later explicit execution phase.
- Sticky `thead th` pattern: inline styles `position: "sticky", top: 0, zIndex: 1, background: "var(--card-bg)", borderBottom: "1px solid var(--table-border)"`.
- `op-error` block style: `border: 1px dashed #7c4040; background: #2a1717`.

---

## Current Phase Status

**CURRENT STATE: Phases 0–9 complete for the current private-alpha/options parity scope. Private alpha live at https://macmarket.io. 3 alpha users. Phase 10 is now the safe planning/polish track for remaining deferred options/provider/crypto work; 10A1 is complete for Analysis Expected Range visualization reuse, 10B1 is complete for Orders durable paper-options display/readability polish, 10C1 through 10C5 are complete for the current explainable metric glossary/tooltips scope, and 10W1 through 10W8D are complete for symbol/watchlist design, current comma-entry cleanup, schema/read-model planning, additive schema/migration, backend repository/resolver foundation, current watchlist table UI polish, bulk symbol duplicate-handling polish, recommendation/schedule universe-selection design, the read-only resolved-universe preview API, Recommendations universe selector preview/apply UI, Schedule universe static-snapshot selector preview/apply UI, and selector closure audit/docs/test alignment; live/broker execution is not active.**

**Phase 11 (Agent Profiles) is complete and paper-only.** Agent Mode expanded from one settings row per user into multiple user-scoped Agent Profiles (`agent_type`: `standard`, `haco_direction`, `true_momentum`, `hybrid`). New additive `agent_profiles` table + nullable `agent_mode_runs.agent_profile_id/agent_profile_name/agent_type` columns; `apply_schema_updates()` now also runs in `_safe_init_db_for_cli` and FastAPI `lifespan`. Existing users migrate idempotently into one default "Standard Strategy Agent" profile (legacy `agent_mode_settings` preserved for rollback). Agent-type triggers are isolated eligibility filters layered on the unchanged ranking/recommendation pipeline (`agent_mode/triggers.py`, reading existing HACO/True Momentum outputs only); bearish/short reads are review-only and no paper shorts are created. Per-profile scheduler latch + duplicate guard (`window_key` is `date|HH:MM|tz|profile_uid`); one notification digest per profile run per channel (subject/body/SMS include profile name + type); runs/trades/performance scope by profile (ownership follows the OPEN intent) or aggregate "all agents". HACO green and True Momentum bullish modes open paper LONGS when risk/sizing/duplicate gates allow; a paper open executes only when the resolved order side is long (deterministic short setups → `paper_short_not_supported` review, never a paper short). New True Momentum profiles default to `conservative` (review_only still selectable). No-universe profiles (e.g. watchlist source with no watchlist) are skipped per-profile with `no_universe` before claiming the window — no misleading completed run. Run outcomes: `opened_paper_long`/`trigger_not_met`/`review_only_mode`/`bearish_review_only`/`paper_short_not_supported`/`no_universe`. Frontend `/agent-mode` is now an Agent Profiles cockpit (profile cards with per-profile enable/kill-switch, paper-open capability + "No watchlist selected" indicators, All-agents/single filter, create/edit with agent-type controls). Key files: `agent_mode/service.py`, `agent_mode/triggers.py`, `storage/repositories.py` (`AgentProfileRepository`), `api/routes/agent_mode.py`, `apps/web/components/agent-mode/agent-mode-console.tsx`, `apps/web/lib/agent-mode-api.ts`. Deploy: back up the SQLite DB first (`scripts/backup_deployed_db.ps1 -StopServices`); see `docs/agent-mode.md` "Phase 11 deployment" for rollback + smoke checks.

**Phase 12 (Agent ownership boundary + market-session scheduler guard) is complete and paper-only.** Paper positions/trades carry an owning `agent_profile_id` (NULL = manual). A run manages (closes/flips) ONLY its own positions: own → normal (`action_reason: managed_own_position`, owned close tags the trade with the profile id); another profile's position → review only, never closed (`reason: blocked_foreign_agent_position`, `position_owner: foreign_agent`); a manual/NULL trade → review only, never closed (`blocked_manual_position`, `position_owner: manual`). Optional `prevent_opposing_agent_positions_across_profiles` (default off) blocks opening a new long while another profile/manual holds an opposing short in the same symbol (`blocked_opposing_cross_profile`) without closing the other position. New `agent_mode/market_session.py` (US Eastern calendar): `run_due()` skips weekends (`market_closed_weekend`) and known NYSE/Nasdaq full-day holidays (`market_closed_holiday`) BEFORE claiming the window — not a failure, no orders, no trade notifications, no scheduled-run row, window left unclaimed so the next trading-day tick runs it once (different `window_key`, no dup-block); manual dry-runs still run but are labeled (`summary.marketClosed`/`marketSession`). Scheduler diagnostics report market session, `market_open_today`, per-profile `would_run_now`, and `next_eligible_trading_run`. Notification digest separates owned actions (`Opened (own)`/`Closed (own)`) from `reviewedExternalPositions`. Run preview adds an Owner column + "will not close positions it does not own" copy + a market-closed banner. Holiday set covers the current+next year (multi-year/observed-rule expansion is a follow-up). No live routing, no broker changes (`BROKER_PROVIDER=mock`), no scoring/HACO/TM/ATR/risk-calendar math changes. Key files: `agent_mode/market_session.py`, `agent_mode/service.py`, `domain/models.py` (`agent_profile_id` on `paper_positions`/`paper_trades` + `prevent_opposing_agent_positions_across_profiles` on `agent_profiles`), `storage/repositories.py`, `apps/web/components/agent-mode/agent-mode-console.tsx`, `apps/web/lib/agent-mode-api.ts`.

**Phase 12 (bidirectional paper lifecycle) is complete and paper-only.** Standard agents stay long-only/backward-compatible; a profile is *directional* when it is an `atr_trailing_stop` agent OR has `allow_shorts` on (HACO/True Momentum/Hybrid). Directional profiles drive opens/closes/flips through `triggers.decide_bidirectional_action` wired into `run()`: candidate loop decides the open side (`opened_long`→`_execute_open`; `opened_short`→new `_execute_directional_short_open`; `blocked_by_short_not_allowed`→`paper_short_not_allowed` review; `review_opposing_external_position`→`blocked_opposing_cross_profile` when the cross-profile guard is on); a separate own-position reconciliation flips/closes held positions on an opposing signal (protective-stop close keeps priority; only a plain HOLD is reconciled). Flips append the own CLOSE before the opposite-side OPEN (executes first) so there is never a simultaneous long+short for one symbol/profile. Paper shorts are risk-sized off the indicator protective stop (ATR where available; 5% fallback), routed through the same paper broker/OMS with a synthetic `agentdir_*` order id, tagged with the owning `agent_profile_id`; new run outcome `opened_paper_short`. Side-aware P&L: short unrealized `(entry-mark)*qty`, realized via side-aware `_equity_trade_pnl`. Ownership boundary still holds on the directional path (foreign/manual never closed/flipped). No live routing, no broker changes, no scoring/HACO/TM/ATR/risk-calendar math changes. Key files: `agent_mode/service.py` (`_profile_is_directional`, `_directional_flags`, `_execute_directional_short_open`, run-loop directional branch + reconciliation + flip-opens + short dispatch), `agent_mode/triggers.py`.

**Phase 12 (directional cockpit UI + directional digest) is complete and paper-only — first ATR user-facing sub-increment.** The Agent Profiles cockpit (`apps/web/components/agent-mode/agent-mode-console.tsx`) adds an **ATR Trailing Stop** create template and exposes the directional execution settings: a collapsed *Advanced ATR settings* block (trail type/period/factor/first trade/average type/decision timeframe/alignment mode) and a collapsed *Directional & short controls* block (`allow_shorts`, `allow_direction_flip`, `close_opposite_before_open`, `close_on_opposite_signal`, `hedge_allowed`, `prevent_opposing_agent_positions_across_profiles`), each with a "Paper shorts are simulated only." warning. Profile cards show capability (opens longs/shorts/both), allow-shorts + flip behavior, current position side, and last action (overview now serializes `directional`/`allow_shorts`/`allow_direction_flip`/`current_position_side`/`last_action`). The run preview gains **Side** + **Expected** columns (open long/short, close, flip long↔short, hold, review/block). The notification digest text breaks opens/closes/flips down by direction (`openedLong/openedShort`, `closedLong/closedShort`, `flippedLongToShort/flippedShortToLong`) — one digest per profile run per channel preserved. No ATR/HACO/TM/scoring/provider/broker/lifecycle changes. ATR Intel page, ATR Direction Heatmap, and the ATR scheduled report are the next sub-increments (Research nav entries added when those pages exist). Key files: `apps/web/components/agent-mode/agent-mode-console.tsx`, `apps/web/lib/agent-mode-api.ts`, `agent_mode/service.py` (`_profile_overview` directional fields + `_last_action_label`, `_intent_execution_metrics` directional buckets + digest text).

Tests (2026-06-07, Phase 12 cockpit UI): full backend pytest 1242 passed / 4 skipped. New backend digest-bucket tests (opened-short + flip) in `tests/test_agent_directional_lifecycle.py`. Frontend vitest 1018 passed (+3 cockpit ATR/directional/preview assertions), `tsc --noEmit` clean. Hygiene: `git diff --check` clean, no conflict markers, no secrets.

**Phase 12 (ATR Intel page) is complete and research-only — second ATR user-facing sub-increment.** New `POST /charts/atr` route (`api/routes/charts.py`, cloning the HACO chart route) backed by `charts/atr_service.py` (`AtrChartService`, reads the frozen ATR engine): returns price candles + trailing-stop series + flip markers + an `explanation` (current state LONG/SHORT, latest trailing stop, distance-to-stop %, bars since flip, last flip direction/time) + a multi-timeframe state table (1W/1D/4H/1H/30M, bounded `ATR_TABLE_TIMEFRAME_BAR_LIMIT=180`) + a config echo + `notes`. New schemas `AtrChartRequest`/`AtrChartPayload`/`AtrTrailingStopChartPoint`/`AtrTimeframeState`/`AtrChartExplanation`/`AtrChartConfigEcho`. Frontend: proxy `app/api/charts/atr/route.ts`, client `lib/atr-api.ts` (`fetchAtrChart`), page `app/(console)/charts/atr/page.tsx` → `components/charts/atr-workspace.tsx` (symbol input/search, state snapshot, dependency-free SVG price+trailing-stop visualization, multi-timeframe table, collapsed advanced ATR settings, "both direction signal and stop/risk reference" explainer, no-data/unsupported handling), and a **Research → ATR Intel** nav entry (`/charts/atr`). Research-only — no ATR/HACO/TM math, scoring, provider, broker, lifecycle, or notification changes. ATR Direction Heatmap and the ATR scheduled report remain the next sub-increments.

Tests (2026-06-07, Phase 12 ATR Intel): new `tests/test_atr_chart.py` (4: payload shape + multi-timeframe table, advanced-settings echo, flip marker on reversal, no-data/unsupported symbol). Frontend `lib/atr-api.test.ts` (2) + `components/charts/atr-workspace.test.tsx` (6: render, controls/API wiring, snapshot fields, multi-timeframe table, collapsed advanced settings, no-data states). Backend smoke 77 passed; frontend vitest 1026 passed; `tsc --noEmit` clean; `npm run build` succeeds (`/charts/atr` + `/api/charts/atr` routes present). Hygiene: `git diff --check` clean, no conflict markers, no secrets.

**Phase 12 (ATR Direction Heatmap + ATR scheduled report) is complete — final ATR user-facing surfaces; research-only, scheduled report email-only.** ATR Direction Heatmap is a **stateless refresh** (cloning the `/charts/momentum-heatmap` chart route, not the persisted HACO-heatmap profile): `POST /charts/atr-heatmap` (+ `/report/csv`, `/report/preview`) backed by `charts/atr_heatmap_service.py` (`AtrHeatmapService`, frozen ATR engine) → per-symbol LONG/SHORT state per 1W/1D/4H/1H/30M + deterministic alignment (**+1 LONG / −1 SHORT per timeframe → `alignment_score`, label LONG/SHORT/MIXED**) + decision-timeframe (1D) trailing stop / distance-to-stop % / bars-since-flip / last-flip dir+time + summary counts; unsupported symbols degrade to `status:"unavailable"`. New schemas `AtrHeatmapRequest`/`AtrHeatmapResponse`/`AtrHeatmapRow`/`AtrHeatmapCell`/`AtrHeatmapSummary`; reporting `charts/atr_heatmap_reporting.py` (`build_atr_report_payload`, `atr_heatmap_csv`, `atr_heatmap_html`, `atr_heatmap_text`). Frontend: proxies `app/api/charts/atr-heatmap/route.ts` + `/report/csv`, client `lib/atr-heatmap-api.ts`, page `app/(console)/atr-heatmap/page.tsx` (manual-symbol + existing-watchlist input, refresh, CSV export, all 12 columns, collapsed advanced ATR settings, responsive table), **Research → ATR Direction Heatmap** nav (`/atr-heatmap`). Symbols come from manual entry or an existing watchlist (no new saved-profile/snapshot persistence — deliberate follow-up). ATR scheduled report: new `REPORT_TYPE_ATR_HEATMAP="atr_heatmap"` in `strategy_reports.py` (`_run_atr_heatmap_schedule` mirrors `_run_haco_heatmap_schedule`; email-only via the existing `_send_heatmap_report`, `atr_heatmap_scheduled_report` template, branded HTML; summary LONG/SHORT/mixed/unavailable + top long/short + recently-flipped + state table), wired into `/schedules` UI report-type selector (static-symbol snapshot, no watchlist editing). Separate from Agent Mode notifications; no SMS path. No ATR/HACO/TM math, scoring, provider, broker, live-routing, weekend-guard, bidirectional-lifecycle, or Agent-digest changes. Key files: `charts/atr_heatmap_service.py`, `charts/atr_heatmap_reporting.py`, `api/routes/charts.py`, `strategy_reports.py`, `apps/web/app/(console)/atr-heatmap/page.tsx`, `apps/web/lib/atr-heatmap-api.ts`, `apps/web/app/(console)/schedules/page.tsx`.

Tests (2026-06-07, Phase 12 ATR Heatmap + report): new `tests/test_atr_heatmap.py` (6: alignment determinism, refresh shape, default/override config, unsupported symbol, CSV export, HTML preview) + `tests/test_atr_report.py` (4: report-type dispatch, payload/CSV/HTML render, email-only scheduled run, failure-email path). Frontend `lib/atr-heatmap-api.test.ts` (3) + `app/(console)/atr-heatmap/page.test.tsx` (5: render, API wiring, columns, advanced settings, summary/explainer) + schedules ATR report-type assertion. **Final validation: full backend pytest 1256 passed / 4 skipped; full frontend vitest 1035 passed; `tsc --noEmit` clean; `npm run build` succeeds (all 5 ATR routes present).** Hygiene: `git diff --check` clean, no conflict markers, no secrets; indicator math files unmodified, `config.py`/providers unchanged, no broker/live-routing changes.

Tests (2026-06-07, Phase 12 bidirectional): full backend pytest 1240 passed / 4 skipped (basetemp outside repo). New `tests/test_agent_directional_lifecycle.py` (13: opens long/short, short blocked when disallowed, flip long↔short, no simultaneous long+short, HACO/TM short via allow_shorts, Standard stays long-only, foreign/manual not closed on directional path, side-aware short realized+unrealized P&L). Frontend `tsc --noEmit` clean; agent-mode vitest green. Hygiene: `git diff --check` clean, no conflict markers, no secrets.

Tests (2026-06-07, Phase 12): pytest 1227 passed / 4 skipped (full run, basetemp outside repo). New `tests/test_agent_market_session.py` (9) + ownership/cross-profile/weekend/digest tests in `tests/test_agent_profiles.py` + `tests/test_agent_bidirectional.py` (14) + `tests/test_atr_trailing_stop.py` (13). Frontend: vitest 1015 passed, `tsc --noEmit` clean, `npm run build` succeeds. Hygiene: `git diff --check` clean, no conflict markers, no secrets.

Tests (2026-06-07, Phase 11): pytest 1172 passed / 4 skipped (the lone failure in a full run was a `--basetemp=.tmp` harness artifact in `test_deploy_test_temp.py`, which passes with a normal basetemp); new `tests/test_agent_profiles.py` (14) + `tests/test_sqlite_schema_updates.py` legacy-DB migration fixture. Frontend: vitest 1013 passed, `tsc --noEmit` clean, `npm run build` succeeds.

Tests (2026-04-30): pytest 271 collected; targeted 10W8D backend validation passed. vitest 199, Playwright 31, tsc clean from latest 10W8D frontend validation.

Phase 10C2 is complete for compact Recommendations score/risk-label help using
the existing glossary and `MetricLabel` foundation. Broader Analysis, Replay,
Orders, and glossary-page rollout remains open; scoring, provider behavior,
backend behavior, lifecycle math, payoff math, commission math, equity
behavior, schema, and execution semantics did not change.

Phase 10C3 is complete for compact Orders P&L/commission-label help using the
existing glossary and `MetricLabel` foundation. Broader Analysis, Replay, and
glossary-page rollout remains open; no Orders actions, backend behavior,
scoring, provider behavior, lifecycle math, payoff math, commission math,
equity behavior, schema, or execution semantics changed.

Phase 10C4 is complete for compact Analysis and Replay metric-label help using
the existing glossary and `MetricLabel` foundation. The rollout adds help to
Analysis options risk/source labels and Replay score/confidence/P&L/fee labels
without changing recommendation scoring, replay behavior, backend behavior,
lifecycle math, payoff math, commission math, equity behavior, schema, or
execution semantics. A broader glossary/reference page remains open.

Phase 10C5 is complete for the explainable metrics glossary closure audit. The
current in-context rollout is closed across Settings, Provider Health, Expected
Range, Recommendations, Orders, Analysis, and Replay. Tiny glossary safety-copy
polish keeps Provider readiness separate from live routing/broker execution and
Replay payoff preview separate from broker mark-to-market simulation; optional
glossary/reference-page work remains open.

Symbol discovery and watchlist management has a docs-only design checkpoint in
`docs/symbol-watchlist-design.md`. Existing Phase 10 numbering is preserved:
`10D` remains expiration-settlement design, while the symbol/watchlist plan is
tracked as `10W` workflow polish. `10W2` adds frontend-only helper copy and
parsed previews around current manual comma/space/new-line entry on
Recommendations, Schedules, and current watchlist editing; schema, provider
search, runtime storage, and recommendation-generation changes remain deferred.
`10W3` is complete as a docs-only schema/read-model checkpoint recommending a
future compatibility-first `user_symbol_universe` plus `watchlist_symbols`
model, resolver behavior, migration/backfill, rollback, and tests without
changing schema or runtime behavior. `10W4` is complete for the additive
schema/migration foundation: ORM models and Alembic tables now exist for
`user_symbol_universe` and `watchlist_symbols` with nullable provider metadata,
active defaults, uniqueness constraints, indexes, and focused schema tests,
without changing current watchlist JSON behavior, schedule payload symbols,
frontend UI, provider search, recommendation generation, or schedule execution.
`10W5` is complete for the backend-only repository/read-model and resolver
foundation: internal helpers can upsert/list active user-symbol rows, manage
normalized watchlist membership, create snapshot-only membership, enforce user
scope, normalize/dedupe symbols, and emit current symbol-array shapes without
wiring production recommendation or schedule flows to the new read model. `10W6`
is complete for frontend-only current watchlist table UI polish on Schedules:
saved watchlists now have search/sort, symbol counts, normalized chips,
per-list symbol filtering, duplicate feedback, and chip removal through the
existing update route while preserving current `watchlists.symbols` JSON
behavior and schedule payload symbols. `10W7` is complete for frontend-only
bulk symbol duplicate-handling polish: watchlist edits now make replace versus
add-to-existing explicit, merge keeps existing symbols first, appends new
unique pasted symbols, reports duplicates, and still submits the same deduped
symbols array through the current update route. `10W8` is complete as a
docs-only recommendation/schedule universe-selection checkpoint: future
selectors should resolve manual lists, watchlists, all-active symbols,
tags/groups, exclusions, and pinned symbols into previewed symbol arrays, with
static schedule snapshots as the default. `10W8A` is complete for a protected
backend read-only preview route that resolves manual, watchlist,
watchlist-plus-manual, all-active, and mixed symbol-universe inputs without
submitting Recommendations, mutating schedules/watchlists, calling providers,
or changing recommendation/schedule behavior. `10W8B` is complete for a
frontend Recommendations universe selector that previews manual, saved
watchlist, watchlist-plus-manual, and all-active sources through that API and
only copies resolved symbols into the existing manual input on explicit
operator action. `10W8C` is complete for a frontend Schedule universe selector
that previews the same sources and only copies resolved symbols into the
existing schedule symbol input as a static snapshot on explicit operator
action. `10W8D` is complete for the current recommendation/schedule
universe-selection closure audit; preview/apply selectors remain separate from
queue submit and schedule save/run behavior, and provider-backed discovery,
normalized production UI, tags/groups, and dynamic watchlist refresh remain
deferred.

Deployment: `https://macmarket.io` via Cloudflare Tunnel; backend `uvicorn` on `127.0.0.1:9510`; frontend Next.js on `0.0.0.0:9500`; SQLite at `C:\Dashboard\MacMarket-Trader\macmarket_trader.db`; daily 3 AM backup via `MacMarket-DB-Backup` task; strategy scheduler every 5 min via `MacMarket-StrategyScheduler` task.

Phase 6 + Pass 4 ships the full Analyze → Recommendation → Replay → Paper Order → Position → Close workflow with cancel-staged + reopen-closed (5 min) lifecycle, `display_id` labels (`AAPL-EVCONT-20260429-0830`), per-user `risk_dollars_per_trade` + Settings page at `/settings`, welcome guide at `/welcome` with brand header on pre-auth pages, invite email with welcome CTA, timezone-aware schedules, role-conditional sidebar, sticky Active Trade banner, auto-advance guided CTAs, Polygon market data (equities live; options chain preview research-only), and Cloudflare Access invite-only enforcement. Phase 7 is closed for equity paper-readiness, Phase 8 is closed for the scoped paper-first options capability, and Phase 9 is closed for current options provider/source/as-of parity plus Recommendations Expected Range visualization. See `docs/roadmap-status.md` for full phase history.

---

## Open Items (Phase 10 planning/polish is next)

### Phase 10 — Deferred-work planning and safe options polish (NEXT)
Phase 10 organizes remaining deferred items before risky implementation. Planned subphases: `10A` options UX/operator polish, `10B` durable Orders parity polish, `10C` options replay/history design checkpoint, `10D` expiration-settlement design checkpoint, `10E` provider-depth/readiness planning, `10F` crypto architecture planning only, and `10G` closure. `10A1` is complete for frontend-only Analysis Expected Range visualization using existing payload fields and the existing reusable component; `10B1` is complete for frontend-only Orders durable paper-options display/readability polish using existing lifecycle fields only; `10C1` through `10C5` are complete for the current in-context explainable metric glossary/tooltips scope; `10W1` is complete for the docs-only symbol discovery/watchlist design checkpoint, `10W2` is complete for frontend-only current comma-entry symbol workflow cleanup, `10W3` is complete for docs-only schema/read-model planning, `10W4` is complete for the additive schema/migration foundation, `10W5` is complete for internal repository/read-model and resolver helpers, `10W6` is complete for current watchlist table UI polish using existing JSON behavior, `10W7` is complete for current bulk symbol merge/duplicate polish, `10W8` is complete as a docs-only recommendation/schedule universe-selection checkpoint, `10W8A` is complete for the backend read-only resolved-universe preview API, `10W8B` is complete for the Recommendations universe selector preview/apply UI, `10W8C` is complete for the Schedule universe static-snapshot selector preview/apply UI, and `10W8D` is complete for the selector closure audit. Broader `10A`/`10B`, optional glossary/reference-page work, provider search implementation, normalized production UI, tags/groups, dynamic watchlist refresh, closure, and replay/history design work remain open.

### Later execution phase — Alpaca paper integration (NOT ACTIVE)
Wire `BROKER_PROVIDER=alpaca` only after a later explicit execution phase. Keys are configured in deployed `.env`, and scaffold exists in `src/macmarket_trader/execution/`, but real brokerage routing/execution remains disabled. Fill polling via CLI `poll-alpaca-fills` is not active.

### Phase 7 — Brokerage fees + commission modeling
Closed for the current equity paper-readiness scope. `gross_pnl` / `net_pnl`, per-trade equity commission, per-contract options commission settings, and current fee display guardrails are documented in `docs/roadmap-status.md`.

### Phase 8 — Options research → paper parity
Closed for the current scoped paper-first options capability: research preview, read-only/non-persisted payoff preview, supported defined-risk paper open/manual-close lifecycle, contract-commission net P&L, and Recommendations operator risk UX. Expiration settlement, assignment/exercise automation, persisted options recommendations, and live routing remain deferred.

### Phase 9 — Options operator parity and data-quality hardening
Closed for the current scope: durable paper-options Orders visibility, provider/source/as-of parity across the current options surfaces, and the Recommendations Expected Range visualization. Analysis visualization later landed in `10A1`; richer replay placement, provider-depth probes, and live routing remain future work only if explicitly reopened.

### Future crypto implementation
Phase 10F may plan crypto architecture only. Crypto implementation, crypto paper execution, and crypto-specific provider wiring remain later work.

### Known gaps (no phase assigned)
- `/account` page does not render Clerk `<UserProfile>` for MFA enrollment (Clerk MFA requires paid plan — deferred)
- `MacMarket-Strategy-Reports` scheduled task may be redundant with `MacMarket-StrategyScheduler` — verify and delete if duplicate
- `display_id` collision if two recs created for same symbol+strategy within same minute — needs suffix handling
- npm vitest/vite/esbuild moderate vulns (dev-server only, not production) — deferred until vitest 4 migration
- `save_alternative` backend action variant not yet implemented (UI button exists, disabled)
- `atm_straddle_mid` expected-range method not yet emitted
- Options remain paper-first only: no live routing, expiration settlement, assignment/exercise automation, naked shorts, persisted options recommendations, or options replay persistence into equity replay flows
- Invite reconciliation: manually patched for current alpha users; `upsert_from_auth` handles it going forward but verify with next new-user signup
