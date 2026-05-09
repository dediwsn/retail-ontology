"""Pure-function unit tests for correctness-critical service helpers.

Three targets — chosen because (a) they are pure (no AWS dependencies,
no I/O), (b) they encode invariants that the cypher-conventions skill
and ADR-0010 explicitly call out, and (c) silent regressions here
would mis-rank or mis-route tool calls without raising errors.

- `data.load._flatten_props` — Neptune SET n += $p only accepts scalar
  property values; a regression would silently coerce wrong types into
  Cypher and fail at MERGE time deep inside the loader.
- `api.services.search._rrf_merge` — Reciprocal Rank Fusion over
  BM25 + KNN result envelopes. Wrong score formula would mis-rank
  candidates without surfacing as an error.
- `api.services.agent._dispatch_tool` — name-to-implementation routing
  for 7 agent tools. A silent rename or branch fall-through would route
  tool calls to the wrong implementation.
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from data.load import _flatten_props
from api.services.search import _rrf_merge
from api.services.agent import _dispatch_tool


# ─── data.load._flatten_props ────────────────────────────────────────────

class TestFlattenProps:
    def test_scalars_pass_through_unchanged(self) -> None:
        out = _flatten_props({"name": "센텔라", "price": 28000, "active": True, "weight": 1.5})
        assert out == {"name": "센텔라", "price": 28000, "active": True, "weight": 1.5}

    def test_none_values_are_dropped(self) -> None:
        out = _flatten_props({"name": "센텔라", "synonym": None, "price": 100})
        assert out == {"name": "센텔라", "price": 100}
        assert "synonym" not in out

    def test_scalar_list_joined_with_semicolon(self) -> None:
        out = _flatten_props({"tags": ["민감성", "수분", "진정"]})
        assert out == {"tags": "민감성;수분;진정"}

    def test_mixed_scalar_list_still_joined(self) -> None:
        out = _flatten_props({"counts": [1, 2, 3]})
        assert out == {"counts": "1;2;3"}

    def test_complex_list_serialized_as_json(self) -> None:
        out = _flatten_props({"refs": [{"id": 1}, {"id": 2}]})
        assert json.loads(out["refs"]) == [{"id": 1}, {"id": 2}]

    def test_dict_value_serialized_as_json(self) -> None:
        out = _flatten_props({"meta": {"source": "kfda", "version": 2}})
        assert json.loads(out["meta"]) == {"source": "kfda", "version": 2}

    def test_empty_input_returns_empty_dict(self) -> None:
        assert _flatten_props({}) == {}

    def test_korean_unicode_preserved_in_json_encoding(self) -> None:
        # ensure_ascii=False is critical — Neptune accepts UTF-8 strings,
        # but \uXXXX-escaped strings would defeat search/text matching.
        out = _flatten_props({"meta": {"label_ko": "민감성 피부"}})
        assert "민감성" in out["meta"]
        assert "\\u" not in out["meta"]


# ─── api.services.search._rrf_merge ──────────────────────────────────────

class TestRRFMerge:
    def test_overlapping_top_ranks_get_highest_fused_score(self) -> None:
        """A doc that ranks #1 in both BM25 and KNN should rank #1 after RRF."""
        bm25 = {"hits": {"hits": [
            {"_id": "doc_a", "_source": {}},
            {"_id": "doc_b", "_source": {}},
        ]}}
        knn = {"hits": {"hits": [
            {"_id": "doc_a", "_source": {}},
            {"_id": "doc_c", "_source": {}},
        ]}}
        fused = _rrf_merge(bm25, knn)
        assert fused[0]["_id"] == "doc_a"
        # Top doc should carry RRF score = 1/(60+1) + 1/(60+1) = 2/61
        assert abs(fused[0]["_rrf_score"] - 2.0 / 61) < 1e-9

    def test_disjoint_top_ranks_preserve_per_source_order(self) -> None:
        """When BM25 and KNN have no overlap, both #1 docs tie for top."""
        bm25 = {"hits": {"hits": [{"_id": "doc_a", "_source": {}}]}}
        knn = {"hits": {"hits": [{"_id": "doc_b", "_source": {}}]}}
        fused = _rrf_merge(bm25, knn)
        ids = {h["_id"] for h in fused}
        assert ids == {"doc_a", "doc_b"}
        # Both should have identical RRF score (each appears once at rank 0)
        assert abs(fused[0]["_rrf_score"] - fused[1]["_rrf_score"]) < 1e-9

    def test_higher_rank_outranks_lower_rank(self) -> None:
        """Doc at rank 0 in both sources beats doc at rank 5 in one source."""
        bm25 = {"hits": {"hits": [
            {"_id": f"doc_{i}", "_source": {}} for i in range(6)
        ]}}
        knn = {"hits": {"hits": [
            {"_id": "doc_5", "_source": {}},
            {"_id": "doc_0", "_source": {}},
        ]}}
        fused = _rrf_merge(bm25, knn)
        # doc_0 = rank 0 in BM25 + rank 1 in KNN = 1/61 + 1/62 ~ 0.0327
        # doc_5 = rank 5 in BM25 + rank 0 in KNN = 1/66 + 1/61 ~ 0.0316
        # → doc_0 should rank above doc_5
        positions = {h["_id"]: i for i, h in enumerate(fused)}
        assert positions["doc_0"] < positions["doc_5"]

    def test_missing_id_skipped_silently(self) -> None:
        """A hit with empty/missing _id must not blow up RRF, just be ignored."""
        bm25 = {"hits": {"hits": [
            {"_id": "doc_a", "_source": {}},
            {"_id": "", "_source": {}},  # malformed; skip
        ]}}
        fused = _rrf_merge(bm25)
        assert len(fused) == 1
        assert fused[0]["_id"] == "doc_a"

    def test_empty_envelope_returns_empty(self) -> None:
        assert _rrf_merge({"hits": {"hits": []}}) == []
        assert _rrf_merge({}) == []  # no `hits` key at all


