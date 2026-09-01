"""
Deterministic in-memory stand-in for the demo graph.

Every entity is derived from a SHA-1-seeded PRNG, matching the convention in
`data/synthetic/` — the same seed always yields the same world, so a mocked
walkthrough is reproducible and screenshots stay comparable across runs.

Region codes are taken verbatim from `web/public/korea-provinces.json`
(`feature.properties.code`), not from the KOSTAT scheme, because that file is
what the choropleth actually joins on. Getting this wrong renders a grey map.
"""
from __future__ import annotations

import hashlib
from datetime import date, timedelta
from typing import Any, Dict, List

ANCHOR = date(2026, 4, 1)


def _rand(*parts: Any) -> float:
    """Stable 0..1 from any key — the SHA-1 trick used by data/synthetic."""
    h = hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()
    return int(h[:12], 16) / float(0xFFFFFFFFFFFF)


def _pick(seq: List[Any], *parts: Any) -> Any:
    return seq[int(_rand(*parts) * len(seq)) % len(seq)]


def _rint(lo: int, hi: int, *parts: Any) -> int:
    return lo + int(_rand(*parts) * (hi - lo + 1)) % (hi - lo + 1)


# ─── Regions — must match web/public/korea-provinces.json ──────────────────
REGIONS: List[Dict[str, Any]] = [
    {"region_code": "11", "name_ko": "서울특별시", "lat": 37.5665, "lng": 126.9780, "population": 9_386_000},
    {"region_code": "21", "name_ko": "부산광역시", "lat": 35.1796, "lng": 129.0756, "population": 3_293_000},
    {"region_code": "22", "name_ko": "대구광역시", "lat": 35.8714, "lng": 128.6014, "population": 2_374_000},
    {"region_code": "23", "name_ko": "인천광역시", "lat": 37.4563, "lng": 126.7052, "population": 2_997_000},
    {"region_code": "24", "name_ko": "광주광역시", "lat": 35.1595, "lng": 126.8526, "population": 1_429_000},
    {"region_code": "25", "name_ko": "대전광역시", "lat": 36.3504, "lng": 127.3845, "population": 1_442_000},
    {"region_code": "26", "name_ko": "울산광역시", "lat": 35.5384, "lng": 129.3114, "population": 1_110_000},
    {"region_code": "29", "name_ko": "세종특별자치시", "lat": 36.4801, "lng": 127.2890, "population": 387_000},
    {"region_code": "31", "name_ko": "경기도", "lat": 37.4138, "lng": 127.5183, "population": 13_630_000},
    {"region_code": "32", "name_ko": "강원도", "lat": 37.8228, "lng": 128.1555, "population": 1_527_000},
    {"region_code": "33", "name_ko": "충청북도", "lat": 36.8000, "lng": 127.7000, "population": 1_593_000},
    {"region_code": "34", "name_ko": "충청남도", "lat": 36.5184, "lng": 126.8000, "population": 2_123_000},
    {"region_code": "35", "name_ko": "전라북도", "lat": 35.7175, "lng": 127.1530, "population": 1_759_000},
    {"region_code": "36", "name_ko": "전라남도", "lat": 34.8679, "lng": 126.9910, "population": 1_814_000},
    {"region_code": "37", "name_ko": "경상북도", "lat": 36.4919, "lng": 128.8889, "population": 2_600_000},
    {"region_code": "38", "name_ko": "경상남도", "lat": 35.4606, "lng": 128.2132, "population": 3_280_000},
    {"region_code": "39", "name_ko": "제주특별자치도", "lat": 33.4890, "lng": 126.4983, "population": 675_000},
]
REGION_CODES = [r["region_code"] for r in REGIONS]
REGION_BY_CODE = {r["region_code"]: r for r in REGIONS}

