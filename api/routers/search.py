"""Scenario A — POST /api/search (+ /api/search/stream SSE variant)."""
from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api.services import neptune, search

router = APIRouter(tags=["search"])


class SearchRequest(BaseModel):
    q: str = Field(min_length=1, max_length=500, description="자연어 검색어")
    persona: Optional[str] = None
    top_k: int = Field(default=10, ge=1, le=50)
    include_subgraph: bool = True


class SearchHitOut(BaseModel):
    sku_id: str
    score: float
    text: str
    metadata: Dict[str, Any]


class SearchResponse(BaseModel):
    hits: List[SearchHitOut]
    subgraph: Dict[str, Any]
    query_echo: str


def _retrieve(req: SearchRequest):
    """Retrieve, then apply the persona lens if one is active.

    With a persona we over-fetch, because the lens drops products whose
    ingredients the persona avoids and we still want `top_k` results back."""
    pool = min(req.top_k * 2, 50) if req.persona else req.top_k
    hits = search.hybrid_search(req.q, top_k=pool)
    if req.persona:
        hits = search.apply_persona_lens(hits, req.persona)[: req.top_k]
    return hits


@router.post("/search", response_model=SearchResponse)
def search_endpoint(req: SearchRequest) -> SearchResponse:
    hits = _retrieve(req)
    subgraph: Dict[str, Any] = {"nodes": [], "edges": []}
    if req.include_subgraph and hits:
        try:
            subgraph = neptune.subgraph_for_skus([h["sku_id"] for h in hits[:5]])
        except Exception:  # noqa: BLE001
            subgraph = {"nodes": [], "edges": [], "_error": "subgraph_unavailable"}
    return SearchResponse(
        hits=[SearchHitOut(**h) for h in hits],
        subgraph=subgraph,
        query_echo=req.q,
    )


def _sse(event: str, data: Dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/search/stream")
def search_stream(req: SearchRequest) -> StreamingResponse:
    """SSE variant — emits phase events for BM25/KNN/RRF/rerank progress
    plus a final `result` event with the same shape as POST /search.
    When `persona` is set, a `persona` phase follows rerank — the lens runs
    after retrieval (see services/search.py:apply_persona_lens).
    Web client `streamSSE<SearchResponse>` consumes the result event.
    Phases are estimated from a single hybrid_search() call (no per-stage
    instrumentation in services/search.py); the demo uses the breakdown
    purely as a visible progress indicator."""
    def stream():
        t0 = time.perf_counter()
        yield _sse("phase", {"name": "bm25", "detail": "Nori 한글 BM25"})
        yield _sse("phase", {"name": "knn", "detail": "Cohere embed-v4 KNN"})
        try:
            hits = _retrieve(req)
        except Exception as exc:  # noqa: BLE001
            yield _sse("phase", {"name": "error", "detail": str(exc)[:200]})
            yield _sse("result", {"hits": [], "subgraph": {"nodes": [], "edges": []}, "query_echo": req.q})
            return
        elapsed = int((time.perf_counter() - t0) * 1000)
        yield _sse("phase", {"name": "rrf", "ms": elapsed, "detail": "RRF fusion"})
        yield _sse("phase", {"name": "rerank", "detail": "Bedrock rerank-v3"})
        if req.persona:
            yield _sse("phase", {"name": "persona", "detail": f"페르소나 렌즈 {req.persona}"})
        subgraph: Dict[str, Any] = {"nodes": [], "edges": []}
        if req.include_subgraph and hits:
            try:
                subgraph = neptune.subgraph_for_skus([h["sku_id"] for h in hits[:5]])
            except Exception:  # noqa: BLE001
                subgraph = {"nodes": [], "edges": [], "_error": "subgraph_unavailable"}
        yield _sse("result", {
            "hits": hits,
            "subgraph": subgraph,
            "query_echo": req.q,
        })

    return StreamingResponse(stream(), media_type="text/event-stream")
