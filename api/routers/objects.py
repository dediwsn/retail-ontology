"""Object Explorer (Phase 4) — /api/objects/{type}, /api/objects/{type}/{id}.

Browses the Knowledge Graph by entity type with a Palantir Foundry-style
"Object Type Browser" pattern: per-type list (top N by fan-out), per-instance
detail with full properties + 1-hop neighborhood subgraph for the right-side
Cytoscape canvas.

Type taxonomy aligned with `web/components/Sidebar.tsx` and
`api/routers/insights.py` drilldown — same labels and colors throughout.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.services import neptune

router = APIRouter(tags=["objects"])


# Type registry: client-facing slug → (Neptune label, primary key prop, name prop, ordering Cypher).
# Order strategy varies — Products by review count, Ingredients by product fanout, etc.
# `name_prop` gates which prop populates the list-row title (defaulting to name_ko).
_TYPE_REGISTRY: Dict[str, Dict[str, str]] = {
    "product": {
        "label": "Product", "id_prop": "sku_id", "name_prop": "name_ko",
        "order_by": (
            "OPTIONAL MATCH (n)-[:HAS_INGREDIENT]->(ing) "
            "WITH n, count(DISTINCT ing) AS ingredients "
            "RETURN n, ingredients AS rank_score "
            "ORDER BY ingredients DESC"
        ),
    },
    "ingredient": {
        "label": "Ingredient", "id_prop": "ingredient_id", "name_prop": "name_ko",
        "order_by": (
            "OPTIONAL MATCH (n)<-[:HAS_INGREDIENT]-(p) "
            "WITH n, count(DISTINCT p) AS products "
            "RETURN n, products AS rank_score "
            "ORDER BY products DESC"
        ),
    },
    "concern": {
        "label": "Concern", "id_prop": "concern_id", "name_prop": "name_ko",
        "order_by": (
            "OPTIONAL MATCH (n)-[:ADDRESSED_BY]->(ing) "
            "WITH n, count(DISTINCT ing) AS ingredients "
            "RETURN n, ingredients AS rank_score "
            "ORDER BY ingredients DESC"
        ),
    },
    "trend": {
        "label": "Trend", "id_prop": "trend_id", "name_prop": "name_ko",
        "order_by": (
            "OPTIONAL MATCH (n)-[:INVOLVES]->(x) "
            "WITH n, count(DISTINCT x) AS fanout "
            "RETURN n, fanout AS rank_score "
            "ORDER BY fanout DESC"
        ),
    },
    "brand": {
        "label": "Brand", "id_prop": "brand_id", "name_prop": "name_ko",
        "order_by": (
            "OPTIONAL MATCH (p:Product)-[:BY_BRAND]->(n) "
            "WITH n, count(DISTINCT p) AS products "
            "RETURN n, products AS rank_score "
            "ORDER BY products DESC"
        ),
    },
    "category": {
        # Loader stores brick name as `gs1_brick_name_en` (no ko). Use that as
        # display name with retail_category_ko fallback for K-categories.
        "label": "Category", "id_prop": "gs1_brick_code", "name_prop": "retail_category_ko",
        "order_by": (
            "OPTIONAL MATCH (p:Product)-[:IN_CATEGORY]->(n) "
            "WITH n, count(DISTINCT p) AS products "
            "RETURN n, products AS rank_score "
            "ORDER BY products DESC"
        ),
    },
    "persona": {
        # Persona schema uses `label_ko` (not name_ko) per data/schemas.py
        "label": "Persona", "id_prop": "persona_id", "name_prop": "label_ko",
        "order_by": (
            "OPTIONAL MATCH (n)-[:HAS_CONCERN]->(c) "
            "WITH n, count(DISTINCT c) AS concerns "
            "RETURN n, concerns AS rank_score "
            "ORDER BY concerns DESC"
        ),
    },
    "channel": {
        "label": "Channel", "id_prop": "channel_id", "name_prop": "name_ko",
        "order_by": "RETURN n, 0 AS rank_score ORDER BY n.name_ko",
    },
    "manufacturer": {
        "label": "Manufacturer", "id_prop": "mfr_id", "name_prop": "name_ko",
        "order_by": (
            "OPTIONAL MATCH (b:Brand)-[:MANUFACTURED_BY]->(n) "
            "OPTIONAL MATCH (p:Product)-[:BY_BRAND]->(b) "
            "WITH n, count(DISTINCT p) AS products "
            "RETURN n, products AS rank_score "
            "ORDER BY products DESC"
        ),
    },
    "review": {
        # Reviews have no name_ko; title_ko is the natural list label, with
        # body_ko prefix as fallback for review rows the synth feed left
        # title-less. Top-N by helpful_count surfaces the most-cited reviews.
        "label": "Review", "id_prop": "review_id", "name_prop": "title_ko",
        "order_by": (
            "WITH n, coalesce(n.helpful_count, 0) AS helpful "
            "RETURN n, helpful AS rank_score "
            "ORDER BY helpful DESC"
        ),
    },
    "region": {
        "label": "Region", "id_prop": "region_code", "name_prop": "name_ko",
        "order_by": (
            "WITH n, coalesce(n.population, 0) AS pop "
            "RETURN n, pop AS rank_score ORDER BY pop DESC"
        ),
    },
    "warehouse": {
        "label": "Warehouse", "id_prop": "wh_id", "name_prop": "name_ko",
        "order_by": (
            "WITH n, coalesce(n.capacity_pallets, 0) AS cap "
            "RETURN n, cap AS rank_score ORDER BY cap DESC"
        ),
    },
    "carrier": {
        "label": "Carrier", "id_prop": "carrier_id", "name_prop": "name_ko",
        "order_by": (
            "OPTIONAL MATCH (s:Shipment)-[:CARRIED_BY]->(n) "
            "WITH n, count(s) AS shipments "
            "RETURN n, shipments AS rank_score ORDER BY shipments DESC"
        ),
    },
    "shipment": {
        # Shipments lack a friendly name; use shipment_id with status/date
        # surfacing through detail page properties.
        "label": "Shipment", "id_prop": "shipment_id", "name_prop": "shipment_id",
        "order_by": (
            "RETURN n, 0 AS rank_score ORDER BY n.dispatched_at DESC"
        ),
    },
    "event": {
        "label": "Event", "id_prop": "event_id", "name_prop": "name_ko",
        "order_by": (
            "WITH n, coalesce(n.severity, 0) AS sev "
            "RETURN n, sev AS rank_score ORDER BY sev DESC, n.start DESC"
        ),
    },
    "inventory": {
        # Inventory rows are keyed by `inv_id` but the natural list label
        # is the `wh_id + sku_id` pair. Order by on-hand desc so the
        # explorer surfaces the largest holdings first.
        "label": "Inventory", "id_prop": "inv_id", "name_prop": "inv_id",
        "order_by": (
            "WITH n, coalesce(n.on_hand_pallets, 0) AS oh "
            "RETURN n, oh AS rank_score ORDER BY oh DESC"
        ),
    },
    # Membership / marketing layer
    "member": {
        # Surface highest-churn members first — that's the wow signal.
        "label": "Member", "id_prop": "member_id", "name_prop": "name_ko",
        "order_by": (
            "WITH n, coalesce(n.churn_risk, 0.0) AS risk "
            "RETURN n, toInteger(risk * 100) AS rank_score "
            "ORDER BY risk DESC, n.ltv_krw DESC"
        ),
    },
    "tier": {
        "label": "MembershipTier", "id_prop": "tier_id", "name_prop": "name_ko",
        "order_by": (
            "WITH n, coalesce(n.threshold_krw, 0) AS thr "
            "RETURN n, thr AS rank_score ORDER BY thr ASC"
        ),
    },
    "campaign": {
        "label": "Campaign", "id_prop": "campaign_id", "name_prop": "name_ko",
        "order_by": (
            "OPTIONAL MATCH (n)<-[:FROM_CAMPAIGN]-(tp:Touchpoint) "
            "WITH n, count(tp) AS reach "
            "RETURN n, reach AS rank_score ORDER BY n.start DESC"
        ),
    },
    "transaction": {
        # Transactions have no name; surface most recent / largest first.
        "label": "Transaction", "id_prop": "transaction_id", "name_prop": "transaction_id",
        "order_by": (
            "WITH n, coalesce(n.amount_krw, 0) AS amt "
            "RETURN n, amt AS rank_score ORDER BY n.ts DESC, amt DESC"
        ),
    },
    "touchpoint": {
        # Responded touchpoints first — that's the marketing signal.
        "label": "Touchpoint", "id_prop": "touchpoint_id", "name_prop": "touchpoint_id",
        "order_by": (
            "WITH n, CASE WHEN n.responded THEN 1 ELSE 0 END AS r "
            "RETURN n, r AS rank_score ORDER BY r DESC, n.ts DESC"
        ),
    },
    # Phase 2B external consumption layer — IndustryCategory rolls up GS1
    # bricks across HAS_CATEGORY_SPEND. Order by aggregate quarterly spend
    # (sum across all members + periods) to surface most-consumed verticals.
    "industry_category": {
        "label": "IndustryCategory", "id_prop": "industry_id", "name_prop": "name_ko",
        "order_by": (
            "OPTIONAL MATCH (n)<-[r:HAS_CATEGORY_SPEND]-(:Member) "
            "WITH n, coalesce(sum(r.amount_krw), 0) AS spend "
            "RETURN n, spend AS rank_score ORDER BY spend DESC"
        ),
    },
}


class ObjectListItem(BaseModel):
    id: str
    name: str
    rank_score: int = 0
    properties: Dict[str, Any] = Field(default_factory=dict)


class ObjectListResponse(BaseModel):
    type: str
    label: str
    total: int
    items: List[ObjectListItem]


class ObjectDetailResponse(BaseModel):
    type: str
    label: str
    id: str
    name: str
    properties: Dict[str, Any]
    subgraph: Dict[str, Any]
    neighbor_summary: Dict[str, int]


def _spec_or_404(slug: str) -> Dict[str, str]:
    spec = _TYPE_REGISTRY.get(slug)
    if not spec:
        raise HTTPException(status_code=404, detail=f"unknown object type: {slug}")
    return spec


def _coerce_props(node: Any) -> Dict[str, Any]:
    if not isinstance(node, dict):
        return {}
    return dict(node.get("~properties", {}))


# Try the per-type name_prop first; if missing or empty, walk a sensible
# fallback chain across all entity types' common name fields. This keeps
# the Object Explorer usable even on mid-migration data (some nodes still
# have only `_id` props from earlier loader runs).
_NAME_FALLBACKS = [
    "name_ko", "label_ko", "title_ko", "retail_category_ko", "name_en", "gs1_brick_name_en",
]


def _humanize_slug_id(raw_id: str) -> Optional[str]:
    """Turn a slug-style id into a readable label, e.g.
    `inci:acetyl_hexapeptide_3` → 'Acetyl Hexapeptide 3'. Returns None for
    opaque numeric IDs (foodon:00002501, ntr:sugar) where humanization
    would just rewrap the ID."""
    if not raw_id or ":" not in raw_id:
        return None
    prefix, rest = raw_id.split(":", 1)
    # Numeric / pure-tag IDs aren't human-readable — leave them.
    if not rest or rest.isdigit():
        return None
    # Tokenize on _, -, whitespace.
    parts = rest.replace("-", " ").replace("_", " ").split()
    if not parts:
        return None
    # All-digit rests already filtered; mixed-numeric (e.g. 'hexapeptide 3') OK.
    return " ".join(p.capitalize() for p in parts)


def _resolve_name(props: Dict[str, Any], primary: str) -> str:
    for key in [primary] + [k for k in _NAME_FALLBACKS if k != primary]:
        v = props.get(key)
        if v not in (None, "", []):
            return str(v)
    # Slug-style IDs (inci:retinyl_palmitate, ntr:sugar) carry a readable
    # name encoded in the slug — humanize before exposing the raw ID so the
    # list shows "Retinyl Palmitate" not "inci:retinyl_palmitate".
    for id_key in ("ingredient_id", "concern_id", "trend_id"):
        rid = props.get(id_key)
        if rid:
            human = _humanize_slug_id(str(rid))
            if human:
                return human
    # Reviews carry no name_ko / title_ko in some rows — fall back to a
    # 60-char body excerpt so the list shows actual review content rather
    # than the opaque review_id.
    body = props.get("body_ko")
    if isinstance(body, str) and body.strip():
        excerpt = body.strip().replace("\n", " ")
        return (excerpt[:57] + "…") if len(excerpt) > 60 else excerpt
    # Transactions / Touchpoints have no name_ko by design — synthesize a
    # human label from the most informative properties so the list shows
    # "2026-04-15 · 35,000원 · sku_abc123" instead of just "tx_000123".
    if props.get("transaction_id"):
        ts = str(props.get("ts") or "")
        amt = props.get("amount_krw")
        sku = str(props.get("sku_id") or "")
        amt_str = f"{int(amt):,}원" if isinstance(amt, (int, float)) else ""
        parts = [s for s in (ts[:10], amt_str, sku) if s]
        if parts:
            return " · ".join(parts)
    if props.get("touchpoint_id"):
        ts = str(props.get("ts") or "")
        ch = str(props.get("type") or "")
        responded = props.get("responded")
        resp_str = "응답" if responded is True else ("미응답" if responded is False else "")
        parts = [s for s in (ts[:10], ch, resp_str) if s]
        if parts:
            return " · ".join(parts)
    # Last resort: surface the canonical ID rather than "(unnamed)".
    for id_key in ("ingredient_id", "gs1_brick_code", "persona_id",
                   "channel_id", "brand_id", "concern_id", "trend_id", "sku_id",
                   "mfr_id", "review_id", "region_code", "wh_id", "carrier_id",
                   "route_id", "shipment_id", "event_id", "inv_id"):
        if props.get(id_key):
            return str(props[id_key])
    return "(unnamed)"


# Static enrichment for channel detail. The 4 channel nodes only carry
# {channel_id, name_ko, type} from `data/output/channels.json`, and the
# loader doesn't connect Product→Channel edges — so the Inspector pane
# would show "name_ko: CU 편의점, type: 편의점" and stop. Enriching with
# operational metadata gives a complete demo card without re-loading
# Neptune. Re-loader work to add Product-AVAILABLE_IN-Channel edges is a
# separate change in data/load.py.
_CHANNEL_ENRICHMENT: Dict[str, Dict[str, Any]] = {
    "chn_cu": {
        "description_ko": "전국 17,000+ 가맹점, 24시간 운영. BGF리테일 운영. 편스토랑·연세우유·곰표 등 자체 PB로 차별화.",
        "operating_hours": "24시간",
        "store_count": "17,000+",
        "primary_domains": ["grocery", "snack", "ready_meal"],
        "anchor_categories_ko": ["도시락", "삼각김밥", "주류·음료", "스낵·과자", "디저트·아이스크림"],
        "signature_brands_ko": ["편스토랑(PB)", "곰표", "하이트진로", "롯데"],
        "target_personas_ko": ["워킹맘 새벽수요", "20·30대 1인가구", "야간 헬스챌린저"],
        "channel_format": "편의점 (Convenience Store)",
        "operator": "BGF리테일",
    },
    "chn_emart": {
        "description_ko": "이마트 - 신세계그룹의 대표 대형마트. 주말 가족쇼핑·대용량 패키지·노브랜드(PB) 중심. 트레이더스/이마트24 자매 채널 보유.",
        "operating_hours": "10:00 – 23:00 (지점별 상이)",
        "store_count": "150+ 직영점",
        "primary_domains": ["grocery", "household", "fresh"],
        "anchor_categories_ko": ["신선식품", "정육·수산", "유아식품", "생활용품", "주류"],
        "signature_brands_ko": ["노브랜드(PB)", "피코크(PB)", "신세계푸드"],
        "target_personas_ko": ["주부 4인 가족 장보기", "임산부·이유식", "글루텐프리 가정"],
        "channel_format": "대형마트 (Hypermarket)",
        "operator": "신세계그룹",
    },
    "chn_oliveyoung": {
        "description_ko": "올리브영 - 국내 1위 헬스&뷰티 드럭스토어. K-beauty 인디 브랜드 발굴/유통의 허브. 자체 멤버십 700만+.",
        "operating_hours": "10:00 – 22:30",
        "store_count": "1,300+",
        "primary_domains": ["beauty", "personal_care", "health"],
        "anchor_categories_ko": ["스킨케어", "메이크업", "이너뷰티", "헤어·바디", "건강기능식품"],
        "signature_brands_ko": ["라운드랩", "토리든", "닥터지", "메디힐", "VT"],
        "target_personas_ko": ["민감성 피부 여대생", "시카케어 트러블", "비건 라이프"],
        "channel_format": "헬스&뷰티 드럭스토어 (H&B)",
        "operator": "CJ올리브영",
    },
    "chn_kurly": {
        "description_ko": "마켓컬리 - 새벽배송 1위 프리미엄 식품 e-커머스. 컬리스(PB)·셰프 PB 강세. 30·40대 워킹맘 충성도 최고.",
        "operating_hours": "24시간 (주문) / 새벽 배송",
        "store_count": "온라인",
        "primary_domains": ["grocery", "specialty_food", "fresh"],
        "anchor_categories_ko": ["프리미엄 신선식품", "밀키트", "수입식품·와인", "베이커리", "유기농 베이비"],
        "signature_brands_ko": ["컬리스(PB)", "에어로(셰프 PB)", "오롯이"],
        "target_personas_ko": ["워킹맘 글루텐프리 자녀", "임산부 새벽수요", "30대 미식 트렌드세터"],
        "channel_format": "프리미엄 새벽배송 (E-commerce)",
        "operator": "컬리㈜",
    },
}


def _node_id(node: Any) -> str:
    return node.get("~id", "") if isinstance(node, dict) else str(node)


def _label_of(node: Any) -> str:
    if not isinstance(node, dict):
        return ""
    labels = node.get("~labels") or []
    return labels[0] if labels else ""


@router.get("/objects/{slug}", response_model=ObjectListResponse)
def list_objects(slug: str, limit: int = 30) -> ObjectListResponse:
    spec = _spec_or_404(slug)
    limit = max(1, min(int(limit), 100))
    cypher = (
        f"MATCH (n:{spec['label']}) "
        f"{spec['order_by']} "
        f"LIMIT {limit}"
    )
    rows = neptune.open_cypher(cypher)
    items: List[ObjectListItem] = []
    for r in rows:
        node = r.get("n", {})
        props = _coerce_props(node)
        items.append(ObjectListItem(
            id=str(props.get(spec["id_prop"], _node_id(node))),
            name=_resolve_name(props, spec["name_prop"]),
            rank_score=int(r.get("rank_score") or 0),
            properties=props,
        ))

    total_rows = neptune.open_cypher(f"MATCH (n:{spec['label']}) RETURN count(n) AS c")
    total = int((total_rows[0].get("c") if total_rows else 0) or 0)
    return ObjectListResponse(type=slug, label=spec["label"], total=total, items=items)


@router.get("/objects/{slug}/{obj_id}", response_model=ObjectDetailResponse)
def object_detail(slug: str, obj_id: str) -> ObjectDetailResponse:
    spec = _spec_or_404(slug)
    # Parameterized lookup — `obj_id` flows as a parameter, never as an interpolated
    # f-string fragment, so a malicious slug-id can't reshape the Cypher.
    #
    # Earlier `UNWIND rs AS rr` zeroed the result whenever `rs` was empty
    # (e.g., Channel nodes with no incoming edges yet) → 404 even when the
    # node existed. Rewrite returns the node + neighbor list + relationship
    # list directly; `[n] + neighbors` concat happens in Python so we
    # don't depend on Neptune's list-concat semantics.
    #
    # Channel nodes can have hundreds of AVAILABLE_IN products which would
    # blow up the Cytoscape canvas — cap rows to 60 (neighbor, relation)
    # pairs before collect(). For all other types this LIMIT is well above
    # actual fan-out and acts as a safety net.
    # Per-label sampling — without diversification, a node with 1000 Member
    # edges + 250 Product edges + 4 Tier edges would return only the first
    # 60 (all Members), making the subgraph look one-dimensional. We bucket
    # neighbours by their primary label and take up to 15 from each bucket
    # so every relationship type the node has is visible in the canvas.
    cypher = (
        f"MATCH (n:{spec['label']} {{{spec['id_prop']}: $oid}}) "
        "OPTIONAL MATCH (n)-[r]-(neighbor) "
        "WITH n, labels(neighbor)[0] AS lbl, neighbor, r "
        "WITH n, lbl, collect({neighbor: neighbor, r: r}) AS items "
        "WITH n, lbl, items[..15] AS sampled "
        "UNWIND sampled AS s "
        "WITH n, collect(DISTINCT s.neighbor) AS neighbors, "
        "     collect(DISTINCT s.r) AS edges "
        "RETURN n, neighbors, edges, size(neighbors) AS neighbor_count"
    )
    rows = neptune.open_cypher(cypher, parameters={"oid": obj_id})
    if not rows:
        raise HTTPException(status_code=404, detail=f"object not found: {slug}/{obj_id}")
    row = rows[0]
    node = row.get("n", {})
    props = _coerce_props(node)
    # Channel nodes carry only 3 fields and no relationships — enrich the
    # property panel with curated operating metadata so the Inspector has
    # something to show beyond `name_ko + type`. Existing Neptune props win
    # on key collision (so name_ko stays authoritative).
    if slug == "channel":
        enrichment = _CHANNEL_ENRICHMENT.get(obj_id, {})
        for k, v in enrichment.items():
            props.setdefault(k, v)
    neighbors_raw = [n for n in (row.get("neighbors") or []) if isinstance(n, dict)]
    nodes_raw = [node] + neighbors_raw
    edges_raw = [e for e in (row.get("edges") or []) if isinstance(e, dict)]

    subgraph = {
        "nodes": [
            {"data": {"id": _node_id(n), "label": _label_of(n), **_coerce_props(n)}}
            for n in nodes_raw if isinstance(n, dict)
        ],
        "edges": [
            {"data": {
                "source": _node_id(e.get("~start", "")),
                "target": _node_id(e.get("~end", "")),
                "label": e.get("~type", ""),
                **(e.get("~properties") or {}),
            }}
            for e in edges_raw
            if isinstance(e, dict) and e.get("~start") and e.get("~end")
        ],
    }

    # Per-type neighbor summary — used by the inspector header to show
    # "→ 12 Ingredients · 3 Concerns · 1 Brand" tags.
    neighbor_summary: Dict[str, int] = {}
    for n in nodes_raw:
        if not isinstance(n, dict) or _node_id(n) == _node_id(node):
            continue
        lbl = _label_of(n)
        neighbor_summary[lbl] = neighbor_summary.get(lbl, 0) + 1

    return ObjectDetailResponse(
        type=slug, label=spec["label"],
        id=str(props.get(spec["id_prop"], obj_id)),
        name=_resolve_name(props, spec["name_prop"]),
        properties=props,
        subgraph=subgraph,
        neighbor_summary=neighbor_summary,
    )
