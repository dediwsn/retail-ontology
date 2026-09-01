---
name: wow-query-eval
description: Run the 30-query wow evaluation against the deployed CloudFront domain to verify search quality. Use when measuring search pass rate, before merging changes to api/services/search.py, api/routers/search.py, ontology/mappings/, or data/synthetic/products.py, or when investigating regressions in semantic search quality.
---

# Wow Query Evaluation

Project-specific search quality gate. The harness has 30 demo-critical queries spanning the five wow personas (psn_001 임산부 / psn_002 글루텐알레르기 워킹맘 / psn_003 민감성 24세 / psn_004 헬스챌린저 / psn_005 MD). The eval declares **≥85% pass rate** as the merge gate, enforced by `sys.exit(1)` in the script (see ADR target on `.claude/commands/test-all.md`).

## Pre-flight checks

Before running, verify:

0. **Domain exported**: `export PUBLIC_DOMAIN=<your CloudFront alias>` — every command below uses it.
1. **CloudFront reachable**: `curl -sI "https://$PUBLIC_DOMAIN/healthz"` returns 200.
2. **API healthy**: `curl -sI "https://$PUBLIC_DOMAIN/api/healthz"` returns 200.
3. **Cognito demo user provisioned**: if `DEMO_PUBLIC_MODE` is unset, `/api/search` requires a session cookie. Either set the demo user's session cookie via `--cookie` (see `scripts/provision_cognito_users.sh`) or temporarily flip `DEMO_PUBLIC_MODE=true` for a one-off measurement.

## Run

```bash
python3 scripts/eval_wow_queries.py --cf-domain "$PUBLIC_DOMAIN"
```

The script prints a per-query pass/fail row, an overall pass rate, and exits non-zero if pass rate < 85%.

## Interpreting failures

If pass rate drops below 85%, investigate in this order:

1. **Per-persona breakdown** — group failures by persona (queries 1-5 = 민감성, 6-10 = 임산부, 11-15 = 글루텐알레르기, 16-20 = 헬스, 21-25 = MD, 26-30 = cross-cutting). Single-persona failure usually points to missing wow_moment SKUs in `data/synthetic/products.py` for that persona.
2. **Keyword vocabulary** — failed queries log the searched keywords. Missing matches often come from missing Korean synonyms in `ontology/mappings/inci-to-korean.csv` or `foodon-to-korean.json`.
3. **RRF tuning** — if many queries return hits but the top-5 don't include a relevant SKU, candidate pool or RRF k may need adjustment in `api/services/search.py`.
4. **Reranker fallback** — if Cohere rerank-v3 is unavailable, the script silently falls back to RRF order. Check the API logs for "reranker unavailable" warnings.

## What "pass" means

A query passes when at least one keyword in its expected-keyword list appears in the top-5 hits' text or metadata fields (case-insensitive substring match). The keyword list per query is curated manually in `scripts/eval_wow_queries.py:21-58`; expand it when adding new wow personas or scenarios.

## Outputs

When this skill completes, emit a single verdict line followed by the per-persona breakdown so the result is comparable across invocations:

```
Pass rate: <N>/30 (<P>%) — [PASS|FAIL]
By persona: 민감성 X/5 · 임산부 X/5 · 글루텐 X/5 · 헬스 X/5 · MD X/5 · cross X/5
First 3 failing queries:
  - q##: "<query>" — top-5 contained no expected keywords (got: <top-1 hit text>)
```

The `[PASS]` verdict requires ≥85% (script's `sys.exit(1)` threshold). `[FAIL]` requires identifying which of the 4 root-cause categories applies (per-persona / vocabulary / RRF tuning / reranker fallback) — at least one category in the verdict block.

## Related

- `.claude/commands/test-all.md` — wraps this eval in the broader test suite (TS type-check + Python AST + wow eval + smoke).
- `data/synthetic/products.py` — the `is_wow` / `wow_moment` columns must remain populated for the queries to pass.
- Upstream API: `api/routers/search.py` (`/api/search` endpoint), `api/services/search.py` (BM25 + KNN + RRF + rerank).
