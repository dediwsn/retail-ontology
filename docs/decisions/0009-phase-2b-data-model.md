# ADR-0009: Phase 2B Data Model — IndustryCategory + OVERLAPS_WITH Bridge

- Status: Accepted
- Date: 2026-05-08
- Deciders: whchoi (solo SA)
- Tags: data-model, external-consumption, neptune, scenario-m

## Context

Real-world external consumption data (NICE 신한카드, KCB, 마이데이터, Nielsen panel) ships at **higher granularity** than internal SKU-level transactions:

| Source | Granularity | Coverage |
|---|---|---|
| Internal Transaction | per-SKU (GS1 8-digit brick) | only what we sell |
| External panel | per-industry-category | all merchants in that vertical |

To compute *wallet share* (`our_internal / (our_internal + external)`) we need to bring both into the same query — which means deciding how to model the granularity mismatch.

## Decision

**Two coexisting category labels with an OVERLAPS_WITH bridge edge.**

```
(Member)-[:HAS_CATEGORY_SPEND {amount_krw, period}]->(IndustryCategory)
(IndustryCategory)-[:OVERLAPS_WITH]->(Category)   ← the new node label
(Product)-[:IN_CATEGORY]->(Category)              ← unchanged GS1 layer
```

`IndustryCategory` is a **separate Neptune node label** (10 nodes — 스킨케어 / 메이크업 / 바디·선케어 / 음료·티 / 건강기능식품 / 영유아 식품 / 캠핑·BBQ 식품 / 일반 식료품 / 생활용품 / 캠핑 장비). Each carries `OVERLAPS_WITH` edges to the GS1 bricks it covers (43 edges total). Two industries (생활용품, 캠핑 장비) deliberately have **zero** overlap — they're "blind spots" where our share = 0 by definition, the strongest Opportunity-VIP signal.

The wallet-share query joins via the bridge:

```cypher
MATCH (m:Member)-[hcs:HAS_CATEGORY_SPEND {period: '2026-Q1'}]->(i:IndustryCategory)
OPTIONAL MATCH (m)-[:MADE]->(:Transaction)-[:OF_PRODUCT]->(:Product)
                -[:IN_CATEGORY]->(:Category)<-[:OVERLAPS_WITH]-(i)
WITH m, i, hcs.amount_krw AS ext, coalesce(sum(t.amount_krw), 0) AS our
...
```

## Alternatives Considered

### A. Extend `Category` with `external_*` properties

Single label, same node carries both internal SKU mapping and external spend stats:

```
Category {gs1_brick_code: "bty_toner", external_quarterly_avg_krw: ...}
```

**Rejected**:
- 53 GS1 bricks but only 10 industry-level groupings — a 5:1 fan-in. Each `Category` gets aggregate properties that conflict with its sibling bricks (e.g., `bty_toner`, `bty_serum`, `bty_cream` all roll up to "스킨케어" externally — but each has different internal sales). Storing the external aggregate on each is wrong and ambiguous.
- The "blind spot" categories (생활용품, 캠핑 장비) **don't have a corresponding GS1 brick** in our data — they'd have to be invented, polluting the GS1 namespace.

### B. Store external spend as Member properties

`Member.external_skincare_q1_krw`, `Member.external_baby_q1_krw`, etc. **Rejected**:
- 10 industries × 2 quarters × 1,000 members = 20k properties on Member nodes. Schema-fragile, breaks on adding/removing an industry.
- No way to express "category overlap" for the wallet-share query.

### C. Single `:Spend` edge with industry+brick on the edge

`(Member)-[:SPENDS_IN {industry: "skincare", brick: "bty_toner", amount: ...}]->(Period)` style. **Rejected**:
- Neptune doesn't allow nested edge properties cleanly, and the data isn't actually per-brick (panel data only ships per-industry).
- Cypher path expressions get clumsy with edge-property filtering.

### D. (Chosen) Separate IndustryCategory label + OVERLAPS_WITH bridge

Pros:
- Mirrors how external panel vendors deliver data (industry-level)
- "Blind spot" categories live cleanly without polluting GS1 brick namespace
- Wallet-share query is a clean 2-hop traversal
- New industries / overlaps add by inserting nodes/edges, not by modifying schema
- Object Explorer can navigate to IndustryCategory as a first-class type

Cons:
- One extra hop in the wallet-share query (`Category<-[:OVERLAPS_WITH]-IndustryCategory` adds latency)
- Two category-like concepts to keep straight in code reviews — mitigated by explicit `IndustryCategory` vs `Category` labels (no name collision)

## Consequences

### Positive

- **Wallet-share VIP cohorts are computable in a single Cypher** — no application-layer reconciliation between internal and external systems
- **5-axis VIP framework** (ADR-0008) shares this data model — adding a 6th VIP definition is *just another Cypher*
- **Object Explorer / Ontology meta page** treat IndustryCategory as a first-class type — round-2 doc-sync gap closed
- **Real-world data integration** (replacing synthetic with actual NICE/마이데이터 feed) becomes a generator change, not a model change

### Negative

- **OVERLAPS_WITH is editorial mapping** — currently 43 edges hand-coded in `data/synthetic/external.py:_INDUSTRY_CATEGORIES`. Real deployments need a mapping process (manual curation or LLM-assisted) for new GS1 bricks. The mapping coverage is also visible in scenario validation views.
- **Two category-flavours** mean any UI that lists "categories" must clarify which type — Object Explorer URLs are `/objects/category` vs `/objects/industry_category`.

## Status

Implemented in:
- `dd5dffd` — Pydantic + load + initial Neptune ingest
- `data/synthetic/external.py` — 10 IndustryCategory + persona × industry multipliers
- `data/load.py` — IndustryCategory MERGE + OVERLAPS_WITH MERGE + HAS_CATEGORY_SPEND with `period` edge property

Verified counts on deployed graph: 10 IndustryCategory · 43 OVERLAPS_WITH · 10,410 HAS_CATEGORY_SPEND.

## See also

- [ADR-0008](0008-wallet-share-vip-framework.md) — the 5-axis VIP framework that consumes this model.
- [docs/membership.md](../membership.md) — full graph topology including Phase 2B.
- `data/synthetic/external.py:_INDUSTRY_CATEGORIES` — the 10 IndustryCategory definitions and GS1 overlap lists.
