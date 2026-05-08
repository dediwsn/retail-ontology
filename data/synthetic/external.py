"""External consumption layer (Phase 2B) — fully deterministic.

Produces two datasets that join above the existing graph:

  - industry_categories.json   (10 industry-level categories with GS1 overlap)
  - external_spend.json        (~6,000 (Member)-[:HAS_CATEGORY_SPEND]-(IndustryCategory)
                                edges with 2026-Q1 KRW amounts)

Why a separate "industry-level" layer (not just GS1 bricks)?
  External consumption data in the real world (NICE, KCB, 마이데이터,
  Nielsen panel) arrives at *higher granularity* than internal SKU-level
  transactions. Modelling that explicitly via `IndustryCategory` +
  `OVERLAPS_WITH` lets a Member simultaneously have:
    - precise internal Transactions on individual Products (GS1 bricks)
    - aggregate external spend on broad market categories
  …and lets queries compute *wallet share* = our_spend ÷ total_spend
  without forcing the synthesis to fake brick-level external data.

Persona bias is applied per industry category — camper indexes high in
캠핑/아웃도어, 임산부 in 영유아 식품, sensitive-skin in 스킨케어 — same
coherence pattern as members.region_id (ADR-0007).

Run:  python -m data.synthetic.external
Outputs to data/output/{industry_categories,external_spend}.json
"""
from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Tuple

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"

# Two demo periods — the *current* quarter for VIP cohort identification,
# and the *prior* quarter for Trajectory VIP (growth = current / prior).
# Real systems would have a deeper time-series; two snapshots is enough
# to demo the *direction* signal that's invisible with a single period.
PERIOD_KEY = "2026-Q1"          # current
PRIOR_PERIOD_KEY = "2025-Q4"    # for trajectory comparison


def _stable_growth_factor(seed: str) -> float:
    """Per-member q0/q1 ratio. Lower = stronger growth.
    Distribution chosen so the trajectory-VIP query (q1/q0 ≥ 1.2) catches
    roughly the top 25% (strong growers).

      25% strong-growth   factor 0.40 .. 0.65   (q1/q0 = 1.54 .. 2.50)
      35% mild-growth     factor 0.65 .. 0.85   (q1/q0 = 1.18 .. 1.54)
      30% flat            factor 0.85 .. 1.05   (q1/q0 = 0.95 .. 1.18)
      10% declining       factor 1.05 .. 1.50   (q1/q0 = 0.67 .. 0.95)
    """
    roll = _stable_int(seed, "growth-roll", mod=100)
    if roll < 25:
        return 0.40 + _stable_float(seed, "g-strong") * 0.25
    elif roll < 60:
        return 0.65 + _stable_float(seed, "g-mild") * 0.20
    elif roll < 90:
        return 0.85 + _stable_float(seed, "g-flat") * 0.20
    else:
        return 1.05 + _stable_float(seed, "g-decl") * 0.45


def _stable_int(*parts: str, mod: int) -> int:
    h = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()
    return int(h[:8], 16) % max(1, mod)


def _stable_float(*parts: str) -> float:
    h = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def _weighted_pick(seed: str, weights: Dict[str, float]) -> str:
    total = sum(weights.values()) or 1.0
    r = _stable_float(seed, "wpick") * total
    acc = 0.0
    for k, w in weights.items():
        acc += w
        if r < acc:
            return k
    return next(iter(weights))


# ─── Industry categories ──────────────────────────────────────────────────
#
# 10 categories at the level external panel data ships at. Each maps to
# zero or more GS1 brick codes via OVERLAPS_WITH. Two of them (`household`,
# `outdoor`) deliberately have NO GS1 overlap — these represent *our blind
# spots*: external categories where members spend but we sell nothing.
# Those produce wallet_share=0 rows, which are the strongest "Opportunity
# VIP" signal for a strategist.

