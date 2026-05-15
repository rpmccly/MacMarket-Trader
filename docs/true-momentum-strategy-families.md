# True Momentum Strategy Families — Phase C0 (scaffolding only)

Phase C0 is the **scaffolding-only** introduction of the True Momentum
strategy-family concept. It exists to:

- pin a stable set of family specs the operator can review,
- expose a read-only resolved-mode status (with guardrails and reason
  codes), and
- keep the Recommendations / paper-order / approval / replay surfaces
  byte-identical to Phase B closeout.

It explicitly does **not**:

- generate recommendations,
- create queue candidates,
- approve, reject, size, route, open, close, or settle trades,
- mutate state, hit a provider, or call market data,
- call an LLM,
- add or require Thinkorswim parity fixture CSVs,
- change ranking math, queue sorting, recommendation approval, or
  paper-order behavior.

## C0 purpose

Phase C0 records what the future True Momentum strategy families will
look like so that:

1. operator authorization can be obtained against an explicit list,
2. the dependency graph between Phase B closeout, Thinkorswim parity,
   and Phase C1 activation is visible, and
3. the frontend can render a "planned families" status card without
   any actionable copy or queue impact.

## Planned families

| Family ID | Label | Intent |
|---|---|---|
| `true_momentum_continuation` | True Momentum Continuation | Bullish continuation when Momentum score, trend, HiLo, and inferred direction align |
| `true_momentum_pullback` | True Momentum Pullback | Bullish pullback near deterministic EMA / ATR support while overall Momentum remains strong |
| `true_momentum_reversal_watch` | True Momentum Reversal / Weakening Watch | Warning / watch family for weakening Bull/Max Bull or Bear/Max Bear transitions |

All three are at `status: "planned"`, `phase: "C0"`,
`implementation_status: "scaffold_only"`.

## Required future inputs

When Phase C1 is authorized, the planned implementations will need:

- Momentum score snapshot (current `total_score`, `total_label`,
  trend / momo components).
- Trend / HiLo state and inferred direction.
- Reversal / no-trade / pullback flags from the Phase B Momentum
  contribution.
- Risk calendar decision (`allow_new_entries`, blocker level).
- Liquidity / spread context.
- Regime / catalyst context.
- Operator authorization checkpoint per active trial cohort.

## Explicit non-goals (Phase C0)

- No queue generation.
- No approval / order behavior.
- No paper-order creation.
- No live trading.
- No active-mode behavior (`active` resolves to `research_preview`
  with the `true_momentum_strategy_active_mode_not_implemented` reason
  code).

## Prerequisites before C1

1. **Accumulated Phase B8 outcome evidence corpus.** The Phase B7
   Active Momentum Trial Journal and the Phase B8 Active Momentum
   Trial Outcome Review are both already implemented — the trial
   journal captures a deterministic snapshot of the queue, and the
   outcome review lets the operator tag each captured candidate
   (worked, missed, too aggressive, good warning, false warning,
   watchlist only, needs ToS parity check, ignored, unclear) and
   export the review as Markdown / JSON. What still remains pending
   here is the *accumulated corpus* of exported B8 reviews across a
   representative sector / regime mix.
2. **Thinkorswim spot-check / parity review.** Real Thinkorswim
   visual/manual parity evidence (typically `parity_mode:
   "visual_attestation"`, which records operator-entered ToS and
   MacMarket rendered chart values from screenshots — no bars or
   study CSV required because ToS does not export either for this
   workflow), landing in `tests/fixtures/thinkorswim_momentum/` and
   the structured parity workflow reaching
   `thinkorswim_parity_workflow_status == "passed"` (see
   [`thinkorswim-momentum-parity.md`](thinkorswim-momentum-parity.md)
   for the manifest schema, capture paths, validator CLI, and report
   interpretation). The `parity_required_for_active` flag must also
   be flipped to `True`.
3. **Operator authorization.** Explicit go-ahead per family.

## Env vars

| Env var | Purpose | Default |
|---|---|---|
| `MACMARKET_TRUE_MOMENTUM_STRATEGY_MODE` | `disabled` / `research_preview` / `active` | `disabled` |
| `MACMARKET_ALLOW_TRUE_MOMENTUM_STRATEGY_FAMILIES` | explicit guard for non-disabled modes | `false` |

