# Daily Target Book

Daily Target Book is the manual-review counterpart to Agent Mode. It answers:

> Given current paper positions and today's deterministic scan, what five
> positions should I be in or reviewing?

It is intentionally read-only. Building a target book creates no paper orders,
changes no paper positions, starts no schedules, and touches no broker or live
execution path.

## How It Differs From Agent Mode

- Agent Mode is an autonomous paper-only lifecycle that can, when enabled,
  create paper orders or close paper positions through the existing paper
  lifecycle.
- Daily Target Book is a manual review cockpit. It labels possible keep, exit,
  open, replace, scale, and cash/no-trade reviews, but the operator must take
  any action elsewhere.
- Daily Target Book does not persist a run audit in the MVP. The `latest`
  endpoint returns defaults and an empty latest state so the page can render a
  safe empty state after reload.

## Endpoints

- `GET /user/daily-target-book/latest`
- `POST /user/daily-target-book/build`

Both endpoints require an approved authenticated user.

## Builder Inputs

- `universeSource`: `manual`, `watchlist`, `watchlist_plus_manual`, `profile`,
  `default`, or `all_active`
- `symbols`: manual symbol list
- `scanDepth`: default `12`, capped server-side
- `includeExistingPositions`: default `true`
- `includeReplacementReviews`: default `true`

For profile/default source, the MVP can use the seeded Momentum Heatmap profile
symbols without creating or mutating a saved heatmap profile. Watchlist and
all-active sources use the existing user-scoped symbol-universe repository.

## Target Slots

Every build returns exactly five slots. Actions are:

- `KEEP_REVIEW`
- `EXIT_REVIEW`
- `OPEN_REVIEW`
- `REPLACE_REVIEW`
- `SCALE_REVIEW`
- `CASH_NO_TRADE`

Existing open paper positions are considered first when `includeExistingPositions`
is enabled. Valid positions are preserved as review slots. Replacement reviews
are labels only and never silently close or open a position. If deterministic
market-data, ranking, or risk gates fail, the slot remains `CASH_NO_TRADE`.

## Data Sources Reused

Daily Target Book reuses existing deterministic services where safe:

- current workflow market-data bars and session/fallback labeling
- deterministic ranking engine
- risk calendar assessment
- paper position review diagnostics
- user-scoped symbol universe and watchlist resolution

It does not call the paper broker, order creation, fill persistence, position
close, schedule, live broker, or provider default selection paths.

## UI Workflow

Open `/daily-target-book`, choose a universe source, adjust symbols/scan depth,
and click `Build target book`. The page shows:

- a prominent running banner during builds while the previous successful
  read-only result remains visible
- Overview counts
- Target Book
- Current Paper Book
- Candidate Queue grouped by symbol
- Differences / Required Review
- Decision Memo
- Data Quality

The page is meant for operator review before using existing Recommendation,
Replay, or Paper Orders workflows. It is not an execution screen.
