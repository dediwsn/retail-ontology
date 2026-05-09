"""Ontology meta-views (Palantir Foundry "Ontology Manager" inspired).

  • /api/ontology/schema      — 12 core classes + their relationships as a
                                Cytoscape-ready meta-graph. Counts via
                                Neptune so the operator sees DATA-density
                                next to TYPE-density.
  • /api/ontology/standards   — adapter mapping tables (GS1↔식약처,
                                INCI↔한글 성분, FoodOn nutrient catalog).
                                Read from ontology/mappings/*.csv bundled
                                into the API container at build time.
  • /api/ontology/validation  — coverage report: which loaded entities
                                lack a mapping in INCI/KFDA/FoodOn? Used
                                to spot data drift between Neptune and
                                the bundled mapping files.
"""
from __future__ import annotations

import csv
import json
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.services import neptune

router = APIRouter(tags=["ontology"])


# ─── Schema (meta-graph) ────────────────────────────────────────────────────

# Per spec § 8.1 (Core Classes 12) + § 8.2 (Core Relations). Hardcoded here
# rather than scraped so the meta-view stays stable even if Neptune is empty.
_CLASSES: List[Dict[str, Any]] = [
    {"label": "Product",      "ko": "상품",       "color": "#60a5fa", "domain": "core"},
    {"label": "Brand",        "ko": "브랜드",     "color": "#f472b6", "domain": "core"},
    {"label": "Manufacturer", "ko": "제조사",     "color": "#94a3b8", "domain": "core"},
    {"label": "Category",     "ko": "카테고리",   "color": "#94a3b8", "domain": "standards"},
    {"label": "Ingredient",   "ko": "성분",       "color": "#34d399", "domain": "standards"},
    {"label": "Nutrient",     "ko": "영양소",     "color": "#10b981", "domain": "standards"},
    {"label": "Concern",      "ko": "관심사/효능", "color": "#fbbf24", "domain": "lifestyle"},
    {"label": "Trend",        "ko": "트렌드",     "color": "#a78bfa", "domain": "lifestyle"},
    {"label": "Persona",      "ko": "페르소나",   "color": "#fb923c", "domain": "lifestyle"},
    {"label": "Channel",      "ko": "채널",       "color": "#22d3ee", "domain": "retail"},
    {"label": "Promotion",    "ko": "프로모션",   "color": "#a3e635", "domain": "retail"},
    {"label": "Review",       "ko": "리뷰",       "color": "#e879f9", "domain": "narrative"},
    {"label": "Region",       "ko": "지역",       "color": "#0ea5e9", "domain": "logistics"},
    {"label": "Warehouse",    "ko": "물류센터",   "color": "#14b8a6", "domain": "logistics"},
    {"label": "Carrier",      "ko": "운송사",     "color": "#06b6d4", "domain": "logistics"},
    {"label": "Route",        "ko": "운송 lane",  "color": "#84cc16", "domain": "logistics"},
    {"label": "Shipment",     "ko": "출하",       "color": "#f59e0b", "domain": "logistics"},
    {"label": "Event",        "ko": "이벤트",     "color": "#ec4899", "domain": "events"},
    {"label": "Inventory",    "ko": "재고",       "color": "#22c55e", "domain": "logistics"},
    # Membership / marketing layer
    {"label": "Member",          "ko": "회원",       "color": "#f97316", "domain": "membership"},
    {"label": "MembershipTier",  "ko": "회원등급",   "color": "#facc15", "domain": "membership"},
    {"label": "Campaign",        "ko": "캠페인",     "color": "#d946ef", "domain": "membership"},
    {"label": "Transaction",     "ko": "거래",       "color": "#38bdf8", "domain": "membership"},
    {"label": "Touchpoint",      "ko": "마케팅 접점","color": "#c084fc", "domain": "membership"},
    # Phase 2B external consumption layer (Scenario M / VIP)
    {"label": "IndustryCategory","ko": "산업 카테고리","color": "#34d399", "domain": "external"},
    # Persona spine/narrative bridge edges live as a self-loop on Persona
    # already covered by HAS_CONCERN. The DERIVED_FROM bridge edge is
    # captured in _RELATIONS below.
]

