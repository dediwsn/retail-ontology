"""Insights endpoint integration tests.

Validates request payload contracts (422 on invalid input) and response
shape when downstream services (neptune.open_cypher + bedrock_runtime)
are mocked. No AWS calls.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tests.fixtures import (
    BEDROCK_CONVERSE_EMPTY_RESPONSE,
    BEDROCK_CONVERSE_TEXT_RESPONSE,
    NEPTUNE_TREND_ROW,
)


@pytest.mark.parametrize("payload", [
    {"period_days": 28},                         # missing q
    {"q": "트렌드", "period_days": 999},          # period_days > 180
    {"q": "x" * 501},                            # q exceeds max_length=500
])
@pytest.mark.asyncio
async def test_insights_rejects_invalid_payload(client, payload) -> None:
    """InsightsRequest enforces q (1..500 chars) and period_days (1..180)."""
    resp = await client.post("/api/insights", json=payload)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_insights_returns_response_with_mocked_services(client) -> None:
    """With neptune trends + bedrock converse mocked, /api/insights returns
    InsightsResponse (answer_ko + chart_spec + drill_down_subgraph)."""
    fake_bedrock_client = MagicMock()
    fake_bedrock_client.converse.return_value = BEDROCK_CONVERSE_TEXT_RESPONSE

    with (
        patch("api.routers.insights.neptune.open_cypher", return_value=[NEPTUNE_TREND_ROW]),
        patch("api.routers.insights.bedrock_runtime", return_value=fake_bedrock_client),
    ):
        resp = await client.post(
            "/api/insights",
            json={"q": "클린 뷰티 트렌드", "period_days": 28},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert "answer_ko" in body
    assert "chart_spec" in body
    assert "drill_down_subgraph" in body
    assert isinstance(body["chart_spec"], dict)


@pytest.mark.asyncio
async def test_insights_falls_back_when_no_trends(client) -> None:
    """When neptune returns 0 trend rows, the answer_ko fallback message kicks
    in instead of an empty string."""
    fake_bedrock_client = MagicMock()
    fake_bedrock_client.converse.return_value = BEDROCK_CONVERSE_EMPTY_RESPONSE

    with (
        patch("api.routers.insights.neptune.open_cypher", return_value=[]),
        patch("api.routers.insights.bedrock_runtime", return_value=fake_bedrock_client),
    ):
        resp = await client.post(
            "/api/insights",
            json={"q": "존재하지 않는 트렌드", "period_days": 7},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert "트렌드 데이터가 부족합니다" in body["answer_ko"]
