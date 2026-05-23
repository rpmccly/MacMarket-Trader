export const SUPPORTED_TIMEFRAME_OPTIONS = [
  { value: "1W", label: "1W" },
  { value: "1D", label: "1D" },
  { value: "4H", label: "4H" },
  { value: "1H", label: "1H" },
  { value: "30M", label: "30M" },
] as const;

export type SupportedTimeframe = (typeof SUPPORTED_TIMEFRAME_OPTIONS)[number]["value"];

export const SUPPORTED_TIMEFRAME_VALUES = SUPPORTED_TIMEFRAME_OPTIONS.map((option) => option.value) as ReadonlyArray<SupportedTimeframe>;

export function isSupportedTimeframe(value: string | null | undefined): value is SupportedTimeframe {
  return (SUPPORTED_TIMEFRAME_VALUES as ReadonlyArray<string>).includes(String(value ?? "").toUpperCase());
}

export function normalizeTimeframe(value: string | null | undefined, fallback: SupportedTimeframe = "1D"): SupportedTimeframe {
  const candidate = String(value ?? fallback).toUpperCase();
  return isSupportedTimeframe(candidate) ? candidate : fallback;
}