_RELATIONS: List[Dict[str, Any]] = [
    {"source": "Product", "target": "Brand",        "label": "BY_BRAND"},
    {"source": "Brand",   "target": "Manufacturer", "label": "MANUFACTURED_BY"},
    {"source": "Product", "target": "Category",     "label": "IN_CATEGORY"},
    {"source": "Product", "target": "Ingredient",   "label": "HAS_INGREDIENT"},
    {"source": "Product", "target": "Nutrient",     "label": "HAS_NUTRIENT"},
    {"source": "Product", "target": "Concern",      "label": "TARGETS_CONCERN"},
    {"source": "Concern", "target": "Ingredient",   "label": "PREFERS_INGREDIENT"},
    {"source": "Concern", "target": "Ingredient",   "label": "AVOIDS_INGREDIENT"},
    {"source": "Trend",   "target": "Ingredient",   "label": "INVOLVES"},
    {"source": "Trend",   "target": "Category",     "label": "INVOLVES"},
    {"source": "Persona", "target": "Concern",      "label": "HAS_CONCERN"},
    {"source": "Review",  "target": "Product",      "label": "ABOUT"},
    {"source": "Review",  "target": "Persona",      "label": "WRITTEN_BY"},
    {"source": "Promotion", "target": "Product",    "label": "PROMOTES"},
    {"source": "Product", "target": "Channel",      "label": "AVAILABLE_IN"},
    # Logistics / SCM / Events
    {"source": "Warehouse", "target": "Region",     "label": "LOCATED_IN"},
    {"source": "Manufacturer", "target": "Warehouse", "label": "OPERATES"},
    {"source": "Channel",   "target": "Warehouse",  "label": "FULFILLED_BY"},
    {"source": "Route",     "target": "Warehouse",  "label": "FROM"},
    {"source": "Route",     "target": "Warehouse",  "label": "TO"},
    {"source": "Route",     "target": "Carrier",    "label": "CARRIED_BY"},
    {"source": "Shipment",  "target": "Route",      "label": "VIA"},
    {"source": "Shipment",  "target": "Carrier",    "label": "CARRIED_BY"},
    {"source": "Shipment",  "target": "Product",    "label": "CONTAINS"},
    {"source": "Event",     "target": "Region",     "label": "AFFECTS_REGION"},
    {"source": "Event",     "target": "Category",   "label": "AFFECTS_CATEGORY"},
    {"source": "Inventory", "target": "Warehouse",  "label": "HELD_AT"},
    {"source": "Inventory", "target": "Product",    "label": "OF_SKU"},
    # Membership / marketing
    {"source": "Member",      "target": "MembershipTier", "label": "BELONGS_TO"},
    {"source": "Member",      "target": "Persona",        "label": "MATCHES_PERSONA"},
    {"source": "Member",      "target": "Channel",        "label": "PREFERS_CHANNEL"},
    {"source": "Member",      "target": "Transaction",    "label": "MADE"},
    {"source": "Transaction", "target": "Product",        "label": "OF_PRODUCT"},
    {"source": "Member",      "target": "Touchpoint",     "label": "HAS_TOUCHPOINT"},
    {"source": "Touchpoint",  "target": "Campaign",       "label": "FROM_CAMPAIGN"},
    {"source": "Campaign",    "target": "Persona",        "label": "TARGETS"},
    {"source": "Member",      "target": "Region",         "label": "LIVES_IN"},
    {"source": "Persona",     "target": "Persona",        "label": "DERIVED_FROM"},
    # Phase 2B external consumption (Scenario M / VIP wallet share)
    {"source": "Member",          "target": "IndustryCategory", "label": "HAS_CATEGORY_SPEND"},
    {"source": "IndustryCategory","target": "Category",         "label": "OVERLAPS_WITH"},
]


