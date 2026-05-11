import React from "react";
import type { ReactNode } from "react";
import { createRequire } from "module";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/components/operator-ui", async () => {
  const ReactModule = await import("react");
  return {
    Card: ({ title, children }: { title?: string; children: ReactNode }) =>
      ReactModule.createElement(
        "section",
        {},
        title ? ReactModule.createElement("h3", {}, title) : null,
        children,
      ),
    EmptyState: ({ title, hint }: { title: string; hint: string }) =>
      ReactModule.createElement("div", { "data-testid": "empty" }, `${title} ${hint}`),
    StatusBadge: ({ tone, children }: { tone?: string; children: ReactNode }) =>
      ReactModule.createElement(
        "span",
        { className: `op-badge op-badge-${tone ?? "neutral"}` },
        children,
      ),
  };
});

import {
  MomentumTrialJournal,
  MomentumTrialJournalView,
  MOMENTUM_TRIAL_JOURNAL_STORAGE_KEY,
} from "@/components/recommendations/momentum-trial-journal";
import {
  buildMomentumTrialJson,
  buildMomentumTrialMarkdown,
  buildMomentumTrialSnapshot,
  MOMENTUM_TRIAL_JOURNAL_DETERMINISTIC_NOTE,
  type MomentumTrialSnapshot,
} from "@/lib/momentum-trial-journal";
import type {
  MomentumRankingContribution,
  QueueCandidate,
} from "@/lib/recommendations";

const require = createRequire(import.meta.url);
const { renderToStaticMarkup } = require("react-dom/server") as {
  renderToStaticMarkup: (element: ReactNode) => string;
};

function contribution(overrides: Partial<MomentumRankingContribution> = {}): MomentumRankingContribution {
  return {
    mode: "active",
    enabled: true,
    applied: true,
    total_contribution: 20,
    shadow_contribution: 20,
    momentum_alignment_score: 10,
    trend_alignment_score: 6,
    hilo_confirmation_bonus: 4,
    reversal_warning_penalty: 0,
    no_trade_warning: false,
    pullback_signal: false,
    reversal_warning: false,
    parity_status: "pending_thinkorswim_fixture_validation",
    higher_timeframe_source: "derived_from_chart_bars",
    total_score: 80,
    total_label: "Bull",
    trend_score: 75,
    momo_score: 65,
    inferred_direction: "long",
    calculation_notes: [],
    reason_codes: [],
    active_delta_scale: 0.35,
    raw_total_contribution: 20,
    applied_score_delta: 0.07,
    ...overrides,
  };
}

function candidate(overrides: Partial<QueueCandidate> = {}): QueueCandidate {
  return {
    rank: 1,
    symbol: "SPY",
    strategy: "Event Continuation",
    workflow_source: "test_provider",
    timeframe: "1D",
    status: "top_candidate",
    score: 0.877,
    expected_rr: 2.0,
    confidence: 0.7,
    reason_text: "",
    thesis: "",
    momentum_contribution: contribution(),
    score_before_momentum: 0.807,
    score_after_momentum: 0.877,
    momentum_score_delta: 0.07,
    momentum_realized_score_delta: 0.07,
    score_consistency_status: "ok",
    ...overrides,
  };
}

const ACTIVE_QUEUE: QueueCandidate[] = [
  candidate({
    rank: 1,
    symbol: "XLK",
    score: 0.967,
    score_before_momentum: 0.897,
  }),
  candidate({
    rank: 2,
    symbol: "IWM",
    score: 0.948,
    score_before_momentum: 0.878,
  }),
  candidate({
    rank: 3,
    symbol: "QQQ",
    score: 0.917,
    score_before_momentum: 0.847,
  }),
];

