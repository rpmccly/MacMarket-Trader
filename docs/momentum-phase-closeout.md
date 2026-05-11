# Momentum Intelligence Phase A/B Closeout — Operator Checklist

This document is the short operator-facing companion to the full
charter at [`momentum-intelligence-layer.md`](momentum-intelligence-layer.md).
It records what shipped, the active-mode knobs, the current safety
posture, and what is outstanding before any Phase C activation.

Phase C0 (scaffolding) is documented separately in
[`true-momentum-strategy-families.md`](true-momentum-strategy-families.md)
and is **not active**.

## Phase A — research surface (complete)

- Backend Momentum indicator math + score engine.
- `/charts/momentum` payload.
- Momentum workspace.
- Symbol Snapshot / Strategy Workbench / Recommendation Detail
  context surfaces.
- Thinkorswim parity fixture infrastructure
  (`tests/fixtures/thinkorswim_momentum/`).

## Phase B — bounded ranking influence (complete)

- B1 — bounded ±20 contribution with mode-aware `off`/`shadow`/`active`.
- B2 — operator UI for ranking contribution.
- B3 — operator status visibility (`/user/momentum-ranking-status`,
  Settings status card).
- B4 — Shadow impact review.
- B6 — controlled active-mode safety guard.
- B6.1 — active delta scale (`0.35`).
- B6.2 / B6.3 / B6.4 — score wiring fix, single-source-of-truth
  guard, last-boundary queue-response consistency guard.
- B7 / B7.1 — Active Momentum Trial Journal (operator evidence
  capture, trade warnings vs operational caveats, single
  deterministic guardrail note).
- Deploy temp handling was hardened.

## Active-mode env vars

| Env var | Purpose | Default | Recommended active-trial |
|---|---|---|---|
| `MACMARKET_MOMENTUM_RANKING_MODE` | `off` / `shadow` / `active` | `shadow` | `active` |
| `MACMARKET_ALLOW_MOMENTUM_ACTIVE_RANKING` | safety guard for active mode | `false` | `true` |
| `MACMARKET_MOMENTUM_ACTIVE_DELTA_SCALE` | bounded contribution scale | `0.35` | `0.35` |

Under these values:

- Raw `+20.00` → applied `+0.070`.
- Active queue no longer saturates to `1.000`.
- Active queue consistency guard is on (Phase B6.4).
- The active trial journal records snapshot evidence locally.

## Safety posture

- Ranking only.
- No approval behavior change.
- No paper-order behavior change.
- No auto-ordering.
- Paper-order creation remains manual.
- Parity pending is visible on every surface.

## Outstanding items

1. Real Thinkorswim parity fixtures.
2. ~~Active-trial outcome tagging / review of the trial journal.~~
   **Phase B8 ships the active trial outcome review** — the next
   evidence loop after B7. Operators can now tag each captured
   candidate (`worked` / `missed` / `too_aggressive` / `good_warning` /
   `false_warning` / `watchlist_only` / `needs_tos_parity_check` /
   `ignored` / `unclear`), record a session-level global conclusion,
   and export the review as Markdown / JSON. Still local/export-only
   (no backend persistence, no DB row).
3. Phase C strategy-family implementation (specs in Phase C0;
   activation deferred). **C1 should wait for the Phase B8 outcome
   evidence corpus and the real Thinkorswim parity review before
   any activation is authorized.**
4. Possible Thinkorswim review for XLY / XLE / XLV differences
   before Phase C activation.

## Phase C posture

- Phase C is **not active**.
- Phase C strategies do **not** generate queue candidates.
- Phase C does **not** approve, reject, size, or route trades.

The Phase C0 scaffold module exposes a read-only status endpoint and
planned family specs only. With defaults the resolved effective mode is
`disabled`, both env knobs are required to flip into `research_preview`,
and `active` is reserved.

## Rollback

To revert the active-mode trial at any time:

```env
MACMARKET_MOMENTUM_RANKING_MODE=shadow
MACMARKET_ALLOW_MOMENTUM_ACTIVE_RANKING=false
```

The Phase B safety guard alone is sufficient — even if
`MACMARKET_MOMENTUM_RANKING_MODE=active` survives an env update, the
guard flipping to `false` forces the effective mode back to `shadow`.
