"use client";

import React, { useEffect, useMemo, useState } from "react";

import { Card, EmptyState, ErrorState, StatusBadge } from "@/components/operator-ui";
import {
  buildTrueMomentumStrategyPreview,
  familyPreviewLabel,
  TRUE_MOMENTUM_STRATEGY_PREVIEW_DETERMINISTIC_NOTE,
  trueMomentumPreviewReasonLabels,
  trueMomentumPreviewTone,
  type TrueMomentumStrategyPreviewCandidate,
  type TrueMomentumStrategyPreviewResult,
} from "@/lib/true-momentum-strategy-preview";
import { TrueMomentumPreviewEvidencePanel } from "@/components/recommendations/true-momentum-preview-evidence-panel";
import {
  fetchTrueMomentumStrategyFamilyStatus,
  trueMomentumStrategyModeLabel,
  trueMomentumStrategyReasonLabel,
  type TrueMomentumStrategyFamilyStatus,
} from "@/lib/true-momentum-strategy-families";
import type { QueueCandidate } from "@/lib/recommendations";

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

function fmtScore(value: number | null | undefined, digits = 3): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return value.toFixed(digits);
}

function fmtRaw(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  const rounded = Math.round(value * 100) / 100;
  if (rounded === 0) return "0.00";
  return rounded > 0 ? `+${rounded.toFixed(2)}` : rounded.toFixed(2);
}

function fmtSigned(value: number | null | undefined, digits = 3): string {
  if (value == null || !Number.isFinite(value)) return "—";
  if (value === 0) return value.toFixed(digits);
  return value > 0 ? `+${value.toFixed(digits)}` : value.toFixed(digits);
}

function PreviewRow({ preview }: { preview: TrueMomentumStrategyPreviewCandidate }) {
  const reasonLabels = trueMomentumPreviewReasonLabels(preview.reason_codes);
  const caveatLabels = trueMomentumPreviewReasonLabels(preview.operational_caveats);
  return (
    <tr
      data-testid="true-momentum-strategy-preview-row"
      data-symbol={preview.symbol}
      data-family-id={preview.family_id}
      data-match-strength={preview.match_strength}
    >
      <td>{preview.rank}</td>
      <td style={{ fontWeight: 600 }}>{preview.symbol}</td>
      <td>{preview.strategy}</td>
      <td>{preview.family_label}</td>
      <td>
        <StatusBadge tone={trueMomentumPreviewTone(preview.match_strength)}>
          {preview.match_strength}
        </StatusBadge>
      </td>
      <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
        {fmtScore(preview.active_score)}
      </td>
      <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
        {fmtRaw(preview.raw_contribution)}
      </td>
      <td>
        {preview.total_score == null ? "—" : preview.total_score}
        {preview.total_label ? (
          <span style={{ color: "var(--op-muted, #7a8999)", marginLeft: 4 }}>
            ({preview.total_label})
          </span>
        ) : null}
      </td>
      <td>
        <div className="op-row" style={{ flexWrap: "wrap", gap: 4 }}>
          {reasonLabels.length === 0 && caveatLabels.length === 0 ? (
            <span style={{ color: "var(--op-muted, #7a8999)", fontSize: "0.78rem" }}>—</span>
          ) : (
            <>
              {reasonLabels.map((label) => (
                <StatusBadge key={`reason-${label}`} tone="neutral">
                  {label}
                </StatusBadge>
              ))}
              {caveatLabels.map((label) => (
                <StatusBadge key={`caveat-${label}`} tone="warn">
                  {label}
                </StatusBadge>
              ))}
            </>
          )}
        </div>
      </td>
    </tr>
  );
}

export type TrueMomentumStrategyPreviewPanelProps = {
  candidates: ReadonlyArray<QueueCandidate> | null | undefined;
  /**
   * Phase C2 — evaluated universe (e.g. the parsed manual-symbol input
   * from the Recommendations page) passed through to the evidence
   * bundle so it can label "Evaluated universe" rather than
   * "Captured symbols". Optional.
   */
  universeSymbols?: ReadonlyArray<string> | null;
  title?: string;
  /**
   * Test-only: render with a pre-fetched status object instead of
   * triggering a backend fetch. Production callers should leave this
   * undefined.
   */
  initialStatus?: TrueMomentumStrategyFamilyStatus | null;
  /**
   * Phase C2 — disable localStorage persistence on the nested evidence
   * panel. Tests should pass ``false``; production callers leave it
   * undefined (defaults to ``true``).
   */
  persistEvidenceLatest?: boolean;
};