class SchemaResponse(BaseModel):
    classes: List[Dict[str, Any]]
    relations: List[Dict[str, Any]]
    node_counts: Dict[str, int]
    edge_counts: Dict[str, int]
    standards: List[Dict[str, str]]


@router.get("/ontology/schema", response_model=SchemaResponse)
def schema() -> SchemaResponse:
    # Hydrate counts so the meta-graph shows DATA density per type.
    node_counts: Dict[str, int] = {}
    edge_counts: Dict[str, int] = {}
    try:
        for r in neptune.open_cypher(
            "MATCH (n) RETURN labels(n)[0] AS lbl, count(n) AS c"
        ):
            node_counts[str(r.get("lbl") or "")] = int(r.get("c") or 0)
        for r in neptune.open_cypher(
            "MATCH ()-[r]->() RETURN type(r) AS rel, count(r) AS c"
        ):
            edge_counts[str(r.get("rel") or "")] = int(r.get("c") or 0)
    except Exception:  # noqa: BLE001
        pass

    standards = [
        {"label": "GS1 GPC",       "scope": "Category brick codes (8-digit)", "kind": "global"},
        {"label": "FoodOn",         "scope": "Food/nutrient ontology",          "kind": "global"},
        {"label": "INCI",           "scope": "Cosmetic ingredient nomenclature","kind": "global"},
        {"label": "schema.org",     "scope": "HealthCondition / Product / Brand","kind": "global"},
        {"label": "식약처 (KFDA)",   "scope": "Korea food category + 효능표시",  "kind": "korea"},
        {"label": "Custom KR",      "scope": "Beauty subcategories (시카/한방/...)","kind": "korea"},
    ]
    return SchemaResponse(
        classes=_CLASSES,
        relations=_RELATIONS,
        node_counts=node_counts,
        edge_counts=edge_counts,
        standards=standards,
    )


# ─── Standards mapping (CSV browser) ────────────────────────────────────────

_MAPPINGS_DIR = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "ontology", "mappings",
))


class StandardsListResponse(BaseModel):
    items: List[Dict[str, Any]]


class StandardsTableResponse(BaseModel):
    file: str
    columns: List[str]
    rows: List[Dict[str, str]]
    total: int


def _list_csv_files() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not os.path.isdir(_MAPPINGS_DIR):
        return out
    for fname in sorted(os.listdir(_MAPPINGS_DIR)):
        if not fname.endswith(".csv"):
            continue
        path = os.path.join(_MAPPINGS_DIR, fname)
        try:
            with open(path, encoding="utf-8") as f:
                # cheap row-count without loading whole CSV
                row_count = sum(1 for _ in f) - 1
        except Exception:  # noqa: BLE001
            row_count = 0
        out.append({"file": fname, "rows": max(row_count, 0)})
    return out


@router.get("/ontology/standards", response_model=StandardsListResponse)
def standards_list() -> StandardsListResponse:
    return StandardsListResponse(items=_list_csv_files())


# ─── Validation report (mapping coverage) ───────────────────────────────────
#
# For each external standard bundled at /ontology/mappings, sample the loaded
# Neptune graph and report which entities reference an ID that doesn't appear
# in the corresponding mapping file. This surfaces silent data drift between
# the loader output and the standards bundle (e.g., a new SKU references
# `foodon:99999999` that no Korean translation exists for).


class ValidationCheck(BaseModel):
    name: str               # human-readable check name
    standard: str           # GS1 / INCI / FOODON / KFDA
    expected: int           # number of distinct refs in graph
    covered: int            # number that map cleanly
    missing: List[str]      # up to 30 unresolved IDs (sample)
    severity: str           # ok / warn / error
    note: str


