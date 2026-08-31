"""Scenario F — POST /api/substitute.

Given a product (sku_id), return same-category alternatives ranked by:
  • shared ingredients      (compositional similarity)
  • shared targeted concerns (use-case similarity)
  • price proximity          (avoids "premium-as-substitute-for-budget")
  • persona fit              (optional — drops alternatives the active persona
                              must avoid, promotes ones it prefers)

The wow-moment is showing WHY each alternative is a substitute — visible
"shared ingredients" + "shared concerns" + price delta tags. Subgraph
emphasizes the original product, its alternatives, and the connecting
ingredient/concern nodes (Cytoscape-ready).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.services import neptune

router = APIRouter(tags=["substitute"])


# A preferred-ingredient match is worth slightly more than a shared ingredient
# (3) and less than a shared concern (5): it says the alternative suits *this
# shopper*, which is weaker evidence of substitutability than shared use-case
# but stronger than incidental composition overlap.
PERSONA_PREFERRED_BONUS = 4


class SubstituteRequest(BaseModel):
    sku_id: str = Field(min_length=1, max_length=64)
    top_k: int = Field(default=8, ge=1, le=20)
    same_brand_ok: bool = False  # if False, prefer cross-brand alternatives
    persona: Optional[str] = None
    # A substitute that the active persona must avoid is not a substitute.
    # Set false to surface conflicts (flagged, not hidden) instead of dropping.
    drop_persona_conflicts: bool = True


class SubstituteCandidate(BaseModel):
    sku_id: str
    name: str
    brand_id: Optional[str] = None
    domain: Optional[str] = None
    price_krw: Optional[int] = None
    price_delta_pct: Optional[float] = None
    score: int
    shared_ingredients: List[str] = Field(default_factory=list)
    shared_concerns: List[str] = Field(default_factory=list)
    persona_preferred: List[str] = Field(default_factory=list)
    persona_conflict: List[str] = Field(default_factory=list)
    properties: Dict[str, Any] = Field(default_factory=dict)


class SubstituteResponse(BaseModel):
    original: Dict[str, Any]
    category: Dict[str, Any]
    candidates: List[SubstituteCandidate]
    subgraph: Dict[str, Any]


def _props(n: Any) -> Dict[str, Any]:
    return dict(n.get("~properties", {})) if isinstance(n, dict) else {}


def _node_id(n: Any) -> str:
    return n.get("~id", "") if isinstance(n, dict) else str(n)


def _label(n: Any) -> str:
    return (n.get("~labels") or [""])[0] if isinstance(n, dict) else ""


@router.post("/substitute", response_model=SubstituteResponse)
def substitute(req: SubstituteRequest) -> SubstituteResponse:
    # 1) Resolve the original product + its category + its ingredients/concerns.
    #    Pulled in one round-trip so the candidate query can re-use the lists.
    base_q = """
    MATCH (p:Product {sku_id: $sku})
    OPTIONAL MATCH (p)-[:IN_CATEGORY]->(cat:Category)
    OPTIONAL MATCH (p)-[:HAS_INGREDIENT]->(ing:Ingredient)
    OPTIONAL MATCH (p)-[:TARGETS_CONCERN]->(concern:Concern)
    RETURN p, cat,
           collect(DISTINCT ing.ingredient_id) AS ings,
           collect(DISTINCT concern.concern_id) AS concerns
    """
    rows = neptune.open_cypher(base_q, parameters={"sku": req.sku_id})
    if not rows:
        raise HTTPException(status_code=404, detail=f"product not found: {req.sku_id}")
    row = rows[0]
    original = row.get("p") or {}
    category = row.get("cat") or {}
    base_ings = [i for i in (row.get("ings") or []) if i]
    base_concerns = [c for c in (row.get("concerns") or []) if c]
    cat_props = _props(category)
    cat_brick = cat_props.get("gs1_brick_code")
    p_props = _props(original)
    base_brand = p_props.get("brand_id")
    base_price = p_props.get("price_krw")

    if not cat_brick:
        return SubstituteResponse(
            original=p_props, category={},
            candidates=[],
            subgraph={"nodes": [], "edges": []},
        )

    # 2) Find same-category alternatives, score by shared ingredient/concern overlap.
    #    Filter out same brand by default (cross-brand substitution is the more
    #    interesting demo signal — buying the SAME brand isn't a "substitute").
    cand_q = """
    MATCH (cat:Category {gs1_brick_code: $brick})<-[:IN_CATEGORY]-(alt:Product)
    WHERE alt.sku_id <> $sku
      AND ($same_brand_ok OR coalesce(alt.brand_id, '') <> coalesce($base_brand, ''))
    OPTIONAL MATCH (alt)-[:HAS_INGREDIENT]->(aing:Ingredient)
    WITH alt, collect(DISTINCT aing.ingredient_id) AS alt_ings
    OPTIONAL MATCH (alt)-[:TARGETS_CONCERN]->(aconcern:Concern)
    WITH alt, alt_ings, collect(DISTINCT aconcern.concern_id) AS alt_concerns
    WITH alt, alt_ings,
         [x IN $base_ings WHERE x IN alt_ings] AS shared_ings,
         [x IN $base_concerns WHERE x IN alt_concerns] AS shared_concerns
    WITH alt, alt_ings, shared_ings, shared_concerns,
         (size(shared_ings) * 3 + size(shared_concerns) * 5) AS overlap_score
    WHERE overlap_score > 0
    RETURN alt, alt_ings, shared_ings, shared_concerns, overlap_score
    ORDER BY overlap_score DESC LIMIT 50
    """
    crows = neptune.open_cypher(
        cand_q,
        parameters={
            "brick": cat_brick,
            "sku": req.sku_id,
            "base_brand": base_brand,
            "base_ings": base_ings,
            "base_concerns": base_concerns,
            "same_brand_ok": bool(req.same_brand_ok),
        },
    )

    # 2b) Persona pass — runs across the whole candidate set *before* the top_k
    #     cut, so dropping a conflicting alternative promotes a real one rather
    #     than leaving a hole. Same ontology facts Scenario A's lens reads.
    from api.services.search import persona_context

    ctx = persona_context(req.persona)
    scored: List[tuple] = []
    for r in crows:
        alt_ings = set(r.get("alt_ings") or [])
        conflict = sorted(alt_ings & ctx["avoided"]) if ctx else []
        if conflict and req.drop_persona_conflicts:
            continue
        preferred = sorted(alt_ings & ctx["preferred"]) if ctx else []
        scored.append((r, conflict, preferred))

    candidates: List[SubstituteCandidate] = []
    subgraph_nodes: Dict[str, Dict[str, Any]] = {}
    subgraph_edges: List[Dict[str, Any]] = []

    # Always seed with the original
    pid_n = _node_id(original)
    if pid_n:
        subgraph_nodes[pid_n] = {"data": {"id": pid_n, "label": "Product", **p_props}}
    if category and _node_id(category):
        cid_n = _node_id(category)
        subgraph_nodes[cid_n] = {"data": {"id": cid_n, "label": "Category", **cat_props}}
        if pid_n:
            subgraph_edges.append({"data": {"source": pid_n, "target": cid_n, "label": "IN_CATEGORY"}})

    for r, persona_conflict, persona_preferred in scored[: req.top_k]:
        alt_node = r.get("alt") or {}
        ap = _props(alt_node)
        shared_ings = list(r.get("shared_ings") or [])
        shared_concerns = list(r.get("shared_concerns") or [])
        alt_price = ap.get("price_krw")
        delta_pct: Optional[float] = None
        if isinstance(alt_price, (int, float)) and isinstance(base_price, (int, float)) and base_price:
            delta_pct = round((float(alt_price) - float(base_price)) / float(base_price) * 100.0, 1)

        # Final score combines graph overlap with price proximity bonus.
        overlap = int(r.get("overlap_score") or 0)
        price_bonus = 0
        if delta_pct is not None:
            if abs(delta_pct) <= 10:
                price_bonus = 4
            elif abs(delta_pct) <= 25:
                price_bonus = 2

        candidates.append(SubstituteCandidate(
            sku_id=str(ap.get("sku_id", _node_id(alt_node))),
            name=str(ap.get("name_ko") or ap.get("name_en") or "(unnamed)"),
            brand_id=ap.get("brand_id"),
            domain=ap.get("domain"),
            price_krw=int(alt_price) if isinstance(alt_price, (int, float)) else None,
            price_delta_pct=delta_pct,
            score=overlap + price_bonus + PERSONA_PREFERRED_BONUS * len(persona_preferred),
            shared_ingredients=shared_ings,
            shared_concerns=shared_concerns,
            persona_preferred=persona_preferred,
            persona_conflict=persona_conflict,
            properties=ap,
        ))

        # Add to subgraph
        an_id = _node_id(alt_node)
        if an_id and an_id not in subgraph_nodes:
            subgraph_nodes[an_id] = {"data": {"id": an_id, "label": "Product", **ap}}
            subgraph_edges.append({"data": {
                "source": an_id, "target": cid_n if category else "", "label": "IN_CATEGORY",
            }})

    candidates.sort(key=lambda x: x.score, reverse=True)

    return SubstituteResponse(
        original=p_props,
        category=cat_props,
        candidates=candidates,
        subgraph={"nodes": list(subgraph_nodes.values()), "edges": [e for e in subgraph_edges if e["data"]["target"]]},
    )


@router.get("/substitute/sample-products")
def sample_products(limit: int = 12) -> Dict[str, Any]:
    """Curated picker for the demo — products with rich ingredient/concern fanout
    (so the substitution recommendations have something to score against)."""
    cy = """
    MATCH (p:Product)
    OPTIONAL MATCH (p)-[:HAS_INGREDIENT]->(i:Ingredient)
    WITH p, count(DISTINCT i) AS ic
    OPTIONAL MATCH (p)-[:TARGETS_CONCERN]->(c:Concern)
    WITH p, ic, count(DISTINCT c) AS cc
    WHERE ic + cc > 1
    RETURN p, ic, cc
    ORDER BY (ic + cc * 2) DESC
    LIMIT $lim
    """
    rows = neptune.open_cypher(cy, parameters={"lim": int(limit)})
    items = []
    for r in rows:
        p = _props(r.get("p"))
        if not p:
            continue
        items.append({
            "sku_id": p.get("sku_id"),
            "name": p.get("name_ko") or "(unnamed)",
            "brand_id": p.get("brand_id"),
            "domain": p.get("domain"),
            "price_krw": p.get("price_krw"),
            "ingredient_count": int(r.get("ic") or 0),
            "concern_count": int(r.get("cc") or 0),
        })
    return {"items": items}
