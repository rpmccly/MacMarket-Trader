# Thinkorswim Momentum Intelligence parity fixtures

This directory holds the **operator-supplied** Thinkorswim CSV exports that
validate MacMarket's deterministic Momentum Intelligence Layer
(`docs/momentum-intelligence-layer.md`) against the source studies.

By design, this directory ships **without real fixture data**. No fabricated
parity values are committed — only the README, the manifest example, and the
parser/test infrastructure live in the repo. The parity test
(`tests/test_momentum_thinkorswim_parity_scaffold.py`) is a no-op until an
operator explicitly drops Thinkorswim CSVs and a `manifest.json` here.

## Why this exists

The Phase A1 backend
(`src/macmarket_trader/indicators/{true_momentum,hilo_elite,true_momentum_score}.py`,
`src/macmarket_trader/charts/momentum_service.py`) ports three Simpler Trading
studies into deterministic Python. The ports document several intentional
approximations:

- **Higher-timeframe series** is derived from chart bars when no explicit HTF
  payload is supplied (1H → daily, 4H → three-session grouping, 1D → ISO
  week). The series exposes `higher_timeframe_source` so the chart layer can
  surface this.
- **ATR trailing stop** is a deterministic EMA-based approximation rather
  than an exact reproduction of Thinkorswim's `ATRTrailingStop` *modified*
  trail type (`atr_stop_mode = "deterministic_ema_trailing_stop_approximation"`).
- **StochasticFull smoothing** uses exponential smoothing matching the
  studies' `AverageType.EXPONENTIAL`.

Until an operator drops Thinkorswim CSVs and reviews them, the
`MomentumChartPayload` carries
`parity_status = "pending_thinkorswim_fixture_validation"`. **Phase B
(ranking influence) remains blocked until parity fixtures land here and have
been reviewed.**

## Workflow to add a fixture

1. **Export OHLCV bars from Thinkorswim** for the symbol/timeframe you want
   to validate. Save as `<SYMBOL>_<TF>_bars.csv` in this directory.
2. **Export study values** from each of the three reference studies:
   - `ST_TrueMomentumScoreSTUDY.ts` — gives `totalScore`, `Trend`, `Momo`.
   - `ST_TrueMomentumSTUDY.ts` — gives `TrueMomentum`, `EMA` (the True
     Momentum EMA line).
   - `ST_HiLoEliteSTUDY.ts` — gives `SlowD`, `SlowD_X`, thrust, and the
     HLP composite (when used inside the score study).

   Save the joined per-bar study output as `<SYMBOL>_<TF>_study.csv` in this
   directory. The CSV should expose at minimum the **latest bar's**
   `totalScore`, `TrueMomentum`, `TrueMomentumEMA`, `HiLoThrust`,
   `HLP_Output`, `Trend`, and `Momo` values — additional rows for prior
   bars are accepted but not required for the parity comparison.

3. **(Optional)** Export the higher-timeframe OHLCV bars as
   `<SYMBOL>_<HTF>_bars.csv`. When a fixture provides
   `higher_timeframe_bars_csv`, the parity test asserts that
   `higher_timeframe_source == "provided_higher_timeframe_bars"`. When it
   doesn't, the deterministic chart-bar derivation is exercised instead.

4. **Add the fixture entry to `manifest.json`** in this directory. Use
   `manifest.example.json` as a template. Provide:
   - `name` (unique label)
   - `symbol`, `timeframe`
   - `bars_csv`, `study_csv` (relative paths inside this directory)
   - optional `higher_timeframe_bars_csv`
   - `expected_latest` — the values exported by the operator from
     Thinkorswim for the **last bar** in `bars_csv`
   - `tolerances` — per-field absolute tolerances. Start with the values in
     `manifest.example.json` and tighten over time.

   Do **not** invent parity values. If you don't have a real Thinkorswim
   export for a field, omit it from `expected_latest`; the test will skip
   any field that isn't in `expected_latest`.

5. **Run the parity test** from the repo root:
   ```
   python -m pytest tests/test_momentum_thinkorswim_parity_scaffold.py -q --tb=short
   ```

   With `manifest.json` present, the test will:
   - parse each fixture's bars and (optional) HTF bars CSVs
   - build the deterministic momentum payload via
     `MomentumChartService.build_payload`
   - compare the payload's latest snapshot against `expected_latest` using
     the per-field absolute `tolerances`
   - cross-check the latest study CSV row against the same expected values
     when the columns are present
   - assert `higher_timeframe_source == "provided_higher_timeframe_bars"`
     when `higher_timeframe_bars_csv` is provided
   - confirm `parity_status` is still surfaced on the payload

   With `manifest.json` absent, the test is a no-op pass.

## Supported CSV column names

Both bars and study CSVs are parsed with **case- and underscore-insensitive**
column matching, so any of the variants below will be recognized.

### Bars CSV

| Concept | Accepted column headers |
|---|---|
| Date / datetime | `Date`, `Datetime`, `Time`, `Timestamp` |
| Open  | `Open`, `O` |
| High  | `High`, `H` |
| Low   | `Low`, `L` |
| Close | `Close`, `C`, `Last` |
| Volume| `Volume`, `Vol`, `V` |

The parser accepts ISO dates (`2026-04-01`), ISO timestamps
(`2026-04-01T14:30:00Z`), and the common Thinkorswim `MM/DD/YY` /
`MM/DD/YYYY HH:MM` shapes.

### Study CSV

| Concept | Accepted column headers |
|---|---|
| Total score | `totalScore`, `TotalScore`, `total_score` |
| True Momentum | `TrueMomentum`, `true_momentum` |
| True Momentum EMA | `TrueMomentumEMA`, `true_momentum_ema`, `EMA` |
| HiLo thrust | `HiLoThrust`, `hilo_thrust` |
| HLP output | `HLP_Output`, `hilo_output`, `HLPOutput` |
| Trend score | `Trend`, `trend_score` |
| Momo score | `Momo`, `momo_score` |

A study row's "latest" value is whichever row has the largest parseable date
or, if no date column is present, the last row in CSV order.

## Why no committed fixture data?

- Thinkorswim license restrictions on derived study values.
- We do not want a fake parity pass to mask deterministic regressions.

When the first real fixture lands, the parity test starts asserting against
real numbers and a regression in any of the indicator math will fail loudly.
