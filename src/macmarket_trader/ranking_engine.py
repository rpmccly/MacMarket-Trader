from __future__ import annotations

from dataclasses import asdict, dataclass, field
from statistics import mean
from typing import Any

from macmarket_trader.charts.momentum_service import MomentumChartService
from macmarket_trader.config import settings as _settings
from macmarket_trader.domain.enums import MarketMode
from macmarket_trader.domain.schemas import Bar, MomentumRankingContribution
from macmarket_trader.recommendation.momentum_ranking import (
    MomentumRankingConfig,
    apply_momentum_score_delta,
    build_momentum_ranking_contribution,
    enforce_score_consistency,
    momentum_ranking_config_from_settings,
)
from macmarket_trader.strategy_registry import StrategyRegistryEntry, list_strategies


@dataclass
class RankedCandidate:
    rank: int
    symbol: str
    strategy: str
    strategy_id: str
    strategy_status: str
    source: str
    workflow_source: str
    market_mode: str
    timeframe: str
    status: str
    conviction_tier: str
    score: float
    score_breakdown: dict[str, float]
    expected_rr: float
    confidence: float
    thesis: str
    trigger: str
    entry_zone: str
    invalidation: str
    targets: str
    reason_text: str
    # Phase B1 momentum ranking influence — optional, mode-aware. Always
    # present (with mode='off' / enabled=False) when no Momentum payload is
    # available so frontend clients can rely on a stable shape.
    momentum_contribution: dict[str, Any] = field(default_factory=dict)
    # Phase B6 — before/after visibility. Always populated so the
    # Momentum Shadow Impact Review can show baseline vs. applied score
    # without recomputing indicators. ``momentum_rank_mode`` mirrors the
    # effective mode at the time of ranking.
    score_before_momentum: float | None = None
    score_after_momentum: float | None = None
    momentum_score_delta: float | None = None
    momentum_rank_mode: str | None = None
    # Phase B6.3 — realized score delta after the [0, 1] clamp engages.
    # Equal to ``momentum_score_delta`` when the clamp does not truncate
    # (e.g. baseline 0.812 + intended +0.07 → score 0.882, realized
    # +0.07). Differs from the intended value when the clamp truncates
    # (e.g. baseline 0.97 + intended +0.07 → score 1.000, realized +0.03).
    momentum_realized_score_delta: float | None = None


def _regime_alignment_bonus(bars: list[Bar], strategy: str) -> float:
    """Return a deterministic bonus [0.0, 0.08] based on simple trend/momentum alignment."""
    if len(bars) < 5:
        return 0.0
    recent = bars[-5:]
    closes = [b.close for b in recent]
    # Uptrend: each close >= previous
    up_count = sum(1 for i in range(1, len(closes)) if closes[i] >= closes[i - 1])
    trend_ratio = up_count / (len(closes) - 1)
    # Momentum strategies align with trend; mean-reversion aligns with counter-trend
    if "Mean Reversion" in strategy:
        alignment = 1.0 - trend_ratio
    elif "Pullback" in strategy:
        alignment = trend_ratio * 0.8
    else:
        alignment = trend_ratio
    return round(alignment * 0.08, 4)


def _recency_weight(bars: list[Bar]) -> float:
    """Return a recency bonus [0.0, 0.06] — higher when latest close is near the recent high."""
    if len(bars) < 10:
        return 0.0
    recent = bars[-10:]
    high = max(b.high for b in recent)
    low = min(b.low for b in recent)
    rng = high - low or 0.01
    last_close = recent[-1].close
    position = (last_close - low) / rng  # 0 = at recent low, 1 = at recent high
    return round(position * 0.06, 4)


def _conviction_tier(score: float) -> str:
    if score >= 0.72:
        return "HIGH"
    if score >= 0.62:
        return "MEDIUM"
    return "LOW"


def _score_symbol(bars: list[Bar], strategy: str) -> dict[str, float]:
    last = bars[-1]
    avg_volume = mean([bar.volume for bar in bars[-20:]]) if bars else float(last.volume)
    daily_ranges = [max(bar.high - bar.low, 0.01) for bar in bars[-14:]]
    atr = mean(daily_ranges) if daily_ranges else 1.0
    close = max(last.close, 0.01)
    rel_volatility = min(2.0, atr / close * 100)
    liquidity = min(1.0, avg_volume / 4_000_000)
    strategy_fit = 0.75 if strategy == "Event Continuation" else 0.68
    regime_fit = 0.65 + min(0.2, rel_volatility / 10)
    catalyst_quality = 0.55
    volatility_fit = min(1.0, rel_volatility / 1.5)
    spread_penalty = 0.05 if liquidity > 0.5 else 0.18
    regime_bonus = _regime_alignment_bonus(bars, strategy)
    recency_bonus = _recency_weight(bars)
    expected_rr = round(1.2 + (strategy_fit * 1.1) + (volatility_fit * 0.35) - spread_penalty, 2)
    confidence = max(0.2, min(0.95, (strategy_fit + regime_fit + liquidity) / 3))
    score = (
        strategy_fit * 0.22
        + regime_fit * 0.17
        + catalyst_quality * 0.11
        + liquidity * 0.13
        + volatility_fit * 0.13
        + confidence * 0.10
        + min(1.0, expected_rr / 3) * 0.10
        - spread_penalty * 0.14
        + regime_bonus
        + recency_bonus
    )
    return {
        "strategy_fit_score": round(strategy_fit, 3),
        "regime_fit_score": round(regime_fit, 3),
        "catalyst_quality_score": round(catalyst_quality, 3),
        "liquidity_score": round(liquidity, 3),
        "volatility_suitability_score": round(volatility_fit, 3),
        "spread_slippage_penalty": round(spread_penalty, 3),
        "regime_alignment_bonus": round(regime_bonus, 4),
        "recency_weight": round(recency_bonus, 4),
        "expected_rr": expected_rr,
        "confidence": round(confidence, 3),
        "total_score": round(score, 3),
    }


