import { describe, expect, it } from 'vitest';

import { INDICATOR_REGISTRY, calculateIndicatorSnapshot, normalizeSelection } from '@/lib/indicator-framework';

describe('indicator framework', () => {
  it('normalizes unknown indicators to defaults', () => {
    const selected = normalizeSelection(['nope', 'ema20']);
    expect(selected.includes('ema20')).toBe(true);
  });

  it('produces deterministic snapshot shape', () => {
    const bars = Array.from({ length: 30 }).map((_, idx) => ({
      time: `2026-01-${String(idx + 1).padStart(2, '0')}`,
      open: 100 + idx,
      high: 101 + idx,
      low: 99 + idx,
      close: 100.5 + idx,
      volume: 1_000_000,
    }));
    const snapshot = calculateIndicatorSnapshot(bars);
    expect(snapshot).toHaveProperty('sma20');
    expect(snapshot).toHaveProperty('sma50');
    expect(snapshot).toHaveProperty('ema20');
    expect(snapshot).toHaveProperty('relativeVolume');
  });

  it('registers ATR as a selectable trailing-stop volatility indicator', () => {
    expect(INDICATOR_REGISTRY).toContainEqual({
      id: 'atr',
      label: 'ATR Trailing Stop',
      category: 'volatility',
      defaultEnabled: false,
    });
  });

  it('registers Momentum Intelligence indicator IDs without changing existing defaults', () => {
    const ids = INDICATOR_REGISTRY.map((entry) => entry.id);
    for (const expected of [
      'true_momentum',
      'true_momentum_ema',
      'hilo_elite',
      'hilo_slowd',
      'hilo_slowd_x',
      'momentum_score',
      'momentum_thrust',
    ]) {
      expect(ids).toContain(expected);
    }
    const newEntries = INDICATOR_REGISTRY.filter((entry) => entry.category === 'momentum_intelligence');
    expect(newEntries).toHaveLength(7);
    for (const entry of newEntries) {
      expect(entry.defaultEnabled).toBe(false);
    }
    // Existing defaults stay backward compatible: ema20, vwap, prior_day_levels.
    const defaults = INDICATOR_REGISTRY.filter((entry) => entry.defaultEnabled).map((entry) => entry.id).sort();
    expect(defaults).toEqual(['ema20', 'prior_day_levels', 'vwap']);
  });

  it('preserves stored momentum-intelligence ids through normalization', () => {
    const result = normalizeSelection(['true_momentum', 'momentum_score', 'ema20']);
    expect(result).toEqual(['true_momentum', 'momentum_score', 'ema20']);
  });
});
