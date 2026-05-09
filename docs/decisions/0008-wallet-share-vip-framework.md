# ADR-0008: Wallet-Share VIP — 5-Axis Definitions Framework

- Status: Accepted
- Date: 2026-05-08
- Deciders: whchoi (solo SA)
- Tags: vip, wallet-share, scenario-m, retail-strategy

## Context

Internal data alone defines "VIP" by spending with us (`tier="VIP"` when `LTV ≥ 5M`). This *misses* members who:

- Spend big in some category externally but only 5% of it with us → **growth-ready blind spot**
- Show majority share in one category, near-zero in adjacent — **cross-sell opportunity invisible**
- Trend rapidly upward across all categories but haven't crossed the LTV threshold yet — **future VIP**

The Phase 2B external-consumption panel (ADR-0009) gives us per-(member, IndustryCategory) external spend. The question is: how do we *operationalise* it into VIP cohorts that drive different marketing actions?

## Decision

**Five strategic axes, all on the same data layer, all with the same persona-aware OR-pattern, all rendered through a single generic `CandidatesTable<T>` component.**

| Axis | Filter (Cypher) | Action |
|---|---|---|
| **Whale** | `Member.tier="VIP"` AND `ltv_krw ≥ 5M` | Retention — keep them |
| **Loyal** | `our_share ≥ 0.5` AND `total_spend ≥ 300k` | Defensive — protect margin |
| **Opportunity** | `our_share ≤ 0.3` AND `total_spend ≥ 500k` | Growth — biggest upside |
| **Cross-category** | `distinct_internal_cats=1` AND `external_floor_krw ≥ 500k` in non-overlapping industries | Up-sell |
| **Trajectory** | `q1/q0 ≥ 1.2` AND `tier≠VIP` | Early-upgrade campaigns |

Implementation choices:

1. **Default thresholds tuned against the synthetic distribution** — most consequentially `Loyal share_floor=0.5` (was 0.7) + `total_floor_krw=300k` (was 1M). The original `0.7/1M` produced 0 candidates because median wallet share is ~0% and p90 is 26%. See `ae4df57`. The slider lets users dial up to 0.95 for stricter "dominant share" selection.

2. **One Cypher query per axis** — no shared base query with conditional filters. Each `/api/vip/{name}` endpoint is independent and easy to read (~60 lines each). The shared abstraction is `_persona_filter_fragment()` (15 lines), used by all 5.

3. **`CandidatesTable<T>` is the only frontend abstraction** — generic over row type, takes a `columns[]` config. Each tab declares its own column shape (4–9 columns). No premature abstraction across tab bodies; all 5 share the same KPI-strip layout with `KpiCard`, `SliderControl`, `ChurnCell`, `ShareCell` widgets.

4. **Persona context flows through `useActivePersona()`** — same widget that drives Coverage/Churn/Tier-up.

## Alternatives Considered

- **Single `/api/vip/list?type=opportunity|loyal|...`** with a dispatcher. Rejected — type-safe response shapes get messy when the schema differs (Whale has no industry, Cross-category has *target* + *internal* industry, Trajectory has q0/q1).
- **Materialised "vip cohort" table per axis**. Rejected for PoC — rules change fast (`0.7/1M` → `0.5/300k` was a same-day decision) and graph queries are fast enough at 1k members.
- **Score-based composite** (`weighted_sum(opportunity_score, loyal_score, ...)` → "top VIPs"). Rejected — collapses 5 *different actions* into one ranking; the strategic value of the framework is keeping them as separate cells a member can simultaneously occupy.

## Consequences

### Positive

- **Single screen, 5 strategic lenses** — Same member can be in multiple cells simultaneously (e.g., Whale + Loyal in one category + Cross-category opportunity in another). Marketing prioritisation = read off the cell intersections.
- **Threshold tunability** — every axis exposes its critical knobs as URL params (`share_ceiling`, `ltv_floor_krw`, `growth_floor`). UI sliders make the demo interactive without an API change.
- **Demo coherence** — persona switch propagates across all 5 tabs automatically because they share the OR-pattern filter.

### Negative

- **5 endpoints to maintain** — schema drift risk if one tab adds a field the others don't. Mitigated by typed response models (Pydantic backend + TS frontend), same `_persona_filter_fragment()` helper, and the generic `CandidatesTable<T>`.
- **Threshold defaults are editorial, not empirical** — the 0.5/300k Loyal default is what works for the synthetic distribution. Real customer data would warrant re-tuning. Documented as a *known synthetic-data trade-off* in the page footnote.

## Status

Implemented across:
- `dd5dffd` — Opportunity tab + data layer
- `c3ab510` — Loyal / Whale / Cross-category / Trajectory tabs (4 endpoints + data layer extended for Q4)
- `ae4df57` — Loyal default tuned

Verified counts on deployed graph (api task-def 31): Whale 239 / Loyal 60 / Opportunity 968 distinct / Cross-category 21 distinct / Trajectory 437 distinct.

## See also

- [ADR-0009](0009-phase-2b-data-model.md) — the IndustryCategory + OVERLAPS_WITH bridge that all 5 axes consume.
- `api/routers/vip.py` — implementation of all 5 endpoints + `_persona_filter_fragment` helper.
- `web/app/vip/page.tsx` — `CandidatesTable<T>` and 5 tab subcomponents.
