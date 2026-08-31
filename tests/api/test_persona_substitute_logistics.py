"""Persona extension to Scenario F (substitute) and Scenario H (logistics).

F and H were persona-blind: F could recommend an alternative the active persona
must avoid, and H's map had no way to show where that persona's demand actually
sits. Both now read the same ontology facts Scenario A's lens reads.

Neptune is mocked at the module object shared by every caller
(`api.services.neptune`), so one patch covers the routers and the
`persona_context()` helper alike.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

PERSONA_ROW = [{
    "avoided": ["ing_retinol"],
    "preferred": ["ing_ceramide"],
    "bricks": ["10000123"],
}]

BASE_ROW = [{
    "p": {"~id": "n1", "~labels": ["Product"],
          "~properties": {"sku_id": "sku_base", "name_ko": "기준 세럼",
                          "brand_id": "brd_a", "price_krw": 20000}},
    "cat": {"~id": "n2", "~labels": ["Category"],
            "~properties": {"gs1_brick_code": "10000123",
                            "retail_category_ko": "세럼"}},
    "ings": ["ing_water"],
    "concerns": ["cnc_dry"],
}]

CAND_ROWS = [
    {"alt": {"~id": "n3", "~labels": ["Product"],
             "~properties": {"sku_id": "sku_retinol", "name_ko": "레티놀 세럼",
                             "brand_id": "brd_b", "price_krw": 21000}},
     "alt_ings": ["ing_retinol", "ing_water"],
     "shared_ings": ["ing_water"], "shared_concerns": ["cnc_dry"],
     "overlap_score": 8},
    {"alt": {"~id": "n4", "~labels": ["Product"],
             "~properties": {"sku_id": "sku_ceramide", "name_ko": "세라마이드 세럼",
                             "brand_id": "brd_c", "price_krw": 20500}},
     "alt_ings": ["ing_ceramide", "ing_water"],
     "shared_ings": ["ing_water"], "shared_concerns": [],
     "overlap_score": 3},
]


def _substitute_cypher(query, *, parameters=None):
    if "MATCH (p:Persona)" in query:
        return PERSONA_ROW
    if "MATCH (p:Product {sku_id: $sku})" in query:
        return BASE_ROW
    return CAND_ROWS


# ─── Scenario F ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_substitute_drops_persona_conflict(client) -> None:
    """A substitute the persona must avoid is not a substitute."""
    with patch("api.services.neptune.open_cypher", side_effect=_substitute_cypher):
        resp = await client.post(
            "/api/substitute",
            json={"sku_id": "sku_base", "top_k": 8, "persona": "per_pregnant"},
        )
    assert resp.status_code == 200
    skus = [c["sku_id"] for c in resp.json()["candidates"]]
    assert "sku_retinol" not in skus
    assert "sku_ceramide" in skus


@pytest.mark.asyncio
async def test_substitute_boosts_preferred_ingredient(client) -> None:
    """sku_ceramide has the lower raw overlap (3 vs 8) but wins once the
    persona's preferred ingredient is counted."""
    from api.routers.substitute import PERSONA_PREFERRED_BONUS
    with patch("api.services.neptune.open_cypher", side_effect=_substitute_cypher):
        resp = await client.post(
            "/api/substitute",
            json={"sku_id": "sku_base", "top_k": 8, "persona": "per_sensitive_skin"},
        )
    top = resp.json()["candidates"][0]
    assert top["sku_id"] == "sku_ceramide"
    assert top["persona_preferred"] == ["ing_ceramide"]
    # overlap 3 + price bonus 4 (delta 2.5%) + persona bonus
    assert top["score"] == 3 + 4 + PERSONA_PREFERRED_BONUS


@pytest.mark.asyncio
async def test_substitute_can_flag_conflicts_instead_of_dropping(client) -> None:
    with patch("api.services.neptune.open_cypher", side_effect=_substitute_cypher):
        resp = await client.post(
            "/api/substitute",
            json={"sku_id": "sku_base", "persona": "per_pregnant",
                  "drop_persona_conflicts": False},
        )
    flagged = [c for c in resp.json()["candidates"] if c["sku_id"] == "sku_retinol"]
    assert flagged and flagged[0]["persona_conflict"] == ["ing_retinol"]


@pytest.mark.asyncio
async def test_substitute_without_persona_is_unchanged(client) -> None:
    with patch("api.services.neptune.open_cypher", side_effect=_substitute_cypher):
        resp = await client.post("/api/substitute", json={"sku_id": "sku_base"})
    cands = resp.json()["candidates"]
    assert [c["sku_id"] for c in cands] == ["sku_retinol", "sku_ceramide"]
    assert all(c["persona_conflict"] == [] and c["persona_preferred"] == []
               for c in cands)


# ─── Scenario H ────────────────────────────────────────────────────────────

REGION_ROWS = [{"region_code": "11", "name_ko": "서울", "level": "sido",
                "lat": 37.5, "lng": 127.0, "population": 9_400_000},
               {"region_code": "42", "name_ko": "강원", "level": "sido",
                "lat": 37.8, "lng": 128.2, "population": 1_500_000}]
WH_ROWS = [{"wh_id": "wh_1", "name_ko": "서울 DC", "type": "dc", "region_code": "11",
            "lat": 37.5, "lng": 127.0, "capacity_pallets": 100,
            "cold_chain": True, "operator_label": "이마트"}]
DEMAND_ROWS = [{"region_code": "42", "members": 37}]


def _network_cypher(query, *, parameters=None):
    if "MATCH (m:Member)-[:LIVES_IN]" in query:
        return DEMAND_ROWS
    if "MATCH (r:Region)" in query:
        return REGION_ROWS
    if "MATCH (w:Warehouse)" in query:
        return WH_ROWS
    return []


@pytest.mark.asyncio
async def test_network_without_persona_has_no_overlay(client) -> None:
    with patch("api.routers.logistics.neptune.open_cypher", side_effect=_network_cypher):
        resp = await client.get("/api/logistics/network")
    body = resp.json()
    assert all(r["persona_member_count"] is None for r in body["regions"])
    assert all(w["persona_member_count"] is None for w in body["warehouses"])


@pytest.mark.asyncio
async def test_network_with_persona_attaches_demand(client) -> None:
    """강원 has camper members; 서울 has none. Zero must be reported as 0,
    not None — 'asked, none here' is the signal the map needs."""
    with patch("api.routers.logistics.neptune.open_cypher", side_effect=_network_cypher):
        resp = await client.get("/api/logistics/network?persona=per_camper")
    body = resp.json()
    counts = {r["region_code"]: r["persona_member_count"] for r in body["regions"]}
    assert counts == {"11": 0, "42": 37}
    # the only warehouse sits in 서울, where this persona has nobody
    assert body["warehouses"][0]["persona_member_count"] == 0


@pytest.mark.asyncio
async def test_network_survives_demand_query_failure(client) -> None:
    """The map must render even if the overlay query fails."""
    def flaky(query, *, parameters=None):
        if "MATCH (m:Member)-[:LIVES_IN]" in query:
            raise RuntimeError("neptune down")
        return _network_cypher(query, parameters=parameters)

    with patch("api.routers.logistics.neptune.open_cypher", side_effect=flaky):
        resp = await client.get("/api/logistics/network?persona=per_camper")
    assert resp.status_code == 200
    assert len(resp.json()["regions"]) == 2