Allowed truthy values for the guard: `true`, `1`, `yes`, `on`
(case-insensitive). Any non-truthy value forces the effective mode
back to `disabled` with the
`true_momentum_strategy_mode_blocked_by_guard` reason code.

Even with the guard truthy, `active` is reserved in Phase C0 and
resolves to `research_preview` with the
`true_momentum_strategy_active_mode_not_implemented` reason code.

## Read-only status endpoint

`GET /user/true-momentum-strategy-families/status` returns the resolved
status payload:

- `requested_mode`, `effective_mode`, `enabled`, `guard_enabled`,
  `invalid_env_value`
- `mode_env_var`, `guard_env_var`
- `reason_codes`, `guardrails`
- `family_specs` (three planned families)
- `phase: "C0"`, `implementation_status: "scaffold_only"`
- `parity_status`, `parity_required_for_active`

Requires an approved user. No DB writes. No provider / market-data
calls. No recommendation generation.

## Phase C1 — read-only research-preview classifier

Phase C1 layers a **read-only research-preview classifier** on top of
the Phase C0 scaffolding. It classifies the already-loaded
Recommendations queue into the three planned True Momentum families
without generating new queue candidates and without changing ranking,
queue sorting, approval, paper-order, replay, or options behavior.

### What it does

- Reads the current Recommendations queue (already loaded in memory).
- Normalizes each candidate's Momentum contribution (total score,
  total label, trend / momo / direction / pullback / reversal flags,
  raw contribution, applied delta, parity / derived-HTF caveats).
- Applies family rules with precedence
  **reversal_watch > pullback > continuation**:
  - `true_momentum_reversal_watch` when any of: `reversal_warning`,
    `no_trade_warning`, bear total label on a long-biased strategy, or
    `total_score ≤ -50` on a long-biased strategy. Match strength is
    always `watch`.
  - `true_momentum_pullback` when a long-biased candidate is bullish
    (`Bull` / `Max Bull` or `total_score ≥ 80`), `raw_contribution > 0`,
    no warnings, and either the `pullback_signal` flag is active or the
    source strategy is "Pullback / Trend Continuation". Strength is
    `strong` if both pullback signal and bullish label fire, otherwise
    `moderate`.
  - `true_momentum_continuation` when a long-biased candidate is
    bullish (`Bull` / `Max Bull` or `total_score ≥ 80`),
    `raw_contribution > 0`, no warnings, and not bearish. Strength is
    `strong` if both `trend_score ≥ 70` and `momo_score ≥ 70` confirm,
    otherwise `moderate`.
- Surfaces operational caveats (`thinkorswim_parity_pending`,
  `derived_higher_timeframe`, `direction_unknown`,
  `active_mode_blocked_by_safety_guard`, `score_consistency_corrected`)
  per preview row.
- Always marks every preview row `non_actionable: true` and never
  includes entry / stop / target / size / approval / order fields.

### What it does NOT do

- **No new queue candidates.** Phase C1 only *labels* existing rows.
- **No ranking math change.** `build_momentum_ranking_contribution`,
  `DeterministicRankingEngine`, Phase B1 / B6 / B6.x wiring are
  byte-identical.
- **No queue sorting change.**
- **No approval, promote, save, paper-order, settle, replay, or
  options-preview behavior change.**
- **No backend mutation.** No DB write, no migration, no LLM call, no
  provider / market-data call.
- **No Phase C active behavior.** `MACMARKET_TRUE_MOMENTUM_STRATEGY_MODE=active`
  is still reserved — the resolved effective mode degrades to
  `research_preview` with the
  `true_momentum_strategy_active_mode_not_implemented` reason code.

### Env to enable the read-only research preview

```env
MACMARKET_TRUE_MOMENTUM_STRATEGY_MODE=research_preview
MACMARKET_ALLOW_TRUE_MOMENTUM_STRATEGY_FAMILIES=true
```

Both env vars are required. The guard alone with `mode=disabled` is a
no-op; the mode alone without the guard forces the effective mode back
to `disabled` with the `true_momentum_strategy_mode_blocked_by_guard`
reason code.

### Surfaces

- **Backend pure evaluator** —
  `src/macmarket_trader/recommendation/true_momentum_strategy_families.py`
  exposes `evaluate_true_momentum_strategy_preview(settings, *,
  candidates)`. Returns a dict carrying `status`, `previews`,
  `previews_generated`, `summary`, `guardrails`, `phase`,
  `implementation_status`, `preview_phase`,
  `preview_implementation_status`, `deterministic_note`, and a typed
  `TrueMomentumStrategyPreviewResult` under `result`.
