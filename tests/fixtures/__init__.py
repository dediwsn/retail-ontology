"""Shared realistic mock payloads for tests/api/ integration tests.

Inline mock dicts inside test files were starting to diverge — every router
test ended up rebuilding its own Neptune row shape, OpenSearch envelope,
and Bedrock response slightly differently. Centralising them here gives
new tests a starting point that already matches the real wire shape.

Conventions:
- Python module (not JSON) so tests can compose with `**fixtures.NEPTUNE_PRODUCT_ROW`.
- One canonical example per dependency surface, plus minimal variants
  (e.g. `NEPTUNE_PRODUCT_ROW_WITH_VIOLATION`) only when a router branches
  on the variant. Keep this file small — divergence is what fixtures are
  meant to prevent.
- All keys mirror the actual openCypher / AOSS / Bedrock response shapes.
"""
from __future__ import annotations

from typing import Any, Dict, List

# ─── Neptune openCypher response rows ────────────────────────────────────
# `neptune.open_cypher` returns List[Dict[str, Any]] where each dict's keys
# are the RETURN clause names. Node values are dicts with `~id`, `~labels`,
# `~properties` keys (Neptune's openCypher JSON shape).

NEPTUNE_NODE_PRODUCT: Dict[str, Any] = {
    "~id": "sku_001",
    "~labels": ["Product"],
    "~properties": {
        "sku_id": "sku_001",
        "name_ko": "민감성 피부용 무기자차 선크림",
        "name_en": "Mineral Sunscreen for Sensitive Skin",
        "price_krw": 28000,
        "brand_id": "brand_aveene",
    },
}

NEPTUNE_NODE_PERSONA: Dict[str, Any] = {
    "~id": "per_sensitive",
    "~labels": ["Persona"],
    "~properties": {
        "persona_id": "per_sensitive",
        "name_ko": "민감성 피부",
        "is_spine": True,
    },
}

NEPTUNE_NODE_CONCERN: Dict[str, Any] = {
    "~id": "concern_redness",
    "~labels": ["Concern"],
    "~properties": {"concern_id": "concern_redness", "name_ko": "홍조 진정"},
}

NEPTUNE_NODE_INGREDIENT: Dict[str, Any] = {
    "~id": "inci:centella-asiatica",
    "~labels": ["Ingredient"],
    "~properties": {"ingredient_id": "inci:centella-asiatica", "name_ko": "센텔라"},
}

# Persona-match profile_q row
NEPTUNE_PERSONA_PROFILE_ROW: Dict[str, Any] = {
    "per": NEPTUNE_NODE_PERSONA,
    "concerns": [NEPTUNE_NODE_CONCERN],
    "preferred": [NEPTUNE_NODE_INGREDIENT],
    "avoided": [],
}

# Persona-match score_q row (Product + scoring fields)
NEPTUNE_PERSONA_SCORE_ROW: Dict[str, Any] = {
    "prod": NEPTUNE_NODE_PRODUCT,
    "concern_match": 1,
    "prefer_score": 1,
    "violation_count": 0,
    "violations": [],
}

# Insights _aggregate_trends row
NEPTUNE_TREND_ROW: Dict[str, Any] = {
    "trend": {
        "~id": "trend_clean_beauty",
        "~labels": ["Trend"],
        "~properties": {"trend_id": "trend_clean_beauty", "name_ko": "클린 뷰티"},
    },
    "ingredients": ["센텔라", "히알루론산", "나이아신아마이드"],
    "fanout": 3,
}


# ─── OpenSearch hit envelopes ────────────────────────────────────────────
# AOSS returns `{"hits": {"hits": [{"_id":..., "_score":..., "_source":...}, ...]}}`.
# `_rrf_merge` reads `raw["hits"]["hits"][i]["_id"]`.

OPENSEARCH_BM25_RESPONSE: Dict[str, Any] = {
    "hits": {
        "hits": [
            {"_id": "sku_001", "_score": 8.21, "_source": {"text": "민감성 피부용 무기자차 선크림"}},
            {"_id": "sku_002", "_score": 6.13, "_source": {"text": "센텔라 진정 세럼"}},
            {"_id": "sku_003", "_score": 4.02, "_source": {"text": "히알루론산 보습 토너"}},
        ]
    }
}

OPENSEARCH_KNN_RESPONSE: Dict[str, Any] = {
    "hits": {
        "hits": [
            # Note: deliberately overlapping with BM25 hits to exercise RRF merge
            {"_id": "sku_002", "_score": 0.91, "_source": {"text": "센텔라 진정 세럼"}},
            {"_id": "sku_001", "_score": 0.87, "_source": {"text": "민감성 피부용 무기자차 선크림"}},
            {"_id": "sku_004", "_score": 0.74, "_source": {"text": "약산성 클렌저"}},
        ]
    }
}


# ─── Bedrock Converse responses ──────────────────────────────────────────
# bedrock-runtime.converse() returns this shape for non-streaming.

BEDROCK_CONVERSE_TEXT_RESPONSE: Dict[str, Any] = {
    "output": {
        "message": {
            "role": "assistant",
            "content": [
                {"text": "최근 28일 클린 뷰티 트렌드는 센텔라와 히알루론산 중심입니다."}
            ],
        }
    },
    "stopReason": "end_turn",
    "usage": {"inputTokens": 120, "outputTokens": 45},
}

BEDROCK_CONVERSE_EMPTY_RESPONSE: Dict[str, Any] = {
    "output": {"message": {"role": "assistant", "content": [{"text": ""}]}}
}


# ─── Agent stream events ────────────────────────────────────────────────
# `agent.converse_stream` yields `{"type": ..., "data": {...}}` dicts.

AGENT_STREAM_EVENTS: List[Dict[str, Any]] = [
    {"type": "phase", "data": {"name": "memory-recall", "detail": "장기 메모리 조회"}},
    {"type": "delta", "data": {"text": "안녕하세요. "}},
    {"type": "delta", "data": {"text": "민감성 피부에는 센텔라가 좋습니다."}},
    {"type": "stop", "data": {"final": "안녕하세요. 민감성 피부에는 센텔라가 좋습니다."}},
]
