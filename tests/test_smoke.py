"""Smoke tests — verify the api package and its routers import cleanly.

This is the minimum bar: every router file must be parseable, every service
must import without side-effect failure, and the FastAPI app must instantiate.
Richer Pydantic-model and route tests live under `tests/api/` (added later).
"""
from __future__ import annotations

import importlib

import pytest


def test_api_main_imports() -> None:
    """`api.main` must import — exercises FastAPI app construction + middleware."""
    mod = importlib.import_module("api.main")
    assert hasattr(mod, "app"), "api.main must expose `app` (the FastAPI instance)"


@pytest.mark.parametrize(
    "router_name",
    [
        "auth",
        "chat",
        "coverage",
        "health",
        "ingest",
        "insights",
        "logistics",
        "objects",
        "ontology",
        "ops",
        "persona_match",
        "price",
        "safety",
        "search",
        "substitute",
    ],
)
def test_router_imports(router_name: str) -> None:
    """Every registered router under `api.routers.*` must import.

    Catches f-string SyntaxErrors and circular imports introduced by recent edits.
    Mirrors the AST validation in `.claude/commands/test-all.md`.
    """
    mod = importlib.import_module(f"api.routers.{router_name}")
    assert hasattr(mod, "router"), (
        f"api.routers.{router_name} must expose `router` (APIRouter instance)"
    )


def test_config_loads() -> None:
    """`api.config.get_settings()` must construct from the environment."""
    from api.config import get_settings

    settings = get_settings()
    assert settings is not None
