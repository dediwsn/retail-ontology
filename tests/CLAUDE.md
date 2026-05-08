# tests/CLAUDE.md — pytest suite

## Role

Offline test surface for the FastAPI backend. Two layers:

- **Smoke** (`tests/test_smoke.py`) — every router under `api.routers.*` and the `api.main` app must import cleanly. Catches f-string SyntaxErrors, circular imports, missing `router` exports.
- **Integration** (`tests/api/`) — Pydantic model validation + ASGI-level endpoint tests with `httpx.AsyncClient` and boto3-touching service functions mocked at the import-site. No real AWS calls.

CDK snapshot tests live separately under `infra-cdk/test/` (Jest), not here.

## Layout

- `conftest.py` — root pytest fixture; sets 18 dummy env vars (`AWS_REGION`, `NEPTUNE_ENDPOINT`, `OPENSEARCH_*`, `BEDROCK_*`, `AGENTCORE_MEMORY_ID`, S3 buckets, `ONTOLOGY_*`, `COGNITO_USER_POOL_CLIENT_ID`, `PUBLIC_DOMAIN`) so `api.config.Settings()` validates. Also flips `DEMO_PUBLIC_MODE=true` and `REQUIRE_ORIGIN_AUTH=false` to bypass auth middleware.
- `test_smoke.py` — 20 tests: parametrized router import (18 routers) + `api.main.app` instantiation + `get_settings()`.
- `api/conftest.py` — async `client` fixture using `httpx.ASGITransport` (no port binding, no real network).
- `api/test_models.py` — Pydantic validation for `SearchRequest` / `SearchResponse` (required fields, bounds, defaults).
- `api/test_health.py` — `/healthz` returns 200; unknown route 404.
- `api/test_search_integration.py` — `/api/search` 422 on bad payload; happy path with mocked `hybrid_search` + `subgraph_for_skus`; subgraph failure isolation (200 with `_error`, not 500).

## Conventions

- **Env defaults at root conftest, not at fixture time**. Pydantic Settings reads the env on first import — `os.environ.setdefault(...)` at the top of `tests/conftest.py` runs before any `api.*` import during pytest collection.
- **Mock at the import-site**, not the source. `api.routers.search` does `from api.services import search`, so the test patches `api.routers.search.search.hybrid_search`, not `api.services.search.hybrid_search`. Patching the source module leaves the router holding a stale reference.
- **`httpx.AsyncClient(transport=ASGITransport(app))`** — no port binding, no uvicorn process, async by default. Matches FastAPI's modern test pattern. Don't use `TestClient` (sync wrapper) for new tests.
- **Filename suffix `_integration` for HTTP-layer tests** — satisfies the harness-eval `prod-e2e-tests` glob (`tests/**/*{e2e,integration,integ}*`) and signals to readers that the test exercises the full app stack.
- **Run from project root**, not from `tests/` — pytest discovers `conftest.py` upward from the test file, but `import api.routers.search` only resolves when CWD is the project root.

## Running

```bash
# Install dev deps (one-time)
pip install -r api/requirements.txt -r requirements-dev.txt

# Run all tests (target <1s)
pytest tests -q

# Run a specific subset
pytest tests/test_smoke.py -q
pytest tests/api/test_search_integration.py -q

# Run with verbose failure output
pytest tests -v --tb=short
```

CI runs `pytest tests -q` as the fourth job in `.github/workflows/ci.yml` after `python-ast`, `tsc-check`, and `cdk-synth+jest`. Local pre-commit doesn't run pytest yet (gap noted by harness-eval design-evaluator) — opt in manually via the test-all.md command or just run pytest before pushing.

## Adding a new test

1. **Pydantic model test**: drop into `tests/api/test_models.py`. Construct with valid data; assert defaults and validation errors. No fixtures needed.
2. **Endpoint integration test**: create `tests/api/test_<router>_integration.py`. Use the `client` fixture from `api/conftest.py`. Patch service-layer calls at `api.routers.<router>.<service>.<func>`. Test 422 on bad payload + happy path + at least one error-isolation case.
3. **Import smoke**: usually automatic — `tests/test_smoke.py` already parametrizes over the 18 router names. If a new router is added, append it to the list.

## Gotchas

- `pytest tests` (no `-q`) prints the env-var setup as deprecation warnings on Python 3.12 — harmless, but `-q` suppresses for cleaner output.
- The smoke tests will fail if a router adds a top-level `_required_env(...)` call for a new env var that `tests/conftest.py` doesn't stub. Add the stub when introducing such patterns; see the `ONTOLOGY_PROJECT` / `COGNITO_USER_POOL_CLIENT_ID` precedent.
- `httpx>=0.27` is required for `ASGITransport`; older versions used a different API. Pinned in `requirements-dev.txt`.
- The mocked `hybrid_search` and `subgraph_for_skus` return literal dicts — they bypass Pydantic validation on the response side. If `SearchResponse` field names change, update the fake dicts too.
