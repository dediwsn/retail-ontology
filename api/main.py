"""
FastAPI entry. Mounts routers, configures CORS, exposes /healthz for ALB
target group health checks (compute-stack tg-api).
"""
from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.config import get_settings
from api.middleware_auth import AuthMiddleware
from api.routers import (
    acquisition, auth, chat, churn, coverage, health, ingest, insights,
    logistics, objects, ontology, ops, persona_match, price, safety,
    search, substitute, tier_up, vip,
)

logger = logging.getLogger("ontology.api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    settings = get_settings()
    logger.info(
        "startup ok region=%s kb=%s guardrail=%s memory=%s opensearch_index=%s",
        settings.aws_region, settings.bedrock_kb_id, settings.bedrock_guardrail_id,
        settings.agentcore_memory_id, settings.opensearch_index,
    )
    yield
    logger.info("shutdown")


app = FastAPI(
    title="Ontology Retail API",
    version="0.1.0",
    description="FastAPI backend — search / chat / insights / ingest",
    lifespan=lifespan,
)

settings = get_settings()
# CORS — wildcard origins with credentials is forbidden by the spec and
# unsafe with non-conforming clients. We allow credentials only when an
# explicit origin list is provided. With wildcard, credentials are off.
_origins = [o.strip() for o in settings.cors_allow_origins.split(",") if o.strip()]
_has_wildcard = "*" in _origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins or ["*"],
    allow_credentials=not _has_wildcard,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Origin-Auth-Token"],
    max_age=600,
)
# Cognito JWT validation + X-Origin-Auth-Token enforcement.
# Modes controlled by DEMO_PUBLIC_MODE / REQUIRE_ORIGIN_AUTH env vars.
app.add_middleware(AuthMiddleware)

app.include_router(health.router)
app.include_router(auth.router, prefix="/api")
app.include_router(search.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(insights.router, prefix="/api")
app.include_router(ingest.router, prefix="/api")
app.include_router(churn.router, prefix="/api")
app.include_router(acquisition.router, prefix="/api")
app.include_router(tier_up.router, prefix="/api")
app.include_router(coverage.router, prefix="/api")
app.include_router(vip.router, prefix="/api")
app.include_router(objects.router, prefix="/api")
app.include_router(ontology.router, prefix="/api")
app.include_router(logistics.router, prefix="/api")
app.include_router(ops.router, prefix="/api")
app.include_router(persona_match.router, prefix="/api")
app.include_router(price.router, prefix="/api")
app.include_router(safety.router, prefix="/api")
app.include_router(substitute.router, prefix="/api")


@app.middleware("http")
async def access_log(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = int((time.perf_counter() - start) * 1000)
    logger.info(
        "%s %s -> %s %dms",
        request.method, request.url.path, response.status_code, duration_ms,
    )
    return response


@app.exception_handler(Exception)
async def unhandled(_: Request, exc: Exception):
    logger.exception("unhandled exception", exc_info=exc)
    return JSONResponse(status_code=500, content={"error": "internal", "type": type(exc).__name__})
