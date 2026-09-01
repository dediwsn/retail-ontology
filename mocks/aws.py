"""
Install in-process fakes for every AWS boundary the API touches.

Purpose: run the *real* FastAPI app and the *real* Next.js pages with no AWS
account, so the UI can be walked page by page exactly as the current codebase
renders it. Nothing in `api/` changes — the boundary functions are swapped at
import time, so routers, Pydantic models, SSE vocabulary and error handling all
execute for real.

What is faked, and where the seam sits:

    api.services.neptune.open_cypher      → query-shape-aware fake (below)
    api.services.neptune.subgraph_for_skus→ Cytoscape subgraph from the world
    api.services.search.hybrid_search     → ranked hits over mocks.world.PRODUCTS
    api.services.embedding.embed_query    → deterministic pseudo-vector
    api.services.guardrails.apply         → pass-through, never intervenes
    api.services.kb.lookup                → canned retrieval passages
    api.services.memory.*                 → per-process dict
    api.aws_clients.bedrock_runtime       → converse / converse_stream /
                                            invoke_model / apply_guardrail
    api.aws_clients.bedrock_agentcore     → memory record stubs
    api.aws_clients.session               → boto3 stub for logs / ce in /ops

The `open_cypher` fake works in two layers. Hand-written handlers cover the
queries whose *semantics* matter — regions and warehouses must be internally
consistent or the maps draw nonsense. Everything else falls through to a
generic responder that parses the query's RETURN projection and synthesises a
row shaped to satisfy it. Unmatched queries are logged with `MOCK-CYPHER-MISS`
so gaps are visible rather than silent.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from mocks import world as W

logger = logging.getLogger("mocks.aws")

_MEMORY: Dict[str, List[Dict[str, Any]]] = {}
MISSES: List[str] = []


# ─── node / row helpers ────────────────────────────────────────────────────

def _node(label: str, props: Dict[str, Any], idx: int) -> Dict[str, Any]:
    """Neptune openCypher node shape, as api/routers/*.py expect to unpack it."""
    return {"~id": f"{label.lower()}-{idx}", "~labels": [label],
            "~properties": dict(props)}


def _edge(src: str, dst: str, rel: str, idx: int) -> Dict[str, Any]:
    return {"~id": f"e-{idx}", "~type": rel, "~start": src, "~end": dst,
            "~properties": {}}


def _mfrs() -> List[Dict[str, Any]]:
    return [{"mfr_id": f"mfr_{i:03d}", "name_ko": n, "country": "KR"}
            for i, n in enumerate(["아모레퍼시픽", "LG생활건강", "CJ제일제당", "롯데칠성",
                                   "오뚜기", "풀무원", "매일유업", "동원F&B",
                                   "농심", "삼양식품"])]


def _reviews() -> List[Dict[str, Any]]:
    bodies = ["향이 순해서 매일 쓰기 좋아요.", "가격 대비 만족합니다.",
              "아이도 쓸 수 있어서 재구매했어요.", "생각보다 흡수가 느립니다.",
              "캠핑 갈 때 챙기기 좋아요.", "글루텐 프리라 안심됩니다."]
    out = []
    for i in range(60):
        p = W.PRODUCTS[i % len(W.PRODUCTS)]
        out.append({
            "review_id": f"rev_{i:04d}", "sku_id": p["sku_id"],
            "persona_id": W._pick([x["persona_id"] for x in W.PERSONAS], "rp", i),
            "sentiment": W._pick(["positive", "neutral", "negative"], "rs", i),
            "rating": W._rint(1, 5, "rr", i),
            "title_ko": f"{p['name_ko'][:12]} 사용 후기",
            "body_ko": W._pick(bodies, "rb", i),
            "helpful_count": W._rint(0, 220, "rh", i),
            "review_date": str(W.ANCHOR - __import__("datetime").timedelta(
                days=W._rint(1, 300, "rd", i))),
        })
    return out


def _inventory() -> List[Dict[str, Any]]:
    out = []
    for i in range(240):
        w = W.WAREHOUSES[i % len(W.WAREHOUSES)]
        p = W.PRODUCTS[(i * 13) % len(W.PRODUCTS)]
        cap = 60 + W._rint(0, 40, "icap", i) * 10
        return_ = {
            "inv_id": f"inv_{i:04d}", "wh_id": w["wh_id"], "sku_id": p["sku_id"],
            "sku_name": p["name_ko"],
            "on_hand_pallets": W._rint(0, cap, "ioh", i),
            "capacity_pallets": cap,
            "days_of_cover": round(W._rand("idc", i) * 30 + 1, 1),
            "temperature": "cold" if w["cold_chain"] else "ambient",
            "wh_name_ko": w["name_ko"], "wh_name": w["name_ko"],
        }
        out.append(return_)
    return out


def _shipments() -> List[Dict[str, Any]]:
    out = []
    for i in range(80):
        r = W.ROUTES[i % len(W.ROUTES)]
        out.append({
            "shipment_id": f"shp_{i:04d}", "route_id": r["route_id"],
            "from_wh_id": r["from_wh_id"], "to_wh_id": r["to_wh_id"],
            "status": W._pick(["delivered", "in_transit", "delayed", "planned"], "ss", i),
            "dispatched_at": str(W.ANCHOR - __import__("datetime").timedelta(
                days=W._rint(0, 30, "sd", i))),
            "delay_reason": W._pick(["", "", "기상", "도로 통제", "물량 급증"], "sr", i),
        })
    return out


_TRANSACTIONS = [
    {"transaction_id": f"trx_{i:05d}",
     "member_id": W.MEMBERS[i % len(W.MEMBERS)]["member_id"],
     "sku_id": W.PRODUCTS[(i * 7) % len(W.PRODUCTS)]["sku_id"],
     "amount_krw": W._rint(3_000, 180_000, "tam", i),
     "ts": str(W.ANCHOR - __import__("datetime").timedelta(days=W._rint(1, 360, "tts", i))),
     "channel_id": W._pick([c[0] for c in W.CHANNELS], "tch", i)}
    for i in range(400)
]
_TOUCHPOINTS = [
    {"touchpoint_id": f"tp_{i:05d}",
     "member_id": W.MEMBERS[i % len(W.MEMBERS)]["member_id"],
     "campaign_id": W.CAMPAIGNS[i % len(W.CAMPAIGNS)]["campaign_id"],
     "type": W._pick(["email", "push", "sms", "kakao", "visit"], "tpt", i),
     "ts": str(W.ANCHOR - __import__("datetime").timedelta(days=W._rint(1, 200, "tpd", i))),
     "responded": W._rand("tpr", i) > 0.72}
    for i in range(400)
]

# label → entity rows, for the Object Explorer and generic node returns
_BY_LABEL: Dict[str, List[Dict[str, Any]]] = {
    "Product": W.PRODUCTS,
    "Ingredient": [{"ingredient_id": i, "name_ko": ko, "name_en": en, "standard": st}
                   for i, ko, en, st in W.INGREDIENTS],
    "Concern": [{"concern_id": c, "name_ko": ko, "name_en": en, "domain": d}
                for c, ko, en, d in W.CONCERNS],
    "Trend": [{"trend_id": t, "name_ko": ko, "type": ty, "description_ko": de}
              for t, ko, ty, de, _ings, _f in W.TRENDS],
    "Brand": [{"brand_id": b, "name_ko": ko, "domain": "beauty"} for b, ko in W.BRANDS],
    "Category": [{"gs1_brick_code": c, "retail_category_ko": ko, "domain": d,
                  "kfda_category_path": f"식품/{ko}"} for c, ko, d in W.CATEGORIES],
    "Persona": W.PERSONAS,
    "Channel": [{"channel_id": c, "name_ko": ko, "type": t} for c, ko, t in W.CHANNELS],
    "Manufacturer": _mfrs(),
    "Review": _reviews(),
    "Region": W.REGIONS,
    "Warehouse": W.WAREHOUSES,
    "Carrier": [{"carrier_id": c, "name_ko": ko, "mode": m} for c, ko, m in W.CARRIERS],
    "Route": W.ROUTES,
    "Shipment": _shipments(),
    "Event": W.EVENTS,
    "Inventory": _inventory(),
    "Member": W.MEMBERS,
    "MembershipTier": [{"tier_id": t, "name_ko": ko, "name_en": en,
                        "threshold_krw": th, "discount_rate": dr}
                       for t, ko, en, th, dr in W.TIERS],
    "Campaign": W.CAMPAIGNS,
    "Transaction": _TRANSACTIONS,
    "Touchpoint": _TOUCHPOINTS,
    "IndustryCategory": [{"industry_id": i, "name_ko": ko} for i, ko in W.INDUSTRY_CATEGORIES],
}


# ─── generic RETURN-shape responder ────────────────────────────────────────

_SPLIT_RE = re.compile(r",(?![^(\[]*[)\]])")


def _projection(query: str) -> List[tuple]:
    """(expression, alias) pairs from the query's final RETURN clause."""
    m = list(re.finditer(r"\bRETURN\b", query, re.I))
    if not m:
        return []
    tail = query[m[-1].end():]
    tail = re.split(r"\bORDER\s+BY\b|\bLIMIT\b|\bSKIP\b", tail, flags=re.I)[0]
    items = []
    for raw in _SPLIT_RE.split(tail):
        raw = raw.strip()
        if not raw:
            continue
        am = re.search(r"\bAS\s+(\w+)\s*$", raw, re.I)
        if am:
            items.append((raw[:am.start()].strip(), am.group(1)))
        else:
            items.append((raw, raw.split(".")[-1].strip()))
    return items


def _labels(query: str) -> Dict[str, str]:
    return {v: l for v, l in re.findall(r"\((\w+)\s*:\s*(\w+)", query)}


def _limit(query: str, default: int = 12) -> int:
    m = re.search(r"\bLIMIT\s+(\d+)", query, re.I)
    return min(int(m.group(1)), 60) if m else default


_INT_HINTS = ("count", "fanout", "members", "frequency", "size", "total", "n_",
              "pallets", "hops", "rank_score", "violation", "neighbor",
              "recency", "buyers", "responded", "hop", "reached", "sent",
              "orders", "txn", "units", "qty")
_MONEY_HINTS = ("krw", "amount", "ltv", "monetary", "cost", "spend", "price")
_FLOAT_HINTS = ("risk", "rate", "share", "score", "ratio", "pct", "avg", "lift",
                "distance", "hours", "days_of_cover", "growth", "roi", "delta",
                "index", "coverage")

# Aliases the routers unpack with list()/iteration. Returning a scalar here is
# what raises "'int' object is not iterable" three frames into a Pydantic model.
_LIST_ALIASES = {
    "violations", "avoided_ings", "ings", "concerns", "targets", "regions",
    "top_ingredients", "nodes", "edges", "categories", "region_codes",
    "shared_ings", "shared_concerns", "ingredients", "bricks", "preferred",
    "avoided", "skus", "members_list", "reasons", "tags", "claims",
}


_AGG_INT = re.compile(r"\b(count|size|toInteger)\s*\(", re.I)
_AGG_NUM = re.compile(r"\b(avg|sum|round|toFloat|min|max|stDev)\s*\(", re.I)
# Short aliases are almost always aggregate results in this codebase
# (`count(DISTINCT m) AS c`), and returning a string for them is what makes a
# router blow up on int()/float(). Decide from the *expression* first.
_NUMERIC_ALIASES = {"c", "n", "ic", "cnt", "q0", "q1", "freq", "sent", "dkm",
                    "gold", "silver", "pop", "cap", "sum_krw", "tot", "num"}


def _scalar(alias: str, expr: str, i: int) -> Any:
    a = alias.lower()
    e = expr or ""
    if _AGG_INT.search(e):
        return W._rint(1, 90, alias, i)
    if _AGG_NUM.search(e):
        if any(h in a for h in _MONEY_HINTS):
            return W._rint(50_000, 3_000_000, alias, i)
        return round(W._rand(alias, i) * 100, 2)
    if a in ("region_code", "code"):
        return W.REGION_CODES[i % len(W.REGION_CODES)]
    if a in ("lat",):
        return W.REGIONS[i % 17]["lat"]
    if a in ("lng",):
        return W.REGIONS[i % 17]["lng"]
    if a in ("wh_id", "warehouse_id", "from_wh_id", "to_wh_id", "from_id"):
        return W.WAREHOUSES[i % len(W.WAREHOUSES)]["wh_id"]
    if a in ("wh_name", "wh_name_ko", "op_label"):
        return W.WAREHOUSES[i % len(W.WAREHOUSES)]["name_ko"]
    if a in ("sku", "sku_id"):
        return W.PRODUCTS[i % len(W.PRODUCTS)]["sku_id"]
    if a == "sku_name":
        return W.PRODUCTS[i % len(W.PRODUCTS)]["name_ko"]
    if a in ("pid", "persona_id"):
        return W.PERSONAS[i % len(W.PERSONAS)]["persona_id"]
    if a == "tier":
        return W.TIERS[i % 4][2]
    if a in ("carrier_id",):
        return W.CARRIERS[i % len(W.CARRIERS)][0]
    if a in ("route_id", "rid"):
        return W.ROUTES[i % len(W.ROUTES)]["route_id"]
    if a in ("mid", "member_id"):
        return W.MEMBERS[i % len(W.MEMBERS)]["member_id"]
    if a in ("id", "cid", "inv_id", "shipment_id"):
        return f"{a}_{i:04d}"
    if a in ("name", "name_ko", "label", "lbl"):
        return W.PRODUCTS[i % len(W.PRODUCTS)]["name_ko"]
    if a in ("description", "description_ko"):
        return "합성 데모 데이터로 생성된 설명입니다."
    if a in ("status",):
        return W._pick(["active", "in_transit", "delivered", "delayed"], "st", i)
    if a in ("type", "mode", "domain", "level"):
        return W._pick(["road", "sido", "beauty", "grocery", "rdc"], "ty", i)
    if any(h in a for h in _MONEY_HINTS):
        return W._rint(5_000, 4_000_000, alias, i)
    if any(h in a for h in _FLOAT_HINTS):
        return round(W._rand(alias, i), 3)
    if any(h in a for h in _INT_HINTS):
        return W._rint(1, 60, alias, i)
    if a.endswith("_at") or a in ("ts", "date", "start", "end", "dispatched_at"):
        return str(W.ANCHOR - __import__("datetime").timedelta(days=W._rint(1, 120, alias, i)))
    if a.startswith(("n_", "num_", "cnt_")) or a.endswith(("_n", "_count", "_cnt")):
        return W._rint(1, 90, alias, i)
    if a in _NUMERIC_ALIASES or len(a) <= 2:
        return W._rint(1, 90, alias, i)
    return f"{alias}-{i}"


def _list_items(alias: str, i: int) -> List[Any]:
    """List-valued projections. The element *type* matters: Pydantic response
    models declare e.g. `violations: List[str]`, so an int element 500s the
    page three frames later."""
    a = alias.lower()
    n = 0 if a in ("violations", "avoided_ings") and i % 3 else 3
    if a in ("violations", "avoided_ings", "top_ingredients"):
        return [W.INGREDIENTS[(i + k) % len(W.INGREDIENTS)][1] for k in range(n)]
    if a in ("ings", "ingredients", "preferred", "avoided", "shared_ings"):
        return [W.INGREDIENTS[(i + k) % len(W.INGREDIENTS)][0] for k in range(n)]
    if a in ("concerns", "shared_concerns"):
        return [W.CONCERNS[(i + k) % len(W.CONCERNS)][0] for k in range(n)]
    if a == "bricks":
        return [W.CATEGORIES[(i + k) % len(W.CATEGORIES)][0] for k in range(n)]
    if a in ("regions", "region_codes"):
        return [W.REGION_CODES[(i + k) % len(W.REGION_CODES)] for k in range(n)]
    if a == "targets":
        return [W.PERSONAS[(i + k) % len(W.PERSONAS)]["persona_id"] for k in range(n)]
    if a == "skus":
        return [W.PRODUCTS[(i + k) % len(W.PRODUCTS)]["sku_id"] for k in range(n)]
    return [f"{alias}-{i}-{k}" for k in range(n)]


def _generic(query: str, i: int) -> Dict[str, Any]:
    proj = _projection(query)
    labels = _labels(query)
    row: Dict[str, Any] = {}
    for expr, alias in proj:
        e = expr.strip()
        if e in labels:                                  # bare node variable
            label = labels[e]
            pool = _BY_LABEL.get(label)
            props = dict(pool[i % len(pool)]) if pool else {"name_ko": f"{label} {i}"}
            row[alias] = _node(label, props, i)
        elif alias.lower() in _LIST_ALIASES or "collect(" in e.lower():
            row[alias] = _list_items(alias, i)
        else:
            row[alias] = _scalar(alias, e, i)
    return row


# ─── hand-written handlers, where semantics matter ─────────────────────────

def _h_persona_ctx(q: str, p: Dict[str, Any]):
    if "MATCH (p:Persona)" not in q or "avoided" not in q:
        return None
    persona = W.PERSONA_BY_ID.get((p or {}).get("pid", ""))
    if not persona:
        return []
    return [{"avoided": persona.get("avoided_ingredient_ids", []),
             "preferred": persona.get("preferred_ingredient_ids", []),
             "bricks": persona.get("favorite_brick_codes", [])}]


def _h_product_facts(q: str, p: Dict[str, Any]):
    if "pr.sku_id IN $skus" not in q:
        return None
    out = []
    for sku in (p or {}).get("skus", []):
        prod = W.PRODUCT_BY_SKU.get(sku)
        if prod:
            out.append({"sku_id": sku, "ingredients": prod["ingredients"],
                        "bricks": [prod["gs1_brick_code"]]})
    return out


def _h_regions(q: str, p: Dict[str, Any]):
    if not re.search(r"MATCH \(r:Region\)\s*RETURN", q):
        return None
    return [dict(r, level="sido") for r in W.REGIONS]


def _h_warehouses(q: str, p: Dict[str, Any]):
    if "MATCH (w:Warehouse)" not in q or "OPTIONAL MATCH (m:Manufacturer)" not in q:
        return None
    return [dict(w) for w in W.WAREHOUSES]


def _h_carriers(q: str, p: Dict[str, Any]):
    if "MATCH (c:Carrier)" not in q:
        return None
    return [{"carrier_id": c, "name_ko": ko, "mode": m} for c, ko, m in W.CARRIERS]


def _h_routes(q: str, p: Dict[str, Any]):
    if "(r:Route)-[:FROM]->" not in q:
        return None
    return [dict(r) for r in W.ROUTES]


def _h_member_region(q: str, p: Dict[str, Any]):
    if "(m:Member)-[:LIVES_IN]->(r:Region)" not in q:
        return None
    persona = (p or {}).get("pid")
    members = W.members_for_persona(persona) if persona else W.MEMBERS
    proj = {a for _e, a in _projection(q)}
    if "members" in proj:                                # count aggregation
        agg: Dict[str, int] = {}
        for m in members:
            agg[m["region_code"]] = agg.get(m["region_code"], 0) + 1
        return [{"region_code": k, "members": v} for k, v in sorted(agg.items())]
    return [{"region_code": m["region_code"], "tier": m["tier"],
             "churn_risk": m["churn_risk"], "ltv_krw": m["ltv_krw"],
             "member_id": m["member_id"], "name_ko": m["name_ko"],
             "recency_days": m["recency_days"], "frequency": m["frequency"],
             "monetary_krw": m["monetary_krw"], "persona_id": m["persona_id"]}
            for m in members]


def _h_members(q: str, p: Dict[str, Any]):
    if "MATCH (m:Member)" not in q or "LIVES_IN" in q:
        return None
    persona = (p or {}).get("pid")
    members = W.members_for_persona(persona) if persona else W.MEMBERS
    proj = [a for _e, a in _projection(q)]
    rows = []
    for i, m in enumerate(members[: _limit(q, 200)]):
        row: Dict[str, Any] = {}
        for a in proj:
            if a in m:
                row[a] = m[a]
            elif a in ("persona_label_ko", "label_ko"):
                row[a] = W.PERSONA_BY_ID.get(m["persona_id"], {}).get("label_ko")
            elif a == "m":
                row[a] = _node("Member", m, i)
            else:
                row[a] = _scalar(a, a, i)
        rows.append(row)
    return rows


def _h_trends(q: str, p: Dict[str, Any]):
    if "(t:Trend)-[:INVOLVES]->" not in q:
        return None
    return [{"trend": ko, "type": ty, "description": de,
             "top_ingredients": ings[:5], "fanout": fan}
            for _tid, ko, ty, de, ings, fan in W.TRENDS]


def _h_substitute_base(q: str, p: Dict[str, Any]):
    if "MATCH (p:Product {sku_id: $sku})" not in q:
        return None
    prod = W.PRODUCT_BY_SKU.get((p or {}).get("sku", ""))
    if not prod:
        return []
    cat = next((c for c in W.CATEGORIES if c[0] == prod["gs1_brick_code"]), W.CATEGORIES[0])
    return [{
        "p": _node("Product", prod, 0),
        "cat": _node("Category", {"gs1_brick_code": cat[0], "retail_category_ko": cat[1],
                                  "domain": cat[2]}, 0),
        "ings": prod["ingredients"],
        "concerns": prod["target_concern_ids"],
    }]


def _h_substitute_candidates(q: str, p: Dict[str, Any]):
    if "<-[:IN_CATEGORY]-(alt:Product)" not in q:
        return None
    params = p or {}
    brick, sku = params.get("brick"), params.get("sku")
    base_ings = set(params.get("base_ings") or [])
    base_cnc = set(params.get("base_concerns") or [])
    base_brand = params.get("base_brand")
    same_brand_ok = bool(params.get("same_brand_ok"))
    rows = []
    for i, prod in enumerate(W.PRODUCTS):
        if prod["gs1_brick_code"] != brick or prod["sku_id"] == sku:
            continue
        if not same_brand_ok and prod["brand_id"] == base_brand:
            continue
        shared_i = sorted(base_ings & set(prod["ingredients"]))
        shared_c = sorted(base_cnc & set(prod["target_concern_ids"]))
        score = len(shared_i) * 3 + len(shared_c) * 5
        if score <= 0:
            continue
        rows.append({"alt": _node("Product", prod, i), "alt_ings": prod["ingredients"],
                     "shared_ings": shared_i, "shared_concerns": shared_c,
                     "overlap_score": score})
    rows.sort(key=lambda r: r["overlap_score"], reverse=True)
    return rows[:50]


def _h_events(q: str, p: Dict[str, Any]):
    if not re.search(r"\(\w+:Event\)", q):
        return None
    proj = [a for _e, a in _projection(q)]
    rows = []
    for i, e in enumerate(W.EVENTS):
        row: Dict[str, Any] = {}
        for a in proj:
            if a in e:
                row[a] = e[a]
            elif a in ("region_codes", "regions", "targets"):
                row[a] = [e["region_code"]]
            elif a in ("category_codes", "categories"):
                row[a] = [W.CATEGORIES[i % len(W.CATEGORIES)][0]]
            elif a in ("name", "label", "lbl"):
                row[a] = e["name_ko"]
            else:
                row[a] = _scalar(a, a, i)
        rows.append(row)
    return rows


_HANDLERS = [
    _h_persona_ctx, _h_product_facts, _h_regions, _h_warehouses, _h_carriers,
    _h_routes, _h_member_region, _h_trends, _h_substitute_base,
    _h_substitute_candidates, _h_events, _h_members,
]


def fake_open_cypher(query: str, *, parameters: Optional[Dict[str, Any]] = None):
    q = " ".join(query.split())
    for h in _HANDLERS:
        try:
            res = h(q, parameters or {})
        except Exception:  # noqa: BLE001 — a bad handler must not break the page
            res = None
        if res is not None:
            return res
    proj = _projection(q)
    if not proj:
        return []
    sig = q[:110]
    if sig not in MISSES:
        MISSES.append(sig)
        logger.info("MOCK-CYPHER-MISS %s", sig)
    return [_generic(q, i) for i in range(_limit(q))]


def fake_subgraph_for_skus(sku_ids: List[str], *, hops: int = 2) -> Dict[str, Any]:
    nodes, edges = [], []
    for i, sku in enumerate(list(sku_ids)[:5]):
        prod = W.PRODUCT_BY_SKU.get(sku)
        if not prod:
            continue
        pid = f"p-{sku}"
        nodes.append({"data": {"id": pid, "label": "Product", **prod}})
        brand = next((b for b in W.BRANDS if b[0] == prod["brand_id"]), None)
        if brand:
            bid = f"b-{brand[0]}"
            nodes.append({"data": {"id": bid, "label": "Brand", "brand_id": brand[0],
                                   "name_ko": brand[1]}})
            edges.append({"data": {"source": pid, "target": bid, "label": "BY_BRAND"}})
        for ing in prod["ingredients"][:3]:
            meta = next((x for x in W.INGREDIENTS if x[0] == ing), None)
            if not meta:
                continue
            iid = f"i-{ing}"
            nodes.append({"data": {"id": iid, "label": "Ingredient",
                                   "ingredient_id": ing, "name_ko": meta[1]}})
            edges.append({"data": {"source": pid, "target": iid, "label": "HAS_INGREDIENT"}})
        cid = f"c-{prod['gs1_brick_code']}"
        cat = next((c for c in W.CATEGORIES if c[0] == prod["gs1_brick_code"]), None)
        if cat:
            nodes.append({"data": {"id": cid, "label": "Category",
                                   "gs1_brick_code": cat[0], "retail_category_ko": cat[1]}})
            edges.append({"data": {"source": pid, "target": cid, "label": "IN_CATEGORY"}})
    seen, uniq = set(), []
    for n in nodes:
        if n["data"]["id"] not in seen:
            seen.add(n["data"]["id"])
            uniq.append(n)
    return {"nodes": uniq, "edges": edges}


# ─── search / embedding / kb / guardrails / memory ─────────────────────────

def fake_hybrid_search(query: str, *, top_k: int = 10, **_kw) -> List[Dict[str, Any]]:
    """Token-overlap ranking over the mock catalogue — deterministic and, for a
    walkthrough, more legible than random scores: typing 선크림 surfaces 선크림."""
    terms = [t for t in re.split(r"\s+", query.strip()) if t]
    scored = []
    for i, p in enumerate(W.PRODUCTS):
        hay = f"{p['name_ko']} {p['description_ko']}"
        overlap = sum(1 for t in terms if t and t in hay)
        base = overlap * 10 + W._rand("hs", query, i) * 3
        if base <= 0:
            continue
        scored.append((base, i, p))
    if not scored:
        scored = [(W._rand("hs2", query, i) * 3, i, p)
                  for i, p in enumerate(W.PRODUCTS[:40])]
    scored.sort(key=lambda x: x[0], reverse=True)
    out = []
    for rank, (sc, i, p) in enumerate(scored[:top_k]):
        out.append({
            "sku_id": p["sku_id"],
            "score": round(0.99 - rank * 0.03, 4),
            "text": f"{p['name_ko']} — {p['description_ko']}",
            "metadata": {"sku_id": p["sku_id"], "brand_id": p["brand_id"],
                         "price_krw": p["price_krw"], "domain": p["domain"],
                         "gs1_brick_code": p["gs1_brick_code"]},
        })
    return out


def fake_embed_query(text: str) -> List[float]:
    return [round(W._rand("emb", text, i), 6) for i in range(1536)]


def fake_kb_lookup(query: str, *, top_k: int = 5) -> List[Dict[str, Any]]:
    return [{
        "text": f"[{W.PRODUCTS[i]['name_ko']}] 제품 매뉴얼 발췌 — "
                f"보관 방법과 사용 주의사항을 안내합니다. (모의 Knowledge Base 응답)",
        "score": round(0.9 - i * 0.07, 3),
        "location": {"type": "S3", "s3Location": {"uri": f"s3://mock-raw-docs/doc_{i}.pdf"}},
        "metadata": {"sku_id": W.PRODUCTS[i]["sku_id"]},
    } for i in range(min(top_k, 5))]


def fake_guardrail_apply(text: str, source: str = "INPUT"):
    return text, False


def fake_save_event(session_id: str, payload: Dict[str, Any]):
    _MEMORY.setdefault(session_id, []).append(payload)
    return {"eventId": f"evt-{len(_MEMORY[session_id])}"}


def fake_list_events(session_id: str, *, top_k: int = 10):
    return [{"eventId": f"evt-{i}", "payload": [{"conversational": {
        "role": (e.get("role") or "user").upper(),
        "content": {"text": e.get("text", "")}}}]}
        for i, e in enumerate(_MEMORY.get(session_id, [])[-top_k:])]


def fake_retrieve_long_term(actor_id: str, query: str, **_kw):
    return [{"memoryRecordId": "mr-1", "content": {"text": "임산부이며 저자극 제품을 선호합니다."},
             "namespace": f"user/{actor_id}/preferences", "score": 0.91},
            {"memoryRecordId": "mr-2", "content": {"text": "주말에 캠핑을 자주 갑니다."},
             "namespace": f"user/{actor_id}/preferences", "score": 0.77}]


# ─── Bedrock runtime ───────────────────────────────────────────────────────

_ANSWER = (
    "요청하신 내용을 모의 데이터 기준으로 정리했습니다.\n\n"
    "1) **핵심 요약** — 현재 그래프에는 상품 250건, 회원 1,000명, 물류 거점 30곳이 적재돼 있습니다.\n"
    "2) **상위 트렌드**\n"
    "   - 클린 뷰티 — 세라마이드 / 센텔라아시아티카 중심의 저자극 처방\n"
    "   - 장벽 강화 — 판테놀 계열 확산\n"
    "   - 글루텐 프리 — 쌀가루·귀리 기반 대체 곡물 수요\n"
    "3) **시사점** — 민감성 피부 페르소나에서 재구매 신호가 가장 뚜렷합니다.\n\n"
    "> 이 응답은 로컬 목(mock) 모드에서 생성된 고정 텍스트입니다. Bedrock 호출은 발생하지 않았습니다."
)


class _Body:
    def __init__(self, payload: Dict[str, Any]):
        self._raw = json.dumps(payload).encode()

    def read(self):
        return self._raw


class FakeBedrockRuntime:
    """Covers every Bedrock call the API makes: Converse (with tool-use),
    ConverseStream, InvokeModel (embed + rerank) and ApplyGuardrail."""

    def __init__(self):
        self._turn = 0

    def converse(self, **kw):
        self._turn += 1
        messages = kw.get("messages") or []
        has_tool_result = any(
            isinstance(b, dict) and "toolResult" in b
            for m in messages for b in (m.get("content") or [])
        )
        tools_available = bool(kw.get("toolConfig"))
        user_text = ""
        for m in messages:
            for b in (m.get("content") or []):
                if isinstance(b, dict) and "text" in b:
                    user_text = b["text"]
        # First turn with tools: call one, so the tool-call panel has something
        # real to show. Afterwards, answer — mirroring a normal agent loop.
        if tools_available and not has_tool_result:
            return {"output": {"message": {"role": "assistant", "content": [
                {"text": "요청을 확인했습니다. 그래프에서 근거를 찾아보겠습니다."},
                {"toolUse": {"toolUseId": f"tu-{self._turn}", "name": "semantic_search",
                             "input": {"query": user_text[:60] or "선크림", "top_k": 5}}},
            ]}}, "stopReason": "tool_use"}
        return {"output": {"message": {"role": "assistant",
                                       "content": [{"text": _ANSWER}]}},
                "stopReason": "end_turn"}

    def converse_stream(self, **_kw):
        def gen():
            for chunk in re.findall(r".{1,28}", _ANSWER, re.S):
                yield {"contentBlockDelta": {"delta": {"text": chunk}}}
            yield {"messageStop": {"stopReason": "end_turn"}}
        return {"stream": gen()}

    def invoke_model(self, **kw):
        model = str(kw.get("modelId", ""))
        body = json.loads(kw.get("body") or "{}")
        if "rerank" in model:
            docs = body.get("documents") or []
            n = int(body.get("top_n") or len(docs))
            return {"body": _Body({"results": [
                {"index": i, "relevance_score": round(0.98 - i * 0.05, 4)}
                for i in range(min(n, len(docs)))]})}
        texts = body.get("texts") or [""]
        return {"body": _Body({"embeddings": {"float": [
            [round(W._rand("e", t, i), 6) for i in range(1536)] for t in texts]}})}

    def apply_guardrail(self, **kw):
        return {"action": "NONE", "outputs": []}


class FakeAgentCore:
    def create_event(self, **kw):
        return fake_save_event(kw.get("sessionId", "s"), {
            "role": kw.get("actorId", "user"), "text": "(mock)"})

    def list_events(self, **kw):
        return {"events": fake_list_events(kw.get("sessionId", "s"),
                                           top_k=kw.get("maxResults", 10))}

    def retrieve_memory_records(self, **kw):
        return {"memoryRecordSummaries": fake_retrieve_long_term("mock", "")}


class _FakeLogs:
    def filter_log_events(self, **kw):
        return {"events": [{
            "timestamp": 1_800_000_000_000 + i * 60_000,
            "message": json.dumps({"action": "NONE", "source": "INPUT",
                                   "note": "mock guardrail log"}),
        } for i in range(5)]}

    def describe_log_groups(self, **kw):
        return {"logGroups": [{"logGroupName": "/aws/ecs/ontology-retail-mock/api"}]}


class _FakeCostExplorer:
    def get_cost_and_usage(self, **kw):
        return {"ResultsByTime": [{
            "TimePeriod": {"Start": "2026-08-24", "End": "2026-08-25"},
            "Groups": [{"Keys": ["Amazon Bedrock"],
                        "Metrics": {"UnblendedCost": {"Amount": "3.41", "Unit": "USD"}}}],
        }]}


class FakeOpenSearch:
    """`/api/ops/ingest` builds its own OpenSearch client inline rather than
    going through services/search.py, so the class itself is patched in the
    router's namespace — otherwise the page waits on a DNS timeout."""

    def __init__(self, *_a, **_kw):
        pass

    def count(self, **_kw):
        return {"count": len(W.PRODUCTS) + 60}

    def search(self, **_kw):
        return {"hits": {"total": {"value": len(W.PRODUCTS)}, "hits": []}}

    def indices(self):
        return self


class FakeSession:
    def client(self, name, **_kw):
        if name == "logs":
            return _FakeLogs()
        if name == "ce":
            return _FakeCostExplorer()
        return FakeBedrockRuntime()

    def get_credentials(self):
        class _C:
            access_key, secret_key, token = "MOCK", "MOCK", None
        return _C()


# ─── installer ─────────────────────────────────────────────────────────────

def install() -> None:
    """Patch every boundary. Import-order safe: routers hold module references
    (`from api.services import neptune`), so rebinding the attribute on the
    module object reaches callers that imported it earlier."""
    from api import aws_clients
    from api.services import embedding, guardrails, kb, memory, neptune, search

    neptune.open_cypher = fake_open_cypher
    neptune.subgraph_for_skus = fake_subgraph_for_skus
    neptune.sparql = lambda q: {"results": {"bindings": []}}

    search.hybrid_search = fake_hybrid_search
    embedding.embed_query = fake_embed_query
    embedding.embed_documents = lambda texts: [fake_embed_query(t) for t in texts]
    kb.lookup = fake_kb_lookup
    kb.rag_answer = lambda q, **_k: {"answer": _ANSWER, "citations": []}

    guardrails.apply = fake_guardrail_apply
    guardrails.apply_or_none = lambda t, source="INPUT": t

    memory.save_event = fake_save_event
    memory.list_events = fake_list_events
    memory.retrieve_long_term = fake_retrieve_long_term

    _runtime = FakeBedrockRuntime()
    _agentcore = FakeAgentCore()
    _session = FakeSession()
    aws_clients.bedrock_runtime = lambda: _runtime
    aws_clients.bedrock_agent_runtime = lambda: _runtime
    aws_clients.bedrock_agentcore = lambda: _agentcore
    aws_clients.bedrock_agentcore_control = lambda: _agentcore
    aws_clients.session = lambda: _session
    aws_clients.cloudwatch = lambda: _FakeLogs()

    # Routers that imported a factory by name need rebinding too.
    for mod_name in ("api.routers.insights", "api.routers.ops", "api.services.agent",
                     "api.services.search", "api.services.embedding",
                     "api.services.guardrails", "api.services.kb",
                     "api.services.memory"):
        import importlib
        try:
            mod = importlib.import_module(mod_name)
        except Exception:  # noqa: BLE001
            continue
        for attr, val in (("bedrock_runtime", lambda: _runtime),
                          ("bedrock_agent_runtime", lambda: _runtime),
                          ("bedrock_agentcore", lambda: _agentcore),
                          ("boto_session", lambda: _session),
                          ("session", lambda: _session)):
            if hasattr(mod, attr):
                setattr(mod, attr, val)

    # OpenSearch: services/search.py builds a client lazily, ops.py builds one
    # inline. Patch the symbol in both namespaces.
    for mod_name in ("api.services.search", "api.routers.ops"):
        import importlib
        try:
            mod = importlib.import_module(mod_name)
        except Exception:  # noqa: BLE001
            continue
        if hasattr(mod, "OpenSearch"):
            mod.OpenSearch = FakeOpenSearch
        if hasattr(mod, "AWSV4SignerAuth"):
            mod.AWSV4SignerAuth = lambda *a, **k: None
        if hasattr(mod, "_os_client"):
            mod._os_client = lambda: FakeOpenSearch()

    logger.info("mocks.aws installed — no AWS calls will be made")
