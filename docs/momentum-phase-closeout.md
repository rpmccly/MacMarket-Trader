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

## Implemented (Phase B closeout + B8 + Phase C0/C1/C2)

- Phase A/B closeout — see the layer charter.
- **Phase B8 Active Momentum Trial Outcome Review (feature
  implemented).** Operators tag each captured Phase B7 snapshot
  per-candidate (`worked` / `missed` / `too_aggressive` /
  `good_warning` / `false_warning` / `watchlist_only` /
  `needs_tos_parity_check` / `ignored` / `unclear`), record a
  session-level global conclusion, and export the review as
  Markdown / JSON. Local/export-only (no backend persistence, no DB
  row, no DB migration). The review surface lives in the
  Recommendations workspace directly under the Trial Journal snapshot.
- **Phase C0 scaffolding (disabled by default).** Three planned True
  Momentum families exposed as specs + a read-only status endpoint at
  `GET /user/true-momentum-strategy-families/status`. No active
  behavior.
- **Phase C1 research-preview classifier (feature implemented).**
  Backend evaluator + `POST /user/true-momentum-strategy-families/preview`
  + frontend lib + Recommendations panel. Classifies the already-loaded
  queue into the three planned families with precedence
  `reversal_watch > pullback > continuation`. Does **not** generate
  new queue candidates. Active mode remains reserved.
- **Phase C2 preview-evidence bundle workflow (feature implemented).**
  Operators capture a deterministic Markdown / JSON bundle of the
  current C1 classification + per-family / per-candidate notes and
  review tags. Local/export-only. Mounted inside the C1 preview panel
  whenever C1 matched at least one row.
- **Phase C2.1 B7/B8 evidence linkage (feature implemented).**
  The C2 panel now rehydrates the latest B7 trial snapshot + B8
  outcome review from `localStorage`, computes a stable
  `rank::symbol::strategy` signature, and surfaces
  `linked` / `missing` / `mismatch` / `partial` link status with
  recommended copy + per-tag outcome counts. The Markdown / JSON
  exports include a "Linked B8 Trial Evidence" section. Duplicate
  guardrail copy under the C1 panel is cleaned up — the C2 panel is
  now the canonical owner of the deterministic research-only note
  whenever it is mounted.
- **Phase C2.2 live B8 outcome linkage + Ranked queue scroll polish
  (feature implemented).** B7 snapshot + B8 outcome review state is
  now lifted to the Recommendations page and passed directly into the
  C2 evidence panel, so a worked / missed tag in B8 immediately flips
  the C2 panel's "B8 outcome review" badge to `linked` (with the
  matching per-tag counts) rather than showing `missing`. Linkage uses
  the *embedded* B7 snapshot signature, so a subset outcome review
  (top + warning candidates only) still links against a larger queue.
  The Ranked queue candidates panel is now wrapped in a scroll
  container that shows ~10 rows at a time, mirroring the Persisted
  recommendations panel.
- **Phase C3 research cohort review (feature implemented).**
  Operators archive each Phase C2 evidence bundle to a local
  research cohort archive (`macmarket.trueMomentumCohortReview.archive`),
  roll up family-level previews + B8 outcome counts across sessions,
  and export a deterministic Markdown / JSON report with a readiness
  label (`insufficient_evidence` / `parity_blocked` /
  `promising_research` / `mixed_research` / `needs_operator_review` /
  `not_recommended_for_activation`). Phase C3 never emits "ready for
  live" or "activate now" wording — the strongest positive label is
  `promising_research`. Mounted inside the C2 evidence panel so the
  operator does not need to export / import bundles manually.
- **Phase C4 strategy-family research context (feature implemented).**
  Recommendations page now renders a True Momentum Strategy Context
  card for the currently selected queue candidate: family-fit badge,
  match strength, trigger-readiness checklist, parity / evidence
  caveats, B8 / C3 evidence status, and an activation-readiness
  classification (`research_ready` / `needs_more_evidence` /
  `parity_blocked` / `composite_mismatch_review` / `warning_blocked` /
  `not_applicable` / `watch_only`). Pure helper at
  `apps/web/lib/true-momentum-strategy-context.ts`. Backend status
  endpoint now ships `thinkorswim_parity_symbol_summaries` so the card
  can surface a symbol-scoped parity caveat (e.g. XLP shows
  `composite_mismatch` while SPY / XLK / XLE remain attested). Phase C4
  is research-only — it does not generate queue candidates, change
  ranking or queue sorting, change recommendation approval, promote,
  save, paper-order, replay, or options behavior, and does not
  activate Phase C strategy families. Activation readiness is research
  context, not trade approval.

## Outstanding items

1. **Real Thinkorswim visual/manual parity evidence.** Land measured
   fixtures in `tests/fixtures/thinkorswim_momentum/` and update
   `manifest.json`. The recommended path today is
   `parity_mode: "visual_attestation"`, which compares operator-
   entered ToS rendered values against operator-entered MacMarket
   rendered values from screenshots — no bars CSV or study CSV is
   required because Thinkorswim cannot export either for this
   workflow. The end-to-end workflow (manifest schema, capture
   paths, validator CLI, report interpretation) is documented in
   [`thinkorswim-momentum-parity.md`](thinkorswim-momentum-parity.md).
   The resolved `thinkorswim_parity_workflow_status` is surfaced on
   `MomentumRankingStatus` and rendered in the Settings card.
2. **Accumulated B8 outcome evidence corpus.** The B8 feature itself
   is implemented — what remains pending is enough exported B8
   outcome reviews across a representative sector / regime mix to
   support a Phase C1 go/no-go review.
3. **Active Phase C strategy-family implementation.** Phase C0
   scaffolding + Phase C1 research-preview classifier + Phase C2
   preview-evidence bundle workflow are implemented and disabled by
   default. **Active Phase C strategy generation should wait for the
   accumulated B8 outcome evidence corpus, the real Thinkorswim parity
   review (visual/manual observations are the accepted operator-
   reviewed substitute given ToS does not export study rows), and
   explicit operator authorization before any active Phase C is
   enabled.**
4. **Possible Thinkorswim review for XLY / XLE / XLV differences**
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
