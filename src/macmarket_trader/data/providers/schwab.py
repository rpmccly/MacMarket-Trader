"""Schwab Trader API market-data diagnostics.

Schwab support in this repo is intentionally read-only and diagnostic-only:
OAuth tokens are stored encrypted server-side, market-data calls are used by
the Market Data Parity Lab, and no broker/order endpoints are implemented.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from time import monotonic
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from cryptography.fernet import Fernet, InvalidToken

from macmarket_trader.config import Settings, settings
from macmarket_trader.data.providers.market_data import (
    DataNotEntitledError,
    MarketDataProvider,
    MarketProviderHealth,
    MarketSnapshot,
    ProviderUnavailableError,
    RTH_BUCKETS_BY_TIMEFRAME,
    RTH_SOURCE_TIMEFRAME,
    SymbolNotFoundError,
    US_EQUITY_TIMEZONE,
    _aggregate_regular_hours_intraday_bars,
    _format_rth_bucket_boundaries,
    _rth_source_page_target_count,
)
from macmarket_trader.domain.schemas import Bar
from macmarket_trader.domain.timeframes import validate_chart_timeframe
from macmarket_trader.storage.db import SessionLocal
from macmarket_trader.storage.repositories import ProviderOAuthRepository


SCHWAB_PROVIDER = "schwab"


class SchwabConfigurationError(Exception):
    """Raised when Schwab diagnostics are enabled but not safely configured."""


class SchwabAuthRequiredError(Exception):
    """Raised when Schwab OAuth is missing, expired, or reconnect is required."""


class SchwabProviderError(Exception):
    """Raised for Schwab market-data responses that are not usable."""


@dataclass(frozen=True)
class SchwabTokenBundle:
    access_token: str
    refresh_token: str | None
    token_type: str | None
    scope: str | None
    access_token_expires_at: datetime | None
    refresh_token_expires_at: datetime | None


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


def _shift_schwab_intraday_bar_end_to_start(bars: list[Bar], *, source_timeframe: str) -> list[Bar]:
    if source_timeframe.upper() != RTH_SOURCE_TIMEFRAME:
        return bars
    shifted: list[Bar] = []
    for bar in bars:
        timestamp = bar.timestamp
        if timestamp is None:
            shifted.append(bar)
            continue
        interval_start = timestamp.astimezone(UTC) - timedelta(minutes=30)
        shifted.append(
            Bar(
                date=interval_start.astimezone(US_EQUITY_TIMEZONE).date(),
                timestamp=interval_start,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
                rel_volume=bar.rel_volume,
                session_policy=bar.session_policy,
                source_session_policy=bar.source_session_policy,
                source_timeframe=bar.source_timeframe,
                provider=bar.provider,
            )
        )
    return shifted


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _safe_error_code(value: object) -> str:
    text = str(value or "").strip().lower().replace(" ", "_")
    cleaned = "".join(ch for ch in text if ch.isalnum() or ch in {"_", "-"})
    return (cleaned or "schwab_error")[:80]


def redact_schwab_text(value: object, cfg: Settings = settings) -> str:
    text = str(value or "").replace("\n", " ").replace("\r", " ").strip()
    for secret in (
        cfg.schwab_client_id,
        cfg.schwab_client_secret,
        cfg.schwab_token_encryption_key,
    ):
        if secret and secret.strip():
            text = text.replace(secret.strip(), "[redacted]")
    lower = text.lower()
    if "authorization:" in lower:
        text = "Schwab provider error included an Authorization header; value redacted."
    if "bearer " in text.lower():
        parts = text.split(" ")
        text = " ".join("[redacted]" if idx and parts[idx - 1].lower() == "bearer" else part for idx, part in enumerate(parts))
    return text[:300]


class SchwabTokenCipher:
    def __init__(self, key: str) -> None:
        normalized = str(key or "").strip()
        if not normalized:
            raise SchwabConfigurationError("SCHWAB_TOKEN_ENCRYPTION_KEY is required when Schwab diagnostics are enabled.")
        try:
            self._fernet = Fernet(normalized.encode("utf-8"))
        except Exception as exc:  # noqa: BLE001 - cryptography validates key shape
            raise SchwabConfigurationError("SCHWAB_TOKEN_ENCRYPTION_KEY is not a valid Fernet key.") from exc

    def encrypt(self, value: str | None) -> str:
        normalized = str(value or "")
        return self._fernet.encrypt(normalized.encode("utf-8")).decode("utf-8")

    def decrypt(self, value: str) -> str:
        try:
            return self._fernet.decrypt(str(value or "").encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise SchwabAuthRequiredError("stored_schwab_token_cannot_be_decrypted") from exc


def _cipher(cfg: Settings = settings) -> SchwabTokenCipher:
    return SchwabTokenCipher(cfg.schwab_token_encryption_key)


def _expires_at_from_seconds(seconds: object, *, now: datetime | None = None) -> datetime | None:
    try:
        parsed = int(seconds) if seconds is not None else 0
    except (TypeError, ValueError):
        parsed = 0
    if parsed <= 0:
        return None
    return (now or _utc_now()) + timedelta(seconds=parsed)


def parse_schwab_token_payload(payload: dict[str, Any], *, now: datetime | None = None) -> SchwabTokenBundle:
    access_token = str(payload.get("access_token") or "").strip()
    if not access_token:
        raise SchwabAuthRequiredError("schwab_token_response_missing_access_token")
    refresh_token = str(payload.get("refresh_token") or "").strip() or None
    refresh_expires = (
        payload.get("refresh_token_expires_in")
        or payload.get("refresh_expires_in")
        or payload.get("refresh_token_expires_at")
    )
    return SchwabTokenBundle(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type=str(payload.get("token_type") or "").strip() or None,
        scope=str(payload.get("scope") or "").strip() or None,
        access_token_expires_at=_expires_at_from_seconds(payload.get("expires_in"), now=now),
        refresh_token_expires_at=_expires_at_from_seconds(refresh_expires, now=now),
    )


def save_schwab_token_bundle(
    *,
    repo: ProviderOAuthRepository,
    bundle: SchwabTokenBundle,
    app_user_id: int | None,
    cfg: Settings = settings,
    refreshed: bool = False,
):
    cipher = _cipher(cfg)
    return repo.save_token_bundle(
        provider=SCHWAB_PROVIDER,
        app_user_id=app_user_id,
        encrypted_access_token=cipher.encrypt(bundle.access_token),
        encrypted_refresh_token=cipher.encrypt(bundle.refresh_token) if bundle.refresh_token is not None else None,
        access_token_expires_at=bundle.access_token_expires_at,
        refresh_token_expires_at=bundle.refresh_token_expires_at,
        token_type=bundle.token_type,
        scope=bundle.scope,
        status="connected",
        last_refresh_at=_utc_now() if refreshed else None,
    )


def schwab_oauth_configured(cfg: Settings = settings) -> bool:
    return bool(
        cfg.schwab_enabled
        and cfg.schwab_client_id.strip()
        and cfg.schwab_client_secret.strip()
        and cfg.schwab_redirect_uri.strip()
        and cfg.schwab_auth_url.strip()
        and cfg.schwab_token_url.strip()
        and cfg.schwab_market_data_base_url.strip()
    )


def exchange_code_for_tokens(code: str, *, cfg: Settings = settings) -> dict[str, Any]:
    if not schwab_oauth_configured(cfg):
        raise SchwabConfigurationError("schwab_oauth_not_configured")
    normalized_code = str(code or "").strip()
    if not normalized_code:
        raise SchwabAuthRequiredError("missing_schwab_authorization_code")
    credentials = f"{cfg.schwab_client_id.strip()}:{cfg.schwab_client_secret.strip()}".encode("utf-8")
    body = urlencode(
        {
            "grant_type": "authorization_code",
            "code": normalized_code,
            "redirect_uri": cfg.schwab_redirect_uri.strip(),
        }
    ).encode("utf-8")
    request = Request(
        cfg.schwab_token_url.strip(),
        data=body,
        headers={
            "Authorization": f"Basic {base64.b64encode(credentials).decode('ascii')}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=cfg.schwab_request_timeout_seconds) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise SchwabAuthRequiredError(f"schwab_token_exchange_http_{exc.code}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise SchwabProviderError(redact_schwab_text(exc, cfg)) from exc
    if not isinstance(payload, dict):
        raise SchwabAuthRequiredError("schwab_token_response_not_json_object")
    return payload


def _refresh_tokens(refresh_token: str, *, cfg: Settings = settings) -> dict[str, Any]:
    credentials = f"{cfg.schwab_client_id.strip()}:{cfg.schwab_client_secret.strip()}".encode("utf-8")
    body = urlencode({"grant_type": "refresh_token", "refresh_token": refresh_token}).encode("utf-8")
    request = Request(
        cfg.schwab_token_url.strip(),
        data=body,
        headers={
            "Authorization": f"Basic {base64.b64encode(credentials).decode('ascii')}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=cfg.schwab_request_timeout_seconds) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise SchwabAuthRequiredError(f"schwab_refresh_http_{exc.code}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise SchwabProviderError(redact_schwab_text(exc, cfg)) from exc
    if not isinstance(payload, dict):
        raise SchwabAuthRequiredError("schwab_refresh_response_not_json_object")
    return payload


def schwab_connection_status(
    *,
    repo: ProviderOAuthRepository | None = None,
    cfg: Settings = settings,
) -> dict[str, object]:
    oauth_repo = repo or ProviderOAuthRepository(SessionLocal)
    credentials_present = bool(cfg.schwab_client_id.strip() and cfg.schwab_client_secret.strip())
    encryption_key_present = bool(cfg.schwab_token_encryption_key.strip())
    configured = schwab_oauth_configured(cfg) and encryption_key_present
    token_row = oauth_repo.get_token(provider=SCHWAB_PROVIDER)
    now = _utc_now()
    token_status = "unconfigured"
    access_state = "missing"
    refresh_state = "missing"
    if cfg.schwab_enabled and not encryption_key_present:
        token_status = "missing_encryption_key"
    elif cfg.schwab_enabled and not schwab_oauth_configured(cfg):
        token_status = "unconfigured"
    elif token_row is None:
        token_status = "not_connected"
    else:
        token_status = token_row.status
        access_expires = _aware(token_row.access_token_expires_at)
        refresh_expires = _aware(token_row.refresh_token_expires_at)
        access_state = "unknown" if access_expires is None else ("valid" if access_expires > now else "refresh_available")
        refresh_state = (
            "missing"
            if not token_row.encrypted_refresh_token
            else "unknown"
            if refresh_expires is None
            else "valid"
            if refresh_expires > now
            else "expired"
        )
        if refresh_expires is not None and refresh_expires <= now:
            token_status = "reconnect_required"
            access_state = "expired"
        elif token_row.status in {"connected", "expired"} and (access_expires is None or access_expires > now):
            token_status = "connected"
        elif access_expires is not None and access_expires <= now:
            if token_row.encrypted_refresh_token:
                token_status = "connected"
                access_state = "refresh_available"
            else:
                token_status = "reconnect_required"
                access_state = "expired"
    oauth_connected = bool(token_row is not None and token_status == "connected")
    return {
        "provider": "schwab_market_data",
        "mode": "diagnostic",
        "status": "ok" if configured and token_status == "connected" else ("expired" if token_status in {"expired", "reconnect_required"} else "unconfigured" if not configured else "configured"),
        "configured": configured,
        "enabled": bool(cfg.schwab_enabled),
        "credentials_present": credentials_present,
        "encryption_key_present": encryption_key_present,
        "oauth_connected": oauth_connected,
        "token_status": token_status,
        "access_state": access_state,
        "refresh_state": refresh_state,
        "requires_reconnect": bool(token_row is None or token_status in {"not_connected", "reconnect_required", "missing_encryption_key", "unconfigured", "degraded"}),
        "access_token_expires_at": token_row.access_token_expires_at.isoformat() if token_row and token_row.access_token_expires_at else None,
        "refresh_token_expires_at": token_row.refresh_token_expires_at.isoformat() if token_row and token_row.refresh_token_expires_at else None,
        "last_refresh_at": token_row.last_refresh_at.isoformat() if token_row and token_row.last_refresh_at else None,
        "last_error": redact_schwab_text(token_row.last_error, cfg) if token_row and token_row.last_error else None,
        "details": (
            "Schwab diagnostic market data is connected. It is not the active production provider and does not enable broker execution."
            if configured and oauth_connected
            else "Schwab diagnostic market data is not connected or not fully configured. It is not the active production provider and does not enable broker execution."
        ),
        "operational_impact": "Diagnostic read-only comparison only. No broker routing, order placement, live trading, or production provider default changes.",
    }


class SchwabMarketDataProvider(MarketDataProvider):
    name = SCHWAB_PROVIDER

    def __init__(
        self,
        *,
        repo: ProviderOAuthRepository | None = None,
        cfg: Settings = settings,
    ) -> None:
        self.cfg = cfg
        self.repo = repo or ProviderOAuthRepository(SessionLocal)
        self.base_url = cfg.schwab_market_data_base_url.rstrip("/")
        self.timeout_seconds = cfg.schwab_request_timeout_seconds
        self._last_success_at: datetime | None = None
        self.last_aggregate_request_metadata: dict[str, object] | None = None

    def is_configured(self) -> bool:
        return schwab_oauth_configured(self.cfg) and bool(self.cfg.schwab_token_encryption_key.strip())

    def _access_token(self) -> str:
        if not self.is_configured():
            raise SchwabConfigurationError("schwab_market_data_not_configured")
        token_row = self.repo.get_token(provider=SCHWAB_PROVIDER)
        if token_row is None:
            raise SchwabAuthRequiredError("schwab_not_connected")
        if token_row.status not in {"connected", "expired"}:
            raise SchwabAuthRequiredError(token_row.status)
        now = _utc_now()
        refresh_expires = _aware(token_row.refresh_token_expires_at)
        if refresh_expires is not None and refresh_expires <= now:
            self.repo.mark_token_status(provider=SCHWAB_PROVIDER, status="reconnect_required", last_error="refresh_token_expired")
            raise SchwabAuthRequiredError("schwab_reconnect_required")
        cipher = _cipher(self.cfg)
        access_expires = _aware(token_row.access_token_expires_at)
        refresh_at = now + timedelta(seconds=max(0, int(self.cfg.schwab_access_token_refresh_leeway_seconds)))
        if access_expires is not None and access_expires <= refresh_at:
            refresh_token = cipher.decrypt(token_row.encrypted_refresh_token)
            if not refresh_token:
                self.repo.mark_token_status(provider=SCHWAB_PROVIDER, status="reconnect_required", last_error="missing_refresh_token")
                raise SchwabAuthRequiredError("schwab_reconnect_required")
            try:
                payload = _refresh_tokens(refresh_token, cfg=self.cfg)
                bundle = parse_schwab_token_payload(payload, now=now)
                if bundle.refresh_token is None:
                    bundle = SchwabTokenBundle(
                        access_token=bundle.access_token,
                        refresh_token=refresh_token,
                        token_type=bundle.token_type,
                        scope=bundle.scope,
                        access_token_expires_at=bundle.access_token_expires_at,
                        refresh_token_expires_at=token_row.refresh_token_expires_at,
                    )
                save_schwab_token_bundle(repo=self.repo, bundle=bundle, app_user_id=token_row.app_user_id, cfg=self.cfg, refreshed=True)
                return bundle.access_token
            except (SchwabAuthRequiredError, SchwabConfigurationError, SchwabProviderError) as exc:
                self.repo.mark_token_status(
                    provider=SCHWAB_PROVIDER,
                    status="reconnect_required" if isinstance(exc, SchwabAuthRequiredError) else "degraded",
                    last_error=redact_schwab_text(exc, self.cfg),
                )
                raise
        return cipher.decrypt(token_row.encrypted_access_token)

    def _request_json(self, path: str, query: dict[str, str]) -> dict[str, Any]:
        token = self._access_token()
        url = f"{self.base_url}{path}?{urlencode(query)}"
        request = Request(
            url=url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
            method="GET",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310
                payload = json.loads(response.read().decode("utf-8"))
                self._last_success_at = _utc_now()
                return payload if isinstance(payload, dict) else {"payload": payload}
        except HTTPError as exc:
            if exc.code in {401, 403}:
                status = "reconnect_required" if exc.code == 401 else "connected"
                self.repo.mark_token_status(provider=SCHWAB_PROVIDER, status=status, last_error=f"schwab_http_{exc.code}")
                if exc.code == 403:
                    raise DataNotEntitledError("Schwab market-data endpoint returned not entitled or forbidden.") from exc
                raise SchwabAuthRequiredError("schwab_reconnect_required") from exc
            if exc.code == 404:
                raise SymbolNotFoundError("Schwab returned 404 for the requested market-data resource.") from exc
            raise ProviderUnavailableError(f"Schwab HTTP {exc.code}: {redact_schwab_text(exc.reason, self.cfg)}") from exc
        except URLError as exc:
            raise ProviderUnavailableError(f"Schwab connection error: {redact_schwab_text(exc.reason, self.cfg)}") from exc
        except TimeoutError as exc:
            raise ProviderUnavailableError(f"Schwab request timed out after {self.timeout_seconds}s") from exc

    @staticmethod
    def _start_ms(days_back: int) -> str:
        return str(int((_utc_now() - timedelta(days=days_back)).timestamp() * 1000))

    @staticmethod
    def _end_ms() -> str:
        return str(int(_utc_now().timestamp() * 1000))

    def _price_history_query(self, *, symbol: str, timeframe: str, limit: int) -> tuple[dict[str, str], str]:
        tf = validate_chart_timeframe(timeframe)
        bounded_limit = max(1, int(limit or 1))
        base: dict[str, str] = {
            "symbol": symbol.upper(),
            "needExtendedHoursData": "false",
            "needPreviousClose": "true",
        }
        if tf == "1W":
            days = max(365, bounded_limit * 7 + 21)
            return {
                **base,
                "periodType": "year",
                "frequencyType": "weekly",
                "frequency": "1",
                "startDate": self._start_ms(days),
                "endDate": self._end_ms(),
            }, "1W"
        if tf == "1D":
            days = max(90, bounded_limit + 10)
            return {
                **base,
                "periodType": "year",
                "frequencyType": "daily",
                "frequency": "1",
                "startDate": self._start_ms(days),
                "endDate": self._end_ms(),
            }, "1D"
        days_by_tf = {
            "30M": max(10, int((bounded_limit / 13) * 1.8) + 10),
            "1H": max(20, int((bounded_limit / 7) * 1.8) + 10),
            "4H": max(40, int((bounded_limit / 2) * 1.8) + 10),
        }
        return {
            **base,
            "periodType": "day",
            "frequencyType": "minute",
            "frequency": "30",
            "startDate": self._start_ms(days_by_tf[tf]),
            "endDate": self._end_ms(),
        }, RTH_SOURCE_TIMEFRAME

    @staticmethod
    def _normalize_candle(candle: dict[str, Any], *, provider: str, source_timeframe: str) -> Bar:
        timestamp_value = candle.get("datetime") or candle.get("date") or candle.get("time")
        try:
            numeric = float(timestamp_value)
        except (TypeError, ValueError):
            numeric = 0.0
        if numeric > 10_000_000_000:
            timestamp = datetime.fromtimestamp(numeric / 1000.0, tz=UTC)
        elif numeric > 0:
            timestamp = datetime.fromtimestamp(numeric, tz=UTC)
        else:
            timestamp = _utc_now()
        return Bar(
            date=timestamp.astimezone(US_EQUITY_TIMEZONE).date(),
            timestamp=timestamp,
            open=float(candle["open"]),
            high=float(candle["high"]),
            low=float(candle["low"]),
            close=float(candle["close"]),
            volume=int(float(candle.get("volume") or 0)),
            rel_volume=None,
            session_policy="provider_session",
            source_session_policy="provider_regular_hours",
            source_timeframe=source_timeframe,
            provider=provider,
        )

    def fetch_raw_historical_bars(self, symbol: str, timeframe: str, limit: int) -> tuple[list[Bar], dict[str, object]]:
        normalized_symbol = str(symbol or "").strip().upper()
        if not normalized_symbol:
            raise ValueError("symbol is required")
        tf = validate_chart_timeframe(timeframe)
        query, source_timeframe = self._price_history_query(symbol=normalized_symbol, timeframe=tf, limit=limit)
        payload = self._request_json("/pricehistory", query)
        if payload.get("empty") is True:
            raise SymbolNotFoundError(f"No Schwab candles returned for {normalized_symbol}")
        candles = payload.get("candles") or []
        if not isinstance(candles, list):
            raise ProviderUnavailableError("Schwab pricehistory response missing candles list.")
        bars = [self._normalize_candle(item, provider=self.name, source_timeframe=source_timeframe) for item in candles if isinstance(item, dict)]
        bars.sort(key=lambda bar: bar.timestamp or datetime.combine(bar.date, datetime.min.time(), tzinfo=UTC))
        if not bars:
            return [], {
                "provider": self.name,
                "source_timeframe": source_timeframe,
                "output_timeframe": tf,
                "session_policy": "regular_hours",
                "source_session_policy": "provider_regular_hours",
                "regular_hours_timezone": str(US_EQUITY_TIMEZONE),
                "weekly_anchor": "schwab_provider_weekly_frequency" if tf == "1W" else None,
                "rth_bucket_boundaries": _format_rth_bucket_boundaries(tf) if tf in RTH_BUCKETS_BY_TIMEFRAME else [],
                "fallback_mode": False,
                "adjusted": "provider_default",
                "needExtendedHoursData": query.get("needExtendedHoursData"),
                "needPreviousClose": query.get("needPreviousClose"),
                "request_period_type": query.get("periodType"),
                "request_frequency_type": query.get("frequencyType"),
                "request_frequency": query.get("frequency"),
                "timestamp_convention": "bar_end" if source_timeframe == RTH_SOURCE_TIMEFRAME else "session_anchor",
                "aggregation_multiplier": query.get("frequency"),
                "aggregation_timespan": query.get("frequencyType"),
                "candles_returned": 0,
            }
        selection_limit = (
            _rth_source_page_target_count(tf, max(1, int(limit or 1)))
            if tf in RTH_BUCKETS_BY_TIMEFRAME
            else max(1, int(limit or 1))
        )
        selected = bars[-selection_limit:]
        metadata = {
            "provider": self.name,
            "source_timeframe": source_timeframe,
            "output_timeframe": tf,
            "session_policy": "provider_regular_hours",
            "source_session_policy": "provider_regular_hours",
            "regular_hours_timezone": str(US_EQUITY_TIMEZONE),
            "weekly_anchor": "schwab_provider_weekly_frequency" if tf == "1W" else None,
            "rth_bucket_boundaries": _format_rth_bucket_boundaries(tf) if tf in RTH_BUCKETS_BY_TIMEFRAME else [],
            "fallback_mode": False,
            "adjusted": "provider_default",
            "needExtendedHoursData": query.get("needExtendedHoursData"),
            "needPreviousClose": query.get("needPreviousClose"),
            "request_period_type": query.get("periodType"),
            "request_frequency_type": query.get("frequencyType"),
            "request_frequency": query.get("frequency"),
            "timestamp_convention": "bar_end" if source_timeframe == RTH_SOURCE_TIMEFRAME else "session_anchor",
            "aggregation_multiplier": query.get("frequency"),
            "aggregation_timespan": query.get("frequencyType"),
            "candles_returned": len(candles),
            "raw_selection_limit": selection_limit,
            "first_bar_timestamp": selected[0].timestamp.isoformat() if selected[0].timestamp else None,
            "last_bar_timestamp": selected[-1].timestamp.isoformat() if selected[-1].timestamp else None,
        }
        return selected, metadata

    def normalize_bars(self, bars: list[Bar], *, timeframe: str, limit: int) -> tuple[list[Bar], dict[str, object]]:
        tf = validate_chart_timeframe(timeframe)
        if tf in RTH_BUCKETS_BY_TIMEFRAME:
            aggregation_input = _shift_schwab_intraday_bar_end_to_start(bars, source_timeframe=RTH_SOURCE_TIMEFRAME)
            selected, metadata = _aggregate_regular_hours_intraday_bars(
                aggregation_input,
                output_timeframe=tf,
                limit=limit,
                provider=self.name,
                source_timeframe=RTH_SOURCE_TIMEFRAME,
                source_session_policy="provider_regular_hours",
            )
            metadata["fallback_mode"] = False
            metadata["adjusted"] = "provider_default"
            metadata["needExtendedHoursData"] = "false"
            metadata["source_timestamp_convention"] = "bar_end"
            metadata["timestamp_convention"] = "bar_start"
            metadata["timestamp_convention_adjustment"] = "schwab_intraday_bar_end_shifted_to_interval_start_for_rth_aggregation"
            metadata["aggregation_multiplier"] = 30
            metadata["aggregation_timespan"] = "minute"
            return selected, metadata
        selected = sorted(bars, key=lambda bar: bar.timestamp or datetime.combine(bar.date, datetime.min.time(), tzinfo=UTC))[-limit:]
        for bar in selected:
            bar.session_policy = "regular_hours"
            bar.source_session_policy = "provider_regular_hours"
            bar.source_timeframe = tf
            bar.provider = self.name
        first = selected[0] if selected else None
        last = selected[-1] if selected else None
        return selected, {
            "provider": self.name,
            "source_timeframe": tf,
            "output_timeframe": tf,
            "session_policy": "regular_hours",
            "source_session_policy": "provider_regular_hours",
            "regular_hours_timezone": str(US_EQUITY_TIMEZONE),
            "weekly_anchor": "schwab_provider_weekly_frequency" if tf == "1W" else None,
            "fallback_mode": False,
            "adjusted": "provider_default",
            "needExtendedHoursData": "false",
            "timestamp_convention": "session_anchor",
            "aggregation_multiplier": 1,
            "aggregation_timespan": "week" if tf == "1W" else "day",
            "first_bar_timestamp": first.timestamp.isoformat() if first and first.timestamp else None,
            "last_bar_timestamp": last.timestamp.isoformat() if last and last.timestamp else None,
        }

    def fetch_historical_bars(self, symbol: str, timeframe: str, limit: int) -> list[Bar]:
        raw, raw_metadata = self.fetch_raw_historical_bars(symbol, timeframe, limit)
        normalized, metadata = self.normalize_bars(raw, timeframe=timeframe, limit=limit)
        self.last_aggregate_request_metadata = {**raw_metadata, **metadata}
        return normalized

    def fetch_latest_snapshot(self, symbol: str, timeframe: str) -> MarketSnapshot:
        bars = self.fetch_historical_bars(symbol=symbol, timeframe=timeframe, limit=1)
        if not bars:
            raise SymbolNotFoundError(f"No Schwab latest bar returned for {symbol}")
        bar = bars[-1]
        return MarketSnapshot(
            symbol=str(symbol or "").upper(),
            timeframe=timeframe,
            as_of=bar.timestamp or datetime.combine(bar.date, datetime.min.time(), tzinfo=UTC),
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=bar.volume,
            source=self.name,
            fallback_mode=False,
        )

    def quotes(self, symbols: list[str]) -> dict[str, dict[str, object]]:
        cleaned = ",".join(sorted({str(symbol or "").strip().upper() for symbol in symbols if str(symbol or "").strip()}))
        if not cleaned:
            return {}
        payload = self._request_json("/quotes", {"symbols": cleaned, "fields": "quote"})
        return {str(key).upper(): value for key, value in payload.items() if isinstance(value, dict)}

    def fetch_index_snapshot(self, symbol: str):  # noqa: ANN201
        raise NotImplementedError("Schwab diagnostic provider does not implement index snapshots in this pass.")

    def health_check(self, sample_symbol: str) -> MarketProviderHealth:
        status = schwab_connection_status(repo=self.repo, cfg=self.cfg)
        if not status.get("configured"):
            return MarketProviderHealth(
                provider="schwab_market_data",
                mode="diagnostic",
                status="warning",
                details=str(status["details"]),
                configured=False,
                feed="stocks",
                sample_symbol=sample_symbol,
            )
        if status.get("token_status") != "connected":
            return MarketProviderHealth(
                provider="schwab_market_data",
                mode="diagnostic",
                status="warning",
                details=str(status["details"]),
                configured=True,
                feed="stocks",
                sample_symbol=sample_symbol,
            )
        started = monotonic()
        try:
            self.fetch_latest_snapshot(sample_symbol, "1D")
            elapsed = round((monotonic() - started) * 1000, 2)
            return MarketProviderHealth(
                provider="schwab_market_data",
                mode="diagnostic",
                status="ok",
                details="Schwab diagnostic market-data probe succeeded. This does not enable broker execution.",
                configured=True,
                feed="stocks",
                sample_symbol=sample_symbol,
                latency_ms=elapsed,
                last_success_at=self._last_success_at,
            )
        except (SchwabAuthRequiredError, SchwabConfigurationError, DataNotEntitledError, ProviderUnavailableError, SymbolNotFoundError, HTTPError, URLError, TimeoutError, ValueError, KeyError, OSError) as exc:
            elapsed = round((monotonic() - started) * 1000, 2)
            return MarketProviderHealth(
                provider="schwab_market_data",
                mode="diagnostic",
                status="warning",
                details=f"Schwab diagnostic probe failed: {redact_schwab_text(exc, self.cfg)}",
                configured=True,
                feed="stocks",
                sample_symbol=sample_symbol,
                latency_ms=elapsed,
                last_success_at=self._last_success_at,
            )


__all__ = [
    "SCHWAB_PROVIDER",
    "SchwabAuthRequiredError",
    "SchwabConfigurationError",
    "SchwabMarketDataProvider",
    "SchwabProviderError",
    "SchwabTokenBundle",
    "SchwabTokenCipher",
    "exchange_code_for_tokens",
    "parse_schwab_token_payload",
    "redact_schwab_text",
    "save_schwab_token_bundle",
    "schwab_connection_status",
    "schwab_oauth_configured",
]
