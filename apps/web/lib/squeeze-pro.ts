export const SQUEEZE_PRO_DEFAULT_SETTINGS = {
  showPanel: true,
  showArrows: false,
  length: 20,
  nBB: 2.0,
  nK_High: 1.0,
  nK_Mid: 1.5,
  nK_Low: 2.0,
} as const;

export const SQUEEZE_PRO_COLORS = {
  oscillator: {
    up: "#4dd9ff",
    up_decreasing: "#4d8dff",
    down: "#d14b4b",
    down_decreasing: "#ffd166",
  },
  squeeze: {
    none: "#21c06e",
    low: "#10151d",
    mid: "#d14b4b",
    high: "#f2a03f",
    unavailable: "#5a6b7c",
  },
} as const;

export function squeezeProStateLabel(state: string | null | undefined): string {
  if (state === "high") return "High squeeze";
  if (state === "mid") return "Mid squeeze";
  if (state === "low") return "Low squeeze";
  if (state === "none") return "No squeeze";
  return "Unavailable";
}

export function squeezeProOscillatorLabel(state: string | null | undefined): string {
  if (state === "up") return "Up";
  if (state === "up_decreasing") return "Up decreasing";
  if (state === "down") return "Down";
  if (state === "down_decreasing") return "Down decreasing";
  return "Unavailable";
}
