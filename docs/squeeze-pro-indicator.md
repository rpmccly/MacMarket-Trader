# Squeeze Pro Research Indicator

Squeeze Pro is implemented as a MacMarket research indicator. It does not
create recommendations, approve trades, size positions, route orders, place
orders, or change paper-trading behavior.

## Implementation status

Implemented:

- backend indicator module:
  `src/macmarket_trader/indicators/squeeze_pro.py`
- Momentum Intelligence chart payload field: `squeeze_pro`
- Momentum Intelligence lower chart panel
- Momentum Heatmap Squeezes column
- Momentum Heatmap report, CSV, and email-ready report rendering
- backend and frontend tests for indicator state, chart payload, heatmap
  squeeze states, and UI wiring

Not implemented:

- exact Thinkorswim or TTM histogram parity
- user-specific Squeeze Pro settings persistence
- using Squeeze Pro inside True Momentum scoring
- using Squeeze Pro as a recommendation, approval, sizing, or execution signal

## Parameters

Default parameters:

- `length = 20`
- `nBB = 2.0`
- `nK_High = 1.0`
- `nK_Mid = 1.5`
- `nK_Low = 2.0`
- `price = close`

The current settings live in code as deterministic defaults. A later pass can
make them user-configurable if that fits the operator profile/settings model.

## Compression formulas

The implementation uses the user-provided Squeeze Pro formulas without copying
proprietary source headers or comments.

Bollinger upper band:

```text
basis = SMA(close, length)
standard deviation = rolling population standard deviation over length
bb_upper = basis + nBB * standard deviation
```

Keltner upper bands:

```text
range_basis = ATR(length)
kc_upper_high = basis + nK_High * range_basis
kc_upper_mid  = basis + nK_Mid  * range_basis
kc_upper_low  = basis + nK_Low  * range_basis
```

Squeeze deltas:

```text
BolKelDelta_High = bb_upper - kc_upper_high
BolKelDelta_Mid  = bb_upper - kc_upper_mid
BolKelDelta_Low  = bb_upper - kc_upper_low
```

State classification:

```text
if BolKelDelta_High <= 0: high
else if BolKelDelta_Mid <= 0: mid
else if BolKelDelta_Low <= 0: low
else: none
```

State colors:

- No squeeze: green
- Low squeeze: dark
- Mid squeeze: red
- High squeeze: orange

## Histogram

The user-provided reference logic names a TTM Squeeze histogram but does not
define the internals of that built-in function. No existing exact TTM Squeeze
histogram implementation was found in this repo.

MacMarket therefore uses a transparent deterministic approximation:

1. Compute a rolling midpoint from recent high/low and SMA(close).
2. Compute `close - midpoint`.
3. Apply a length-20 linear regression and use the fitted last value as the
   oscillator.

This is labeled in payloads as:

```text
macmarket_linear_regression_momentum_approximation
```

MacMarket does not claim exact Thinkorswim/TTM histogram parity for this
oscillator.

Histogram color states:

- `up`: previous < current and current >= 0, colored cyan
- `down_decreasing`: previous < current and current < 0, colored yellow
- `up_decreasing`: previous >= current and current >= 0, colored blue
- `down`: previous >= current and current < 0, colored red

## Deferred

Arrow logic is deferred until approved arrow rules are provided; compatibility
fields remain disabled/null with `show_arrows = false`.

## Chart Payload

Momentum chart payloads include:

```json
{
  "squeeze_pro": {
    "enabled": true,
    "status": "ok",
    "parameters": {},
    "version": "macmarket_squeeze_pro.v1",
    "histogram_mode": "macmarket_linear_regression_momentum_approximation",
    "series": []
  }
}
```

Every Squeeze Pro point shares the same canonical chart time value as the
candle and True Momentum panels. Warmup bars remain present with null
oscillator values and unavailable squeeze state so the lower panel preserves
the full source chart timeline.

## Heatmap Behavior

Momentum Heatmap computes Squeeze Pro per requested timeframe. The Squeezes
column displays the strongest active state across the refreshed timeframes.
Unsupported symbols remain visible and fail fast with unavailable Squeeze Pro
state and a reason.

Squeeze Pro is not included in:

- Long-Term Score
- Short-Term Score
- Strength %
- True Momentum Score
- recommendation approval or ranking decisions

## Known Limitations

- Histogram is a MacMarket approximation until an approved exact histogram
  contract or fixture exists.
- Squeeze Pro settings are code defaults, not yet profile/user editable.
- Unsupported workbook labels remain unsupported unless a provider-safe symbol
  mapping is added later.