# ─── Personas — 5 spine + a few narrative, as in data/synthetic/personas ───
SPINE_PERSONAS = [
    {"persona_id": "per_pregnant", "label_ko": "임산부", "age": 32, "gender": "F",
     "life_stage_ko": "임신 2기", "is_spine": True,
     "avoided_ingredient_ids": ["ing_retinol", "ing_salicylic"],
     "preferred_ingredient_ids": ["ing_ceramide", "ing_panthenol"],
     "favorite_brick_codes": ["10000123"]},
    {"persona_id": "per_kid_4yo_mom", "label_ko": "4세 아이 엄마", "age": 35, "gender": "F",
     "life_stage_ko": "육아기", "is_spine": True,
     "avoided_ingredient_ids": ["ing_paraben"],
     "preferred_ingredient_ids": ["ing_oat"], "favorite_brick_codes": ["10000456"]},
    {"persona_id": "per_camper", "label_ko": "캠퍼", "age": 41, "gender": "M",
     "life_stage_ko": "아웃도어", "is_spine": True,
     "avoided_ingredient_ids": [], "preferred_ingredient_ids": ["ing_electrolyte"],
     "favorite_brick_codes": ["10000789"]},
    {"persona_id": "per_sensitive_skin", "label_ko": "민감성 피부", "age": 28, "gender": "F",
     "life_stage_ko": "직장인", "is_spine": True,
     "avoided_ingredient_ids": ["ing_alcohol_denat", "ing_fragrance"],
     "preferred_ingredient_ids": ["ing_ceramide", "ing_centella"],
     "favorite_brick_codes": ["10000123"]},
    {"persona_id": "per_gluten_allergy", "label_ko": "글루텐 알레르기", "age": 37, "gender": "F",
     "life_stage_ko": "직장인", "is_spine": True,
     "avoided_ingredient_ids": ["ing_gluten", "ing_wheat"],
     "preferred_ingredient_ids": ["ing_rice_flour"], "favorite_brick_codes": ["10000456"]},
]
NARRATIVE_LABELS = [
    "야근 잦은 개발자", "주말 등산러", "신혼 2년차", "수험생 학부모", "홈카페 애호가",
    "러닝 크루", "반려견 보호자", "1인 가구 자취생", "채식 지향", "환절기 비염",
]
NARRATIVE_PERSONAS = [
    {"persona_id": f"psn_{i:03d}", "label_ko": lbl, "age": 24 + (i * 3) % 30,
     "gender": "F" if i % 2 else "M", "is_spine": False,
     "derived_from": SPINE_PERSONAS[i % len(SPINE_PERSONAS)]["persona_id"],
     "avoided_ingredient_ids": [], "preferred_ingredient_ids": [],
     "favorite_brick_codes": []}
    for i, lbl in enumerate(NARRATIVE_LABELS)
]
PERSONAS = SPINE_PERSONAS + NARRATIVE_PERSONAS
PERSONA_BY_ID = {p["persona_id"]: p for p in PERSONAS}

