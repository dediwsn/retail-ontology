# ADR-0005: Narrative→Spine Persona Bridge via Label-Keyword Matching

- Status: Accepted
- Date: 2026-05-08
- Deciders: whchoi (solo SA)
- Tags: persona, ontology, neptune, demo-coherence

## Context

The synthetic data layer ships **two persona ID schemes** that *do not align*:

- `data/output/personas.ndjson` (40 narratives) — Bedrock-narrated specific profiles like `psn_001 "임산부 6개월 32세"`, `psn_011 "34세 육아 중 아빠"`. Drives the persona-match scenario (D), which traverses `(Persona)-[:HAS_CONCERN]->(Concern)<-[:TARGETS_CONCERN]-(Product)`.
- `data/synthetic/membership.py` (5 spine) — semantic archetype IDs `per_pregnant`, `per_kid_4yo_mom`, `per_camper`, `per_sensitive_skin`, `per_gluten_allergy`. Used by 1,000 `Member` nodes via `m.persona_id = "per_*"`. Drives the segment scenarios (I/J/K/L).

Before this ADR, the loader's `MATCH (per:Persona {persona_id: $pid})` against `per_*` IDs silently created **0** `MATCHES_PERSONA` edges (no Persona node existed with `per_*` IDs). This was a latent bug that became visible only when scenario L (Coverage Map) was added — selecting any persona from the global `PersonaSwitch` widget (which lists `psn_*`) returned 0 members on the new map endpoints.

The spine MERGE (commit `a622c2b`) added the 5 `per_*` Persona nodes, fixing direct-spine selections. But the global persona widget still shipped narrative IDs to the API, and those couldn't reach the now-spine-linked Members.

## Decision

We bridge the two ID schemes with **`(narrative:Persona)-[:DERIVED_FROM]->(spine:Persona)`** edges, computed at load-time via **label-keyword matching**:

```python
_SPINE_KEYWORDS = {
    "per_pregnant":       ["임산부", "임신"],
    "per_kid_4yo_mom":    ["엄마", "4세", "유아", "아이", "워킹맘"],
    "per_camper":         ["캠퍼", "캠핑", "아웃도어"],
    "per_sensitive_skin": ["민감성", "트러블"],
    "per_gluten_allergy": ["글루텐", "셀리악", "알레르기"],
}
```

For each narrative `psn_*` Persona, scan `label_ko` for any keyword in each spine's list; create one `DERIVED_FROM` edge per match. **Multi-mapping is supported** — `psn_002 "38세 워킹맘 (4세 글루텐알레르기)"` correctly produces two edges (per_kid_4yo_mom and per_gluten_allergy).

The MERGE is idempotent: re-running the loader produces no duplicate edges, and existing `psn_*` nodes are untouched (no SET, only MERGE on the relationship).

Routers that filter by persona use the **OR pattern**:

```cypher
WHERE (m)-[:MATCHES_PERSONA]->(:Persona {persona_id: $pid})
   OR (m)-[:MATCHES_PERSONA]->(:Persona)<-[:DERIVED_FROM]-(:Persona {persona_id: $pid})
```

This accepts either spine (`per_*`) or narrative (`psn_*`) IDs and resolves the latter through one DERIVED_FROM hop. Used in `coverage.py`, `churn.py:/map`, `tier_up.py:/map`.

## Alternatives Considered

- **Embed spine ID as a property on each narrative**: simpler at query time, but loses the ability to multi-map (a narrative might span 2–3 spine concepts) and bakes an editorial decision into raw data. Rejected.
- **Use Concern overlap to bridge** (`(narrative)-[:HAS_CONCERN]->(c)<-[:HAS_CONCERN]-(spine)`): semantically richer but spines have *no* concern_ids in our data, and adding curated ones requires editorial work that isn't justified at PoC scale. Rejected for this iteration.
- **Embeddings-based similarity** (label embedding cosine ≥ 0.7): would catch cases keyword matching misses (e.g. "비건 라이프스타일" → no spine match today). Adds Bedrock dependency on the loader and doesn't help the 5-spine constraint. Rejected for PoC; revisit if spine count grows.
- **Drop narratives entirely from PersonaSwitch**: smallest code change but kills the demo richness in scenario D. Rejected.

## Consequences

### Positive

- **Selecting any visible persona returns members** on Coverage / Churn /map / Tier-up /map. The "선택하면 회원수 0" UX failure is gone for all spine + bridged-narrative selections.
- **Multi-mapping works naturally**: `psn_002` → 396 members = `per_kid_4yo_mom` (199) ∪ `per_gluten_allergy` (197). The graph union is exactly what the narrative semantically describes.
- **Backward compatibility**: `/match` scenario unchanged — it still uses the original `/api/personas` listing without the `segment_eligible` flag.
- **Auditable**: every bridge edge is reproducible from `_SPINE_KEYWORDS` + the narrative label.

### Negative — false positives

Substring matching introduces editorial noise:

- `psn_022 "21세 아이돌 지망 보컬 연습생"` → bridges to `per_kid_4yo_mom` because "아이" is a substring of "아이돌". Functionally returns ~199 members of the 4세맘 cohort.
- `psn_037 "54세 관절 건강 챙기는 등산 동호회 남성"` → bridges to `per_kid_4yo_mom` because "4세" is a substring of "54세".

These do not return 0 (UX-OK), but they semantically misclassify. **Mitigation** (deferred): word-boundary matching via regex `\b{keyword}\b`. Not worth it at PoC scale because the keyword set itself is editorial — even with word boundaries, we'd manually decide whether "55세 갱년기 주부" maps anywhere.

### Negative — coverage gap

Of 40 narratives, only ~9 distinct narratives match a spine keyword (10 edges total because of multi-mapping). The other ~30 narratives ("헬스 챌린저", "MD", "비건 라이프스타일", "55세 갱년기 주부" etc.) produce no DERIVED_FROM edges. We mitigate at the *picker* level via `GET /api/personas?segment_eligible=true` (see ADR-0006) — those narratives are simply hidden from the segment-scenario picker.

## Status

Implemented in commit `099bcef` (`fix(persona): bridge narrative→spine so any Persona selection works`). 10 edges materialized at load time; verified via Coverage / Churn /map / Tier-up /map returning non-zero member counts for both spine and bridged narrative selections.

## See also

- [ADR-0006](0006-persona-spine-coexistence.md) — why we keep both ID schemes coexisting instead of migrating to a single one.
- [ADR-0007](0007-member-region-distribution.md) — the persona-biased KOSTAT distribution that made segment maps meaningful in the first place.
- `data/load.py` `_SPINE_KEYWORDS` block — implementation.
- [docs/membership.md](../membership.md) — membership layer overview that this fix unblocks.