const WARNING_QUEUE: QueueCandidate[] = [
  candidate({
    symbol: "AAA",
    momentum_contribution: contribution({
      reversal_warning: true,
      reason_codes: ["momentum_reversal_warning", "thinkorswim_parity_pending"],
    }),
  }),
  candidate({
    symbol: "BBB",
    momentum_contribution: contribution({
      no_trade_warning: true,
      reason_codes: ["momentum_no_trade_warning"],
    }),
  }),
];

describe("MomentumTrialJournal (container)", () => {
  it("renders empty state when no snapshot has been captured", () => {
    const html = renderToStaticMarkup(
      <MomentumTrialJournal candidates={ACTIVE_QUEUE} persistLatest={false} />,
    );
    expect(html).toContain("Active Momentum Trial Journal");
    expect(html).toContain("Capture Momentum Trial Snapshot");
    expect(html).toContain("No trial snapshot captured yet");
    expect(html).toContain(MOMENTUM_TRIAL_JOURNAL_DETERMINISTIC_NOTE);
  });

  it("renders an operator note input", () => {
    const html = renderToStaticMarkup(
      <MomentumTrialJournal candidates={ACTIVE_QUEUE} persistLatest={false} />,
    );
    expect(html).toContain("Operator note");
    expect(html).toContain("momentum-trial-journal-note-input");
  });

  it("disables capture button when no candidates are loaded", () => {
    const html = renderToStaticMarkup(
      <MomentumTrialJournal candidates={[]} persistLatest={false} />,
    );
    // disabled buttons are still rendered; the empty-state hint differs.
    expect(html).toContain("disabled");
    expect(html).toContain("Generate a recommendation queue first");
  });

  it("renders the captured snapshot summary via initialSnapshot", () => {
    const snapshot = buildMomentumTrialSnapshot(ACTIVE_QUEUE, {
      operatorNote: "XLK leading; IWM follow.",
    });
    const html = renderToStaticMarkup(
      <MomentumTrialJournal
        candidates={ACTIVE_QUEUE}
        initialSnapshot={snapshot}
        persistLatest={false}
      />,
    );
    expect(html).toContain("Snapshot captured");
    expect(html).toContain("momentum-trial-journal-snapshot");
    expect(html).toContain("Top candidates");
    expect(html).toContain("XLK");
    expect(html).toContain("IWM");
    expect(html).toContain("QQQ");
    expect(html).toContain("Operator note");
    expect(html).toContain("XLK leading; IWM follow.");
  });

  it("exposes copy / download / clear buttons when a snapshot exists", () => {
    const snapshot = buildMomentumTrialSnapshot(ACTIVE_QUEUE);
    const html = renderToStaticMarkup(
      <MomentumTrialJournal
        candidates={ACTIVE_QUEUE}
        initialSnapshot={snapshot}
        persistLatest={false}
      />,
    );
    expect(html).toContain("Copy Markdown");
    expect(html).toContain("Download Markdown");
    expect(html).toContain("Download JSON");
    expect(html).toContain("Clear snapshot");
    expect(html).toContain("momentum-trial-journal-copy-markdown");
    expect(html).toContain("momentum-trial-journal-download-json");
  });

  it("never renders forbidden action language", () => {
    const html = renderToStaticMarkup(
      <MomentumTrialJournal
        candidates={ACTIVE_QUEUE}
        initialSnapshot={buildMomentumTrialSnapshot(ACTIVE_QUEUE)}
        persistLatest={false}
      />,
    ).toLowerCase();
    for (const phrase of ["buy now", "sell now", "enter now", "short now", "auto approve", "route order"]) {
      expect(html).not.toContain(phrase);
    }
  });
});

