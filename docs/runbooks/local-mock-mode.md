# Runbook — local mock mode (walk the UI with no AWS)

Run the **real** FastAPI app and the **real** Next.js pages with every AWS
boundary faked, so the whole UI can be reviewed page by page without an
account, credentials, or a deployed environment.

Nothing under `api/` or `web/app/` is modified to make this work. Routers,
Pydantic models, the SSE event vocabulary, error handling and the auth
middleware all execute for real; only calls that would leave the process are
replaced. See [`mocks/aws.py`](../../mocks/aws.py) for the exact seam.

## Start

```bash
# 1. API (port 8000) — no AWS credentials needed
source .venv/bin/activate
python3 scripts/devserver.py                 # --port 8100 to move it

# 2. Web (port 3100) — point the client at the mock API
cd web && npm ci
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 npx next dev -p 3100
```

Open <http://localhost:3100>. Interactive API docs: <http://localhost:8000/docs>.

Stop with `pkill -f "[d]evserver.py"` and `pkill -f "[n]ext dev"`.

## What is faked

| Real dependency | Mock |
|---|---|
| Neptune `open_cypher` | Query-shape-aware fake (two layers, below) |
| Neptune `subgraph_for_skus` | Cytoscape subgraph built from the mock catalogue |
| OpenSearch (BM25 + KNN) | `hybrid_search` replaced by token-overlap ranking |
| Bedrock Converse / ConverseStream | Fixed Korean answer, streamed in chunks |
| Bedrock InvokeModel | Deterministic 1536-dim vector; rerank returns descending scores |
| Bedrock Guardrails | Pass-through, never intervenes |
| Bedrock Knowledge Base | Canned retrieval passages |
| AgentCore Memory | Per-process dict |
| CloudWatch Logs / Cost Explorer | Canned rows for `/ops` |
| Cognito | Bypassed — `DEMO_PUBLIC_MODE=true` |

The chat agent still performs a **real tool-use round trip**: the fake Converse
returns a `toolUse` block on the first turn, so `_dispatch_tool` runs, the trace
ring buffer fills, and the tool-call panel shows genuine activity.

## How the Cypher fake works

Two layers, because most queries only need the right *shape* but a few need the
right *meaning*:

1. **Hand-written handlers** for queries whose semantics matter — regions,
   warehouses, routes, members, trends, substitute candidates, persona
   preferences. These must be internally consistent or the maps draw nonsense:
   route endpoints reference real warehouse ids, warehouses sit in real regions.
2. **Generic responder** for everything else. It parses the query's `RETURN`
   projection and synthesises a row satisfying it, deciding types from the
   *expression* (`count(...)` → int, `avg(...)` → float, `collect(...)` → list)
   before falling back to alias-name heuristics.

Unmatched queries log `MOCK-CYPHER-MISS <query prefix>` and are collected in
`mocks.aws.MISSES`, so gaps are visible rather than silent. Grep the API log:

```bash
grep MOCK-CYPHER-MISS /tmp/mockapi.log | sort -u
```

**Region codes come from `web/public/korea-provinces.json`
(`feature.properties.code`), not the KOSTAT scheme.** That file is what the
choropleth joins on; using KOSTAT codes renders a uniformly grey map.

## Verified surface

All **41 API endpoints** return 200, and all **27 page routes** compile and
render: `/`, A–M (`/search` `/chat` `/insights` `/match` `/safety` `/substitute`
`/price` `/logistics` `/churn` `/acquisition` `/tier-up` `/coverage` `/vip`),
`/objects/{type}`, `/schema`, `/standards`, `/validation`,
`/ops/{ingest,guardrail,memory,eval,trace}`, `/codegraph`.

Note `/ops` itself is a 404 by design — the route is `/ops/[area]`.

## What this mode does *not* prove

- **Data realism.** Numbers are plausible and internally consistent, not
  accurate. The generic responder invents values for any query without a
  hand-written handler, so a figure on screen may be shaped correctly and mean
  nothing. Use it to review layout, flow and wiring — never to validate an
  analytical result.
- **Query correctness.** A Cypher statement with a logic error still "works"
  here, because the fake answers the projection rather than executing the query.
- **Latency.** Everything is in-process; real Bedrock and Neptune calls dominate
  production response times.
- **Auth.** The Cognito flow and the Lambda@Edge gate are bypassed entirely.

## Determinism

Every entity derives from a SHA-1-seeded PRNG against a fixed
`ANCHOR = 2026-04-01`, matching the convention in `data/synthetic/`. The same
world is regenerated on every start, so screenshots stay comparable and a
walkthrough can be rehearsed.

Volumes: 17 regions · 30 warehouses · 76 routes · 12 events · 250 products ·
10 brands · 15 personas (5 spine + 10 narrative) · 1,000 members · 20 campaigns ·
400 transactions · 400 touchpoints · 10 industry categories.
