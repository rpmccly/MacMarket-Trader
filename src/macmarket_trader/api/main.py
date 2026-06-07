"""FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

from macmarket_trader.api.routes.admin import router as admin_router
from macmarket_trader.api.routes.admin import user_router
from macmarket_trader.api.routes.agent_mode import router as agent_mode_router
from macmarket_trader.api.routes.charts import router as charts_router
from macmarket_trader.api.routes.data_parity import router as data_parity_router
from macmarket_trader.api.routes.daily_target_book import router as daily_target_book_router
from macmarket_trader.api.routes.haco_heatmap import router as haco_heatmap_router
from macmarket_trader.api.routes.health import router as health_router
from macmarket_trader.api.routes.momentum_heatmap import router as momentum_heatmap_router
from macmarket_trader.api.routes.recommendations import router as recommendation_router
from macmarket_trader.api.routes.replay import router as replay_router
from macmarket_trader.api.routes.schwab import router as schwab_router
from macmarket_trader.api.security import validate_mutation_origin, validate_rate_limit
from macmarket_trader.config import settings, validate_auth_runtime_configuration
from macmarket_trader.logging_config import configure_logging

@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    validate_auth_runtime_configuration(settings)
    # Self-heal the schema and migrate legacy Agent Mode settings into Agent
    # Profiles on boot so the API works regardless of deploy ordering. Both steps
    # are idempotent and best-effort: a hiccup must never block app startup.
    try:
        from macmarket_trader.storage.db import apply_schema_updates
        from macmarket_trader.storage.db import SessionLocal
        from macmarket_trader.storage.repositories import AgentProfileRepository

        apply_schema_updates()
        AgentProfileRepository(SessionLocal).migrate_legacy_settings_to_profiles()
    except Exception:  # noqa: BLE001 - startup must not fail on schema/migration.
        pass
    yield


configure_logging()


def _api_docs_kwargs(environment: str, docs_enabled: bool) -> dict[str, str | None]:
    prod_like = environment.strip().lower() in {"prod", "production"}
    enabled = docs_enabled and not prod_like
    return {
        "docs_url": "/docs" if enabled else None,
        "redoc_url": "/redoc" if enabled else None,
        "openapi_url": "/openapi.json" if enabled else None,
    }


app = FastAPI(
    title="MacMarket-Trader API",
    version="0.1.0",
    lifespan=lifespan,
    **_api_docs_kwargs(settings.environment, settings.api_docs_enabled),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def security_guardrails(request, call_next):
    try:
        validate_mutation_origin(request)
    except HTTPException as exc:
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
    limited = validate_rate_limit(request)
    if limited is not None:
        return limited
    return await call_next(request)


app.include_router(health_router)
app.include_router(recommendation_router)
app.include_router(replay_router)
app.include_router(charts_router)
app.include_router(momentum_heatmap_router)
app.include_router(haco_heatmap_router)
app.include_router(schwab_router)

app.include_router(user_router)
app.include_router(agent_mode_router)
app.include_router(daily_target_book_router)
app.include_router(data_parity_router)
app.include_router(admin_router)