export function TrueMomentumStrategyPreviewPanelView({
  result,
  status,
  loading = false,
  error = null,
  title = "True Momentum strategy preview (Phase C1 research-only)",
  candidates = null,
  universeSymbols = null,
  persistEvidenceLatest = true,
}: {
  result: TrueMomentumStrategyPreviewResult | null;
  status: TrueMomentumStrategyFamilyStatus | null;
  loading?: boolean;
  error?: string | null;
  title?: string;
  candidates?: ReadonlyArray<QueueCandidate> | null;
  universeSymbols?: ReadonlyArray<string> | null;
  persistEvidenceLatest?: boolean;
}) {
  if (error) {
    return (
      <Card title={title}>
        <div
          role="region"
          aria-label="True Momentum strategy preview error"
          data-testid="true-momentum-strategy-preview-error"
        >
          <ErrorState
            title="True Momentum strategy preview unavailable"
            hint={error}
          />
          <p style={{ ...NOTE_STYLE, marginTop: 8 }}>
            {TRUE_MOMENTUM_STRATEGY_PREVIEW_DETERMINISTIC_NOTE}
          </p>
        </div>
      </Card>
    );
  }

  if (loading && !result) {
    return (
      <Card title={title}>
        <div
          role="region"
          aria-label="True Momentum strategy preview loading"
          data-testid="true-momentum-strategy-preview-loading"
        >
          <div
            role="status"
            aria-live="polite"
            style={{ color: "var(--op-muted, #7a8999)", fontSize: "0.85rem" }}
          >
            Loading True Momentum strategy preview…
          </div>
          <p style={{ ...NOTE_STYLE, marginTop: 8 }}>
            {TRUE_MOMENTUM_STRATEGY_PREVIEW_DETERMINISTIC_NOTE}
          </p>
        </div>
      </Card>
    );
  }

  const effectiveMode = status?.effective_mode ?? "disabled";
  const requestedActive = status?.requested_mode === "active";

  if (effectiveMode === "disabled") {
    return (
      <Card title={title}>
        <div
          role="region"
          aria-label="True Momentum strategy preview disabled"
          data-testid="true-momentum-strategy-preview-disabled"
          className="op-stack"
          style={{ gap: 10 }}
        >
          <EmptyState
            title="Phase C1 research preview is disabled."
            hint="Phase C0 is scaffold-only. To enable the read-only research preview, set the env vars below."
          />
          <pre
            data-testid="true-momentum-strategy-preview-env-instructions"
            style={{
              padding: "8px 10px",
              borderRadius: 6,
              background: "rgba(15, 24, 34, 0.55)",
              border: "1px solid rgba(115, 138, 163, 0.24)",
              fontSize: "0.78rem",
              color: "var(--op-text, #d9e2ef)",
              whiteSpace: "pre-wrap",
              margin: 0,
            }}
          >
{`MACMARKET_TRUE_MOMENTUM_STRATEGY_MODE=research_preview
MACMARKET_ALLOW_TRUE_MOMENTUM_STRATEGY_FAMILIES=true`}
          </pre>
          <p style={NOTE_STYLE}>
            This remains read-only and does not generate queue candidates, approve,
            reject, size, or route trades. Paper-order creation remains manual.
          </p>
          {requestedActive ? (
            <p style={NOTE_STYLE} data-testid="true-momentum-strategy-preview-active-reserved">
              Active Phase C is reserved and not implemented — the resolved mode
              remains disabled.
            </p>
          ) : null}
          <p
            style={NOTE_STYLE}
            data-testid="true-momentum-strategy-preview-deterministic-note"
          >
            {TRUE_MOMENTUM_STRATEGY_PREVIEW_DETERMINISTIC_NOTE}
          </p>
        </div>
      </Card>
    );
  }

  const summary = result?.summary;
  const previews = result?.previews ?? [];

  return (
    <Card title={title}>
      <div
        role="region"
        aria-label="True Momentum strategy preview"
        data-testid="true-momentum-strategy-preview"
        className="op-stack"
        style={{ gap: 10 }}
      >
        <div className="op-row" style={{ flexWrap: "wrap", gap: 6, alignItems: "center" }}>
          <StatusBadge tone="neutral">
            Phase C0 · {status?.implementation_status ?? "scaffold_only"}
          </StatusBadge>
          <StatusBadge tone="warn">
            Preview Phase {result?.preview_phase ?? "C1"} ·{" "}
            {result?.preview_implementation_status ?? "research_preview"}
          </StatusBadge>
          <StatusBadge tone="neutral">
            Effective: {trueMomentumStrategyModeLabel(effectiveMode)}
          </StatusBadge>
          {requestedActive ? (
            <StatusBadge tone="warn" data-testid="true-momentum-strategy-preview-active-reserved">
              Active reserved — not implemented
            </StatusBadge>
          ) : null}
        </div>

        <div
          data-testid="true-momentum-strategy-preview-summary"
          className="op-row"
          style={{ flexWrap: "wrap", gap: 8 }}
          aria-label="Preview summary"
        >
          <div style={SUMMARY_CARD_STYLE}>
            <span style={SUMMARY_LABEL_STYLE}>Preview candidates</span>
            <span style={SUMMARY_VALUE_STYLE}>{summary?.preview_count ?? 0}</span>
          </div>
          <div style={SUMMARY_CARD_STYLE}>
            <span style={SUMMARY_LABEL_STYLE}>Continuation</span>
            <span
              style={SUMMARY_VALUE_STYLE}
              data-testid="true-momentum-strategy-preview-summary-continuation"
            >
              {summary?.continuation_count ?? 0}
            </span>
          </div>
          <div style={SUMMARY_CARD_STYLE}>
            <span style={SUMMARY_LABEL_STYLE}>Pullback</span>
            <span
              style={SUMMARY_VALUE_STYLE}
              data-testid="true-momentum-strategy-preview-summary-pullback"
            >
              {summary?.pullback_count ?? 0}
            </span>
          </div>
          <div style={SUMMARY_CARD_STYLE}>
            <span style={SUMMARY_LABEL_STYLE}>Reversal / watch</span>
            <span
              style={SUMMARY_VALUE_STYLE}
              data-testid="true-momentum-strategy-preview-summary-reversal"
            >
              {summary?.reversal_watch_count ?? 0}
            </span>
          </div>
          <div style={SUMMARY_CARD_STYLE}>
            <span style={SUMMARY_LABEL_STYLE}>Parity pending</span>
            <span style={SUMMARY_VALUE_STYLE}>{summary?.parity_pending_count ?? 0}</span>
          </div>
          <div style={SUMMARY_CARD_STYLE}>
            <span style={SUMMARY_LABEL_STYLE}>Operational caveats</span>
            <span style={SUMMARY_VALUE_STYLE}>{summary?.operational_caveat_count ?? 0}</span>
          </div>
        </div>

        {result?.extra_reason_codes.length ? (
          <div
            className="op-row"
            style={{ flexWrap: "wrap", gap: 4 }}
            data-testid="true-momentum-strategy-preview-reasons"
          >
            {result.extra_reason_codes.map((code) => (
              <StatusBadge key={code} tone="warn">
                {trueMomentumStrategyReasonLabel(code)}
              </StatusBadge>
            ))}
          </div>
        ) : null}

        {previews.length === 0 ? (
          <p style={NOTE_STYLE} data-testid="true-momentum-strategy-preview-empty">
            No candidates matched a planned True Momentum family for this queue.
          </p>
        ) : (
          <div
            data-testid="true-momentum-strategy-preview-table"
            style={{ overflowX: "auto", minWidth: 0 }}
          >
            <table
              className="op-table"
              style={{ width: "100%", borderCollapse: "collapse" }}
            >
              <thead>
                <tr>
                  <th style={{ textAlign: "left" }}>Rank</th>
                  <th style={{ textAlign: "left" }}>Symbol</th>
                  <th style={{ textAlign: "left" }}>Current strategy</th>
                  <th style={{ textAlign: "left" }}>Preview family</th>
                  <th style={{ textAlign: "left" }}>Match strength</th>
                  <th style={{ textAlign: "right" }}>Active score</th>
                  <th style={{ textAlign: "right" }}>Raw</th>
                  <th style={{ textAlign: "left" }}>Total</th>
                  <th style={{ textAlign: "left" }}>Reasons / caveats</th>
                </tr>
              </thead>
              <tbody>
                {previews.map((preview) => (
                  <PreviewRow key={preview.preview_id} preview={preview} />
                ))}
              </tbody>
            </table>
          </div>
        )}

        {previews.length > 0 ? (
          <TrueMomentumPreviewEvidencePanel
            candidates={candidates}
            previewResult={result}
            universeSymbols={universeSymbols ?? null}
            persistLatest={persistEvidenceLatest}
          />
        ) : null}

        <p
          style={NOTE_STYLE}
          data-testid="true-momentum-strategy-preview-deterministic-note"
        >
          {TRUE_MOMENTUM_STRATEGY_PREVIEW_DETERMINISTIC_NOTE}
        </p>
        <p style={NOTE_STYLE} data-testid="true-momentum-strategy-preview-still-pending">
          Still pending: accumulated B8 outcome evidence · Thinkorswim fixture parity
          · operator authorization before any active Phase C.
        </p>
      </div>
    </Card>
  );
}