describe("MomentumTrialJournalView (presentational)", () => {
  it("renders summary cards and top candidates", () => {
    const snapshot = buildMomentumTrialSnapshot(ACTIVE_QUEUE);
    const html = renderToStaticMarkup(<MomentumTrialJournalView snapshot={snapshot} />);
    expect(html).toContain("momentum-trial-journal-summary");
    expect(html).toContain("Candidates captured");
    expect(html).toContain("Active / shadow / off");
    expect(html).toContain("XLK");
    expect(html).toContain("IWM");
    expect(html).toContain("QQQ");
    expect(html).toContain("Top candidates");
  });

  it("uses Phase B7.1 summary card labels", () => {
    const snapshot = buildMomentumTrialSnapshot(ACTIVE_QUEUE);
    const html = renderToStaticMarkup(<MomentumTrialJournalView snapshot={snapshot} />);
    expect(html).toContain("Trade warnings");
    expect(html).toContain("Operational caveats");
    expect(html).toContain("Positive / negative / zero contribution");
    expect(html).toContain("momentum-trial-journal-summary-trade-warnings");
    expect(html).toContain("momentum-trial-journal-summary-operational-caveats");
  });

  it("renders the Trade warnings section with no-trade / reversal rows", () => {
    const snapshot = buildMomentumTrialSnapshot(WARNING_QUEUE);
    const html = renderToStaticMarkup(<MomentumTrialJournalView snapshot={snapshot} />);
    expect(html).toContain("momentum-trial-journal-trade-warnings-table");
    expect(html).toContain("Trade warnings");
    expect(html).toContain("reversal warning");
    expect(html).toContain("no trade warning");
  });

  it("renders the Operational caveats section with parity-pending rows when present", () => {
    const snapshot = buildMomentumTrialSnapshot(WARNING_QUEUE);
    const html = renderToStaticMarkup(<MomentumTrialJournalView snapshot={snapshot} />);
    expect(html).toContain("momentum-trial-journal-operational-caveats-table");
    expect(html).toContain("Operational caveats");
    expect(html).toContain("parity pending");
  });

  it("shows 'No trade warnings captured.' when only parity caveats exist", () => {
    const snapshot = buildMomentumTrialSnapshot([
      candidate({
        symbol: "AAA",
        momentum_contribution: contribution({
          reason_codes: ["thinkorswim_parity_pending"],
        }),
      }),
    ]);
    const html = renderToStaticMarkup(<MomentumTrialJournalView snapshot={snapshot} />);
    expect(html).toContain("No trade warnings captured.");
    expect(html).toContain("momentum-trial-journal-operational-caveats-table");
    // The operational caveats table itself should render the parity row.
    expect(html).toContain("parity pending");
  });

  it("shows 'No operational caveats captured.' when only trade warnings exist", () => {
    const snapshot = buildMomentumTrialSnapshot([
      candidate({
        symbol: "BBB",
        momentum_contribution: contribution({
          no_trade_warning: true,
          reason_codes: ["momentum_no_trade_warning"],
        }),
      }),
    ]);
    const html = renderToStaticMarkup(<MomentumTrialJournalView snapshot={snapshot} />);
    expect(html).toContain("No operational caveats captured.");
    expect(html).toContain("no trade warning");
  });

  it("hides both tables in compact mode", () => {
    const snapshot = buildMomentumTrialSnapshot(WARNING_QUEUE);
    const html = renderToStaticMarkup(
      <MomentumTrialJournalView snapshot={snapshot} compact />,
    );
    expect(html).not.toContain("momentum-trial-journal-trade-warnings-table");
    expect(html).not.toContain("momentum-trial-journal-operational-caveats-table");
  });

  it("renders the universe block as 'Captured symbols' when universe_kind is captured", () => {
    const snapshot = buildMomentumTrialSnapshot(ACTIVE_QUEUE);
    const html = renderToStaticMarkup(<MomentumTrialJournalView snapshot={snapshot} />);
    expect(html).toContain("Captured symbols");
    expect(html).not.toContain("Evaluated universe");
    expect(html).toContain('data-universe-kind="captured"');
  });

  it("renders the universe block as 'Evaluated universe' when universeSymbols was passed", () => {
    const snapshot = buildMomentumTrialSnapshot(ACTIVE_QUEUE, {
      universeSymbols: ["XLK", "IWM", "QQQ", "DIA", "SPY"],
    });
    const html = renderToStaticMarkup(<MomentumTrialJournalView snapshot={snapshot} />);
    expect(html).toContain("Evaluated universe");
    expect(html).toContain("DIA");
    expect(html).toContain('data-universe-kind="evaluated"');
  });

  it("does NOT render the deterministic guardrail copy (container owns it)", () => {
    const snapshot = buildMomentumTrialSnapshot(ACTIVE_QUEUE);
    const html = renderToStaticMarkup(<MomentumTrialJournalView snapshot={snapshot} />);
    // Phase B7.1: the note is rendered exactly once by the outer
    // container so it is not duplicated when the view is nested.
    expect(html).not.toContain(MOMENTUM_TRIAL_JOURNAL_DETERMINISTIC_NOTE);
  });
});