- **Read-only endpoint** —
  `POST /user/true-momentum-strategy-families/preview` (approved-user
  auth). Request: `{ "candidates": [...] }`. Response: the typed
  `TrueMomentumStrategyPreviewResultPayload` (status + summary +
  previews + guardrails + deterministic note). No DB writes, no
  provider calls, no market-data calls.
- **Frontend pure helper** —
  `apps/web/lib/true-momentum-strategy-preview.ts`
  (`buildTrueMomentumStrategyPreview`,
  `summarizeTrueMomentumStrategyPreview`,
  `trueMomentumPreviewReasonLabels`, `trueMomentumPreviewTone`,
  `familyPreviewLabel`).
- **Frontend panel** —
  `apps/web/components/recommendations/true-momentum-strategy-preview-panel.tsx`
  is mounted on the Recommendations page directly after the Momentum
  Trial Journal. Renders the disabled empty state with env
  instructions, the research-preview summary cards + preview table,
  the active-reserved copy, and the deterministic guardrail note.

### Still pending

- Accumulated B8 outcome evidence corpus.
- Real Thinkorswim visual/manual parity evidence (typically `parity_mode: "visual_attestation"`, which records operator-entered ToS and MacMarket rendered chart values from screenshots; no bars or study CSV needed because ToS does not export either for this workflow).
- Operator authorization before any active Phase C.

## Phase C2 — research-preview evidence bundle

Phase C2 wraps the Phase C1 classification into an operator-facing
**evidence bundle workflow**. It captures whatever rows Phase C1
matched, lets the operator overlay a global research conclusion plus
per-family and per-candidate notes / tags, and exports the result as
deterministic Markdown / JSON. Everything is local/export-only — no
backend write, no DB row, no migration, no LLM call.

### What it does

- Builds a `TrueMomentumPreviewEvidenceBundle` from an existing
  Phase C1 `TrueMomentumStrategyPreviewResult` and the already-loaded
  queue candidates.
- Records the resolved ranking mode and active delta scale from the
  Phase C1 result (no recomputation).
- Surfaces `evaluated_universe` (when the page passes
  `universeSymbols`) or falls back to `captured_symbols` derived from
  the loaded queue.
- Groups the matched preview rows per family (continuation /
  pullback / reversal-watch), with per-family preview / strong /
  moderate / watch / blocked counts plus per-row trade warnings and
  operational caveats (`thinkorswim_parity_pending`,
  `derived_higher_timeframe`, `score_consistency_corrected`, …).
- Records whether a Phase B7 trial snapshot and Phase B8 outcome
  review are linked (presence flags only — no shared mutable state).
- Lets the operator attach a global conclusion, per-family notes, and
  per-candidate notes / review tags
  (`research_candidate`, `watchlist_only`, `needs_tos_parity_check`,
  `needs_b8_outcome_evidence`, `too_noisy`, `defer`).
- Exports as **Markdown** (Copy + Download) and **JSON**, both
  carrying the deterministic guardrail copy and the "Active Phase C
  True Momentum strategy families are not implemented" reminder.
- Persists the latest captured bundle to
  `macmarket.trueMomentumPreviewEvidence.latest`, keyed by the queue
  signature so stale caches across different queues are discarded.

### What it does NOT do

- **No new queue candidates.** The bundle only re-frames already
  matched Phase C1 rows.
- **No ranking math change.** `build_momentum_ranking_contribution`,
  `DeterministicRankingEngine`, Phase B1 / B6 / B6.x wiring are
  byte-identical.
- **No queue sorting change.**
- **No approval / promote / save / paper-order / settle / replay /
  options-preview behavior change.**
- **No backend mutation.** No DB write, no migration, no LLM call, no
  provider / market-data call. Phase C2 is frontend-only.
- **No Phase C active behavior.** `MACMARKET_TRUE_MOMENTUM_STRATEGY_MODE=active`
  remains reserved — Phase C1 still degrades it to
  `research_preview` with the
  `true_momentum_strategy_active_mode_not_implemented` reason code.

### Surfaces