# ─── Ingredients / concerns / trends ───────────────────────────────────────
INGREDIENTS = [
    ("ing_ceramide", "세라마이드", "Ceramide NP", "INCI"),
    ("ing_centella", "센텔라아시아티카", "Centella Asiatica Extract", "INCI"),
    ("ing_panthenol", "판테놀", "Panthenol", "INCI"),
    ("ing_retinol", "레티놀", "Retinol", "INCI"),
    ("ing_salicylic", "살리실릭애씨드", "Salicylic Acid", "INCI"),
    ("ing_alcohol_denat", "변성알코올", "Alcohol Denat.", "INCI"),
    ("ing_fragrance", "향료", "Fragrance", "INCI"),
    ("ing_paraben", "파라벤", "Methylparaben", "INCI"),
    ("ing_gluten", "글루텐", "Gluten", "FoodOn"),
    ("ing_wheat", "밀", "Wheat", "FoodOn"),
    ("ing_rice_flour", "쌀가루", "Rice Flour", "FoodOn"),
    ("ing_oat", "귀리", "Oat", "FoodOn"),
    ("ing_electrolyte", "전해질", "Electrolyte Blend", "Custom"),
    ("ing_niacinamide", "나이아신아마이드", "Niacinamide", "INCI"),
    ("ing_hyaluronic", "히알루론산", "Sodium Hyaluronate", "INCI"),
]
CONCERNS = [
    ("cnc_dry", "건조함", "Dryness", "skin"),
    ("cnc_sensitive", "민감함", "Sensitivity", "skin"),
    ("cnc_sebum", "피지", "Sebum", "skin"),
    ("cnc_gluten_free", "글루텐 프리", "Gluten free", "diet"),
    ("cnc_lowsugar", "저당", "Low sugar", "diet"),
    ("cnc_outdoor", "야외활동", "Outdoor", "lifestyle"),
]
TRENDS = [
    ("trd_clean", "클린 뷰티", "kbeauty", "성분 투명성과 저자극 처방을 앞세운 흐름",
     ["세라마이드", "센텔라아시아티카", "판테놀"], 9),
    ("trd_barrier", "장벽 강화", "kbeauty", "피부 장벽 회복을 핵심 소구점으로 삼는 스킨케어",
     ["세라마이드", "판테놀"], 7),
    ("trd_glutenfree", "글루텐 프리", "diet", "알레르기·소화 이슈로 확대되는 대체 곡물 수요",
     ["쌀가루", "귀리"], 6),
    ("trd_camping", "캠핑 간편식", "korea", "간편 조리와 보관성을 앞세운 아웃도어 식품",
     ["전해질"], 5),
    ("trd_lowsugar", "저당 음료", "functional", "제로 슈거 확산 이후의 기능성 음료",
     ["전해질"], 4),
    ("trd_sunprotect", "데일리 선케어", "seasonal", "사계절 자외선 차단 루틴 정착",
     ["나이아신아마이드"], 4),
]

# ─── Brands / categories / products ────────────────────────────────────────
BRANDS = [
    ("brd_001", "라네즈"), ("brd_002", "이니스프리"), ("brd_003", "아이오페"),
    ("brd_004", "닥터자르트"), ("brd_005", "롯데칠성"), ("brd_006", "오뚜기"),
    ("brd_007", "풀무원"), ("brd_008", "매일유업"), ("brd_009", "아모레퍼시픽"),
    ("brd_010", "CJ제일제당"),
]
CATEGORIES = [
    ("10000123", "세럼/에센스", "beauty"),
    ("10000456", "영유아 간식", "grocery"),
    ("10000789", "간편 조리식품", "grocery"),
    ("10000321", "선케어", "beauty"),
    ("10000654", "기능성 음료", "grocery"),
]
PRODUCT_NOUNS = ["세럼", "크림", "선크림", "간편식", "이온음료", "쌀과자", "로션", "앰플"]


def _product(i: int) -> Dict[str, Any]:
    brand = _pick(BRANDS, "brand", i)
    cat = _pick(CATEGORIES, "cat", i)
    noun = _pick(PRODUCT_NOUNS, "noun", i)
    ings = sorted({_pick(INGREDIENTS, "ing", i, k)[0] for k in range(3)})
    return {
        "sku_id": f"sku_{i:03d}",
        "name_ko": f"{brand[1]} {noun} {100 + i % 400}",
        "brand_id": brand[0],
        "gs1_brick_code": cat[0],
        "domain": cat[2],
        "price_krw": 3_000 + _rint(0, 60, "price", i) * 500,
        "ingredients": ings,
        "target_concern_ids": [_pick(CONCERNS, "cnc", i)[0]],
        "description_ko": f"{brand[1]}의 {noun}. {_pick(['저자극 처방', '데일리 사용', '휴대 간편', '가족용 대용량'], 'desc', i)}.",
    }


PRODUCTS = [_product(i) for i in range(250)]
PRODUCT_BY_SKU = {p["sku_id"]: p for p in PRODUCTS}

# ─── Channels ──────────────────────────────────────────────────────────────
CHANNELS = [
    ("ch_cu", "CU", "편의점"), ("ch_emart", "이마트", "마트"),
    ("ch_oliveyoung", "올리브영", "드럭스토어"), ("ch_kurly", "마켓컬리", "온라인"),
]

