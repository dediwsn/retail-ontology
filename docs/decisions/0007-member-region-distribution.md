# ADR-0007: Persona-Biased KOSTAT Distribution for Synthetic Member Geography

- Status: Accepted
- Date: 2026-05-08
- Deciders: whchoi (solo SA)
- Tags: data-synthesis, demo-coherence, geography, neptune

## Context

Phase 2A introduced 1,000 synthetic `Member` nodes with persona, tier, RFM, channel, and lifecycle fields — but no location. This was an explicit limitation noted in the original `docs/membership.md` §8: "회원 위치 없음 → 시나리오 H 물류와 직접 연결 불가".

The new scenario L (Coverage Map) needs per-member geography to render the persona-filtered choropleth and compute coverage to the existing Warehouse markers. We had three options for *how* to assign location.

## Decision

We assign **`Member.region_id`** (KOSTAT 시도 코드) at synthesis time using **persona-biased weighted picks over a population baseline**.

### Mechanism

```python
# baseline (population in millions, KOSTAT 2024)
_REGION_POPULATION_M = {
    "11": 9.7,   # 서울
    "31": 13.4,  # 경기
    "21": 3.3,   # 부산
    ...  # 17 시도
}

# per-persona multipliers — domain-driven, applied on top of population baseline
_PERSONA_REGION_MULTIPLIER = {
    "per_pregnant":       {"11": 1.6, "31": 1.7, "23": 1.4},          # 수도권 신혼·출산
    "per_kid_4yo_mom":    {"31": 2.0, "23": 1.5, "11": 1.2, "34": 1.2}, # 신도시 띠
    "per_camper":         {"32": 3.0, "37": 1.6, "38": 1.5, "34": 1.4,
                           "33": 1.4, "39": 1.8},                       # 산림·캠핑 인프라
    "per_sensitive_skin": {"11": 1.4, "31": 1.4, "23": 1.2, "21": 1.2}, # 도시 미세먼지
    "per_gluten_allergy": {},                                           # 인구 비례 균등
}

# weighted pick = (population × multiplier) per region, weighted_pick(seed, weights)
```

The result is **deterministic** (same SHA1 seed always picks the same region) and **persona-coherent** (camper persona over-indexes 강원 1.8× relative to overall, kid_4yo_mom over-indexes 경기 by 32%, etc.). The 17-sido distribution is rendered via a new `(Member)-[:LIVES_IN]->(Region)` edge in Neptune that reuses the `Region` nodes already created by the logistics layer.

## Alternatives Considered

### A. Random assignment (uniform over 17 sido)

Simple but breaks demo coherence: a "캠퍼 페르소나" with 1/17 = 5.9% of members in each region looks identical to "임산부" — the choropleth shows no persona signal. **Rejected** — the entire point of the map is that persona switches show *visually distinct* distributions.

### B. Pure population proportional (no persona bias)

`region_weight = population_M`, no multiplier. Realistic in aggregate, but persona × region cells show *zero variance* across personas: 임산부 in 경기 = 임산부 in 서울 = 캠퍼 in 경기 = same proportions. The persona switch would only change the *total count*, not the *shape*. **Rejected** for the same reason as A.

### C. Real-world data (e.g. 통계청 등록인구·인구총조사 by 시도 × 연령 × 가구 형태)

Most authentic. But (i) the 5-spine personas don't map cleanly to 통계청 segmentation (no "캠퍼" demographic exists), and (ii) we'd need to license + load a multi-table dataset for what is fundamentally a *demo coherence* property. **Rejected** for PoC scope; revisit if this becomes a customer-facing product.

### D. (Chosen) Persona-biased weighted picks

Population baseline keeps aggregate distribution realistic (경기 29.3% vs real 26%, 서울 18.3% vs real 19%). Multipliers carry the *story* — viewers immediately see why camper persona "lights up" 강원/제주, why kid_4yo_mom dominates 경기 신도시 띠. The multipliers are explicit (in code, in this ADR, in `docs/membership.md` §3.3), so the synthesis is *defensible* under the kind of challenge described in the team's "임계치 챌린지" discussion: "왜 강원 7.7%? 인구 baseline의 1.8× over-index, multiplier 3.0이 보여줍니다."

## Consequences

### Positive

- **Persona switch produces visible map difference** — the headline UX of scenario L works. Camper top-3 시도 = 경기 40 / 서울 37 / **강원 16** (강원 over-indexed at 7.7% vs overall 4.3%). Pregnant top-3 = 경기 67 / 서울 43 / 부산 14 (수도권 집중).
- **Aggregate looks right** — without bias, scenario L "does the data look real?" question would fail; multipliers preserve the population shape.
- **Reuses logistics `Region` nodes** — no duplicate node label, no duplicate centroids.
- **Deterministic** — re-runs of the loader produce the same per-member region assignment, so demo URLs / member IDs are stable.

### Negative — synthesis bias is editorial, not empirical

The multipliers are *opinionated*. A QA/PM might disagree: "왜 캠퍼는 강원 ×3.0 인가? 제주는 ×1.8 이지만 인천 가까운 영종도 캠핑이 더 많지 않나?" These are real critiques. The defense is documented (this ADR) but not data-driven.

**Mitigation**: keep multipliers in **one place** (`_PERSONA_REGION_MULTIPLIER` dict in `data/synthetic/membership.py`) and link from this ADR. When a stakeholder pushes back, the conversation is: "OK let's adjust multiplier X to Y, re-run loader, observe the choropleth shift" — not "let's redesign the synthesis pipeline".

### Negative — small samples in small 시도

Sejong (29) has population 0.4M and no multiplier → after weighted pick produces ~5 members. With a persona filter that 5 becomes 1–2. The choropleth renders but the value is statistical noise.

**Mitigation**: scenario L's right-side panel already shows raw counts (`{r.members}명 미도달`). Users can see the small-N and discount accordingly.

### Negative — coupling synthesis to a "5-spine" assumption

If the team adds a 6th spine (e.g. `per_senior`), the multiplier dict needs a new row. Easy to spot but not auto-generated. Captured as a checklist item in `docs/membership.md` §9 "확장 체크리스트".

## Status

Implemented in commit `5d748c6` (`feat(data): Member.region_id with persona-biased KOSTAT distribution`). 1,000 LIVES_IN edges materialized at load time; verified that camper 강원 = 7.7% (1.8× over-index) and pregnant 수도권 = 60%+ in deployed graph queries.

## See also

- [ADR-0005](0005-narrative-spine-keyword-bridge.md) — the persona bridge that lets selections in PersonaSwitch land on the right Member cohort.
- [docs/membership.md](../membership.md) §3.3 — full distribution table with all 17 시도 weights.
- `data/synthetic/membership.py` `_REGION_POPULATION_M`, `_persona_region_bias()` — implementation.
- `api/routers/coverage.py` — the scenario that consumes this distribution end-to-end.
