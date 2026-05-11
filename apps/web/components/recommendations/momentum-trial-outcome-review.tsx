"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";

import { Card, EmptyState, StatusBadge } from "@/components/operator-ui";
import {
  buildMomentumOutcomeJson,
  buildMomentumOutcomeMarkdown,
  buildMomentumTrialOutcomeReview,
  candidateOutcomeDefaults,
  isMomentumTrialOutcomeTag,
  momentumCandidateOutcomeKey,
  MOMENTUM_TRIAL_OUTCOME_DETERMINISTIC_NOTE,
  MOMENTUM_TRIAL_OUTCOME_STORAGE_KEY,
  MOMENTUM_TRIAL_OUTCOME_TAGS,
  outcomeTagLabel,
  outcomeTagTone,
  sanitizeMomentumOutcomeNote,
  summarizeMomentumTrialOutcomes,
  type MomentumTrialCandidateOutcome,
  type MomentumTrialOutcomeReview,
  type MomentumTrialOutcomeTag,
} from "@/lib/momentum-trial-outcomes";
import type { MomentumTrialSnapshot } from "@/lib/momentum-trial-journal";

const NOTE_STYLE: React.CSSProperties = {
  margin: 0,
  color: "var(--op-muted, #7a8999)",
  fontSize: "0.78rem",
  lineHeight: 1.5,
};

const SUMMARY_CARD_STYLE: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 2,
  padding: "6px 10px",
  borderRadius: 6,
  background: "rgba(15, 24, 34, 0.45)",
  border: "1px solid rgba(115, 138, 163, 0.18)",
  minWidth: 110,
};

const SUMMARY_LABEL_STYLE: React.CSSProperties = {
  color: "var(--op-muted, #7a8999)",
  fontSize: "0.72rem",
  textTransform: "uppercase",
  letterSpacing: "0.04em",
};

const SUMMARY_VALUE_STYLE: React.CSSProperties = {
  fontVariantNumeric: "tabular-nums",
  fontSize: "1.05rem",
  fontWeight: 600,
};

const NOTE_INPUT_STYLE: React.CSSProperties = {
  width: "100%",
  minHeight: 56,
  resize: "vertical",
  fontFamily: "inherit",
  fontSize: "0.85rem",
  padding: 8,
  borderRadius: 6,
  background: "rgba(15, 24, 34, 0.55)",
  border: "1px solid rgba(115, 138, 163, 0.28)",
  color: "var(--op-text, #d9e2ef)",
};

const SHORT_NOTE_INPUT_STYLE: React.CSSProperties = {
  width: "100%",
  minHeight: 32,
  resize: "vertical",
  fontFamily: "inherit",
  fontSize: "0.82rem",
  padding: 6,
  borderRadius: 6,
  background: "rgba(15, 24, 34, 0.55)",
  border: "1px solid rgba(115, 138, 163, 0.28)",
  color: "var(--op-text, #d9e2ef)",
};

function downloadTextFile(filename: string, mime: string, content: string): void {
  if (typeof window === "undefined" || typeof document === "undefined") return;
  try {
    const blob = new Blob([content], { type: mime });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  } catch {
    // best-effort
  }
}

function readPersistedOutcomes(
  snapshotGeneratedAt: string,
): {
  outcomes: MomentumTrialCandidateOutcome[];
  globalConclusion: string;
} | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(MOMENTUM_TRIAL_OUTCOME_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as {
      snapshot_generated_at?: string;
      outcomes?: MomentumTrialCandidateOutcome[];
      global_conclusion?: string;
    };
    if (!parsed || typeof parsed !== "object") return null;
    if (parsed.snapshot_generated_at !== snapshotGeneratedAt) return null;
    return {
      outcomes: Array.isArray(parsed.outcomes) ? parsed.outcomes : [],
      globalConclusion:
        typeof parsed.global_conclusion === "string" ? parsed.global_conclusion : "",
    };
  } catch {
    return null;
  }
}

