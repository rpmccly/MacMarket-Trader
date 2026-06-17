"""Application configuration models."""

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-backed configuration values."""

    app_name: str = "MacMarket-Trader"
    environment: str = "dev"
    database_url: str = "sqlite:///./macmarket_trader.db"
    log_level: str = "INFO"
    risk_dollars_per_trade: float = 1000.0
    paper_max_order_notional: float = 1000.0
    commission_per_trade: float = 0.0
    commission_per_contract: float = 0.65
    max_portfolio_heat: float = 0.06
    max_position_notional: float = 0.20
    audit_persistence_enabled: bool = True
    llm_enabled: bool = False
    llm_provider: str = "mock"
    llm_model: str = ""
    openai_api_key: str = ""
    llm_api_key: str = ""
    llm_timeout_seconds: float = 12.0
    llm_max_output_tokens: int = 1200
    llm_temperature: float = 0.2
    risk_calendar_enabled: bool = True
    risk_calendar_provider: str = "static"
    risk_calendar_mode: str = "warn"
    risk_calendar_default_block_high_impact: bool = True
    earnings_avoidance_enabled: bool = True
    earnings_block_days_before: int = 1
    earnings_block_days_after: int = 1
    macro_event_block_before_minutes: int = 60
    macro_event_block_after_minutes: int = 60
    high_vol_block_enabled: bool = True
    high_vol_intraday_range_threshold: float = 0.04
    high_vol_gap_threshold: float = 0.03
    vix_high_threshold: float = 30.0
    index_risk_enabled: bool = True
    vix_caution_level: float = 20.0
    vix_restricted_level: float = 30.0
    vix_spike_caution_pct: float = 10.0
    spx_gap_caution_pct: float = 1.0
    spx_gap_restricted_pct: float = 2.0
    rut_underperform_caution_pct: float = -1.0
    ndx_underperform_caution_pct: float = -1.0
    index_data_stale_minutes: int = 60
    intraday_rth_session_required: bool = True
    intraday_rth_violation_mode: str = "caution"

    # auth/email/provider config
    auth_provider: str = "mock"
    clerk_jwt_issuer: str = ""
    clerk_jwks_url: str = ""
    clerk_jwt_audience: str = ""
    clerk_secret_key: str = ""
    clerk_api_base_url: str = "https://api.clerk.com"
    require_mfa_for_admin: bool = True
    enforce_global_mfa: bool = False
    email_provider: str = "console"
    cors_allowed_origins: list[str] = Field(default_factory=lambda: ["http://127.0.0.1:9500", "http://localhost:9500"])
    security_allowed_origins: list[str] = Field(default_factory=list)
    security_origin_check_enabled: bool = True
    security_rate_limit_enabled: bool = True
    api_docs_enabled: bool = True

    app_base_url: str = "http://localhost:9500"

    resend_api_key: str = ""
    resend_from_email: str = "noreply@macmarket-trader.local"
    brand_from_name: str = "MacMarket Trader"
    sms_provider: str = "twilio"
    sms_notifications_enabled: bool = True
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = "+1XXXXXXXXXX"
    twilio_messaging_service_sid: str = ""
    twilio_request_timeout_seconds: int = 10
    sms_max_messages_per_user_per_day: int = 20
    sms_max_messages_per_run: int = 25
    # Self-hosted at /brand/<file> from the Next.js public dir, served by the
    # production tunnel. The base64 embed in email_templates.py is the deeper
    # fallback so emails render even if this URL fails to load.
    brand_logo_url: str = "https://macmarket.io/brand/square_console_ticks_lockup_light.png"
    # console_url is no longer a separately-configurable field. It always
    # mirrors app_base_url — outbound emails (invite welcome CTA, approval CTA)
    # build their links off the same base URL the operator already configures
    # via APP_BASE_URL. Eliminating the localhost fallback prevents production
    # invites from emitting localhost URLs when CONSOLE_URL was not also set.

    # market data provider config
    market_data_provider: str = "fallback"
    market_data_enabled: bool = False
    alpaca_api_key_id: str = Field(default="", validation_alias=AliasChoices("APCA_API_KEY_ID", "APCA-API-KEY-ID"))
    alpaca_api_secret_key: str = Field(default="", validation_alias=AliasChoices("APCA_API_SECRET_KEY", "APCA-API-SECRET-KEY"))
    alpaca_market_data_base_url: str = "https://data.alpaca.markets"
    alpaca_market_data_feed: str = "iex"
    market_data_request_timeout_seconds: int = 8
    market_data_latest_cache_ttl_seconds: int = 10
    market_data_option_snapshot_cache_ttl_seconds: int = 30
    market_data_option_snapshot_stale_seconds: int = 86_400
    market_data_historical_cache_ttl_seconds: int = 120
    options_max_strike_snap_abs: float = 5.0
    options_max_strike_snap_pct: float = 0.025
    polygon_enabled: bool = False
    polygon_api_key: str = ""
    polygon_base_url: str = "https://api.polygon.io"
    polygon_timeout_seconds: int = 8
    workflow_demo_fallback: bool = False

    # Schwab Trader API market data. Schwab can be selected as the read-only
    # production market-data provider with MARKET_DATA_PROVIDER=schwab, and is
    # also used by the admin Market Data Parity Lab. This does not enable
    # broker routing, live trading, or order placement.
    schwab_enabled: bool = False
    schwab_client_id: str = ""
    schwab_client_secret: str = ""
    schwab_redirect_uri: str = "https://api.macmarket.io/auth/schwab/callback"
    schwab_base_url: str = "https://api.schwabapi.com"
    schwab_auth_url: str = "https://api.schwabapi.com/v1/oauth/authorize"
    schwab_token_url: str = "https://api.schwabapi.com/v1/oauth/token"
    schwab_market_data_base_url: str = "https://api.schwabapi.com/marketdata/v1"
    schwab_request_timeout_seconds: int = 8
    schwab_access_token_refresh_leeway_seconds: int = 90
    schwab_token_encryption_key: str = ""

    # Admin-only Market Data Parity Lab controls.
    data_parity_enabled: bool = True
    data_parity_default_lookback_bars: int = 250
    data_parity_max_lookback_bars: int = 500
    data_parity_max_symbols: int = 10
    data_parity_save_snapshots: bool = True

    # news provider config
    news_provider: str = "mock"
    news_polygon_max_articles: int = 10
    news_cache_ttl_seconds: int = 300

    # macro calendar provider config
    macro_calendar_provider: str = "mock"
    fred_api_key: str = ""
    fred_base_url: str = "https://api.stlouisfed.org/fred"
    fred_timeout_seconds: int = 8

    # broker provider config
    broker_provider: str = "mock"
    alpaca_paper_base_url: str = "https://paper-api.alpaca.markets"

    # deterministic recommendation quality gates
    min_expected_rr: float = 1.4
    max_event_continuation_volatility: float = 0.045
    min_catalyst_source_quality_score: float = 0.0

    # Momentum Intelligence Layer ranking influence (Phase B1).
    # off    = do not compute or attach a momentum ranking contribution.
    # shadow = compute and attach the contribution as explanation only;
    #          rank/score is unchanged. (Default — safest while Thinkorswim
    #          parity fixtures remain pending.)
    # active = apply bounded contribution (≤ ±20 score points) to the rank.
    # The contribution is bounded, audited, and never approves, rejects,
    # sizes, or routes trades. See docs/momentum-intelligence-layer.md.
    momentum_ranking_mode: str = Field(
        default="shadow",
        validation_alias=AliasChoices(
            "MACMARKET_MOMENTUM_RANKING_MODE",
            "MOMENTUM_RANKING_MODE",
        ),
    )

    # Phase B6 — safety guard for active Momentum ranking mode. Active
    # contribution only applies when *both* momentum_ranking_mode=="active"
    # and momentum_active_ranking_allowed is truthy. Default False so
    # production cannot silently flip ranking behavior even if someone
    # changes MACMARKET_MOMENTUM_RANKING_MODE without coordinating with
    # the operator. Truthy values: ``true`` / ``1`` / ``yes``
    # (case-insensitive).
    momentum_active_ranking_allowed: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "MACMARKET_ALLOW_MOMENTUM_ACTIVE_RANKING",
            "ALLOW_MOMENTUM_ACTIVE_RANKING",
        ),
    )

    # Phase B6.1 — operator-tunable scale applied to the bounded Momentum
    # ranking contribution **after** Phase B1's raw score-unit math runs.
    # Raw contribution stays in score units (max ±20). The applied
    # ranking-score delta is ``raw / 100 * active_delta_scale``, so at the
    # default 0.35 a +20 raw contribution becomes +0.07 on the [0, 1]
    # ranking score — keeping Momentum meaningful without saturating
    # too many candidates at 1.000. Stored as a string so pydantic does
    # not raise on bad input; ``_resolve_active_delta_scale`` clamps to
    # [0.0, 1.0] and falls back to 0.35 with an invalid-reason code.
    momentum_active_delta_scale: str = Field(
        default="0.35",
        validation_alias=AliasChoices(
            "MACMARKET_MOMENTUM_ACTIVE_DELTA_SCALE",
            "MOMENTUM_ACTIVE_DELTA_SCALE",
        ),
    )

    # Phase C0 — True Momentum strategy-family scaffolding mode.
    # disabled         = no Phase C strategy candidates generated, only
    #                    status/specs available via the read-only API.
    # research_preview = render specs and resolved status only; still
    #                    does not generate queue candidates, approve,
    #                    reject, size, route, open, close, or settle
    #                    trades. Requires the guard env var below.
    # active           = reserved for a future Phase C1; resolves to
    #                    research_preview in Phase C0.
    # See ``docs/true-momentum-strategy-families.md``.
    true_momentum_strategy_mode: str = Field(
        default="disabled",
        validation_alias=AliasChoices(
            "MACMARKET_TRUE_MOMENTUM_STRATEGY_MODE",
            "TRUE_MOMENTUM_STRATEGY_MODE",
        ),
    )

    # Phase C0 — explicit guard for the True Momentum strategy-family
    # scaffolding. ``research_preview``/``active`` require this to be
    # truthy; otherwise the effective mode is forced back to ``disabled``
    # with the ``true_momentum_strategy_mode_blocked_by_guard`` reason
    # code. Truthy values: ``true`` / ``1`` / ``yes`` / ``on``
    # (case-insensitive). Default False so production cannot silently
    # flip Phase C state.
    allow_true_momentum_strategy_families: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "MACMARKET_ALLOW_TRUE_MOMENTUM_STRATEGY_FAMILIES",
            "ALLOW_TRUE_MOMENTUM_STRATEGY_FAMILIES",
        ),
    )

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    @model_validator(mode="after")
    def prefer_openai_api_key(self) -> "Settings":
        """Prefer OPENAI_API_KEY while preserving LLM_API_KEY as a legacy fallback."""

        if self.openai_api_key.strip():
            self.llm_api_key = self.openai_api_key
        return self

    @property
    def console_url(self) -> str:
        return self.app_base_url


settings = Settings()


def validate_auth_runtime_configuration(cfg: Settings = settings) -> None:
    """Fail closed when mock auth is configured outside explicit local/test environments."""

    auth_provider = cfg.auth_provider.strip().lower()
    environment = cfg.environment.strip().lower()
    if auth_provider == "mock" and environment not in {"dev", "local", "test"}:
        raise RuntimeError(
            "AUTH_PROVIDER=mock is only allowed when ENVIRONMENT is one of: dev, local, test. "
            f"Received ENVIRONMENT={cfg.environment!r}."
        )
