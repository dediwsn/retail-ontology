# ADR-0010: Codegraph Community Labelling via Direct Bedrock Sonnet

- Status: Accepted
- Date: 2026-05-09
- Deciders: whchoi (solo SA)
- Tags: codegraph, graphify, bedrock, llm-labelling, ops

## Context

`/codegraph` embeds a graphify-generated AST graph (1,751 nodes / 2,217 edges / 159 communities). graphify's own `update` command produces communities labelled only as numbers (`Community 0`, `Community 1`, …). Semantic labelling requires graphify's `extract --backend <gemini|kimi|claude|openai|ollama>` pipeline, which calls an *external* LLM API.

mfg-ontology used `extract --backend claude` to populate `community_labels`. We have two reasons not to copy that:

1. **No external API key** required for retail. The EC2 IAM role already has Bedrock access (we use Bedrock Sonnet 4.6 throughout the API for chat/insights). Adding `ANTHROPIC_API_KEY` introduces a new secret to manage for one offline build step.
2. **Richer schema than graphify's default**. We want per-community `description`, `key_concepts`, `top_files` — not just a label string.

## Decision

**Skip graphify's LLM pipeline. Call Bedrock Sonnet 4.6 directly via boto3, requesting structured 4-field JSON per community.**

```
scripts/label_codegraph_communities.py
  ├─ Read graph.json (1,751 nodes, 159 communities)
  ├─ For each community:
  │     ├─ Pick top-15 representative nodes (degree-ranked)
  │     ├─ Send to Bedrock Sonnet (Converse API, JSON-only prompt)
  │     └─ Parse {label, description, key_concepts}
  ├─ Compute top_files (degree-ordered, no LLM)
  └─ Write graph.community_labels + graph.community_meta
              + sidecar community_labels.json + community_meta.json
```

**graph.html receives an in-place patch** because graphify bakes node data into the HTML at build time. Each of the 1,751 nodes has `"community_name": "Community NNN"` as a JSON literal — replaced with the semantic label via simple string substitution. Patch is idempotent and survives `graphify update` re-runs as long as the script re-runs after.

**Single-call-per-community structured output** (label + description + 3 key concepts) keeps token cost low (~5–10k tokens per community × 159 ≈ 1M total) and runtime ~3 min. Temperature 0.2 keeps labels stable across re-runs.

The full pipeline (`scripts/refresh_codegraph.sh`):

1. `graphify update . --force` — AST re-extraction
2. `cp graphify-out/* web/public/codegraph/` — bundle copy
3. `python scripts/label_codegraph_communities.py` — Bedrock labelling + meta
4. In-place patch graph.html node `community_name` (1,751 occurrences)

## Alternatives Considered

### A. graphify extract --backend claude

Requires `ANTHROPIC_API_KEY` env var, single-field output (label only), schema not extensible. **Rejected** — not worth a new secret + lower information density.

### B. graphify extract --backend ollama (self-hosted)

Avoids cloud LLM cost. **Rejected** — Ollama isn't running on this EC2, deploying a labelling model is more work than calling Bedrock that's already there.

### C. Pure heuristic labelling (no LLM)

E.g., "label = filename of highest-degree node + 'module'". **Rejected** — produces unhelpful labels like "api-client.ts module" instead of "API 클라이언트 인터페이스". The whole point of labelling is *semantic compression*, which heuristics can't do for Korean.

### D. Regenerate graph.html from labelled graph.json

Run a custom rendering pass over the labelled graph.json. **Rejected** — graphify's renderer is a bundled D3 viewer (1.3MB self-contained HTML) we don't want to replicate or fork. In-place string substitution is a 30-line Python block that survives all our use cases.

## Consequences

### Positive

- **No additional secret** to provision. The Bedrock IAM permission already exists on the API task role.
- **4-field structured output** drives the rich community side-panel in `/codegraph` (description + concept chips + top-file list, all from one Sonnet call).
- **Stable across re-runs** — temperature 0.2 keeps labels close to identical between refreshes; the in-place patch is idempotent.
- **One shell script** (`scripts/refresh_codegraph.sh`) is the entire refresh contract. Documented in [runbooks/codegraph-refresh.md](../runbooks/codegraph-refresh.md).

### Negative

- **Bedrock call cost per refresh** — ~159 calls × Sonnet 4.6 pricing ≈ small dollars per refresh. Not nightly cron material; refresh on PR-merge cadence is enough.
- **Quality depends on Bedrock + the prompt** — we own the prompt now, so format drift (Sonnet returning markdown fences instead of JSON) is on us to handle. Mitigated by a regex JSON extractor.
- **Sample false positives** — a few small communities (`__init__.py`-only) get generic labels like "패키지 초기화". Acceptable for PoC; would warrant LLM prompt tuning for production.

## Status

Implemented in:
- `de2b903` — initial 159-label generation (label-only)
- `d8b6e7c` — extended to 4-field structured output (label + description + key_concepts + top_files)

Verified — 159 community labels in `community_meta.json`, 1,751 `community_name` patches in `graph.html`. Refresh runtime ~3 min including all 159 Bedrock calls.

## See also

- `scripts/label_codegraph_communities.py` — implementation
- `scripts/refresh_codegraph.sh` — one-shot pipeline wrapper
- [docs/runbooks/codegraph-refresh.md](../runbooks/codegraph-refresh.md) — operational runbook
- [`web/app/codegraph/page.tsx`](../../web/app/codegraph/page.tsx) — frontend rendering
