"""Scenario L — Coverage Map (회원-거점 커버리지).

페르소나 컨텍스트로 필터링된 회원의 시도(sido)별 분포를 한국 지도 위에
코로플레스로 그리고, 같은 지도 위에 Warehouse 마커를 겹쳐 "내 페르소나
회원 중 N km 안에 거점이 없는 비율"이라는 단일 KPI를 노출한다.

설계 결정:
  • Phase 2A-G에서 추가된 (Member)-[:LIVES_IN]->(Region) 엣지를 출발점으로 사용.
    region_id가 없는 회원은 집계에서 제외 (도입 직후에는 0명).
  • Coverage = 회원의 거주 시도 중심점에서 가장 가까운 Warehouse까지
    haversine 거리. radius_km(기본 80) 이하면 "도달", 초과면 "미도달".
  • Region centroid는 그래프 측 r.lat/r.lng 가 있으면 사용, 없으면 in-code
    fallback dict (logistics-load 갭에 견고하게).
  • dimension 토글로 같은 화면이 4개 보기를 가짐:
      - count : 회원 수 (인구 기준)
      - churn : 평균 churn risk (이탈 hot zone)
      - ltv   : 평균 LTV (가치 hot zone)
      - uncov : 미도달 비율 (거점 갭)
  • 페르소나 미선택 시 전체 1,000명 대상.

Endpoint:
  GET /api/coverage/dashboard?persona=<id>&dimension=<count|churn|ltv|uncov>
                              &radius_km=<int>
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from api.services import neptune

router = APIRouter(tags=["coverage"])

# 시도(sido) centroids — KOSTAT region_code → (lat, lng).
# Region 노드의 lat/lng가 비어있을 때 fallback. 17개 모두 정의.
_SIDO_CENTROID: Dict[str, Dict[str, Any]] = {
    "11": {"name_ko": "서울특별시",       "lat": 37.5665, "lng": 126.9780},
    "21": {"name_ko": "부산광역시",       "lat": 35.1796, "lng": 129.0756},
    "22": {"name_ko": "대구광역시",       "lat": 35.8714, "lng": 128.6014},
    "23": {"name_ko": "인천광역시",       "lat": 37.4563, "lng": 126.7052},
    "24": {"name_ko": "광주광역시",       "lat": 35.1595, "lng": 126.8526},
    "25": {"name_ko": "대전광역시",       "lat": 36.3504, "lng": 127.3845},
    "26": {"name_ko": "울산광역시",       "lat": 35.5384, "lng": 129.3114},
    "29": {"name_ko": "세종특별자치시",   "lat": 36.4800, "lng": 127.2890},
    "31": {"name_ko": "경기도",           "lat": 37.4138, "lng": 127.5183},
    "32": {"name_ko": "강원특별자치도",   "lat": 37.8228, "lng": 128.1555},
    "33": {"name_ko": "충청북도",         "lat": 36.6357, "lng": 127.4914},
    "34": {"name_ko": "충청남도",         "lat": 36.5184, "lng": 126.8000},
    "35": {"name_ko": "전북특별자치도",   "lat": 35.7167, "lng": 127.1442},
    "36": {"name_ko": "전라남도",         "lat": 34.8161, "lng": 126.4630},
    "37": {"name_ko": "경상북도",         "lat": 36.4919, "lng": 128.8889},
    "38": {"name_ko": "경상남도",         "lat": 35.4606, "lng": 128.2132},
    "39": {"name_ko": "제주특별자치도",   "lat": 33.4996, "lng": 126.5312},
}

_PERSONA_LABEL: Dict[str, str] = {
    "per_pregnant":       "임산부",
    "per_kid_4yo_mom":    "4세 아이 엄마",
    "per_camper":         "캠퍼",
    "per_sensitive_skin": "민감성 피부",
    "per_gluten_allergy": "글루텐 알레르기",
}


def _haversine_km(a_lat: float, a_lng: float, b_lat: float, b_lng: float) -> float:
    R = 6371.0
    dlat = math.radians(b_lat - a_lat)
    dlng = math.radians(b_lng - a_lng)
    h = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(a_lat)) * math.cos(math.radians(b_lat))
         * math.sin(dlng / 2) ** 2)
    return round(R * 2 * math.atan2(math.sqrt(h), math.sqrt(1 - h)), 1)


def _coerce_float(v: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


# ─── Response models ──────────────────────────────────────────────────────


class WarehouseMarker(BaseModel):
    warehouse_id: str
    name_ko: str
    type: str
    region_code: str
    lat: float
    lng: float


class RegionCoverage(BaseModel):
    region_code: str
    name_ko: str
    lat: float
    lng: float
    members: int
    avg_churn_risk: float
    avg_ltv_krw: int
    tier_mix: Dict[str, int]
    nearest_warehouse_id: Optional[str] = None
    nearest_warehouse_km: Optional[float] = None
    covered: bool


class CoverageSummary(BaseModel):
    persona_id: Optional[str] = None
    persona_label_ko: Optional[str] = None
    radius_km: int
    total_members: int
    covered_members: int
    uncovered_members: int
    coverage_pct: float
    top_uncovered_region_code: Optional[str] = None
    top_uncovered_region_ko: Optional[str] = None
    top_uncovered_member_count: int = 0


class CoverageDashboardResponse(BaseModel):
    summary: CoverageSummary
    regions: List[RegionCoverage]
    warehouses: List[WarehouseMarker]


# ─── Endpoint ─────────────────────────────────────────────────────────────


@router.get("/coverage/dashboard", response_model=CoverageDashboardResponse)
def coverage_dashboard(
    persona: Optional[str] = Query(None, description="per_pregnant | per_camper | …"),
    dimension: str = Query("count", pattern="^(count|churn|ltv|uncov)$"),  # noqa: F841
    radius_km: int = Query(80, ge=10, le=300),
) -> CoverageDashboardResponse:
    # `dimension`은 프론트엔드 색 스케일 결정용 — 백엔드 응답은 4개 차원의
    # 원본 수치를 모두 포함하므로 클라이언트가 토글 시 재호출 불필요.

    # 1. 회원 집계 — LIVES_IN 트래버설로 region 결정. region_id property 대신
    # 관계를 권위로 사용. persona 필터는 spine(per_*)와 narrative(psn_*)를 모두
    # 받는 OR 패턴 — narrative는 (Persona)-[:DERIVED_FROM]->(spine) 1-hop으로
    # spine-linked Member에 도달.
    member_q = (
        "MATCH (m:Member)-[:LIVES_IN]->(r:Region) "
        + ("WHERE (m)-[:MATCHES_PERSONA]->(:Persona {persona_id: $pid}) "
           "   OR (m)-[:MATCHES_PERSONA]->(:Persona)<-[:DERIVED_FROM]-(:Persona {persona_id: $pid}) "
           if persona else "")
        + "RETURN r.region_code AS region_code, m.tier AS tier, "
        "       m.churn_risk AS churn_risk, m.ltv_krw AS ltv_krw"
    )
    params: Dict[str, Any] = {}
    if persona:
        params["pid"] = persona
    member_rows = neptune.open_cypher(member_q, parameters=params) or []

    # 2. Warehouse — 모든 거점의 좌표 + region_code
    wh_rows = neptune.open_cypher(
        "MATCH (w:Warehouse) "
        "RETURN w.wh_id AS warehouse_id, w.name_ko AS name_ko, w.type AS type, "
        "       w.region_code AS region_code, w.lat AS lat, w.lng AS lng"
    ) or []
    warehouses: List[WarehouseMarker] = [
        WarehouseMarker(
            warehouse_id=str(w.get("warehouse_id") or ""),
            name_ko=str(w.get("name_ko") or ""),
            type=str(w.get("type") or ""),
            region_code=str(w.get("region_code") or ""),
            lat=_coerce_float(w.get("lat")) or 0.0,
            lng=_coerce_float(w.get("lng")) or 0.0,
        )
        for w in wh_rows
        if w.get("warehouse_id") and w.get("lat") is not None and w.get("lng") is not None
    ]

    # 3. Region centroid — Neptune side 우선, 없으면 in-code fallback
    region_meta_rows = neptune.open_cypher(
        "MATCH (r:Region) WHERE r.level = 'sido' OR r.level IS NULL "
        "RETURN r.region_code AS region_code, r.name_ko AS name_ko, "
        "       r.lat AS lat, r.lng AS lng"
    ) or []
    region_meta: Dict[str, Dict[str, Any]] = {}
    for r in region_meta_rows:
        rc = str(r.get("region_code") or "")
        if not rc:
            continue
        lat = _coerce_float(r.get("lat"))
        lng = _coerce_float(r.get("lng"))
        if lat is None or lng is None:
            continue
        region_meta[rc] = {
            "name_ko": str(r.get("name_ko") or _SIDO_CENTROID.get(rc, {}).get("name_ko", rc)),
            "lat": lat, "lng": lng,
        }
    # Fallback fill — 17 시도 모두 등장 보장
    for rc, meta in _SIDO_CENTROID.items():
        region_meta.setdefault(rc, dict(meta))

    # 4. Region별 회원 집계 (Python-side — 1,000행이면 충분히 가벼움)
    region_buckets: Dict[str, Dict[str, Any]] = {}
    for row in member_rows:
        rc = str(row.get("region_code") or "")
        if rc not in region_meta:
            continue
        b = region_buckets.setdefault(rc, {
            "members": 0, "churn_sum": 0.0, "ltv_sum": 0,
            "tier_mix": {"Bronze": 0, "Silver": 0, "Gold": 0, "VIP": 0},
        })
        b["members"] += 1
        b["churn_sum"] += float(row.get("churn_risk") or 0.0)
        b["ltv_sum"]   += int(row.get("ltv_krw") or 0)
        tier = str(row.get("tier") or "Bronze")
        if tier in b["tier_mix"]:
            b["tier_mix"][tier] += 1

    # 5. Region → 가장 가까운 Warehouse 거리 계산 + coverage 판정
    regions_out: List[RegionCoverage] = []
    total_members = 0
    covered_members = 0
    uncovered_buckets: List[tuple] = []  # (members, region_code)
    for rc, meta in region_meta.items():
        b = region_buckets.get(rc, {
            "members": 0, "churn_sum": 0.0, "ltv_sum": 0,
            "tier_mix": {"Bronze": 0, "Silver": 0, "Gold": 0, "VIP": 0},
        })
        nearest_id, nearest_km = None, None
        for w in warehouses:
            d = _haversine_km(meta["lat"], meta["lng"], w.lat, w.lng)
            if nearest_km is None or d < nearest_km:
                nearest_km, nearest_id = d, w.warehouse_id
        covered = nearest_km is not None and nearest_km <= radius_km
        members = int(b["members"])
        avg_churn = round(b["churn_sum"] / members, 3) if members else 0.0
        avg_ltv = int(b["ltv_sum"] / members) if members else 0
        regions_out.append(RegionCoverage(
            region_code=rc,
            name_ko=str(meta["name_ko"]),
            lat=float(meta["lat"]),
            lng=float(meta["lng"]),
            members=members,
            avg_churn_risk=avg_churn,
            avg_ltv_krw=avg_ltv,
            tier_mix=b["tier_mix"],
            nearest_warehouse_id=nearest_id,
            nearest_warehouse_km=nearest_km,
            covered=covered,
        ))
        total_members += members
        if covered:
            covered_members += members
        elif members > 0:
            uncovered_buckets.append((members, rc, str(meta["name_ko"])))

    uncovered_buckets.sort(reverse=True)
    top_uncov = uncovered_buckets[0] if uncovered_buckets else None

    summary = CoverageSummary(
        persona_id=persona,
        persona_label_ko=_PERSONA_LABEL.get(persona) if persona else None,
        radius_km=radius_km,
        total_members=total_members,
        covered_members=covered_members,
        uncovered_members=total_members - covered_members,
        coverage_pct=round(covered_members / total_members * 100, 1) if total_members else 0.0,
        top_uncovered_region_code=top_uncov[1] if top_uncov else None,
        top_uncovered_region_ko=top_uncov[2] if top_uncov else None,
        top_uncovered_member_count=top_uncov[0] if top_uncov else 0,
    )

    # region_code 정렬 — 지도 색 스케일 비교 시 안정적 순서
    regions_out.sort(key=lambda r: r.region_code)
    return CoverageDashboardResponse(
        summary=summary,
        regions=regions_out,
        warehouses=warehouses,
    )