export function TrueMomentumStrategyPreviewPanel({
  candidates,
  universeSymbols = null,
  title,
  initialStatus = null,
  persistEvidenceLatest = true,
}: TrueMomentumStrategyPreviewPanelProps) {
  const [status, setStatus] = useState<TrueMomentumStrategyFamilyStatus | null>(initialStatus);
  const [loading, setLoading] = useState<boolean>(!initialStatus);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (initialStatus) return;
    let cancelled = false;
    async function load() {
      setLoading(true);
      const result = await fetchTrueMomentumStrategyFamilyStatus();
      if (cancelled) return;
      setLoading(false);
      if (result.authPending) {
        setStatus(null);
        setError(null);
        return;
      }
      if (!result.ok) {
        setError(result.error ?? "Unable to load True Momentum strategy preview status.");
        return;
      }
      setStatus(result.data);
      setError(null);
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [initialStatus]);

  const result = useMemo(
    () => buildTrueMomentumStrategyPreview(candidates ?? null, status),
    [candidates, status],
  );

  return (
    <TrueMomentumStrategyPreviewPanelView
      result={result}
      status={status}
      loading={loading}
      error={error}
      title={title}
      candidates={candidates ?? null}
      universeSymbols={universeSymbols ?? null}
      persistEvidenceLatest={persistEvidenceLatest}
    />
  );
}