- **Pure helpers** —
  `apps/web/lib/true-momentum-preview-evidence.ts`
  (`buildTrueMomentumPreviewEvidenceBundle`,
  `summarizeTrueMomentumPreviewEvidence`,
  `partitionTrueMomentumPreviewEvidenceByFamily`,
  `topTrueMomentumPreviewEvidence`,
  `trueMomentumPreviewEvidenceWarnings`,
  `sanitizeTrueMomentumPreviewEvidenceNote`,
  `buildTrueMomentumPreviewEvidenceMarkdown`,
  `buildTrueMomentumPreviewEvidenceJson`,
  `validateTrueMomentumPreviewEvidenceBundle`,
  `trueMomentumPreviewEvidenceTagLabel`,
  `trueMomentumPreviewEvidenceTagTone`,
  `TRUE_MOMENTUM_PREVIEW_EVIDENCE_DETERMINISTIC_NOTE`,
  `TRUE_MOMENTUM_PREVIEW_EVIDENCE_STORAGE_KEY`).
- **Reusable component** —
  `apps/web/components/recommendations/true-momentum-preview-evidence-panel.tsx`
  (`<TrueMomentumPreviewEvidencePanel candidates previewResult
  universeSymbols b8Snapshot b8OutcomeReview persistLatest
  initialBundle />`).
- **C1 integration** —
  `apps/web/components/recommendations/true-momentum-strategy-preview-panel.tsx`
  mounts the evidence panel below its preview table whenever Phase C1
  produced at least one preview row.

### Recommended workflow

1. Run the active Momentum queue from Recommendations.
2. Review the Phase C1 family preview panel.
3. Press **Capture True Momentum Preview Evidence** to record the
   current C1 classification + operator notes / tags into a Phase C2
   evidence bundle.
4. Capture a Phase B7 trial-journal snapshot and a Phase B8 outcome
   review for the same session.
5. Compare the exported Phase C2 preview evidence (Markdown / JSON)
   against the Phase B8 outcome reviews before any Phase C3 / active
   Phase C authorization.

### Still pending (carried forward)

- Accumulated B8 outcome evidence corpus.
- Real Thinkorswim visual/manual parity evidence (typically `parity_mode: "visual_attestation"`, which records operator-entered ToS and MacMarket rendered chart values from screenshots; no bars or study CSV needed because ToS does not export either for this workflow).
- Operator authorization before any active Phase C.

## Phase C2.1 — link B7/B8 trial evidence into the C2 bundle

Phase C2.1 wires the existing Phase B7 trial-journal snapshot and the
Phase B8 outcome review into the Phase C2 preview-evidence bundle.
The C2 panel can now show whether the captured B8 evidence belongs to
the current queue, and the exported Markdown / JSON carry the linked
B8 metadata.

It is still **frontend-only and research-only**. No backend write, no
DB row, no migration, no LLM call. No active Phase C activation. No
ranking / queue-sorting / approval / paper-order / replay / options
behavior change.

### What it does

- Adds a shared `computeMomentumQueueSignature` helper that builds a
  stable `rank::symbol::strategy` signature from any iterable of rows
  (live `QueueCandidate[]` or `MomentumTrialSnapshot.candidates`).
  Sorted so reorder-free re-renders produce the same signature.
- The C2 evidence panel rehydrates the latest B7 snapshot and B8
  outcome review from `localStorage` (read-only — never writes back)
  using the canonical storage keys
  (`macmarket.momentumTrial.latest` / `macmarket.momentumTrial.outcome.latest`).
- The C2 bundle gains
  `b8_snapshot_link_status` (`linked` / `missing` / `mismatch`) and
  `b8_outcome_review_link_status`
  (`linked` / `missing` / `mismatch` / `partial`) plus
  `b8_snapshot_generated_at`, `b8_outcome_generated_at`,
  `b8_snapshot_candidate_count`, `b8_outcome_reviewed_count`,
  `b8_outcome_summary` (compact per-tag counts),
  `linked_b8_snapshot_schema_version`,
  `linked_b8_outcome_schema_version`, and a
  human-readable `b8_link_warning`. Existing `b8_snapshot_present` /
  `b8_outcome_review_present` boolean flags are preserved for
  back-compat.
- The "partial" outcome status fires when the outcome review snapshot
  signature matches but every candidate outcome is still tagged
  `unclear`.

### UI changes

- The B8 snapshot + B8 outcome review badges now show the resolved
  status (`linked` / `missing` / `mismatch` / `partial`) rather than
  a binary "yes / no".
