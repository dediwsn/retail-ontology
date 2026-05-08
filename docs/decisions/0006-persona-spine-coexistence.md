# ADR-0006: Coexistence of Spine and Narrative Persona ID Schemes

- Status: Accepted
- Date: 2026-05-08
- Deciders: whchoi (solo SA)
- Tags: persona, ontology, api-contract, demo-coherence

## Context

The synthetic data layer evolved in two phases that produced two unrelated persona ID conventions:

| Layer | ID format | Count | Purpose |
|---|---|---|---|
| Phase 1 narrative (`data/synthetic/personas.py`) | `psn_001..psn_040` | 40 | Bedrock-narrated rich profiles ("38세 워킹맘 4세 글루텐알레르기"); drives scenario D persona-match graph traversal |
| Phase 2A spine (`data/synthetic/membership.py`) | `per_pregnant, per_kid_4yo_mom, per_camper, per_sensitive_skin, per_gluten_allergy` | 5 | Semantic archetypes referenced by `Member.persona_id`; drives segment scenarios I/J/K/L |

These coexist on the same `Persona` label in Neptune (45 nodes total). Bridge edges from ADR-0005 connect the two via `DERIVED_FROM`.

The question this ADR answers: **why keep both, instead of consolidating to one scheme?**

## Decision

We keep **both** schemes coexisting, distinguished by a `is_spine: true` boolean on the 5 spine nodes.

API contract layered on top:

- `GET /api/personas` (no flag) — returns all 45 personas. Backward compatible for narrative-rich consumers (`/match`).
- `GET /api/personas?segment_eligible=true` — returns only `is_spine=true` OR has `(p)-[:DERIVED_FROM]->(:Persona)` outgoing edge. Returns ~14 personas (5 spine + 9 distinct bridged narratives). Used by the global `PersonaSwitch` widget so that *every visible selection* resolves to a non-empty Member cohort on segment scenarios.

Each persona item in the response exposes `is_spine`, `is_bridged`, `bridge_targets[]` so clients can group / badge appropriately. PersonaSwitch renders two visual sections — "5-spine 페르소나" (top, with SPINE badge) and "Narrative (bridged)".

## Alternatives Considered

- **Migrate all narratives to spine IDs** — collapses the data model but kills scenario D's richness (40 specific personas → 5 archetypes). Rejected.
- **Migrate spine to narrative IDs** — would require rewriting every narrative's `label_ko` to fit a 5-archetype taxonomy and re-running Bedrock generation, plus updating `Member.persona_id` references in 1,000 members + 20 campaigns. Cost/benefit doesn't pay back at PoC scale. Rejected.
- **Two separate Persona labels** (`:NarrativePersona` vs `:SpinePersona`) — clean separation but requires schema changes throughout `api/routers/objects.py`, `api/routers/ontology.py`, all Cypher in scenario routers. Bigger blast radius than necessary. Rejected.
- **Coexistence without `is_spine` flag** — query-time discrimination via ID prefix (`p.persona_id STARTS WITH 'per_'`). Works but couples ID format to behavior; prefix is convention-only. Rejected for explicitness.

## Consequences

### Positive

- **Scenario D unchanged**: persona-match keeps the rich 40-narrative library. No regression.
- **Segment scenarios work for the 5-archetype demo spine**: clean cohort separation, deterministic distributions, narrative bridging makes detail-rich PersonaSwitch entries usable.
- **Single Persona label** keeps Cypher uniform (`MATCH (p:Persona)`); the `is_spine` flag and DERIVED_FROM edges live as standard graph features.
- **API contract scales**: as the data team adds more narratives or refines the spine, only the keyword dict in ADR-0005 + `is_spine` flag need updating; the OR-pattern queries don't change.

### Negative

- **Two queries needed for full picker UX**: Match scenario uses unflagged listing, segment scenarios use `?segment_eligible=true`. Manageable but adds one decision at every new picker integration.
- **`Persona.persona_id` is no longer regex-uniform**: code paths that filter on persona ID format (none today) would need to handle both `per_*` and `psn_*` prefixes. Easy to spot (regex), but easy to miss for newcomers — captured in `api/CLAUDE.md`.
- **Persona node count is "45, but conceptually 5"**: ops dashboards that count personas need to interpret carefully. The is_spine flag lets ops queries split the 45 into "5 spine + 40 narrative" cleanly.

## Status

Implemented in commits `a622c2b` (5-spine MERGE), `099bcef` (DERIVED_FROM bridge), `f0f6b7a` (segment_eligible filter). Verified via API revision 28: `?segment_eligible=true` returns 14 items, `?` returns 45.

## See also

- [ADR-0005](0005-narrative-spine-keyword-bridge.md) — the keyword-matching mechanism that connects the two.
- `api/routers/persona_match.py` `list_personas()` — segment_eligible filter implementation.
- `web/components/PersonaSwitch.tsx` — two-group rendering of spine vs bridged.