class ValidationResponse(BaseModel):
    checks: List[ValidationCheck]


def _read_csv_keys(path: str, *key_cols: str) -> set[str]:
    """Read a CSV and return the union of values across the given columns
    (first match wins per-row, falling back to next column if missing).
    Trying multiple columns lets validators cope with mappings that may
    rename keys across versions.
    """
    if not os.path.isfile(path):
        return set()
    keys: set[str] = set()
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            for col in key_cols:
                v = (row.get(col) or "").strip()
                if v:
                    keys.add(v)
                    break
    return keys


def _inci_slug(name: str) -> str:
    """Mirror data/public/inci.py::_slug. The loader stores ingredient_id as
    `inci:{_slug(inci_name)}`, but the CSV only has the human-readable
    `inci_name` column. To compare apples-to-apples, slugify CSV names
    into the same `inci:...` form before set-diff."""
    return (
        name.lower()
        .replace(" ", "-")
        .replace("/", "-")
        .replace(",", "")
        .replace("(", "")
        .replace(")", "")
    )


def _read_json_keys(path: str) -> set[str]:
    if not os.path.isfile(path):
        return set()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return set(str(k) for k in data.keys()) if isinstance(data, dict) else set()
    except Exception:  # noqa: BLE001
        return set()


def _severity(missing: int, expected: int) -> str:
    if expected == 0:
        return "ok"
    ratio = missing / expected
    if ratio == 0:
        return "ok"
    if ratio < 0.05:
        return "warn"
    return "error"