# ─── Warehouses / carriers / routes ────────────────────────────────────────
WH_TYPES = ["mfr", "rdc", "3pl", "lastmile"]
WH_OPERATORS = ["CJ대한통운", "한진", "롯데글로벌로지스", "이마트", "쿠팡", "마켓컬리"]


def _warehouse(i: int) -> Dict[str, Any]:
    region = REGIONS[i % len(REGIONS)]
    jitter_lat = (_rand("wlat", i) - 0.5) * 0.5
    jitter_lng = (_rand("wlng", i) - 0.5) * 0.5
    op = _pick(WH_OPERATORS, "op", i)
    return {
        "wh_id": f"wh_{i:02d}",
        "name_ko": f"{op} {region['name_ko'][:2]} {_pick(['DC', 'FC', '허브', '센터'], 'whk', i)}",
        "type": WH_TYPES[i % len(WH_TYPES)],
        "region_code": region["region_code"],
        "lat": round(region["lat"] + jitter_lat, 4),
        "lng": round(region["lng"] + jitter_lng, 4),
        "capacity_pallets": 400 + _rint(0, 40, "cap", i) * 50,
        "cold_chain": _rand("cold", i) > 0.55,
        "operator_label": op,
    }


WAREHOUSES = [_warehouse(i) for i in range(30)]
WH_BY_ID = {w["wh_id"]: w for w in WAREHOUSES}

CARRIERS = [
    ("car_cj", "CJ대한통운", "road"), ("car_hanjin", "한진택배", "road"),
    ("car_lotte", "롯데택배", "road"), ("car_kdexp", "경동택배", "road"),
    ("car_coupang", "쿠팡로지스틱스", "road"), ("car_air", "대한항공 화물", "air"),
    ("car_sea", "연안해운", "sea"),
]


def _routes() -> List[Dict[str, Any]]:
    out = []
    for i in range(76):
        a = WAREHOUSES[i % len(WAREHOUSES)]
        b = WAREHOUSES[(i * 7 + 3) % len(WAREHOUSES)]
        if a["wh_id"] == b["wh_id"]:
            b = WAREHOUSES[(i * 7 + 4) % len(WAREHOUSES)]
        dist = round(abs(a["lat"] - b["lat"]) * 111 + abs(a["lng"] - b["lng"]) * 89, 1) + 12
        out.append({
            "route_id": f"rte_{i:03d}",
            "from_wh_id": a["wh_id"], "to_wh_id": b["wh_id"],
            "carrier_id": _pick([c[0] for c in CARRIERS], "car", i),
            "distance_km": dist,
            "transit_hours": round(dist / 62.0 + 1.5, 1),
        })
    return out


ROUTES = _routes()

EVENT_TYPES = ["폭설", "집중호우", "명절 물량 급증", "도로 통제", "항만 파업", "한파"]
EVENTS = [
    {
        "event_id": f"evt_{i:03d}",
        "name_ko": f"{_pick(EVENT_TYPES, 'evt', i)} — {REGIONS[i % len(REGIONS)]['name_ko'][:2]}",
        "type": _pick(EVENT_TYPES, "evt", i),
        "severity": _pick(["low", "medium", "high"], "sev", i),
        "region_code": REGIONS[i % len(REGIONS)]["region_code"],
        "start": str(ANCHOR - timedelta(days=_rint(1, 40, "evs", i))),
        "end": str(ANCHOR + timedelta(days=_rint(1, 20, "eve", i))),
        "status": _pick(["active", "resolved"], "est", i),
    }
    for i in range(12)
]

# ─── Members / tiers / campaigns ───────────────────────────────────────────
TIERS = [
    ("tier_bronze", "브론즈", "Bronze", 0, 0.00),
    ("tier_silver", "실버", "Silver", 500_000, 0.03),
    ("tier_gold", "골드", "Gold", 2_000_000, 0.05),
    ("tier_vip", "VIP", "VIP", 5_000_000, 0.08),
]
_SURNAMES = ["김", "이", "박", "최", "정", "강", "조", "윤", "장", "임"]
_GIVEN = ["서연", "지우", "민준", "하은", "도윤", "시우", "예린", "지호", "수아", "건우"]

