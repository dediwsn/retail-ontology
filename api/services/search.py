"""
Hybrid search: OpenSearch BM25 (Nori) + KNN (Cohere embed) → Bedrock Rerank.

Pipeline (spec § 7.1):
  1. Embed query (Cohere)
  2. OpenSearch hybrid query: BM25 on Korean text + KNN on vector field
  3. Bedrock Rerank top-100 → top-k via cross-region inference profile
  4. Guardrails sweep before rerank (PII safety per spec § 10.2)
"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any, Dict, List, Optional, TypedDict
from urllib.parse import urlparse

from opensearchpy import AWSV4SignerAuth, OpenSearch, RequestsHttpConnection

from api.aws_clients import bedrock_runtime, session
from api.config import get_settings
from api.services import embedding, guardrails


class SearchHit(TypedDict):
    sku_id: str
    score: float
    text: str
    metadata: Dict[str, Any]


def hybrid_search(
    query: str,
    *,
    top_k: int = 10,
    candidate_pool: int = 100,
    apply_guardrails: bool = True,
    rerank: bool = True,
) -> List[SearchHit]:
    settings = get_settings()
    if apply_guardrails:
        scrubbed = guardrails.apply_or_none(query, source="INPUT") or query
    else:
        scrubbed = query

    qvec = embedding.embed_query(scrubbed)

    # AOSS rejects OpenSearch's `hybrid` query plugin
    # ('unsupported_operation_exception'). We run match (BM25/Nori) and KNN
    # as separate searches and merge with Reciprocal Rank Fusion (RRF).
    # RRF gives quality close to native hybrid (k≈60 is the standard tuning).
    knn_body = {
        "size": candidate_pool,
        "query": {
            "knn": {
                "bedrock-knowledge-base-default-vector": {
                    "vector": qvec, "k": candidate_pool,
                }
            }
        },
        "_source": ["AMAZON_BEDROCK_TEXT_CHUNK", "AMAZON_BEDROCK_METADATA"],
    }
    bm25_body = {
        "size": candidate_pool,
        "query": {
            "match": {
                "AMAZON_BEDROCK_TEXT_CHUNK": {
                    "query": scrubbed, "analyzer": "korean_nori",
                }
            }
        },
        "_source": ["AMAZON_BEDROCK_TEXT_CHUNK", "AMAZON_BEDROCK_METADATA"],
    }
    client = _os_client()
    knn_raw = client.search(index=settings.opensearch_index, body=knn_body)
    bm25_raw = client.search(index=settings.opensearch_index, body=bm25_body)
    hits_raw = _rrf_merge(knn_raw, bm25_raw, k=60)

    candidates: List[SearchHit] = []
    for h in hits_raw:
        src = h.get("_source", {})
        meta = _parse_metadata(src.get("AMAZON_BEDROCK_METADATA", ""))
        # AOSS doesn't accept custom _id; original SKU/review id is in metadata
        original_id = meta.get("sku_id") or meta.get("review_id") or h.get("_id", "")
        candidates.append(SearchHit(
            sku_id=original_id,
            score=float(h.get("_rrf_score") or h.get("_score", 0.0)),
            text=src.get("AMAZON_BEDROCK_TEXT_CHUNK", ""),
            metadata=meta,
        ))

    if not rerank or not settings.bedrock_reranker_inference_profile_arn or not candidates:
        return candidates[:top_k]

    # Reranker is optional — Cohere rerank-v3 may not be available in all
    # regions/accounts. Fall back to KNN+BM25 RRF order on any error.
    try:
        return _bedrock_rerank(scrubbed, candidates, top_k)
    except Exception:
        return candidates[:top_k]


def _bedrock_rerank(query: str, candidates: List[SearchHit], top_k: int) -> List[SearchHit]:
    settings = get_settings()
    docs = [{"text": c["text"]} for c in candidates]
    body = {"query": query, "documents": docs, "top_n": top_k}
    resp = bedrock_runtime().invoke_model(
        modelId=settings.bedrock_reranker_inference_profile_arn,
        body=json.dumps(body),
        contentType="application/json",
        accept="application/json",
    )
    payload = json.loads(resp["body"].read())
    out: List[SearchHit] = []
    for r in payload.get("results", []):
        idx = r["index"]
        c = dict(candidates[idx])
        c["score"] = float(r.get("relevance_score", 0.0))
        out.append(c)  # type: ignore[arg-type]
    return out


def _parse_metadata(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"_raw": raw}
    return {}


def _rrf_merge(
    *raws: Dict[str, Any], k: int = 60,
) -> List[Dict[str, Any]]:
    """
    Reciprocal Rank Fusion: score(d) = sum_i 1/(k + rank_i(d)).
    Standard k=60 from the original RRF paper. Higher k gives smoother fusion;
    lower k weights top-ranked candidates more heavily.
    """
    scores: Dict[str, float] = {}
    pool: Dict[str, Dict[str, Any]] = {}
    for raw in raws:
        hits = raw.get("hits", {}).get("hits", []) or []
        for rank, h in enumerate(hits):
            hid = h.get("_id", "")
            if not hid:
                continue
            scores[hid] = scores.get(hid, 0.0) + 1.0 / (k + rank + 1)
            pool[hid] = h  # keep one copy per id (last wins; equivalent fields)
    fused = sorted(pool.values(),
                   key=lambda h: scores.get(h.get("_id", ""), 0.0),
                   reverse=True)
    for h in fused:
        h["_rrf_score"] = scores.get(h.get("_id", ""), 0.0)
    return fused


@lru_cache(maxsize=1)
def _os_client() -> OpenSearch:
    """opensearch-py with SigV4 — manual signing via botocore had inconsistent
    header normalization that AOSS rejects with 403 (same issue we hit in
    scripts/create_kb_index.py)."""
    settings = get_settings()
    host = urlparse(settings.opensearch_endpoint).netloc or settings.opensearch_endpoint
    creds = session().get_credentials()
    return OpenSearch(
        hosts=[{"host": host, "port": 443}],
        http_auth=AWSV4SignerAuth(creds, settings.aws_region, "aoss"),
        use_ssl=True, verify_certs=True,
        connection_class=RequestsHttpConnection, pool_maxsize=4,
        timeout=settings.request_timeout_seconds,
    )


# ─── Persona lens (Scenario A) ─────────────────────────────────────────────
#
# `SearchRequest.persona` was accepted by the router and never read, so the
# global PersonaSwitch had no effect on Scenario A results. The lens re-slices
# already-retrieved hits through the persona's own ontology context: products
# carrying an ingredient the persona avoids are dropped, and products matching
# preferred ingredients or favourite GS1 bricks are promoted.
#
# Applied *after* retrieval rather than as an OpenSearch filter, deliberately:
# the prefer/avoid facts live in Neptune, not in the index, and keeping the
# retrieval stage persona-blind preserves the division of labour the whole
# design rests on — RAG retrieves, the ontology explains and constrains.
# @see docs/diagrams/ontology-rag-llm.puml

_PERSONA_CYPHER = (
    "MATCH (p:Persona) WHERE p.persona_id = $pid "
    "RETURN coalesce(p.avoided_ingredient_ids, []) AS avoided, "
    "       coalesce(p.preferred_ingredient_ids, []) AS preferred, "
    "       coalesce(p.favorite_brick_codes, []) AS bricks"
)

_PRODUCT_FACTS_CYPHER = (
    "MATCH (pr:Product) WHERE pr.sku_id IN $skus "
    "OPTIONAL MATCH (pr)-[:HAS_INGREDIENT]->(i:Ingredient) "
    "OPTIONAL MATCH (pr)-[:IN_CATEGORY]->(c:Category) "
    "RETURN pr.sku_id AS sku_id, "
    "       collect(DISTINCT i.ingredient_id) AS ingredients, "
    "       collect(DISTINCT c.gs1_brick_code) AS bricks"
)

PREFERRED_BOOST = 0.15
FAVORITE_BRICK_BOOST = 0.08


def persona_context(persona_id: Optional[str]) -> Optional[Dict[str, set]]:
    """Fetch a persona's avoid / prefer / favourite-category sets from the graph.

    Shared by Scenario A (search) and Scenario F (substitute) so both read the
    *same* ontology facts and cannot drift apart — a product rejected as unsafe
    in search must not reappear as a "substitute".

    Returns None when the persona is unknown, states no preferences, or the
    graph is unreachable. Every caller treats None as "no lens", so a Neptune
    outage degrades to unfiltered results rather than an error.
    """
    if not persona_id:
        return None

    from api.services import neptune  # local import keeps the import graph flat

    try:
        rows = neptune.open_cypher(_PERSONA_CYPHER, parameters={"pid": persona_id})
    except Exception:  # noqa: BLE001
        return None
    if not rows:
        return None

    ctx = {
        "avoided": set(rows[0].get("avoided") or []),
        "preferred": set(rows[0].get("preferred") or []),
        "bricks": set(rows[0].get("bricks") or []),
    }
    if not (ctx["avoided"] or ctx["preferred"] or ctx["bricks"]):
        return None
    return ctx


def apply_persona_lens(
    hits: List[SearchHit], persona_id: Optional[str], *, drop_avoided: bool = True,
) -> List[SearchHit]:
    """Re-slice `hits` through the ontology context of `persona_id`.

    Drops products containing an avoided ingredient, boosts products matching a
    preferred ingredient or favourite category, and annotates metadata with the
    reason (`persona_preferred`, `persona_favorite_category`, `persona_conflict`)
    so the UI can explain the re-ordering rather than silently changing it.

    Hits that are not Products (reviews, unknown ids) pass through untouched.
    Any Neptune failure returns the input unchanged — a persona lens is an
    enhancement and must never fail the search.
    """
    if not persona_id or not hits:
        return hits

    ctx = persona_context(persona_id)
    if ctx is None:
        return hits
    avoided, preferred, fav_bricks = ctx["avoided"], ctx["preferred"], ctx["bricks"]

    from api.services import neptune  # local import keeps the import graph flat

    try:
        skus = [h["sku_id"] for h in hits if h.get("sku_id")]
        if not skus:
            return hits
        facts = {
            r["sku_id"]: r
            for r in neptune.open_cypher(_PRODUCT_FACTS_CYPHER, parameters={"skus": skus})
        }
    except Exception:  # noqa: BLE001
        return hits

    out: List[SearchHit] = []
    for h in hits:
        f = facts.get(h.get("sku_id", ""))
        if f is None:
            out.append(h)
            continue
        ings = set(f.get("ingredients") or [])
        bricks = set(f.get("bricks") or [])
        conflict = sorted(ings & avoided)
        if conflict and drop_avoided:
            continue

        hit = dict(h)
        meta = dict(hit.get("metadata") or {})
        boost = 0.0
        matched = sorted(ings & preferred)
        if matched:
            boost += PREFERRED_BOOST
            meta["persona_preferred"] = matched
        fav = sorted(bricks & fav_bricks)
        if fav:
            boost += FAVORITE_BRICK_BOOST
            meta["persona_favorite_category"] = fav
        if conflict:
            meta["persona_conflict"] = conflict
        meta["persona_id"] = persona_id
        hit["metadata"] = meta
        hit["score"] = float(hit.get("score", 0.0)) + boost
        out.append(hit)  # type: ignore[arg-type]

    out.sort(key=lambda h: h["score"], reverse=True)
    return out
