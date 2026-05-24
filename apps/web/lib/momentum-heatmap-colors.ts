export const MOMENTUM_HEATMAP_COLOR_STORAGE_KEY = "macmarket-momentum-heatmap-colors-v1";

export type MomentumHeatmapScoreRange = {
  id: string;
  min: number;
  max: number;
  label: string;
  color: string;
  className: string;
};

export const DEFAULT_MOMENTUM_HEATMAP_SCORE_RANGES: MomentumHeatmapScoreRange[] = [
  { id: "bright-green", min: 75, max: 100, label: "Bright green", color: "#56f08a", className: "hm-score-bright-green" },
  { id: "green", min: 25, max: 74.999, label: "Green", color: "#1f9f62", className: "hm-score-green" },
  { id: "purple", min: -24.999, max: 24.999, label: "Purple", color: "#7d5cff", className: "hm-score-purple" },
  { id: "red", min: -74.999, max: -25, label: "Red", color: "#bd3d4b", className: "hm-score-red" },
  { id: "bright-red", min: -100, max: -75, label: "Bright red", color: "#ff4b4b", className: "hm-score-bright-red" },
];

// Backwards-compatible export name used by existing tests/imports.
export const MOMENTUM_HEATMAP_SCORE_RANGES = DEFAULT_MOMENTUM_HEATMAP_SCORE_RANGES;

const HEX_COLOR_PATTERN = /^#[0-9a-fA-F]{6}$/;

export function cloneDefaultMomentumHeatmapScoreRanges(): MomentumHeatmapScoreRange[] {
  return DEFAULT_MOMENTUM_HEATMAP_SCORE_RANGES.map((range) => ({ ...range }));
}

export function normalizeMomentumHeatmapScoreRanges(value: unknown): MomentumHeatmapScoreRange[] {
  if (!Array.isArray(value)) return cloneDefaultMomentumHeatmapScoreRanges();
  const defaultsById = new Map(DEFAULT_MOMENTUM_HEATMAP_SCORE_RANGES.map((range) => [range.id, range]));
  const normalized = DEFAULT_MOMENTUM_HEATMAP_SCORE_RANGES.map((fallback) => {
    const candidate = value.find((item) => item && typeof item === "object" && "id" in item && item.id === fallback.id) as
      | Partial<MomentumHeatmapScoreRange>
      | undefined;
    const min = Number(candidate?.min);
    const max = Number(candidate?.max);
    const color = String(candidate?.color ?? fallback.color);
    const label = String(candidate?.label ?? fallback.label).trim();
    const className = String(candidate?.className ?? fallback.className).trim();
    const defaultRange = defaultsById.get(fallback.id) ?? fallback;
    return {
      id: fallback.id,
      min: Number.isFinite(min) ? min : defaultRange.min,
      max: Number.isFinite(max) ? max : defaultRange.max,
      label: label || defaultRange.label,
      color: HEX_COLOR_PATTERN.test(color) ? color : defaultRange.color,
      className: className || defaultRange.className,
    };
  });
  return normalized;
}

export function momentumHeatmapScoreRange(
  value: number | null | undefined,
  ranges: MomentumHeatmapScoreRange[] = DEFAULT_MOMENTUM_HEATMAP_SCORE_RANGES,
): MomentumHeatmapScoreRange | null {
  if (value == null || Number.isNaN(value)) return null;
  return ranges.find((range) => value >= range.min && value <= range.max) ?? null;
}

export function momentumHeatmapScoreClass(value: number | null | undefined): string {
  return momentumHeatmapScoreRange(value)?.className ?? "hm-score-unavailable";
}

function hexToRgb(hex: string): { r: number; g: number; b: number } | null {
  if (!HEX_COLOR_PATTERN.test(hex)) return null;
  return {
    r: Number.parseInt(hex.slice(1, 3), 16),
    g: Number.parseInt(hex.slice(3, 5), 16),
    b: Number.parseInt(hex.slice(5, 7), 16),
  };
}

export function readableTextColor(background: string): string {
  const rgb = hexToRgb(background);
  if (!rgb) return "#ffffff";
  const luminance = (0.299 * rgb.r + 0.587 * rgb.g + 0.114 * rgb.b) / 255;
  return luminance > 0.58 ? "#06150b" : "#fffafa";
}
