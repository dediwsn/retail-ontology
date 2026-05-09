"""Insights endpoint integration tests.

Validates request payload contracts (422 on invalid input) and response
shape when downstream services (neptune.open_cypher + bedrock_runtime)
are mocked. No AWS calls.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tests.fixtures import NEPTUNE_TREND_ROW


@pytest.mark.asyncio
async def test_insights_rejects_missing_q(client) -> None:
    resp = await client.post("/api/insights", json={"period_days": 28})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_insights_rejects_period_out_of_range(client) -> None:
    """InsightsRequest.period_days has ge=1, le=180."""
    resp = await client.post("/api/insights", json={"q": "트렌드", "period_days": 999})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_insights_rejects_oversized_q(client) -> None:
    """InsightsRequest.q has max_length=500."""
    resp = await client.post("/api/insights", json={"q": "x" * 501})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_insights_returns_response_with_mocked_services(client) -> None:
    """With neptune trends + bedrock converse mocked, /api/insights returns
    InsightsResponse (answer_ko + chart_spec + drill_down_subgraph)."""
    fake_bedrock_client = MagicMock()
    fake_bedrock_client.converse.return_value = {
        "output": {
            "message": {
                "role": "assistant",
                "content": [{"text": "최근 28일 클린 뷰티 트렌드 분석입니다."}],
            }
        }
    }

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
    # InsightsResponse shape
    assert "answer_ko" in body
    assert "chart_spec" in body
    assert "drill_down_subgraph" in body
    assert isinstance(body["chart_spec"], dict)


@pytest.mark.asyncio
async def test_insights_falls_back_when_no_trends(client) -> None:
    """When neptune returns 0 trend rows, the answer_ko fallback message kicks
    in instead of an empty string."""
    fake_bedrock_client = MagicMock()
    # Bedrock generator returns nothing — bedrock_summarize yields no tokens
    fake_bedrock_client.converse.return_value = {
        "output": {"message": {"role": "assistant", "content": [{"text": ""}]}}
    }

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