# ─── api.services.agent._dispatch_tool ───────────────────────────────────

class TestDispatchTool:
    def test_unknown_tool_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="unknown tool"):
            _dispatch_tool("not_a_real_tool", {}, actor_id="alice")

    def test_semantic_search_routes_to_hybrid_search(self) -> None:
        with patch("api.services.agent.search.hybrid_search", return_value=[{"sku_id": "x"}]) as m:
            out = _dispatch_tool("semantic_search", {"query": "테스트", "top_k": 5}, actor_id="alice")
        m.assert_called_once_with("테스트", top_k=5)
        assert out == [{"sku_id": "x"}]

    def test_kb_lookup_routes_to_kb_lookup(self) -> None:
        with patch("api.services.agent.kb.lookup", return_value=[{"doc": "y"}]) as m:
            out = _dispatch_tool("kb_lookup", {"query": "q", "top_k": 3}, actor_id="alice")
        m.assert_called_once_with("q", top_k=3)
        assert out == [{"doc": "y"}]

    def test_neptune_subgraph_routes_to_subgraph_for_skus(self) -> None:
        fake_graph = {"nodes": [], "edges": []}
        with patch("api.services.agent.neptune.subgraph_for_skus", return_value=fake_graph) as m:
            out = _dispatch_tool("neptune_subgraph", {"sku_ids": ["sku_001"], "hops": 1}, actor_id="alice")
        m.assert_called_once_with(["sku_001"], hops=1)
        assert out is fake_graph

    def test_memory_recall_uses_explicit_actor_id_override(self) -> None:
        """If args contains actor_id, it overrides the dispatch-level actor_id."""
        with patch("api.services.agent.memory.retrieve_long_term", return_value=[]) as m:
            _dispatch_tool(
                "memory_recall",
                {"query": "preferences", "actor_id": "bob"},
                actor_id="alice",
            )
        m.assert_called_once_with("bob", "preferences")

    def test_memory_recall_falls_back_to_dispatch_actor_id(self) -> None:
        with patch("api.services.agent.memory.retrieve_long_term", return_value=[]) as m:
            _dispatch_tool("memory_recall", {"query": "preferences"}, actor_id="alice")
        m.assert_called_once_with("alice", "preferences")

    def test_default_top_k_applied_when_missing(self) -> None:
        """semantic_search default top_k is 10."""
        with patch("api.services.agent.search.hybrid_search", return_value=[]) as m:
            _dispatch_tool("semantic_search", {"query": "q"}, actor_id="alice")
        m.assert_called_once_with("q", top_k=10)
