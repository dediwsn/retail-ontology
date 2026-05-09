# ADR-0013: Codegraph LEGEND.label patched alongside RAW_NODES.community_name

- Status: Accepted
- Date: 2026-05-09
- Deciders: @whchoi98
- Tags: codegraph, graphify, ux

## Context

`scripts/refresh_codegraph.sh` regenerates `web/public/codegraph/graph.html` from the third-party `graphify` AST tool, then a Bedrock Sonnet labelling pass produces `community_labels.json` (159 Korean labels, one per community). Until now, step 4 of the pipeline patched `RAW_NODES[i].community_name` *only* — the field consumed by graphify's per-node detail tooltip. The `LEGEND[i].label` field — consumed by the right-hand "Communities" sidebar inside the iframe, which is the most prominent visual surface — was left untouched, still showing raw `Community 0` / `Community 1` / … strings.

Result: node tooltips correctly displayed `API 클라이언트 인터페이스`, but the always-visible legend showed `Community 0`, making the Bedrock labelling appear broken. ADR-0010 documents the labelling itself; this ADR documents the *fan-out* that the labelling has to perform across multiple in-place data structures inside graph.html.

## Decision

The refresh pipeline patches **both** parallel data structures inside `graph.html` whenever it patches one — `RAW_NODES[].community_name` *and* `LEGEND[].label` are substituted from the same `community_labels.json` source. The patch step also writes `community_meta.json` (4-field JSON: label / description / key_concepts / top_files) for the external `CommunityListPanel` consumer, which is unaffected by graph.html internals. After the patch a sanity check asserts zero remaining `"label": "Community <N>"` patterns to surface any future graphify schema change as a hard signal.

## Alternatives Considered

- **Patch only `community_name`, document the legend gap (status quo)** — Rejected: the legend is the dominant visible surface inside the iframe; an inconsistent surface where tooltip and legend disagree is worse than having no labelling at all.
- **Stop using graphify's bundled HTML; render our own viewer over `graph.json`** — Rejected for now: doable but expensive (network/edge layout, hover/click interactions, search) and the patch-in-place approach is one ~20-line shell function.
- **Move labelling upstream into graphify itself (PR or fork)** — Rejected: graphify's pipeline doesn't know about Bedrock; injecting a labelling step would couple the third-party tool to AWS-specific concerns. The patch boundary stays in this repo's `refresh_codegraph.sh`.

## Consequences

### Positive

- Three surfaces (iframe legend, iframe node tooltip, external `CommunityListPanel`) now draw labels from the same source — no visible inconsistency.
- The refresh pipeline encodes the invariant ("both parallel structures get patched") as a script step, not as institutional memory — future runs can't regress as long as the script is used.

### Negative

- The pipeline is now coupled to graphify's *current* HTML schema (specifically the existence of `RAW_NODES[].community_name` and `LEGEND[].label` fields). A graphify version bump that renames these would silently produce zero substitutions; the post-patch zero-check is the early-warning signal.

### Neutral

- The Python heredoc inside `refresh_codegraph.sh` step 4 grew from ~15 to ~25 lines. Still fits comfortably in one screen and the comment block at the top of step 4 calls out the dual-data invariant explicitly.

## Implementation Notes

- Files touched:
  - `scripts/refresh_codegraph.sh` — step 4 patches both `community_name` and `LEGEND[].label`, prints both substitution counts.
  - `web/public/codegraph/graph.html` — one-time backfill (159 LEGEND substitutions) committed alongside this ADR.
- Operational invariant — after every `refresh_codegraph.sh` run, verify:
  ```bash
  grep -c '"label": "Community ' web/public/codegraph/graph.html  # must be 0
  ```
- Rollback: revert the script edit and the in-place graph.html change. The labelling pipeline will continue to work; only the legend will regress to raw IDs.

## References

- Commit `cb8fffa fix(codegraph): patch LEGEND[].label to match community_name semantic labels`
- ADR-0010 — Bedrock-driven community labelling (the upstream decision; this ADR is an addendum about distribution within graph.html)
- `docs/runbooks/codegraph-refresh.md` — end-to-end refresh procedure
