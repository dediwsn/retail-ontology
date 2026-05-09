"""Chat endpoint integration tests.

Validates request payload contracts (422 on invalid input) and SSE response
shape when `agent.converse_stream` is mocked. No AWS / Bedrock calls.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from tests.fixtures import AGENT_STREAM_EVENTS


@pytest.mark.parametrize("payload", [
    {"session_id": "sess1234"},                            # missing message
    {"session_id": "ab", "message": "hi"},                 # session_id < min_length=4
    {"session_id": "sess1234", "message": "x" * 4001},     # message > max_length=4000
])
@pytest.mark.asyncio
async def test_chat_rejects_invalid_payload(client, payload) -> None:
    """ChatRequest enforces session_id (4..128) and message (1..4000) bounds."""
    resp = await client.post("/api/chat", json=payload)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_chat_streams_sse_with_mocked_agent(client) -> None:
    """With converse_stream mocked, /api/chat emits one `event:` line per
    yielded event in the same order the agent produced them."""
    def fake_stream(**_kwargs):
        for ev in AGENT_STREAM_EVENTS:
            yield ev

    with patch("api.routers.chat.agent.converse_stream", side_effect=fake_stream):
        resp = await client.post(
            "/api/chat",
            json={"session_id": "sess1234", "message": "민감성 피부에 좋은 성분?"},
        )

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    body = resp.text
    # Each fixture event becomes one SSE frame: `event: <type>\ndata: <json>\n\n`
    assert body.count("event: phase") == 1
    assert body.count("event: delta") == 2
    assert body.count("event: stop") == 1
    # Korean payload survives JSON encoding (ensure_ascii=False in router)
    assert "센텔라" in body
