"""Scenario D — POST /api/persona-match.

Pick a persona; we walk Persona → HAS_CONCERN → Concern (PREFERS/AVOIDS)
→ Ingredient ← HAS_INGREDIENT — Product, score products by:
  + targets one of the persona's concerns  (concern_match)
  + contains a preferred ingredient        (prefer_score)
  - contains an avoided ingredient         (heavy negative — flagged as violation)

Returns the top recommendations + a "safety warnings" list (products that
match concerns but violate avoided-ingredient rules) + a 1-hop subgraph
suitable for Cytoscape with violation edges highlighted client-side.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.services import neptune

router = APIRouter(tags=["persona-match"])


class PersonaMatchRequest(BaseModel):
    persona_id: str = Field(min_length=1, max_length=64)
    top_k: int = Field(default=10, ge=1, le=30)


class RecommendedProduct(BaseModel):
    sku_id: str
    name: str
    score: int
    concern_match: int
    prefer_score: int
    violation_count: int
    violations: List[str] = Field(default_factory=list)
    properties: Dict[str, Any] = Field(default_factory=dict)


class PersonaMatchResponse(BaseModel):
    persona: Dict[str, Any]
    concerns: List[Dict[str, Any]]
    preferred_ingredients: List[str]
    avoided_ingredients: List[str]
    recommendations: List[RecommendedProduct]
    warnings: List[RecommendedProduct]
    subgraph: Dict[str, Any]


def _props(n: Any) -> Dict[str, Any]:
    return dict(n.get("~properties", {})) if isinstance(n, dict) else {}


def _node_id(n: Any) -> str:
    return n.get("~id", "") if isinstance(n, dict) else str(n)


def _node_label(n: Any) -> str:
    if not isinstance(n, dict):
        return ""
    labels = n.get("~labels") or []
    return labels[0] if labels else ""


@router.post("/persona-match", response_model=PersonaMatchResponse)
def persona_match(req: PersonaMatchRequest) -> PersonaMatchResponse:
    # Fetch persona + concerns + preferred/avoided ingredients in one round-trip.
    profile_q = """
    MATCH (per:Persona {persona_id: $pid})
    OPTIONAL MATCH (per)-[:HAS_CONCERN]->(c:Concern)
    OPTIONAL MATCH (c)-[:PREFERS_INGREDIENT]->(pi:Ingredient)
    OPTIONAL MATCH (c)-[:AVOIDS_INGREDIENT]->(ai:Ingredient)
    RETURN per,
           collect(DISTINCT c) AS concerns,
           collect(DISTINCT pi) AS preferred,
           collect(DISTINCT ai) AS avoided
    """
    rows = neptune.open_cypher(profile_q, parameters={"pid": req.persona_id})
    if not rows:
        raise HTTPException(status_code=404, detail=f"persona not found: {req.persona_id}")
    row = rows[0]
    persona_node = row.get("per") or {}
    concerns_raw = row.get("concerns") or []
    preferred_raw = row.get("preferred") or []
    avoided_raw = row.get("avoided") or []
    concern_ids = [_props(c).get("concern_id") for c in concerns_raw if _props(c).get("concern_id")]
    preferred_ids = [_props(i).get("ingredient_id") for i in preferred_raw if _props(i).get("ingredient_id")]
    avoided_ids = [_props(i).get("ingredient_id") for i in avoided_raw if _props(i).get("ingredient_id")]

    # Score products: targets a persona-relevant concern, contains preferred,
    # avoids the avoided. Single openCypher round-trip with two passes through
    # the ingredient list. `coalesce(...,0)` keeps scores numeric on null.
    score_q = """
    MATCH (per:Persona {persona_id: $pid})-[:HAS_CONCERN]->(c:Concern)<-[:TARGETS_CONCERN]-(prod:Product)
    WITH prod, count(DISTINCT c) AS concern_match
    OPTIONAL MATCH (prod)-[:HAS_INGREDIENT]->(ing:Ingredient)
    WITH prod, concern_match, collect(DISTINCT ing.ingredient_id) AS prod_ings
    WITH prod, concern_match, prod_ings,
         size([x IN $preferred WHERE x IN prod_ings]) AS prefer_score,
         [x IN $avoided WHERE x IN prod_ings] AS violations
    RETURN prod, concern_match, prefer_score,
           size(violations) AS violation_count, violations
    ORDER BY (concern_match + prefer_score - 100 * size(violations)) DESC
    LIMIT 50
    """
    score_rows = neptune.open_cypher(
        score_q,
        parameters={
            "pid": req.persona_id,
            "preferred": preferred_ids,
            "avoided": avoided_ids,
        },
    )

    recommendations: List[RecommendedProduct] = []
    warnings: List[RecommendedProduct] = []
    subgraph_nodes: Dict[str, Dict[str, Any]] = {}
    subgraph_edges: List[Dict[str, Any]] = []

    # Persona node always in subgraph
    persona_id = _node_id(persona_node)
    if persona_node:
        subgraph_nodes[persona_id] = {
            "data": {"id": persona_id, "label": "Persona", **_props(persona_node)}
        }
    for c in concerns_raw:
        cid = _node_id(c)
        subgraph_nodes[cid] = {"data": {"id": cid, "label": "Concern", **_props(c)}}
        subgraph_edges.append({"data": {
            "source": persona_id, "target": cid, "label": "HAS_CONCERN",
        }})

    for r in score_rows:
        prod_node = r.get("prod") or {}
        p = _props(prod_node)
        rec = RecommendedProduct(
            sku_id=str(p.get("sku_id", _node_id(prod_node))),
            name=str(p.get("name_ko") or p.get("name_en") or "(unnamed)"),
            score=int((r.get("concern_match") or 0) + (r.get("prefer_score") or 0)
                      - 100 * (r.get("violation_count") or 0)),
            concern_match=int(r.get("concern_match") or 0),
            prefer_score=int(r.get("prefer_score") or 0),
            violation_count=int(r.get("violation_count") or 0),
            violations=list(r.get("violations") or []),
            properties=p,
        )
        if rec.violation_count > 0:
            warnings.append(rec)
        else:
            recommendations.append(rec)
        # Add to subgraph (top-N only — limit graph density)
        if len(recommendations) <= req.top_k or rec.violation_count > 0:
            pid_n = _node_id(prod_node)
            if pid_n and pid_n not in subgraph_nodes:
                subgraph_nodes[pid_n] = {"data": {"id": pid_n, "label": "Product", **p}}

    recommendations.sort(key=lambda x: x.score, reverse=True)
    recommendations = recommendations[: req.top_k]

    return PersonaMatchResponse(
        persona=_props(persona_node),
        concerns=[_props(c) for c in concerns_raw],
        preferred_ingredients=preferred_ids,
        avoided_ingredients=avoided_ids,
        recommendations=recommendations,
        warnings=warnings[: req.top_k],
        subgraph={"nodes": list(subgraph_nodes.values()), "edges": subgraph_edges},
    )


@router.get("/personas")
def list_personas(
    limit: int = 50,
    segment_eligible: bool = False,
) -> Dict[str, Any]:
    """Light listing for the persona picker — no graph computation.

    `segment_eligible=true` 는 *세그먼트 시나리오* (Coverage / Churn /map /
    Tier-up /map 등 spine MATCHES_PERSONA에 의존하는 화면) 에서 사용 —
    spine persona(`is_spine=true`) 또는 narrative→spine bridge(`DERIVED_FROM`
    엣지가 있는 narrative)만 반환해서 *선택해도 0명 나오는* 페르소나를
    드롭다운에서 숨김. 기본값 false 는 기존 narrative-rich 시나리오
    (/match 등)와의 backward compat 유지.

    각 항목에 `is_spine`, `is_bridged`, `bridge_targets` 필드를 노출해
    클라이언트가 시각적으로 구분 가능 (예: spine을 상단 그룹화).
    """
    eligibility_filter = (
        "WHERE p.is_spine = true OR (p)-[:DERIVED_FROM]->(:Persona) "
        if segment_eligible else ""
    )
    rows = neptune.open_cypher(
        f"MATCH (p:Persona) "
        f"{eligibility_filter}"
        f"OPTIONAL MATCH (p)-[:HAS_CONCERN]->(c:Concern) "
        f"OPTIONAL MATCH (p)-[:DERIVED_FROM]->(s:Persona) "
        f"WITH p, count(DISTINCT c) AS concern_count, "
        f"     collect(DISTINCT s.persona_id) AS bridges "
        f"RETURN p, concern_count, bridges "
        f"ORDER BY p.is_spine DESC, concern_count DESC "
        f"LIMIT {max(1, min(int(limit), 100))}"
    )
    items = []
    for r in rows:
        p = _props(r.get("p"))
        if not p:
            continue
        bridges = [b for b in (r.get("bridges") or []) if b]
        items.append({
            "persona_id": p.get("persona_id"),
            "label_ko": p.get("label_ko") or p.get("name_ko") or "(unnamed)",
            "age": p.get("age"),
            "gender": p.get("gender"),
            "life_stage_ko": p.get("life_stage_ko"),
            "narrative_ko": p.get("narrative_ko"),
            "is_wow": bool(p.get("is_wow")),
            "is_spine": bool(p.get("is_spine")),
            "is_bridged": len(bridges) > 0,
            "bridge_targets": bridges,
            "concern_count": int(r.get("concern_count") or 0),
        })
    return {"items": items, "total": len(items)}
