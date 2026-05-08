"""Membership / Marketing synthetic generator (fully deterministic).

Produces five datasets that join the existing graph beneath the 5 Persona
archetypes:
  - tiers          (4 membership tiers: Bronze/Silver/Gold/VIP)
  - campaigns      (~20 marketing campaigns: acquisition / retention / winback)
  - members        (1,000 individual members; 홍길동/김영희/최우형 reserved)
  - transactions   (~6 / member; references existing products.ndjson)
  - touchpoints    (~10 / member; campaign reach + response)

Determinism is critical (matches data/synthetic/logistics.py): SHA1-based
PRNGs everywhere — no `random.random()`. Re-running produces identical IDs,
names, and RFM values, so demos are reproducible.

Run:  python -m data.synthetic.membership
Outputs to data/output/{tiers,campaigns,members,transactions,touchpoints}.json
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"

# Anchor matches logistics.py so events / campaigns / member activity all
# reference the same "now" without drift.
ANCHOR_DATE = date(2026, 4, 1)

TOTAL_MEMBERS = 1000
TX_PER_MEMBER_AVG = 6
TP_PER_MEMBER_AVG = 10


def _stable_int(*parts: str, mod: int) -> int:
    h = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()
    return int(h[:8], 16) % max(1, mod)


def _stable_float(*parts: str) -> float:
    """Uniform [0, 1) deterministically derived from inputs."""
    h = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def _stable_pick(seed: str, options: List[Any]) -> Any:
    return options[_stable_int(seed, mod=len(options))]


# ─── Tiers ─────────────────────────────────────────────────────────────────

_TIERS: List[Dict[str, Any]] = [
    {"tier_id": "tier_bronze", "name_ko": "브론즈", "name_en": "Bronze",
     "threshold_krw":         0, "discount_rate": 0.00},
    {"tier_id": "tier_silver", "name_ko": "실버",   "name_en": "Silver",
     "threshold_krw":   500_000, "discount_rate": 0.03},
    {"tier_id": "tier_gold",   "name_ko": "골드",   "name_en": "Gold",
     "threshold_krw": 2_000_000, "discount_rate": 0.05},
    {"tier_id": "tier_vip",    "name_ko": "VIP",    "name_en": "VIP",
     "threshold_krw": 5_000_000, "discount_rate": 0.08},
]


def _tier_for_ltv(ltv_krw: int) -> str:
    for t in reversed(_TIERS):
        if ltv_krw >= t["threshold_krw"]:
            return t["name_en"]
    return "Bronze"


def generate_tiers() -> List[Dict[str, Any]]:
    return [dict(t) for t in _TIERS]


# ─── Campaigns ─────────────────────────────────────────────────────────────
#
# 20 campaigns spanning the past 12 months. Mix is deliberately skewed
# toward retention (real Korean retail is ~60% retention, 25% acquisition,
# 15% winback). Channel mix favours kakao push (the dominant Korean channel)
# over email.

_CAMPAIGN_SEED: List[Tuple[str, str, str, str, int, int, List[str]]] = [
    # (name_ko, type, channel, start_offset_days, duration_days, cost_krw, target_persona_ids)
    # acquisition (5)
    ("신규 가입 1만원 쿠폰",        "acquisition", "kakao", 365, 30, 12_000_000, []),
    ("임산부 신혼 할인 패키지",     "acquisition", "kakao", 300, 21, 8_000_000,  ["per_pregnant"]),
    ("아이맘 환영 키트",            "acquisition", "email", 240, 14, 4_500_000,  ["per_kid_4yo_mom"]),
    ("캠퍼 시즌 할인 모객",         "acquisition", "push",  180, 21, 6_000_000,  ["per_camper"]),
    ("민감성 피부 진단 무료",       "acquisition", "kakao", 120, 14, 5_000_000,  ["per_sensitive_skin"]),
    # retention (12) — backbone of marketing spend
    ("VIP 전용 시즌 미리보기",      "retention",   "email", 350, 14, 3_000_000,  []),
    ("실버→골드 등급 상승 프로모",  "retention",   "kakao", 320, 21, 5_500_000,  []),
    ("골드 회원 적립 2배",          "retention",   "kakao", 280, 14, 4_000_000,  []),
    ("정기배송 30% 할인",           "retention",   "push",  250, 30, 7_000_000,  ["per_kid_4yo_mom", "per_pregnant"]),
    ("주말 깜짝 핫딜",              "retention",   "push",  200, 7,  2_500_000,  []),
    ("어린이날 가족 패밀리팩",      "retention",   "kakao", 145, 7,  3_500_000,  ["per_kid_4yo_mom"]),
    ("여름 폭염 대비 음료 큐레이션","retention",   "kakao", 90,  21, 4_500_000,  []),
    ("추석 명절 선물세트 미리보기", "retention",   "email", 60,  14, 6_000_000,  []),
    ("글루텐 프리 신상 큐레이션",   "retention",   "email", 50,  14, 2_500_000,  ["per_gluten_allergy"]),
    ("캠핑 시즌 BBQ 큐레이션",      "retention",   "push",  40,  14, 3_500_000,  ["per_camper"]),
    ("VIP 전용 주말 딜리버리",      "retention",   "kakao", 30,  14, 5_000_000,  []),
    ("뷰티 정기배송 추천",          "retention",   "push",  20,  21, 4_000_000,  ["per_sensitive_skin"]),
    # winback (3)
    ("90일 미접속 회원 복귀 1만원","winback",      "sms",   270, 14, 9_000_000,  []),
    ("VIP 이탈 방지 컨시어지",      "winback",      "kakao", 200, 21, 12_000_000, []),
    ("골드 등급 유지 혜택 안내",    "winback",      "email", 150, 14, 4_000_000,  []),
]


def generate_campaigns() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for i, (name, ctype, channel, start_off, dur, cost, targets) in enumerate(_CAMPAIGN_SEED):
        cid = f"cmp_{i+1:03d}"
        start = ANCHOR_DATE - timedelta(days=start_off)
        end = start + timedelta(days=dur)
        out.append({
            "campaign_id": cid,
            "name_ko": name,
            "type": ctype,
            "channel": channel,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "cost_krw": cost,
            "target_persona_ids": list(targets),
        })
    return out


# ─── Members ───────────────────────────────────────────────────────────────
#
# Korean name pool. The first three slots are reserved real-name fixtures
# requested for demo searchability (NL queries like "홍길동의 이탈 위험은?"
# need to find the same member every run).

_RESERVED_NAMES: List[Tuple[str, int, str]] = [
    # (name_ko, age, gender)
    ("홍길동", 38, "M"),
    ("김영희", 34, "F"),
    ("최우형", 42, "M"),
]

_SURNAMES = [
    "김", "이", "박", "최", "정", "강", "조", "윤", "장", "임",
    "한", "오", "서", "신", "권", "황", "안", "송", "유", "전",
    "고", "문", "손", "양", "배", "백", "허", "남", "심", "노",
]

_GIVEN_F = [
    "서연", "지우", "하윤", "서윤", "지민", "수아", "지유", "하은", "윤서", "민서",
    "예은", "지아", "채원", "유진", "예린", "수빈", "다은", "은서", "주아", "가은",
    "혜원", "지수", "다인", "서아", "예나", "유나", "서영", "예진", "선영", "은지",
]

_GIVEN_M = [
    "민준", "서준", "도윤", "예준", "시우", "주원", "하준", "지호", "지훈", "건우",
    "현우", "선우", "정우", "연우", "유찬", "준서", "도현", "민성", "재민", "성민",
    "지환", "현준", "승우", "진우", "강민", "윤호", "태윤", "동현", "민재", "수호",
]

# 5 Persona archetypes (matches data/synthetic/personas.py and demo spec)
_PERSONA_IDS = [
    "per_pregnant",
    "per_kid_4yo_mom",
    "per_camper",
    "per_sensitive_skin",
    "per_gluten_allergy",
]

# Channels to assign as the member's primary touchpoint surface
_CHANNEL_IDS = ["chn_emart", "chn_kurly", "chn_cu", "chn_oliveyoung"]


# KOSTAT 17 시도 인구(백만 명, 2024 추정) — region 분포의 baseline.
# `_persona_region_bias`가 이 값에 페르소나별 multiplier를 곱해 weighted pick.
_REGION_POPULATION_M: Dict[str, float] = {
    "11": 9.7,   # 서울특별시
    "21": 3.3,   # 부산광역시
    "22": 2.4,   # 대구광역시
    "23": 3.0,   # 인천광역시
    "24": 1.4,   # 광주광역시
    "25": 1.5,   # 대전광역시
    "26": 1.1,   # 울산광역시
    "29": 0.4,   # 세종특별자치시
    "31": 13.4,  # 경기도
    "32": 1.5,   # 강원특별자치도
    "33": 1.6,   # 충청북도
    "34": 2.1,   # 충청남도
    "35": 1.8,   # 전북특별자치도
    "36": 1.8,   # 전라남도
    "37": 2.6,   # 경상북도
    "38": 3.3,   # 경상남도
    "39": 0.7,   # 제주특별자치도
}


def _persona_region_bias(persona_id: str) -> Dict[str, float]:
    """페르소나별 시도 분포 가중치. 인구 baseline에 도메인 기반 multiplier를
    곱해 데모 코히런스를 만든다 — 페르소나 스위치 시 지도 색이 즉시 달라지도록.

    스토리 의도:
      - 임산부:   수도권 결혼/출산 집중 → 11/31/23 ↑
      - 4세맘:    경기 신도시 띠 → 31 강하게, 23/11 보조
      - 캠퍼:     산림·캠핑 인프라 → 32/37/38/34/33/39 ↑
      - 민감성피부: 도시 미세먼지 노출 → 11/31/23/21 ↑
      - 글루텐알레르기: 통계적 지역성 약함 → 균등(인구 비례)
    """
    multipliers: Dict[str, Dict[str, float]] = {
        "per_pregnant":        {"11": 1.6, "31": 1.7, "23": 1.4},
        "per_kid_4yo_mom":     {"31": 2.0, "23": 1.5, "11": 1.2, "34": 1.2},
        "per_camper":          {"32": 3.0, "37": 1.6, "38": 1.5, "34": 1.4,
                                "33": 1.4, "39": 1.8},
        "per_sensitive_skin":  {"11": 1.4, "31": 1.4, "23": 1.2, "21": 1.2},
        "per_gluten_allergy":  {},
    }
    out: Dict[str, float] = dict(_REGION_POPULATION_M)
    for code, mult in multipliers.get(persona_id, {}).items():
        out[code] = _REGION_POPULATION_M[code] * mult
    return out


def _persona_tier_bias(persona_id: str) -> Dict[str, float]:
    """Each persona has a different tier distribution — drives wow-coherence
    (e.g. pregnancy / family personas skew higher LTV; camper skews seasonal
    Silver). Values are weights, normalised by the caller."""
    return {
        "per_pregnant":        {"Bronze": 0.05, "Silver": 0.20, "Gold": 0.45, "VIP": 0.30},
        "per_kid_4yo_mom":     {"Bronze": 0.05, "Silver": 0.20, "Gold": 0.40, "VIP": 0.35},
        "per_camper":          {"Bronze": 0.30, "Silver": 0.45, "Gold": 0.20, "VIP": 0.05},
        "per_sensitive_skin":  {"Bronze": 0.15, "Silver": 0.30, "Gold": 0.40, "VIP": 0.15},
        "per_gluten_allergy":  {"Bronze": 0.10, "Silver": 0.25, "Gold": 0.40, "VIP": 0.25},
    }.get(persona_id, {"Bronze": 0.30, "Silver": 0.40, "Gold": 0.20, "VIP": 0.10})


def _weighted_pick(seed: str, weights: Dict[str, float]) -> str:
    """Deterministic weighted choice over a dict of {key: weight}."""
    total = sum(weights.values())
    r = _stable_float(seed, "weight") * total
    acc = 0.0
    for k, w in weights.items():
        acc += w
        if r < acc:
            return k
    return next(iter(weights))


def _ltv_for(persona_id: str, tier: str, seed: str) -> int:
    """LTV in KRW — log-normal-ish; tier sets the band, persona tunes the mean."""
    base_band = {"Bronze": (50_000, 400_000),
                 "Silver": (500_000, 1_900_000),
                 "Gold":   (2_000_000, 4_900_000),
                 "VIP":    (5_000_000, 15_000_000)}[tier]
    persona_mult = {"per_pregnant": 1.15, "per_kid_4yo_mom": 1.20,
                    "per_camper": 0.85, "per_sensitive_skin": 1.05,
                    "per_gluten_allergy": 1.10}.get(persona_id, 1.0)
    span = base_band[1] - base_band[0]
    raw = base_band[0] + _stable_int(seed, "ltv", mod=span)
    return int(raw * persona_mult / 1000) * 1000  # round to KRW 1k


def _churn_risk(recency_days: int, frequency: int, tier: str) -> float:
    """Heuristic RFM → churn risk in [0, 1].

    Pure age (recency) alone moves the score from ~0.2 (recent) to ~0.85
    (>180 days). Low frequency adds up to +0.15. VIP gets a -0.05 floor
    (high-LTV inertia). Result is clamped."""
    if recency_days <= 14:
        base = 0.10
    elif recency_days <= 45:
        base = 0.25
    elif recency_days <= 90:
        base = 0.45
    elif recency_days <= 180:
        base = 0.70
    else:
        base = 0.85
    freq_penalty = max(0.0, (5 - frequency)) * 0.03   # 0 .. 0.15
    tier_floor   = -0.05 if tier == "VIP" else 0.0
    risk = base + freq_penalty + tier_floor
    return max(0.0, min(1.0, round(risk, 2)))


def generate_members() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for i in range(TOTAL_MEMBERS):
        member_id = f"mem_{i+1:04d}"
        seed = member_id

        # Name: first 3 are fixtures; rest deterministic
        if i < len(_RESERVED_NAMES):
            name_ko, age, gender = _RESERVED_NAMES[i]
        else:
            gender = "F" if _stable_int(seed, "g", mod=2) == 0 else "M"
            given_pool = _GIVEN_F if gender == "F" else _GIVEN_M
            surname = _stable_pick(f"{seed}-sn", _SURNAMES)
            given   = _stable_pick(f"{seed}-gn", given_pool)
            name_ko = f"{surname}{given}"
            age = 22 + _stable_int(seed, "age", mod=43)  # 22..64

        # Persona match — uniform draw across 5 archetypes
        persona_id = _stable_pick(f"{seed}-per", _PERSONA_IDS)

        # Tier — biased per persona
        tier = _weighted_pick(seed, _persona_tier_bias(persona_id))

        # Frequency: VIP/Gold transact more
        freq_band = {"Bronze": (1, 4), "Silver": (3, 9),
                     "Gold":   (8, 18), "VIP": (15, 30)}[tier]
        frequency = freq_band[0] + _stable_int(seed, "freq", mod=freq_band[1] - freq_band[0] + 1)

        # Recency: 30% are at-risk (>90 days), distributed by tier with
        # the inverse of the freq band (weak buyers churn more)
        churn_roll = _stable_int(seed, "rec", mod=100)
        if tier == "VIP":
            risk_pct = 12
        elif tier == "Gold":
            risk_pct = 22
        elif tier == "Silver":
            risk_pct = 35
        else:
            risk_pct = 55
        if churn_roll < risk_pct:
            recency_days = 90 + _stable_int(seed, "rd-c", mod=120)   # 90..209
        else:
            recency_days = 1 + _stable_int(seed, "rd", mod=60)       # 1..60

        # LTV → tier alignment is approximate (band overlap allowed)
        ltv = _ltv_for(persona_id, tier, seed)
        # Monetary = a portion of LTV from observed transactions
        monetary = int(ltv * (0.55 + 0.30 * _stable_float(seed, "mon")))
        monetary = (monetary // 1000) * 1000

        joined_offset = 30 + _stable_int(seed, "joined", mod=900)  # joined 30..929 days ago
        joined_at = ANCHOR_DATE - timedelta(days=joined_offset)
        last_purchase_at = ANCHOR_DATE - timedelta(days=recency_days)

        churn_risk = _churn_risk(recency_days, frequency, tier)
        primary_channel_id = _stable_pick(f"{seed}-chn", _CHANNEL_IDS)
        region_id = _weighted_pick(f"{seed}-rgn", _persona_region_bias(persona_id))

        out.append({
            "member_id": member_id,
            "name_ko": name_ko,
            "age": age,
            "gender": gender,
            "tier": tier,
            "persona_id": persona_id,
            "joined_at": joined_at.isoformat(),
            "last_purchase_at": last_purchase_at.isoformat(),
            "recency_days": recency_days,
            "frequency": frequency,
            "monetary_krw": monetary,
            "ltv_krw": ltv,
            "churn_risk": churn_risk,
            "primary_channel_id": primary_channel_id,
            "region_id": region_id,
        })
    return out


# ─── Transactions ──────────────────────────────────────────────────────────


def generate_transactions(
    members: List[Dict[str, Any]],
    sku_ids: List[str],
) -> List[Dict[str, Any]]:
    """~`frequency` transactions per member, dated within the member's active
    window (joined_at..last_purchase_at). Average price ~30k KRW."""
    out: List[Dict[str, Any]] = []
    tid = 1
    if not sku_ids:
        return out
    for m in members:
        joined = date.fromisoformat(m["joined_at"])
        last = date.fromisoformat(m["last_purchase_at"])
        window = max(1, (last - joined).days)
        # Frequency hard-cap to keep the dataset bounded (~6k rows)
        n_tx = min(m["frequency"], TX_PER_MEMBER_AVG + 4)
        for k in range(n_tx):
            tx_seed = f"{m['member_id']}-tx-{k}"
            day_offset = _stable_int(tx_seed, "d", mod=window)
            ts = joined + timedelta(days=day_offset)
            sku = sku_ids[_stable_int(tx_seed, "sku", mod=len(sku_ids))]
            # Amount: 8k..120k KRW, slight tier upward bias on big-ticket
            amount = 8_000 + _stable_int(tx_seed, "amt", mod=80_000)
            if m["tier"] in ("Gold", "VIP"):
                amount += _stable_int(tx_seed, "amt2", mod=40_000)
            amount = (amount // 1000) * 1000
            out.append({
                "transaction_id": f"tx_{tid:06d}",
                "member_id": m["member_id"],
                "sku_id": sku,
                "amount_krw": amount,
                "ts": ts.isoformat(),
                "channel_id": m.get("primary_channel_id"),
            })
            tid += 1
    return out


# ─── Touchpoints ───────────────────────────────────────────────────────────


def generate_touchpoints(
    members: List[Dict[str, Any]],
    campaigns: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """~10 touchpoints per member spread across recent campaigns. Response
    rate is biased by tier (VIP/Gold respond ~30%, Bronze ~8%) and by
    persona-target match (+15% if persona is in target_persona_ids)."""
    out: List[Dict[str, Any]] = []
    tpid = 1
    if not campaigns:
        return out
    for m in members:
        n_tp = TP_PER_MEMBER_AVG + _stable_int(m["member_id"], "tpn", mod=5) - 2  # 8..12
        for k in range(n_tp):
            seed = f"{m['member_id']}-tp-{k}"
            campaign = campaigns[_stable_int(seed, "c", mod=len(campaigns))]
            # Touchpoint date inside the campaign window
            cstart = date.fromisoformat(campaign["start"])
            cend   = date.fromisoformat(campaign["end"])
            span = max(1, (cend - cstart).days)
            ts = cstart + timedelta(days=_stable_int(seed, "d", mod=span))
            tp_type = campaign["channel"] if _stable_int(seed, "t", mod=10) < 9 else "visit"

            base_response = {"VIP": 0.32, "Gold": 0.24, "Silver": 0.13, "Bronze": 0.07}[m["tier"]]
            if m.get("persona_id") in (campaign.get("target_persona_ids") or []):
                base_response += 0.15
            # Winback campaigns deliberately yield much lower response
            if campaign["type"] == "winback":
                base_response *= 0.5
            responded = _stable_float(seed, "r") < base_response

            out.append({
                "touchpoint_id": f"tp_{tpid:06d}",
                "member_id": m["member_id"],
                "campaign_id": campaign["campaign_id"],
                "type": tp_type,
                "ts": ts.isoformat(),
                "responded": responded,
            })
            tpid += 1
    return out


# ─── Entry point ───────────────────────────────────────────────────────────


def _load_sku_ids() -> List[str]:
    products_path = OUTPUT_DIR / "products.ndjson"
    sku_ids: List[str] = []
    if products_path.exists():
        with open(products_path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        sku_ids.append(json.loads(line)["sku_id"])
                    except (json.JSONDecodeError, KeyError):
                        continue
    return sku_ids


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    tiers = generate_tiers()
    campaigns = generate_campaigns()
    members = generate_members()
    sku_ids = _load_sku_ids()
    transactions = generate_transactions(members, sku_ids)
    touchpoints = generate_touchpoints(members, campaigns)

    for name, data in [
        ("tiers", tiers),
        ("campaigns", campaigns),
        ("members", members),
        ("transactions", transactions),
        ("touchpoints", touchpoints),
    ]:
        path = OUTPUT_DIR / f"{name}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"  wrote {len(data):>5d}  {path}")


if __name__ == "__main__":
    main()
