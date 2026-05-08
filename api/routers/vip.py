"""Scenario M — VIP Target Builder (외부 소비 데이터 × 멤버쉽 = wallet-share-aware VIP).

External-panel data (Phase 2B IndustryCategory + HAS_CATEGORY_SPEND) layered
above internal Member transactions surfaces five VIP definitions that
internal data alone cannot see. Implemented endpoints in this iteration:

  • GET /api/vip/opportunity — *the headline card*. Members with a large
    *external* spend in some category but a *small share captured by us*.
    These are the "growth-ready whales" invisible without external data.

The other 4 definitions (loyal / cross-category / trajectory / whale)
will land in future iterations on the same data layer — this router is
the placement that scales.

Design notes:
  - "Opportunity" semantics: total_spend = our_internal_spend + external_amount.
    our_share = our_internal_spend / total_spend. Selecting members where
    total >= floor AND our_share <= ceiling AND total_spend - our_internal > 0
    isolates the "they buy a lot in this category, we have ≤30% of it".
  - Persona filter respects ADR-0006 — accepts spine OR narrative ID.
  - The IndustryCategory↔Category overlap edge is the join: members'
    internal Transactions sum to `our_spend(member, industry)` by walking
    Transaction → Product → Category ← OVERLAPS_WITH ← IndustryCategory.

  Endpoint:  GET /api/vip/opportunity
             ?persona=<spine|narrative ID>
             &share_ceiling=<float, default 0.3>
             &total_floor_krw=<int, default 500000>
             &top_k=<int, default 30>
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from api.services import neptune

router = APIRouter(tags=["vip"])

_PERSONA_LABEL = {
    "per_pregnant":       "임산부",
    "per_kid_4yo_mom":    "4세 아이 엄마",
    "per_camper":         "캠퍼",
    "per_sensitive_skin": "민감성 피부",
    "per_gluten_allergy": "글루텐 알레르기",
}


class OpportunityCandidate(BaseModel):
    member_id: str
    name_ko: str
    tier: str
    persona_id: Optional[str] = None
    industry_id: str
    industry_ko: str
    our_spend_krw: int
    external_spend_krw: int
    total_spend_krw: int
    our_share: float                       # 0..1
    untapped_krw: int                      # total - our_internal — the upside
    churn_risk: float                      # carry through for prioritisation


class OpportunitySummary(BaseModel):
    persona_id: Optional[str] = None
    persona_label_ko: Optional[str] = None
    share_ceiling: float
    total_floor_krw: int
    candidate_count: int                   # member-industry rows matching filter
    distinct_member_count: int             # how many unique members
    sum_untapped_krw: int                  # total addressable upside KRW
    avg_our_share: float
    top_industry_id: Optional[str] = None
    top_industry_ko: Optional[str] = None


class OpportunityResponse(BaseModel):
    summary: OpportunitySummary
    candidates: List[OpportunityCandidate]


@router.get("/vip/opportunity", response_model=OpportunityResponse)
def opportunity_vip(
    persona: Optional[str] = Query(None),
    share_ceiling: float = Query(0.3, ge=0.0, le=1.0),
    total_floor_krw: int = Query(500_000, ge=0),
    top_k: int = Query(30, ge=1, le=200),
) -> OpportunityResponse:
    persona_filter = (
        "AND ((m)-[:MATCHES_PERSONA]->(:Persona {persona_id: $pid}) "
        "  OR (m)-[:MATCHES_PERSONA]->(:Persona)<-[:DERIVED_FROM]-(:Persona {persona_id: $pid})) "
        if persona else ""
    )

    # The query joins three layers in one round trip:
    #   1. Member-EXTERNAL-IndustryCategory  → external_amt
    #   2. Member-MADE-Transaction-OF_PRODUCT-Product-IN_CATEGORY-Category
    #      ← OVERLAPS_WITH ← IndustryCategory  → our_internal
    #   3. Persona filter via OR-pattern (spine | narrative)
    #
    # OPTIONAL MATCH on the internal-spend traversal — if the member has
    # zero matching internal transactions, our_internal = 0 (which is the
    # 100% blind-spot case; e.g. ind_household, ind_outdoor with no GS1
    # overlap). Those rows have our_share = 0.0 — strongest signal.
    rows = neptune.open_cypher(
        "MATCH (m:Member)-[hcs:HAS_CATEGORY_SPEND]->(i:IndustryCategory) "
        "WHERE 1=1 " + persona_filter
        + "OPTIONAL MATCH (m)-[:MADE]->(t:Transaction)-[:OF_PRODUCT]->(p:Product)"
        "                 -[:IN_CATEGORY]->(c:Category)<-[:OVERLAPS_WITH]-(i) "
        "WITH m, i, hcs.amount_krw AS external_amt, "
        "     coalesce(sum(t.amount_krw), 0) AS our_internal "
        "WITH m, i, external_amt, our_internal, "
        "     (external_amt + our_internal) AS total_spend, "
        "     CASE WHEN (external_amt + our_internal) > 0 "
        "          THEN toFloat(our_internal) / (external_amt + our_internal) "
        "          ELSE 0.0 END AS our_share "
        "WHERE total_spend >= $total_floor "
        "  AND our_share <= $share_ceiling "
        "  AND external_amt > 0 "
        "RETURN m.member_id AS mid, m.name_ko AS name_ko, m.tier AS tier, "
        "       m.persona_id AS pid, coalesce(m.churn_risk, 0.0) AS churn_risk, "
        "       i.industry_id AS iid, i.name_ko AS iko, "
        "       our_internal AS our_spend, external_amt AS external_spend, "
        "       total_spend, our_share "
        "ORDER BY total_spend DESC, our_share ASC "
        "LIMIT $k",
        parameters={
            "total_floor": total_floor_krw,
            "share_ceiling": share_ceiling,
            "k": top_k,
            **({"pid": persona} if persona else {}),
        },
    ) or []

    candidates: List[OpportunityCandidate] = []
    for r in rows:
        our_spend = int(r.get("our_spend") or 0)
        ext = int(r.get("external_spend") or 0)
        total = int(r.get("total_spend") or 0)
        share = float(r.get("our_share") or 0.0)
        candidates.append(OpportunityCandidate(
            member_id=str(r.get("mid") or ""),
            name_ko=str(r.get("name_ko") or r.get("mid") or ""),
            tier=str(r.get("tier") or "Bronze"),
            persona_id=r.get("pid"),
            industry_id=str(r.get("iid") or ""),
            industry_ko=str(r.get("iko") or ""),
            our_spend_krw=our_spend,
            external_spend_krw=ext,
            total_spend_krw=total,
            our_share=round(share, 4),
            untapped_krw=total - our_spend,
            churn_risk=round(float(r.get("churn_risk") or 0.0), 3),
        ))

    distinct_members = len({c.member_id for c in candidates})
    sum_untapped = sum(c.untapped_krw for c in candidates)
    avg_share = (
        sum(c.our_share for c in candidates) / len(candidates)
        if candidates else 0.0
    )
    industry_counts: Dict[str, int] = {}
    industry_label: Dict[str, str] = {}
    for c in candidates:
        industry_counts[c.industry_id] = industry_counts.get(c.industry_id, 0) + 1
        industry_label[c.industry_id] = c.industry_ko
    top_industry_id, top_industry_ko = None, None
    if industry_counts:
        top_industry_id = max(industry_counts, key=lambda k: industry_counts[k])
        top_industry_ko = industry_label.get(top_industry_id)

    summary = OpportunitySummary(
        persona_id=persona,
        persona_label_ko=_PERSONA_LABEL.get(persona) if persona else None,
        share_ceiling=share_ceiling,
        total_floor_krw=total_floor_krw,
        candidate_count=len(candidates),
        distinct_member_count=distinct_members,
        sum_untapped_krw=sum_untapped,
        avg_our_share=round(avg_share, 4),
        top_industry_id=top_industry_id,
        top_industry_ko=top_industry_ko,
    )

    return OpportunityResponse(summary=summary, candidates=candidates)
