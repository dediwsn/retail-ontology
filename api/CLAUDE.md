# api/CLAUDE.md — FastAPI backend

## Role

HTTP surface for all thirteen scenarios (A–M) plus the knowledge-graph object explorer, ontology meta views, and operations console. Runs as `uvicorn api.main:app` on Fargate ARM64. The same image is reused as a one-shot loader via command override, so anything imported by `api.main` must also be importable inside the loader.

## Layout

- `routers/` — one file per API surface area: `acquisition, auth, chat, churn, coverage, health, ingest, insights, logistics, objects, ontology, ops, persona_match, price, safety, search, substitute, tier_up, vip` (19 routers). Registered in `api/main.py:include_router`.
- **Persona filter convention** — endpoints that filter by an active persona (coverage, churn /map, tier-up /map, **all 5 vip endpoints**) accept either spine (`per_*`) or narrative (`psn_*`) IDs and use the OR pattern `(m)-[:MATCHES_PERSONA]->(:Persona {persona_id: $pid}) OR (m)-[:MATCHES_PERSONA]->(:Persona)<-[:DERIVED_FROM]-(:Persona {persona_id: $pid})`. The narrative→spine bridge lets a UI that lists narrative personas still resolve to spine-linked Members. `/api/personas?segment_eligible=true` returns only spine + bridged narratives so the picker hides personas that would yield 0 results. The shared helper `_persona_filter_fragment()` in `api/routers/vip.py` formalises this pattern.
- **Phase 2B wallet-share queries** (vip.py) — join external panel data with internal Transactions through the OVERLAPS_WITH bridge:
  ```
  MATCH (m:Member)-[hcs:HAS_CATEGORY_SPEND {period: '2026-Q1'}]->(i:IndustryCategory)
  OPTIONAL MATCH (m)-[:MADE]->(:Transaction)-[:OF_PRODUCT]->(:Product)
                  -[:IN_CATEGORY]->(:Category)<-[:OVERLAPS_WITH]-(i)
  ```
  Computes `our_share = our_internal / (our_internal + external)` per (Member, IndustryCategory) — the basis for Opportunity / Loyal / Cross-category VIP cohorts. See ADR-0008.
- `services/` — boto3 / Neptune / OpenSearch / AgentCore wrappers. Each service module owns one external dependency.
- `services/agent.py` — Bedrock Converse multi-turn with TOOL_SPECS (`semantic_search`, `kb_lookup`, `neptune_subgraph`, `memory_recall`, `inventory_lookup`, `nearest_warehouses`, `shortest_path`). The chat scenario (B) and the logistics inline panel both stream from `/api/chat`.
- `aws_clients.py` — `@lru_cache` factory functions for boto3 clients/sessions. **Always call as functions** (`session().client(...)`, not `session.client(...)`).
- `middleware_auth.py` — Cognito JWT verification (RS256, JWKS TTL cache, constant-time origin token compare).
- `config.py` — Pydantic settings, env-var hydration.
- `Dockerfile` — multi-stage Python 3.12-slim, `linux/arm64` only.

## Conventions

- **Cypher params**: pass as `parameters={...}` keyword argument to `neptune.open_cypher`. Positional 2nd arg is a TypeError (the function signature has `*` between query and parameters).
- **F-strings**: never escape quotes inside expressions (`f"...{d[\"k\"]}..."` is a SyntaxError). Extract a local variable first.
- **boto3 sessions**: `from api.aws_clients import session as boto_session` then `boto_session().client("ce", region_name="us-east-1")`.
- **SSE events**: every streaming endpoint must yield `{"type": "<phase|delta|log|final|result>", "data": {...}}`. The web client `streamSSE<T>` consumes this shape generically.
- **Bedrock model**: chat and insights both use `s.bedrock_chat_model_id` (Sonnet 4.6). Never silently downgrade to Haiku Lite.
- **Guardrails**: input scrub via `guardrails.apply` for chat and search; output scrub for insights answer. Failure is non-fatal.
- **Tool dispatch in agent.py**: tool calls are also recorded in `_TRACE_BUF` (in-process ring buffer for `/ops/trace`).

## Adding a new scenario

1. Create `api/routers/<slug>.py` with a `router = APIRouter(tags=["<slug>"])`.
2. Add `app.include_router(<slug>.router, prefix="/api")` in `api/main.py`.
3. Define request/response Pydantic models inline.
4. If invoking Bedrock, use `from api.aws_clients import bedrock_runtime` and the `s.bedrock_chat_model_id` model.
5. Document the route in `docs/api-reference.md`.
6. If long-running, also add an SSE streaming variant `/<slug>/stream` using the shared event vocabulary.

## Testing

Three layers, fastest first:

```bash
# 1. AST validation — single router (sub-second)
python3 -c "import ast; ast.parse(open('api/routers/<file>.py').read())"

# 2. Pytest offline suite (28 tests, ~0.6s) — covers smoke imports + Pydantic + /healthz + /api/search integration with mocked services
pytest tests -q

# 3. Live wow-query eval against deployed CloudFront (target ≥85%, sys.exit(1) below)
python3 scripts/eval_wow_queries.py
```

CI runs steps 1+2 on every push/PR (`.github/workflows/ci.yml`). Step 3 requires a deployed environment with `DEMO_PUBLIC_MODE=true` or a session cookie — see `.claude/skills/wow-query-eval.md`.

Adding a router test: create `tests/api/test_<router>_integration.py`, use the `client` fixture from `tests/api/conftest.py`, patch service-layer calls at `api.routers.<router>.<service>.<func>`. See `tests/CLAUDE.md` for conventions.

Local uvicorn run (`uvicorn api.main:app --reload`) requires VPN/SSM into the VPC for Neptune + AOSS reachability — most demo work is done against the deployed instance.