_INDUSTRY_CATEGORIES: List[Dict[str, Any]] = [
    {
        "industry_id": "ind_skincare",
        "name_ko": "스킨케어",
        "domain": "beauty",
        "baseline_krw_q": 240_000,    # quarterly median per consumer
        "gs1_brick_codes": ["bty_toner","bty_serum","bty_cleanser","bty_cream",
                            "bty_mask","bty_cica","bty_cleansing_oil","bty_eye"],
    },
    {
        "industry_id": "ind_makeup",
        "name_ko": "메이크업",
        "domain": "beauty",
        "baseline_krw_q": 150_000,
        "gs1_brick_codes": ["bty_makeup","bty_lip"],
    },
    {
        "industry_id": "ind_body_sun",
        "name_ko": "바디·선케어",
        "domain": "beauty",
        "baseline_krw_q": 90_000,
        "gs1_brick_codes": ["bty_sunscreen","bty_body"],
    },
    {
        "industry_id": "ind_beverage",
        "name_ko": "음료·티",
        "domain": "grocery",
        "baseline_krw_q": 300_000,
        "gs1_brick_codes": ["10000064","10000065","10000066","10000067",
                            "10000148","10000149","10000150"],
    },
    {
        "industry_id": "ind_food_health",
        "name_ko": "건강기능식품",
        "domain": "grocery",
        "baseline_krw_q": 360_000,
        "gs1_brick_codes": ["10000228","10000229","10000245","10000246",
                            "10000247","10000248"],
    },
    {
        "industry_id": "ind_food_baby",
        "name_ko": "영유아 식품·이유식",
        "domain": "grocery",
        "baseline_krw_q": 600_000,
        "gs1_brick_codes": ["10000700","10000701","10000702"],
    },
    {
        "industry_id": "ind_food_camping",
        "name_ko": "캠핑·BBQ 식품",
        "domain": "grocery",
        "baseline_krw_q": 270_000,
        "gs1_brick_codes": ["10000800","10000801","10000802",
                            "10000900","10000901","10000902","10000903"],
    },
    {
        "industry_id": "ind_grocery_general",
        "name_ko": "일반 식료품",
        "domain": "grocery",
        "baseline_krw_q": 750_000,
        "gs1_brick_codes": ["10000159","10000160","10000300","10000400",
                            "10000604","10000605","10000606","10000607"],
    },
    # Two blind-spot categories — no GS1 overlap, our wallet share = 0.
    # These are the primary signal-generators for "Opportunity VIP".
    {
        "industry_id": "ind_household",
        "name_ko": "생활용품·세제",
        "domain": "grocery",
        "baseline_krw_q": 210_000,
        "gs1_brick_codes": [],
    },
    {
        "industry_id": "ind_outdoor",
        "name_ko": "캠핑 장비·아웃도어",
        "domain": "lifestyle",
        "baseline_krw_q": 180_000,
        "gs1_brick_codes": [],
    },
]


# Persona × Industry multiplier — same pattern as Phase 2A-G region bias
# (ADR-0007). Multipliers compound on top of `baseline_krw_q`.
_PERSONA_INDUSTRY_BIAS: Dict[str, Dict[str, float]] = {
    "per_pregnant": {
        "ind_food_baby":     2.5,
        "ind_food_health":   2.0,
        "ind_skincare":      1.3,
        "ind_household":     1.4,
    },
    "per_kid_4yo_mom": {
        "ind_food_baby":     2.0,
        "ind_grocery_general": 1.6,
        "ind_household":     1.6,
        "ind_food_health":   1.3,
        "ind_beverage":      1.2,
    },
    "per_camper": {
        "ind_food_camping":  3.0,
        "ind_outdoor":       3.5,
        "ind_beverage":      1.5,
        "ind_household":     1.2,
    },
    "per_sensitive_skin": {
        "ind_skincare":      2.5,
        "ind_body_sun":      1.6,
        "ind_makeup":        1.3,
        "ind_food_health":   1.2,
    },
    "per_gluten_allergy": {
        "ind_food_health":   2.0,
        "ind_food_baby":     1.3,
        "ind_grocery_general": 1.2,
        "ind_household":     1.1,
    },
}