function persistOutcomes(
  snapshotGeneratedAt: string,
  outcomes: ReadonlyArray<MomentumTrialCandidateOutcome>,
  globalConclusion: string,
): void {
  if (typeof window === "undefined") return;
  try {
    const payload = {
      snapshot_generated_at: snapshotGeneratedAt,
      outcomes,
      global_conclusion: globalConclusion,
    };
    window.localStorage.setItem(
      MOMENTUM_TRIAL_OUTCOME_STORAGE_KEY,
      JSON.stringify(payload),
    );
  } catch {
    // best-effort
  }
}

function clearPersistedOutcomes(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(MOMENTUM_TRIAL_OUTCOME_STORAGE_KEY);
  } catch {
    // best-effort
  }
}

export type MomentumTrialOutcomeReviewProps = {
  snapshot: MomentumTrialSnapshot | null | undefined;
  title?: string;
  /**
   * Test-only: render the panel with a pre-existing outcomes list and
   * global conclusion so tests do not depend on user interaction or
   * localStorage.
   */
  initialOutcomes?: ReadonlyArray<MomentumTrialCandidateOutcome> | null;
  initialGlobalConclusion?: string;
  /**
   * Disable localStorage round-trip. Defaults to enabled.
   */
  persistLatest?: boolean;
};

