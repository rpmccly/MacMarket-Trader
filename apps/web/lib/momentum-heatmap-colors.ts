export type MomentumHeatmapScoreRange = {
  min: number;
  max: number;
  label: string;
  className: string;
};

// TODO(momentum-heatmap): make these operator-configurable once a user-scoped
// preference model exists for the heatmap.
export const MOMENTUM_HEATMAP_SCORE_RANGES: MomentumHeatmapScoreRange[] = [
  { min: 80, max: 100, label: "80 to 100", className: "hm-score-bright-green" },
  { min: 60, max: 80, label: "60 to <80", className: "hm-score-green" },
  { min: 40, max: 60, label: "40 to <60", className: "hm-score-purple" },
  { min: 20, max: 40, label: "20 to <40", className: "hm-score-red" },
  { min: 0, max: 20, label: "0 to <20", className: "hm-score-bright-red" },
];

export function momentumHeatmapScoreClass(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "hm-score-unavailable";
  if (value >= 80) return "hm-score-bright-green";
  if (value >= 60) return "hm-score-green";
  if (value >= 40) return "hm-score-purple";
  if (value >= 20) return "hm-score-red";
  return "hm-score-bright-red";
}