def _recent_trend(bars: list[Bar]) -> float:
    """5-bar net close change. Positive = recent upward bias; used as a
    direction hint for momentum-aligned strategies in Phase B1 only."""
    if len(bars) < 6:
        return 0.0
    return float(bars[-1].close - bars[-6].close)


def _build_momentum_payload(bars: list[Bar], symbol: str, timeframe: str) -> Any:
    """Compute the Momentum chart payload locally from already-loaded bars.

    Phase B1 fail-soft: any error returns None so the contribution falls
    through to ``momentum_payload_unavailable`` rather than raising into the
    ranking engine.
    """
    try:
        return MomentumChartService().build_payload(
            symbol=symbol,
            timeframe=timeframe,
            bars=list(bars),
        )
    except Exception:  # noqa: BLE001 - fail-soft per Phase B1 design
        return None


class DeterministicRankingEngine:
    def __init__(self, momentum_config: MomentumRankingConfig | None = None) -> None:
        # Falls back to settings on every call, so an env-var change between
        # process starts is honored even when callers don't pass an explicit
        # config. Tests can pass a custom MomentumRankingConfig directly.
        self._momentum_config = momentum_config

    def _resolve_momentum_config(self) -> MomentumRankingConfig:
        if self._momentum_config is not None:
            return self._momentum_config
        return momentum_ranking_config_from_settings(_settings)

    def rank_candidates(
        self,
        *,
        bars_by_symbol: dict[str, tuple[list[Bar], str, bool]],
        strategies: list[str],
        market_mode: MarketMode,
        timeframe: str,
        top_n: int = 5,
        momentum_config: MomentumRankingConfig | None = None,
    ) -> dict[str, object]:
        allowed = {entry.display_name: entry for entry in list_strategies(market_mode)}
        selected: list[StrategyRegistryEntry] = [allowed[name] for name in strategies if name in allowed]
        if not selected:
            fallback_entry = next(iter(allowed.values()), None)
            if fallback_entry is None:
                return {"queue": [], "top_candidates": [], "watchlist_only": [], "no_trade": [], "summary": {"total": 0, "top_candidate_count": 0, "watchlist_count": 0, "no_trade_count": 0}}
            selected = [fallback_entry]

        active_config = momentum_config or self._resolve_momentum_config()
        # Compute the momentum payload **once per symbol** even if multiple
        # strategies are scored — momentum is a per-bar context, not
        # strategy-specific.
        momentum_by_symbol: dict[str, Any] = {}
        if active_config.mode != "off":
            for symbol, (bars, _, _) in bars_by_symbol.items():
                if bars:
                    momentum_by_symbol[symbol] = _build_momentum_payload(bars, symbol, timeframe)

        output: list[RankedCandidate] = []
        for symbol, (bars, source, fallback_mode) in bars_by_symbol.items():
            if not bars:
                continue
            latest = bars[-1]
            prior = bars[-2] if len(bars) > 1 else latest
            workflow_source = f"fallback ({source})" if fallback_mode else source
            recent_trend = _recent_trend(bars)
            for entry in selected:
                metrics = _score_symbol(bars, entry.display_name)
                total = metrics["total_score"]
                # Phase B6 — capture the baseline before the bounded
                # momentum contribution is applied so the operator UI can
                # show before/after visibility without recomputing
                # indicators. ``score_before_momentum`` is the raw
                # deterministic score from ``_score_symbol``; the active
                # mode delta is layered on top below.
                score_before_momentum: float | None = total
                momentum_score_delta: float | None = None

                # Phase B1: bounded momentum ranking contribution.
                # Phase B4.2: enrich the inference context with the
                # registry's strategy_id and directional_profile so
                # known bullish/bearish strategies surface the inferred
                # direction instead of falling back to unknown.
                contribution_dict: dict[str, Any] = {}
                momentum_realized_score_delta: float | None = None
                if active_config.mode != "off":
                    payload = momentum_by_symbol.get(symbol)
                    contribution = build_momentum_ranking_contribution(
                        payload,
                        recommendation_context={
                            "strategy": entry.display_name,
                            "strategy_id": entry.strategy_id,
                            "directional_profile": entry.directional_profile,
                            "recent_trend": recent_trend,
                        },
                        config=active_config,
                    )
                    if active_config.mode == "active" and contribution.applied:
                        # Phase B6.2 — route every score change through the
                        # single ``apply_momentum_score_delta`` helper so
                        # the engine, the contribution payload, and the
                        # frontend all see the same scaled delta.
                        new_total, applied_delta = apply_momentum_score_delta(total, contribution)
                        # Phase B6.3 — single-source-of-truth output guard.
                        # Recompute the expected score from the contribution
                        # payload and force ``total`` to match. If any other
                        # path mutated the score, ``corrected=True`` and a
                        # reason code is appended so the operator UI shows
                        # which row needed correction.
                        guard = enforce_score_consistency(
                            observed_score=new_total,
                            score_before_momentum=score_before_momentum,
                            contribution=contribution,
                        )
                        if guard.corrected and "momentum_score_consistency_corrected" not in contribution.reason_codes:
                            contribution = contribution.model_copy(
                                update={
                                    "reason_codes": list(contribution.reason_codes)
                                    + ["momentum_score_consistency_corrected"],
                                }
                            )
                        # ``momentum_score_delta`` is the **intended**
                        # scaled delta and must equal
                        # ``contribution.applied_score_delta`` so the
                        # operator card and queue agree even when the
                        # clamp truncates the realized value.
                        momentum_score_delta = guard.intended_applied_delta
                        momentum_realized_score_delta = guard.realized_score_delta
                        total = guard.final_score
                    contribution_dict = contribution.model_dump(mode="json")
                else:
                    # off-mode: still emit a stable shape so clients/tests
                    # can read momentum_contribution without conditional logic.
                    contribution_dict = MomentumRankingContribution(
                        mode="off", enabled=False, applied=False
                    ).model_dump(mode="json")
                    score_before_momentum = None
                    momentum_score_delta = None

                status = "top_candidate" if total >= 0.62 else "watchlist"
                if metrics["confidence"] < 0.45:
                    status = "no_trade"
                tier = _conviction_tier(total)
                reason_text = (
                    f"{entry.display_name}: fit {metrics['strategy_fit_score']}, liquidity {metrics['liquidity_score']}, "
                    f"volatility {metrics['volatility_suitability_score']}, confidence {metrics['confidence']}, "
                    f"regime bonus {metrics['regime_alignment_bonus']}, recency {metrics['recency_weight']}."
                )
                output.append(
                    RankedCandidate(
                        rank=0,
                        symbol=symbol,
                        strategy=entry.display_name,
                        strategy_id=entry.strategy_id,
                        strategy_status=entry.status,
                        source=source,
                        workflow_source=workflow_source,
                        market_mode=market_mode.value,
                        timeframe=timeframe,
                        status=status,
                        conviction_tier=tier,
                        score=round(total, 3),
                        score_breakdown={k: v for k, v in metrics.items() if k not in {"expected_rr", "confidence", "total_score"}},
                        expected_rr=metrics["expected_rr"],
                        confidence=metrics["confidence"],
                        thesis=f"{entry.display_name} alignment with deterministic regime and liquidity filters.",
                        trigger="Hold above opening range high with RVOL confirmation.",
                        entry_zone=f"{latest.close * 0.995:.2f} - {latest.close * 1.005:.2f}",
                        invalidation=f"{prior.low * 0.995:.2f}",
                        score_before_momentum=(
                            round(score_before_momentum, 4) if score_before_momentum is not None else None
                        ),
                        score_after_momentum=round(total, 4) if score_before_momentum is not None else None,
                        momentum_score_delta=(
                            round(momentum_score_delta, 6) if momentum_score_delta is not None else None
                        ),
                        momentum_realized_score_delta=(
                            round(momentum_realized_score_delta, 6)
                            if momentum_realized_score_delta is not None
                            else None
                        ),
                        momentum_rank_mode=active_config.mode if active_config.mode != "off" else "off",
                        targets=f"{latest.close * 1.02:.2f} / {latest.close * 1.04:.2f}",
                        reason_text=reason_text,
                        momentum_contribution=contribution_dict,
                    )
                )

        output.sort(key=lambda item: item.score, reverse=True)
        for idx, item in enumerate(output, start=1):
            item.rank = idx

        top_candidates = [asdict(item) for item in output if item.status == "top_candidate"][:top_n]
        watchlist = [asdict(item) for item in output if item.status == "watchlist"]
        no_trade = [asdict(item) for item in output if item.status == "no_trade"]

        return {
            "queue": [asdict(item) for item in output],
            "top_candidates": top_candidates,
            "watchlist_only": watchlist,
            "no_trade": no_trade,
            "summary": {
                "total": len(output),
                "top_candidate_count": len(top_candidates),
                "watchlist_count": len(watchlist),
                "no_trade_count": len(no_trade),
            },
        }