# persona region bias — camper skews 강원, kid-mom skews 경기 (matches
# data/synthetic/membership.py intent so the maps tell the same story)
_PERSONA_REGION_BIAS = {
    "per_camper": "32", "per_kid_4yo_mom": "31",
    "per_pregnant": "11", "per_sensitive_skin": "11", "per_gluten_allergy": "21",
}


def _member(i: int) -> Dict[str, Any]:
    persona = _pick([p["persona_id"] for p in SPINE_PERSONAS], "mp", i)
    bias = _PERSONA_REGION_BIAS.get(persona)
    region = bias if (bias and _rand("mrb", i) < 0.45) else _pick(REGION_CODES, "mr", i)
    ltv = _rint(30_000, 8_000_000, "ltv", i)
    tier = ("VIP" if ltv >= 5_000_000 else "Gold" if ltv >= 2_000_000
            else "Silver" if ltv >= 500_000 else "Bronze")
    recency = _rint(1, 400, "rec", i)
    freq = _rint(1, 60, "frq", i)
    risk = min(1.0, max(0.0, recency / 420.0 * 0.7 + (1 - min(freq, 40) / 40) * 0.3))
    return {
        "member_id": f"mem_{i:04d}",
        "name_ko": _pick(_SURNAMES, "sn", i) + _pick(_GIVEN, "gn", i),
        "age": _rint(19, 68, "age", i),
        "gender": "F" if _rand("g", i) > 0.42 else "M",
        "tier": tier,
        "persona_id": persona,
        "region_code": region,
        "recency_days": recency,
        "frequency": freq,
        "monetary_krw": ltv,
        "ltv_krw": ltv,
        "churn_risk": round(risk, 3),
        "primary_channel_id": _pick([c[0] for c in CHANNELS], "pc", i),
    }


MEMBERS = [_member(i) for i in range(1000)]

CAMPAIGN_CHANNELS = ["email", "push", "sms", "kakao"]
CAMPAIGN_TYPES = ["acquisition", "retention", "winback"]
CAMPAIGNS = [
    {
        "campaign_id": f"cmp_{i + 1:03d}",
        "name_ko": f"{_pick(['봄맞이', '신규회원', '휴면고객', '등급업', '캠핑시즌'], 'cn', i)} "
                   f"{_pick(['카카오톡', '이메일', '푸시'], 'cc', i)} 캠페인 {i + 1}",
        "type": _pick(CAMPAIGN_TYPES, "ct", i),
        "channel": _pick(CAMPAIGN_CHANNELS, "cch", i),
        "cost_krw": _rint(500_000, 12_000_000, "cost", i),
        "start": str(ANCHOR - timedelta(days=_rint(30, 200, "cs", i))),
        "end": str(ANCHOR - timedelta(days=_rint(1, 29, "ce", i))),
    }
    for i in range(20)
]

INDUSTRY_CATEGORIES = [
    ("ind_skincare", "스킨케어"), ("ind_makeup", "메이크업"),
    ("ind_bodysun", "바디·선케어"), ("ind_beverage", "음료·티"),
    ("ind_health", "건강기능식품"), ("ind_babyfood", "영유아 식품"),
    ("ind_campfood", "캠핑·BBQ 식품"), ("ind_grocery", "일반 식료품"),
    ("ind_household", "생활용품"), ("ind_outdoor", "캠핑 장비"),
]
# The two deliberate blind spots — no OVERLAPS_WITH edge, so wallet share is 0%.
BLIND_SPOT_INDUSTRIES = {"ind_household", "ind_outdoor"}


def members_for_persona(persona_id: str | None) -> List[Dict[str, Any]]:
    """Spine or narrative persona → members, mirroring the DERIVED_FROM bridge."""
    if not persona_id:
        return MEMBERS
    spine = persona_id
    p = PERSONA_BY_ID.get(persona_id)
    if p and not p.get("is_spine"):
        spine = p.get("derived_from", persona_id)
    return [m for m in MEMBERS if m["persona_id"] == spine]