export function MomentumTrialOutcomeReviewPanel({
  snapshot,
  title = "Momentum Trial Outcome Review",
  initialOutcomes = null,
  initialGlobalConclusion = "",
  persistLatest = true,
}: MomentumTrialOutcomeReviewProps) {
  const defaults = useMemo(
    () => (snapshot ? candidateOutcomeDefaults(snapshot) : []),
    [snapshot],
  );

  const [outcomes, setOutcomes] = useState<MomentumTrialCandidateOutcome[]>(() => {
    if (initialOutcomes && initialOutcomes.length > 0) {
      return initialOutcomes.map((o) => ({ ...o }));
    }
    return defaults.map((o) => ({ ...o }));
  });
  const [globalConclusion, setGlobalConclusion] = useState<string>(
    initialGlobalConclusion ?? "",
  );
  const [exportStatus, setExportStatus] = useState<"idle" | "copied" | "failed">(
    "idle",
  );

  // Re-key outcomes whenever the snapshot changes. Re-hydrate from
  // localStorage when persistLatest is enabled and the cached payload
  // matches the current snapshot timestamp.
  useEffect(() => {
    if (!snapshot) {
      setOutcomes([]);
      setGlobalConclusion(initialGlobalConclusion ?? "");
      return;
    }
    let hydrated: { outcomes: MomentumTrialCandidateOutcome[]; globalConclusion: string } | null = null;
    if (persistLatest) {
      hydrated = readPersistedOutcomes(snapshot.generated_at);
    }
    if (hydrated) {
      const review = buildMomentumTrialOutcomeReview(snapshot, {
        existingOutcomes: hydrated.outcomes,
        globalConclusion: hydrated.globalConclusion,
        generatedAt: snapshot.generated_at,
      });
      setOutcomes(review.candidate_outcomes);
      setGlobalConclusion(hydrated.globalConclusion);
    } else if (initialOutcomes && initialOutcomes.length > 0) {
      const review = buildMomentumTrialOutcomeReview(snapshot, {
        existingOutcomes: initialOutcomes as unknown[],
        globalConclusion: initialGlobalConclusion ?? "",
        generatedAt: snapshot.generated_at,
      });
      setOutcomes(review.candidate_outcomes);
      setGlobalConclusion(initialGlobalConclusion ?? "");
    } else {
      setOutcomes(candidateOutcomeDefaults(snapshot));
      setGlobalConclusion(initialGlobalConclusion ?? "");
    }
    // initialOutcomes/initialGlobalConclusion are test-only props; they
    // are not expected to change between renders in production callers,
    // so excluding them from the dep array is intentional.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [snapshot, persistLatest]);

  const review = useMemo<MomentumTrialOutcomeReview>(() => {
    if (!snapshot) {
      return buildMomentumTrialOutcomeReview(null, {
        globalConclusion,
        generatedAt: new Date().toISOString(),
      });
    }
    return {
      schema_version: "phase_b8.v1",
      generated_at: new Date().toISOString(),
      snapshot,
      global_conclusion: globalConclusion.trim()
        ? {
            text: sanitizeMomentumOutcomeNote(globalConclusion),
            authored_at: new Date().toISOString(),
          }
        : null,
      candidate_outcomes: outcomes,
      summary: summarizeMomentumTrialOutcomes({
        schema_version: "phase_b8.v1",
        generated_at: "",
        snapshot,
        global_conclusion: null,
        candidate_outcomes: outcomes,
        summary: summarizeMomentumTrialOutcomes(null),
      }),
    };
  }, [snapshot, outcomes, globalConclusion]);

  const summary = review.summary;

  const updateTag = useCallback(
    (key: string, tag: MomentumTrialOutcomeTag) => {
      setOutcomes((prev) => {
        const next = prev.map((row) => {
          if (momentumCandidateOutcomeKey(row) === key) {
            return { ...row, tag };
          }
          return row;
        });
        if (persistLatest && snapshot) {
          persistOutcomes(snapshot.generated_at, next, globalConclusion);
        }
        return next;
      });
      setExportStatus("idle");
    },
    [persistLatest, snapshot, globalConclusion],
  );

  const updateNote = useCallback(
    (key: string, note: string) => {
      setOutcomes((prev) => {
        const next = prev.map((row) => {
          if (momentumCandidateOutcomeKey(row) === key) {
            return { ...row, note };
          }
          return row;
        });
        if (persistLatest && snapshot) {
          persistOutcomes(snapshot.generated_at, next, globalConclusion);
        }
        return next;
      });
      setExportStatus("idle");
    },
    [persistLatest, snapshot, globalConclusion],
  );

  const updateGlobalConclusion = useCallback(
    (text: string) => {
      setGlobalConclusion(text);
      if (persistLatest && snapshot) {
        persistOutcomes(snapshot.generated_at, outcomes, text);
      }
      setExportStatus("idle");
    },
    [persistLatest, snapshot, outcomes],
  );

  const clearOutcomeReview = useCallback(() => {
    if (!snapshot) return;
    const reset = candidateOutcomeDefaults(snapshot);
    setOutcomes(reset);
    setGlobalConclusion("");
    if (persistLatest) clearPersistedOutcomes();
    setExportStatus("idle");
  }, [snapshot, persistLatest]);

  const downloadMarkdown = useCallback(() => {
    if (!snapshot) return;
    const stamp = review.generated_at.replace(/[^0-9A-Za-z]+/g, "-");
    downloadTextFile(
      `momentum-trial-outcome-${stamp}.md`,
      "text/markdown;charset=utf-8",
      buildMomentumOutcomeMarkdown(review),
    );
    setExportStatus("idle");
  }, [snapshot, review]);

  const downloadJson = useCallback(() => {
    if (!snapshot) return;
    const stamp = review.generated_at.replace(/[^0-9A-Za-z]+/g, "-");
    downloadTextFile(
      `momentum-trial-outcome-${stamp}.json`,
      "application/json;charset=utf-8",
      buildMomentumOutcomeJson(review),
    );
    setExportStatus("idle");
  }, [snapshot, review]);

  if (!snapshot) {
    return (
      <Card title={title}>
        <div
          role="region"
          aria-label="Momentum trial outcome review empty"
          data-testid="momentum-trial-outcome-review-empty"
        >
          <EmptyState
            title="No snapshot captured yet"
            hint="Capture a Momentum trial snapshot first; outcome tagging applies to that snapshot."
          />
          <p style={{ ...NOTE_STYLE, marginTop: 8 }}>
            {MOMENTUM_TRIAL_OUTCOME_DETERMINISTIC_NOTE}
          </p>
        </div>
      </Card>
    );
  }

  return (
    <Card title={title}>
      <div
        role="region"
        aria-label="Momentum trial outcome review"
        data-testid="momentum-trial-outcome-review"
        className="op-stack"
        style={{ gap: 10 }}
      >
        <div
          data-testid="momentum-trial-outcome-summary"
          className="op-row"
          style={{ flexWrap: "wrap", gap: 8 }}
          aria-label="Outcome summary"
        >
          <div style={SUMMARY_CARD_STYLE}>
            <span style={SUMMARY_LABEL_STYLE}>Worked</span>
            <span
              style={SUMMARY_VALUE_STYLE}
              data-testid="momentum-trial-outcome-summary-worked"
            >
              {summary.worked_count}
            </span>
          </div>
          <div style={SUMMARY_CARD_STYLE}>
            <span style={SUMMARY_LABEL_STYLE}>Missed</span>
            <span
              style={SUMMARY_VALUE_STYLE}
              data-testid="momentum-trial-outcome-summary-missed"
            >
              {summary.missed_count}
            </span>
          </div>
          <div style={SUMMARY_CARD_STYLE}>
            <span style={SUMMARY_LABEL_STYLE}>Too aggressive</span>
            <span style={SUMMARY_VALUE_STYLE}>{summary.too_aggressive_count}</span>
          </div>
          <div style={SUMMARY_CARD_STYLE}>
            <span style={SUMMARY_LABEL_STYLE}>Good warnings</span>
            <span style={SUMMARY_VALUE_STYLE}>{summary.good_warning_count}</span>
          </div>
          <div style={SUMMARY_CARD_STYLE}>
            <span style={SUMMARY_LABEL_STYLE}>False warnings</span>
            <span style={SUMMARY_VALUE_STYLE}>{summary.false_warning_count}</span>
          </div>
          <div style={SUMMARY_CARD_STYLE}>
            <span style={SUMMARY_LABEL_STYLE}>Needs ToS parity</span>
            <span style={SUMMARY_VALUE_STYLE}>
              {summary.needs_tos_parity_check_count}
            </span>
          </div>
          <div style={SUMMARY_CARD_STYLE}>
            <span style={SUMMARY_LABEL_STYLE}>Unclear</span>
            <span style={SUMMARY_VALUE_STYLE}>{summary.unclear_count}</span>
          </div>
        </div>

        <label
          style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: "0.82rem" }}
          aria-label="Global outcome conclusion"
        >
          <span style={SUMMARY_LABEL_STYLE}>Global outcome conclusion (optional)</span>
          <textarea
            data-testid="momentum-trial-outcome-global-conclusion"
            value={globalConclusion}
            onChange={(event) => updateGlobalConclusion(event.target.value)}
            placeholder='e.g. "Momentum correctly elevated XLK/IWM; XLB remains watchlist only; XLI needs parity check."'
            style={NOTE_INPUT_STYLE}
            maxLength={1500}
          />
        </label>

        <div
          data-testid="momentum-trial-outcome-table-wrapper"
          style={{ overflowX: "auto", minWidth: 0 }}
        >
          <table className="op-table" style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th style={{ textAlign: "left" }}>Rank</th>
                <th style={{ textAlign: "left" }}>Symbol</th>
                <th style={{ textAlign: "left" }}>Strategy</th>
                <th style={{ textAlign: "left" }}>Outcome</th>
                <th style={{ textAlign: "left" }}>Operator note</th>
                <th style={{ textAlign: "left" }}>Reasons / caveats</th>
              </tr>
            </thead>
            <tbody>
              {outcomes.map((row) => {
                const key = momentumCandidateOutcomeKey(row);
                return (
                  <tr
                    key={key}
                    data-testid="momentum-trial-outcome-row"
                    data-symbol={row.symbol}
                    data-tag={row.tag}
                  >
                    <td>{row.rank}</td>
                    <td style={{ fontWeight: 600 }}>{row.symbol}</td>
                    <td>{row.strategy}</td>
                    <td>
                      <div className="op-stack" style={{ gap: 4 }}>
                        <StatusBadge tone={outcomeTagTone(row.tag)}>
                          {outcomeTagLabel(row.tag)}
                        </StatusBadge>
                        <select
                          aria-label={`Outcome tag for ${row.symbol}`}
                          data-testid="momentum-trial-outcome-tag-select"
                          value={row.tag}
                          onChange={(event) => {
                            const next = event.target.value;
                            if (isMomentumTrialOutcomeTag(next)) updateTag(key, next);
                          }}
                          style={{
                            fontSize: "0.78rem",
                            padding: "2px 4px",
                            borderRadius: 4,
                            background: "rgba(15, 24, 34, 0.55)",
                            color: "var(--op-text, #d9e2ef)",
                            border: "1px solid rgba(115, 138, 163, 0.28)",
                          }}
                        >
                          {MOMENTUM_TRIAL_OUTCOME_TAGS.map((tag) => (
                            <option key={tag} value={tag}>
                              {outcomeTagLabel(tag)}
                            </option>
                          ))}
                        </select>
                      </div>
                    </td>
                    <td>
                      <textarea
                        data-testid="momentum-trial-outcome-note-input"
                        aria-label={`Operator note for ${row.symbol}`}
                        value={row.note}
                        onChange={(event) => updateNote(key, event.target.value)}
                        placeholder="Short note (optional)"
                        style={SHORT_NOTE_INPUT_STYLE}
                        maxLength={400}
                      />
                    </td>
                    <td>
                      <div className="op-row" style={{ flexWrap: "wrap", gap: 4 }}>
                        {row.trade_warning_flags.length === 0 &&
                        row.operational_caveat_flags.length === 0 ? (
                          <span style={{ color: "var(--op-muted, #7a8999)", fontSize: "0.78rem" }}>
                            —
                          </span>
                        ) : (
                          <>
                            {row.trade_warning_flags.map((flag) => (
                              <StatusBadge key={`trade-${flag}`} tone="bad">
                                {flag.replaceAll("_", " ")}
                              </StatusBadge>
                            ))}
                            {row.operational_caveat_flags.map((flag) => (
                              <StatusBadge key={`caveat-${flag}`} tone="warn">
                                {flag.replaceAll("_", " ")}
                              </StatusBadge>
                            ))}
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        <div
          className="op-row"
          style={{ flexWrap: "wrap", gap: 6, justifyContent: "flex-end" }}
        >
          <button
            type="button"
            data-testid="momentum-trial-outcome-download-markdown"
            onClick={downloadMarkdown}
          >
            Export Outcome Markdown
          </button>
          <button
            type="button"
            data-testid="momentum-trial-outcome-download-json"
            onClick={downloadJson}
          >
            Export Outcome JSON
          </button>
          <button
            type="button"
            data-testid="momentum-trial-outcome-clear"
            onClick={clearOutcomeReview}
          >
            Clear outcome review
          </button>
        </div>

        {exportStatus !== "idle" ? (
          <div
            data-testid="momentum-trial-outcome-export-status"
            role="status"
            aria-live="polite"
            style={{
              fontSize: "0.78rem",
              color:
                exportStatus === "copied"
                  ? "var(--op-good-text, #6ec07c)"
                  : "var(--op-warn-text, #d6a25b)",
            }}
          >
            {exportStatus === "copied"
              ? "Outcome export copied."
              : "Export failed — try Download instead."}
          </div>
        ) : null}

        <p
          style={NOTE_STYLE}
          data-testid="momentum-trial-outcome-deterministic-note"
        >
          {MOMENTUM_TRIAL_OUTCOME_DETERMINISTIC_NOTE}
        </p>
      </div>
    </Card>
  );
}
