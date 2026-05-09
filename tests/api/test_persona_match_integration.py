"""Persona-match endpoint integration tests.

Validates request payload contracts (422 on invalid input), 404 for unknown
persona, and response shape when neptune.open_cypher is mocked. No AWS calls.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from tests.fixtures import (
    NEPTUNE_PERSONA_PROFILE_ROW,
    NEPTUNE_PERSONA_SCORE_ROW,
)


@pytest.mark.parametrize("payload", [
    {"top_k": 5},                                           # missing persona_id
    {"persona_id": "per_sensitive", "top_k": 999},          # top_k > 30
])
@pytest.mark.asyncio
async def test_persona_match_rejects_invalid_payload(client, payload) -> None:
    """PersonaMatchRequest enforces persona_id (1..64) and top_k (1..30)."""
    resp = await client.post("/api/persona-match", json=payload)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_persona_match_unknown_persona_returns_404(client) -> None:
    """Profile query returns no rows → router raises 404, not 500."""
    with patch("api.routers.persona_match.neptune.open_cypher", return_value=[]):
        resp = await client.post(
            "/api/persona-match",
            json={"persona_id": "per_does_not_exist", "top_k": 5},
        )
    assert resp.status_code == 404
    assert "persona not found" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_persona_match_returns_recommendations_with_mocked_neptune(client) -> None:
    """With profile + score queries mocked, /api/persona-match returns the
    PersonaMatchResponse shape with at least one recommendation."""
    # neptune.open_cypher is called twice by the router: (1) profile, (2) scoring.
    # Use side_effect to return different responses per call.
    with patch(
        "api.routers.persona_match.neptune.open_cypher",
        side_effect=[
            [NEPTUNE_PERSONA_PROFILE_ROW],
            [NEPTUNE_PERSONA_SCORE_ROW],
        ],
    ):
        resp = await client.post(
            "/api/persona-match",
            json={"persona_id": "per_sensitive", "top_k": 5},
        )

    assert resp.status_code == 200
    body = resp.json()
    # PersonaMatchResponse shape
    assert "persona" in body
    assert "concerns" in body
    assert "preferred_ingredients" in body
    assert "avoided_ingredients" in body
    assert "recommendations" in body
    assert "warnings" in body
    assert "subgraph" in body
    # Mocked score row had violation_count=0 → it's a recommendation, not a warning
    assert len(body["recommendations"]) == 1
    assert body["recommendations"][0]["sku_id"] == "sku_001"
    assert body["recommendations"][0]["violation_count"] == 0
    # Subgraph wires persona → concern
    assert any(n["data"]["label"] == "Persona" for n in body["subgraph"]["nodes"])
    assert any(e["data"]["label"] == "HAS_CONCERN" for e in body["subgraph"]["edges"])


@pytest.mark.asyncio
async def test_persona_match_violation_routes_to_warnings(client) -> None:
    """A scored product with violation_count > 0 must end up in `warnings`,
    not `recommendations` — this is the safety gate of the scenario."""
    violating_score_row = {
        **NEPTUNE_PERSONA_SCORE_ROW,
        "violation_count": 1,
        "violations": ["inci:fragrance"],
    }
    with patch(
        "api.routers.persona_match.neptune.open_cypher",
        side_effect=[
            [NEPTUNE_PERSONA_PROFILE_ROW],
            [violating_score_row],
        ],
    ):
        resp = await client.post(
            "/api/persona-match",
            json={"persona_id": "per_sensitive", "top_k": 5},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["recommendations"]) == 0
    assert len(body["warnings"]) == 1
    assert body["warnings"][0]["violations"] == ["inci:fragrance"]
