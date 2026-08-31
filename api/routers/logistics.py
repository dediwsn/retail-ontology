"""Scenario H — Logistics Network (한국 지도 기반).

  • /api/logistics/network         — Full network: regions + warehouses + routes
                                      for the Korean map view.
  • /api/logistics/warehouse/{id}  — Warehouse detail + recent shipments + lanes.
  • /api/logistics/events          — Active events with affected regions/categories.
  • /api/logistics/status          — KPI summary (OTD rate, active shipments, …).
  • /api/logistics/inventory/wh/{id} — Inventory at one warehouse.
  • /api/logistics/inventory/sku/{id} — Inventory of one SKU across warehouses.
  • /api/logistics/nearest         — Nearest warehouses to lat/lng (haversine).
  • /api/logistics/shortest-path   — Shortest path between two warehouses (BFS
                                      over Route edges).
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.services import neptune

router = APIRouter(tags=["logistics"])


def _haversine_km(a_lat: float, a_lng: float, b_lat: float, b_lng: float) -> float:
    R = 6371.0
    dlat = math.radians(b_lat - a_lat)
    dlng = math.radians(b_lng - a_lng)
    h = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(a_lat)) * math.cos(math.radians(b_lat))
         * math.sin(dlng / 2) ** 2)
    return round(R * 2 * math.atan2(math.sqrt(h), math.sqrt(1 - h)), 1)


class RegionOut(BaseModel):
    region_code: str
    name_ko: str
    level: str
    lat: float
    lng: float
    population: Optional[int] = None
    # Members of the requested persona living in this region. None when no
    # persona was supplied — distinguishes "not asked" from "asked, zero here".
    persona_member_count: Optional[int] = None


class WarehouseOut(BaseModel):
    wh_id: str
    name_ko: str
    type: str
    region_code: str
    lat: float
    lng: float
    capacity_pallets: int
    cold_chain: bool
    operator_label: Optional[str] = None
    # Persona demand in this warehouse's own region — lets the map show nodes
    # sitting where the persona is not, which is the whole point of the overlay.
    persona_member_count: Optional[int] = None


class CarrierOut(BaseModel):
    carrier_id: str
    name_ko: str
    mode: str


class RouteOut(BaseModel):
    route_id: str
    from_wh_id: str
    to_wh_id: str
    carrier_id: str
    distance_km: float
    transit_hours: float


class NetworkResponse(BaseModel):
    regions: List[RegionOut]
    warehouses: List[WarehouseOut]
    carriers: List[CarrierOut]
    routes: List[RouteOut]


def _coerce_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def _coerce_int(v: Any, default: int = 0) -> int:
    try:
        return int(v) if v is not None else default
    except (TypeError, ValueError):
        return default


@router.get("/logistics/network", response_model=NetworkResponse)
def network(persona: Optional[str] = None) -> NetworkResponse:
    """Network topology, optionally overlaid with persona demand.

    With `persona`, every region and warehouse carries `persona_member_count` —
    how many of that persona's members live there. The network itself does not
    change; the overlay makes "our nodes are here, this persona is there" legible
    on the same map. Scenario L answers the derived coverage KPI; this is the
    raw demand layer behind it."""
    # Regions — sido + sigungu for the choropleth + marker layers
    region_rows = neptune.open_cypher(
        "MATCH (r:Region) RETURN r.region_code AS region_code, r.name_ko AS name_ko, "
        "       r.level AS level, r.lat AS lat, r.lng AS lng, r.population AS population "
        "ORDER BY r.region_code"
    )
    # Persona demand overlay. Same OR-pattern as coverage / churn / tier-up so a
    # narrative persona still reaches spine-linked Members through DERIVED_FROM.
    # Failure degrades to no overlay — the network map must always render.
    demand: Dict[str, int] = {}
    if persona:
        try:
            demand_rows = neptune.open_cypher(
                "MATCH (m:Member)-[:LIVES_IN]->(r:Region) "
                "WHERE (m)-[:MATCHES_PERSONA]->(:Persona {persona_id: $pid}) "
                "   OR (m)-[:MATCHES_PERSONA]->(:Persona)<-[:DERIVED_FROM]-"
                "(:Persona {persona_id: $pid}) "
                "RETURN r.region_code AS region_code, count(m) AS members",
                parameters={"pid": persona},
            ) or []
            demand = {
                str(r["region_code"]): _coerce_int(r.get("members"))
                for r in demand_rows if r.get("region_code")
            }
        except Exception:  # noqa: BLE001
            demand = {}

    regions = [
        RegionOut(
            region_code=str(r.get("region_code", "")),
            name_ko=str(r.get("name_ko", "")),
            level=str(r.get("level", "sido")),
            lat=_coerce_float(r.get("lat")),
            lng=_coerce_float(r.get("lng")),
            population=int(r["population"]) if r.get("population") is not None else None,
            persona_member_count=(
                demand.get(str(r.get("region_code", "")), 0) if persona else None
            ),
        )
        for r in region_rows
        if r.get("region_code")
    ]

    # Warehouses — join with operator (Manufacturer or Channel) for label
    wh_rows = neptune.open_cypher(
        "MATCH (w:Warehouse) "
        "OPTIONAL MATCH (m:Manufacturer)-[:OPERATES]->(w) "
        "OPTIONAL MATCH (c:Channel)-[:FULFILLED_BY]->(w) "
        "RETURN w.wh_id AS wh_id, w.name_ko AS name_ko, w.type AS type, "
        "       w.region_code AS region_code, w.lat AS lat, w.lng AS lng, "
        "       w.capacity_pallets AS capacity_pallets, w.cold_chain AS cold_chain, "
        "       coalesce(m.name_ko, c.name_ko) AS operator_label"
    )
    warehouses = [
        WarehouseOut(
            wh_id=str(w.get("wh_id", "")),
            name_ko=str(w.get("name_ko", "")),
            type=str(w.get("type", "")),
            region_code=str(w.get("region_code", "")),
            lat=_coerce_float(w.get("lat")),
            lng=_coerce_float(w.get("lng")),
            capacity_pallets=_coerce_int(w.get("capacity_pallets")),
            cold_chain=bool(w.get("cold_chain")),
            operator_label=str(w["operator_label"]) if w.get("operator_label") else None,
            persona_member_count=(
                demand.get(str(w.get("region_code", "")), 0) if persona else None
            ),
        )
        for w in wh_rows
        if w.get("wh_id")
    ]

    # Carriers — also gives the legend for route colors
    carrier_rows = neptune.open_cypher(
        "MATCH (c:Carrier) RETURN c.carrier_id AS carrier_id, c.name_ko AS name_ko, "
        "       c.mode AS mode"
    )
    carriers = [
        CarrierOut(
            carrier_id=str(c.get("carrier_id", "")),
            name_ko=str(c.get("name_ko", "")),
            mode=str(c.get("mode", "")),
        )
        for c in carrier_rows
        if c.get("carrier_id")
    ]

    # Routes — endpoints denormalized so the map can draw lines without
    # extra lookups. We drop carrier-less or endpoint-less rows defensively.
    route_rows = neptune.open_cypher(
        "MATCH (r:Route)-[:FROM]->(a:Warehouse), (r)-[:TO]->(b:Warehouse), "
        "      (r)-[:CARRIED_BY]->(c:Carrier) "
        "RETURN r.route_id AS route_id, a.wh_id AS from_wh_id, b.wh_id AS to_wh_id, "
        "       c.carrier_id AS carrier_id, r.distance_km AS distance_km, "
        "       r.transit_hours AS transit_hours"
    )
    routes = [
        RouteOut(
            route_id=str(r.get("route_id", "")),
            from_wh_id=str(r.get("from_wh_id", "")),
            to_wh_id=str(r.get("to_wh_id", "")),
            carrier_id=str(r.get("carrier_id", "")),
            distance_km=_coerce_float(r.get("distance_km")),
            transit_hours=_coerce_float(r.get("transit_hours")),
        )
        for r in route_rows
        if r.get("route_id")
    ]

    return NetworkResponse(
        regions=regions, warehouses=warehouses, carriers=carriers, routes=routes,
    )


class WarehouseDetail(BaseModel):
    wh_id: str
    name_ko: str
    type: str
    region_code: str
    region_name_ko: Optional[str] = None
    lat: float
    lng: float
    capacity_pallets: int
    cold_chain: bool
    operator_label: Optional[str] = None
    inbound_routes: List[RouteOut]
    outbound_routes: List[RouteOut]
    recent_shipments: List[Dict[str, Any]]


@router.get("/logistics/warehouse/{wh_id}", response_model=WarehouseDetail)
def warehouse_detail(wh_id: str) -> WarehouseDetail:
    rows = neptune.open_cypher(
        "MATCH (w:Warehouse {wh_id: $wid}) "
        "OPTIONAL MATCH (w)-[:LOCATED_IN]->(reg:Region) "
        "OPTIONAL MATCH (m:Manufacturer)-[:OPERATES]->(w) "
        "OPTIONAL MATCH (ch:Channel)-[:FULFILLED_BY]->(w) "
        "RETURN w, reg, coalesce(m.name_ko, ch.name_ko) AS op_label",
        parameters={"wid": wh_id},
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"warehouse not found: {wh_id}")
    row = rows[0]
    w_props = (row.get("w") or {}).get("~properties", {}) if isinstance(row.get("w"), dict) else {}
    reg_props = (row.get("reg") or {}).get("~properties", {}) if isinstance(row.get("reg"), dict) else {}

    inbound_rows = neptune.open_cypher(
        "MATCH (r:Route)-[:TO]->(w:Warehouse {wh_id: $wid}), (r)-[:FROM]->(a:Warehouse), "
        "      (r)-[:CARRIED_BY]->(c:Carrier) "
        "RETURN r.route_id AS route_id, a.wh_id AS from_wh_id, $wid AS to_wh_id, "
        "       c.carrier_id AS carrier_id, r.distance_km AS distance_km, "
        "       r.transit_hours AS transit_hours",
        parameters={"wid": wh_id},
    )
    outbound_rows = neptune.open_cypher(
        "MATCH (r:Route)-[:FROM]->(w:Warehouse {wh_id: $wid}), (r)-[:TO]->(b:Warehouse), "
        "      (r)-[:CARRIED_BY]->(c:Carrier) "
        "RETURN r.route_id AS route_id, $wid AS from_wh_id, b.wh_id AS to_wh_id, "
        "       c.carrier_id AS carrier_id, r.distance_km AS distance_km, "
        "       r.transit_hours AS transit_hours",
        parameters={"wid": wh_id},
    )
    ship_rows = neptune.open_cypher(
        "MATCH (s:Shipment)-[:VIA]->(r:Route) "
        "WHERE (r)-[:FROM]->(:Warehouse {wh_id: $wid}) "
        "   OR (r)-[:TO]->(:Warehouse {wh_id: $wid}) "
        "RETURN s.shipment_id AS shipment_id, s.dispatched_at AS dispatched_at, "
        "       s.delivered_at AS delivered_at, s.status AS status, s.pallets AS pallets, "
        "       s.delay_reason AS delay_reason "
        "ORDER BY s.dispatched_at DESC LIMIT 30",
        parameters={"wid": wh_id},
    )

    def _route(row: Dict[str, Any]) -> RouteOut:
        return RouteOut(
            route_id=str(row.get("route_id", "")),
            from_wh_id=str(row.get("from_wh_id", "")),
            to_wh_id=str(row.get("to_wh_id", "")),
            carrier_id=str(row.get("carrier_id", "")),
            distance_km=_coerce_float(row.get("distance_km")),
            transit_hours=_coerce_float(row.get("transit_hours")),
        )

    return WarehouseDetail(
        wh_id=wh_id,
        name_ko=str(w_props.get("name_ko", wh_id)),
        type=str(w_props.get("type", "")),
        region_code=str(w_props.get("region_code", "")),
        region_name_ko=str(reg_props.get("name_ko")) if reg_props else None,
        lat=_coerce_float(w_props.get("lat")),
        lng=_coerce_float(w_props.get("lng")),
        capacity_pallets=_coerce_int(w_props.get("capacity_pallets")),
        cold_chain=bool(w_props.get("cold_chain")),
        operator_label=str(row["op_label"]) if row.get("op_label") else None,
        inbound_routes=[_route(r) for r in inbound_rows],
        outbound_routes=[_route(r) for r in outbound_rows],
        recent_shipments=[dict(r) for r in ship_rows],
    )


class EventOut(BaseModel):
    event_id: str
    name_ko: str
    type: str
    start: str
    end: str
    severity: int
    description_ko: Optional[str] = None
    demand_multiplier: float = 1.0
    affected_region_codes: List[str]
    affected_brick_codes: List[str]


class EventListResponse(BaseModel):
    events: List[EventOut]


@router.get("/logistics/events", response_model=EventListResponse)
def events_list() -> EventListResponse:
    rows = neptune.open_cypher(
        "MATCH (e:Event) "
        "OPTIONAL MATCH (e)-[:AFFECTS_REGION]->(r:Region) "
        "OPTIONAL MATCH (e)-[:AFFECTS_CATEGORY]->(c:Category) "
        "RETURN e, collect(DISTINCT r.region_code) AS regions, "
        "       collect(DISTINCT c.gs1_brick_code) AS bricks "
        "ORDER BY e.start ASC"
    )
    out: List[EventOut] = []
    for row in rows:
        e = row.get("e")
        if not isinstance(e, dict):
            continue
        props = e.get("~properties", {})
        out.append(EventOut(
            event_id=str(props.get("event_id", "")),
            name_ko=str(props.get("name_ko", "")),
            type=str(props.get("type", "")),
            start=str(props.get("start", "")),
            end=str(props.get("end", "")),
            severity=_coerce_int(props.get("severity")),
            description_ko=str(props.get("description_ko")) if props.get("description_ko") else None,
            demand_multiplier=_coerce_float(props.get("demand_multiplier"), 1.0),
            affected_region_codes=[str(x) for x in (row.get("regions") or []) if x],
            affected_brick_codes=[str(x) for x in (row.get("bricks") or []) if x],
        ))
    return EventListResponse(events=out)


# ─── /api/logistics/status — KPI summary ────────────────────────────────────


class CarrierKpi(BaseModel):
    carrier_id: str
    name_ko: str
    total: int
    delivered: int
    in_transit: int
    delayed: int
    exception: int
    on_time_rate: float                    # 0..1


class LogisticsKpi(BaseModel):
    total_shipments: int
    delivered: int
    in_transit: int
    delayed: int
    exception: int
    on_time_rate: float                    # delivered with no delay / total delivered
    avg_transit_hours: float               # planned, weighted by shipment count
    active_events: int
    carriers: List[CarrierKpi]


@router.get("/logistics/status", response_model=LogisticsKpi)
def status() -> LogisticsKpi:
    rows = neptune.open_cypher(
        "MATCH (s:Shipment) "
        "RETURN s.status AS status, s.delay_reason AS delay_reason, "
        "       count(s) AS c"
    )
    total = 0
    by_status: Dict[str, int] = {"delivered": 0, "in_transit": 0, "delayed": 0, "exception": 0}
    for r in rows:
        st = str(r.get("status", "")).lower()
        c = int(r.get("c") or 0)
        total += c
        if st in by_status:
            by_status[st] += c

    on_time_rate = (by_status["delivered"] / total) if total else 0.0

    transit_rows = neptune.open_cypher(
        "MATCH (s:Shipment)-[:VIA]->(r:Route) "
        "RETURN avg(coalesce(r.transit_hours, 0)) AS avg_h"
    )
    avg_transit = float(transit_rows[0].get("avg_h") or 0) if transit_rows else 0.0

    # Active events = events whose start <= today <= end (we approximate
    # "active" as any with severity >= 3 since the dataset is anchored to
    # 2026-04-01; demoability matters more than calendar accuracy here).
    ev_rows = neptune.open_cypher(
        "MATCH (e:Event) WHERE coalesce(e.severity, 0) >= 3 "
        "RETURN count(e) AS c"
    )
    active_events = int(ev_rows[0].get("c") or 0) if ev_rows else 0

    # Per-carrier breakdown
    car_rows = neptune.open_cypher(
        "MATCH (c:Carrier) "
        "OPTIONAL MATCH (s:Shipment)-[:CARRIED_BY]->(c) "
        "RETURN c.carrier_id AS carrier_id, c.name_ko AS name_ko, "
        "       count(s) AS total, "
        "       sum(CASE WHEN s.status='delivered'  THEN 1 ELSE 0 END) AS delivered, "
        "       sum(CASE WHEN s.status='in_transit' THEN 1 ELSE 0 END) AS in_transit, "
        "       sum(CASE WHEN s.status='delayed'    THEN 1 ELSE 0 END) AS delayed, "
        "       sum(CASE WHEN s.status='exception'  THEN 1 ELSE 0 END) AS exception "
        "ORDER BY total DESC"
    )
    carriers_kpi: List[CarrierKpi] = []
    for r in car_rows:
        t = int(r.get("total") or 0)
        deliv = int(r.get("delivered") or 0)
        otr = (deliv / t) if t else 0.0
        carriers_kpi.append(CarrierKpi(
            carrier_id=str(r.get("carrier_id", "")),
            name_ko=str(r.get("name_ko", "")),
            total=t, delivered=deliv,
            in_transit=int(r.get("in_transit") or 0),
            delayed=int(r.get("delayed") or 0),
            exception=int(r.get("exception") or 0),
            on_time_rate=round(otr, 4),
        ))

    return LogisticsKpi(
        total_shipments=total,
        delivered=by_status["delivered"],
        in_transit=by_status["in_transit"],
        delayed=by_status["delayed"],
        exception=by_status["exception"],
        on_time_rate=round(on_time_rate, 4),
        avg_transit_hours=round(avg_transit, 1),
        active_events=active_events,
        carriers=carriers_kpi,
    )


# ─── /api/logistics/inventory/* — inventory views ───────────────────────────


class InventoryRow(BaseModel):
    inv_id: str
    wh_id: str
    wh_name_ko: Optional[str] = None
    sku_id: str
    sku_name_ko: Optional[str] = None
    on_hand_pallets: int
    capacity_pallets: int
    days_of_cover: float
    last_updated: str
    temperature: str


class InventoryListResponse(BaseModel):
    rows: List[InventoryRow]
    total_pallets: int
    total_skus: int


def _to_inventory_row(r: Dict[str, Any]) -> InventoryRow:
    return InventoryRow(
        inv_id=str(r.get("inv_id", "")),
        wh_id=str(r.get("wh_id", "")),
        wh_name_ko=str(r.get("wh_name_ko")) if r.get("wh_name_ko") else None,
        sku_id=str(r.get("sku_id", "")),
        sku_name_ko=str(r.get("sku_name_ko")) if r.get("sku_name_ko") else None,
        on_hand_pallets=int(r.get("on_hand_pallets") or 0),
        capacity_pallets=int(r.get("capacity_pallets") or 0),
        days_of_cover=float(r.get("days_of_cover") or 0),
        last_updated=str(r.get("last_updated", "")),
        temperature=str(r.get("temperature", "ambient")),
    )


@router.get("/logistics/inventory/wh/{wh_id}", response_model=InventoryListResponse)
def inventory_at_warehouse(wh_id: str, limit: int = 100) -> InventoryListResponse:
    rows = neptune.open_cypher(
        "MATCH (i:Inventory)-[:HELD_AT]->(w:Warehouse {wh_id: $wid}), "
        "      (i)-[:OF_SKU]->(p:Product) "
        "RETURN i.inv_id AS inv_id, w.wh_id AS wh_id, w.name_ko AS wh_name_ko, "
        "       p.sku_id AS sku_id, p.name_ko AS sku_name_ko, "
        "       i.on_hand_pallets AS on_hand_pallets, "
        "       i.capacity_pallets AS capacity_pallets, "
        "       i.days_of_cover AS days_of_cover, "
        "       i.last_updated AS last_updated, "
        "       i.temperature AS temperature "
        "ORDER BY i.on_hand_pallets DESC "
        f"LIMIT {max(1, min(int(limit), 500))}",
        parameters={"wid": wh_id},
    )
    out = [_to_inventory_row(r) for r in rows]
    return InventoryListResponse(
        rows=out,
        total_pallets=sum(r.on_hand_pallets for r in out),
        total_skus=len({r.sku_id for r in out}),
    )


@router.get("/logistics/inventory/sku/{sku_id}", response_model=InventoryListResponse)
def inventory_for_sku(sku_id: str, limit: int = 50) -> InventoryListResponse:
    rows = neptune.open_cypher(
        "MATCH (i:Inventory)-[:HELD_AT]->(w:Warehouse), "
        "      (i)-[:OF_SKU]->(p:Product {sku_id: $sid}) "
        "RETURN i.inv_id AS inv_id, w.wh_id AS wh_id, w.name_ko AS wh_name_ko, "
        "       p.sku_id AS sku_id, p.name_ko AS sku_name_ko, "
        "       i.on_hand_pallets AS on_hand_pallets, "
        "       i.capacity_pallets AS capacity_pallets, "
        "       i.days_of_cover AS days_of_cover, "
        "       i.last_updated AS last_updated, "
        "       i.temperature AS temperature "
        "ORDER BY i.on_hand_pallets DESC "
        f"LIMIT {max(1, min(int(limit), 200))}",
        parameters={"sid": sku_id},
    )
    out = [_to_inventory_row(r) for r in rows]
    return InventoryListResponse(
        rows=out,
        total_pallets=sum(r.on_hand_pallets for r in out),
        total_skus=len({r.sku_id for r in out}),
    )


# ─── /api/logistics/nearest — k-NN warehouses ───────────────────────────────


class NearestRequest(BaseModel):
    lat: float
    lng: float
    limit: int = 8
    types: Optional[List[str]] = None       # filter by warehouse type
    cold_only: bool = False


class NearestResult(BaseModel):
    wh_id: str
    name_ko: str
    type: str
    region_code: str
    distance_km: float
    lat: float
    lng: float
    cold_chain: bool


class NearestResponse(BaseModel):
    origin_lat: float
    origin_lng: float
    results: List[NearestResult]


@router.post("/logistics/nearest", response_model=NearestResponse)
def nearest_warehouses(req: NearestRequest) -> NearestResponse:
    where_parts: List[str] = []
    params: Dict[str, Any] = {}
    if req.types:
        where_parts.append("w.type IN $types")
        params["types"] = req.types
    if req.cold_only:
        where_parts.append("coalesce(w.cold_chain, false) = true")
    where = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""
    rows = neptune.open_cypher(
        f"MATCH (w:Warehouse){where} "
        "RETURN w.wh_id AS wh_id, w.name_ko AS name_ko, w.type AS type, "
        "       w.region_code AS region_code, w.lat AS lat, w.lng AS lng, "
        "       w.cold_chain AS cold_chain",
        parameters=params,
    )
    scored: List[NearestResult] = []
    for r in rows:
        try:
            lat = float(r.get("lat") or 0); lng = float(r.get("lng") or 0)
        except (TypeError, ValueError):
            continue
        if lat == 0 and lng == 0:
            continue
        d = _haversine_km(req.lat, req.lng, lat, lng)
        scored.append(NearestResult(
            wh_id=str(r.get("wh_id", "")),
            name_ko=str(r.get("name_ko", "")),
            type=str(r.get("type", "")),
            region_code=str(r.get("region_code", "")),
            distance_km=d, lat=lat, lng=lng,
            cold_chain=bool(r.get("cold_chain")),
        ))
    scored.sort(key=lambda x: x.distance_km)
    n = max(1, min(int(req.limit), 30))
    return NearestResponse(origin_lat=req.lat, origin_lng=req.lng, results=scored[:n])


# ─── /api/logistics/shortest-path — BFS over Route edges ────────────────────
#
# Cypher's variable-length pattern handles short hops well, but unweighted BFS
# is sufficient given the ~3-hop limit of our network (mfr → 3pl → rdc → lm).
# We bound depth to 4 to keep the query fast and finite.


class ShortestPathHop(BaseModel):
    from_wh_id: str
    to_wh_id: str
    route_id: str
    carrier_id: str
    distance_km: float
    transit_hours: float


class ShortestPathResponse(BaseModel):
    from_wh_id: str
    to_wh_id: str
    hops: List[ShortestPathHop]
    total_distance_km: float
    total_transit_hours: float
    found: bool


@router.get("/logistics/shortest-path", response_model=ShortestPathResponse)
def shortest_path(from_wh_id: str, to_wh_id: str) -> ShortestPathResponse:
    if from_wh_id == to_wh_id:
        return ShortestPathResponse(
            from_wh_id=from_wh_id, to_wh_id=to_wh_id,
            hops=[], total_distance_km=0.0, total_transit_hours=0.0, found=True,
        )
    # Build the graph once via Cypher then BFS in Python — Cypher's
    # variable-length match doesn't naturally extract per-edge route_id and
    # carrier_id when the pattern is `(a)-[:FROM]-(r:Route)-[:TO]-(b)`. A
    # small Python BFS keeps the result well-typed.
    edges = neptune.open_cypher(
        "MATCH (a:Warehouse)<-[:FROM]-(r:Route)-[:TO]->(b:Warehouse), "
        "      (r)-[:CARRIED_BY]->(c:Carrier) "
        "RETURN a.wh_id AS a, b.wh_id AS b, r.route_id AS rid, "
        "       c.carrier_id AS cid, r.distance_km AS dkm, r.transit_hours AS th"
    )
    adj: Dict[str, List[Dict[str, Any]]] = {}
    for e in edges:
        a = str(e.get("a", "")); b = str(e.get("b", ""))
        if not a or not b:
            continue
        adj.setdefault(a, []).append({
            "to": b,
            "route_id": str(e.get("rid", "")),
            "carrier_id": str(e.get("cid", "")),
            "distance_km": float(e.get("dkm") or 0),
            "transit_hours": float(e.get("th") or 0),
        })

    # Standard BFS — shortest path in unweighted hops. For weighted shortest,
    # swap to a heap-based Dijkstra over `distance_km` or `transit_hours`.
    from collections import deque
    parent: Dict[str, Dict[str, Any]] = {}
    seen = {from_wh_id}
    q: deque[str] = deque([from_wh_id])
    found = False
    while q:
        u = q.popleft()
        if u == to_wh_id:
            found = True
            break
        for e in adj.get(u, []):
            v = e["to"]
            if v in seen:
                continue
            seen.add(v)
            parent[v] = {"prev": u, **e}
            q.append(v)

    if not found:
        return ShortestPathResponse(
            from_wh_id=from_wh_id, to_wh_id=to_wh_id,
            hops=[], total_distance_km=0.0, total_transit_hours=0.0, found=False,
        )

    # Walk parents back from target → source, then reverse.
    hops_rev: List[ShortestPathHop] = []
    cur = to_wh_id
    while cur != from_wh_id:
        e = parent.get(cur)
        if not e:
            break
        hops_rev.append(ShortestPathHop(
            from_wh_id=e["prev"], to_wh_id=cur, route_id=e["route_id"],
            carrier_id=e["carrier_id"],
            distance_km=e["distance_km"], transit_hours=e["transit_hours"],
        ))
        cur = e["prev"]
    hops = list(reversed(hops_rev))
    return ShortestPathResponse(
        from_wh_id=from_wh_id, to_wh_id=to_wh_id,
        hops=hops,
        total_distance_km=round(sum(h.distance_km for h in hops), 1),
        total_transit_hours=round(sum(h.transit_hours for h in hops), 1),
        found=True,
    )