def _persona_industry_weights(persona_id: str) -> Dict[str, float]:
    """Per-industry weight for a persona, normalised so weights sum to 1.

    Used both for picking which industries this Member spends in (some
    are skipped) and for scaling the spend amount within a chosen
    industry.
    """
    bias = _PERSONA_INDUSTRY_BIAS.get(persona_id, {})
    out: Dict[str, float] = {}
    for cat in _INDUSTRY_CATEGORIES:
        cid = cat["industry_id"]
        out[cid] = bias.get(cid, 1.0)
    return out


def generate_industry_categories() -> List[Dict[str, Any]]:
    return [dict(c) for c in _INDUSTRY_CATEGORIES]


def generate_external_spend(members: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """For each Member, select 4–7 industries (persona-biased) and assign
    a deterministic quarterly spend amount.

    Multi-persona Member is simplified — Member.persona_id is used as the
    bias source. Fall back to uniform weighting when persona_id is None.
    """
    out: List[Dict[str, Any]] = []
    for m in members:
        member_id = m["member_id"]
        seed = f"ext-{member_id}"
        persona_id = m.get("persona_id") or "per_gluten_allergy"

        weights = _persona_industry_weights(persona_id)
        # Member tier nudges discretionary spend up — VIP/Gold spend more
        # across the board. Scale the weighted base.
        tier_scale = {"VIP": 1.6, "Gold": 1.3, "Silver": 1.0, "Bronze": 0.7}.get(
            m.get("tier", "Bronze"), 1.0
        )

        # How many industries this member spends in: 4–7, persona-biased.
        # Members in more "broad-life" personas (kid_4yo_mom, camper) hit
        # more categories; sensitive_skin / gluten members are narrower.
        breadth_band = {
            "per_pregnant":       (4, 6),
            "per_kid_4yo_mom":    (5, 7),
            "per_camper":         (5, 7),
            "per_sensitive_skin": (3, 5),
            "per_gluten_allergy": (4, 6),
        }.get(persona_id, (4, 6))
        breadth = breadth_band[0] + _stable_int(seed, "breadth",
                                                 mod=breadth_band[1] - breadth_band[0] + 1)

        # Pick `breadth` distinct industries, deterministically.
        picked: List[str] = []
        remaining = dict(weights)
        for i in range(breadth):
            if not remaining:
                break
            choice = _weighted_pick(f"{seed}-pick{i}", remaining)
            picked.append(choice)
            del remaining[choice]

        # Per-member growth factor — same across all this member's industries
        # so the "rising member" signal is coherent (not category-by-category
        # random). Trajectory VIP catches members with low q0_factor.
        q0_factor = _stable_growth_factor(seed)

        # Assign amount per chosen industry — baseline × tier × persona-multiplier × noise.
        for cid in picked:
            cat = next(c for c in _INDUSTRY_CATEGORIES if c["industry_id"] == cid)
            persona_mult = _PERSONA_INDUSTRY_BIAS.get(persona_id, {}).get(cid, 1.0)
            noise = 0.5 + _stable_float(f"{seed}-{cid}", "noise") * 1.5  # 0.5..2.0
            q1_amount = int(cat["baseline_krw_q"] * tier_scale * persona_mult * noise)
            q1_amount = (q1_amount // 1000) * 1000
            q0_amount = int(q1_amount * q0_factor)
            q0_amount = (q0_amount // 1000) * 1000
            out.append({
                "member_id": member_id,
                "industry_id": cid,
                "period": PERIOD_KEY,
                "amount_krw": q1_amount,
            })
            out.append({
                "member_id": member_id,
                "industry_id": cid,
                "period": PRIOR_PERIOD_KEY,
                "amount_krw": q0_amount,
            })
    return out


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    members_path = OUTPUT_DIR / "members.json"
    if not members_path.exists():
        raise SystemExit(
            f"data/output/members.json not found. Run "
            f"`python -m data.synthetic.membership` first."
        )
    with open(members_path, encoding="utf-8") as f:
        members = json.load(f)

    industries = generate_industry_categories()
    spend = generate_external_spend(members)

    for name, data in [("industry_categories", industries),
                       ("external_spend", spend)]:
        path = OUTPUT_DIR / f"{name}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"  wrote {len(data):>5d}  {path.name}")


if __name__ == "__main__":
    main()
