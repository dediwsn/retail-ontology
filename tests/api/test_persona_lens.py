"""Persona lens + insights output-guardrail tests.

Covers the two gaps closed after the runtime trace in
`docs/diagrams/ontology-rag-llm.puml`:

  1. `SearchRequest.persona` was declared but never read, so the global
     PersonaSwitch had no effect on Scenario A.
  2. `/api/insights` applied no guardrail at all, despite the documented
     "guardrails on chat input and insights output" contract.

Neptune and Bedrock are mocked at the import site; no AWS calls are made.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from api.services import search as search_svc

PERSONA_ROW = [{
    "avoided": ["ing_retinol"],
    "preferred": ["ing_ceramide"],
    "bricks": ["10000123"],
}]

FACTS_ROWS = [
    {"sku_id": "sku_safe", "ingredients": ["ing_ceramide"], "bricks": ["10000123"]},
    {"sku_id": "sku_unsafe", "ingredients": ["ing_retinol"], "bricks": ["10000999"]},
    {"sku_id": "sku_plain", "ingredients": ["ing_water"], "bricks": ["10000999"]},
]

HITS = [
    {"sku_id": "sku_unsafe", "score": 0.99, "text": "레티놀 세럼", "metadata": {}},
    {"sku_id": "sku_plain", "score": 0.80, "text": "일반 로션", "metadata": {}},
    {"sku_id": "sku_safe", "score": 0.70, "text": "세라마이드 크림", "metadata": {}},
]


def _fake_cypher(query, *, parameters=None):
    return PERSONA_ROW if "MATCH (p:Persona)" in query else FACTS_ROWS


# ─── apply_persona_lens ────────────────────────────────────────────────────

def test_lens_is_identity_without_persona() -> None:
    assert search_svc.apply_persona_lens(HITS, None) is HITS
    assert search_svc.apply_persona_lens([], "per_pregnant") == []


def test_lens_drops_avoided_ingredient() -> None:
    with patch("api.services.neptune.open_cypher", side_effect=_fake_cypher):
        out = search_svc.apply_persona_lens(HITS, "per_pregnant")
    assert [h["sku_id"] for h in out] == ["sku_safe", "sku_plain"]


def test_lens_boosts_preferred_and_reorders() -> None:
    """sku_safe starts last (0.70) but matches a preferred ingredient AND a
    favourite brick, so it outranks sku_plain (0.80) after the lens."""
    with patch("api.services.neptune.open_cypher", side_effect=_fake_cypher):
        out = search_svc.apply_persona_lens(HITS, "per_sensitive_skin")
    assert out[0]["sku_id"] == "sku_safe"
    assert out[0]["score"] == pytest.approx(
        0.70 + search_svc.PREFERRED_BOOST + search_svc.FAVORITE_BRICK_BOOST
    )
    assert out[0]["metadata"]["persona_preferred"] == ["ing_ceramide"]
    assert out[0]["metadata"]["persona_favorite_category"] == ["10000123"]
    assert out[0]["metadata"]["persona_id"] == "per_sensitive_skin"


def test_lens_leaves_non_product_hits_untouched() -> None:
    """A review id has no Product row; it must survive the lens unchanged."""
    hits = HITS + [{"sku_id": "rev_001", "score": 0.5, "text": "리뷰", "metadata": {}}]
    with patch("api.services.neptune.open_cypher", side_effect=_fake_cypher):
        out = search_svc.apply_persona_lens(hits, "per_pregnant")
    assert any(h["sku_id"] == "rev_001" for h in out)


def test_lens_survives_neptune_failure() -> None:
    """A persona lens is an enhancement — a graph outage must not fail search."""
    with patch("api.services.neptune.open_cypher", side_effect=RuntimeError("neptune down")):
        assert search_svc.apply_persona_lens(HITS, "per_camper") == HITS


def test_lens_noop_when_persona_has_no_preferences() -> None:
    empty = [{"avoided": [], "preferred": [], "bricks": []}]
    with patch("api.services.neptune.open_cypher", return_value=empty):
        assert search_svc.apply_persona_lens(HITS, "per_blank") == HITS


# ─── router wiring ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_applies_lens_when_persona_present(client) -> None:
    with (
        patch("api.routers.search.search.hybrid_search", return_value=HITS) as hs,
        patch("api.routers.search.search.apply_persona_lens",
              return_value=HITS[:1]) as lens,
        patch("api.routers.search.neptune.subgraph_for_skus",
              return_value={"nodes": [], "edges": []}),
    ):
        resp = await client.post(
            "/api/search",
            json={"q": "선크림", "top_k": 5, "persona": "per_pregnant"},
        )
    assert resp.status_code == 200
    lens.assert_called_once()
    assert lens.call_args[0][1] == "per_pregnant"
    # over-fetch so the lens can drop hits and still return top_k
    assert hs.call_args.kwargs["top_k"] == 10


@pytest.mark.asyncio
async def test_search_skips_lens_without_persona(client) -> None:
    with (
        patch("api.routers.search.search.hybrid_search", return_value=HITS) as hs,
        patch("api.routers.search.search.apply_persona_lens") as lens,
        patch("api.routers.search.neptune.subgraph_for_skus",
              return_value={"nodes": [], "edges": []}),
    ):
        resp = await client.post("/api/search", json={"q": "선크림", "top_k": 5})
    assert resp.status_code == 200
    lens.assert_not_called()
    assert hs.call_args.kwargs["top_k"] == 5


# ─── insights output guardrail ─────────────────────────────────────────────

def test_insights_output_guardrail_scrubs() -> None:
    from api.routers import insights
    with patch("api.routers.insights.guardrails.apply",
               return_value=("scrubbed", True)) as g:
        assert insights._guard_output("raw answer") == "scrubbed"
    g.assert_called_once()
    assert g.call_args.kwargs["source"] == "OUTPUT"


def test_insights_output_guardrail_never_raises() -> None:
    """Insights degrades to the raw answer rather than 500-ing."""
    from api.routers import insights
    with patch("api.routers.insights.guardrails.apply",
               side_effect=RuntimeError("guardrail unavailable")):
        assert insights._guard_output("raw answer") == "raw answer"


def test_insights_output_guardrail_skips_empty() -> None:
    from api.routers import insights
    with patch("api.routers.insights.guardrails.apply") as g:
        assert insights._guard_output("") == ""
    g.assert_not_called()