describe("MomentumTrialJournal — Phase B7.1 deterministic-note + universe", () => {
  it("renders the deterministic guardrail copy exactly once in empty state", () => {
    const html = renderToStaticMarkup(
      <MomentumTrialJournal candidates={ACTIVE_QUEUE} persistLatest={false} />,
    );
    const occurrences = html.split(MOMENTUM_TRIAL_JOURNAL_DETERMINISTIC_NOTE).length - 1;
    expect(occurrences).toBe(1);
  });

  it("renders the deterministic guardrail copy exactly once when a snapshot is captured", () => {
    const snapshot = buildMomentumTrialSnapshot(ACTIVE_QUEUE, {
      operatorNote: "XLK leading; IWM follow.",
    });
    const html = renderToStaticMarkup(
      <MomentumTrialJournal
        candidates={ACTIVE_QUEUE}
        initialSnapshot={snapshot}
        persistLatest={false}
      />,
    );
    const occurrences = html.split(MOMENTUM_TRIAL_JOURNAL_DETERMINISTIC_NOTE).length - 1;
    expect(occurrences).toBe(1);
  });

  it("respects the universeSymbols prop end-to-end (captured → snapshot → render)", () => {
    const universe = ["XLK", "IWM", "QQQ", "SPY", "DIA", "XLE", "XLV"];
    const snapshot = buildMomentumTrialSnapshot(ACTIVE_QUEUE, {
      universeSymbols: universe,
    });
    const html = renderToStaticMarkup(
      <MomentumTrialJournal
        candidates={ACTIVE_QUEUE}
        universeSymbols={universe}
        initialSnapshot={snapshot}
        persistLatest={false}
      />,
    );
    expect(html).toContain("Evaluated universe");
    for (const sym of universe) expect(html).toContain(sym);
  });
});

describe("MomentumTrialJournal copy + download payloads", () => {
  it("Markdown payload from view-level snapshot is well-formed", () => {
    const snapshot = buildMomentumTrialSnapshot(ACTIVE_QUEUE, {
      operatorNote: "captured for compare next session",
    });
    const md = buildMomentumTrialMarkdown(snapshot);
    expect(md).toContain("# Momentum Trial Journal Snapshot");
    expect(md).toContain("XLK");
    expect(md).toContain("Operator note");
    expect(md).toContain("captured for compare next session");
  });

  it("JSON payload round-trips", () => {
    const snapshot = buildMomentumTrialSnapshot(ACTIVE_QUEUE);
    const json = buildMomentumTrialJson(snapshot);
    const parsed = JSON.parse(json) as { snapshot: MomentumTrialSnapshot };
    expect(parsed.snapshot.candidates.length).toBe(ACTIVE_QUEUE.length);
  });
});

describe("MomentumTrialJournal localStorage", () => {
  it("storage key is stable and namespaced", () => {
    expect(MOMENTUM_TRIAL_JOURNAL_STORAGE_KEY).toBe("macmarket.momentumTrial.latest");
  });
});