- Two short copy lines summarize the snapshot + outcome status with
  the recommended operator copy
  ("Linked to current Momentum Trial Journal snapshot…",
  "A B8 snapshot exists, but it belongs to a different queue.", etc.).
- When linked, the snapshot timestamp + per-tag outcome counts are
  surfaced inline.
- The C1 preview panel now suppresses its trailing deterministic note
  + "Still pending" caveat line whenever the C2 evidence panel is
  mounted (i.e. when previews exist). The C2 panel already renders
  both lines as the canonical owner; this removes the previously
  visible duplicate guardrail copy.
- Capture / export / clear buttons remain enabled regardless of B8
  state — Phase C2.1 never blocks the operator on missing B8 evidence.

### Markdown / JSON export

- A new Markdown section "## Linked B8 Trial Evidence" appears between
  the header bullets and the existing "## Summary" section. It
  enumerates B8 snapshot + outcome status + timestamps + candidate
  counts + per-tag outcome counts, with an explicit "missing" line
  when no B8 evidence is available, and the resolved
  `b8_link_warning` text when applicable.
- The JSON export carries every new bundle field
  (`b8_snapshot_link_status`, `b8_outcome_review_link_status`,
  timestamps, candidate / reviewed counts, compact outcome summary,
  schema versions, warning).

### What it does NOT do

- No backend mutation.
- No DB row, no migration, no LLM call, no provider / market-data
  call.
- No new queue candidates.
- No ranking math change.
- No queue sorting change.
- No approval / promote / save / paper-order / settle / replay /
  options-preview behavior change.
- No Phase C activation. `MACMARKET_TRUE_MOMENTUM_STRATEGY_MODE=active`
  remains reserved.

### Still pending

- Accumulated B8 outcome evidence corpus.
- Real Thinkorswim visual/manual parity evidence (typically `parity_mode: "visual_attestation"`, which records operator-entered ToS and MacMarket rendered chart values from screenshots; no bars or study CSV needed because ToS does not export either for this workflow).
- Operator authorization before any active Phase C.

## Phase C2.2 — live B8 outcome linkage + Ranked queue scroll polish

Phase C2.2 fixes the deployed-state mismatch between the Phase B8
outcome review (rendered live on the same page) and the Phase C2
evidence panel's "B8 outcome review: missing" badge, and adds the
scroll container the operator expected on the Ranked queue panel.

It is still **frontend-only and research-only**. No backend write, no
DB row, no migration, no LLM call. No Phase C activation. No ranking,
queue sorting, approval, paper-order, replay, or options-preview
behavior change.

### Live B8 linkage (state lifting)

- `MomentumTrialJournal` now exposes two callbacks,
  `onSnapshotChange(snapshot)` and `onOutcomeReviewChange(review)`,
  and threads the outcome callback through to
  `MomentumTrialOutcomeReviewPanel`.
- The Recommendations page lifts the live B7 snapshot and B8 outcome
  review state and passes them straight to
  `<TrueMomentumStrategyPreviewPanel>`, which forwards them through
  to `<TrueMomentumPreviewEvidencePanel>`.
- The evidence panel keeps its existing `localStorage` rehydration as
  a fallback for fresh page loads, but the lifted state now takes
  precedence and updates the C2 link status the moment the operator
  tags an outcome in B8.
- Linkage uses the *embedded* B7 snapshot signature
  (`review.snapshot.candidates`) — a 14-row outcome review against a
  45-row queue still links as long as the embedded snapshot matches
  the live queue.

### Resolved deployed scenario

- B8 snapshot signature matches the queue → `b8_snapshot_link_status: "linked"`.
- B8 outcome review with `worked_count = 1` / `unclear_count = 13` →
  `b8_outcome_review_link_status: "linked"` (the operator has tagged
  at least one row beyond `unclear`).
- The compact outcome counts line + `Reviewed candidates` /
  `Unclear outcomes` summary cards render the same numbers the B8
  panel shows.
- The Markdown export's "Linked B8 Trial Evidence" section lists the
  resolved status and per-tag counts; the JSON export carries every
  link field.

### What still does NOT link

- A B8 outcome review whose embedded `review.snapshot` signature
  differs from the live queue → `mismatch` with the existing warning
  copy.
- No B8 outcome review in lifted state or `localStorage` → `missing`
  with the existing pointer copy.
