"use client";

import React, { useState } from "react";

export type MomentumContextLegendEntry = {
  id: string;
  term: string;
  definition: string;
};

/**
 * Canonical glossary entries for candle-pane Momentum annotations.
 * Copy is deterministic and never carries trade-action language
 * (no buy/sell/enter/short/approve/route language).
 */
export const MOMENTUM_CONTEXT_LEGEND_ENTRIES: MomentumContextLegendEntry[] = [
  {
    id: "rally_context",
    term: "Rally context",
    definition:
      "Momentum context suggesting a constructive recovery or continuation zone. Research context only.",
  },
  {
    id: "pullback_context",
    term: "Pullback context",
    definition:
      "Price/momentum pullback while broader Momentum context may remain constructive.",
  },
  {
    id: "reversal_warning",
    term: "Reversal warning",
    definition:
      "Momentum weakening or exhaustion context. Review risk; not an automatic reject.",
  },
  {
    id: "neutral_to_bull",
    term: "Neutral → Bull",
    definition: "Composite state transitioned from neutral toward bullish.",
  },
  {
    id: "neutral_to_bear",
    term: "Neutral → Bear",
    definition: "Composite state transitioned from neutral toward bearish.",
  },
  {
    id: "no_trade_warning",
    term: "No-trade warning",
    definition:
      "Momentum context is not supportive enough for this deterministic setup. Warning-only unless another deterministic rule acts on it.",
  },
  {
    id: "bullish_cross",
    term: "True Momentum cross up",
    definition:
      "True Momentum crossed above its EMA. Deterministic context only; not a trade signal.",
  },
  {
    id: "bearish_cross",
    term: "True Momentum cross down",
    definition:
      "True Momentum crossed below its EMA. Deterministic context only; not a trade signal.",
  },
  {
    id: "hilo_confirmed",
    term: "HiLo confirmed",
    definition:
      "HiLo thrust transitioned to bullish/confirmed. Context only; not a trade signal.",
  },
  {
    id: "hilo_deconfirmed",
    term: "HiLo deconfirmed",
    definition:
      "HiLo thrust transitioned to bearish/unconfirmed. Context only; not a trade signal.",
  },
];

const CONTAINER_STYLE: React.CSSProperties = {
  margin: 0,
  padding: "8px 10px",
  borderRadius: 8,
  background: "rgba(15, 24, 34, 0.55)",
  border: "1px solid rgba(115, 138, 163, 0.22)",
  fontSize: "0.78rem",
  lineHeight: 1.45,
  color: "var(--op-muted, #c9d3df)",
};

const SUMMARY_STYLE: React.CSSProperties = {
  cursor: "pointer",
  fontWeight: 600,
  color: "var(--op-text, #d9e2ef)",
};

const LIST_STYLE: React.CSSProperties = {
  margin: "6px 0 0 0",
  padding: 0,
  listStyle: "none",
  display: "grid",
  gap: 4,
};

const TERM_STYLE: React.CSSProperties = {
  color: "var(--op-text, #d9e2ef)",
  fontWeight: 600,
  marginRight: 6,
};

export type MomentumContextLegendProps = {
  /** Optional override; defaults to the canonical entry list. */
  entries?: MomentumContextLegendEntry[];
  /** When true, render expanded by default. */
  initiallyOpen?: boolean;
  /** Override the title text. */
  title?: string;
  testId?: string;
};

export function MomentumContextLegend({
  entries = MOMENTUM_CONTEXT_LEGEND_ENTRIES,
  initiallyOpen = false,
  title = "Chart annotation glossary",
  testId = "momentum-context-legend",
}: MomentumContextLegendProps) {
  const [open, setOpen] = useState(initiallyOpen);

  return (
    <details
      style={CONTAINER_STYLE}
      data-testid={testId}
      open={open}
      onToggle={(event) => setOpen((event.target as HTMLDetailsElement).open)}
    >
      <summary style={SUMMARY_STYLE} data-testid={`${testId}-summary`}>
        {title}
      </summary>
      <ul style={LIST_STYLE} data-testid={`${testId}-list`}>
        {entries.map((entry) => (
          <li key={entry.id} data-testid={`${testId}-item-${entry.id}`}>
            <span style={TERM_STYLE}>{entry.term}:</span>
            <span>{entry.definition}</span>
          </li>
        ))}
      </ul>
      <p
        style={{ margin: "6px 0 0 0", color: "var(--op-muted, #7a8999)", fontSize: "0.72rem" }}
        data-testid={`${testId}-deterministic-note`}
      >
        Annotations describe deterministic Momentum context only. They are
        never trade approval, position sizing, or routing instructions.
      </p>
    </details>
  );
}
