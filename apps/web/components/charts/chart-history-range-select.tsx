"use client";

import React from "react";

import {
  CHART_HISTORY_RANGES,
  defaultChartHistoryRange,
  validateChartHistoryRange,
  type ChartHistoryRangeId,
} from "@/lib/chart-history-range";

export type ChartHistoryRangeSelectProps = {
  value: ChartHistoryRangeId | string | null | undefined;
  onChange: (next: ChartHistoryRangeId) => void;
  /** Disable the control while a chart is loading. */
  disabled?: boolean;
  /** Accessible label override. Defaults to "History range". */
  ariaLabel?: string;
  /** ``data-testid`` override for callers that mount multiple selectors. */
  testId?: string;
  /** Optional className passthrough for chart-toolbar integration. */
  className?: string;
  /** Optional inline style passthrough. */
  style?: React.CSSProperties;
};

export const CHART_HISTORY_RANGE_SELECT_TEST_ID = "chart-history-range-select";

export function ChartHistoryRangeSelect({
  value,
  onChange,
  disabled = false,
  ariaLabel = "History range",
  testId = CHART_HISTORY_RANGE_SELECT_TEST_ID,
  className,
  style,
}: ChartHistoryRangeSelectProps) {
  const resolved = validateChartHistoryRange(value ?? defaultChartHistoryRange());
  return (
    <label
      className={className}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        fontSize: "0.82rem",
        ...style,
      }}
    >
      <span style={{ marginRight: 4 }}>History range</span>
      <select
        aria-label={ariaLabel}
        data-testid={testId}
        value={resolved}
        disabled={disabled}
        onChange={(event) => {
          const next = validateChartHistoryRange(event.target.value);
          onChange(next);
        }}
        style={{
          fontSize: "0.82rem",
          padding: "2px 6px",
          borderRadius: 4,
          background: "rgba(15, 24, 34, 0.55)",
          color: "var(--op-text, #d9e2ef)",
          border: "1px solid rgba(115, 138, 163, 0.28)",
        }}
      >
        {CHART_HISTORY_RANGES.map((option) => (
          <option
            key={option.id}
            value={option.id}
            title={option.description}
          >
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}