- The C2 evidence capture and Markdown / JSON export remain enabled
  regardless of B8 state.

### Ranked queue scroll polish

The Ranked queue candidates table on the Recommendations page is now
wrapped in the same scrollable container pattern as the Persisted
recommendations panel (`maxHeight: 360`, `overflowY: "auto"`, a themed
border, and `data-testid="ranked-queue-scroll-container"`). The
wrapper shows roughly 10 rows at a time before scrolling.

- Row selection behavior, the compare-checkbox column, and the
  ranking order are unchanged.
- No promote / approve / route / paper-order paths are touched.
- Persisted recommendations keeps its existing scroll wrapper.

### Still pending

- Accumulated B8 outcome evidence corpus.
- Real Thinkorswim visual/manual parity evidence (typically `parity_mode: "visual_attestation"`, which records operator-entered ToS and MacMarket rendered chart values from screenshots; no bars or study CSV needed because ToS does not export either for this workflow).
- Operator authorization before any active Phase C.

## Phase C3 — research cohort review

Phase C3 adds a local research cohort archive on top of Phase C2.
Operators archive each captured C2 evidence bundle, the C3 panel rolls
up family-level previews and B8 outcome counts across sessions, and
exports a deterministic Markdown / JSON report with a readiness label.

Still **frontend-only and research-only**: no backend write, no DB
row, no migration, no LLM call. No queue candidates. No ranking math
change. No approval / promote / save / paper-order / settle / replay /
options-preview behavior change.

### What it does

- `apps/web/lib/true-momentum-cohort-review.ts` — pure helpers:
  `buildTrueMomentumCohortRecord`, `addTrueMomentumCohortRecord`,
  `replaceTrueMomentumCohortRecord`, `removeTrueMomentumCohortRecord`,
  `summarizeTrueMomentumCohortArchive`,
  `summarizeTrueMomentumFamilyCohort`,
  `buildTrueMomentumCohortReviewReport`,
  `classifyTrueMomentumCohortReadiness`,
  `buildTrueMomentumCohortMarkdown`,
  `buildTrueMomentumCohortJson`,
  `validateTrueMomentumCohortArchive`,
  `sanitizeTrueMomentumCohortNote`,
  `trueMomentumCohortReadinessLabel`,
  `trueMomentumCohortReadinessTone`, plus the
  `macmarket.trueMomentumCohortReview.archive` localStorage key and
  `phase_c3.v1` archive / report schema versions.
- `apps/web/components/recommendations/true-momentum-cohort-review-panel.tsx` —
  reusable `<TrueMomentumCohortReviewPanel currentBundle persistLatest
  compact initialArchive />` rendered inside the Phase C2 evidence
  panel. Summary cards (archived sessions / total preview rows /
  family counts / linked B8 reviews / parity-pending records),
  per-outcome counts, family rollups, archived record table, plus
  Add / Export Markdown / Export JSON / Clear / per-row Remove
  buttons.
- The Recommendations page does not need to be modified — C3 is
  mounted by the C2 panel automatically once a bundle exists.

### Readiness statuses

| Status | Meaning |
|---|---|
| `insufficient_evidence` | Default. No records, < 3 records, or every outcome is still `unclear`. |
| `parity_blocked` | Thinkorswim parity is pending across ≥ 50% of archived records. |
| `promising_research` | ≥ 5 tagged outcomes and positive outcomes lead negatives by ≥ 2. |
| `mixed_research` | Tagged outcomes exist but balance is neither strongly positive nor strongly negative. |
| `needs_operator_review` | Negatives ≥ positives but not 2× negatives. |
| `not_recommended_for_activation` | Negatives ≥ 2× positives across archived records. |

Phase C3 **never** emits "ready for live" or "activate now" wording.
The strongest positive label is `promising_research` — "research
evidence supports further review", not "approved".

### Archive behavior

- LocalStorage key: `macmarket.trueMomentumCohortReview.archive`.
- Records are deduped by `record_id` (default
  `${queue_signature}::${source_bundle_generated_at}`).
- Add / remove / replace helpers never mutate the input archive.
- Stale / corrupt localStorage is ignored and replaced with a clean
  empty archive on next write.
- No backend persistence. No DB row. No migration. No LLM call.

### Exports

Markdown report sections (always emitted):

1. Header (`# True Momentum Cohort Review (Phase C3)`) + generated
   timestamp + schema version + archived session count + readiness
   status + readiness caveats.