@router.get("/ontology/validation", response_model=ValidationResponse)
def validation_report() -> ValidationResponse:
    checks: List[ValidationCheck] = []

    # 1. INCI — every Ingredient with `standard=INCI` should appear in
    #    inci-to-korean.csv. The CSV stores readable `inci_name` (e.g.
    #    "Tocopherol") but Neptune nodes store the slugified ID
    #    `inci:tocopherol` — we slugify the CSV side to match.
    inci_path = os.path.join(_MAPPINGS_DIR, "inci-to-korean.csv")
    inci_csv_names = _read_csv_keys(inci_path, "inci_name", "inci_id", "id")
    inci_keys = {f"inci:{_inci_slug(n)}" for n in inci_csv_names}
    rows = neptune.open_cypher(
        "MATCH (n:Ingredient) WHERE n.standard = 'INCI' "
        "RETURN n.ingredient_id AS id"
    )
    inci_ids = {str(r["id"]) for r in rows if r.get("id")}
    inci_missing = sorted(inci_ids - inci_keys)[:30]
    checks.append(ValidationCheck(
        name="INCI 한글 매핑 커버리지",
        standard="INCI",
        expected=len(inci_ids),
        covered=len(inci_ids & inci_keys),
        missing=inci_missing,
        severity=_severity(len(inci_ids - inci_keys), len(inci_ids)),
        note="Ingredient(standard=INCI) 노드의 ingredient_id가 inci-to-korean.csv (slug 매칭)에 존재하는지",
    ))

    # 2. FoodOn — every `foodon:NNNNNNN` Ingredient ID should appear in the
    #    Korean alias map (foodon-to-korean.json). Recently hydrated.
    foodon_path = os.path.join(_MAPPINGS_DIR, "foodon-to-korean.json")
    foodon_keys = _read_json_keys(foodon_path)
    rows = neptune.open_cypher(
        "MATCH (n:Ingredient) WHERE n.ingredient_id STARTS WITH 'foodon:' "
        "RETURN n.ingredient_id AS id"
    )
    foodon_ids = {str(r["id"]) for r in rows if r.get("id")}
    foodon_missing = sorted(foodon_ids - foodon_keys)[:30]
    checks.append(ValidationCheck(
        name="FoodOn 한글 매핑 커버리지",
        standard="FOODON",
        expected=len(foodon_ids),
        covered=len(foodon_ids & foodon_keys),
        missing=foodon_missing,
        severity=_severity(len(foodon_ids - foodon_keys), len(foodon_ids)),
        note="foodon:NNNNNNN ID가 foodon-to-korean.json에 존재하는지",
    ))

    # 3. GS1 GPC ↔ KFDA — every food-domain Product with a brick code
    #    should map to a KFDA category path via gs1-gpc-to-kfda-food.csv.
    #    Beauty/personal-care brick codes are out of scope for the food
    #    CSV (they have a separate KFDA cosmetics adapter, not bundled
    #    in this demo), so we filter the Neptune side to grocery/food.
    gs1_path = os.path.join(_MAPPINGS_DIR, "gs1-gpc-to-kfda-food.csv")
    gs1_keys = _read_csv_keys(gs1_path, "gs1_brick_code", "brick_code")
    rows = neptune.open_cypher(
        "MATCH (p:Product)-[:IN_CATEGORY]->(c:Category) "
        "WHERE c.gs1_brick_code IS NOT NULL "
        "  AND (c.domain = 'grocery' OR c.domain = 'food') "
        "RETURN DISTINCT c.gs1_brick_code AS code"
    )
    gs1_codes = {str(r["code"]) for r in rows if r.get("code")}
    gs1_missing = sorted(gs1_codes - gs1_keys)[:30]
    checks.append(ValidationCheck(
        name="GS1 GPC ↔ 식약처(식품) 매핑 커버리지",
        standard="GS1/KFDA",
        expected=len(gs1_codes),
        covered=len(gs1_codes & gs1_keys),
        missing=gs1_missing,
        severity=_severity(len(gs1_codes - gs1_keys), len(gs1_codes)),
        note="식품 도메인 Product가 참조하는 GS1 brick code가 KFDA 식품 매핑 CSV에 있는지 (뷰티 brick은 범위 외)",
    ))

    # 4. Channel coverage — every Product should be reachable from at least
    #    one Channel via AVAILABLE_IN. This catches broken loader runs.
    rows = neptune.open_cypher(
        "MATCH (p:Product) "
        "OPTIONAL MATCH (p)-[:AVAILABLE_IN]->(c:Channel) "
        "WITH p, count(c) AS chans "
        "WHERE chans = 0 "
        "RETURN p.sku_id AS sku LIMIT 30"
    )
    isolated_skus = [str(r["sku"]) for r in rows if r.get("sku")]
    total_rows = neptune.open_cypher("MATCH (p:Product) RETURN count(p) AS c")
    total_products = int((total_rows[0].get("c") if total_rows else 0) or 0)
    checks.append(ValidationCheck(
        name="Product → Channel 적재 커버리지",
        standard="LOADER",
        expected=total_products,
        covered=total_products - len(isolated_skus),
        missing=isolated_skus,
        severity=_severity(len(isolated_skus), total_products),
        note="모든 Product가 최소 1개 Channel과 AVAILABLE_IN 연결돼야 함 (지정 채널 누락 검출)",
    ))

    return ValidationResponse(checks=checks)


@router.get("/ontology/standards/{filename}", response_model=StandardsTableResponse)
def standards_table(filename: str, limit: int = 500) -> StandardsTableResponse:
    if "/" in filename or "\\" in filename or filename.startswith("."):
        raise HTTPException(status_code=400, detail="invalid filename")
    if not filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="only .csv allowed")
    path = os.path.join(_MAPPINGS_DIR, filename)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail=f"not found: {filename}")
    rows: List[Dict[str, str]] = []
    columns: List[str] = []
    try:
        with open(path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            columns = list(reader.fieldnames or [])
            for i, r in enumerate(reader):
                if i >= int(limit):
                    break
                rows.append({k: (v or "") for k, v in r.items()})
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"read failed: {e}")
    return StandardsTableResponse(
        file=filename, columns=columns, rows=rows, total=len(rows),
    )
