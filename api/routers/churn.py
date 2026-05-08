"""Scenario I — Churn Risk Diagnosis (이탈 위험 진단).

Surfaces high-LTV members at risk of churn ("최근 90일 미구매 + 캠페인 미응답
VIP 회원") and recommends winback campaigns. Powered by the membership
layer added in Phase 2A (Member, MembershipTier, Campaign, Touchpoint).

Endpoints:
  GET /api/churn/dashboard            — aggregate dashboard for the page
  GET /api/churn/member/{member_id}   — drill-down per member

Risk model is *graph-side* — `m.churn_risk` is hydrated by the synthetic
generator (data/synthetic/membership.py:_churn_risk) using RFM, so the
endpoint stays cheap and the same field is used for ordering / breakdowns.

Subgraph shape matches the Cytoscape contract used by all other scenarios
(`{nodes, edges}` with `data.id` / `data.source` / `data.target` / `data.label`).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.services import neptune

router = APIRouter(tags=["churn"])

# Risk threshold treated as "high" — surfaces in the persona/tier breakdown
# `at_risk` count and the recommended-action logic. Aligned with the
# generator distribution: ~24% of 1000 synthetic members sit ≥ 0.7.
HIGH_RISK = 0.7


# ─── Response models ──────────────────────────────────────────────────────


class AtRiskMember(BaseModel):
    member_id: str
    name_ko: str
    tier: str
    persona_id: Optional[str] = None
    persona_label_ko: Optional[str] = None
    churn_risk: float
    recency_days: int
    frequency: int
    ltv_krw: int
    last_purchase_at: Optional[str] = None


class PersonaRiskBucket(BaseModel):
    persona_id: str
    persona_label_ko: str
    total: int
    at_risk: int
    avg_churn_risk: float


class TierRiskBucket(BaseModel):
    tier: str
    total: int
    at_risk: int
    avg_churn_risk: float
    avg_ltv_krw: int


class RecommendedCampaign(BaseModel):
    campaign_id: str
    name_ko: str
    type: str
    channel: str
    target_persona_ids: List[str] = Field(default_factory=list)
    expected_response_rate: float = 0.0


class ChurnSummary(BaseModel):
    total_members: int
    high_risk_count: int
    high_risk_pct: float
    vip_at_risk_count: int
    avg_recency_days: float


class ChurnDashboardResponse(BaseModel):
    summary: ChurnSummary
    top_at_risk: List[AtRiskMember]
    persona_breakdown: List[PersonaRiskBucket]
    tier_breakdown: List[TierRiskBucket]
    recommended_winback: List[RecommendedCampaign]
    subgraph: Dict[str, Any]


class MemberDetail(BaseModel):
    member: AtRiskMember
    transactions: List[Dict[str, Any]]
    touchpoints: List[Dict[str, Any]]
    response_rate: float
    recommended_campaign: Optional[RecommendedCampaign] = None
    subgraph: Dict[str, Any]


# ─── Helpers ──────────────────────────────────────────────────────────────


def _props(n: Any) -> Dict[str, Any]:
    return dict(n.get("~properties", {})) if isinstance(n, dict) else {}


def _node_id(n: Any) -> str:
    return n.get("~id", "") if isinstance(n, dict) else str(n)


def _node_label(n: Any) -> str:
    if not isinstance(n, dict):
        return ""
    labels = n.get("~labels") or []
    return labels[0] if labels else ""


def _at_risk_from_member(props: Dict[str, Any], persona_label_ko: Optional[str] = None) -> AtRiskMember:
    return AtRiskMember(
        member_id=str(props.get("member_id") or ""),
        name_ko=str(props.get("name_ko") or props.get("member_id") or ""),
        tier=str(props.get("tier") or "Bronze"),
        persona_id=props.get("persona_id"),
        persona_label_ko=persona_label_ko,
        churn_risk=float(props.get("churn_risk") or 0.0),
        recency_days=int(props.get("recency_days") or 0),
        frequency=int(props.get("frequency") or 0),
        ltv_krw=int(props.get("ltv_krw") or 0),
        last_purchase_at=str(props.get("last_purchase_at") or "") or None,
    )


# ─── Dashboard ────────────────────────────────────────────────────────────


@router.get("/churn/dashboard", response_model=ChurnDashboardResponse)
def churn_dashboard(top_k: int = 30) -> ChurnDashboardResponse:
    top_k = max(1, min(top_k, 100))

    # 1. Top at-risk members + their persona label.
    rows = neptune.open_cypher(
        "MATCH (m:Member) "
        "OPTIONAL MATCH (m)-[:MATCHES_PERSONA]->(p:Persona) "
        "RETURN m, p "
        "ORDER BY m.churn_risk DESC, m.ltv_krw DESC LIMIT $k",
        parameters={"k": int(top_k)},
    )
    top_at_risk: List[AtRiskMember] = []
    for r in rows:
        m_props = _props(r.get("m"))
        p_props = _props(r.get("p")) if r.get("p") else {}
        top_at_risk.append(_at_risk_from_member(m_props, p_props.get("label_ko")))

    # 2. Persona breakdown.
    rows = neptune.open_cypher(
        "MATCH (m:Member)-[:MATCHES_PERSONA]->(p:Persona) "
        "WITH p, count(m) AS total, "
        "     sum(CASE WHEN m.churn_risk >= $hr THEN 1 ELSE 0 END) AS at_risk, "
        "     avg(coalesce(m.churn_risk, 0.0)) AS avg_risk "
        "RETURN p.persona_id AS pid, p.label_ko AS label, total, at_risk, avg_risk "
        "ORDER BY at_risk DESC",
        parameters={"hr": HIGH_RISK},
    )
    persona_breakdown = [
        PersonaRiskBucket(
            persona_id=str(r.get("pid") or ""),
            persona_label_ko=str(r.get("label") or ""),
            total=int(r.get("total") or 0),
            at_risk=int(r.get("at_risk") or 0),
            avg_churn_risk=round(float(r.get("avg_risk") or 0.0), 3),
        )
        for r in rows
    ]

    # 3. Tier breakdown.
    rows = neptune.open_cypher(
        "MATCH (m:Member) "
        "WITH m.tier AS tier, count(m) AS total, "
        "     sum(CASE WHEN m.churn_risk >= $hr THEN 1 ELSE 0 END) AS at_risk, "
        "     avg(coalesce(m.churn_risk, 0.0)) AS avg_risk, "
        "     avg(coalesce(m.ltv_krw, 0)) AS avg_ltv "
        "RETURN tier, total, at_risk, avg_risk, avg_ltv "
        "ORDER BY CASE tier WHEN 'VIP' THEN 0 WHEN 'Gold' THEN 1 "
        "                  WHEN 'Silver' THEN 2 ELSE 3 END",
        parameters={"hr": HIGH_RISK},
    )
    tier_breakdown = [
        TierRiskBucket(
            tier=str(r.get("tier") or "Bronze"),
            total=int(r.get("total") or 0),
            at_risk=int(r.get("at_risk") or 0),
            avg_churn_risk=round(float(r.get("avg_risk") or 0.0), 3),
            avg_ltv_krw=int(r.get("avg_ltv") or 0),
        )
        for r in rows
    ]

    # 4. Summary derived from breakdowns (cheaper than another round-trip).
    total_members = sum(t.total for t in tier_breakdown)
    high_risk_count = sum(t.at_risk for t in tier_breakdown)
    vip_at_risk_count = next(
        (t.at_risk for t in tier_breakdown if t.tier == "VIP"), 0
    )
    rows = neptune.open_cypher(
        "MATCH (m:Member) RETURN avg(coalesce(m.recency_days, 0)) AS r"
    )
    avg_recency = round(float((rows[0] if rows else {}).get("r") or 0.0), 1)
    summary = ChurnSummary(
        total_members=total_members,
        high_risk_count=high_risk_count,
        high_risk_pct=(round(high_risk_count / total_members, 4) if total_members else 0.0),
        vip_at_risk_count=vip_at_risk_count,
        avg_recency_days=avg_recency,
    )

    # 5. Recommended winback campaigns + their target personas.
    rows = neptune.open_cypher(
        "MATCH (c:Campaign) WHERE c.type = 'winback' "
        "OPTIONAL MATCH (c)-[:TARGETS]->(p:Persona) "
        "RETURN c, collect(DISTINCT p.persona_id) AS targets "
        "ORDER BY c.start DESC"
    )
    recommended_winback: List[RecommendedCampaign] = []
    for r in rows:
        c_props = _props(r.get("c"))
        targets = [t for t in (r.get("targets") or []) if t]
        # Expected response rate: rough heuristic — VIP/Gold tier-mix
        # plus a winback dampening factor (matches the synthetic generator).
        recommended_winback.append(
            RecommendedCampaign(
                campaign_id=str(c_props.get("campaign_id") or ""),
                name_ko=str(c_props.get("name_ko") or ""),
                type=str(c_props.get("type") or "winback"),
                channel=str(c_props.get("channel") or ""),
                target_persona_ids=targets,
                expected_response_rate=0.18 if targets else 0.12,
            )
        )

    # 6. Subgraph — top 10 at-risk + their tier + persona nodes (small).
    rows = neptune.open_cypher(
        "MATCH (m:Member) "
        "WITH m ORDER BY m.churn_risk DESC, m.ltv_krw DESC LIMIT 10 "
        "OPTIONAL MATCH (m)-[r1:BELONGS_TO]->(t:MembershipTier) "
        "OPTIONAL MATCH (m)-[r2:MATCHES_PERSONA]->(p:Persona) "
        "RETURN collect(DISTINCT m) + collect(DISTINCT t) + collect(DISTINCT p) AS nodes, "
        "       collect(DISTINCT r1) + collect(DISTINCT r2) AS edges"
    )
    nodes_raw: List[Any] = []
    edges_raw: List[Any] = []
    if rows:
        nodes_raw = [n for n in (rows[0].get("nodes") or []) if n]
        edges_raw = [e for e in (rows[0].get("edges") or []) if e]
    subgraph = {
        "nodes": [
            {"data": {"id": _node_id(n), "label": _node_label(n), **_props(n)}}
            for n in nodes_raw
        ],
        "edges": [
            {"data": {
                "source": _node_id(e.get("~start")) if isinstance(e, dict) else "",
                "target": _node_id(e.get("~end")) if isinstance(e, dict) else "",
                "label": e.get("~type", "") if isinstance(e, dict) else "",
            }}
            for e in edges_raw
        ],
    }

    return ChurnDashboardResponse(
        summary=summary,
        top_at_risk=top_at_risk,
        persona_breakdown=persona_breakdown,
        tier_breakdown=tier_breakdown,
        recommended_winback=recommended_winback,
        subgraph=subgraph,
    )


# ─── Member drill-down ────────────────────────────────────────────────────


@router.get("/churn/member/{member_id}", response_model=MemberDetail)
def churn_member(member_id: str) -> MemberDetail:
    rows = neptune.open_cypher(
        "MATCH (m:Member {member_id: $mid}) "
        "OPTIONAL MATCH (m)-[:MATCHES_PERSONA]->(p:Persona) "
        "RETURN m, p",
        parameters={"mid": member_id},
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"member not found: {member_id}")
    m_props = _props(rows[0].get("m"))
    p_props = _props(rows[0].get("p")) if rows[0].get("p") else {}
    member = _at_risk_from_member(m_props, p_props.get("label_ko"))

    # Recent transactions (last 10)
    rows = neptune.open_cypher(
        "MATCH (m:Member {member_id: $mid})-[:MADE]->(tx:Transaction) "
        "OPTIONAL MATCH (tx)-[:OF_PRODUCT]->(p:Product) "
        "RETURN tx, p ORDER BY tx.ts DESC LIMIT 10",
        parameters={"mid": member_id},
    )
    transactions: List[Dict[str, Any]] = []
    for r in rows:
        tx = _props(r.get("tx"))
        p = _props(r.get("p")) if r.get("p") else {}
        transactions.append({
            "transaction_id": tx.get("transaction_id"),
            "ts": tx.get("ts"),
            "amount_krw": tx.get("amount_krw"),
            "sku_id": p.get("sku_id"),
            "product_name_ko": p.get("name_ko"),
        })

    # Recent touchpoints (last 12)
    rows = neptune.open_cypher(
        "MATCH (m:Member {member_id: $mid})-[:HAS_TOUCHPOINT]->(tp:Touchpoint) "
        "OPTIONAL MATCH (tp)-[:FROM_CAMPAIGN]->(c:Campaign) "
        "RETURN tp, c ORDER BY tp.ts DESC LIMIT 12",
        parameters={"mid": member_id},
    )
    touchpoints: List[Dict[str, Any]] = []
    sent = 0
    responded = 0
    for r in rows:
        tp = _props(r.get("tp"))
        c = _props(r.get("c")) if r.get("c") else {}
        sent += 1
        if tp.get("responded"):
            responded += 1
        touchpoints.append({
            "touchpoint_id": tp.get("touchpoint_id"),
            "type": tp.get("type"),
            "ts": tp.get("ts"),
            "responded": bool(tp.get("responded")),
            "campaign_id": c.get("campaign_id"),
            "campaign_name_ko": c.get("name_ko"),
        })
    response_rate = round(responded / sent, 3) if sent else 0.0

    # Recommend the most recent winback campaign — prefer one targeting
    # this member's persona, else any winback.
    rows = neptune.open_cypher(
        "MATCH (c:Campaign) WHERE c.type = 'winback' "
        "OPTIONAL MATCH (c)-[:TARGETS]->(p:Persona) "
        "RETURN c, collect(DISTINCT p.persona_id) AS targets "
        "ORDER BY c.start DESC"
    )
    chosen: Optional[RecommendedCampaign] = None
    fallback: Optional[RecommendedCampaign] = None
    for r in rows:
        c_props = _props(r.get("c"))
        targets = [t for t in (r.get("targets") or []) if t]
        rec = RecommendedCampaign(
            campaign_id=str(c_props.get("campaign_id") or ""),
            name_ko=str(c_props.get("name_ko") or ""),
            type=str(c_props.get("type") or "winback"),
            channel=str(c_props.get("channel") or ""),
            target_persona_ids=targets,
            expected_response_rate=0.22 if member.tier in ("VIP", "Gold") else 0.10,
        )
        if member.persona_id and member.persona_id in targets:
            chosen = rec
            break
        if fallback is None:
            fallback = rec
    recommended = chosen or fallback

    # Subgraph — member + tier + persona + last 5 transaction edges + last 5
    # touchpoint edges, kept small enough for the density toggle to show
    # cleanly without LIMIT-stripping in the UI.
    rows = neptune.open_cypher(
        "MATCH (m:Member {member_id: $mid}) "
        "OPTIONAL MATCH (m)-[r1:BELONGS_TO]->(t:MembershipTier) "
        "OPTIONAL MATCH (m)-[r2:MATCHES_PERSONA]->(per:Persona) "
        "OPTIONAL MATCH (m)-[r3:MADE]->(tx:Transaction) "
        "WITH m, r1, t, r2, per, tx, r3 "
        "ORDER BY tx.ts DESC "
        "WITH m, r1, t, r2, per, collect(DISTINCT tx)[..5] AS txs, "
        "     collect(DISTINCT r3)[..5] AS r3s "
        "OPTIONAL MATCH (m)-[r4:HAS_TOUCHPOINT]->(tp:Touchpoint) "
        "WITH m, r1, t, r2, per, txs, r3s, tp, r4 "
        "ORDER BY tp.ts DESC "
        "RETURN m, r1, t, r2, per, txs, r3s, "
        "       collect(DISTINCT tp)[..5] AS tps, "
        "       collect(DISTINCT r4)[..5] AS r4s",
        parameters={"mid": member_id},
    )
    nodes_raw: List[Any] = []
    edges_raw: List[Any] = []
    if rows:
        row = rows[0]
        for key in ("m", "t", "per"):
            if row.get(key):
                nodes_raw.append(row[key])
        nodes_raw.extend([n for n in (row.get("txs") or []) if n])
        nodes_raw.extend([n for n in (row.get("tps") or []) if n])
        for key in ("r1", "r2"):
            if row.get(key):
                edges_raw.append(row[key])
        edges_raw.extend([e for e in (row.get("r3s") or []) if e])
        edges_raw.extend([e for e in (row.get("r4s") or []) if e])
    subgraph = {
        "nodes": [
            {"data": {"id": _node_id(n), "label": _node_label(n), **_props(n)}}
            for n in nodes_raw
        ],
        "edges": [
            {"data": {
                "source": _node_id(e.get("~start")) if isinstance(e, dict) else "",
                "target": _node_id(e.get("~end")) if isinstance(e, dict) else "",
                "label": e.get("~type", "") if isinstance(e, dict) else "",
            }}
            for e in edges_raw
        ],
    }

    return MemberDetail(
        member=member,
        transactions=transactions,
        touchpoints=touchpoints,
        response_rate=response_rate,
        recommended_campaign=recommended,
        subgraph=subgraph,
    )


# ─── Map view (시도별 이탈 위험 분포) ─────────────────────────────────────


class ChurnRegionRow(BaseModel):
    region_code: str
    name_ko: str
    members: int
    at_risk: int
    avg_churn_risk: float
    avg_ltv_krw: int


class ChurnMapResponse(BaseModel):
    persona_id: Optional[str] = None
    persona_label_ko: Optional[str] = None
    high_risk_threshold: float
    regions: List[ChurnRegionRow]


@router.get("/churn/map", response_model=ChurnMapResponse)
def churn_map(persona: Optional[str] = None) -> ChurnMapResponse:
    """시도(region)별 이탈 위험 집계.

    Member.region_id 가 부여된 회원만 대상. persona가 주어지면 그 페르소나
    슬라이스로 좁힘. 코로플레스 색은 클라이언트가 avg_churn_risk 또는
    at_risk 비율로 결정.
    """
    # LIVES_IN 트래버설을 권위로 사용. persona 필터는 pattern expression form —
    # Neptune의 EXISTS{MATCH} subquery form은 엔진 버전 호환성 좁음.
    persona_filter = (
        "AND (m)-[:MATCHES_PERSONA]->(:Persona {persona_id: $pid}) "
        if persona else ""
    )
    rows = neptune.open_cypher(
        "MATCH (m:Member)-[:LIVES_IN]->(r:Region) "
        "WHERE 1=1 " + persona_filter
        + "WITH r.region_code AS region_code, "
        "     coalesce(r.name_ko, '') AS name_ko, "
        "     count(m) AS members, "
        "     sum(CASE WHEN m.churn_risk >= $hr THEN 1 ELSE 0 END) AS at_risk, "
        "     avg(coalesce(m.churn_risk, 0.0)) AS avg_risk, "
        "     avg(coalesce(m.ltv_krw, 0)) AS avg_ltv "
        "RETURN region_code, name_ko, members, at_risk, avg_risk, avg_ltv "
        "ORDER BY region_code",
        parameters={"hr": HIGH_RISK, **({"pid": persona} if persona else {})},
    )

    # 페르소나 라벨 룩업 (UI 헤더용)
    persona_label = None
    if persona:
        plr = neptune.open_cypher(
            "MATCH (p:Persona {persona_id: $pid}) RETURN p.label_ko AS label",
            parameters={"pid": persona},
        )
        if plr:
            persona_label = str(plr[0].get("label") or "") or None

    out = [
        ChurnRegionRow(
            region_code=str(r.get("region_code") or ""),
            name_ko=str(r.get("name_ko") or ""),
            members=int(r.get("members") or 0),
            at_risk=int(r.get("at_risk") or 0),
            avg_churn_risk=round(float(r.get("avg_risk") or 0.0), 3),
            avg_ltv_krw=int(r.get("avg_ltv") or 0),
        )
        for r in rows
        if r.get("region_code")
    ]
    return ChurnMapResponse(
        persona_id=persona,
        persona_label_ko=persona_label,
        high_risk_threshold=HIGH_RISK,
        regions=out,
    )