2. `## Archive summary` — total preview rows, family-level counts,
   parity-pending records, records-with-outcome-review.
3. `## Outcome counts (across archived B8 reviews)` — per-tag counts
   plus tagged-vs-total tally.
4. `## Family summaries` — one line per planned True Momentum family.
5. `## Archived records` — table of every archived session
   (`Captured at`, universe count, preview rows, B8 snapshot status,
   B8 outcome review status + worked/unclear counts, parity-pending
   count, review tags).
6. `## Pending prerequisites for any active Phase C`.
7. Trailing deterministic guardrail line.

JSON envelope:
`{ schema_version: "phase_c3.v1", report, archive, deterministic_note }`.

### Operator workflow

1. Refresh the active Momentum queue.
2. Capture a Phase B7 trial snapshot.
3. Tag at least one B8 outcome.
4. Capture a Phase C2 preview evidence bundle.
5. Press **Add current evidence bundle to cohort archive** inside the
   Phase C3 panel.
6. Repeat across a representative cross-sector / cross-regime cohort.
7. Export Cohort Markdown / Cohort JSON to archive the corpus
   alongside the per-session B7 / B8 / C2 artifacts.

### Still pending

- Larger accumulated B8 outcome evidence corpus.
- Real Thinkorswim visual/manual parity evidence (typically `parity_mode: "visual_attestation"`, which records operator-entered ToS and MacMarket rendered chart values from screenshots; no bars or study CSV needed because ToS does not export either for this workflow).
- Operator authorization before any active Phase C.

## Phase C4 — True Momentum strategy-family research context integration

Phase C4 is a frontend-only research-only integration: it surfaces
the existing Phase C1 family classification, Phase C3 cohort
readiness, and the Thinkorswim visual-attestation parity status for
the **currently selected Recommendations queue candidate** as a
single operator-readable context card. Phase C4 explicitly does
**not**:

- generate queue candidates,
- change recommendation ranking, queue sorting, promote / make-active
  / save / paper-order, replay, or options behavior,
- approve / reject / size / route trades,
- activate Phase C strategy families,
- mutate the source candidates or the queue,
- call providers, the database, or an LLM.

### Surface

`apps/web/lib/true-momentum-strategy-context.ts` exposes pure helpers
(`buildTrueMomentumStrategyContext`,
`buildTrueMomentumTriggerChecklist`,
`classifyTrueMomentumStrategyActivationReadiness`,
`findSelectedSymbolParitySummary`,
`summarizeTrueMomentumStrategyContext`,
`collectTrueMomentumStrategyContextSurfaces`). The
`<TrueMomentumStrategyContextCard />` component renders the bundle on
the Recommendations page beneath the existing Phase C1 preview panel
when an operator selects a queue row.

### Trigger-readiness checklist

The card renders a family-specific checklist:

- **Continuation** — Total score Bull / Max Bull or ≥ 80; True
  Momentum above EMA; Trend score ≥ 70; Momo score ≥ 70; HiLo score
  > 0 or thrust confirmed; no no-trade warning; no reversal warning;
  existing deterministic price setup; parity / evidence does not
  block research review.
- **Pullback** — Bull / Max Bull or ≥ 80; pullback signal active OR
  source strategy is Pullback / Trend Continuation; True Momentum
  above EMA or recently crossed above EMA; HiLo score not strongly
  negative; no reversal warning; existing deterministic pullback
  setup; risk / invalidation captured.
- **Reversal / Weakening Watch** — Reversal OR no-trade warning OR
  Bear / Max Bear contradiction OR total_score ≤ -50; watch-only;
  never proposes entry; existing candidate downgraded to research
  context.

Each item carries `status: pass | fail | warning | unavailable`,
`reason`, and `source_field`. Missing fields degrade to
`unavailable`. The checklist never uses trade-execution language.

### Activation-readiness status

`classifyTrueMomentumStrategyActivationReadiness` returns one of:

| Status | Meaning |
|---|---|
| `research_ready` | Family matches strongly and no blocking caveats remain |
| `needs_more_evidence` | Parity partial / cohort insufficient / no clear signal |
| `parity_blocked` | Selected symbol's parity fixture failed broadly |
| `composite_mismatch_review` | Selected symbol's parity shows oscillator aligned but composite mismatch (XLP-style) |
| `warning_blocked` | no_trade or reversal warning active on a non-reversal-watch family |
| `not_applicable` | No family match for the selected candidate |
| `watch_only` | Family is `true_momentum_reversal_watch` |

The card never returns "approved" or "ready for live". Activation
readiness is research context only.

### XLP example

XLP currently fails visual attestation on composite score only:
oscillator (True Momentum / EMA) is aligned, but `total_score` and
`total_label` diverge. The Phase C4 card classifies a selected XLP
candidate as `composite_mismatch_review`, surfaces the
*"oscillator aligned but composite total score differs"* caveat, and
keeps unrelated symbols (SPY / XLK / XLE) at `research_ready` even
though the global visual attestation status is `visual_failed`.

### Strategy Workbench / blueprints

Strategy Workbench-style blueprints stay docs-only research
descriptions (`status: research_preview`,
`generates_candidates: false`, `activation: reserved`,
`prerequisites: [B8 outcome evidence corpus, C3 cohort review,
visual parity review, operator authorization]`). No active generator
function was added.

### Phase C research closeout — what shipped, blockers, next phase

Phase C is now closed out as **research-only**. The full closeout
posture, what shipped (C0 / C1 / C2 / C2.1 / C2.2 / C3 / C4 / C4.1),
the explicit not-shipped list (active strategy generation, queue
candidate generation, auto approval, auto sizing, order routing),
the current parity state (SPY pass, XLK pass, XLE pass, XLP
oscillator aligned / composite mismatch), the remaining blockers
(resolve / document XLP composite mismatch, accumulate B8 outcome
evidence, accumulate C3 cohort evidence, operator authorization),
and the next allowed phase (C5 research candidate proposal — still
non-active and non-ordering) are documented in
[`true-momentum-phase-c-closeout.md`](true-momentum-phase-c-closeout.md).
The Phase C closeout helper + card surface this on the
Recommendations page inside the "True Momentum research evidence"
collapsible. Active Phase C strategy generation is **not
implemented**; no True Momentum queue candidates are generated;
recommendation approval and paper-order behavior remain
unchanged.

### Phase C4.1 — True Momentum UX consolidation

Phase C4.1 is a frontend-only UX consolidation. The Recommendations
page now leads with the Phase C4 selected-candidate card and groups
every other Momentum / True Momentum research surface into clearly
labeled collapsibles. No backend behavior changes.

Order on the Recommendations page:

1. **True Momentum operator guide** (compact mini-guide).
2. **True Momentum Strategy Context — selected candidate** (Phase C4
   card; empty state when no candidate selected).
3. **Momentum ranking diagnostics** — collapsible `<details>`
   wrapping the Phase B4 Momentum Shadow Impact Review (global
   ranking diagnostic, not a selected-candidate evaluation).
4. **True Momentum research evidence** — collapsible `<details>`
   wrapping:
   - C1 Family Preview — current queue (with C2 Preview Evidence +
     C3 Cohort Review nested inside the C1 panel as before).
   - B7/B8 Trial Journal — capture and tag outcomes.

Phase C4.1 does **not** change ranking, queue sorting, recommendation
approval, promote / save / paper-order, replay, or options behavior,
and does not generate queue candidates. All capture / export /
archive buttons (Capture Momentum Trial Snapshot, Export Outcome
Markdown/JSON, Capture True Momentum Preview Evidence, Add current
evidence bundle to cohort archive, Export Cohort Markdown/JSON,
Shadow impact sorting/details) still work — they live inside the
expanded subsection that owns them.

The Phase C4 card now carries an explicit scope note on both states
("This card evaluates the selected queue candidate only. … and does
not approve, reject, size, or route trades.") plus the
"How to use True Momentum on this page" operator guide just above it.

Recommended operator workflow:

1. Select a queue candidate.
2. Read True Momentum Strategy Context for that candidate.
3. Use the chart to confirm price context.
4. Capture trial / evidence snapshots only when reviewing a session
   (expand the research evidence collapsible).
5. Approval and paper orders remain manual.

## Related documents

- [`momentum-intelligence-layer.md`](momentum-intelligence-layer.md) —
  full Momentum charter, Phase A/B specifications, Phase A/B closeout.
- [`momentum-phase-closeout.md`](momentum-phase-closeout.md) — operator
  checklist summarizing what shipped, current env knobs, outstanding
  items, and Phase C posture.
